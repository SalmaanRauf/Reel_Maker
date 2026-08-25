from __future__ import annotations

import json

import pytest

from podcast_studio.agent import AgentResult
from podcast_studio.exceptions import ValidationError
from podcast_studio.script_writer import save_script, write_script


def _source(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start": 0,
                        "end": 20,
                        "text": "The result may help some people, but it does not apply to everyone.",
                    }
                ]
            }
        )
    )
    return path


def test_writes_camera_ready_script_and_text_sidecar(monkeypatch, tmp_path):
    script = (
        "The result may help some people, but it does not apply to everyone. "
        "That distinction matters because a useful finding is not the same as a universal rule. "
        "Start by checking who was studied, what was measured, and whether your situation matches."
    )
    payload = {
        "title": "A Useful Result Is Not A Universal Rule",
        "hook": "The result may help some people, but it does not apply to everyone.",
        "beats": [
            {"label": "Hook", "text": "The result may help some people, but it does not apply to everyone.", "visual_cue": "Hold on speaker"},
            {"label": "Mechanism", "text": "That distinction matters because a useful finding is not the same as a universal rule.", "visual_cue": "Show study population"},
            {"label": "Payoff", "text": "Start by checking who was studied, what was measured, and whether your situation matches.", "visual_cue": "Checklist"},
        ],
        "full_script": script,
        "integrity_notes": ["Preserve may and does not apply to everyone."],
    }
    monkeypatch.setattr(
        "podcast_studio.script_writer.run_subscription_agent",
        lambda *args, **kwargs: AgentResult("claude", json.dumps(payload), payload, ["claude"], True, 1),
    )
    package = write_script(
        "Explain why one result is not universal.",
        provider="claude",
        project_root=tmp_path,
        target_seconds=30,
        source_transcript=_source(tmp_path),
    )
    output = save_script(package, tmp_path / "script.json")
    assert output.is_file()
    assert output.with_suffix(".txt").read_text().strip() == script
    assert package.integrity_notes


def test_rejects_numbers_not_in_source(monkeypatch, tmp_path):
    payload = {
        "title": "The 99 Percent Result",
        "hook": "This works 99 percent of the time.",
        "beats": [
            {"label": "Hook", "text": "This works 99 percent of the time.", "visual_cue": "Number"},
            {"label": "Payoff", "text": "That is the takeaway.", "visual_cue": "Hold"},
        ],
        "full_script": "This works 99 percent of the time. That is the takeaway.",
        "integrity_notes": [],
    }
    monkeypatch.setattr(
        "podcast_studio.script_writer.run_subscription_agent",
        lambda *args, **kwargs: AgentResult("claude", json.dumps(payload), payload, ["claude"], True, 1),
    )
    with pytest.raises(ValidationError):
        write_script(
            "Explain the result.",
            provider="claude",
            project_root=tmp_path,
            target_seconds=20,
            source_transcript=_source(tmp_path),
        )
