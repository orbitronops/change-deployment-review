"""CLI: python -m orbitronops_change_review review <change.yaml>
[--baseline baseline.yaml] [--format text|json|markdown]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from a checkout without installing: `src` on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orbitronops_change_review.checks import review_change  # noqa: E402
from orbitronops_change_review.report import render_markdown, render_text  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="orbitronops-change-review",
        description="Review a Kubernetes deployment change before it ships (OrbitronOps demo).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review", help="Review one manifest change file.")
    review.add_argument("file", help="Path to the change manifest (YAML). See examples/.")
    review.add_argument("--baseline", default=None,
                        help="Path to the baseline manifest to diff against.")
    review.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    args = parser.parse_args(argv)

    if args.command == "review":
        try:
            change_text = Path(args.file).read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"error: file not found: {args.file}", file=sys.stderr)
            return 2
        baseline_text = None
        if args.baseline:
            try:
                baseline_text = Path(args.baseline).read_text(encoding="utf-8")
            except FileNotFoundError:
                print(f"error: baseline file not found: {args.baseline}", file=sys.stderr)
                return 2
        if not change_text.strip():
            print("error: empty manifest file", file=sys.stderr)
            return 2
        try:
            result = review_change(change_text, baseline_text)
        except ValueError as exc:
            print(f"error: could not parse manifest: {exc}", file=sys.stderr)
            return 2

        if args.format == "json":
            print(json.dumps(result.to_dict(), indent=2))
        elif args.format == "markdown":
            print(render_markdown(result))
        else:
            print(render_text(result))
        return 0 if result.verdict != "BLOCK" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
