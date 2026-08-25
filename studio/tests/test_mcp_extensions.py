from __future__ import annotations

from podcast_studio.mcp_server_full import TOOLS, handle_message


def test_extended_mcp_surface_includes_style_publish_review_and_finishing():
    response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    names = {item["name"] for item in response["result"]["tools"]}
    assert len(TOOLS) >= 23
    assert {
        "publish_package",
        "style_fingerprint_plan",
        "style_analyze_reference",
        "style_compare",
        "export_timeline",
        "review_manifest",
        "provider_consent",
        "provider_run",
    }.issubset(names)
