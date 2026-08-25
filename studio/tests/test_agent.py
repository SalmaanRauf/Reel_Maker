from __future__ import annotations

import os

import pytest

from podcast_studio.agent import extract_json, subscription_environment, validate_json_shape
from podcast_studio.exceptions import ValidationError


def test_subscription_environment_strips_metered_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "paid")
    monkeypatch.setenv("OPENAI_API_KEY", "paid")
    monkeypatch.setenv("SAFE_VALUE", "keep")
    environment = subscription_environment()
    assert "ANTHROPIC_API_KEY" not in environment
    assert "OPENAI_API_KEY" not in environment
    assert environment["SAFE_VALUE"] == "keep"
    assert environment["PODCAST_STUDIO_SUBSCRIPTION_ONLY"] == "1"


def test_extract_json_accepts_json_eventual_output():
    assert extract_json('Editorial notes\n```json\n{"clips":[{"id":"one"}]}\n```') == {
        "clips": [{"id": "one"}]
    }


def test_shape_validation_rejects_unknown_keys():
    schema = {
        "type": "object",
        "required": ["title"],
        "additionalProperties": False,
        "properties": {"title": {"type": "string"}},
    }
    validate_json_shape({"title": "Valid"}, schema)
    with pytest.raises(ValidationError):
        validate_json_shape({"title": "Valid", "invented": True}, schema)
