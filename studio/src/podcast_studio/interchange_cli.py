from __future__ import annotations

import argparse
import json
from pathlib import Path

from .exceptions import PodcastStudioError
from .interchange import export_edl, export_fcpxml, export_otio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="podcast-studio-export",
        description="Export an edit plan to CMX 3600 EDL, FCPXML, or OpenTimelineIO.",
    )
    parser.add_argument("plan")
    parser.add_argument("output")
    parser.add_argument("--format", choices=("edl", "fcpxml", "otio"))
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--title")
    args = parser.parse_args(argv)
    export_format = args.format or Path(args.output).suffix.lower().lstrip(".")
    try:
        if export_format == "edl":
            output = export_edl(args.plan, args.output, fps=round(args.fps), title=args.title)
        elif export_format in {"fcpxml", "xml"}:
            output = export_fcpxml(
                args.plan,
                args.output,
                fps=round(args.fps),
                width=args.width,
                height=args.height,
                title=args.title,
            )
        elif export_format in {"otio", "opentimelineio"}:
            output = export_otio(args.plan, args.output, fps=args.fps)
        else:
            parser.error("Unable to infer export format; use --format edl, fcpxml, or otio")
    except PodcastStudioError as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(Path(output).resolve()), "format": export_format}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
