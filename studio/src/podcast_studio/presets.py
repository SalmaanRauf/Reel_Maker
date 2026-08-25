from __future__ import annotations

from dataclasses import dataclass, replace

from .style_models import (
    BrandKit,
    CaptionAnimation,
    CaptionStyle,
    EditIntensity,
    TransitionKind,
)


@dataclass(slots=True, frozen=True)
class IntensityRules:
    beat_interval_min: float
    beat_interval_max: float
    shot_min: float
    shot_target: float
    shot_max: float
    punch_gap: float
    punch_zoom_min: float
    punch_zoom_max: float
    punch_attack: float
    settle_seconds: float
    text_events_per_minute: float
    broll_events_per_minute: float
    broll_coverage_max: float
    sfx_events_per_minute: float
    transition_rate_max: float
    proof_priority: float
    reaction_rate: float


@dataclass(slots=True, frozen=True)
class StyleProfile:
    name: str
    description: str
    caption: CaptionStyle
    brand: BrandKit
    rules: IntensityRules
    allowed_transitions: tuple[TransitionKind, ...]
    prefer_hard_cuts: bool = True
    use_proof_cards: bool = True
    use_semantic_broll: bool = True
    use_sound_effects: bool = False
    keep_natural_breaths: bool = True
    one_primary_phrase_at_a_time: bool = True
    prohibit_constant_drift: bool = True
    minimum_broll_confidence: float = 0.64
    maximum_repeated_framing: int = 3
    maximum_caption_lines: int = 2
    medical_qualifier_guard: bool = True


_INTENSITIES: dict[EditIntensity, IntensityRules] = {
    EditIntensity.RESTRAINED: IntensityRules(
        beat_interval_min=0.75,
        beat_interval_max=1.50,
        shot_min=4.0,
        shot_target=8.5,
        shot_max=14.0,
        punch_gap=6.0,
        punch_zoom_min=1.055,
        punch_zoom_max=1.09,
        punch_attack=0.16,
        settle_seconds=1.4,
        text_events_per_minute=1.5,
        broll_events_per_minute=1.5,
        broll_coverage_max=0.18,
        sfx_events_per_minute=0.0,
        transition_rate_max=0.05,
        proof_priority=0.9,
        reaction_rate=0.12,
    ),
    EditIntensity.BALANCED: IntensityRules(
        beat_interval_min=0.55,
        beat_interval_max=1.25,
        shot_min=2.8,
        shot_target=6.2,
        shot_max=10.0,
        punch_gap=4.2,
        punch_zoom_min=1.065,
        punch_zoom_max=1.12,
        punch_attack=0.13,
        settle_seconds=1.1,
        text_events_per_minute=3.0,
        broll_events_per_minute=3.0,
        broll_coverage_max=0.30,
        sfx_events_per_minute=0.7,
        transition_rate_max=0.10,
        proof_priority=0.92,
        reaction_rate=0.20,
    ),
    EditIntensity.DENSE: IntensityRules(
        beat_interval_min=0.38,
        beat_interval_max=1.05,
        shot_min=1.8,
        shot_target=4.4,
        shot_max=7.5,
        punch_gap=2.8,
        punch_zoom_min=1.075,
        punch_zoom_max=1.145,
        punch_attack=0.10,
        settle_seconds=0.85,
        text_events_per_minute=5.0,
        broll_events_per_minute=5.0,
        broll_coverage_max=0.42,
        sfx_events_per_minute=1.5,
        transition_rate_max=0.14,
        proof_priority=0.95,
        reaction_rate=0.28,
    ),
    EditIntensity.MAXIMAL: IntensityRules(
        beat_interval_min=0.30,
        beat_interval_max=0.90,
        shot_min=1.2,
        shot_target=3.3,
        shot_max=5.8,
        punch_gap=2.0,
        punch_zoom_min=1.085,
        punch_zoom_max=1.17,
        punch_attack=0.08,
        settle_seconds=0.70,
        text_events_per_minute=7.0,
        broll_events_per_minute=7.0,
        broll_coverage_max=0.52,
        sfx_events_per_minute=2.2,
        transition_rate_max=0.18,
        proof_priority=0.95,
        reaction_rate=0.34,
    ),
}


def _caption(
    name: str,
    *,
    size_ratio: float,
    active: str,
    emphasis: str,
    animation: CaptionAnimation,
    max_words: int,
    box: bool = False,
    uppercase: bool = False,
) -> CaptionStyle:
    return CaptionStyle(
        name=name,
        font_family="Arial",
        font_size_ratio=size_ratio,
        min_font_size=40,
        max_font_size=94,
        primary_color="&H00FFFFFF",
        secondary_color="&H006F7785",
        active_color=active,
        emphasis_color=emphasis,
        outline_color="&H00100F12",
        back_color="&H9A101014",
        outline=3.2,
        shadow=0.0,
        uppercase=uppercase,
        max_words=max_words,
        max_chars=34,
        max_lines=2,
        animation=animation,
        active_scale=1.055,
        box=box,
        auto_scale=True,
        auto_move=True,
    )


_BASE_BRAND = BrandKit(
    name="authority",
    primary_color="#FFFFFF",
    secondary_color="#B8BEC9",
    accent_color="#F4D35E",
    evidence_color="#7AB8FF",
    background_color="#0B0C10",
    corner_radius=26,
    stroke_width=3,
)


