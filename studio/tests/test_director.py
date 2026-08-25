from podcast_studio.director import BeatKind, analyze_beats, direct_clip
from podcast_studio.models import EditIntensity, MotionKind, Transcript, Word
from podcast_studio.presets import get_style, style_names


def sample_transcript() -> Transcript:
    text = [
        ("Most", 0.0, 0.3), ("people", 0.31, 0.65), ("get", 0.66, 0.82), ("this", 0.83, 1.0), ("wrong.", 1.01, 1.35),
        ("A", 1.8, 1.9), ("2024", 1.91, 2.22), ("study", 2.23, 2.55), ("found", 2.56, 2.82), ("a", 2.83, 2.9), ("37", 2.91, 3.15), ("percent", 3.16, 3.52), ("difference.", 3.53, 4.0),
        ("But", 4.35, 4.55), ("the", 4.56, 4.68), ("study", 4.69, 4.95), ("was", 4.96, 5.1), ("in", 5.11, 5.22), ("mice,", 5.23, 5.5), ("so", 5.51, 5.68), ("we", 5.69, 5.8), ("do", 5.81, 5.92), ("not", 5.93, 6.05), ("know", 6.06, 6.3), ("whether", 6.31, 6.58), ("it", 6.59, 6.7), ("translates", 6.71, 7.05), ("to", 7.06, 7.15), ("humans.", 7.16, 7.55),
        ("The", 8.0, 8.15), ("takeaway", 8.16, 8.52), ("is", 8.53, 8.65), ("to", 8.66, 8.75), ("separate", 8.76, 9.1), ("the", 9.11, 9.2), ("signal", 9.21, 9.5), ("from", 9.51, 9.7), ("the", 9.71, 9.8), ("claim.", 9.81, 10.2),
    ]
    return Transcript(asset_id="cam-a", words=[Word(word, start, end) for word, start, end in text])


def test_style_profiles_are_named_and_density_resolves():
    assert "authority" in style_names()
    dense = get_style("authority", EditIntensity.DENSE)
    restrained = get_style("authority", EditIntensity.RESTRAINED)
    assert dense.rules.shot_target < restrained.rules.shot_target
    assert dense.rules.punch_gap < restrained.rules.punch_gap


def test_director_preserves_qualifier_sensitive_beats_and_builds_motion():
    transcript = sample_transcript()
    beats = analyze_beats(transcript)
    assert beats[0].kind is BeatKind.HOOK
    assert any(item.kind is BeatKind.CAVEAT and item.qualifier for item in beats)
    result = direct_clip(transcript, style="authority", intensity="balanced")
    assert result.plan.duration > 9
    assert result.plan.metadata["editorial_constraints"]["constant_drift_prohibited"] is True
    assert any(segment.motion.kind is not MotionKind.HOLD for segment in result.plan.segments)
    assert any("Qualifier-sensitive" in item for item in result.warnings)
    assert result.plan.to_dict()["intensity"] == "balanced"


def test_broll_requires_semantic_reason_and_confidence():
    result = direct_clip(sample_transcript(), style="proof-driven", intensity="dense")
    assert result.broll_cues
    for cue in result.broll_cues:
        assert cue.query
        assert cue.reason
        assert cue.require_provenance is True
        assert cue.confidence >= result.plan.metadata["editorial_constraints"]["minimum_broll_confidence"]
