from podcast_studio.aesthetic_qc import analyze_aesthetics
from podcast_studio.director_calibrated import direct_clip
from podcast_studio.models import (
    EditPlan,
    EditSegment,
    MotionKeyframe,
    MotionKind,
    MotionTrack,
    Overlay,
    OverlayKind,
    SoundEvent,
    TextOverlay,
    TextRole,
    Transcript,
    Word,
)


def transcript() -> Transcript:
    tokens = [
        ("This", 0, .3), ("study", .31, .65), ("found", .66, .9), ("a", .91, 1), ("large", 1.01, 1.25), ("effect.", 1.26, 1.65),
        ("But", 1.9, 2.1), ("it", 2.11, 2.2), ("was", 2.21, 2.35), ("preclinical", 2.36, 2.8), ("in", 2.81, 2.9), ("mice.", 2.91, 3.3),
        ("The", 3.6, 3.75), ("takeaway", 3.76, 4.1), ("is", 4.11, 4.2), ("to", 4.21, 4.3), ("be", 4.31, 4.45), ("precise.", 4.46, 4.8),
    ]
    return Transcript(asset_id="a", words=[Word(text, start, end) for text, start, end in tokens])


def checks(report):
    return {item.name: item for item in report.checks}


def test_directed_plan_passes_core_semantic_motion_and_integrity_gates() -> None:
    source = transcript()
    result = direct_clip(source, style="authority", intensity="balanced")
    report = analyze_aesthetics(result.plan, transcript=source, source_transcript=source)
    values = checks(report)
    assert values["motion_constant_drift"].passed
    assert values["integrity_qualifier_retention"].passed
    assert values["text_primary_hierarchy"].passed
    assert report.score >= 80


def test_bad_template_edit_fails_constant_zoom_text_broll_provenance_and_sfx_gates() -> None:
    source = transcript()
    drift = MotionTrack(
        kind=MotionKind.PUNCH_IN,
        keyframes=[MotionKeyframe(0, 1), MotionKeyframe(4.8, 1.25)],
        reason="constant zoom",
    )
    plan = EditPlan(
        id="bad",
        title="bad",
        segments=[EditSegment(source_id="a", source_start=0, source_end=4.8, reason="everything", motion=drift)],
        text_overlays=[
            TextOverlay(0, 3, "THIS IS A GIANT GENERIC HEADLINE", role=TextRole.HEADLINE),
            TextOverlay(1, 4, "ANOTHER PRIMARY HEADLINE", role=TextRole.CALLOUT),
        ],
        overlays=[
            Overlay(
                path="generic.mp4", start=.3, end=4.6, kind=OverlayKind.BROLL,
                semantic_confidence=.2, semantic_reason=None, source_url=None, license=None,
            )
        ],
        sound_effects=[
            SoundEvent("hit.wav", .5, gain_db=-2, reason=""),
            SoundEvent("hit.wav", .55, gain_db=-2, reason=""),
        ],
        metadata={
            "beat_map": [
                {"id": "claim", "start": 0, "end": 1.65, "strength": .85, "qualifier": False},
                {"id": "qualifier", "start": 1.9, "end": 3.3, "strength": .75, "qualifier": True},
            ]
        },
    )
    report = analyze_aesthetics(plan, transcript=source, source_transcript=source)
    values = checks(report)
    assert not values["motion_constant_drift"].passed
    assert not values["text_primary_hierarchy"].passed
    assert not values["broll_semantic_fit"].passed
    assert not values["broll_provenance"].passed
    assert not values["sfx_peak_guard"].passed
    assert not values["sfx_stacking"].passed
    assert report.score < 60


def test_dropping_adjacent_preclinical_qualifier_is_an_error() -> None:
    source = transcript()
    plan = EditPlan(
        id="unsafe",
        title="unsafe",
        segments=[EditSegment(source_id="a", source_start=0, source_end=1.65, reason="claim only")],
        metadata={
            "beat_map": [
                {"id": "claim", "start": 0, "end": 1.65, "strength": .85, "qualifier": False},
                {"id": "qualifier", "start": 1.9, "end": 3.3, "strength": .75, "qualifier": True},
            ]
        },
    )
    report = analyze_aesthetics(plan, source_transcript=source)
    assert not checks(report)["integrity_qualifier_retention"].passed