_PROFILE_TEMPLATES: dict[str, StyleProfile] = {
    "authority": StyleProfile(
        name="authority",
        description="Expert-led, proof-aware, restrained motion with one clear hierarchy.",
        caption=_caption(
            "authority",
            size_ratio=0.038,
            active="&H005ED7F7",
            emphasis="&H0054D1F7",
            animation=CaptionAnimation.WORD_POP,
            max_words=5,
        ),
        brand=_BASE_BRAND,
        rules=_INTENSITIES[EditIntensity.BALANCED],
        allowed_transitions=(TransitionKind.CUT, TransitionKind.DISSOLVE, TransitionKind.DIP_TO_BLACK),
        use_sound_effects=False,
        minimum_broll_confidence=0.70,
    ),
    "editorial-clean": StyleProfile(
        name="editorial-clean",
        description="Minimal captions, measured reframes, and almost exclusively hard cuts.",
        caption=_caption(
            "editorial-clean",
            size_ratio=0.036,
            active="&H00FFFFFF",
            emphasis="&H0054D1F7",
            animation=CaptionAnimation.FADE,
            max_words=6,
        ),
        brand=replace(_BASE_BRAND, name="editorial-clean", accent_color="#8DB5FF"),
        rules=_INTENSITIES[EditIntensity.RESTRAINED],
        allowed_transitions=(TransitionKind.CUT, TransitionKind.DISSOLVE),
        use_sound_effects=False,
        minimum_broll_confidence=0.76,
    ),
    "proof-driven": StyleProfile(
        name="proof-driven",
        description="Sources, documents, charts, UI, and product details lead the visual hierarchy.",
        caption=_caption(
            "proof-driven",
            size_ratio=0.036,
            active="&H00FFC77A",
            emphasis="&H00FFC77A",
            animation=CaptionAnimation.ACTIVE_FILL,
            max_words=5,
        ),
        brand=replace(_BASE_BRAND, name="proof-driven", accent_color="#79B8FF", evidence_color="#79B8FF"),
        rules=replace(_INTENSITIES[EditIntensity.BALANCED], proof_priority=1.0, broll_coverage_max=0.38),
        allowed_transitions=(TransitionKind.CUT, TransitionKind.DISSOLVE, TransitionKind.ZOOM),
        use_sound_effects=False,
        minimum_broll_confidence=0.72,
    ),
    "conversation": StyleProfile(
        name="conversation",
        description="Multicam dialogue with active-speaker cuts, reactions, and group-view fallbacks.",
        caption=_caption(
            "conversation",
            size_ratio=0.035,
            active="&H005ED7F7",
            emphasis="&H005ED7F7",
            animation=CaptionAnimation.RISE,
            max_words=6,
        ),
        brand=replace(_BASE_BRAND, name="conversation"),
        rules=replace(_INTENSITIES[EditIntensity.BALANCED], reaction_rate=0.34, shot_target=5.2),
        allowed_transitions=(TransitionKind.CUT, TransitionKind.DISSOLVE),
        use_sound_effects=False,
        minimum_broll_confidence=0.74,
    ),
    "kinetic-explainer": StyleProfile(
        name="kinetic-explainer",
        description="Dense but semantic motion, progressive labels, diagrams, and controlled SFX.",
        caption=_caption(
            "kinetic-explainer",
            size_ratio=0.040,
            active="&H0054E0FF",
            emphasis="&H0054E0FF",
            animation=CaptionAnimation.WORD_POP,
            max_words=4,
        ),
        brand=replace(_BASE_BRAND, name="kinetic-explainer", accent_color="#FFE05D"),
        rules=_INTENSITIES[EditIntensity.DENSE],
        allowed_transitions=(TransitionKind.CUT, TransitionKind.DISSOLVE, TransitionKind.ZOOM, TransitionKind.WHIP),
        use_sound_effects=True,
        minimum_broll_confidence=0.66,
    ),
    "cinematic-story": StyleProfile(
        name="cinematic-story",
        description="Longer holds, emotional breaths, selective cutaways, and understated text.",
        caption=_caption(
            "cinematic-story",
            size_ratio=0.034,
            active="&H00FFFFFF",
            emphasis="&H00D7C07A",
            animation=CaptionAnimation.FADE,
            max_words=7,
        ),
        brand=replace(_BASE_BRAND, name="cinematic-story", accent_color="#D7C07A"),
        rules=replace(_INTENSITIES[EditIntensity.RESTRAINED], shot_target=10.0, shot_max=17.0),
        allowed_transitions=(TransitionKind.CUT, TransitionKind.DISSOLVE, TransitionKind.DIP_TO_BLACK),
        use_sound_effects=False,
        minimum_broll_confidence=0.72,
    ),
}


def style_names() -> tuple[str, ...]:
    return tuple(_PROFILE_TEMPLATES)


def get_style(name: str = "authority", intensity: EditIntensity | str | None = None) -> StyleProfile:
    key = name.strip().lower()
    if key not in _PROFILE_TEMPLATES:
        available = ", ".join(style_names())
        raise KeyError(f"Unknown style profile {name!r}. Available: {available}")
    profile = _PROFILE_TEMPLATES[key]
    if intensity is None:
        return profile
    resolved = EditIntensity(intensity)
    rules = _INTENSITIES[resolved]
    rules = replace(
        rules,
        proof_priority=max(rules.proof_priority, profile.rules.proof_priority),
        reaction_rate=max(rules.reaction_rate, profile.rules.reaction_rate),
    )
    caption = replace(
        profile.caption,
        max_words=max(3, profile.caption.max_words - (1 if resolved in {EditIntensity.DENSE, EditIntensity.MAXIMAL} else 0)),
    )
    return replace(profile, rules=rules, caption=caption)
