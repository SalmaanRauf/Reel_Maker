from __future__ import annotations

from podcast_studio.reframe import Box, FaceObservation, choose_layout, crop_dimensions, plan_reframe


def test_vertical_crop_dimensions_cover_source_height():
    width, height = crop_dimensions(1920, 1080, 1080, 1920)
    assert height == 1080.0
    assert round(width, 3) == 607.5


def test_dead_zone_reduces_crop_jitter():
    observations = [
        FaceObservation(time=0.0, box=Box(800, 180, 260, 260), confidence=0.95),
        FaceObservation(time=0.25, box=Box(805, 181, 260, 260), confidence=0.95),
        FaceObservation(time=0.5, box=Box(798, 178, 260, 260), confidence=0.95),
        FaceObservation(time=1.5, box=Box(1160, 200, 260, 260), confidence=0.95),
    ]
    plan = plan_reframe(observations, source_width=1920, source_height=1080)
    assert len(plan.keyframes) < len(observations)
    assert plan.keyframes[0].reason == "Acquire subject"
    assert plan.keyframes[-1].x > plan.keyframes[0].x
    assert plan.keyframes[-1].reason == "Ease pan to subject"


def test_low_confidence_track_falls_back_to_center_crop():
    plan = plan_reframe(
        [FaceObservation(time=0, box=Box(0, 0, 10, 10), confidence=0.2)],
        source_width=1920,
        source_height=1080,
    )
    assert len(plan.keyframes) == 1
    assert "center crop" in plan.keyframes[0].reason


def test_layout_uses_active_speaker_for_separate_vertical_angles():
    assert choose_layout(2, output_aspect=9 / 16, same_scene=False) == "active-speaker"
    assert choose_layout(2, output_aspect=9 / 16, same_scene=True) == "stacked"
