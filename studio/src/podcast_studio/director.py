from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable

from .model_core import Transcript, Word
from .presets import StyleProfile, get_style
from .style_models import (
    EditIntensity,
    Easing,
    LayoutKind,
    MotionKeyframe,
    MotionKind,
    MotionTrack,
    TextRole,
    Transform,
    Transition,
    TransitionKind,
)
from .timeline import EditPlan, EditSegment, LayoutEvent, TextOverlay
from .util import clamp, compact_whitespace, stable_id


class BeatKind(str, Enum):
    HOOK = "hook"
    CLAIM = "claim"
    QUESTION = "question"
    NUMBER = "number"
    CONTRAST = "contrast"
    MECHANISM = "mechanism"
    EVIDENCE = "evidence"
    EXAMPLE = "example"
    CAVEAT = "caveat"
    PAYOFF = "payoff"
    TRANSITION = "transition"


@dataclass(slots=True)
class Beat:
    id: str
    start: float
    end: float
    text: str
    kind: BeatKind
    strength: float
    speaker: str | None = None
    entities: list[str] = field(default_factory=list)
    qualifier: bool = False
    rationale: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["kind"] = self.kind.value
        return value


@dataclass(slots=True)
class BrollCue:
    id: str
    start: float
    end: float
    query: str
    role: str
    reason: str
    confidence: float
    transcript_text: str
    source_beat_id: str
    require_provenance: bool = True
    allow_generated: bool = False
    preferred_media: tuple[str, ...] = ("video", "image", "screenshot")
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["preferred_media"] = list(self.preferred_media)
        return value


@dataclass(slots=True)
class DirectionResult:
    plan: EditPlan
    beats: list[Beat]
    broll_cues: list[BrollCue]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "beats": [item.to_dict() for item in self.beats],
            "broll_cues": [item.to_dict() for item in self.broll_cues],
            "warnings": self.warnings,
        }


_SENTENCE_END = re.compile(r"[.!?…][\"'’”)]*$")
_NUMBER = re.compile(r"(?:\$|\b)(?:\d+(?:[.,]\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I)
_QUESTION_STARTERS = {"what", "why", "how", "when", "where", "who", "which", "can", "could", "does", "do", "is", "are"}
_CONTRAST = {"but", "however", "instead", "versus", "vs", "yet", "although", "whereas", "except"}
_MECHANISM = {"because", "causes", "cause", "mechanism", "pathway", "through", "therefore", "why", "how"}
_EVIDENCE = {"study", "studies", "research", "trial", "trials", "evidence", "data", "paper", "published", "meta-analysis", "review"}
_EXAMPLE = {"example", "instance", "imagine", "say", "suppose", "case", "story"}
_CAVEAT = {
    "may", "might", "could", "suggest", "suggests", "associated", "possible", "possibly", "uncertain",
    "unknown", "limited", "preclinical", "animal", "animals", "mouse", "mice", "rat", "rats", "anecdote", "anecdotal",
}
_PAYOFF = {"so", "therefore", "result", "means", "ultimately", "bottom", "takeaway", "conclusion", "finally"}
_TRANSITION = {"next", "another", "second", "third", "now", "separately", "meanwhile"}
_HIGH_IMPACT = {
    "never", "always", "biggest", "mistake", "truth", "wrong", "actually", "exactly", "only", "critical", "important",
    "dangerous", "failed", "worked", "changed", "surprising", "wild", "first", "best", "worst",
}
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at", "for", "from", "with", "without",
    "this", "that", "these", "those", "it", "its", "is", "are", "was", "were", "be", "been", "being", "you",
    "your", "we", "our", "they", "their", "he", "she", "i", "me", "my", "do", "does", "did", "have", "has",
    "had", "can", "could", "would", "should", "will", "just", "really", "very", "kind", "like", "actually",
}


