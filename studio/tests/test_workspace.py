from __future__ import annotations

from pathlib import Path

from podcast_studio.workspace import (
    add_assets,
    initialize_workspace,
    load_manifest,
    project_summary,
    resolve_asset,
)


def test_workspace_initialization_is_idempotent(tmp_path):
    root = tmp_path / "episode"
    first = initialize_workspace(root, name="Episode One")
    second = initialize_workspace(root, name="Ignored")
    assert first["id"] == "episode-one"
    assert second["name"] == "Episode One"
    assert (root / "analysis" / "transcripts").is_dir()
    assert (root / "renders" / "final").is_dir()


def test_add_reference_asset_and_resolve(monkeypatch, tmp_path):
    root = tmp_path / "episode"
    initialize_workspace(root)
    source = tmp_path / "camera.mp4"
    source.write_bytes(b"not-real-media")
    monkeypatch.setattr(
        "podcast_studio.workspace.probe_media",
        lambda path, ffprobe="ffprobe": {"duration": 42.0, "video": {"width": 1920, "height": 1080}, "audio": {"channels": 2}},
    )
    assets = add_assets(root, [source], role="camera", mode="reference")
    assert len(assets) == 1
    asset, path = resolve_asset(root, assets[0]["id"])
    assert path == source.resolve()
    assert asset["probe"]["duration"] == 42.0
    assert project_summary(root)["asset_count"] == 1


def test_copy_mode_keeps_source_immutable(monkeypatch, tmp_path):
    root = tmp_path / "episode"
    initialize_workspace(root)
    source = tmp_path / "audio.wav"
    source.write_bytes(b"source-bytes")
    monkeypatch.setattr("podcast_studio.workspace.probe_media", lambda path, ffprobe="ffprobe": {"duration": 1.0})
    asset = add_assets(root, [source], role="audio", mode="copy")[0]
    copied = root / asset["path"]
    assert copied.read_bytes() == b"source-bytes"
    copied.write_bytes(b"derived-change")
    assert source.read_bytes() == b"source-bytes"
