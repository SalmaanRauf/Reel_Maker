from __future__ import annotations

import argparse
import json
from pathlib import Path

from .exceptions import PodcastStudioError
from .script_writer import save_script, write_script


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="podcast-studio-script",
        description="Create a camera-ready, teleprompter-ready script with Claude Code or Codex subscription access.",
    )
    parser.add_argument("brief")
    parser.add_argument("--agent", required=True, choices=("claude", "codex"))
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target-seconds", type=float, default=60.0)
    parser.add_argument("--voice", default="natural, direct, credible, conversational")
    parser.add_argument("--source-transcript")
    parser.add_argument("--source-notes")
    args = parser.parse_args(argv)
    try:
        package = write_script(
            args.brief,
            provider=args.agent,
            project_root=args.project_root,
            target_seconds=args.target_seconds,
            voice=args.voice,
            source_transcript=args.source_transcript,
            source_notes=args.source_notes,
        )
        output = save_script(package, args.output)
    except PodcastStudioError as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(Path(output).resolve()), "script": package.to_dict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
