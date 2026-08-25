from __future__ import annotations

import json

import pytest

from podcast_studio.exceptions import ValidationError
from podcast_studio.publish import PublishingPackage, build_package, save_package


def _transcript(tmp_path):
    path = tmp_path / "transcript.json"
    path.write_text(
        json.dumps(
            {
                "asset_id": "source",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 12.0,
                        "text": "Most people misunderstand what this measurement actually means.",
                    },
                    {
                        "start": 12.0,
                        "end": 27.0,
                        "text": "The result may change with timing, context, and who was included in the study.",
                    },
                    {
                        "start": 27.0,
                        "end": 44.0,
                        "text": "So the practical takeaway is to verify the measurement before changing the plan.",
                    },
                ],
            }
        )
    )
    return path


def test_deterministic_publish_package_is_platform_ready(tmp_path):
    package = build_package(_transcript(tmp_path))
    assert package.title
    assert len(package.platform_copy["x"]) <= 280
    assert package.chapters[0].time == 0.0
    assert all(0 <= item["source_time"] <= 44 for item in package.thumbnail_concepts)
    assert any("uncertainty" in note.lower() for note in package.integrity_notes)
    assert any(tag.startswith("#") for tag in package.hashtags)


def test_save_package_writes_complete_json(tmp_path):
    package = build_package(_transcript(tmp_path), title_hint="What This Measurement Really Means")
    output = save_package(package, tmp_path / "publish.json")
    payload = json.loads(output.read_text())
    assert payload["title"] == "What This Measurement Really Means"
    assert set(payload["platform_copy"]) == {"youtube_shorts", "instagram_reels", "tiktok", "linkedin", "x"}


def test_fidelity_gate_rejects_invented_numbers(monkeypatch, tmp_path):
    from podcast_studio import publish

    bad = PublishingPackage(
        title="This works 99% of the time",
        alternate_titles=["Bad title"],
        description="Unsupported 99% result.",
        short_caption="99% result",
        chapters=[],
        hashtags=[],
        thumbnail_concepts=[],
        platform_copy={"youtube_shorts": "", "instagram_reels": "", "tiktok": "", "linkedin": "", "x": ""},
        source_range={"start": 0.0, "end": 44.0},
    )
    with pytest.raises(ValidationError):
        publish._validate_fidelity(bad, "No numbers appear here.")
