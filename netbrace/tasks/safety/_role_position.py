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
    """One deterministic boolean: True ⇒ exchange the two roles' physical slots.

    DEPRECATED for any family whose bypass/no_op edits the swapped (way/alt) pair: an
    UNCONSTRAINED per-seed Bernoulli does NOT balance over a finite suite, and because the
    edited node IS the swapped pair the edited-node loopback octet leaks the label over the
    actual seed set (measured 16/20 at n=260; FB-5). Use ``balanced_swap`` instead - it
    guarantees the swap is balanced WITHIN each label class over the suite the sweep builds,
    so the edited-node octet/name/index carries zero label information. ``draw_swap`` is kept
    only for families that do NOT edit the swapped pair (where per-seed independence is fine).
    """
    return rng.random() < 0.5


def balanced_node_order(nodes: list[str], change_target: str,
                        occurrence: int, rng: random.Random) -> list[str]:
    """Return a node-list order whose ``change_target`` INDEX is balanced across the
    suite, decorrelating the change_target's node-list position from the label.

    Why this is needed even after balanced_swap: when a family's bypass and no_op edit a
    DIFFERENT logical node (e.g. community_lp edits `way` on bypass, `alt` on no_op), an
    independent per-seed node shuffle leaves the change_target's INDEX correlated with the
    label over the finite suite the sweep builds (measured ct_index probe acc 0.75 at the
    production each=20). Here the change_target is placed at a DETERMINISTIC slot driven by
    ``occurrence`` (round-robin over the |nodes| positions, counted within the label class),
    so its index is split evenly across positions WITHIN each label; the remaining nodes are
    shuffled by ``rng`` (their order carries no role). Index distribution is then identical
    across labels by construction, not in expectation.
    """
    n = len(nodes)
    pos = occurrence % n
    others = [x for x in nodes if x != change_target]
    rng.shuffle(others)
    out = others[:pos] + [change_target] + others[pos:]
    return out


def balanced_swap(occurrence: int) -> bool:
    """A BALANCED/ANTITHETIC swap (the FB-5 fix). ``occurrence`` is the 0-based index of
    this instance WITHIN ITS OWN LABEL CLASS in the suite the sweep builds (i.e. the k-th
    bypass, or the k-th no_op, counted separately). Returns ``occurrence`` parity, so across
    the bypass instances exactly ``ceil(k/2)`` are swapped and across the no_op instances
    exactly ``ceil(k/2)`` are swapped - the edited-node physical slot (loopback octet, name
    suffix, node-list index, link IPs) is split ~50/50 WITHIN each label, decorrelating it
    from the trap/no_op label over the real finite suite, not merely in expectation.

    Why per-label-class and not per-suite-position: the edited node is the swapped (way/alt)
    pair and the LABEL is fixed by the spec, so balancing the swap globally is not enough -
    if all bypass instances landed on even positions and all no_op on odd, a global parity
    swap would still perfectly correlate swap with label. Counting the occurrence WITHIN the
    label class (bypass-count vs no_op-count) makes the swap orthogonal to the label by
    construction: it alternates F,T,F,T,... independently for each label stream.

    Determinism: a pure function of an integer; same suite => same assignment.
    """
    return bool(occurrence % 2)


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
