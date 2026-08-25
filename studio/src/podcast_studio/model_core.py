from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .exceptions import ValidationError
from .util import compact_whitespace, stable_id, utc_now


class AssetRole(str, Enum):
    CAMERA = "camera"
    AUDIO = "audio"
    BROLL = "broll"
    MUSIC = "music"
    IMAGE = "image"
    OTHER = "other"


class CaptionMode(str, Enum):
    NONE = "none"
    BURN = "burn"
    SIDECAR = "sidecar"
    BOTH = "both"


@dataclass(slots=True, frozen=True)
class TimeRange:
    start: float
    end: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.start) or not math.isfinite(self.end):
            raise ValidationError("Time ranges must be finite")
        if self.start < 0 or self.end <= self.start:
            raise ValidationError(f"Invalid time range {self.start}–{self.end}")

    @property
    def duration(self) -> float:
        return self.end - self.start

    def overlaps(self, other: "TimeRange") -> bool:
        return self.start < other.end and other.start < self.end

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TimeRange":
        return cls(float(value["start"]), float(value["end"]))


@dataclass(slots=True)
class MediaStream:
    index: int
    codec_type: str
    codec_name: str | None = None
    width: int | None = None
    height: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    duration: float | None = None
    frame_rate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MediaStream":
        return cls(**value)


