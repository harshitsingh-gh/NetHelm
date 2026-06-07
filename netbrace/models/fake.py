"""FakeModel: returns canned output for pipeline testing (zero API spend)."""

from __future__ import annotations

from netbrace.core.jsonio import to_json
from netbrace.core.schemas import BlastRadius, TaskSpec

_GARBAGE = "The network change looks fine to me. No issues expected."


class FakeModel:
    """Returns canned raw text per task, for testing the pipeline end-to-end.

    mode:
      'oracle'  — echo the task's ground-truth blast_radius as JSON (F1 = 1.0)
      'empty'   — predict empty blast radius (correct for trap tasks, miss otherwise)
      'garbage' — return non-JSON text (scores 'invalid')
    """

    def __init__(self, mode: str = "oracle") -> None:
        if mode not in ("oracle", "empty", "garbage"):
            raise ValueError(f"unknown mode {mode!r}")
        self.mode = mode

    def respond(self, task: TaskSpec) -> str:
        """Return raw model-style text (a ```json block) for the given task."""
        if self.mode == "garbage":
            return _GARBAGE
        if self.mode == "empty":
            br = BlastRadius()
        else:  # oracle
            br = task.oracle.blast_radius
        payload = to_json(br).strip()
        return f"```json\n{payload}\n```"
