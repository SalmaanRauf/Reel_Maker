from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .exceptions import ValidationError
from .process import run_command
from .util import dump_json, slugify

SCHEMA_VERSION = 1
DIRECTORIES = (
    "sources",
    "analysis",
    "analysis/transcripts",
    "analysis/frames",
    "analysis/waveforms",
    "analysis/reframe",
    "analysis/sync",
    "plans",
    "renders/previews",
    "renders/final",
    "review",
    "publish",
    "cache",
    "logs",
)


def initialize_workspace(root: str | Path, *, name: str | None = None, force: bool = False) -> dict[str, Any]:
    path = Path(root).expanduser().resolve()
    manifest_path = path / "project.json"
    if manifest_path.exists() and not force:
        return load_manifest(path)
    path.mkdir(parents=True, exist_ok=True)
    for directory in DIRECTORIES:
        (path / directory).mkdir(parents=True, exist_ok=True)
    now = _now()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "id": slugify(name or path.name),
        "name": name or path.name,
        "created_at": now,
        "updated_at": now,
        "assets": [],
        "transcripts": [],
        "plans": [],
        "renders": [],
        "settings": {
            "default_style": "authority",
            "default_aspect_ratio": "9:16",
            "subscription_only": True,
            "allow_unlicensed_media": False,
        },
    }
    dump_json(manifest, manifest_path)
    _write_gitignore(path)
    return manifest


