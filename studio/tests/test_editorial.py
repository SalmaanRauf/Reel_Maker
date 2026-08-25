from __future__ import annotations

from podcast_studio.editorial import discover_candidates, score_candidate, snap_to_words
from podcast_studio.transcript import transcript_from_json


def _sample_transcript():
    segments = []
    texts = [
        "Most people misunderstand what this number actually means.",
        "The reason is that the measurement changes with timing and context.",
        "In a randomized trial, about thirty percent of participants improved, but the result may not apply to everyone.",
        "So the practical takeaway is to verify the measurement before changing the plan.",
    ]
    cursor = 0.0
    for index, text in enumerate(texts):
        end = cursor + 18.0
        words = []
        tokens = text.split()
        duration = (end - cursor) / len(tokens)
        for word_index, token in enumerate(tokens):
            words.append({"word": token, "start": cursor + word_index * duration, "end": cursor + (word_index + 1) * duration})
        segments.append({"id": index, "start": cursor, "end": end, "text": text, "words": words})
        cursor = end
    return transcript_from_json({"asset_id": "source", "segments": segments})


def test_candidate_scoring_rewards_hook_structure_evidence_and_payoff():
    transcript = _sample_transcript()
    candidate = score_candidate(transcript.segments)
    assert candidate.duration == 72.0
    assert candidate.components["hook"] > 0.5
    assert candidate.components["structure"] == 1.0
    assert candidate.components["payoff"] > 0.5
    assert candidate.components["qualifier_integrity"] == 1.0
    assert candidate.score > 75


def test_candidate_discovery_returns_non_overlapping_high_quality_windows():
    candidates = discover_candidates(_sample_transcript(), minimum_seconds=35, maximum_seconds=100)
    assert candidates
    assert candidates[0].start == 0.0
    assert candidates[0].end == 72.0


def test_snap_to_words_never_invents_timecodes():
    transcript = _sample_transcript()
    start, end = snap_to_words(transcript, 0.2, 71.8)
    assert start == 0.0
    assert end == 72.0
