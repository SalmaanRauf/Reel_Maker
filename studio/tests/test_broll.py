from podcast_studio.broll import AssetCatalog, AssetRecord, rank_assets, resolve_broll_cues
from podcast_studio.director import BrollCue
from podcast_studio.models import MotionKind, OverlayKind


def cue() -> BrollCue:
    return BrollCue(
        id="cue-1",
        start=2,
        end=5,
        query="2024 mouse study 37 percent",
        role="proof",
        reason="Show the actual study result instead of generic laboratory footage.",
        confidence=0.9,
        transcript_text="A 2024 mouse study found a 37 percent difference.",
        source_beat_id="beat-1",
        preferred_media=("screenshot", "image", "video"),
    )


def assets() -> list[AssetRecord]:
    return [
        AssetRecord(
            id="generic",
            path="lab-stock.mp4",
            kind="video",
            description="generic medical science laboratory people",
            tags=["medical", "science", "laboratory"],
            roles=["illustration"],
            source_url="https://example.test/stock",
            license="licensed",
            width=1920,
            height=1080,
            fingerprint="generic-1",
        ),
        AssetRecord(
            id="study",
            path="study-result.png",
            kind="screenshot",
            description="2024 mouse study table showing 37 percent difference",
            tags=["2024", "mouse", "study", "37", "percent"],
            roles=["proof"],
            source_url="https://example.test/paper",
            license="fair-use excerpt",
            width=1800,
            height=2400,
            fingerprint="study-1",
            verified=True,
        ),
        AssetRecord(
            id="unlicensed",
            path="study-copy.png",
            kind="screenshot",
            description="2024 mouse study 37 percent",
            tags=["study", "mouse"],
            roles=["proof"],
            width=1800,
            height=2400,
            fingerprint="copy-1",
        ),
    ]


def test_ranker_prefers_specific_provenanced_proof_over_generic_stock() -> None:
    matches = rank_assets(cue(), assets(), minimum_score=0.1)
    assert matches[0].asset.id == "study"
    assert all(item.asset.id != "unlicensed" for item in matches)
    assert matches[0].breakdown["lexical"] > matches[-1].breakdown["lexical"]


def test_duplicate_fingerprint_is_heavily_penalized() -> None:
    first = rank_assets(cue(), assets(), minimum_score=0.1)
    used = {first[0].asset.fingerprint}
    second = rank_assets(cue(), assets(), used_fingerprints=used, minimum_score=0.1)
    assert not second or second[0].asset.id != first[0].asset.id


def test_resolver_builds_provenanced_proof_overlay_and_still_motion() -> None:
    overlays, decisions = resolve_broll_cues([cue()], AssetCatalog(assets()), minimum_score=0.5, plan_duration=10, coverage_cap=0.4)
    assert len(overlays) == 1
    assert overlays[0].kind is OverlayKind.PROOF
    assert overlays[0].semantic_reason
    assert overlays[0].source_url
    assert overlays[0].license
    assert overlays[0].motion.kind is MotionKind.KEN_BURNS
    assert decisions[0]["status"] == "resolved"
