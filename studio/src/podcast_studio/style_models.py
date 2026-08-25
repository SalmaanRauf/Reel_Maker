from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .exceptions import ValidationError


class EditIntensity(str, Enum):
    RESTRAINED = "restrained"
    BALANCED = "balanced"
    DENSE = "dense"
    MAXIMAL = "maximal"


class Easing(str, Enum):
    HOLD = "hold"
    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"
    SPRING = "spring"


class MotionKind(str, Enum):
    HOLD = "hold"
    PUNCH_IN = "punch_in"
    PULL_BACK = "pull_back"
    REFRAME = "reframe"
    PUSH_THROUGH = "push_through"
    PAN = "pan"
    KEN_BURNS = "ken_burns"
    CUSTOM = "custom"


class TransitionKind(str, Enum):
    CUT = "cut"
    DISSOLVE = "dissolve"
    DIP_TO_BLACK = "dip_to_black"
    DIP_TO_WHITE = "dip_to_white"
    ZOOM = "zoom"
    BLUR = "blur"
    WIPE_LEFT = "wipe_left"
    WIPE_RIGHT = "wipe_right"
    WHIP = "whip"


class OverlayKind(str, Enum):
    BROLL = "broll"
    PROOF = "proof"
    SCREENSHOT = "screenshot"
    IMAGE = "image"
    LOGO = "logo"
    FULLSCREEN = "fullscreen"
    INSET = "inset"


class LayoutKind(str, Enum):
    SINGLE = "single"
    SPLIT_VERTICAL = "split_vertical"
    SPLIT_HORIZONTAL = "split_horizontal"
    PICTURE_IN_PICTURE = "picture_in_picture"
    GRID = "grid"
    GROUP = "group"
    CONTENT_SHARE = "content_share"


class TextRole(str, Enum):
    EYEBROW = "eyebrow"
    HEADLINE = "headline"
    SUBHEAD = "subhead"
    LABEL = "label"
    QUOTE = "quote"
    STATISTIC = "statistic"
    EVIDENCE = "evidence"
    SOURCE = "source"
    CALLOUT = "callout"


class EvidenceKind(str, Enum):
    SOURCE = "source"
    SCREENSHOT = "screenshot"
    DOCUMENT = "document"
    CHART = "chart"
    PRODUCT = "product"
    UI = "ui"
    BEFORE_AFTER = "before_after"


class CaptionAnimation(str, Enum):
    NONE = "none"
    FADE = "fade"
    POP = "pop"
    RISE = "rise"
    WORD_POP = "word_pop"
    ACTIVE_FILL = "active_fill"
    BOUNCE = "bounce"


@dataclass(slots=True)
class SafeArea:
    left: float = 0.06
    right: float = 0.06
    top: float = 0.08
    bottom: float = 0.16
    subject_top: float = 0.05
    subject_bottom: float = 0.12

    def __post_init__(self) -> None:
        for name in self.__slots__:
            if not 0 <= float(getattr(self, name)) < 0.5:
                raise ValidationError(f"Safe-area value {name} must be between 0 and 0.5")

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "SafeArea":
        return cls(**(value or {}))


@dataclass(slots=True)
class BrandKit:
    name: str = "editorial-default"
    font_family: str = "Arial"
    font_file: str | None = None
    headline_font_family: str | None = None
    headline_font_file: str | None = None
    primary_color: str = "#FFFFFF"
    secondary_color: str = "#B7BDC8"
    accent_color: str = "#F7D154"
    evidence_color: str = "#79B8FF"
    background_color: str = "#0C0D10"
    logo_path: str | None = None
    corner_radius: int = 28
    stroke_width: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "BrandKit":
        return cls(**(value or {}))


