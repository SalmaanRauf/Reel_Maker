from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from .exceptions import ValidationError


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def slugify(value: str, fallback: str = "item") -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value or fallback


def stable_id(prefix: str, *parts: object, length: int = 12) -> str:
    raw = "\x1f".join(str(part) for part in parts).encode()
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:length]}"


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def dump_json(value: Any, path: str | Path, *, indent: int = 2) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=indent, ensure_ascii=False, default=json_default) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return destination


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def seconds_to_srt(seconds: float) -> str:
    millis = round(max(0.0, seconds) * 1000)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def seconds_to_vtt(seconds: float) -> str:
    return seconds_to_srt(seconds).replace(",", ".")


def seconds_to_timecode(seconds: float, fps: float = 30.0) -> str:
    total_frames = round(max(0.0, seconds) * fps)
    frame_base = max(1, round(fps))
    frames = total_frames % frame_base
    total_seconds = total_frames // frame_base
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"


def parse_timestamp(value: str) -> float:
    match = re.fullmatch(r"\s*(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})\s*", value)
    if not match:
        raise ValidationError(f"Invalid timestamp: {value!r}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    millis = int(match.group(4).ljust(3, "0"))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def pairwise(values: Iterable[Any]) -> Iterator[tuple[Any, Any]]:
    iterator = iter(values)
    try:
        previous = next(iterator)
    except StopIteration:
        return
    for current in iterator:
        yield previous, current
        previous = current


def safe_resolve(path: str | Path, root: str | Path) -> Path:
    root_path = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValidationError(f"Path escapes project root: {path}") from exc
    return candidate


def finite(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValidationError(f"{name} must be finite")
    return result
