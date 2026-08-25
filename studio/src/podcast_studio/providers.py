from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .exceptions import DependencyError, ValidationError
from .process import run_command
from .util import dump_json

_SENSITIVE_SCOPES = {"voice-clone", "identity-manipulation", "digital-replica"}


@dataclass(slots=True, frozen=True)
class ConsentReceipt:
    subject: str
    scope: str
    granted_at: str
    evidence: str
    expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "scope": self.scope,
            "granted_at": self.granted_at,
            "evidence": self.evidence,
            "expires_at": self.expires_at,
        }


@dataclass(slots=True, frozen=True)
class ProviderResult:
    provider: str
    output: str
    command: list[str]
    network_allowed: bool
    receipt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "output": self.output,
            "command": self.command,
            "network_allowed": self.network_allowed,
            "receipt": self.receipt,
        }


def load_providers(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValidationError(f"Provider configuration not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    providers = payload.get("providers") if isinstance(payload, dict) else None
    if not isinstance(providers, dict):
        raise ValidationError("Provider configuration requires a `providers` object")
    return providers


def write_consent(
    directory: str | Path,
    *,
    subject: str,
    scope: str,
    evidence: str,
    expires_at: str | None = None,
) -> Path:
    if scope not in _SENSITIVE_SCOPES:
        raise ValidationError(f"Unknown consent scope: {scope}")
    if not subject.strip() or not evidence.strip():
        raise ValidationError("Consent subject and evidence are required")
    receipt = ConsentReceipt(
        subject=subject.strip(),
        scope=scope,
        granted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        evidence=evidence.strip(),
        expires_at=expires_at,
    )
    digest = hashlib.sha256(f"{subject}|{scope}|{receipt.granted_at}|{evidence}".encode()).hexdigest()[:12]
    destination = Path(directory).expanduser().resolve() / f"{scope}-{digest}.json"
    dump_json(receipt.to_dict(), destination)
    return destination


def run_provider(
    config_path: str | Path,
    provider_name: str,
    substitutions: Mapping[str, str | Path | int | float],
    *,
    receipts_dir: str | Path,
    consent_path: str | Path | None = None,
) -> ProviderResult:
    providers = load_providers(config_path)
    config = providers.get(provider_name)
    if not isinstance(config, dict):
        raise ValidationError(f"Unknown provider: {provider_name}")
    if not config.get("enabled", False):
        raise ValidationError(f"Provider `{provider_name}` is disabled")
    if config.get("mode") != "command":
        raise ValidationError("Only deterministic command providers are supported")
    command_template = config.get("command")
    if not isinstance(command_template, list) or not command_template or not all(isinstance(item, str) for item in command_template):
        raise ValidationError(f"Provider `{provider_name}` requires a command array")

    required_scope = config.get("required_consent_scope")
    if config.get("requires_consent") or required_scope:
        _validate_consent(consent_path, required_scope)

    command = [_substitute(item, substitutions) for item in command_template]
    executable = Path(command[0]).name
    allowed = {Path(str(item)).name for item in config.get("allowed_executables", [])}
    if not allowed or executable not in allowed:
        raise ValidationError(f"Provider executable `{executable}` is not allowlisted")
    resolved = shutil.which(command[0]) or shutil.which(executable)
    if not resolved:
        raise DependencyError(f"Provider executable not found: {command[0]}")
    command[0] = resolved

    output_raw = substitutions.get("output")
    if output_raw is None:
        raise ValidationError("Provider invocation requires an `output` substitution")
    output = Path(str(output_raw)).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    environment = dict(os.environ)
    network_allowed = bool(config.get("network_allowed", False))
    if not network_allowed:
        for key in list(environment):
            if any(token in key.upper() for token in ("API_KEY", "ACCESS_TOKEN", "SECRET_KEY")):
                environment.pop(key, None)
        environment["PODCAST_STUDIO_NETWORK_DISABLED"] = "1"
    timeout = float(config.get("timeout_seconds", 1800))
    result = run_command(command, env=environment, timeout=timeout, check=False)
    if result.returncode != 0:
        raise DependencyError(f"Provider `{provider_name}` failed: {result.stderr[-1600:]}")
    if not output.is_file() or output.stat().st_size == 0:
        raise ValidationError(f"Provider `{provider_name}` did not create a non-empty output: {output}")

    receipt_directory = Path(receipts_dir).expanduser().resolve()
    receipt_directory.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_directory / f"{provider_name}-{hashlib.sha256(str(output).encode()).hexdigest()[:12]}.receipt.json"
    receipt = {
        "provider": provider_name,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "command": command,
        "output": str(output),
        "output_sha256": _sha256(output),
        "network_allowed": network_allowed,
        "consent": str(Path(consent_path).resolve()) if consent_path else None,
        "substitutions": {key: str(value) for key, value in substitutions.items() if key not in {"script", "prompt"}},
    }
    dump_json(receipt, receipt_path)
    return ProviderResult(provider_name, str(output), command, network_allowed, str(receipt_path))


def _validate_consent(path: str | Path | None, required_scope: str | None) -> None:
    if not path:
        raise ValidationError(f"Provider requires explicit consent scope: {required_scope or 'unspecified'}")
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValidationError(f"Consent receipt not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if required_scope and payload.get("scope") != required_scope:
        raise ValidationError(f"Consent scope must be `{required_scope}`")
    if not payload.get("subject") or not payload.get("evidence") or not payload.get("granted_at"):
        raise ValidationError("Consent receipt is incomplete")
    expires_at = payload.get("expires_at")
    if expires_at:
        expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if expiry <= datetime.now(timezone.utc):
            raise ValidationError("Consent receipt has expired")


def _substitute(template: str, values: Mapping[str, str | Path | int | float]) -> str:
    try:
        return template.format_map({key: str(value) for key, value in values.items()})
    except KeyError as exc:
        raise ValidationError(f"Provider command is missing substitution: {exc.args[0]}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
