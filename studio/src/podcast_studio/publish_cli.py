from __future__ import annotations

import argparse
import json
from pathlib import Path

from .exceptions import PodcastStudioError
from .publish import build_package, save_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="podcast-studio-publish",
        description="Create faithful titles, descriptions, platform copy, chapters, hashtags, and thumbnail concepts.",
    )
    parser.add_argument("transcript")
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float)
    parser.add_argument("--title-hint")
    parser.add_argument("--agent", choices=("claude", "codex"))
    parser.add_argument("--project-root")
    parser.add_argument("--brand-voice", default="clear, precise, credible, direct")
    args = parser.parse_args(argv)
    try:
        package = build_package(
            args.transcript,
            start=args.start,
            end=args.end,
            title_hint=args.title_hint,
            agent=args.agent,
            project_root=args.project_root,
            brand_voice=args.brand_voice,
        )
        output = save_package(package, args.output)
    except PodcastStudioError as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(Path(output).resolve()), "package": package.to_dict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
