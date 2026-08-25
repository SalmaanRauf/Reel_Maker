from __future__ import annotations

import json

from podcast_studio.capture import _extension_for, _load_script, _safe_stem, _unique_path


def test_capture_filename_is_sanitized_and_bounded(tmp_path):
    assert _safe_stem("../../My Great Take #1.mov") == "My-Great-Take-1"
    assert len(_safe_stem("a" * 200)) == 96


def test_capture_extension_uses_browser_media_type():
    assert _extension_for("video/webm") == ".webm"
    assert _extension_for("video/mp4") == ".mp4"


def test_loads_teleprompter_script_from_json(tmp_path):
    path = tmp_path / "script.json"
    path.write_text(json.dumps({"full_script": "Read this naturally."}))
    assert _load_script(path) == "Read this naturally."


def test_unique_capture_path_never_overwrites(tmp_path):
    path = tmp_path / "take.webm"
    path.write_bytes(b"one")
    candidate = _unique_path(path)
    assert candidate.name == "take-2.webm"
