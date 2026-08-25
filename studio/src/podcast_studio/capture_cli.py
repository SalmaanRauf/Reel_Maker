from __future__ import annotations

import argparse

from .capture import serve_capture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="podcast-studio-capture",
        description="Open a local browser camera recorder with a scrolling teleprompter.",
    )
    parser.add_argument("root")
    parser.add_argument("--script")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    serve_capture(args.root, script=args.script, host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
