from __future__ import annotations

import json

from podcast_studio.interchange import export_edl, export_fcpxml, extract_clips


def _plan(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(
            {
                "segments": [
                    {"id": "a", "source": "camera-a.mp4", "start": 10.0, "end": 13.0},
                    {"id": "b", "source": "camera-b.mp4", "start": 20.0, "end": 24.0},
                ]
            }
        )
    )
    return path


def test_extracts_linear_timeline_when_offsets_are_implicit(tmp_path):
    clips = extract_clips(json.loads(_plan(tmp_path).read_text()))
    assert clips[0].timeline_in == 0.0
    assert clips[0].timeline_out == 3.0
    assert clips[1].timeline_in == 3.0
    assert clips[1].timeline_out == 7.0


def test_exports_cmx_edl(tmp_path):
    output = export_edl(_plan(tmp_path), tmp_path / "edit.edl", fps=30)
    text = output.read_text()
    assert "TITLE: plan" in text
    assert "00:00:10:00 00:00:13:00" in text
    assert "* SOURCE FILE: camera-a.mp4" in text


def test_exports_fcpxml(tmp_path):
    output = export_fcpxml(_plan(tmp_path), tmp_path / "edit.fcpxml", fps=30)
    text = output.read_text()
    assert "<fcpxml" in text
    assert "asset-clip" in text
    assert "Podcast Studio" in text
