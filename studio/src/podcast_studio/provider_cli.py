from __future__ import annotations

import argparse
import json
from pathlib import Path

from .exceptions import PodcastStudioError
from .providers import run_provider, write_consent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="podcast-studio-provider",
        description="Create consent receipts and run allowlisted specialty model adapters.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    consent = subparsers.add_parser("consent")
    consent.add_argument("directory")
    consent.add_argument("--subject", required=True)
    consent.add_argument("--scope", required=True, choices=("voice-clone", "identity-manipulation", "digital-replica"))
    consent.add_argument("--evidence", required=True)
    consent.add_argument("--expires-at")

    run = subparsers.add_parser("run")
    run.add_argument("config")
    run.add_argument("provider")
    run.add_argument("--receipts-dir", required=True)
    run.add_argument("--consent")
    run.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")

    args = parser.parse_args(argv)
    try:
        if args.command == "consent":
            output = write_consent(
                args.directory,
                subject=args.subject,
                scope=args.scope,
                evidence=args.evidence,
                expires_at=args.expires_at,
            )
            payload = {"consent": str(output)}
        else:
            substitutions: dict[str, str] = {}
            for assignment in args.set:
                if "=" not in assignment:
                    parser.error(f"Invalid --set value: {assignment}; expected KEY=VALUE")
                key, value = assignment.split("=", 1)
                if not key.strip():
                    parser.error("Provider substitution key cannot be empty")
                substitutions[key.strip()] = value
            result = run_provider(
                args.config,
                args.provider,
                substitutions,
                receipts_dir=args.receipts_dir,
                consent_path=args.consent,
            )
            payload = result.to_dict()
    except PodcastStudioError as exc:
        parser.error(str(exc))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