def analyze_beats(
    transcript: Transcript,
    *,
    start: float = 0.0,
    end: float | None = None,
    target_phrase_seconds: float = 2.7,
    maximum_words: int = 16,
) -> list[Beat]:
    end = transcript.duration if end is None else min(end, transcript.duration)
    words = [word for word in transcript.words if word.end > start and word.start < end]
    if not words:
        return []
    phrases = _phrase_words(words, target_phrase_seconds=target_phrase_seconds, maximum_words=maximum_words)
    beats: list[Beat] = []
    for index, phrase in enumerate(phrases):
        text = _join_words(phrase)
        tokens = _tokens(text)
        kind, rationale = _classify(tokens, text, first=index == 0)
        qualifier = bool(tokens & _CAVEAT)
        entities = _entities(phrase)
        strength = _strength(kind, tokens, text, index=index, entity_count=len(entities), qualifier=qualifier)
        beats.append(
            Beat(
                id=stable_id("beat", transcript.asset_id, round(phrase[0].start, 3), round(phrase[-1].end, 3), text),
                start=max(start, phrase[0].start),
                end=min(end, phrase[-1].end),
                text=text,
                kind=kind,
                strength=strength,
                speaker=phrase[0].speaker,
                entities=entities,
                qualifier=qualifier,
                rationale=rationale,
            )
        )
    return beats


def direct_clip(
    transcript: Transcript,
    *,
    source_id: str | None = None,
    start: float = 0.0,
    end: float | None = None,
    title: str = "Directed podcast clip",
    style: str | StyleProfile = "authority",
    intensity: EditIntensity | str = EditIntensity.BALANCED,
    width: int = 1080,
    height: int = 1920,
    fps: float = 30,
    camera_by_speaker: dict[str, str] | None = None,
    transcript_path: str | None = None,
) -> DirectionResult:
    end = transcript.duration if end is None else min(end, transcript.duration)
    if end <= start:
        raise ValueError("Clip end must follow start")
    profile = style if isinstance(style, StyleProfile) else get_style(style, intensity)
    source_id = source_id or transcript.asset_id
    beats = analyze_beats(transcript, start=start, end=end)
    if not beats:
        raise ValueError("No timed words were found in the requested clip range")

    segments = _schedule_segments(beats, source_id=source_id, profile=profile, camera_by_speaker=camera_by_speaker or {})
    _attach_timeline_starts(segments)
    text_overlays = _schedule_text_overlays(beats, segments, profile, end - start)
    layout_events = _schedule_layouts(beats, segments, camera_by_speaker or {}, profile)
    broll_cues = _schedule_broll_cues(beats, segments, profile, end - start)

    metadata = {
        "directed_by": "semantic-director-v2",
        "source_range": {"start": start, "end": end},
        "style_profile": profile.name,
        "beat_map": [item.to_dict() for item in beats],
        "broll_cues": [item.to_dict() for item in broll_cues],
        "editorial_constraints": {
            "semantic_motion_only": True,
            "constant_drift_prohibited": profile.prohibit_constant_drift,
            "minimum_broll_confidence": profile.minimum_broll_confidence,
            "one_primary_phrase_at_a_time": profile.one_primary_phrase_at_a_time,
            "medical_qualifier_guard": profile.medical_qualifier_guard,
        },
    }
    plan = EditPlan(
        id=stable_id("plan", transcript.asset_id, round(start, 3), round(end, 3), profile.name, intensity),
        title=title,
        segments=segments,
        width=width,
        height=height,
        fps=fps,
        style_profile=profile.name,
        intensity=EditIntensity(intensity),
        brand=profile.brand,
        caption_style=profile.caption,
        transcript_path=transcript_path,
        text_overlays=text_overlays,
        layout_events=layout_events,
        metadata=metadata,
    )
    warnings: list[str] = []
    if not broll_cues:
        warnings.append("No B-roll was scheduled because no cue cleared the semantic confidence threshold.")
    if any(item.qualifier for item in beats):
        warnings.append("Qualifier-sensitive language detected; revisions must preserve those source words.")
    return DirectionResult(plan=plan, beats=beats, broll_cues=broll_cues, warnings=warnings)


def _phrase_words(words: list[Word], *, target_phrase_seconds: float, maximum_words: int) -> list[list[Word]]:
    phrases: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current:
            gap = word.start - current[-1].end
            duration = current[-1].end - current[0].start
            speaker_change = bool(word.speaker and current[-1].speaker and word.speaker != current[-1].speaker)
            should_break = (
                gap >= 0.48
                or speaker_change
                or len(current) >= maximum_words
                or (duration >= target_phrase_seconds and (_SENTENCE_END.search(current[-1].text) or gap >= 0.18))
                or duration >= target_phrase_seconds * 1.55
            )
            if should_break:
                phrases.append(current)
                current = []
        current.append(word)
        if _SENTENCE_END.search(word.text) and current[-1].end - current[0].start >= 0.55:
            phrases.append(current)
            current = []
    if current:
        phrases.append(current)
    return phrases


