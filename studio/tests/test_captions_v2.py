from podcast_studio.captions import (
    OccupiedRegion,
    caption_metrics,
    chunk_words,
    occupied_regions_for_plan,
    to_ass,
    to_ass_for_plan,
)
from podcast_studio.models import (
    CaptionAnimation,
    CaptionStyle,
    EditPlan,
    EditSegment,
    EvidenceCard,
    EvidenceKind,
    TextOverlay,
    TextRole,
    Transcript,
    Transition,
    TransitionKind,
    Word,
)


def words() -> list[Word]:
    return [
        Word("Most", 0.0, 0.28),
        Word("people", 0.29, 0.64),
        Word("miss", 0.65, 0.86),
        Word("this.", 0.87, 1.2),
        Word("The", 1.55, 1.75),
        Word("study", 1.76, 2.08),
        Word("found", 2.09, 2.37),
        Word("37", 2.38, 2.61),
        Word("percent.", 2.62, 3.1),
    ]


def test_responsive_caption_cues_obey_reading_and_layout_limits() -> None:
    style = CaptionStyle(max_words=4, max_lines=2, maximum_chars_per_second=22)
    cues = chunk_words(words(), style, width=1080, height=1920)
    assert cues
    assert all(len(cue.words) <= 4 for cue in cues)
    assert all(len(cue.lines) <= 2 for cue in cues)
    assert all(style.min_font_size <= cue.font_size <= style.max_font_size for cue in cues)
    metrics = caption_metrics(cues)
    assert metrics["maximum_words"] <= 4
    assert metrics["maximum_lines"] <= 2


def test_caption_lane_moves_away_from_proof_card() -> None:
    style = CaptionStyle(auto_move=True)
    occupied = [OccupiedRegion(0, 2, 0.68, 0.92, priority=100, label="proof")]
    cues = chunk_words(words()[:4], style, width=1080, height=1920, occupied=occupied)
    assert cues[0].lane_y < 0.68


def test_ass_contains_individual_active_word_events_and_animation() -> None:
    style = CaptionStyle(
        max_words=4,
        animation=CaptionAnimation.WORD_POP,
        karaoke=True,
        emphasis_words=["37"],
    )
    ass = to_ass(Transcript(asset_id="a", words=words()), style=style)
    assert "Style: Active" in ass
    assert "Dialogue: 2" in ass
    assert "\\kf" in ass
    assert "\\t(" in ass
    assert "37" in ass


def test_plan_caption_remap_accounts_for_transition_overlap_and_collisions() -> None:
    transcript = Transcript(asset_id="a", words=words())
    plan = EditPlan(
        id="p",
        title="caption remap",
        segments=[
            EditSegment(
                source_id="a",
                source_start=0,
                source_end=1.2,
                reason="opening",
                transition_to_next=Transition(TransitionKind.DISSOLVE, 0.12, reason="section bridge"),
            ),
            EditSegment(source_id="a", source_start=1.55, source_end=3.1, reason="proof"),
        ],
        text_overlays=[TextOverlay(0, 1, "Most people miss this", role=TextRole.HEADLINE)],
        evidence_cards=[EvidenceCard(1.08, 2.1, "Study result", kind=EvidenceKind.SOURCE)],
    )
    regions = occupied_regions_for_plan(plan)
    assert len(regions) == 2
    ass = to_ass_for_plan(transcript, plan)
    assert "Most" in ass
    assert "37" in ass
    assert "0:00:01.08" in ass or "0:00:01.09" in ass
