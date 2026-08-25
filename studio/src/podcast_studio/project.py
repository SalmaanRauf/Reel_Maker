from __future__ import annotations

import os
import shutil
from importlib import resources
from pathlib import Path
from typing import Any, Iterable

from .exceptions import ValidationError
from .models import AssetRole, MediaAsset, ProjectManifest
from .util import dump_json, load_json, sha256_file, slugify, stable_id, utc_now

PROJECT_DIRS = (
    "sources", "analysis", "transcripts", "plans", "renders", "qc", "captions",
    "assets", "generated", "receipts", ".cache"
)

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "editing": {
        "min_clip_seconds": 45,
        "max_clip_seconds": 120,
        "target_clip_seconds": 75,
        "silence_threshold_db": -38,
        "silence_min_seconds": 0.65,
        "preserved_gap_seconds": 0.22,
        "cut_padding_seconds": 0.08,
        "maximum_punch_in": 1.10,
        "default_aspect": "9:16",
    },
    "audio": {"target_lufs": -16, "true_peak_db": -1.5, "highpass_hz": 70, "denoise": False},
    "captions": {"font_family": "Arial", "font_size": 64, "max_words": 5, "max_chars": 32, "uppercase": False, "karaoke": True, "box": False},
    "agents": {"default": "heuristic", "max_context_chars": 600000, "subscription_only": True, "medical_guardrails": True},
    "providers_file": "providers.json",
}


class ProjectWorkspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.manifest_path = self.root / "project.json"
        self.config_path = self.root / "config.json"

    @classmethod
    def create(cls, root: str | Path, name: str | None = None, *, force: bool = False) -> "ProjectWorkspace":
        workspace = cls(root)
        if workspace.manifest_path.exists() and not force:
            raise ValidationError(f"Project already exists: {workspace.root}")
        workspace.root.mkdir(parents=True, exist_ok=True)
        for directory in PROJECT_DIRS:
            (workspace.root / directory).mkdir(parents=True, exist_ok=True)
        manifest = ProjectManifest(
            id=stable_id("project", workspace.root, name or workspace.root.name),
            name=name or workspace.root.name,
        )
        workspace.save_manifest(manifest)
        dump_json(DEFAULT_CONFIG, workspace.config_path)
        if not (workspace.root / "providers.json").exists():
            provider_template = resources.files("podcast_studio").joinpath("templates", "providers.example.json")
            dump_json(load_json_resource(provider_template), workspace.root / "providers.json")
        return workspace

    @classmethod
    def open(cls, root: str | Path) -> "ProjectWorkspace":
        workspace = cls(root)
        if not workspace.manifest_path.is_file():
            raise ValidationError(f"Not a podcast-studio project: {workspace.root}")
        return workspace

    def manifest(self) -> ProjectManifest:
        return ProjectManifest.from_dict(load_json(self.manifest_path))

    def save_manifest(self, manifest: ProjectManifest) -> Path:
        manifest.updated_at = utc_now()
        return dump_json(manifest.to_dict(), self.manifest_path)

    def config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return DEFAULT_CONFIG.copy()
        return _deep_merge(DEFAULT_CONFIG, load_json(self.config_path))

    def add_media(
        self,
        paths: Iterable[str | Path],
        *,
        role: AssetRole | str = AssetRole.CAMERA,
        mode: str = "reference",
        hash_source: bool = False,
        label: str | None = None,
    ) -> list[MediaAsset]:
        from .media import probe_media

        if mode not in {"reference", "copy", "symlink"}:
            raise ValidationError("mode must be reference, copy, or symlink")
        manifest = self.manifest()
        added: list[MediaAsset] = []
        source_paths = [Path(value).expanduser().resolve() for value in paths]
        for source in source_paths:
            if not source.is_file():
                raise ValidationError(f"Media file not found: {source}")
            stored = source
            if mode in {"copy", "symlink"}:
                token = stable_id("src", source, source.stat().st_size, length=8).split("_", 1)[1]
                stored = self.root / "sources" / f"{slugify(source.stem)}-{token}{source.suffix.lower()}"
                if not stored.exists():
                    if mode == "copy":
                        shutil.copy2(source, stored)
                    else:
                        try:
                            stored.symlink_to(source)
                        except OSError:
                            shutil.copy2(source, stored)
            probe = probe_media(stored)
            asset_id = stable_id("asset", source, source.stat().st_size, source.stat().st_mtime_ns)
            try:
                stored_path = str(stored.relative_to(self.root))
            except ValueError:
                stored_path = str(stored)
            asset = MediaAsset(
                id=asset_id,
                path=stored_path,
                role=AssetRole(role),
                duration=probe.duration,
                streams=probe.streams,
                label=label or source.stem,
                sha256=sha256_file(source) if hash_source else None,
                metadata={"format_name": probe.format_name, "size": source.stat().st_size, "source_path": str(source), "ingest_mode": mode},
            )
            manifest.upsert_asset(asset)
            added.append(asset)
        self.save_manifest(manifest)
        self.write_receipt("add_media", inputs=[str(path) for path in source_paths], outputs=[asset.path for asset in added], metadata={"asset_ids": [asset.id for asset in added], "mode": mode})
        return added

    def resolve_asset(self, asset_or_id: str | MediaAsset) -> tuple[MediaAsset, Path]:
        manifest = self.manifest()
        asset = asset_or_id if isinstance(asset_or_id, MediaAsset) else manifest.asset(asset_or_id)
        path = Path(asset.path).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if not path.exists():
            raise ValidationError(f"Asset is offline: {asset.id} -> {path}")
        return asset, path

    def resolve_project_path(self, value: str | Path, *, must_exist: bool = False) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if must_exist and not path.exists():
            raise ValidationError(f"Project file not found: {path}")
        return path

    def artifact_path(self, category: str, name: str, suffix: str) -> Path:
        if category not in PROJECT_DIRS:
            raise ValidationError(f"Unknown artifact category: {category}")
        path = self.root / category / f"{slugify(name)}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def latest(self, category: str, pattern: str = "*") -> Path | None:
        paths = [path for path in (self.root / category).glob(pattern) if path.is_file()]
        return max(paths, key=lambda path: path.stat().st_mtime_ns) if paths else None

    def write_json_artifact(self, category: str, name: str, value: Any) -> Path:
        return dump_json(value, self.artifact_path(category, name, ".json"))

    def write_receipt(self, action: str, *, inputs: list[str] | None = None, outputs: list[str] | None = None, command: list[str] | None = None, metadata: dict[str, Any] | None = None) -> Path:
        now = utc_now()
        receipt_id = stable_id("receipt", action, now, os.getpid())
        return dump_json({"id": receipt_id, "action": action, "created_at": now, "inputs": inputs or [], "outputs": outputs or [], "command": command or [], "metadata": metadata or {}}, self.root / "receipts" / f"{receipt_id}.json")

    def summary(self) -> dict[str, Any]:
        manifest = self.manifest()
        return {"root": str(self.root), "project": manifest.to_dict(), "artifacts": {category: len([path for path in (self.root / category).glob("*") if path.is_file()]) for category in PROJECT_DIRS}}


def load_json_resource(resource: Any) -> Any:
    import json

    return json.loads(resource.read_text(encoding="utf-8"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in base.items():
        if isinstance(value, dict):
            child = override.get(key, {}) if isinstance(override.get(key), dict) else {}
            merged[key] = _deep_merge(value, child)
        else:
            merged[key] = override.get(key, value)
    for key, value in override.items():
        if key not in merged:
            merged[key] = value
    return merged
