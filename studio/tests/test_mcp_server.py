from __future__ import annotations

from podcast_studio.mcp_server import TOOLS, handle_message


def test_mcp_initialization_echoes_protocol_and_server_info():
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert response["result"]["serverInfo"]["name"] == "podcast-studio"


def test_mcp_lists_narrow_documented_tools():
    response = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = {item["name"] for item in response["result"]["tools"]}
    assert len(TOOLS) >= 15
    assert {
        "workspace_init",
        "transcribe_local",
        "discover_clips",
        "direct_clip",
        "render_plan",
        "quality_control",
        "sync_assets",
        "analyze_reframe",
    }.issubset(names)


def test_mcp_unknown_method_returns_protocol_error():
    response = handle_message({"jsonrpc": "2.0", "id": 3, "method": "unknown/method"})
    assert response["error"]["code"] == -32601
