from __future__ import annotations

import json

from podcast_studio.benchmark import BenchmarkThresholds, build_blind_review_packet, run_case


def _plan(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(
            {
                "duration": 60,
                "segments": [
                    {"start": 0, "end": 20, "source": "a.mp4"},
                    {"start": 20, "end": 40, "source": "a.mp4"},
                    {"start": 40, "end": 60, "source": "a.mp4"},
                ],
                "captions": [
                    {"start": 0, "end": 3, "text": "A clean phrase"},
                    {"start": 3, "end": 6, "text": "Another clean phrase"},
                ],
                "overlays": [{"type": "text", "start": 0, "end": 4}],
                "broll": [{"type": "broll", "start": 25, "end": 30}],
            }
        )
    )
    return path


def test_plan_only_benchmark_enforces_visual_density(tmp_path):
    result = run_case(
        {"id": "clean-plan", "plan": str(_plan(tmp_path))},
        manifest_directory=tmp_path,
        default_thresholds=BenchmarkThresholds(),
    )
    assert result.passed is True
    assert any(item["name"] == "visual_concurrency" and item["passed"] for item in result.checks)
    assert any(item["name"] == "render_present" and not item["required"] for item in result.checks)


def test_blind_review_packet_is_repeatable_without_exposing_ids_in_entries(tmp_path):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    packet_one = build_blind_review_packet(
        [{"id": "human", "path": first}, {"id": "agent", "path": second}],
        tmp_path / "packet-one.json",
        seed="same-seed",
    )
    packet_two = build_blind_review_packet(
        [{"id": "human", "path": first}, {"id": "agent", "path": second}],
        tmp_path / "packet-two.json",
        seed="same-seed",
    )
    assert packet_one["entries"] == packet_two["entries"]
    assert {item["label"] for item in packet_one["entries"]} == {"Version A", "Version B"}
    assert all("private_id" not in item for item in packet_one["entries"])
    assert set(packet_one["private_answer_key"].values()) == {"human", "agent"}
