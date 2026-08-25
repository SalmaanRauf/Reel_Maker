from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from .bridge import render_plan_file, run_quality_control
from .direct_bridge import direct_clip
from .doctor import doctor_exit_code, format_doctor, run_doctor
from .editorial import ClipCandidate, discover_candidates, select_with_agent
from .exceptions import PodcastStudioError, ValidationError
from .reframe import analyze_and_write
from .sync import synchronize_many
from .transcription import transcribe_media
from .transcript import load_transcript
from .util import dump_json, slugify
from .workspace import add_assets, initialize_workspace, project_summary, register_artifact, resolve_asset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="podcast-studio",
        description="Agent-native, local-first podcast editing for Claude Code and Codex subscriptions.",
    )
    parser.add_argument("--version", action="version", version="podcast-studio 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a reproducible episode workspace")
    init.add_argument("root")
    init.add_argument("--name")
    init.add_argument("--force", action="store_true")

    add = subparsers.add_parser("add", help="Register source media")
    add.add_argument("root")
    add.add_argument("sources", nargs="+")
    add.add_argument("--role", default="camera", choices=("camera", "audio", "broll", "music", "sfx", "graphic", "reference"))
    add.add_argument("--mode", default="reference", choices=("reference", "copy", "symlink", "hardlink"))
    add.add_argument("--label")

    summary = subparsers.add_parser("summary", help="Summarize a workspace")
    summary.add_argument("root")

    doctor = subparsers.add_parser("doctor", help="Validate local tools, models, and subscription CLIs")
    doctor.add_argument("root", nargs="?")
    doctor.add_argument("--json", action="store_true", dest="json_output")

    transcribe = subparsers.add_parser("transcribe", help="Transcribe an asset locally with word timestamps")
    transcribe.add_argument("root")
    transcribe.add_argument("asset_id")
    transcribe.add_argument("--engine", default="auto")
    transcribe.add_argument("--model", default="large-v3-turbo")
    transcribe.add_argument("--language")
    transcribe.add_argument("--output")

    discover = subparsers.add_parser("discover", help="Score standalone podcast clip candidates")
    discover.add_argument("transcript")
    discover.add_argument("--output", required=True)
    discover.add_argument("--maximum", type=int, default=80)

    select = subparsers.add_parser("select", help="Select the strongest candidates with Claude Code or Codex")
    select.add_argument("root")
    select.add_argument("transcript")
    select.add_argument("candidates")
    select.add_argument("--agent", required=True, choices=("claude", "codex"))
    select.add_argument("--count", type=int, default=10)
    select.add_argument("--brief", default="")
    select.add_argument("--output", required=True)

    sync = subparsers.add_parser("sync", help="Estimate camera/audio offsets with local cross-correlation")
    sync.add_argument("root")
    sync.add_argument("reference_asset")
    sync.add_argument("target_assets", nargs="+")
    sync.add_argument("--output")
    sync.add_argument("--maximum-offset", type=float, default=45.0)

    reframe = subparsers.add_parser("reframe", help="Build a dead-zone smoothed face-aware crop track")
    reframe.add_argument("root")
    reframe.add_argument("asset_id")
    reframe.add_argument("--output")
    reframe.add_argument("--width", type=int, default=1080)
    reframe.add_argument("--height", type=int, default=1920)
    reframe.add_argument("--interval", type=float, default=0.25)

    direct = subparsers.add_parser("direct", help="Compile a selected transcript range into an edit plan")
    direct.add_argument("transcript")
    direct.add_argument("source_asset_id")
    direct.add_argument("start", type=float)
    direct.add_argument("end", type=float)
    direct.add_argument("--output", required=True)
    direct.add_argument("--title", default="Podcast clip")
    direct.add_argument("--style", default="authority")
    direct.add_argument("--aspect-ratio", default="9:16")
    direct.add_argument("--brief", default="")

    render = subparsers.add_parser("render", help="Render a validated non-destructive edit plan")
    render.add_argument("root")
    render.add_argument("plan")
    render.add_argument("output")
    render.add_argument("--preview", action="store_true")

    qc = subparsers.add_parser("qc", help="Run technical and aesthetic quality control")
    qc.add_argument("media")
    qc.add_argument("--report")

    install = subparsers.add_parser("install-agent", help="Install project-scoped Claude/Codex skills and MCP config")
    install.add_argument("root")
    install.add_argument("--client", choices=("claude", "codex", "both"), default="both")

    auto = subparsers.add_parser("auto", help="Run transcript → discovery → selection → direction → render")
    auto.add_argument("root")
    auto.add_argument("asset_id")
    auto.add_argument("--agent", choices=("claude", "codex"))
    auto.add_argument("--count", type=int, default=8)
    auto.add_argument("--brief", default="")
    auto.add_argument("--style", default="authority")
    auto.add_argument("--engine", default="auto")
    auto.add_argument("--model", default="large-v3-turbo")
    auto.add_argument("--transcript")
    auto.add_argument("--preview", action="store_true")
    auto.add_argument("--no-render", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result, exit_code = dispatch(args)
    except PodcastStudioError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        return 130
    if isinstance(result, str):
        print(result)
    elif result is not None:
        print(json.dumps(result, indent=2, default=str))
    return exit_code


def dispatch(args: argparse.Namespace) -> tuple[Any, int]:
    if args.command == "init":
        return initialize_workspace(args.root, name=args.name, force=args.force), 0
    if args.command == "add":
        return {"assets": add_assets(args.root, args.sources, role=args.role, mode=args.mode, label=args.label)}, 0
    if args.command == "summary":
        return project_summary(args.root), 0
    if args.command == "doctor":
        checks = run_doctor(project=args.root)
        return format_doctor(checks, json_output=args.json_output), doctor_exit_code(checks)
    if args.command == "transcribe":
        asset, source = resolve_asset(args.root, args.asset_id)
        output = Path(args.output) if args.output else Path(args.root) / "analysis" / "transcripts" / str(asset["id"])
        transcript = transcribe_media(
            source,
            output,
            asset_id=str(asset["id"]),
            engine=args.engine,
            model=args.model,
            language=args.language,
        )
        artifact = register_artifact(
            args.root,
            "transcript",
            {
                "asset_id": asset["id"],
                "path": _relative(args.root, output / "transcript.json"),
                "engine": transcript.engine,
                "language": transcript.language,
            },
        )
        return artifact, 0
    if args.command == "discover":
        transcript = load_transcript(args.transcript)
        candidates = discover_candidates(transcript, maximum_candidates=args.maximum)
        dump_json({"transcript": str(Path(args.transcript).resolve()), "candidates": [item.to_dict() for item in candidates]}, args.output)
        return {"output": str(Path(args.output).resolve()), "candidate_count": len(candidates)}, 0
    if args.command == "select":
        candidates = _load_candidates(args.candidates)
        selected = select_with_agent(
            args.transcript,
            candidates,
            provider=args.agent,
            project_root=args.root,
            count=args.count,
            brief=args.brief,
        )
        dump_json({"agent": args.agent, "clips": selected}, args.output)
        return {"output": str(Path(args.output).resolve()), "selected_count": len(selected), "clips": selected}, 0
    if args.command == "sync":
        _, reference = resolve_asset(args.root, args.reference_asset)
        target_paths = [resolve_asset(args.root, item)[1] for item in args.target_assets]
        output = Path(args.output) if args.output else Path(args.root) / "analysis" / "sync" / f"{args.reference_asset}.json"
        results = synchronize_many(reference, target_paths, output, maximum_offset_seconds=args.maximum_offset)
        return {"output": str(output.resolve()), "results": [item.to_dict() for item in results]}, 0
    if args.command == "reframe":
        asset, source = resolve_asset(args.root, args.asset_id)
        output = Path(args.output) if args.output else Path(args.root) / "analysis" / "reframe" / f"{asset['id']}.json"
        plan = analyze_and_write(source, output, output_width=args.width, output_height=args.height, every_seconds=args.interval)
        return {"output": str(output.resolve()), "plan": plan.to_dict()}, 0
    if args.command == "direct":
        payload = direct_clip(
            transcript_path=args.transcript,
            source_asset_id=args.source_asset_id,
            start=args.start,
            end=args.end,
            output_path=args.output,
            title=args.title,
            style=args.style,
            aspect_ratio=args.aspect_ratio,
            brief=args.brief,
        )
        return {"output": str(Path(args.output).resolve()), "plan": payload}, 0
    if args.command == "render":
        payload = render_plan_file(args.root, args.plan, args.output, preview=args.preview)
        register_artifact(args.root, "render", {"plan": _relative(args.root, args.plan), "path": _relative(args.root, args.output), "preview": args.preview})
        return payload, 0
    if args.command == "qc":
        return run_quality_control(args.media, report_path=args.report), 0
    if args.command == "install-agent":
        return install_agent_files(args.root, client=args.client), 0
    if args.command == "auto":
        return _auto(args), 0
    raise ValidationError(f"Unknown command: {args.command}")


def install_agent_files(root: str | Path, *, client: str = "both") -> dict[str, Any]:
    project = Path(root).expanduser().resolve()
    initialize_workspace(project)
    template = Path(__file__).parent / "templates" / "podcast-editor" / "SKILL.md"
    if not template.is_file():
        raise ValidationError(f"Packaged podcast editor skill is missing: {template}")
    installed: list[str] = []
    if client in {"claude", "both"}:
        destination = project / ".claude" / "skills" / "podcast-editor" / "SKILL.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, destination)
        installed.append(str(destination))
        mcp_path = project / ".mcp.json"
        payload: dict[str, Any] = {}
        if mcp_path.exists():
            payload = json.loads(mcp_path.read_text(encoding="utf-8"))
        payload.setdefault("mcpServers", {})["podcast-studio"] = {
            "command": sys.executable,
            "args": ["-m", "podcast_studio.mcp_server"],
            "env": {"PODCAST_STUDIO_PROJECT": str(project)},
        }
        dump_json(payload, mcp_path)
        installed.append(str(mcp_path))
    if client in {"codex", "both"}:
        destination = project / ".agents" / "skills" / "podcast-editor" / "SKILL.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, destination)
        installed.append(str(destination))
        codex_config = project / ".codex" / "config.toml"
        codex_config.parent.mkdir(parents=True, exist_ok=True)
        block = (
            "[mcp_servers.podcast-studio]\n"
            f'command = "{_toml_escape(sys.executable)}"\n'
            f'args = ["-m", "podcast_studio.mcp_server"]\n'
            f'env = {{ PODCAST_STUDIO_PROJECT = "{_toml_escape(str(project))}" }}\n'
        )
        existing = codex_config.read_text(encoding="utf-8") if codex_config.exists() else ""
        if "[mcp_servers.podcast-studio]" not in existing:
            codex_config.write_text(existing.rstrip() + ("\n\n" if existing.strip() else "") + block, encoding="utf-8")
        installed.append(str(codex_config))
        agents = project / "AGENTS.md"
        marker = "## Podcast Studio"
        existing_agents = agents.read_text(encoding="utf-8") if agents.exists() else ""
        if marker not in existing_agents:
            agents.write_text(
                existing_agents.rstrip()
                + ("\n\n" if existing_agents.strip() else "")
                + marker
                + "\nUse the podcast-editor skill and podcast-studio MCP tools for every media edit. Never bypass QC or source provenance.\n",
                encoding="utf-8",
            )
        installed.append(str(agents))
    return {"project": str(project), "client": client, "installed": installed}


def _auto(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.root).expanduser().resolve()
    asset, source = resolve_asset(workspace, args.asset_id)
    if args.transcript:
        transcript_path = Path(args.transcript).expanduser().resolve()
    else:
        transcript_dir = workspace / "analysis" / "transcripts" / str(asset["id"])
        transcribe_media(source, transcript_dir, asset_id=str(asset["id"]), engine=args.engine, model=args.model)
        transcript_path = transcript_dir / "transcript.json"
    transcript = load_transcript(transcript_path, asset_id=str(asset["id"]))
    candidates = discover_candidates(transcript)
    candidate_path = workspace / "analysis" / f"{asset['id']}.candidates.json"
    dump_json({"candidates": [item.to_dict() for item in candidates]}, candidate_path)
    if args.agent:
        selections = select_with_agent(
            transcript_path,
            candidates,
            provider=args.agent,
            project_root=workspace,
            count=args.count,
            brief=args.brief,
        )
    else:
        selections = [
            {
                "id": item.id,
                "candidate_id": item.id,
                "title": f"Clip {index + 1}",
                "hook": compact_hook(item.text),
                "editorial_reason": "Highest deterministic standalone score",
                "confidence": item.score / 100.0,
                "risk": ", ".join(item.flags),
                "start": item.start,
                "end": item.end,
                "duration": item.duration,
                "source_text": item.text,
                "deterministic_score": item.score,
            }
            for index, item in enumerate(candidates[: args.count])
        ]
    slate_path = workspace / "plans" / f"{asset['id']}.slate.json"
    dump_json({"asset_id": asset["id"], "clips": selections}, slate_path)
    results: list[dict[str, Any]] = []
    for index, selection in enumerate(selections):
        stem = f"{index + 1:02d}-{slugify(selection['title'])[:52]}"
        plan_path = workspace / "plans" / f"{stem}.json"
        plan = direct_clip(
            transcript_path=transcript_path,
            source_asset_id=str(asset["id"]),
            start=float(selection["start"]),
            end=float(selection["end"]),
            output_path=plan_path,
            title=str(selection["title"]),
            style=args.style,
            aspect_ratio="9:16",
            brief=args.brief,
        )
        item: dict[str, Any] = {"selection": selection, "plan": str(plan_path), "plan_id": plan.get("id")}
        if not args.no_render:
            destination = workspace / "renders" / ("previews" if args.preview else "final") / f"{stem}.mp4"
            item["render"] = render_plan_file(workspace, plan_path, destination, preview=args.preview)
        results.append(item)
    return {
        "workspace": str(workspace),
        "asset_id": asset["id"],
        "transcript": str(transcript_path),
        "candidates": str(candidate_path),
        "slate": str(slate_path),
        "clips": results,
    }


def _load_candidates(path: str | Path) -> list[ClipCandidate]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("candidates") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValidationError("Candidate file must contain a `candidates` array")
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidates.append(
            ClipCandidate(
                id=str(row["id"]),
                start=float(row["start"]),
                end=float(row["end"]),
                text=str(row["text"]),
                score=float(row.get("score", 0.0)),
                components=dict(row.get("components", {})),
                flags=list(row.get("flags", [])),
                speaker=row.get("speaker"),
            )
        )
    return candidates


def compact_hook(text: str, maximum_words: int = 14) -> str:
    words = text.split()
    return " ".join(words[:maximum_words]) + ("…" if len(words) > maximum_words else "")


def _relative(root: str | Path, value: str | Path) -> str:
    root_path = Path(root).expanduser().resolve()
    path = Path(value).expanduser().resolve()
    try:
        return str(path.relative_to(root_path))
    except ValueError:
        return str(path)


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


if __name__ == "__main__":
    raise SystemExit(main())
