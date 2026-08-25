from __future__ import annotations

from typing import Any

from .director import DirectionResult, direct_clip as _base_direct_clip
from .models import Easing, MotionKeyframe, MotionKind, MotionTrack
from .presets import get_style


def direct_clip(*args: Any, **kwargs: Any) -> DirectionResult:
    """Run the semantic director, then enforce a visual event on every strong missed beat.

    The base director intentionally stays conservative. This production wrapper closes
    short-clip dead zones without falling back to a metronomic zoom schedule.
    """
    result = _base_direct_clip(*args, **kwargs)
    _refine_semantic_motion(result)
    _attach_layout_source_times(result)
    result.plan.metadata["directed_by"] = "semantic-director-v2.1-calibrated"
    return result


def _refine_semantic_motion(result: DirectionResult) -> None:
    plan = result.plan
    profile = get_style(plan.style_profile, plan.intensity)
    for segment in plan.segments:
        beats = [
            beat for beat in result.beats
            if beat.start >= segment.source_start - 1e-6
            and beat.start < segment.source_end - 1e-6
            and beat.strength >= 0.74
            and not beat.qualifier
        ]
        if not beats:
            continue
        keyframes = list(segment.motion.keyframes)
        if not keyframes:
            keyframes = [MotionKeyframe(0, segment.transform.zoom, segment.transform.crop_x, segment.transform.crop_y, easing=Easing.HOLD)]
        event_times = [item.time for item in keyframes]
        duration = segment.duration
        minimum_gap = min(profile.rules.punch_gap, max(1.6, duration * 0.42))
        for order, beat in enumerate(beats[:3]):
            local = max(0.05, beat.start - segment.source_start)
            if min((abs(local - item) for item in event_times), default=999) <= 0.45:
                continue
            prior_semantic = max((item for item in event_times if item <= local), default=-999)
            if local - prior_semantic < minimum_gap:
                continue
            baseline = keyframes[-1].zoom
            amplitude = min(profile.rules.punch_zoom_max, max(baseline + 0.035, profile.rules.punch_zoom_min + order * 0.012))
            attack = min(duration, local + profile.rules.punch_attack)
            settle = min(duration, attack + profile.rules.settle_seconds)
            keyframes.extend(
                [
                    MotionKeyframe(local, segment.transform.zoom, segment.transform.crop_x, segment.transform.crop_y, easing=Easing.HOLD),
                    MotionKeyframe(attack, amplitude, segment.transform.crop_x, segment.transform.crop_y, easing=Easing.EASE_OUT),
                    MotionKeyframe(settle, max(segment.transform.zoom, amplitude - 0.025), segment.transform.crop_x, segment.transform.crop_y, easing=Easing.EASE_IN_OUT),
                ]
            )
            event_times.extend([local, attack, settle])
        keyframes = _dedupe(keyframes)
        if keyframes[-1].time < duration:
            tail = keyframes[-1]
            keyframes.append(MotionKeyframe(duration, tail.zoom, tail.crop_x, tail.crop_y, easing=Easing.HOLD))
        segment.motion = MotionTrack(
            kind=MotionKind.CUSTOM if len(keyframes) > 4 else segment.motion.kind,
            keyframes=keyframes,
            reason="semantic emphasis with calibrated short-clip dead-zone protection",
            confidence=segment.motion.confidence,
            metadata={**segment.motion.metadata, "calibrated": True},
        )


def _attach_layout_source_times(result: DirectionResult) -> None:
    beats_by_id = {beat.id: beat for beat in result.beats}
    for event in result.plan.layout_events:
        if "source_start" in event.metadata:
            continue
        ids = event.metadata.get("source_beat_ids", [])
        beats = [beats_by_id[item] for item in ids if item in beats_by_id]
        event.metadata["source_start"] = max(0.0, min((item.start for item in beats), default=event.start) - 0.25)


def _dedupe(values: list[MotionKeyframe]) -> list[MotionKeyframe]:
    result: list[MotionKeyframe] = []
    for value in sorted(values, key=lambda item: item.time):
        if result and abs(result[-1].time - value.time) < 1e-4:
            result[-1] = value
        else:
            result.append(value)
    return result
