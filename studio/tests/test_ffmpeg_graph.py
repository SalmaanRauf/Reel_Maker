from podcast_studio.ffmpeg_graph import (
    easing_expression,
    motion_filter,
    piecewise_expression,
    responsive_text_size,
    transition_name,
)
from podcast_studio.models import (
    Easing,
    MotionKeyframe,
    MotionKind,
    MotionTrack,
    Transform,
    TransitionKind,
)


def track() -> MotionTrack:
    return MotionTrack(
        kind=MotionKind.PUNCH_IN,
        keyframes=[
            MotionKeyframe(0, 1.0, 0.5, 0.48, easing=Easing.HOLD),
            MotionKeyframe(0.8, 1.0, 0.5, 0.48, easing=Easing.HOLD),
            MotionKeyframe(0.95, 1.11, 0.52, 0.47, easing=Easing.EASE_OUT),
            MotionKeyframe(2.0, 1.08, 0.52, 0.47, easing=Easing.EASE_IN_OUT),
        ],
        reason="emphasis",
    )


def test_piecewise_keyframes_compile_to_non_linear_expression() -> None:
    expression = piecewise_expression(track().keyframes, "zoom", time_var="on/30")
    assert "if(lt" in expression
    assert "pow" in expression
    assert "1.11" in expression


def test_motion_filter_uses_zoompan_without_constant_linear_drift() -> None:
    graph = motion_filter(track(), Transform(), width=1080, height=1920, fps=30, duration=2)
    assert "zoompan=" in graph
    assert "on/30" in graph
    assert "linear" not in graph
    assert "setsar=1" in graph


def test_responsive_text_wraps_and_scales_to_width() -> None:
    size, text = responsive_text_size(
        "This is a deliberately long source-backed editorial headline",
        requested=88,
        minimum=42,
        maximum=100,
        width=1080,
        max_width_ratio=0.76,
    )
    assert 42 <= size <= 88
    assert "\n" in text


def test_transition_and_spring_mappings_are_explicit() -> None:
    assert transition_name(TransitionKind.DISSOLVE) == "fade"
    assert "exp" in easing_expression("p", Easing.SPRING)
