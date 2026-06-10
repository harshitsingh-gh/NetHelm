#!/usr/bin/env python3
"""
NetHELM Research Agent — check whether code, experimental results, or paper
text meets research publication standards for HotNets / ACM SIGCOMM / NeurIPS
workshop venues.

Usage examples:
    # Review a grader Python file
    ./research-check --file harness/graders/safety.py

    # Review a paper draft section (inline)
    ./research-check --input "We evaluate 8 LLMs on 300 scenarios..."

    # Review an experimental results table
    ./research-check --mode results --file runs/2026-06-01_sweep/results.csv

    # Preview prompt without calling the API
    ./research-check --file harness/graders/safety.py --dry-run

Modes:
    code     (default) — networking correctness, grader validity, edge cases
    paper    — protocol claims, citations, novelty, NetPress overlap
    results  — statistical validity, N per cell, confidence intervals, baselines

Verdict codes:
    PASS         — meets publication standards
    NEEDS_WORK   — fixable issues (detailed feedback attached)
    FAIL         — blocking issues; not publishable as-is

Requires: ANTHROPIC_API_KEY env var.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_MODE_PREAMBLES = {
    "code": (
        "Review the following code for publication-readiness. Check: networking "
        "correctness, Batfish API usage (column names, question types), edge case "
        "handling, reproducibility, and alignment with NetConfEval/HELM methodology."
    ),
    "paper": (
        "Review the following paper text for publication-readiness. Check: "
        "protocol claims vs. RFCs, citation accuracy, novelty claims vs. existing "
        "work (especially NetPress arXiv:2506.03231), and scope accuracy."
    ),
    "results": (
        "Review the following experimental results for publication-readiness. "
        "Check: N per (scenario, model) cell, confidence intervals, baseline "
        "comparisons, model version pinning, API cost tracking, and grader "
        "inter-annotator agreement (κ ≥ 0.7)."
    ),
}


def _build_input(args: argparse.Namespace) -> str:
    preamble = _MODE_PREAMBLES[args.mode]

    if args.file:
        fp = Path(args.file)
        if not fp.exists():
            sys.exit(f"File not found: {args.file}")
        ext = fp.suffix.lower()
        lang = "python" if ext == ".py" else "text"
        body = (
            f"## File: {args.file}\n"
            f"```{lang}\n{fp.read_text(encoding='utf-8')}\n```"
        )
        return f"{preamble}\n\n{body}"

    if args.input:
        return f"{preamble}\n\n{args.input}"

    print("Reading from stdin (Ctrl+D to end)…", file=sys.stderr)
    raw = sys.stdin.read()
    return f"{preamble}\n\n{raw}"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="NetHELM Research Agent — check code/paper/results against publication standards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    input_group = ap.add_mutually_exclusive_group()
    input_group.add_argument("--file",  default=None,
                             help="Path to code file, paper draft, or results CSV")
    input_group.add_argument("--input", default=None,
                             help="Inline text to evaluate")
    ap.add_argument("--mode",    choices=list(_MODE_PREAMBLES), default="code",
                    help="What kind of content is being reviewed (default: code)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview prompt without calling the API")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    from agents.run_agent import run  # noqa: PLC0415

    # For paper/results modes the KB source hint targets the papers/ subcorpus;
    # for code mode it targets batfish/ (grader facts, patterns)
    hint = "papers" if args.mode in ("paper", "results") else "batfish"

    user_input = _build_input(args)
    run("research", user_input, dry_run=args.dry_run, source_hint=hint)


if __name__ == "__main__":
    main()