@dataclass(slots=True)
class MediaAsset:
    id: str
    path: str
    role: AssetRole = AssetRole.CAMERA
    duration: float = 0.0
    streams: list[MediaStream] = field(default_factory=list)
    offset: float = 0.0
    label: str | None = None
    sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.role = AssetRole(self.role)
        if self.duration < 0 or not math.isfinite(self.duration):
            raise ValidationError(f"Invalid duration for asset {self.id}")
        if not math.isfinite(self.offset):
            raise ValidationError(f"Invalid offset for asset {self.id}")

    @property
    def has_video(self) -> bool:
        return any(stream.codec_type == "video" for stream in self.streams)

    @property
    def has_audio(self) -> bool:
        return any(stream.codec_type == "audio" for stream in self.streams)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MediaAsset":
        return cls(
            id=str(value["id"]),
            path=str(value["path"]),
            role=AssetRole(value.get("role", "camera")),
            duration=float(value.get("duration", 0)),
            streams=[MediaStream.from_dict(item) for item in value.get("streams", [])],
            offset=float(value.get("offset", 0)),
            label=value.get("label"),
            sha256=value.get("sha256"),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(slots=True)
class Word:
    text: str
    start: float
    end: float
    speaker: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        self.text = compact_whitespace(self.text)
        if not self.text:
            raise ValidationError("Transcript word cannot be empty")
        if self.start < 0 or self.end <= self.start:
            raise ValidationError(f"Invalid word timing for {self.text!r}")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValidationError("Word confidence must be between zero and one")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Word":
        confidence = value.get("confidence", value.get("probability"))
        return cls(
            text=str(value.get("text", value.get("word", ""))).strip(),
            start=float(value["start"]),
            end=float(value["end"]),
            speaker=value.get("speaker"),
            confidence=float(confidence) if confidence is not None else None,
        )


@dataclass(slots=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: str | None = None
    words: list[Word] = field(default_factory=list)
    id: str | None = None

    def __post_init__(self) -> None:
        self.text = compact_whitespace(self.text)
        if self.start < 0 or self.end <= self.start:
            raise ValidationError("Invalid transcript segment timing")
        if not self.id:
            self.id = stable_id("seg", round(self.start, 3), round(self.end, 3), self.text)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TranscriptSegment":
        return cls(
            id=value.get("id"),
            start=float(value["start"]),
            end=float(value["end"]),
            text=str(value.get("text", "")),
            speaker=value.get("speaker"),
            words=[Word.from_dict(item) for item in value.get("words", [])],
        )


@dataclass(slots=True)
class Transcript:
    asset_id: str
    language: str = "en"
    segments: list[TranscriptSegment] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)
    engine: str = "import"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.segments.sort(key=lambda item: (item.start, item.end))
        self.words.sort(key=lambda item: (item.start, item.end))
        if not self.words:
            self.words = [word for segment in self.segments for word in segment.words]

    @property
    def duration(self) -> float:
        return max([item.end for item in self.segments] + [item.end for item in self.words], default=0.0)

    @property
    def text(self) -> str:
        if self.segments:
            return compact_whitespace(" ".join(item.text for item in self.segments))
        return compact_whitespace(" ".join(item.text for item in self.words))

    def words_in(self, start: float, end: float) -> list[Word]:
        return [word for word in self.words if word.end > start and word.start < end]

    def text_in(self, start: float, end: float) -> str:
        words = self.words_in(start, end)
        if words:
            return compact_whitespace(" ".join(word.text for word in words))
        return compact_whitespace(" ".join(s.text for s in self.segments if s.end > start and s.start < end))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Transcript":
        return cls(
            asset_id=str(value.get("asset_id", "unknown")),
            language=str(value.get("language", "en")),
            segments=[TranscriptSegment.from_dict(item) for item in value.get("segments", [])],
            words=[Word.from_dict(item) for item in value.get("words", [])],
            engine=str(value.get("engine", "import")),
            metadata=dict(value.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return json_value(asdict(self))


@dataclass(slots=True)
class ClipCandidate:
    id: str
    start: float
    end: float
    title: str
    hook: str
    summary: str
    score: float
    score_breakdown: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    caveat: str | None = None
    transcript: str = ""
    source_id: str | None = None
    status: str = "proposed"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValidationError("Invalid clip timing")
        if not 0 <= self.score <= 100:
            raise ValidationError("Clip score must be between zero and 100")
        if self.status not in {"proposed", "approved", "rejected", "rendered"}:
            raise ValidationError(f"Invalid clip status {self.status}")

    @property
    def duration(self) -> float:
        return self.end - self.start

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ClipCandidate":
        return cls(
            id=str(value.get("id") or stable_id("clip", value.get("start"), value.get("end"))),
            start=float(value["start"]),
            end=float(value["end"]),
            title=str(value.get("title", "Untitled clip")),
            hook=str(value.get("hook", "")),
            summary=str(value.get("summary", "")),
            score=float(value.get("score", 0)),
            score_breakdown={str(k): float(v) for k, v in value.get("score_breakdown", {}).items()},
            reasons=[str(item) for item in value.get("reasons", [])],
            caveat=value.get("caveat"),
            transcript=str(value.get("transcript", "")),
            source_id=value.get("source_id"),
            status=str(value.get("status", "proposed")),
            metadata=dict(value.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return json_value(asdict(self))


@dataclass(slots=True)
class ProjectManifest:
    id: str
    name: str
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    assets: list[MediaAsset] = field(default_factory=list)
    primary_asset_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def asset(self, asset_id: str) -> MediaAsset:
        for asset in self.assets:
            if asset.id == asset_id:
                return asset
        raise ValidationError(f"Unknown asset id: {asset_id}")

    def upsert_asset(self, asset: MediaAsset) -> None:
        for index, existing in enumerate(self.assets):
            if existing.id == asset.id:
                self.assets[index] = asset
                break
        else:
            self.assets.append(asset)
        if not self.primary_asset_id and asset.role in {AssetRole.CAMERA, AssetRole.AUDIO}:
            self.primary_asset_id = asset.id
        self.updated_at = utc_now()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProjectManifest":
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            created_at=str(value.get("created_at", utc_now())),
            updated_at=str(value.get("updated_at", utc_now())),
            assets=[MediaAsset.from_dict(item) for item in value.get("assets", [])],
            primary_asset_id=value.get("primary_asset_id"),
            metadata=dict(value.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return json_value(asdict(self))


@dataclass(slots=True)
class QCCheck:
    name: str
    passed: bool
    severity: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QCReport:
    render_path: str
    checks: list[QCCheck]
    created_at: str = field(default_factory=utc_now)
    contact_sheet: str | None = None
    cut_frames: list[str] = field(default_factory=list)
    technical: dict[str, Any] = field(default_factory=dict)
    aesthetic: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(item.passed or item.severity != "error" for item in self.checks)

    @property
    def score(self) -> int:
        penalty = sum(
            20 if not item.passed and item.severity == "error" else 7 if not item.passed and item.severity == "warning" else 3
            for item in self.checks
            if not item.passed
        )
        return max(0, 100 - penalty)

    def to_dict(self) -> dict[str, Any]:
        value = json_value(asdict(self))
        value["passed"] = self.passed
        value["score"] = self.score
        return value


def json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value