def _classify(tokens: set[str], text: str, *, first: bool) -> tuple[BeatKind, list[str]]:
    rationale: list[str] = []
    first_token = next(iter(_ordered_tokens(text)), "")
    if text.rstrip().endswith("?") or first_token in _QUESTION_STARTERS:
        rationale.append("direct question")
        kind = BeatKind.QUESTION
    elif tokens & _CAVEAT:
        rationale.append("qualifier or uncertainty")
        kind = BeatKind.CAVEAT
    elif tokens & _EVIDENCE:
        rationale.append("source or evidence language")
        kind = BeatKind.EVIDENCE
    elif _NUMBER.search(text):
        rationale.append("specific number")
        kind = BeatKind.NUMBER
    elif tokens & _CONTRAST:
        rationale.append("contrast")
        kind = BeatKind.CONTRAST
    elif tokens & _MECHANISM:
        rationale.append("mechanism or causality")
        kind = BeatKind.MECHANISM
    elif tokens & _EXAMPLE:
        rationale.append("concrete example")
        kind = BeatKind.EXAMPLE
    elif tokens & _PAYOFF:
        rationale.append("resolution or takeaway")
        kind = BeatKind.PAYOFF
    elif tokens & _TRANSITION:
        rationale.append("section transition")
        kind = BeatKind.TRANSITION
    else:
        kind = BeatKind.CLAIM
        rationale.append("substantive statement")
    if first and kind in {BeatKind.CLAIM, BeatKind.QUESTION, BeatKind.NUMBER, BeatKind.CONTRAST}:
        rationale.append("opening beat")
        kind = BeatKind.HOOK
    return kind, rationale


def _strength(
    kind: BeatKind,
    tokens: set[str],
    text: str,
    *,
    index: int,
    entity_count: int,
    qualifier: bool,
) -> float:
    base = {
        BeatKind.HOOK: 0.88,
        BeatKind.QUESTION: 0.75,
        BeatKind.NUMBER: 0.78,
        BeatKind.CONTRAST: 0.76,
        BeatKind.EVIDENCE: 0.80,
        BeatKind.MECHANISM: 0.70,
        BeatKind.EXAMPLE: 0.66,
        BeatKind.CAVEAT: 0.64,
        BeatKind.PAYOFF: 0.82,
        BeatKind.TRANSITION: 0.48,
        BeatKind.CLAIM: 0.60,
    }[kind]
    base += min(0.10, 0.025 * entity_count)
    if tokens & _HIGH_IMPACT:
        base += 0.06
    if index <= 1:
        base += 0.04
    if 5 <= len(text.split()) <= 14:
        base += 0.03
    if qualifier:
        base = max(base, 0.64)
    return clamp(base, 0.0, 1.0)


def _schedule_segments(
    beats: list[Beat],
    *,
    source_id: str,
    profile: StyleProfile,
    camera_by_speaker: dict[str, str],
) -> list[EditSegment]:
    rules = profile.rules
    groups: list[list[Beat]] = []
    current: list[Beat] = []
    for beat in beats:
        if not current:
            current = [beat]
            continue
        duration_if_added = beat.end - current[0].start
        speaker_changed = bool(beat.speaker and current[-1].speaker and beat.speaker != current[-1].speaker)
        strong_boundary = beat.strength >= 0.76 and beat.start - current[0].start >= rules.shot_min
        target_reached = beat.start - current[0].start >= rules.shot_target
        if speaker_changed or duration_if_added > rules.shot_max or (strong_boundary and target_reached):
            groups.append(current)
            current = [beat]
        else:
            current.append(beat)
    if current:
        groups.append(current)

    segments: list[EditSegment] = []
    previous_zoom = 1.0
    for index, group in enumerate(groups):
        strongest = max(group, key=lambda item: item.strength)
        speaker = group[0].speaker
        selected_source = camera_by_speaker.get(speaker or "", source_id)
        base_zoom = 1.0 if index % 3 == 0 else 1.025 if index % 3 == 1 else 1.045
        if math.isclose(base_zoom, previous_zoom, abs_tol=0.005):
            base_zoom = 1.0 if previous_zoom > 1.02 else 1.04
        previous_zoom = base_zoom
        crop_x = 0.5 + (0.018 if index % 2 else -0.014)
        transform = Transform(zoom=base_zoom, crop_x=crop_x, crop_y=0.48)
        motion = _motion_for_group(group, transform, profile)
        transition = _transition_for_boundary(group, index, len(groups), profile)
        segments.append(
            EditSegment(
                source_id=selected_source,
                source_start=group[0].start,
                source_end=group[-1].end,
                reason=f"{strongest.kind.value}: {compact_whitespace(strongest.text)[:120]}",
                transform=transform,
                motion=motion,
                transition_to_next=transition,
                speaker=speaker,
                label=strongest.kind.value,
                camera_priority=strongest.strength,
                reaction=False,
                metadata={"beat_ids": [item.id for item in group], "strongest_beat_id": strongest.id},
            )
        )
    return segments


