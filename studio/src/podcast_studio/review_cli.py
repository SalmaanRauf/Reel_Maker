from __future__ import annotations

import argparse

from .review import serve_review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="podcast-studio-review", description="Open the local Podcast Studio clip review room.")
    parser.add_argument("root")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    serve_review(args.root, host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
