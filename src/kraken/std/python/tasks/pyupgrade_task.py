from __future__ import annotations

import dataclasses
from difflib import unified_diff
from pathlib import Path
from sys import stdout
from tempfile import TemporaryDirectory
from typing import Any, Collection, Iterable, List

from kraken.core import TaskStatus
from kraken.core.api import Project, Property

from .. import python_settings
from .base_task import EnvironmentAwareDispatchTask


class PyUpgradeTask(EnvironmentAwareDispatchTask):
    description = "Upgrades to newer Python syntax sugars with pyupgrade."
    python_dependencies = ["pyupgrade"]

    keep_runtime_typing: Property[bool] = Property.config(default=False)
    additional_files: Property[List[Path]] = Property.config(default_factory=list)
    python_version: Property[str]

    # EnvironmentAwareDispatchTask

    def get_execute_command(self) -> List[str]:
        return self.run_pyupgrade(self.additional_files.get(), ("--exit-zero-even-if-changed",))

    def run_pyupgrade(self, files: Iterable[Path], extra: Iterable[str]) -> List[str]:
        command = ["pyupgrade", f"--py{self.python_version.get_or('3').replace('.', '')}-plus", *extra]
        if self.keep_runtime_typing.get():
            command.append("--keep-runtime-typing")
        command.extend(str(f) for f in files)
        return command


class PyUpgradeCheckTask(PyUpgradeTask):
    description = "Check Python source files syntax sugars with pyupgrade."
    python_dependencies = ["pyupgrade"]

    keep_runtime_typing: Property[bool] = Property.config(default=False)
    additional_files: Property[List[Path]] = Property.config(default_factory=list)
    python_version: Property[str]

    def execute(self) -> TaskStatus:
        # We copy the file because there is no way to make pyupgrade not edit the files
        old_dir = self.settings.project.directory.resolve()
        new_file_for_old_file = {}
        with TemporaryDirectory() as new_dir:
            for file in self.additional_files.get():
                new_file = new_dir / file.resolve().relative_to(old_dir)
                new_file.parent.mkdir(parents=True, exist_ok=True)
                new_file.write_bytes(file.read_bytes())
                new_file_for_old_file[file] = new_file
            self._files = new_file_for_old_file.values()

            result = super().execute()
            if not result.is_failed():
                return result  # nothing more to do

            # We print a diff
            for old_file, new_file in new_file_for_old_file.items():
                old_content = old_file.read_text()
                new_content = new_file.read_text()
                if old_content != new_content:
                    stdout.writelines(
                        unified_diff(
                            old_content.splitlines(keepends=True),
                            new_content.splitlines(keepends=True),
                            fromfile=str(old_file),
                            tofile=str(old_file),
                            n=5,
                        )
                    )
            return result

    def get_execute_command(self) -> List[str]:
        return self.run_pyupgrade(self._files, ())


@dataclasses.dataclass
class PyUpgradeTasks:
    check: PyUpgradeTask
    format: PyUpgradeTask


def pyupgrade(
    *,
    name: str = "python.pyupgrade",
    project: Project | None = None,
    exclude: Collection[Path] = (),
    exclude_patterns: Collection[str] = (),
    **kwargs: Any,
) -> PyUpgradeTasks:
    project = project or Project.current()
    settings = python_settings(project)

    directories = [
        p
        for p in (*kwargs.pop("additional_files", ()), settings.source_directory, settings.get_tests_directory())
        if p is not None
    ]
    files = {f.resolve() for p in directories for f in Path(p).glob("**/*.py")}
    exclude = [e.resolve() for e in exclude]
    filtered_files = [
        f
        for f in files
        if not any(_is_relative_to(f, i) for i in exclude) and not any(f.match(p) for p in exclude_patterns)
    ]

    check_task = project.do(
        f"{name}.check", PyUpgradeCheckTask, group="lint", **kwargs, additional_files=filtered_files
    )
    format_task = project.do(name, PyUpgradeTask, group="fmt", default=False, **kwargs, additional_files=filtered_files)
    return PyUpgradeTasks(check_task, format_task)


def _is_relative_to(a: Path, b: Path) -> bool:
    # Polyfill for Python 3.7 and 3.8
    try:
        a.relative_to(b)
        return True
    except ValueError:
        return False
