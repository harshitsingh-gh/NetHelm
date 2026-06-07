"""The `blackhole` scenario (D7): a recursive-next-hop blackhole on square4.

Scenario S15/S08-flavored (paper/refs/blast_radius_scenario_catalog.md). Reuses
the verified square4 baseline (iBGP full mesh + static routes to loopbacks). The
change removes r1's static route to r4's loopback (10.0.0.4/32). r1's only BGP
path to 10.0.0.4/32 has next-hop 10.0.0.4 (next-hop-self from r4), which is
resolved *via that very static route* — so removing it makes the next-hop
unresolvable and r1 silently drops traffic to 10.0.0.4 (Batfish disposition
NO_ROUTE). Other routers are unaffected.

The point of D7 over D3: not just "r1 cannot reach 10.0.0.4" (reachability) but
the *classification* (a silent blackhole, not a filtered/denied drop) and the
*localization* (the dropping node is r1). The change reads like a harmless
cleanup of a "redundant" static route.

Verified live: PRE r1->10.0.0.4 ACCEPTED; POST r1->10.0.0.4 NO_ROUTE at r1.
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
