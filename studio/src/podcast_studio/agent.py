from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import DependencyError, ValidationError
from .process import run_command

_CLOUD_CREDENTIALS = {
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "ANTHROPIC_BEDROCK_BASE_URL",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
}


@dataclass(slots=True, frozen=True)
class AgentResult:
    provider: str
    text: str
    structured: Any | None
    command: list[str]
    subscription_mode: bool
    attempts: int


def available_agents() -> dict[str, str | None]:
    return {"claude": shutil.which("claude"), "codex": shutil.which("codex")}


def run_subscription_agent(
    provider: str,
    prompt: str,
    *,
    cwd: str | Path,
    schema: dict[str, Any] | None = None,
    timeout_seconds: float = 900,
    allow_api_credentials: bool = False,
) -> AgentResult:
    normalized = provider.strip().lower()
    executable = available_agents().get(normalized)
    if normalized not in {"claude", "codex"}:
        raise ValidationError("Agent provider must be `claude` or `codex`")
    if not executable:
        raise DependencyError(f"{normalized} CLI is not installed or not on PATH")
    project = Path(cwd).expanduser().resolve()
    if not project.is_dir():
        raise ValidationError(f"Agent working directory does not exist: {project}")
    environment = subscription_environment(allow_api_credentials=allow_api_credentials)
    disciplined_prompt = _structured_prompt(prompt, schema)

    candidates = _candidate_commands(normalized, executable, disciplined_prompt, schema)
    errors: list[str] = []
    for attempt, command in enumerate(candidates, 1):
        result = run_command(command, cwd=project, env=environment, timeout=timeout_seconds, check=False)
        if result.returncode != 0:
            errors.append(f"attempt {attempt}: {result.stderr[-800:]}")
            continue
        text = _extract_text(normalized, result.stdout)
        if not text.strip():
            errors.append(f"attempt {attempt}: agent returned no text")
            continue
        structured = None
        if schema is not None:
            try:
                structured = extract_json(text)
                validate_json_shape(structured, schema)
            except ValidationError as exc:
                errors.append(f"attempt {attempt}: {exc}")
                continue
        return AgentResult(normalized, text, structured, command, not allow_api_credentials, attempt)
    raise DependencyError(
        f"{normalized} could not complete the subscription-backed job. "
        + " | ".join(errors[-3:])
        + ". Confirm the CLI is signed in to your subscription."
    )


def subscription_environment(*, allow_api_credentials: bool = False) -> dict[str, str]:
    environment = dict(os.environ)
    if not allow_api_credentials:
        for name in _CLOUD_CREDENTIALS:
            environment.pop(name, None)
        environment["PODCAST_STUDIO_SUBSCRIPTION_ONLY"] = "1"
    environment.setdefault("NO_COLOR", "1")
    environment.setdefault("TERM", "dumb")
    return environment


def extract_json(text: str) -> Any:
    candidates = [text.strip()]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    candidates.extend(item.strip() for item in fenced)
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        for index, character in enumerate(candidate):
            if character not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[index:])
                return value
            except json.JSONDecodeError:
                continue
    raise ValidationError("Agent response did not contain valid JSON")


def validate_json_shape(value: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    expected = schema.get("type")
    if isinstance(expected, list):
        valid = any(_matches_type(value, item) for item in expected)
    else:
        valid = expected is None or _matches_type(value, expected)
    if not valid:
        raise ValidationError(f"{path} must be {expected}, got {type(value).__name__}")
    if expected == "object" or (isinstance(value, dict) and expected is None):
        for required in schema.get("required", []):
            if required not in value:
                raise ValidationError(f"{path}.{required} is required")
        properties = schema.get("properties", {})
        for key, child in properties.items():
            if key in value:
                validate_json_shape(value[key], child, path=f"{path}.{key}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ValidationError(f"{path} contains unknown keys: {', '.join(unknown)}")
    if expected == "array" and isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if minimum is not None and len(value) < minimum:
            raise ValidationError(f"{path} requires at least {minimum} items")
        if maximum is not None and len(value) > maximum:
            raise ValidationError(f"{path} permits at most {maximum} items")
        child_schema = schema.get("items")
        if child_schema:
            for index, item in enumerate(value):
                validate_json_shape(item, child_schema, path=f"{path}[{index}]")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if schema.get("minimum") is not None and value < schema["minimum"]:
            raise ValidationError(f"{path} is below minimum {schema['minimum']}")
        if schema.get("maximum") is not None and value > schema["maximum"]:
            raise ValidationError(f"{path} exceeds maximum {schema['maximum']}")
    if isinstance(value, str) and schema.get("enum") and value not in schema["enum"]:
        raise ValidationError(f"{path} must be one of {schema['enum']}")


def _candidate_commands(provider: str, executable: str, prompt: str, schema: dict[str, Any] | None) -> list[list[str]]:
    if provider == "claude":
        return [
            [executable, "-p", prompt, "--output-format", "json"],
            [executable, "-p", prompt],
        ]
    commands: list[list[str]] = []
    if schema:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(schema, handle)
            schema_path = handle.name
        commands.append([executable, "exec", "--json", "--sandbox", "read-only", "--output-schema", schema_path, prompt])
    commands.extend(
        [
            [executable, "exec", "--json", "--sandbox", "read-only", prompt],
            [executable, "exec", "--sandbox", "read-only", prompt],
        ]
    )
    return commands


def _extract_text(provider: str, stdout: str) -> str:
    raw = stdout.strip()
    if not raw:
        return ""
    if provider == "claude":
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                result = payload.get("result") or payload.get("text") or payload.get("content")
                if isinstance(result, str):
                    return result
        except json.JSONDecodeError:
            return raw
        return raw

    pieces: list[str] = []
    parsed_any = False
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        parsed_any = True
        if not isinstance(event, dict):
            continue
        item = event.get("item") if isinstance(event.get("item"), dict) else event
        event_type = str(item.get("type") or event.get("type") or "")
        if event_type in {"agent_message", "message", "assistant_message"}:
            text = item.get("text") or item.get("content")
            if isinstance(text, str):
                pieces.append(text)
        elif event_type.endswith("completed"):
            text = item.get("text") or item.get("result")
            if isinstance(text, str):
                pieces.append(text)
    return "\n".join(pieces).strip() if parsed_any and pieces else raw


def _structured_prompt(prompt: str, schema: dict[str, Any] | None) -> str:
    if schema is None:
        return prompt
    return (
        f"{prompt.rstrip()}\n\n"
        "Return exactly one JSON value and no markdown, commentary, or code fence. "
        "It must validate against this JSON Schema:\n"
        f"{json.dumps(schema, indent=2, sort_keys=True)}"
    )


def _matches_type(value: Any, expected: str | None) -> bool:
    return {
        None: True,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)
