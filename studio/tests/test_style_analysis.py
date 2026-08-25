from __future__ import annotations

import json

from podcast_studio.style_analysis import StyleFingerprint, compare_fingerprints, fingerprint_plan


def _plan(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(
            {
                "duration": 60.0,
                "segments": [
                    {"start": 0.0, "end": 12.0, "source": "a.mp4"},
                    {"start": 12.0, "end": 25.0, "source": "b.mp4"},
                    {"start": 25.0, "end": 42.0, "source": "a.mp4"},
                    {"start": 42.0, "end": 60.0, "source": "b.mp4"},
                ],
                "motion": [
                    {"type": "zoom", "start": 1.0, "end": 2.0, "from_scale": 1.0, "to_scale": 1.06},
                    {"type": "zoom", "start": 31.0, "end": 32.0, "from_scale": 1.0, "to_scale": 1.08},
                ],
                "captions": [
                    {"start": 0.0, "end": 2.0, "text": "Most people miss this"},
                    {"start": 2.0, "end": 4.0, "text": "because context changes it"},
                ],
                "overlays": [{"type": "text", "start": 0.0, "end": 3.0, "text": "The Real Problem"}],
                "broll": [{"type": "broll", "start": 20.0, "end": 26.0}],
                "proof": [{"type": "proof", "start": 35.0, "end": 41.0}],
                "audio_events": [{"type": "sfx", "start": 0.3, "end": 0.5}],
                "transitions": [{"start": 12.0, "end": 12.2}],
            }
        )
    )
    return path


def test_plan_fingerprint_measures_coordinated_edit_dynamics(tmp_path):
    fingerprint = fingerprint_plan(_plan(tmp_path))
    assert fingerprint.duration == 60.0
    assert fingerprint.cuts_per_minute == 3.0
    assert fingerprint.zooms_per_minute == 2.0
    assert fingerprint.text_events_per_minute == 1.0
    assert fingerprint.broll_coverage == 0.1
    assert fingerprint.proof_events_per_minute == 1.0
    assert fingerprint.average_zoom_delta == 0.07


def test_style_comparison_returns_actionable_gap_ordering(tmp_path):
    candidate = fingerprint_plan(_plan(tmp_path))
    reference = StyleFingerprint(
        duration=60.0,
        cuts_per_minute=8.0,
        median_shot_seconds=6.0,
        zooms_per_minute=5.0,
        text_events_per_minute=3.0,
        broll_events_per_minute=2.0,
        proof_events_per_minute=1.0,
        sfx_events_per_minute=1.0,
        average_zoom_delta=0.07,
        caption_words_per_group=4.0,
        caption_changes_per_minute=12.0,
    )
    comparison = compare_fingerprints(reference, candidate)
    assert 0 <= comparison["style_match_score"] < 100
    assert comparison["comparisons"][0]["normalized_distance"] >= comparison["comparisons"][-1]["normalized_distance"]
    assert any("cut frequency" in item for item in comparison["recommendations"])
