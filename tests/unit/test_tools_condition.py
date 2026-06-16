"""Tests for the tools-augmented condition (scrutiny_2026-06-09.md change #2) and the
verification-gate reframe (change #1).

Two cheap, additive pieces:
  * ``_format_pre_state`` renders BGP-session + RIB dataframes as plain show-style
    text (pure; no Batfish) — the PRE-state observation the tools condition feeds the
    model. It must contain only PRE facts, never post-state.
  * ``_build_prompt(scn, pre_state=...)`` appends that block in the tools condition
    and the gate framing in BOTH conditions, WITHOUT leaking the outcome (hygiene).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

from netbrace.batfish.extended_oracle import _format_pre_state
from netbrace.tasks.safety import scenarios

# load scripts/run_extended_scenario.py as a module (scripts/ is not a package).
_SPEC = importlib.util.spec_from_file_location(
    "run_extended_scenario",
    Path(__file__).resolve().parents[2] / "scripts" / "run_extended_scenario.py")
_res = importlib.util.module_from_spec(_SPEC)
sys.modules["run_extended_scenario"] = _res
_SPEC.loader.exec_module(_res)


def _frames():
    sess = pd.DataFrame([
        {"Node": "r1", "VRF": "default", "Remote_IP": "10.0.0.2",
         "Remote_AS": "65000", "Established_Status": "ESTABLISHED"},
        {"Node": "r2", "VRF": "default", "Remote_IP": "10.0.0.1",
         "Remote_AS": "65000", "Established_Status": "ESTABLISHED"},
    ])
    routes = pd.DataFrame([
        {"Node": "r1", "VRF": "default", "Network": "10.0.0.1/32",
         "Next_Hop_IP": "AUTO/NONE(-1l)", "Next_Hop_Interface": "lo",
         "Protocol": "connected"},
        {"Node": "r2", "VRF": "default", "Network": "203.0.113.0/24",
         "Next_Hop_IP": "10.0.0.3", "Next_Hop_Interface": "dynamic",
         "Protocol": "ibgp"},
    ])
    return sess, routes


def test_format_pre_state_is_show_style_and_grouped_per_node():
    text = _format_pre_state(*_frames())
    assert "=== r1 ===" in text and "=== r2 ===" in text
    assert "show ip bgp summary" in text
    assert "show ip route" in text
    assert "ESTABLISHED" in text
    assert "203.0.113.0/24" in text and "via 10.0.0.3" in text
    # the AUTO/NONE next-hop sentinel is suppressed (a connected loopback)
    assert "AUTO/NONE" not in text


def test_format_pre_state_is_deterministic():
    a = _format_pre_state(*_frames())
    b = _format_pre_state(*_frames())
    assert a == b


def test_build_prompt_no_tools_has_gate_framing_but_no_observed_state():
    scn = scenarios.build("ipc")
    p = _res._build_prompt(scn)
    assert "verification gate" in p.lower()
    assert "Observed PRE-change network state" not in p


def test_build_prompt_tools_appends_observed_state():
    scn = scenarios.build("ipc")
    pre = "=== r1 ===\n--- show ip bgp summary ---\n10.0.0.2 65000 ESTABLISHED"
    p = _res._build_prompt(scn, pre_state=pre)
    assert "Observed PRE-change network state" in p
    assert "ESTABLISHED" in p
    # the block is labelled PRE / before-the-change (never the post-state answer)
    assert "before the change is applied" in p.lower() or "pre-change" in p.lower()


def test_gate_framing_does_not_leak_an_outcome():
    # The reframe is a build gate: it states the ROLE of the prediction, not the
    # result of any change. Reuse the same ban list the hygiene CI uses.
    from tests.unit.test_prompt_hygiene import _BANNED
    framing = _res._GATE_FRAMING.lower()
    assert not [w for w in _BANNED if w in framing]
