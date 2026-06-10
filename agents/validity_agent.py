#!/usr/bin/env python3
"""
NetHELM Validity Agent — evaluate whether a scenario is technically correct
and Batfish-gradeable before adding it to the benchmark.

Usage examples:
    # Inline scenario description
    ./validate-scenario --scenario "Remove next-hop-self on iBGP peer, frr_square topology"

    # Scenario Python file
    ./validate-scenario --file tasks/safety/baseline_square4.py

    # Pre/post router config pair
    ./validate-scenario --pre configs/r1_pre.conf --post configs/r1_post.conf

    # Preview prompt without calling the API
    ./validate-scenario --scenario "..." --dry-run

Verdict codes:
    APPROVED       — valid, non-trivial, Batfish-gradeable
    NEEDS_REVISION — fixable issues (detailed feedback attached)
    REJECTED       — fundamental flaw; not suitable for the benchmark

Requires: ANTHROPIC_API_KEY env var.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _build_input(args: argparse.Namespace) -> str:
    if args.pre and args.post:
        for fp in (args.pre, args.post):
            if not Path(fp).exists():
                sys.exit(f"File not found: {fp}")
        pre_text  = Path(args.pre).read_text(encoding="utf-8")
        post_text = Path(args.post).read_text(encoding="utf-8")
        return (
            f"## Pre-change configuration ({args.pre})\n```\n{pre_text}\n```\n\n"
            f"## Post-change configuration ({args.post})\n```\n{post_text}\n```\n\n"
            "Evaluate this pre→post config diff as a potential NetHELM safety-axis "
            "scenario. Check: technical correctness, Batfish gradeability across "
            "D1–D8 dimensions, non-triviality, and failure mode clarity."
        )

    if args.file:
        fp = Path(args.file)
        if not fp.exists():
            sys.exit(f"File not found: {args.file}")
        return (
            f"## Scenario file: {args.file}\n"
            f"```python\n{fp.read_text(encoding='utf-8')}\n```\n\n"
            "Evaluate this scenario file for inclusion in the NetHELM safety "
            "benchmark: technical correctness, Batfish gradeability, and novelty."
        )

    if args.scenario:
        return args.scenario

    print("Reading from stdin (Ctrl+D to end)…", file=sys.stderr)
    return sys.stdin.read()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="NetHELM Validity Agent — check scenario correctness and gradeability",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    input_group = ap.add_mutually_exclusive_group()
    input_group.add_argument("--scenario", default=None,
                             help="Inline scenario text")
    input_group.add_argument("--file",     default=None,
                             help="Path to a scenario file (Python or config)")
    ap.add_argument("--pre",     default=None,
                    help="Pre-change router config (pair with --post)")
    ap.add_argument("--post",    default=None,
                    help="Post-change router config (pair with --pre)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview prompt without calling the API")
    args = ap.parse_args()

    if bool(args.pre) != bool(args.post):
        ap.error("--pre and --post must be used together")

    # Guard: --pre/--post can't be combined with --file/--scenario
    if (args.pre or args.post) and (args.file or args.scenario):
        ap.error("Use either --pre/--post OR --file/--scenario, not both")

    sys.path.insert(0, str(ROOT))
    from agents.run_agent import run  # noqa: PLC0415

    user_input = _build_input(args)
    run("validity", user_input, dry_run=args.dry_run, source_hint="batfish")


if __name__ == "__main__":
    main()