def _motion_for_group(group: list[Beat], base: Transform, profile: StyleProfile) -> MotionTrack:
    duration = group[-1].end - group[0].start
    keyframes = [MotionKeyframe(0.0, base.zoom, base.crop_x, base.crop_y, easing=Easing.HOLD)]
    last_motion = -999.0
    selected = [beat for beat in group if beat.strength >= 0.74 and not beat.qualifier]
    selected.sort(key=lambda item: (-item.strength, item.start))
    selected = sorted(selected[:2], key=lambda item: item.start)
    for order, beat in enumerate(selected):
        local = max(0.05, beat.start - group[0].start)
        if local - last_motion < profile.rules.punch_gap:
            continue
        amplitude_span = profile.rules.punch_zoom_max - profile.rules.punch_zoom_min
        amplitude = profile.rules.punch_zoom_min + amplitude_span * ((beat.strength * 0.73 + order * 0.19) % 1)
        attack = min(duration, local + profile.rules.punch_attack)
        settle = min(duration, attack + profile.rules.settle_seconds)
        keyframes.extend(
            [
                MotionKeyframe(local, base.zoom, base.crop_x, base.crop_y, easing=Easing.HOLD),
                MotionKeyframe(attack, max(base.zoom, amplitude), base.crop_x, base.crop_y, easing=Easing.EASE_OUT),
                MotionKeyframe(settle, max(base.zoom, amplitude - 0.025), base.crop_x, base.crop_y, easing=Easing.EASE_IN_OUT),
            ]
        )
        last_motion = local
    if keyframes[-1].time < duration:
        keyframes.append(
            MotionKeyframe(duration, keyframes[-1].zoom, keyframes[-1].crop_x, keyframes[-1].crop_y, easing=Easing.HOLD)
        )
    keyframes = _dedupe_keyframes(keyframes)
    kind = MotionKind.HOLD if len(keyframes) <= 2 else MotionKind.PUNCH_IN if len(selected) == 1 else MotionKind.CUSTOM
    reason = "stable hold" if kind == MotionKind.HOLD else "semantic emphasis; no constant drift"
    return MotionTrack(kind=kind, keyframes=keyframes, reason=reason, confidence=max(item.strength for item in group))


def _transition_for_boundary(group: list[Beat], index: int, group_count: int, profile: StyleProfile) -> Transition:
    if index >= group_count - 1 or profile.prefer_hard_cuts:
        return Transition()
    strongest = max(group, key=lambda item: item.strength)
    if strongest.kind == BeatKind.TRANSITION and TransitionKind.DISSOLVE in profile.allowed_transitions:
        return Transition(TransitionKind.DISSOLVE, 0.12, reason="section boundary")
    return Transition()


def _attach_timeline_starts(segments: list[EditSegment]) -> None:
    cursor = 0.0
    for segment in segments:
        segment.metadata["timeline_start"] = round(cursor, 6)
        cursor += segment.duration - segment.transition_to_next.duration


