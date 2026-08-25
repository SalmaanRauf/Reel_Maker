from __future__ import annotations

from typing import Any

from . import mcp_server as base
from .mcp_extensions import EXTRA_TOOL_NAMES, EXTRA_TOOLS, call_extra_tool

if not EXTRA_TOOL_NAMES.issubset({item["name"] for item in base.TOOLS}):
    base.TOOLS.extend(EXTRA_TOOLS)

_base_call_tool = base.call_tool


def _combined_call_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name in EXTRA_TOOL_NAMES:
        return call_extra_tool(name, arguments)
    return _base_call_tool(name, arguments)


base.call_tool = _combined_call_tool
TOOLS = base.TOOLS
handle_message = base.handle_message


def main() -> None:
    base.main()


if __name__ == "__main__":
    main()
