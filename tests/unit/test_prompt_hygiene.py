"""CI guard: a scenario's model-visible prose (description + intents_text) must
state the CONFIG EDIT + the POLICY INTENT only — never the routing OUTCOME.

Stating the result ("this blackholes / bypasses / is preferred / overflows") lets a
model score by parroting the prompt with zero protocol reasoning. The red-team
killed lp_waypoint and scale_deagg for exactly this; this test makes prompt hygiene
a build gate instead of a recurring manual catch.

Scope: only `description` + `intents_text` (what the model reads as prose). The diff
(`patch`) legitimately contains config keywords (e.g. an `ip route ... blackhole`
discard static) and is NOT checked here — that's real config, not an outcome claim.
"""
from __future__ import annotations

import re

import pytest

from netbrace.tasks.safety import scenarios

# Substrings that assert an OUTCOME (the answer) rather than the change/intent.
# Kept conservative to avoid false positives; "loop" is excluded (loopback).
_BANNED = [
    "blackhole", "black-hole", "blackholed",
    "null_routed", "null-routed", "null routed",
    "bypass",                       # bypasses the waypoint
    "reroute",                      # states the path shift
    "preferred over", "strictly preferred", "is preferred",
    "withdrawn", "withdraws",       # states the control-plane loss
    "overflow", "overflows",
    "unreachable", "no real path",
    "masks", "masking",
    "severs", "severed",
]


def _prose(scn) -> str:
    return f"{scn.description}\n{scn.intents_text}".lower()


@pytest.mark.parametrize("name", sorted(scenarios.REGISTRY))
def test_prompt_does_not_state_the_outcome(name):
    prose = _prose(scenarios.build(name))
    hits = [w for w in _BANNED if w in prose]
    assert not hits, (
        f"scenario {name!r} leaks the outcome in its prompt prose: {hits}. "
        f"State only the config edit + the policy intent; let the model derive the "
        f"blast from the diff/configs."
    )


def test_every_scenario_has_nonempty_prompt_prose():
    # A scenario with no description/intent gives the model nothing to reason from.
    for name in scenarios.REGISTRY:
        scn = scenarios.build(name)
        assert scn.description.strip(), f"{name}: empty description"
        assert scn.intents_text.strip(), f"{name}: empty intents_text"


def test_ban_list_is_lowercase_and_would_catch_a_known_leak():
    # Guard the guard: a sentence like the old lp_waypoint leak must trip.
    leaky = "this makes the alt egress strictly preferred over the way egress"
    assert any(w in leaky for w in _BANNED)
    assert all(w == w.lower() for w in _BANNED)  # _prose() lowercases input
