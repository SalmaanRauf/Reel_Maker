from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import build_blind_review_packet, run_benchmark
from .exceptions import PodcastStudioError, ValidationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="podcast-studio-benchmark",
        description="Run reproducible edit-quality gates or create a blind human-review packet.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("manifest")
    run.add_argument("--output", required=True)

    blind = subparsers.add_parser("blind")
    blind.add_argument("--candidate", action="append", required=True, metavar="ID=PATH")
    blind.add_argument("--output", required=True)
    blind.add_argument("--seed", default="podcast-studio")

    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            payload = run_benchmark(args.manifest, args.output)
            exit_code = 0 if payload["summary"]["failed"] == 0 else 1
        else:
            candidates = []
            for assignment in args.candidate:
                if "=" not in assignment:
                    raise ValidationError(f"Invalid candidate `{assignment}`; expected ID=PATH")
                candidate_id, path = assignment.split("=", 1)
                candidates.append({"id": candidate_id.strip(), "path": path})
            payload = build_blind_review_packet(candidates, args.output, seed=args.seed)
            exit_code = 0
    except PodcastStudioError as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(Path(args.output).resolve()), "result": payload}, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
