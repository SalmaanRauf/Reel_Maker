from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .exceptions import ValidationError
from .model_core import CaptionMode, json_value
from .style_models import (
    BrandKit, CaptionStyle, EditIntensity, EvidenceKind, LayoutKind, MotionTrack,
    OverlayKind, SafeArea, TextRole, Transform, Transition, TransitionKind,
)
from .util import clamp, stable_id


@dataclass(slots=True)
class EditSegment:
    source_id: str
    source_start: float
    source_end: float
    reason: str
    transform: Transform = field(default_factory=Transform)
    motion: MotionTrack = field(default_factory=MotionTrack)
    transition_to_next: Transition = field(default_factory=Transition)
    layout: LayoutKind = LayoutKind.SINGLE
    speaker: str | None = None
    label: str | None = None
    audio_gain_db: float = 0.0
    color_filter: str | None = None
    audio_source_id: str | None = None
    audio_source_start: float | None = None
    audio_source_end: float | None = None
    camera_priority: float = 0.5
    reaction: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.layout = LayoutKind(self.layout)
        if self.source_start < 0 or self.source_end <= self.source_start:
            raise ValidationError("Invalid edit segment timing")
        if not self.reason.strip():
            raise ValidationError("Every edit segment needs an editorial reason")
        if self.audio_source_start is not None and self.audio_source_start < 0:
            raise ValidationError("Audio source start cannot be negative")
        if self.audio_source_end is not None and self.audio_source_start is not None and self.audio_source_end <= self.audio_source_start:
            raise ValidationError("Audio source end must follow audio source start")
        if not 0 <= self.camera_priority <= 1:
            raise ValidationError("Camera priority must be normalized")
        self.motion.validate_duration(self.duration)
        if self.transition_to_next.duration >= self.duration:
            raise ValidationError("Transition cannot consume the entire segment")

    @property
    def duration(self) -> float:
        return self.source_end - self.source_start

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EditSegment":
        return cls(
            source_id=str(value["source_id"]), source_start=float(value["source_start"]),
            source_end=float(value["source_end"]), reason=str(value.get("reason", "kept by editor")),
            transform=Transform.from_dict(value.get("transform")), motion=MotionTrack.from_dict(value.get("motion")),
            transition_to_next=Transition.from_dict(value.get("transition_to_next")),
            layout=LayoutKind(value.get("layout", "single")), speaker=value.get("speaker"), label=value.get("label"),
            audio_gain_db=float(value.get("audio_gain_db", 0)), color_filter=value.get("color_filter"),
            audio_source_id=value.get("audio_source_id"),
            audio_source_start=float(value["audio_source_start"]) if value.get("audio_source_start") is not None else None,
            audio_source_end=float(value["audio_source_end"]) if value.get("audio_source_end") is not None else None,
            camera_priority=float(value.get("camera_priority", 0.5)), reaction=bool(value.get("reaction", False)),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(slots=True)
class Overlay:
    path: str
    start: float
    end: float
    source_start: float = 0.0
    source_end: float | None = None
    x: str = "(W-w)/2"
    y: str = "(H-h)/2"
    width: int | None = None
    height: int | None = None
    opacity: float = 1.0
    kind: OverlayKind = OverlayKind.BROLL
    label: str | None = None
    fit: str = "cover"
    mute: bool = True
    corner_radius: int = 0
    motion: MotionTrack = field(default_factory=MotionTrack)
    transition_in: Transition = field(default_factory=lambda: Transition(TransitionKind.DISSOLVE, 0.12, reason="overlay enter"))
    transition_out: Transition = field(default_factory=lambda: Transition(TransitionKind.DISSOLVE, 0.12, reason="overlay exit"))
    semantic_reason: str | None = None
    semantic_confidence: float = 1.0
    source_url: str | None = None
    license: str | None = None
    asset_fingerprint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.kind = OverlayKind(self.kind)
        if self.start < 0 or self.end <= self.start:
            raise ValidationError("Invalid overlay timing")
        if self.source_start < 0 or (self.source_end is not None and self.source_end <= self.source_start):
            raise ValidationError("Invalid overlay source timing")
        if not 0 <= self.opacity <= 1 or not 0 <= self.semantic_confidence <= 1:
            raise ValidationError("Overlay opacity/confidence must be normalized")
        if self.fit not in {"cover", "contain", "stretch"}:
            raise ValidationError("Overlay fit must be cover, contain, or stretch")
        self.motion.validate_duration(self.end - self.start)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Overlay":
        payload = dict(value)
        payload["kind"] = OverlayKind(payload.get("kind", "broll"))
        payload["motion"] = MotionTrack.from_dict(payload.get("motion"))
        payload["transition_in"] = Transition.from_dict(payload.get("transition_in"))
        payload["transition_out"] = Transition.from_dict(payload.get("transition_out"))
        return cls(**payload)


@dataclass(slots=True)
class TextOverlay:
    start: float
    end: float
    text: str
    role: TextRole = TextRole.HEADLINE
    x: str = "(w-text_w)/2"
    y: str = "h*0.16"
    font_size: int = 72
    min_font_size: int = 36
    max_font_size: int = 112
    max_width_ratio: float = 0.82
    line_height: float = 1.0
    letter_spacing: float = 0.0
    font_file: str | None = None
    font_color: str = "white"
    accent_color: str | None = None
    box: bool = False
    box_color: str = "black@0.55"
    box_border: int = 24
    opacity: float = 1.0
    fade_seconds: float = 0.18
    animation: str = "rise"
    kind: str = "title"
    source_label: str | None = None
    source_url: str | None = None
    priority: int = 50
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.role = TextRole(self.role)
        if self.start < 0 or self.end <= self.start or not self.text.strip():
            raise ValidationError("Invalid text overlay")
        if self.font_size <= 0 or self.min_font_size <= 0 or self.max_font_size < self.min_font_size:
            raise ValidationError("Text overlay font sizes are invalid")
        if not 0.1 <= self.max_width_ratio <= 1:
            raise ValidationError("Text overlay width ratio is invalid")
        self.opacity = clamp(self.opacity, 0.0, 1.0)
        self.fade_seconds = max(0.0, self.fade_seconds)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TextOverlay":
        allowed = set(cls.__dataclass_fields__)
        payload = {key: item for key, item in value.items() if key in allowed}
        payload["role"] = TextRole(payload.get("role", "headline"))
        return cls(**payload)


@dataclass(slots=True)
class EvidenceCard:
    start: float
    end: float
    title: str
    path: str | None = None
    kind: EvidenceKind = EvidenceKind.SOURCE
    source_name: str | None = None
    source_url: str | None = None
    citation: str | None = None
    crop: tuple[float, float, float, float] | None = None
    callout: str | None = None
    x: float = 0.08
    y: float = 0.12
    width: float = 0.84
    height: float = 0.62
    confidence: float = 1.0
    reason: str = "support the spoken claim"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.kind = EvidenceKind(self.kind)
        if self.start < 0 or self.end <= self.start or not self.title.strip():
            raise ValidationError("Invalid evidence card")
        if not 0 <= self.confidence <= 1:
            raise ValidationError("Evidence confidence must be normalized")
        for name in ("x", "y", "width", "height"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValidationError(f"Evidence-card {name} must be normalized")
        if self.x + self.width > 1.001 or self.y + self.height > 1.001:
            raise ValidationError("Evidence card exceeds the canvas")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EvidenceCard":
        payload = dict(value)
        payload["kind"] = EvidenceKind(payload.get("kind", "source"))
        if payload.get("crop") is not None:
            payload["crop"] = tuple(float(item) for item in payload["crop"])
        return cls(**payload)


@dataclass(slots=True)
class LayoutEvent:
    start: float
    end: float
    kind: LayoutKind
    source_ids: list[str]
    active_source_id: str | None = None
    gap: int = 18
    padding: int = 24
    corner_radius: int = 28
    background_color: str = "black"
    reason: str = "speaker-aware layout"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.kind = LayoutKind(self.kind)
        if self.start < 0 or self.end <= self.start or not self.source_ids:
            raise ValidationError("Invalid layout event")
        if self.active_source_id and self.active_source_id not in self.source_ids:
            raise ValidationError("Active layout source must be included in source_ids")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LayoutEvent":
        payload = dict(value)
        payload["kind"] = LayoutKind(payload["kind"])
        payload["source_ids"] = [str(item) for item in payload.get("source_ids", [])]
        return cls(**payload)


@dataclass(slots=True)
class AudioBed:
    path: str
    gain_db: float = -24.0
    start: float = 0.0
    end: float | None = None
    duck: bool = True
    loop: bool = True
    fade_in: float = 0.5
    fade_out: float = 1.0
    semantic_role: str = "bed"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AudioBed":
        return cls(**value)


@dataclass(slots=True)
class SoundEvent:
    path: str
    start: float
    gain_db: float = -12.0
    duration: float | None = None
    role: str = "accent"
    reason: str = "semantic emphasis"
    confidence: float = 1.0
    duck_music_db: float = 3.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.start < 0 or (self.duration is not None and self.duration <= 0):
            raise ValidationError("Invalid sound-event timing")
        if not 0 <= self.confidence <= 1:
            raise ValidationError("Sound-event confidence must be normalized")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SoundEvent":
        return cls(**value)


@dataclass(slots=True)
class CensorEvent:
    start: float
    end: float
    mode: str = "beep"
    frequency: int = 1000

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValidationError("Invalid censor timing")
        if self.mode not in {"beep", "mute"}:
            raise ValidationError("Censor mode must be beep or mute")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CensorEvent":
        return cls(**value)


@dataclass(slots=True)
class EditPlan:
    id: str
    title: str
    segments: list[EditSegment]
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    style_profile: str = "authority"
    intensity: EditIntensity = EditIntensity.BALANCED
    brand: BrandKit = field(default_factory=BrandKit)
    safe_area: SafeArea = field(default_factory=SafeArea)
    caption_mode: CaptionMode = CaptionMode.BURN
    caption_style: CaptionStyle = field(default_factory=CaptionStyle)
    transcript_path: str | None = None
    overlays: list[Overlay] = field(default_factory=list)
    text_overlays: list[TextOverlay] = field(default_factory=list)
    evidence_cards: list[EvidenceCard] = field(default_factory=list)
    layout_events: list[LayoutEvent] = field(default_factory=list)
    music: AudioBed | None = None
    sound_effects: list[SoundEvent] = field(default_factory=list)
    censors: list[CensorEvent] = field(default_factory=list)
    audio_target_lufs: float = -16.0
    audio_true_peak: float = -1.5
    global_color_filter: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.caption_mode = CaptionMode(self.caption_mode)
        self.intensity = EditIntensity(self.intensity)
        if not self.segments:
            raise ValidationError("Edit plan needs at least one segment")
        if self.width <= 0 or self.height <= 0 or self.width % 2 or self.height % 2:
            raise ValidationError("Output dimensions must be positive even integers")
        if not 1 <= self.fps <= 120:
            raise ValidationError("FPS must be between 1 and 120")
        if not self.id:
            self.id = stable_id("plan", self.title, self.duration)
        for event in [*self.overlays, *self.text_overlays, *self.evidence_cards, *self.layout_events]:
            if event.end > self.duration + 0.1:
                raise ValidationError(f"Timeline event exceeds plan duration: {type(event).__name__}")
        if any(event.start > self.duration + 0.1 for event in self.sound_effects):
            raise ValidationError("Sound event exceeds plan duration")

    @property
    def transition_overlap(self) -> float:
        return sum(segment.transition_to_next.duration for segment in self.segments[:-1])

    @property
    def duration(self) -> float:
        return sum(segment.duration for segment in self.segments) - self.transition_overlap

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EditPlan":
        return cls(
            id=str(value.get("id", "")), title=str(value.get("title", "Untitled edit")),
            segments=[EditSegment.from_dict(item) for item in value.get("segments", [])],
            width=int(value.get("width", 1080)), height=int(value.get("height", 1920)), fps=float(value.get("fps", 30)),
            style_profile=str(value.get("style_profile", "authority")), intensity=EditIntensity(value.get("intensity", "balanced")),
            brand=BrandKit.from_dict(value.get("brand")), safe_area=SafeArea.from_dict(value.get("safe_area")),
            caption_mode=CaptionMode(value.get("caption_mode", "burn")), caption_style=CaptionStyle.from_dict(value.get("caption_style")),
            transcript_path=value.get("transcript_path"), overlays=[Overlay.from_dict(item) for item in value.get("overlays", [])],
            text_overlays=[TextOverlay.from_dict(item) for item in value.get("text_overlays", [])],
            evidence_cards=[EvidenceCard.from_dict(item) for item in value.get("evidence_cards", [])],
            layout_events=[LayoutEvent.from_dict(item) for item in value.get("layout_events", [])],
            music=AudioBed.from_dict(value["music"]) if value.get("music") else None,
            sound_effects=[SoundEvent.from_dict(item) for item in value.get("sound_effects", [])],
            censors=[CensorEvent.from_dict(item) for item in value.get("censors", [])],
            audio_target_lufs=float(value.get("audio_target_lufs", -16)), audio_true_peak=float(value.get("audio_true_peak", -1.5)),
            global_color_filter=value.get("global_color_filter"), metadata=dict(value.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return json_value(asdict(self))
