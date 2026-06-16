"""The `blackhole` scenario: removing a "redundant" static route severs a
loopback-sourced iBGP session AND blackholes the data plane (square4).

Scenario S15/S08-flavored (paper/refs/blast_radius_scenario_catalog.md). Reuses
the verified square4 baseline (iBGP full mesh + static routes to loopbacks). The
change removes r1's static route to r4's loopback (10.0.0.4/32).

That single static is LOAD-BEARING in two ways the "looks redundant" framing
hides:
  1. Data plane: r1's BGP path to 10.0.0.4/32 has next-hop 10.0.0.4 (next-hop-self
     from r4), resolved recursively *via that very static*. Removing it makes the
     next-hop unresolvable.
  2. Control plane: 10.0.0.4 is ALSO the peering address of r1's loopback-sourced
     iBGP session to r4. Removing the static means r1 can no longer reach the
     peer, so the r1<->r4 iBGP session TEARS DOWN (both endpoints report it lost).

So the TRUE blast radius is MULTI-DIMENSIONAL — NOT a quiet single-node blackhole
with other routers unaffected (verified live; see HANDOFF.md "verified facts"):
  * D1 = {r1's session to r4, r4's session to r1}  (the iBGP session, both ends = 2)
  * D2 = r1 loses 10.0.0.4/32 from its RIB (static gone, BGP next-hop unresolvable)
  * D3 = r1 -> 10.0.0.4 unreachable
  * D7 = NO_ROUTE blackhole localized at r1

The point of D7 OVER D3: not just "r1 cannot reach 10.0.0.4" (reachability) but
the *classification* (a silent blackhole, not a filtered/denied drop) and the
*localization* (the dropping node is r1). The change reads like a harmless cleanup
of a "redundant" static route — the trap is that the static is load-bearing for
BOTH the recursive next-hop AND the iBGP peering.

DELIBERATE D3+D7 OVERLAP (disclosed): the registration declares the SAME flow set
as both reachability_flows (D3) and forwarding_flows (D7), so the single
r1->10.0.0.4 NO_ROUTE is intentionally scored under BOTH dimensions to demonstrate
D7's added classification/localization value. This is the OPPOSITE choice from
`ipc_scenario` (scenarios.py), which declares D3-only precisely to avoid
double-counting. Read the two together as a contrast — NOT as evidence of two
independent damage events here.

Verified live: PRE r1->10.0.0.4 ACCEPTED; POST r1->10.0.0.4 NO_ROUTE at r1, AND
the r1<->r4 iBGP session drops at both endpoints (D1=2). Earlier prose / catalog
under-reported this as a quiet "D7, D3" event with "other routers unaffected" —
that was wrong: r4 loses its session to r1, and D1/D2 fire.
"""

from __future__ import annotations

import difflib

from netbrace.tasks.safety import baseline_square4 as sq4
from netbrace.topology.patches import apply_unified_diff

CHANGE_TARGET = "r1"

# The static route removed by the change (r1's reachability to r4's loopback).
_REMOVED_LINE = "ip route 10.0.0.4/32 192.0.2.10"

# Flows to probe for forwarding anomalies: every node toward r4's loopback.
PROBE_FLOWS = [("r1", "10.0.0.4/32"), ("r2", "10.0.0.4/32"),
               ("r3", "10.0.0.4/32"), ("r4", "10.0.0.4/32")]

WATCHED_PREFIXES = ["10.0.0.4/32"]


def baseline_configs() -> dict[str, str]:
    """The (frozen) square4 baseline — reused verbatim."""
    return sq4.baseline_configs()


def _post_r1_config() -> str:
    """r1 with the static route to 10.0.0.4/32 removed."""
    before = sq4.baseline_configs()["r1"]
    after = "\n".join(ln for ln in before.splitlines() if ln.strip() != _REMOVED_LINE)
    return after + "\n" if before.endswith("\n") else after


def change_patch() -> str:
    """Unified diff on r1 removing the static route. Guaranteed to apply."""
    before = sq4.baseline_configs()["r1"]
    after = _post_r1_config()
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="r1.conf", tofile="r1.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError("blackhole change patch does not round-trip")
    return patch
