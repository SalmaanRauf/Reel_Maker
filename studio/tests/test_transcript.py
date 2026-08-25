from __future__ import annotations

import json

from podcast_studio.transcript import (
    approximate_words,
    load_transcript,
    save_transcript,
    to_srt,
    to_vtt,
    transcript_from_json,
    transcript_from_subtitles,
)


def test_imports_srt_and_generates_word_timestamps(tmp_path):
    transcript = transcript_from_subtitles(
        """1
00:00:01,000 --> 00:00:03,400
HOST: This is a real sentence.

2
00:00:04,000 --> 00:00:06,000
It has a second thought.
""",
        asset_id="camera-a",
    )
    words = transcript.all_words()
    assert transcript.asset_id == "camera-a"
    assert len(transcript.segments) == 2
    assert len(words) == 11
    assert words[0].start == 1.0
    assert words[-1].end == 6.0
    assert transcript.segments[0].speaker == "HOST"


def test_round_trips_json_srt_and_vtt(tmp_path):
    payload = {
        "asset_id": "source-1",
        "language": "en",
        "segments": [
            {
                "start": 0.5,
                "end": 2.0,
                "text": "May help some people.",
                "words": [
                    {"word": "May", "start": 0.5, "end": 0.8},
                    {"word": "help", "start": 0.81, "end": 1.1},
                    {"word": "some", "start": 1.11, "end": 1.45},
                    {"word": "people.", "start": 1.46, "end": 2.0},
                ],
            }
        ],
    }
    transcript = transcript_from_json(payload)
    json_path = save_transcript(transcript, tmp_path / "transcript.json")
    srt_path = save_transcript(transcript, tmp_path / "transcript.srt")
    vtt_path = save_transcript(transcript, tmp_path / "transcript.vtt")

    assert load_transcript(json_path).all_words()[0].text == "May"
    assert "00:00:00,500 --> 00:00:02,000" in srt_path.read_text()
    assert "00:00:00.500 --> 00:00:02.000" in vtt_path.read_text()
    assert "May help some people." in to_srt(transcript)
    assert to_vtt(transcript).startswith("WEBVTT")


def test_approximate_words_respects_exact_bounds():
    words = approximate_words("one unusuallylong token", 4.0, 7.0)
    assert words[0].start == 4.0
    assert words[-1].end == 7.0
    assert all(left.end <= right.start + 1e-9 for left, right in zip(words, words[1:]))
