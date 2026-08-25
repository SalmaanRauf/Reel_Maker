from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .agent import available_agents
from .transcription import available_engines


@dataclass(slots=True, frozen=True)
class Check:
    name: str
    status: str
    detail: str
    required: bool = False

    @property
    def passed(self) -> bool:
        return self.status in {"ok", "available"}

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "status": self.status, "detail": self.detail, "required": self.required}


def run_doctor(*, project: str | Path | None = None) -> list[Check]:
    checks: list[Check] = []
    checks.extend(_binary_checks())
    checks.extend(_python_checks())
    checks.extend(_agent_checks())
    checks.extend(_transcription_checks())
    checks.append(
        Check(
            "platform",
            "ok",
            f"{platform.system()} {platform.release()} / {platform.machine()} / Python {platform.python_version()}",
        )
    )
    if project is not None:
        checks.extend(_project_checks(Path(project).expanduser().resolve()))
    api_keys = sorted(
        name
        for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY")
        if os.environ.get(name)
    )
    checks.append(
        Check(
            "subscription isolation",
            "warning" if api_keys else "ok",
            "API keys are present but will be stripped from agent child processes: " + ", ".join(api_keys)
            if api_keys
            else "No metered API credentials detected in the current environment.",
        )
    )
    return checks


def doctor_exit_code(checks: Iterable[Check]) -> int:
    return 1 if any(check.required and not check.passed for check in checks) else 0


def format_doctor(checks: Iterable[Check], *, json_output: bool = False) -> str:
    materialized = list(checks)
    if json_output:
        return json.dumps(
            {
                "ok": doctor_exit_code(materialized) == 0,
                "checks": [item.to_dict() for item in materialized],
            },
            indent=2,
        )
    icons = {"ok": "PASS", "available": "PASS", "warning": "WARN", "missing": "MISS", "error": "FAIL"}
    width = max((len(item.name) for item in materialized), default=0)
    lines = [f"[{icons.get(item.status, item.status.upper())}] {item.name:<{width}}  {item.detail}" for item in materialized]
    lines.append("")
    lines.append("Ready for local editing." if doctor_exit_code(materialized) == 0 else "Required dependencies are missing.")
    return "\n".join(lines)


def _binary_checks() -> list[Check]:
    checks: list[Check] = []
    for name, required in (("ffmpeg", True), ("ffprobe", True), ("git", False)):
        path = shutil.which(name)
        if not path:
            checks.append(Check(name, "missing", "Not found on PATH", required=required))
            continue
        version = _version_line([path, "-version"])
        checks.append(Check(name, "ok", f"{path} — {version}", required=required))
    return checks


def _python_checks() -> list[Check]:
    packages = (
        ("numpy", "sync", False),
        ("cv2", "vision", False),
        ("mlx_whisper", "Apple Silicon transcription", False),
        ("faster_whisper", "cross-platform transcription", False),
    )
    return [
        Check(label, "available" if importlib.util.find_spec(module) else "missing", module, required=required)
        for module, label, required in packages
    ]


def _agent_checks() -> list[Check]:
    checks = []
    for name, path in available_agents().items():
        checks.append(
            Check(
                f"{name} subscription CLI",
                "available" if path else "missing",
                path or f"Install and sign in to {name}; at least one agent is recommended.",
            )
        )
    if not any(item.passed for item in checks):
        checks.append(Check("editorial agent", "warning", "Neither Claude Code nor Codex was found; deterministic editing remains available."))
    return checks


def _transcription_checks() -> list[Check]:
    engines = available_engines()
    checks = [Check(f"transcription:{item.name}", "available" if item.available else "missing", item.detail) for item in engines]
    if not any(item.available for item in engines):
        checks.append(Check("local transcription", "warning", "Install at least one transcription extra before running automatic transcription."))
    return checks


def _project_checks(project: Path) -> list[Check]:
    checks = [Check("project path", "ok" if project.is_dir() else "error", str(project), required=True)]
    if not project.is_dir():
        return checks
    project_file = project / "project.json"
    checks.append(Check("project manifest", "ok" if project_file.is_file() else "missing", str(project_file), required=True))
    for directory in ("sources", "analysis", "plans", "renders", "review"):
        path = project / directory
        checks.append(Check(f"project:{directory}", "ok" if path.is_dir() else "warning", str(path)))
    return checks


def _version_line(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        return (result.stdout or result.stderr).splitlines()[0][:160]
    except Exception as exc:  # pragma: no cover - diagnostic only
        return f"version unavailable: {exc}"
