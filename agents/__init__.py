"""NetHELM agent API — importable Python interface to the validity and research agents."""
from __future__ import annotations

from .run_agent import run as _run


def run_validity_check(text: str, dry_run: bool = False) -> str:
    """Evaluate `text` as a NetHELM scenario for technical correctness and Batfish gradeability.

    Returns the model's full verdict string (APPROVED / NEEDS_REVISION / REJECTED + reasoning).
    Also streams the response to stdout in real time.
    """
    return _run("validity", text, dry_run=dry_run, source_hint="batfish")


def run_research_check(text: str, dry_run: bool = False) -> str:
    """Evaluate `text` (code, paper section, or results) against publication standards.

    Returns the model's full verdict string (PASS / NEEDS_WORK / FAIL + issues).
    Also streams the response to stdout in real time.
    """
    return _run("research", text, dry_run=dry_run, source_hint="papers")