def _schedule_text_overlays(
    beats: list[Beat],
    segments: list[EditSegment],
    profile: StyleProfile,
    source_duration: float,
) -> list[TextOverlay]:
    maximum = max(1, round(source_duration / 60 * profile.rules.text_events_per_minute))
    candidates = [
        beat for beat in beats
        if beat.kind in {BeatKind.HOOK, BeatKind.NUMBER, BeatKind.CONTRAST, BeatKind.EVIDENCE, BeatKind.PAYOFF}
        and beat.strength >= 0.72
    ]
    candidates.sort(key=lambda item: (-item.strength, item.start))
    selected: list[Beat] = []
    for beat in candidates:
        if any(abs(beat.start - other.start) < 4.0 for other in selected):
            continue
        selected.append(beat)
        if len(selected) >= maximum:
            break
    selected.sort(key=lambda item: item.start)

    overlays: list[TextOverlay] = []
    for beat in selected:
        start = _source_to_timeline(beat.start, segments)
        end = min(_plan_duration(segments), start + min(3.2, max(1.35, beat.duration + 0.45)))
        role = TextRole.HEADLINE
        if beat.kind == BeatKind.NUMBER:
            role = TextRole.STATISTIC
        elif beat.kind == BeatKind.EVIDENCE:
            role = TextRole.EVIDENCE
        elif beat.kind == BeatKind.PAYOFF:
            role = TextRole.CALLOUT
        phrase = _on_screen_phrase(beat.text, role)
        overlays.append(
            TextOverlay(
                start=start,
                end=end,
                text=phrase,
                role=role,
                y="h*0.13",
                font_size=78 if role == TextRole.STATISTIC else 66,
                max_width_ratio=0.82,
                font_color=profile.brand.primary_color,
                accent_color=profile.brand.accent_color,
                box=role in {TextRole.EVIDENCE, TextRole.STATISTIC},
                box_color=f"{profile.brand.background_color}@0.72",
                box_border=22,
                fade_seconds=0.14,
                animation="rise" if role != TextRole.STATISTIC else "pop",
                priority=90 if beat.kind == BeatKind.HOOK else 70,
                metadata={"source_beat_id": beat.id, "exact_source_phrase": beat.text},
            )
        )
    return overlays


def _schedule_broll_cues(
    beats: list[Beat],
    segments: list[EditSegment],
    profile: StyleProfile,
    source_duration: float,
) -> list[BrollCue]:
    if not profile.use_semantic_broll:
        return []
    maximum = max(0, round(source_duration / 60 * profile.rules.broll_events_per_minute))
    candidates = [
        beat for beat in beats
        if beat.entities
        and beat.kind in {BeatKind.NUMBER, BeatKind.MECHANISM, BeatKind.EVIDENCE, BeatKind.EXAMPLE, BeatKind.CONTRAST}
    ]
    candidates.sort(key=lambda item: (-item.strength, item.start))
    selected: list[Beat] = []
    for beat in candidates:
        confidence = _broll_confidence(beat)
        if confidence < profile.minimum_broll_confidence:
            continue
        if any(abs(beat.start - other.start) < 5.0 for other in selected):
            continue
        selected.append(beat)
        if len(selected) >= maximum:
            break
    selected.sort(key=lambda item: item.start)

    cues: list[BrollCue] = []
    for beat in selected:
        timeline_start = _source_to_timeline(beat.start, segments)
        duration = min(4.5, max(2.2, beat.duration + 0.7))
        role = "proof" if beat.kind == BeatKind.EVIDENCE else "mechanism" if beat.kind == BeatKind.MECHANISM else "illustration"
        cues.append(
            BrollCue(
                id=stable_id("broll", beat.id, role),
                start=timeline_start,
                end=min(_plan_duration(segments), timeline_start + duration),
                query=" ".join(beat.entities[:4]),
                role=role,
                reason=f"Visualize {beat.kind.value}: {beat.text}",
                confidence=_broll_confidence(beat),
                transcript_text=beat.text,
                source_beat_id=beat.id,
                require_provenance=True,
                allow_generated=False,
                preferred_media=("screenshot", "image", "video") if role == "proof" else ("video", "image", "screenshot"),
                metadata={"entities": beat.entities, "qualifier_sensitive": beat.qualifier},
            )
        )
    return cues


def _schedule_layouts(
    beats: list[Beat],
    segments: list[EditSegment],
    camera_by_speaker: dict[str, str],
    profile: StyleProfile,
) -> list[LayoutEvent]:
    speakers = {beat.speaker for beat in beats if beat.speaker}
    if len(speakers) < 2 or not camera_by_speaker:
        return []
    events: list[LayoutEvent] = []
    for previous, current in zip(beats, beats[1:], strict=False):
        if not previous.speaker or not current.speaker or previous.speaker == current.speaker:
            continue
        gap = current.start - previous.end
        timeline_start = max(0.0, _source_to_timeline(previous.end - 0.25, segments))
        if gap < 0.25 and min(previous.duration, current.duration) < 1.4:
            source_ids = [camera_by_speaker[item] for item in (previous.speaker, current.speaker) if item in camera_by_speaker]
            if len(source_ids) == 2:
                events.append(
                    LayoutEvent(
                        start=timeline_start,
                        end=min(_plan_duration(segments), timeline_start + 1.4),
                        kind=LayoutKind.GROUP,
                        source_ids=source_ids,
                        active_source_id=camera_by_speaker.get(current.speaker),
                        reason="rapid exchange; avoid unreadable ping-pong cuts",
                    )
                )
    return _merge_layout_events(events)


