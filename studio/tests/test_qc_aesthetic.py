from podcast_studio.director_calibrated import direct_clip
from podcast_studio.models import EditPlan, EditSegment, MotionKeyframe, MotionKind, MotionTrack, Transition, TransitionKind, Transcript, Word
from podcast_studio.qc import _inspection_times


def transcript() -> Transcript:
    return Transcript(
        asset_id="a",
        words=[
            Word("Strong", 0, .3), Word("claim.", .31, .75),
            Word("But", 1.1, 1.3), Word("this", 1.31, 1.5), Word("may", 1.51, 1.7), Word("vary.", 1.71, 2.05),
            Word("Takeaway", 2.4, 2.8), Word("here.", 2.81, 3.2),
        ],
    )


def test_inspection_times_cover_semantic_motion_and_transition_boundaries() -> None:
    motion = MotionTrack(
        kind=MotionKind.PUNCH_IN,
        keyframes=[MotionKeyframe(0, 1), MotionKeyframe(.8, 1.1), MotionKeyframe(1.4, 1.07)],
        reason="claim",
    )
    plan = EditPlan(
        id="inspect",
        title="inspect",
        segments=[
            EditSegment("a", 0, 1.6, "claim", motion=motion, transition_to_next=Transition(TransitionKind.DISSOLVE, .2, reason="bridge")),
            EditSegment("a", 1.7, 3.2, "takeaway"),
        ],
        metadata={"beat_map": [{"id": "claim", "start": 0, "end": .75, "strength": .9}]},
    )
    values = _inspection_times(plan, plan.duration)
    boundary = 1.4
    assert any(abs(item - .8) < .06 for item in values)
    assert any(abs(item - boundary) < .08 for item in values)


def test_calibrated_director_produces_multiple_semantic_inspection_events() -> None:
    result = direct_clip(transcript(), style="authority", intensity="balanced")
    values = _inspection_times(result.plan, result.plan.duration)
    assert len(values) >= 5
    assert values == sorted(set(values))
