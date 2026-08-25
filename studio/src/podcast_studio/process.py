from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .exceptions import CommandError, DependencyError


@dataclass(slots=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def command_string(self) -> str:
        return shlex.join(self.args)


def which(name: str) -> str | None:
    return shutil.which(name)


def require_binary(name: str) -> str:
    result = which(name)
    if not result:
        raise DependencyError(f"Required executable '{name}' was not found on PATH")
    return result


def run_command(
    args: Sequence[str | Path],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    unset_env: Sequence[str] = (),
    stdin: str | bytes | None = None,
    timeout: float | None = None,
    check: bool = True,
) -> CommandResult:
    command = [str(item) for item in args]
    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(key): str(value) for key, value in env.items()})
    for key in unset_env:
        merged_env.pop(str(key), None)
    text_mode = not isinstance(stdin, bytes)
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=merged_env,
            input=stdin,
            capture_output=True,
            text=text_mode,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DependencyError(f"Executable not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        raise CommandError(
            f"Command timed out after {timeout}s: {shlex.join(command)}",
            command=command,
            stderr=stderr,
        ) from exc
    stdout = completed.stdout.decode(errors="replace") if isinstance(completed.stdout, bytes) else completed.stdout
    stderr = completed.stderr.decode(errors="replace") if isinstance(completed.stderr, bytes) else completed.stderr
    result = CommandResult(command, completed.returncode, stdout or "", stderr or "")
    if check and result.returncode != 0:
        tail = result.stderr[-4000:].strip()
        raise CommandError(
            f"Command failed with exit code {result.returncode}: {result.command_string}\n{tail}",
            command=command,
            stderr=result.stderr,
        )
    return result
