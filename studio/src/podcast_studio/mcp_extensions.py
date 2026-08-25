from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .interchange import export_edl, export_fcpxml, export_otio
from .providers import run_provider, write_consent
from .publish import build_package, save_package
from .review import build_manifest
from .style_analysis import analyze_reference_video, fingerprint_plan, save_comparison
from .util import dump_json


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
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


EXTRA_TOOLS = [
    _tool(
        "publish_package",
        "Create source-faithful titles, descriptions, platform copy, chapters, hashtags, and thumbnail concepts.",
        {
            "transcript": {"type": "string"},
            "output": {"type": "string"},
            "start": {"type": "number", "minimum": 0},
            "end": {"type": "number", "minimum": 0},
            "title_hint": {"type": "string"},
            "agent": {"type": "string", "enum": ["claude", "codex"]},
            "project_root": {"type": "string"},
            "brand_voice": {"type": "string"},
        },
        ["transcript", "output"],
    ),
    _tool(
        "style_fingerprint_plan",
        "Measure the coordinated edit dynamics encoded in a candidate plan.",
        {"plan": {"type": "string"}, "output": {"type": "string"}},
        ["plan", "output"],
    ),
    _tool(
        "style_analyze_reference",
        "Measure hard-cut cadence in a rendered reference and optionally combine human event annotations for zoom/text/B-roll/proof/caption/SFX dynamics.",
        {
            "video": {"type": "string"},
            "output": {"type": "string"},
            "annotations": {"type": "string"},
            "scene_threshold": {"type": "number", "minimum": 0.01, "maximum": 0.99},
        },
        ["video", "output"],
    ),
    _tool(
        "style_compare",
        "Compare a candidate edit plan with a saved reference fingerprint and return measurable style gaps.",
        {"reference": {"type": "string"}, "plan": {"type": "string"}, "output": {"type": "string"}},
        ["reference", "plan", "output"],
    ),
    _tool(
        "export_timeline",
        "Export a plan for finishing in a professional NLE as EDL, FCPXML, or OpenTimelineIO.",
        {
            "plan": {"type": "string"},
            "output": {"type": "string"},
            "format": {"type": "string", "enum": ["edl", "fcpxml", "otio"]},
            "fps": {"type": "number", "minimum": 1, "maximum": 240},
            "width": {"type": "integer", "minimum": 240},
            "height": {"type": "integer", "minimum": 240},
            "title": {"type": "string"},
        },
        ["plan", "output", "format"],
    ),
    _tool(
        "review_manifest",
        "Read the local review queue, QC summaries, and latest human approval decisions.",
        {"root": {"type": "string"}},
        ["root"],
    ),
    _tool(
        "provider_consent",
        "Write a scoped consent receipt before voice-clone, identity-manipulation, or digital-replica providers can run.",
        {
            "directory": {"type": "string"},
            "subject": {"type": "string"},
            "scope": {"type": "string", "enum": ["voice-clone", "identity-manipulation", "digital-replica"]},
            "evidence": {"type": "string"},
            "expires_at": {"type": "string"},
        },
        ["directory", "subject", "scope", "evidence"],
    ),
    _tool(
        "provider_run",
        "Run an enabled, executable-allowlisted specialty provider and record output provenance.",
        {
            "config": {"type": "string"},
            "provider": {"type": "string"},
            "substitutions": {"type": "object"},
            "receipts_dir": {"type": "string"},
            "consent": {"type": "string"},
        },
        ["config", "provider", "substitutions", "receipts_dir"],
    ),
]

EXTRA_TOOL_NAMES = {item["name"] for item in EXTRA_TOOLS}


def call_extra_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "publish_package":
        package = build_package(
            arguments["transcript"],
            start=float(arguments.get("start", 0.0)),
            end=float(arguments["end"]) if arguments.get("end") is not None else None,
            title_hint=arguments.get("title_hint"),
            agent=arguments.get("agent"),
            project_root=arguments.get("project_root"),
            brand_voice=arguments.get("brand_voice", "clear, precise, credible, direct"),
        )
        output = save_package(package, arguments["output"])
        return {"output": str(output.resolve()), "package": package.to_dict()}
    if name == "style_fingerprint_plan":
        fingerprint = fingerprint_plan(arguments["plan"])
        output = dump_json(fingerprint.to_dict(), arguments["output"])
        return {"output": str(output.resolve()), "fingerprint": fingerprint.to_dict()}
    if name == "style_analyze_reference":
        fingerprint = analyze_reference_video(
            arguments["video"],
            arguments["output"],
            scene_threshold=float(arguments.get("scene_threshold", 0.32)),
            annotations=arguments.get("annotations"),
        )
        return {"output": str(Path(arguments["output"]).resolve()), "fingerprint": fingerprint.to_dict()}
    if name == "style_compare":
        result = save_comparison(arguments["reference"], arguments["plan"], arguments["output"])
        return {"output": str(Path(arguments["output"]).resolve()), "comparison": result}
    if name == "export_timeline":
        export_format = arguments["format"]
        fps = float(arguments.get("fps", 30.0))
        if export_format == "edl":
            output = export_edl(arguments["plan"], arguments["output"], fps=round(fps), title=arguments.get("title"))
        elif export_format == "fcpxml":
            output = export_fcpxml(
                arguments["plan"],
                arguments["output"],
                fps=round(fps),
                width=int(arguments.get("width", 1080)),
                height=int(arguments.get("height", 1920)),
                title=arguments.get("title"),
            )
        else:
            output = export_otio(arguments["plan"], arguments["output"], fps=fps)
        return {"output": str(output.resolve()), "format": export_format}
    if name == "review_manifest":
        return build_manifest(arguments["root"])
    if name == "provider_consent":
        output = write_consent(
            arguments["directory"],
            subject=arguments["subject"],
            scope=arguments["scope"],
            evidence=arguments["evidence"],
            expires_at=arguments.get("expires_at"),
        )
        return {"consent": str(output.resolve())}
    if name == "provider_run":
        result = run_provider(
            arguments["config"],
            arguments["provider"],
            arguments["substitutions"],
            receipts_dir=arguments["receipts_dir"],
            consent_path=arguments.get("consent"),
        )
        return result.to_dict()
    raise KeyError(name)