@dataclass(slots=True)
class CaptionStyle:
    name: str = "editorial-clean"
    font_family: str = "Arial"
    font_file: str | None = None
    font_size: int = 64
    font_size_ratio: float = 0.039
    min_font_size: int = 42
    max_font_size: int = 96
    primary_color: str = "&H00FFFFFF"
    secondary_color: str = "&H008F8F8F"
    active_color: str = "&H0054D1F7"
    emphasis_color: str = "&H0054D1F7"
    outline_color: str = "&H00101010"
    back_color: str = "&H99000000"
    outline: float = 3.0
    shadow: float = 0.0
    bold: bool = True
    uppercase: bool = False
    preserve_punctuation: bool = True
    alignment: int = 2
    margin_v: int = 150
    safe_margin_x_ratio: float = 0.07
    safe_top_ratio: float = 0.08
    safe_bottom_ratio: float = 0.16
    max_words: int = 5
    max_chars: int = 32
    max_lines: int = 2
    pause_split: float = 0.32
    minimum_duration: float = 0.28
    maximum_duration: float = 3.2
    maximum_chars_per_second: float = 21.0
    karaoke: bool = True
    box: bool = False
    active_word_box: bool = False
    background_padding: int = 16
    background_radius: int = 18
    line_spacing: int = 8
    letter_spacing: float = 0.0
    animation: CaptionAnimation = CaptionAnimation.WORD_POP
    animation_ms: int = 110
    active_scale: float = 1.06
    random_rotation_degrees: float = 0.0
    auto_move: bool = True
    auto_scale: bool = True
    emphasis_words: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.animation = CaptionAnimation(self.animation)
        if self.font_size <= 0 or self.min_font_size <= 0 or self.max_font_size < self.min_font_size:
            raise ValidationError("Caption font sizes are invalid")
        if not 0.01 <= self.font_size_ratio <= 0.15:
            raise ValidationError("Caption font-size ratio is invalid")
        if self.max_words < 1 or self.max_chars < 4 or self.max_lines not in {1, 2, 3}:
            raise ValidationError("Caption chunk limits are invalid")
        if self.pause_split < 0 or self.minimum_duration <= 0 or self.maximum_duration <= self.minimum_duration:
            raise ValidationError("Caption timing limits are invalid")
        if not 0.8 <= self.active_scale <= 1.5:
            raise ValidationError("Caption active scale is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "CaptionStyle":
        if not value:
            return cls()
        allowed = set(cls.__dataclass_fields__)
        payload = {key: item for key, item in value.items() if key in allowed}
        if "animation" in payload:
            payload["animation"] = CaptionAnimation(payload["animation"])
        return cls(**payload)


@dataclass(slots=True)
class Transform:
    zoom: float = 1.0
    crop_x: float = 0.5
    crop_y: float = 0.5
    rotation: float = 0.0
    opacity: float = 1.0

    def __post_init__(self) -> None:
        if not 1 <= self.zoom <= 4:
            raise ValidationError("Zoom must be between 1 and 4")
        if not 0 <= self.crop_x <= 1 or not 0 <= self.crop_y <= 1:
            raise ValidationError("Crop anchors must be normalized")
        if not 0 <= self.opacity <= 1:
            raise ValidationError("Opacity must be normalized")

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "Transform":
        return cls(**(value or {}))


@dataclass(slots=True)
class MotionKeyframe:
    time: float
    zoom: float = 1.0
    crop_x: float = 0.5
    crop_y: float = 0.5
    rotation: float = 0.0
    opacity: float = 1.0
    easing: Easing = Easing.EASE_IN_OUT

    def __post_init__(self) -> None:
        self.easing = Easing(self.easing)
        if self.time < 0 or not math.isfinite(self.time):
            raise ValidationError("Motion keyframe time must be finite and non-negative")
        Transform(self.zoom, self.crop_x, self.crop_y, self.rotation, self.opacity)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MotionKeyframe":
        return cls(
            time=float(value["time"]), zoom=float(value.get("zoom", 1)),
            crop_x=float(value.get("crop_x", 0.5)), crop_y=float(value.get("crop_y", 0.5)),
            rotation=float(value.get("rotation", 0)), opacity=float(value.get("opacity", 1)),
            easing=Easing(value.get("easing", "ease_in_out")),
        )


@dataclass(slots=True)
class MotionTrack:
    kind: MotionKind = MotionKind.HOLD
    keyframes: list[MotionKeyframe] = field(default_factory=list)
    reason: str = "stable hold"
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.kind = MotionKind(self.kind)
        self.keyframes.sort(key=lambda item: item.time)
        if not 0 <= self.confidence <= 1:
            raise ValidationError("Motion confidence must be normalized")
        if any(a.time == b.time for a, b in zip(self.keyframes, self.keyframes[1:], strict=False)):
            raise ValidationError("Motion keyframes must have unique times")

    def validate_duration(self, duration: float) -> None:
        if any(item.time > duration + 1e-6 for item in self.keyframes):
            raise ValidationError("Motion keyframe exceeds segment duration")

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "MotionTrack":
        if not value:
            return cls()
        return cls(
            kind=MotionKind(value.get("kind", "hold")),
            keyframes=[MotionKeyframe.from_dict(item) for item in value.get("keyframes", [])],
            reason=str(value.get("reason", "stable hold")), confidence=float(value.get("confidence", 1)),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(slots=True)
class Transition:
    kind: TransitionKind = TransitionKind.CUT
    duration: float = 0.0
    easing: Easing = Easing.EASE_IN_OUT
    reason: str = "editorial cut"

    def __post_init__(self) -> None:
        self.kind = TransitionKind(self.kind)
        self.easing = Easing(self.easing)
        if self.duration < 0 or self.duration > 2.0:
            raise ValidationError("Transition duration must be between 0 and 2 seconds")
        if self.kind == TransitionKind.CUT:
            self.duration = 0.0
        elif self.duration <= 0:
            raise ValidationError("Non-cut transitions require positive duration")

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "Transition":
        return cls(**(value or {}))
