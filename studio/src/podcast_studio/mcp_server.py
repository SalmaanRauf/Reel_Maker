from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from .bridge import load_edit_plan, render_plan_file, run_quality_control
from .cli import install_agent_files
from .direct_bridge import direct_clip
from .doctor import format_doctor, run_doctor
from .editorial import discover_candidates
from .exceptions import PodcastStudioError, ValidationError
from .reframe import analyze_and_write
from .sync import synchronize_many
from .transcription import transcribe_media
from .transcript import load_transcript
from .util import dump_json
from .workspace import add_assets, initialize_workspace, project_summary, resolve_asset

SERVER_NAME = "podcast-studio"
SERVER_VERSION = "0.1.0"


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


TOOLS = [
    _tool(
        "workspace_init",
        "Create the canonical local episode workspace. Safe to call repeatedly.",
        {"root": {"type": "string"}, "name": {"type": "string"}},
        ["root"],
    ),
    _tool(
        "workspace_summary",
        "Read project assets, artifacts, settings, and offline-media state.",
        {"root": {"type": "string"}},
        ["root"],
    ),
    _tool(
        "media_add",
        "Register source media without modifying it. Reference mode is safest and fastest.",
        {
            "root": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "role": {"type": "string", "enum": ["camera", "audio", "broll", "music", "sfx", "graphic", "reference"]},
            "mode": {"type": "string", "enum": ["reference", "copy", "symlink", "hardlink"]},
            "label": {"type": "string"},
        },
        ["root", "sources"],
    ),
    _tool(
        "transcribe_local",
        "Transcribe one registered asset locally with word timestamps; no transcription API is used.",
        {
            "root": {"type": "string"},
            "asset_id": {"type": "string"},
            "engine": {"type": "string"},
            "model": {"type": "string"},
            "language": {"type": "string"},
        },
        ["root", "asset_id"],
    ),
    _tool(
        "discover_clips",
        "Generate an evidence-backed slate of standalone clip candidates from a transcript.",
        {
            "transcript": {"type": "string"},
            "output": {"type": "string"},
            "maximum": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        ["transcript", "output"],
    ),
    _tool(
        "direct_clip",
        "Compile an approved source range into a semantic edit plan with captions, motion, graphics, proof, B-roll cues, and audio events.",
        {
            "transcript": {"type": "string"},
            "source_asset_id": {"type": "string"},
            "start": {"type": "number", "minimum": 0},
            "end": {"type": "number", "minimum": 0},
            "output": {"type": "string"},
            "title": {"type": "string"},
            "style": {"type": "string"},
            "aspect_ratio": {"type": "string", "enum": ["9:16", "1:1", "16:9"]},
            "brief": {"type": "string"},
        },
        ["transcript", "source_asset_id", "start", "end", "output"],
    ),
    _tool(
        "plan_validate",
        "Parse and validate a non-destructive edit-plan JSON before rendering.",
        {"plan": {"type": "string"}},
        ["plan"],
    ),
    _tool(
        "render_plan",
        "Render a validated plan locally with FFmpeg. Preview uses faster settings; final uses delivery settings.",
        {
            "root": {"type": "string"},
            "plan": {"type": "string"},
            "output": {"type": "string"},
            "preview": {"type": "boolean"},
        },
        ["root", "plan", "output"],
    ),
    _tool(
        "quality_control",
        "Run technical and aesthetic QC on a rendered clip and optionally write a report.",
        {"media": {"type": "string"}, "report": {"type": "string"}},
        ["media"],
    ),
    _tool(
        "sync_assets",
        "Estimate local audio offsets for multicamera or separate-recorder sources.",
        {
            "root": {"type": "string"},
            "reference_asset": {"type": "string"},
            "target_assets": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "output": {"type": "string"},
            "maximum_offset": {"type": "number", "minimum": 0.1, "maximum": 600},
        },
        ["root", "reference_asset", "target_assets", "output"],
    ),
    _tool(
        "analyze_reframe",
        "Build a stable face-aware crop track with dead zones and eased pans for vertical output.",
        {
            "root": {"type": "string"},
            "asset_id": {"type": "string"},
            "output": {"type": "string"},
            "width": {"type": "integer", "minimum": 240},
            "height": {"type": "integer", "minimum": 240},
            "interval": {"type": "number", "minimum": 0.05, "maximum": 5},
        },
        ["root", "asset_id", "output"],
    ),
    _tool(
        "doctor",
        "Check FFmpeg, transcription engines, optional vision/sync packages, and Claude/Codex subscription CLIs.",
        {"root": {"type": "string"}},
    ),
    _tool(
        "install_project_agent",
        "Install project-scoped podcast-editor skills and MCP configuration without touching global configuration.",
        {
            "root": {"type": "string"},
            "client": {"type": "string", "enum": ["claude", "codex", "both"]},
        },
        ["root"],
    ),
    _tool(
        "read_json",
        "Read a project JSON artifact. Use this instead of guessing the plan or analysis schema.",
        {"path": {"type": "string"}},
        ["path"],
    ),
    _tool(
        "write_json",
        "Write a JSON project artifact atomically. Never use this to overwrite source media.",
        {"path": {"type": "string"}, "payload": {}},
        ["path", "payload"],
    ),
]


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    project_default = os.environ.get("PODCAST_STUDIO_PROJECT")
    if name == "workspace_init":
        return initialize_workspace(arguments["root"], name=arguments.get("name"))
    if name == "workspace_summary":
        return project_summary(arguments["root"])
    if name == "media_add":
        return {
            "assets": add_assets(
                arguments["root"],
                arguments["sources"],
                role=arguments.get("role", "camera"),
                mode=arguments.get("mode", "reference"),
                label=arguments.get("label"),
            )
        }
    if name == "transcribe_local":
        root = Path(arguments["root"]).expanduser().resolve()
        asset, source = resolve_asset(root, arguments["asset_id"])
        output = root / "analysis" / "transcripts" / str(asset["id"])
        transcript = transcribe_media(
            source,
            output,
            asset_id=str(asset["id"]),
            engine=arguments.get("engine", "auto"),
            model=arguments.get("model", "large-v3-turbo"),
            language=arguments.get("language"),
        )
        return {"transcript": str(output / "transcript.json"), "engine": transcript.engine, "language": transcript.language}
    if name == "discover_clips":
        transcript = load_transcript(arguments["transcript"])
        candidates = discover_candidates(transcript, maximum_candidates=int(arguments.get("maximum", 80)))
        payload = {"candidates": [item.to_dict() for item in candidates]}
        dump_json(payload, arguments["output"])
        return {"output": str(Path(arguments["output"]).resolve()), "candidate_count": len(candidates)}
    if name == "direct_clip":
        if float(arguments["end"]) <= float(arguments["start"]):
            raise ValidationError("Clip end must be after clip start")
        return direct_clip(
            transcript_path=arguments["transcript"],
            source_asset_id=arguments["source_asset_id"],
            start=float(arguments["start"]),
            end=float(arguments["end"]),
            output_path=arguments["output"],
            title=arguments.get("title", "Podcast clip"),
            style=arguments.get("style", "authority"),
            aspect_ratio=arguments.get("aspect_ratio", "9:16"),
            brief=arguments.get("brief", ""),
        )
    if name == "plan_validate":
        plan = load_edit_plan(arguments["plan"])
        for method_name in ("to_dict", "model_dump", "dict"):
            method = getattr(plan, method_name, None)
            if callable(method):
                plan = method()
                break
        return {"valid": True, "plan": plan}
    if name == "render_plan":
        return render_plan_file(arguments["root"], arguments["plan"], arguments["output"], preview=bool(arguments.get("preview", False)))
    if name == "quality_control":
        return run_quality_control(arguments["media"], report_path=arguments.get("report"))
    if name == "sync_assets":
        _, reference = resolve_asset(arguments["root"], arguments["reference_asset"])
        targets = [resolve_asset(arguments["root"], item)[1] for item in arguments["target_assets"]]
        results = synchronize_many(
            reference,
            targets,
            arguments["output"],
            maximum_offset_seconds=float(arguments.get("maximum_offset", 45.0)),
        )
        return {"output": str(Path(arguments["output"]).resolve()), "results": [item.to_dict() for item in results]}
    if name == "analyze_reframe":
        _, source = resolve_asset(arguments["root"], arguments["asset_id"])
        plan = analyze_and_write(
            source,
            arguments["output"],
            output_width=int(arguments.get("width", 1080)),
            output_height=int(arguments.get("height", 1920)),
            every_seconds=float(arguments.get("interval", 0.25)),
        )
        return {"output": str(Path(arguments["output"]).resolve()), "plan": plan.to_dict()}
    if name == "doctor":
        checks = run_doctor(project=arguments.get("root") or project_default)
        return {"report": format_doctor(checks), "checks": [item.to_dict() for item in checks]}
    if name == "install_project_agent":
        return install_agent_files(arguments["root"], client=arguments.get("client", "both"))
    if name == "read_json":
        path = Path(arguments["path"]).expanduser().resolve()
        return json.loads(path.read_text(encoding="utf-8"))
    if name == "write_json":
        return {"path": str(dump_json(arguments["payload"], arguments["path"]).resolve())}
    raise ValidationError(f"Unknown MCP tool: {name}")


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "initialize":
        requested = (message.get("params") or {}).get("protocolVersion") or "2024-11-05"
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            result = call_tool(str(name), arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}], "isError": False},
            }
        except (PodcastStudioError, OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True},
            }
    if request_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            response = handle_message(message)
        except Exception as exc:  # Last-resort protocol protection; never emit logs to stdout.
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Internal error: {exc}"},
            }
            if os.environ.get("PODCAST_STUDIO_DEBUG") == "1":
                traceback.print_exc(file=sys.stderr)
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":"), default=str) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