def _source_to_timeline(source_time: float, segments: list[EditSegment]) -> float:
    for segment in segments:
        if segment.source_start - 1e-6 <= source_time <= segment.source_end + 1e-6:
            return float(segment.metadata.get("timeline_start", 0.0)) + max(0.0, source_time - segment.source_start)
    if source_time < segments[0].source_start:
        return 0.0
    return _plan_duration(segments)


def _plan_duration(segments: list[EditSegment]) -> float:
    return sum(item.duration for item in segments) - sum(item.transition_to_next.duration for item in segments[:-1])


def _on_screen_phrase(text: str, role: TextRole, maximum_words: int = 8) -> str:
    words = text.split()
    if role == TextRole.STATISTIC:
        number_index = next((index for index, word in enumerate(words) if _NUMBER.search(word)), 0)
        left = max(0, number_index - 2)
        words = words[left : left + maximum_words]
    else:
        content = [word for word in words if _clean_token(word) not in _STOPWORDS]
        words = content[:maximum_words] if len(content) >= 3 else words[:maximum_words]
    phrase = compact_whitespace(" ".join(words)).strip(" ,.;:")
    return phrase or compact_whitespace(text)[:80]


def _broll_confidence(beat: Beat) -> float:
    role_bonus = 0.10 if beat.kind in {BeatKind.EVIDENCE, BeatKind.EXAMPLE, BeatKind.MECHANISM} else 0.04
    entity_bonus = min(0.16, len(beat.entities) * 0.045)
    qualifier_penalty = 0.05 if beat.qualifier and beat.kind != BeatKind.EVIDENCE else 0.0
    return clamp(beat.strength * 0.76 + role_bonus + entity_bonus - qualifier_penalty, 0.0, 1.0)


def _merge_layout_events(events: list[LayoutEvent]) -> list[LayoutEvent]:
    if not events:
        return []
    events.sort(key=lambda item: item.start)
    merged = [events[0]]
    for event in events[1:]:
        previous = merged[-1]
        if event.start <= previous.end + 0.12 and event.kind == previous.kind and event.source_ids == previous.source_ids:
            previous.end = max(previous.end, event.end)
        else:
            merged.append(event)
    return merged


def _dedupe_keyframes(keyframes: Iterable[MotionKeyframe]) -> list[MotionKeyframe]:
    result: list[MotionKeyframe] = []
    for keyframe in sorted(keyframes, key=lambda item: item.time):
        if result and math.isclose(result[-1].time, keyframe.time, abs_tol=1e-4):
            result[-1] = keyframe
        else:
            result.append(keyframe)
    return result


def _entities(words: list[Word]) -> list[str]:
    scored: dict[str, float] = {}
    for index, word in enumerate(words):
        token = _clean_token(word.text)
        if len(token) < 3 or token in _STOPWORDS or token in _CAVEAT:
            continue
        score = 1.0
        if word.text[:1].isupper() and index > 0:
            score += 0.45
        if _NUMBER.fullmatch(token):
            score += 0.4
        if token in _EVIDENCE | _MECHANISM | _HIGH_IMPACT:
            score += 0.2
        scored[token] = max(scored.get(token, 0), score)
    return [item for item, _ in sorted(scored.items(), key=lambda pair: (-pair[1], pair[0]))[:6]]


def _ordered_tokens(text: str) -> list[str]:
    return [_clean_token(item) for item in text.split() if _clean_token(item)]


def _tokens(text: str) -> set[str]:
    return set(_ordered_tokens(text))


def _clean_token(value: str) -> str:
    return re.sub(r"[^a-z0-9$%-]+", "", value.lower())


def _join_words(words: list[Word]) -> str:
    text = " ".join(item.text.strip() for item in words)
    return compact_whitespace(re.sub(r"\s+([,.;:!?…])", r"\1", text))
