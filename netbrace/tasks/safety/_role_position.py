"""Per-seed ROLE->PHYSICAL-POSITION randomization (the positional-leak fix).

THE DEFECT this closes (measured, publishability-blocking). Every reroute generator
emits a bypass twin (is_trap=True) and a diff-shape-identical no_op twin
(is_trap=False). Originally the WAYPOINT/inspection role (`way`/`wabr`/`rr->way`/the
live high-LP clause/the WAY-side route-map) was HARD-PINNED to a fixed physical slot —
interface index `eth1`, node-list position 1, loopback octet `.2`, route-map name
`*_WAY_*`, clause `permit 10`. Because the trap/no_op label correlates with "is the edit
on the waypoint side", a probe classifier reading ONLY the edited element's
identity/position (+ direction) — with ZERO routing reasoning — perfectly predicted the
label, invariant across seeds. That invalidates any published detection number.

THE FIX. Per seed, randomly assign which PHYSICAL slot plays the inspection/waypoint role
vs the bypass role. The LOGICAL roles (`way` = waypoint, `alt` = bypass) remain the
semantic anchors the ground truth + intents are built from; only their PHYSICAL identity
(loopback octet, node name suffix, link-IP carving, node-list order, and — where the
generator encodes the role in an identifier — the route-map name / clause seq) is swapped
per seed. So "raise eth1" / "edit the node at position 1" / "edit RM_TO_WAY_OUT" / "edit
clause permit 10" is a TRAP in ~half the seeds and a NO_OP in the other half. The only
remaining signal is "the edit moves traffic off the waypoint", which REQUIRES reading
which interface/neighbor/clause the config places on the inspection path (via the
waypoint_intents the model is given) — exactly the routing reasoning the benchmark tests.

Determinism is preserved: the swap is a single deterministic draw seeded by ``seed``
(see ``draw_swap``), so the same seed yields the same instance. The ground truth is
preserved: the logical-role configs are byte-identical to before up to the physical
relabeling, so bypass still fires {D4 waypoint, D10 intent} ONLY and no_op stays empty.

Usage pattern (each leaky generator):

    swap = draw_swap(rng)                 # one extra draw, AFTER the existing draws so
                                          # the prior addressing draws are untouched
    ...
    rid_index = swapped_rid_index(base_rid_index, swap, ("way", "alt"))
    name      = swapped_names(base_names, swap, ("way", "alt"))
    nodes     = shuffled_nodes(all_role_names, rng2)   # node-list order carries no role

The two swapped roles MUST be the inspection/bypass pair (e.g. ("way","alt") or
("wabr","babr")); ``swap=True`` exchanges their physical slot assignments.
"""

from __future__ import annotations

import random
from typing import Sequence


def draw_swap(rng: random.Random) -> bool:
    """One deterministic boolean: True ⇒ exchange the two roles' physical slots."""
    return rng.random() < 0.5


def swapped_rid_index(
    base: dict[str, int], swap: bool, pair: tuple[str, str]
) -> dict[str, int]:
    """Return a copy of ``base`` (role->slot index) with ``pair``'s indices exchanged
    when ``swap`` — so the waypoint role's loopback octet / link-IP slot / name suffix
    lands on either physical slot per seed."""
    out = dict(base)
    if swap:
        a, b = pair
        out[a], out[b] = base[b], base[a]
    return out


def swapped_names(
    base: dict[str, str], swap: bool, pair: tuple[str, str]
) -> dict[str, str]:
    """Return a copy of ``base`` (role->node name) with ``pair``'s names exchanged when
    ``swap`` — so the waypoint role's name suffix index is not a fixed tell."""
    out = dict(base)
    if swap:
        a, b = pair
        out[a], out[b] = base[b], base[a]
    return out


def swap_token(swap: bool, pair: tuple[str, str], role: str) -> str:
    """Map a LOGICAL role to the PHYSICAL token to use for an identifier (route-map name
    suffix, clause-seq selector, etc.). When ``swap`` and ``role`` is in ``pair`` it
    returns the OTHER member, so the identifier the waypoint role uses is not fixed."""
    if swap and role in pair:
        a, b = pair
        return b if role == a else a
    return role
