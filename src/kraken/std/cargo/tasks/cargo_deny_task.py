import subprocess
from pathlib import Path
from typing import Optional, Sequence

from kraken.core import Task, TaskStatus
from kraken.core.api import Property


class CargoDenyTask(Task):
    description = "Executes cargo deny to verify dependencies."
    checks: Property[Optional[Sequence[str]]] = Property.default(None)
    config_file: Property[Optional[Path]] = Property.default(None)

    def execute(self) -> TaskStatus:
        command = ["cargo", "deny", "check"]

        config_file = self.config_file.get()
        if config_file is not None:
            command.extend(["--config", str(config_file.absolute())])

        checks = self.checks.get()
        if checks is not None:
            command.extend(checks)

        result = subprocess.run(command)
        return TaskStatus.from_exit_code(command, result.returncode)
