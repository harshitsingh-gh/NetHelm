"""ExtendedFakeModel: canned 8-dimension output for zero-API pipeline testing.

Emits the FLAT model-output JSON that evals/extended_parser.py consumes (not the
nested ExtendedBlastRadius.to_json form), so the full prompt->model->parse->grade
loop can run end-to-end without an API key. Swapping this for a real model
(e.g. Claude) is a one-function change — see scripts/run_extended_scenario.py.
"""

from __future__ import annotations

import json

from netbrace.core.dimensions import ExtendedBlastRadius

_GARBAGE = "The change looks harmless to me; nothing should break."


def flat_prediction_json(ext: ExtendedBlastRadius) -> str:
    """Serialize an ExtendedBlastRadius to the flat 8-key model-output format."""
    e = ext.normalized()
    obj = {
        "sessions_lost": [m.model_dump() for m in e.base.sessions_lost],
        "prefixes_lost": [m.model_dump() for m in e.base.prefixes_lost],
        "reachability_lost": [m.model_dump() for m in e.base.reachability_lost],
        "waypoint_violations": [m.model_dump() for m in e.waypoint_violations],
        "redundancy_losses": [m.model_dump() for m in e.redundancy_losses],
        "filter_deltas": [m.model_dump() for m in e.filter_deltas],
        "forwarding_anomalies": [m.model_dump() for m in e.forwarding_anomalies],
        "scale_violations": [m.model_dump() for m in e.scale_violations],
        "bgp_withdrawals": [m.model_dump() for m in e.bgp_withdrawals],
        "intent_violations": [m.model_dump() for m in e.intent_violations],
    }
    return json.dumps(obj, sort_keys=True, indent=2)


class ExtendedFakeModel:
    """Returns canned raw text given the oracle ground truth, for pipeline tests.

    mode:
      'oracle'  — echo the ground-truth ExtendedBlastRadius as flat JSON (F1=1.0)
      'empty'   — predict nothing (correct for traps, total miss otherwise)
      'garbage' — non-JSON text (scores 'invalid')
    """

    def __init__(self, mode: str = "oracle") -> None:
        if mode not in ("oracle", "empty", "garbage"):
            raise ValueError(f"unknown mode {mode!r}")
        self.mode = mode

    def respond(self, ground_truth: ExtendedBlastRadius) -> str:
        if self.mode == "garbage":
            return _GARBAGE
        ext = ExtendedBlastRadius() if self.mode == "empty" else ground_truth
        return f"```json\n{flat_prediction_json(ext)}\n```"
