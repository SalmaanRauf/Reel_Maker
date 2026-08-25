from __future__ import annotations

import argparse
import json
from pathlib import Path

from .exceptions import PodcastStudioError
from .style_analysis import analyze_reference_video, fingerprint_plan, save_comparison
from .util import dump_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="podcast-studio-style",
        description="Measure edit dynamics in a reference render or edit plan and compare style fingerprints.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reference = subparsers.add_parser("reference")
    reference.add_argument("video")
    reference.add_argument("--output", required=True)
    reference.add_argument("--annotations")
    reference.add_argument("--scene-threshold", type=float, default=0.32)

    plan = subparsers.add_parser("plan")
    plan.add_argument("plan")
    plan.add_argument("--output", required=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("reference")
    compare.add_argument("plan")
    compare.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "reference":
            fingerprint = analyze_reference_video(
                args.video,
                args.output,
                scene_threshold=args.scene_threshold,
                annotations=args.annotations,
            )
            payload = fingerprint.to_dict()
        elif args.command == "plan":
            fingerprint = fingerprint_plan(args.plan)
            dump_json(fingerprint.to_dict(), args.output)
            payload = fingerprint.to_dict()
        else:
            payload = save_comparison(args.reference, args.plan, args.output)
    except PodcastStudioError as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(Path(args.output).resolve()), "result": payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
