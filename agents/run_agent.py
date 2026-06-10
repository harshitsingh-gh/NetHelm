#!/usr/bin/env python3
"""
Core runner for NetHELM validity and research agents.

Reads system prompt from agents/{validity,research}_agent_prompt.md,
enriches the prompt with KB context, then calls Claude Opus 4.8 with
adaptive thinking and streaming.

Usage:
    python agents/run_agent.py validity --input "scenario: ..."
    python agents/run_agent.py validity --file tasks/safety/baseline_square4.py
    python agents/run_agent.py research --file harness/graders/safety.py
    python agents/run_agent.py research --input "..." --dry-run

Requires: ANTHROPIC_API_KEY env var. Use --dry-run to preview without calling API.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT       = Path(__file__).resolve().parent.parent
AGENTS_DIR = Path(__file__).resolve().parent

AGENT_PROMPTS = {
    "validity": AGENTS_DIR / "validity_agent_prompt.md",
    "research": AGENTS_DIR / "research_agent_prompt.md",
}

# ANSI colours — disabled automatically when not a TTY
_USE_COLOR = sys.stdout.isatty()

_COLORS = {
    "green":  "\033[32m",
    "red":    "\033[31m",
    "yellow": "\033[33m",
    "bold":   "\033[1m",
    "reset":  "\033[0m",
}

_VERDICT_COLORS = {
    # validity agent verdicts
    "APPROVED":        "green",
    "REJECTED":        "red",
    "NEEDS_REVISION":  "yellow",
    # research agent verdicts
    "PASS":            "green",
    "FAIL":            "red",
    "NEEDS_WORK":      "yellow",
}


def _color(text: str, color: str) -> str:
    if not _USE_COLOR:
        return text
    code = _COLORS.get(color, "")
    reset = _COLORS["reset"]
    return f"{code}{text}{reset}"


def _kb_context(query_text: str, top_general: int = 3,
                source_hint: str | None = None, top_focused: int = 2) -> str:
    """Retrieve KB chunks for the query and return a formatted context block.

    Runs two passes:
      1. General top-N search across all sources.
      2. (optional) Focused top-N search filtered to `source_hint`.
    Deduplicates by source+text before returning.
    """
    try:
        sys.path.insert(0, str(ROOT))
        from knowledge.tools.query import query as kb_query

        general  = kb_query(query_text[:500], top=top_general, silent=True)
        focused  = []
        if source_hint:
            focused = kb_query(query_text[:500], top=top_focused,
                               source_filter=source_hint, silent=True)

        seen, merged = set(), []
        for r in general + focused:
            key = (r["source"], r["text"][:80])
            if key not in seen:
                seen.add(key)
                merged.append(r)

        if not merged:
            return ""

        lines = ["## Relevant knowledge base context\n"]
        for r in merged:
            lines.append(
                f"### {r['source']} (score={r['score']:.3f})\n{r['text']}\n"
            )
        return "\n".join(lines)

    except Exception as e:
        return f"[KB unavailable: {e}]"


def run(agent: str, user_input: str, dry_run: bool = False,
        source_hint: str | None = None) -> str:
    """Run an agent check and stream results to stdout.

    Args:
        agent:       "validity" or "research"
        user_input:  the scenario/code/paper text to evaluate
        dry_run:     if True, print prompt preview without calling the API
        source_hint: optional KB source filter for the focused pass
                     (e.g. "batfish" for validity, "papers" for research)

    Returns:
        The full text response from the model.
    """
    prompt_path = AGENT_PROMPTS.get(agent)
    if not prompt_path or not prompt_path.exists():
        sys.exit(f"Unknown agent or missing prompt file: {agent}")

    system_prompt = prompt_path.read_text(encoding="utf-8")
    kb_ctx        = _kb_context(user_input, source_hint=source_hint)

    full_user_msg = user_input
    if kb_ctx:
        full_user_msg = kb_ctx + "\n\n---\n\n" + user_input

    if dry_run:
        print(_color("=== SYSTEM PROMPT (first 600 chars) ===", "bold"))
        print(system_prompt[:600])
        print(_color("\n=== USER MESSAGE (first 1200 chars) ===", "bold"))
        print(full_user_msg[:1200])
        return "[dry-run: no API call made]"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit(
            "ANTHROPIC_API_KEY not set.\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "Or use --dry-run to preview the prompt."
        )

    try:
        import anthropic
    except ImportError:
        sys.exit(
            "anthropic package not installed.\n"
            "  Run: harness/venvs/nethelm/bin/pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=api_key)

    collected: list[str] = []
    in_verdict_line = False

    with client.messages.stream(
        model="claude-opus-4-8",
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": full_user_msg}],
    ) as stream:
        for text in stream.text_stream:
            # Colour any VERDICT: line as it streams
            if "VERDICT:" in text:
                in_verdict_line = True
            if in_verdict_line:
                for verdict, color in _VERDICT_COLORS.items():
                    if verdict in text:
                        text = text.replace(verdict, _color(verdict, color))
                        in_verdict_line = False
                        break
            print(text, end="", flush=True)
            collected.append(text)

    print()  # trailing newline
    return "".join(collected)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run a NetHELM validity or research agent check"
    )
    ap.add_argument("agent", choices=["validity", "research"],
                    help="Which agent to run")
    ap.add_argument("--input",    default=None,
                    help="Inline text input to evaluate")
    ap.add_argument("--file",     default=None,
                    help="Path to file to evaluate")
    ap.add_argument("--dry-run",  action="store_true",
                    help="Preview prompt without calling the API")
    args = ap.parse_args()

    if args.file:
        p = Path(args.file)
        if not p.exists():
            sys.exit(f"File not found: {args.file}")
        user_input = f"File: {args.file}\n\n```\n{p.read_text(encoding='utf-8')}\n```"
    elif args.input:
        user_input = args.input
    else:
        print("Reading from stdin (Ctrl+D to end)…", file=sys.stderr)
        user_input = sys.stdin.read()

    hint = "batfish" if args.agent == "validity" else "papers"
    run(args.agent, user_input, dry_run=args.dry_run, source_hint=hint)


if __name__ == "__main__":
    main()