def load_manifest(root: str | Path) -> dict[str, Any]:
    path = Path(root).expanduser().resolve() / "project.json"
    if not path.is_file():
        raise ValidationError(f"Not a Podcast Studio workspace: {path.parent}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("assets"), list):
        raise ValidationError(f"Invalid project manifest: {path}")
    return payload


def save_manifest(root: str | Path, manifest: dict[str, Any]) -> Path:
    manifest["updated_at"] = _now()
    return dump_json(manifest, Path(root).expanduser().resolve() / "project.json")


def add_assets(
    root: str | Path,
    sources: Iterable[str | Path],
    *,
    role: str = "camera",
    mode: str = "reference",
    label: str | None = None,
    ffprobe: str = "ffprobe",
) -> list[dict[str, Any]]:
    workspace = Path(root).expanduser().resolve()
    manifest = load_manifest(workspace)
    if mode not in {"reference", "copy", "symlink", "hardlink"}:
        raise ValidationError("Asset mode must be reference, copy, symlink, or hardlink")
    created: list[dict[str, Any]] = []
    existing_paths = {str(item.get("path")) for item in manifest["assets"]}
    for source_value in sources:
        source = Path(source_value).expanduser().resolve()
        if not source.is_file():
            raise ValidationError(f"Source media not found: {source}")
        destination = source
        if mode != "reference":
            destination = _materialize_source(workspace, source, mode)
        stored_path = _portable_path(workspace, destination)
        if stored_path in existing_paths:
            created.append(next(item for item in manifest["assets"] if item.get("path") == stored_path))
            continue
        probe = probe_media(destination, ffprobe=ffprobe)
        fingerprint = _fingerprint(source)
        asset_id = f"{slugify(label or source.stem)[:36]}-{fingerprint[:8]}"
        asset = {
            "id": asset_id,
            "label": label or source.stem,
            "role": role,
            "path": stored_path,
            "original_path": str(source),
            "storage_mode": mode,
            "fingerprint": fingerprint,
            "size_bytes": source.stat().st_size,
            "added_at": _now(),
            "probe": probe,
        }
        manifest["assets"].append(asset)
        existing_paths.add(stored_path)
        created.append(asset)
    save_manifest(workspace, manifest)
    return created


def resolve_asset(root: str | Path, asset_id: str) -> tuple[dict[str, Any], Path]:
    workspace = Path(root).expanduser().resolve()
    manifest = load_manifest(workspace)
    matches = [item for item in manifest["assets"] if item.get("id") == asset_id]
    if not matches:
        partial = [item for item in manifest["assets"] if str(item.get("id", "")).startswith(asset_id)]
        matches = partial if len(partial) == 1 else []
    if not matches:
        raise ValidationError(f"Unknown asset: {asset_id}")
    asset = matches[0]
    path = Path(str(asset["path"]))
    if not path.is_absolute():
        path = workspace / path
    if not path.is_file():
        original = Path(str(asset.get("original_path", ""))).expanduser()
        if original.is_file():
            path = original.resolve()
        else:
            raise ValidationError(f"Asset is offline: {asset_id} ({path})")
    return asset, path.resolve()


def probe_media(path: str | Path, *, ffprobe: str = "ffprobe") -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    result = run_command(
        [
            ffprobe, "-v", "error", "-show_format", "-show_streams", "-print_format", "json", str(source),
        ],
        check=False,
    )
    if result.returncode != 0:
        raise ValidationError(f"ffprobe failed for {source}: {result.stderr[-1000:]}")
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    format_payload = payload.get("format", {})
    duration = _float(format_payload.get("duration"))
    if duration is None:
        duration = max((_float(item.get("duration")) or 0.0 for item in streams), default=0.0)
    return {
        "duration": duration,
        "format": format_payload.get("format_name"),
        "bit_rate": _int(format_payload.get("bit_rate")),
        "video": _stream_summary(video),
        "audio": _stream_summary(audio),
    }


def register_artifact(root: str | Path, category: str, payload: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(root).expanduser().resolve()
    manifest = load_manifest(workspace)
    mapping = {"transcript": "transcripts", "plan": "plans", "render": "renders"}
    key = mapping.get(category, category)
    if key not in manifest or not isinstance(manifest[key], list):
        manifest[key] = []
    artifact = dict(payload)
    artifact.setdefault("created_at", _now())
    manifest[key].append(artifact)
    save_manifest(workspace, manifest)
    return artifact


def project_summary(root: str | Path) -> dict[str, Any]:
    workspace = Path(root).expanduser().resolve()
    manifest = load_manifest(workspace)
    offline: list[str] = []
    duration = 0.0
    for asset in manifest["assets"]:
        path = Path(str(asset["path"]))
        if not path.is_absolute():
            path = workspace / path
        if not path.exists() and not Path(str(asset.get("original_path", ""))).exists():
            offline.append(str(asset.get("id")))
        duration += float(asset.get("probe", {}).get("duration") or 0.0)
    return {
        "root": str(workspace),
        "id": manifest.get("id"),
        "name": manifest.get("name"),
        "asset_count": len(manifest["assets"]),
        "total_source_seconds": duration,
        "transcript_count": len(manifest.get("transcripts", [])),
        "plan_count": len(manifest.get("plans", [])),
        "render_count": len(manifest.get("renders", [])),
        "offline_assets": offline,
        "settings": manifest.get("settings", {}),
    }


def _materialize_source(workspace: Path, source: Path, mode: str) -> Path:
    target = workspace / "sources" / source.name
    if target.exists():
        if _fingerprint(target) == _fingerprint(source):
            return target
        target = workspace / "sources" / f"{source.stem}-{_fingerprint(source)[:8]}{source.suffix}"
    if mode == "copy":
        shutil.copy2(source, target)
    elif mode == "symlink":
        target.symlink_to(source)
    elif mode == "hardlink":
        try:
            os.link(source, target)
        except OSError as exc:
            raise ValidationError(f"Unable to hardlink {source}; use copy or reference mode") from exc
    return target


def _portable_path(workspace: Path, path: Path) -> str:
    try:
        return str(path.relative_to(workspace))
    except ValueError:
        return str(path)


def _fingerprint(path: Path, *, sample_bytes: int = 1024 * 1024) -> str:
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(stat.st_size).encode())
    with path.open("rb") as handle:
        digest.update(handle.read(sample_bytes))
        if stat.st_size > sample_bytes:
            handle.seek(max(0, stat.st_size - sample_bytes))
            digest.update(handle.read(sample_bytes))
    return digest.hexdigest()


def _stream_summary(stream: dict[str, Any] | None) -> dict[str, Any] | None:
    if not stream:
        return None
    return {
        "codec": stream.get("codec_name"),
        "profile": stream.get("profile"),
        "width": _int(stream.get("width")),
        "height": _int(stream.get("height")),
        "frame_rate": stream.get("avg_frame_rate") or stream.get("r_frame_rate"),
        "sample_rate": _int(stream.get("sample_rate")),
        "channels": _int(stream.get("channels")),
        "channel_layout": stream.get("channel_layout"),
        "duration": _float(stream.get("duration")),
    }


def _write_gitignore(root: Path) -> None:
    path = root / ".gitignore"
    if path.exists():
        return
    path.write_text(
        "cache/\nlogs/\nrenders/\nreview/decisions.jsonl\n*.tmp\n.DS_Store\n",
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
