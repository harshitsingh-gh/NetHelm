"""Rendered-prompt hygiene gate (red-team freeze gate 2026-06-10, INVALIDATOR #1).

The old prompt-hygiene test inspected scenario FIELDS (description/intents_text) —
and missed that the runner rendered the scenario NAME (which encodes the answer
category: "no_op", "ms_blackhole", "under-kept", ...) straight into the prompt as
the topology header. This gate checks the FINAL RENDERED PROMPT STRING — the exact
text a paid model receives — for every registry scenario and a multi-generator
sample. Any answer-bearing token in the rendered prompt is a paid-run invalidator.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from netbrace.tasks.safety import scenarios

_SPEC = importlib.util.spec_from_file_location(
    "run_extended_scenario",
    Path(__file__).resolve().parents[2] / "scripts" / "run_extended_scenario.py")
_res = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("run_extended_scenario", _res)
_SPEC.loader.exec_module(_res)
_build_prompt = _res._build_prompt


# Axis labels across all four generators — none may EVER reach a model.
_AXIS_TOKENS = (
    "no_op", "-bypass", "lp_raise_alt", "lp_drop_way", "prepend_way",
    "ms_blackhole", "ms_reroute", "low_half", "high_half", "both_halves",
    "over_clear", "over_marginal", "under-kept", "under-withdrawn",
    "-withdrawn", "-kept", "is_trap", "dims_label",
)


def _all_instances():
    insts = [scenarios.build(n) for n in sorted(scenarios.REGISTRY)]
    insts += scenarios.build_generated_suite_multi(24, base_seed=0)
    return insts


@pytest.mark.parametrize("scn", _all_instances(), ids=lambda s: s.name)
def test_rendered_prompt_carries_no_answer_tokens(scn):
    prompt = _build_prompt(scn)

    # 1) the scenario name (and any seedless prefix of it) must not appear.
    assert scn.name not in prompt, "scenario name rendered into the prompt"
    if scn.name.startswith("gen_"):
        label = scn.name[len("gen_"):].rsplit("_s", 1)[0]
        assert label not in prompt, f"dims_label {label!r} rendered into the prompt"

    # 2) no generator axis token anywhere in the rendered text.
    for tok in _AXIS_TOKENS:
        assert tok not in prompt, f"axis token {tok!r} leaked into the prompt"


def test_topology_header_is_content_free():
    scn = scenarios.build_generated_suite_multi(4, base_seed=0)[0]
    prompt = _build_prompt(scn)
    assert "### Topology: topology_" in prompt
