from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .director import BrollCue
from .exceptions import ValidationError
from .models import (
    Easing,
    MotionKeyframe,
    MotionKind,
    MotionTrack,
    Overlay,
    OverlayKind,
    Transition,
    TransitionKind,
)
from .util import clamp, dump_json, load_json, sha256_file, stable_id

MEDIA_EXTENSIONS = {
    ".mp4": "video", ".mov": "video", ".m4v": "video", ".webm": "video", ".mkv": "video",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".bmp": "image",
    ".gif": "image", ".pdf": "document",
}
GENERIC_TERMS = {
    "business", "technology", "person", "people", "woman", "man", "office", "city", "abstract", "background",
    "lifestyle", "success", "health", "medical", "science", "computer", "phone", "money", "future", "innovation",
}
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "to", "of", "in", "on", "at", "for", "from", "with", "without",
    "this", "that", "these", "those", "is", "are", "was", "were", "be", "been", "being", "it", "its", "they",
    "their", "we", "our", "you", "your", "i", "my", "as", "by", "about", "into", "over", "under", "why",
    "how", "what", "when", "where", "who", "which", "can", "could", "would", "should", "will", "just", "very",
}


@dataclass(slots=True)
class AssetRecord:
    id: str
    path: str
    kind: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    source_url: str | None = None
    license: str | None = None
    attribution: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    fingerprint: str | None = None
    generated: bool = False
    verified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.kind = self.kind.lower()
        if self.kind not in {"video", "image", "screenshot", "document", "chart", "ui", "product"}:
            raise ValidationError(f"Unsupported B-roll asset kind: {self.kind}")
        self.tags = sorted({_clean_token(item) for item in self.tags if _clean_token(item)})
        self.roles = sorted({_clean_token(item) for item in self.roles if _clean_token(item)})
        if (self.width is not None and self.width <= 0) or (self.height is not None and self.height <= 0):
            raise ValidationError("Asset dimensions must be positive")
        if self.duration is not None and self.duration <= 0:
            raise ValidationError("Asset duration must be positive")

    @property
    def has_provenance(self) -> bool:
        return bool(self.license and (self.source_url or self.metadata.get("original")))

    @property
    def aspect_ratio(self) -> float | None:
        if not self.width or not self.height:
            return None
        return self.width / self.height

    @property
    def search_text(self) -> str:
        values = [self.description, *self.tags, *self.roles, Path(self.path).stem.replace("_", " ").replace("-", " ")]
        return " ".join(item for item in values if item)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AssetRecord":
        return cls(
            id=str(value.get("id") or stable_id("asset", value.get("path", ""))),
            path=str(value["path"]), kind=str(value.get("kind", _kind_from_path(value["path"]))),
            description=str(value.get("description", "")), tags=[str(item) for item in value.get("tags", [])],
            roles=[str(item) for item in value.get("roles", [])], source_url=value.get("source_url"),
            license=value.get("license"), attribution=value.get("attribution"),
            width=int(value["width"]) if value.get("width") else None,
            height=int(value["height"]) if value.get("height") else None,
            duration=float(value["duration"]) if value.get("duration") else None,
            fingerprint=value.get("fingerprint"), generated=bool(value.get("generated", False)),
            verified=bool(value.get("verified", False)), metadata=dict(value.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AssetCatalog:
    assets: list[AssetRecord] = field(default_factory=list)
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ids = [item.id for item in self.assets]
        if len(ids) != len(set(ids)):
            raise ValidationError("B-roll catalog contains duplicate asset IDs")

    @classmethod
    def load(cls, path: str | Path) -> "AssetCatalog":
        source = Path(path)
        if not source.is_file():
            return cls()
        payload = load_json(source)
        values = payload.get("assets", payload) if isinstance(payload, dict) else payload
        if not isinstance(values, list):
            raise ValidationError("B-roll catalog must contain an assets array")
        return cls(
            assets=[AssetRecord.from_dict(item) for item in values if isinstance(item, dict)],
            version=int(payload.get("version", 1)) if isinstance(payload, dict) else 1,
            metadata=dict(payload.get("metadata", {})) if isinstance(payload, dict) else {},
        )

    def save(self, path: str | Path) -> Path:
        return dump_json({"version": self.version, "assets": [item.to_dict() for item in self.assets], "metadata": self.metadata}, path)

    def add(self, asset: AssetRecord) -> None:
        for index, existing in enumerate(self.assets):
            if existing.id == asset.id:
                self.assets[index] = asset
                return
        self.assets.append(asset)

    @classmethod
    def index_directory(cls, root: str | Path, *, assume_license: str | None = None) -> "AssetCatalog":
        directory = Path(root).expanduser().resolve()
        if not directory.is_dir():
            raise ValidationError(f"B-roll directory not found: {directory}")
        assets: list[AssetRecord] = []
        for path in sorted(directory.rglob("*")):
            kind = MEDIA_EXTENSIONS.get(path.suffix.lower())
            if not kind or path.name.endswith(".asset.json"):
                continue
            sidecar = path.with_suffix(path.suffix + ".asset.json")
            metadata: dict[str, Any] = {}
            if sidecar.is_file():
                loaded = json.loads(sidecar.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    metadata = loaded
            relative = path.relative_to(directory).as_posix()
            record = AssetRecord.from_dict(
                {
                    "id": metadata.get("id") or stable_id("asset", relative, path.stat().st_size),
                    "path": relative,
                    "kind": metadata.get("kind", kind),
                    "description": metadata.get("description", " ".join(path.stem.replace("_", " ").replace("-", " ").split())),
                    "tags": metadata.get("tags", [part for part in path.parent.relative_to(directory).parts]),
                    "roles": metadata.get("roles", []),
                    "source_url": metadata.get("source_url"),
                    "license": metadata.get("license", assume_license),
                    "attribution": metadata.get("attribution"),
                    "width": metadata.get("width"), "height": metadata.get("height"), "duration": metadata.get("duration"),
                    "fingerprint": metadata.get("fingerprint") or sha256_file(path),
                    "generated": metadata.get("generated", False), "verified": metadata.get("verified", False),
                    "metadata": {**metadata.get("metadata", {}), "original": str(path)},
                }
            )
            assets.append(record)
        return cls(assets=assets, metadata={"root": str(directory)})


@dataclass(slots=True, frozen=True)
class AssetMatch:
    asset: AssetRecord
    score: float
    breakdown: dict[str, float]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"asset": self.asset.to_dict(), "score": self.score, "breakdown": self.breakdown, "reasons": list(self.reasons)}


def rank_assets(
    cue: BrollCue,
    assets: Iterable[AssetRecord],
    *,
    output_width: int = 1080,
    output_height: int = 1920,
    used_fingerprints: set[str] | None = None,
    minimum_score: float = 0.0,
    limit: int = 10,
) -> list[AssetMatch]:
    used_fingerprints = used_fingerprints or set()
    cue_tokens = _tokens(" ".join([cue.query, cue.reason, cue.transcript_text]))
    cue_phrases = _phrases(cue.query)
    target_aspect = output_width / output_height
    matches: list[AssetMatch] = []
    for asset in assets:
        asset_tokens = _tokens(asset.search_text)
        overlap = cue_tokens & asset_tokens
        weighted_overlap = sum(_token_weight(token) for token in overlap)
        query_weight = sum(_token_weight(token) for token in cue_tokens) or 1.0
        lexical = weighted_overlap / query_weight
        phrase = 1.0 if cue_phrases and any(item in asset.search_text.lower() for item in cue_phrases) else 0.0
        role = 1.0 if cue.role in asset.roles else 0.65 if cue.role == "proof" and asset.kind in {"screenshot", "document", "chart", "ui"} else 0.35 if overlap else 0.0
        media_preference = _media_preference(asset, cue.preferred_media)
        aspect = _aspect_score(asset.aspect_ratio, target_aspect)
        resolution = _resolution_score(asset, output_width, output_height)
        provenance = 1.0 if asset.has_provenance else 0.45 if not cue.require_provenance else 0.0
        verified = 1.0 if asset.verified else 0.6
        generic_ratio = len(asset_tokens & GENERIC_TERMS) / max(1, len(asset_tokens))
        duplicate = 1.0 if asset.fingerprint and asset.fingerprint in used_fingerprints else 0.0
        generated_penalty = 0.18 if asset.generated and not cue.allow_generated else 0.0
        score = (
            lexical * 0.34 + phrase * 0.12 + role * 0.15 + media_preference * 0.08 + aspect * 0.08
            + resolution * 0.06 + provenance * 0.09 + verified * 0.04 + cue.confidence * 0.09
            - generic_ratio * 0.18 - duplicate * 0.55 - generated_penalty
        )
        score = clamp(score, 0.0, 1.0)
        if cue.require_provenance and not asset.has_provenance:
            continue
        if score < minimum_score:
            continue
        reasons: list[str] = []
        if overlap:
            reasons.append("shared semantic terms: " + ", ".join(sorted(overlap)[:6]))
        if phrase:
            reasons.append("exact cue phrase")
        if role >= 0.65:
            reasons.append(f"fits {cue.role} role")
        if asset.has_provenance:
            reasons.append("provenance complete")
        if asset.fingerprint and asset.fingerprint in used_fingerprints:
            reasons.append("duplicate asset penalty")
        matches.append(
            AssetMatch(
                asset=asset,
                score=round(score, 6),
                breakdown={
                    "lexical": round(lexical, 6), "phrase": phrase, "role": role,
                    "media_preference": media_preference, "aspect": round(aspect, 6),
                    "resolution": round(resolution, 6), "provenance": provenance,
                    "verified": verified, "generic_penalty": round(generic_ratio, 6),
                    "duplicate_penalty": duplicate, "generated_penalty": generated_penalty,
                },
                reasons=tuple(reasons),
            )
        )
    return sorted(matches, key=lambda item: (-item.score, item.asset.id))[:limit]


def resolve_broll_cues(
    cues: Sequence[BrollCue],
    catalog: AssetCatalog,
    *,
    output_width: int = 1080,
    output_height: int = 1920,
    minimum_score: float = 0.62,
    coverage_cap: float | None = None,
    plan_duration: float | None = None,
) -> tuple[list[Overlay], list[dict[str, Any]]]:
    used: set[str] = set()
    overlays: list[Overlay] = []
    decisions: list[dict[str, Any]] = []
    covered = 0.0
    maximum_coverage = math.inf if coverage_cap is None or plan_duration is None else plan_duration * coverage_cap
    for cue in sorted(cues, key=lambda item: (item.start, -item.confidence)):
        if covered >= maximum_coverage:
            decisions.append({"cue": cue.to_dict(), "status": "skipped", "reason": "coverage cap reached"})
            continue
        matches = rank_assets(
            cue, catalog.assets, output_width=output_width, output_height=output_height,
            used_fingerprints=used, minimum_score=minimum_score, limit=5,
        )
        if not matches:
            decisions.append({"cue": cue.to_dict(), "status": "unresolved", "reason": "no asset cleared semantic/provenance threshold"})
            continue
        match = matches[0]
        duration = min(cue.end - cue.start, maximum_coverage - covered)
        if duration < 1.0:
            decisions.append({"cue": cue.to_dict(), "status": "skipped", "reason": "remaining coverage budget below one second"})
            continue
        end = cue.start + duration
        kind = _overlay_kind(cue.role, match.asset.kind)
        motion = _asset_motion(match.asset, cue, duration)
        overlay = Overlay(
            path=match.asset.path,
            start=cue.start,
            end=end,
            source_start=0.0,
            source_end=min(duration, match.asset.duration) if match.asset.duration else None,
            width=output_width if kind in {OverlayKind.BROLL, OverlayKind.FULLSCREEN, OverlayKind.PROOF, OverlayKind.SCREENSHOT} else None,
            height=output_height if kind in {OverlayKind.BROLL, OverlayKind.FULLSCREEN} else None,
            opacity=1.0,
            kind=kind,
            label=cue.query,
            fit="cover" if kind in {OverlayKind.BROLL, OverlayKind.FULLSCREEN} else "contain",
            mute=True,
            corner_radius=0 if kind in {OverlayKind.BROLL, OverlayKind.FULLSCREEN} else 26,
            motion=motion,
            transition_in=Transition(TransitionKind.DISSOLVE, 0.10, reason="semantic insert enter"),
            transition_out=Transition(TransitionKind.DISSOLVE, 0.10, reason="semantic insert exit"),
            semantic_reason=cue.reason,
            semantic_confidence=match.score,
            source_url=match.asset.source_url,
            license=match.asset.license,
            asset_fingerprint=match.asset.fingerprint,
            metadata={
                "asset_id": match.asset.id, "cue_id": cue.id, "role": cue.role,
                "rank_breakdown": match.breakdown, "rank_reasons": list(match.reasons),
                "attribution": match.asset.attribution, "generated": match.asset.generated,
            },
        )
        overlays.append(overlay)
        covered += duration
        if match.asset.fingerprint:
            used.add(match.asset.fingerprint)
        decisions.append({"cue": cue.to_dict(), "status": "resolved", "selected": match.to_dict(), "overlay": asdict(overlay)})
    return overlays, decisions


def _asset_motion(asset: AssetRecord, cue: BrollCue, duration: float) -> MotionTrack:
    if asset.kind == "video":
        return MotionTrack(kind=MotionKind.HOLD, keyframes=[MotionKeyframe(0, 1.0), MotionKeyframe(duration, 1.0)], reason="preserve native B-roll motion")
    seed = sum(ord(character) for character in f"{asset.id}:{cue.id}")
    start_x = 0.47 if seed % 2 else 0.53
    end_x = 1.0 - start_x
    start_y = 0.47 if seed % 3 else 0.53
    end_y = 1.0 - start_y
    return MotionTrack(
        kind=MotionKind.KEN_BURNS,
        keyframes=[
            MotionKeyframe(0, 1.0, start_x, start_y, easing=Easing.EASE_IN_OUT),
            MotionKeyframe(duration, 1.045, end_x, end_y, easing=Easing.EASE_IN_OUT),
        ],
        reason="subtle still-image movement toward the semantic subject",
        confidence=cue.confidence,
    )


def _media_preference(asset: AssetRecord, preferred: Sequence[str]) -> float:
    normalized = "image" if asset.kind in {"screenshot", "document", "chart", "ui", "product"} else asset.kind
    try:
        index = preferred.index(normalized)
    except ValueError:
        try:
            index = preferred.index(asset.kind)
        except ValueError:
            return 0.15
    return max(0.25, 1.0 - index * 0.25)


def _aspect_score(aspect: float | None, target: float) -> float:
    if not aspect:
        return 0.5
    distance = abs(math.log(max(0.05, aspect) / max(0.05, target)))
    return math.exp(-distance * 0.85)


def _resolution_score(asset: AssetRecord, width: int, height: int) -> float:
    if not asset.width or not asset.height:
        return 0.5
    scale = min(asset.width / width, asset.height / height)
    return clamp(scale, 0.0, 1.0)


def _overlay_kind(role: str, kind: str) -> OverlayKind:
    if role == "proof" or kind in {"document", "chart", "ui"}:
        return OverlayKind.PROOF
    if kind == "screenshot":
        return OverlayKind.SCREENSHOT
    if kind == "image":
        return OverlayKind.IMAGE
    return OverlayKind.BROLL


def _kind_from_path(path: str | Path) -> str:
    return MEDIA_EXTENSIONS.get(Path(path).suffix.lower(), "image")


def _phrases(value: str) -> list[str]:
    normalized = " ".join(_clean_token(item) for item in value.split() if _clean_token(item))
    words = normalized.split()
    return [" ".join(words[index : index + size]) for size in (3, 2) for index in range(max(0, len(words) - size + 1))]


def _tokens(value: str) -> set[str]:
    return {_clean_token(item) for item in re.findall(r"[A-Za-z0-9%$'-]+", value) if _clean_token(item) not in STOPWORDS and len(_clean_token(item)) >= 2}


def _clean_token(value: str) -> str:
    return re.sub(r"[^a-z0-9%$-]+", "", value.lower()).strip("-")


def _token_weight(token: str) -> float:
    if any(character.isdigit() for character in token):
        return 1.7
    if token in GENERIC_TERMS:
        return 0.35
    return 1.0 + min(0.6, max(0, len(token) - 5) * 0.08)
