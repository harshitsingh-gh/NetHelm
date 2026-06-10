"""S-IPC-01 — Class 1: Internal routing-policy silent withdrawal (the FLAGSHIP).

The "implicit deny-all" maintenance trap (Maintenance Type 2 in
knowledge/corpus/noc/maintenances_that_caused_outages.md; operational lore): an
iBGP **outbound prefix-list** edit on the route reflector (r1) that, intending only
to "clean up" advertisements toward a client, actually withdraws a prefix the data
plane needs. BGP sessions stay ESTABLISHED; the RIB silently empties; reachability
collapses. At the prefix level this resembles part of the Facebook Oct-2021
withdrawal (which, note, ALSO took BGP fully down — so this is a clean kernel of the
*silent-withdrawal* failure mode, not a reproduction of that whole incident).

Grounding note: this is NOT the Rogers Jul-2022 mechanism. Rogers was a filter
*removal* → route *flood* → core *overload/crash* (a D8 scale event), which grounds
the separate scale/overload class — see the corrected rogers_canada_outage_jul2022.md.

Topology: `baseline_ipc3` — r2 — r1(RR) — r3. r3 originates the customer prefix
203.0.113.0/24 (no static backup anywhere). The pre state advertises it r3→r1→r2.

The change (on r1, toward r2 only):
  + ip prefix-list CLEANUP_OUT seq 5  permit 10.0.0.0/8 le 32
  + ip prefix-list CLEANUP_OUT seq 10 permit 192.0.2.0/24 le 30
  + route-map TO_R2_OUT permit 10
  +  match ip address prefix-list CLEANUP_OUT
  + neighbor 10.0.0.2 route-map TO_R2_OUT out

The engineer's intent (see the prompt) is to stop leaking internal infrastructure
noise. The two permit clauses cover the loopbacks (10/8) and the link nets
(192.0.2.0/24). They do NOT cover the customer prefix — so the route-map's implicit
deny-all drops 203.0.113.0/24 toward r2 (Maintenance Type 2 in
knowledge/corpus/noc/maintenances_that_caused_outages.md: "engineer forgets the
final permit any"). Filtering is expressed as prefix-list + route-map ONLY (no FRR
access-list), per docs/oracle_determinism_spec_v1.md.

Verified ground truth on live Batfish (batfish/allinone, 2026-06-08):
  * D1 sessions_lost = ∅            — all 4 directional iBGP sessions stay ESTABLISHED
  * D2 prefixes_lost = {(r2, 203.0.113.0/24)} — sole RIB delta, network-wide
  * D3 reachability_lost = {(r2, 203.0.113.0/24)} — r2→203.0.113.1 ACCEPTED → NO_ROUTE
  * loopbacks survive (static backup); r1, r3 reach the customer prefix unchanged.

This is the trap: a session-only view (and a model that pattern-matches
"route-map → session reset") scores it as ZERO blast radius. The damage is a
control-plane withdrawal that strands a data-plane prefix with no static fallback.
"""

from __future__ import annotations

import difflib

from netbrace.tasks.safety import baseline_ipc3 as ipc
from netbrace.topology.patches import apply_unified_diff

CHANGE_TARGET = ipc.CHANGE_TARGET  # "r1"

# Watched prefixes (D2): all four — the customer prefix that IS lost, plus the
# three loopbacks as NEGATIVE CONTROLS. A model that falsely flags a loopback as
# lost is penalized via precision (false positive); reporting is per-dimension
# P/R/F1, not a pass/fail threshold (a coarse threshold can absorb a single FP).
WATCHED_PREFIXES = list(ipc.WATCHED_PREFIXES)

# D2/D3/D7 probe target: r2 toward the customer prefix (the one that collapses).
# r1 and r3 are negative-control sources: the oracle confirms they are UNAFFECTED,
# and a model FP on them costs precision.
REACHABILITY_FLOWS = [
    ("r2", ipc.CUSTOMER_PREFIX),
    ("r1", ipc.CUSTOMER_PREFIX),
    ("r3", ipc.CUSTOMER_PREFIX),
]

# The lines added to r1's config by the change, in order, anchored after the
# `ip route ...` block (before `router bgp`) for the policy objects, and inside
# the address-family for the neighbor attachment. We build the post text by exact
# string insertion against the frozen baseline so the diff always round-trips.
_POLICY_BLOCK = (
    "ip prefix-list CLEANUP_OUT seq 5 permit 10.0.0.0/8 le 32\n"
    "ip prefix-list CLEANUP_OUT seq 10 permit 192.0.2.0/24 le 30\n"
    "route-map TO_R2_OUT permit 10\n"
    " match ip address prefix-list CLEANUP_OUT\n"
    "!\n"
)
_POLICY_ANCHOR = "ip route 10.0.0.3/32 192.0.2.6\n!\n"
_NEIGHBOR_LINE = "  neighbor 10.0.0.2 route-map TO_R2_OUT out\n"
_NEIGHBOR_ANCHOR = "  neighbor 10.0.0.2 next-hop-self\n"


def baseline_configs() -> dict[str, str]:
    """The (frozen) ipc3 baseline — reused verbatim."""
    return ipc.baseline_configs()


def _post_r1_config() -> str:
    """r1 with the outbound CLEANUP prefix-list + route-map attached toward r2."""
    before = ipc.baseline_configs()["r1"]
    if _POLICY_ANCHOR not in before or _NEIGHBOR_ANCHOR not in before:
        raise RuntimeError("ipc3 baseline r1 changed; re-verify scenario_ipc anchors")
    after = before.replace(_POLICY_ANCHOR, _POLICY_ANCHOR + _POLICY_BLOCK, 1)
    after = after.replace(_NEIGHBOR_ANCHOR, _NEIGHBOR_ANCHOR + _NEIGHBOR_LINE, 1)
    return after


def change_patch() -> str:
    """Unified diff on r1 adding the outbound filter. Guaranteed to round-trip."""
    before = ipc.baseline_configs()["r1"]
    after = _post_r1_config()
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="r1.conf", tofile="r1.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError("ipc change patch does not round-trip")
    return patch
