"""ipc_aggregate — Class 1 mechanism #4: aggregate survives, more-specifics withdrawn.

A DISTINCT blast STRUCTURE from S-IPC-01 (flagship), ipc_static, and S-IPC-02
(fanout). An aggregation router (r3) advertises a /24 supernet AND two more-specific
/25 prefixes that pin traffic. A downstream "cleanup" outbound route-map on the RR
(r1) toward the client (r2) permits the /24 aggregate (plus loopbacks + link nets)
but implicit-denies the two /25 more-specifics. The result:

  * the AGGREGATE /24 survives on r2 (still in r2's RIB), AND
  * the two /25 MORE-SPECIFICS are withdrawn from r2's RIB.

The interesting trap: D2 fires on the /25s, but D3 reachability to an address that
falls inside a /25 may be SILENT — because the surviving /24 aggregate still covers
it. "Looks fine because the /24 is still there." Whether D3/D4 actually fire is an
EMPIRICAL question answered by the oracle; this module declares only the dimensions
the oracle confirms (see the verification block).

Topology: `baseline_ipc_aggregate` (RR r1, client r2, aggregation router/origin r3).
The filter is applied on r1 toward r2 ONLY. r3 keeps originating all three prefixes,
and r1 keeps all three in its own RIB (negative controls) — this is purely an
advertisement-suppression of the /25s toward the single client r2.

The change (on r1, toward r2 only): a CLEANUP_OUT prefix-list that permits the /24
aggregate EXACTLY (no `le`, so the /25s do NOT match), plus loopbacks (10/8) and
link nets (192.0.2.0/24), attached via the TO_R2_OUT route-map (implicit deny-all
drops the two /25s). Filtering is prefix-list + route-map ONLY (no FRR access-list),
per docs/oracle_determinism_spec_v1.md (Class 1: STATIC-DETERMINISTIC).

VERIFIED ground truth on live Batfish (batfish/allinone, 127.0.0.1:9997),
2026-06-08 — oracle run TWICE, byte-identical (deterministic by construction):
  * D1 sessions_lost = ∅            — 4/4 iBGP sessions stay ESTABLISHED (the trap)
  * D2 prefixes_lost = {(r2, 203.0.113.0/25), (r2, 203.0.113.128/25)} — the SOLE
    delta network-wide. r2 RIB pre = {/24, /25-low, /25-high via ibgp nh 10.0.0.3};
    r2 RIB post = {/24 only}. The two /25 more-specifics are withdrawn.
  * D3 reachability_lost = ∅        — SILENT (the trap). r2 → 203.0.113.10 (inside
    the low /25) and r2 → 203.0.113.200 (inside the high /25) are BOTH
    DELIVERED_TO_SUBNET in pre AND post — the surviving /24 aggregate still resolves
    them. "Looks fine because the /24 is still there."
  * D4–D9 = ∅. Aggregate /24 and loopbacks survive on r2 (negative controls hold);
    r1 and r3 keep all three prefixes (negative-control sources unchanged).
The ONLY declared/firing dimension is D2 (prefixes) — declaring D3 would be a false
claim the oracle refutes.

Grounding: aggregation routers routinely advertise a covering aggregate AND pin
more-specifics for multihoming / inbound traffic engineering (RFC 4632 §5.3 / BGP
operational practice). A "cleanup" template that permits the aggregate but forgets
the more-specifics silently de-pins TE/multihoming routes while coarse reachability
still works via the supernet — a real and pernicious de-aggregation trap distinct
from the implicit-deny-all collapse (where there is no covering aggregate).
"""

from __future__ import annotations

import difflib

from netbrace.tasks.safety import baseline_ipc_aggregate as agg
from netbrace.topology.patches import apply_unified_diff

CHANGE_TARGET = agg.CHANGE_TARGET  # "r1"

AGGREGATE_PREFIX = agg.AGGREGATE_PREFIX
SPECIFIC_LOW = agg.SPECIFIC_LOW
SPECIFIC_HIGH = agg.SPECIFIC_HIGH

# D2: aggregate + both /25s + all loopbacks (loopbacks + aggregate = negative
# controls; only the /25s should be lost). A false positive on the aggregate or a
# loopback costs precision.
WATCHED_PREFIXES = list(agg.WATCHED_PREFIXES)

# D2/D3 probes. r2 toward an IP inside the low /25, an IP inside the high /25, and
# an IP that exercises the aggregate. r1 and r3 are negative-control sources (they
# keep all three prefixes). We probe ALL of these so the oracle tells us, per flow,
# exactly which reachability is lost and which survives via the /24.
REACHABILITY_FLOWS = [
    ("r2", agg.IP_IN_LOW),
    ("r2", agg.IP_IN_HIGH),
    ("r2", agg.IP_IN_AGG),
    ("r1", agg.IP_IN_LOW),
    ("r3", agg.IP_IN_LOW),
]

# Policy objects inserted after r1's static-route block (before `router bgp`).
# CLEANUP_OUT permits the /24 aggregate EXACTLY (seq 5, no `le` => /25s do not
# match), loopbacks (seq 10), and link nets (seq 15). The route-map's implicit
# deny-all then drops the two /25 more-specifics toward r2.
_POLICY_BLOCK = (
    "ip prefix-list CLEANUP_OUT seq 5 permit 203.0.113.0/24\n"
    "ip prefix-list CLEANUP_OUT seq 10 permit 10.0.0.0/8 le 32\n"
    "ip prefix-list CLEANUP_OUT seq 15 permit 192.0.2.0/24 le 30\n"
    "route-map TO_R2_OUT permit 10\n"
    " match ip address prefix-list CLEANUP_OUT\n"
    "!\n"
)
_POLICY_ANCHOR = "ip route 10.0.0.3/32 192.0.2.6\n!\n"

_NEIGHBOR_LINE = "  neighbor 10.0.0.2 route-map TO_R2_OUT out\n"
_NEIGHBOR_ANCHOR = "  neighbor 10.0.0.2 next-hop-self\n"


def baseline_configs() -> dict[str, str]:
    """The (frozen) ipc_aggregate baseline — reused verbatim."""
    return agg.baseline_configs()


def _post_r1_config() -> str:
    """r1 with the outbound CLEANUP route-map (permit /24, deny /25s) toward r2."""
    before = agg.baseline_configs()["r1"]
    if _POLICY_ANCHOR not in before or _NEIGHBOR_ANCHOR not in before:
        raise RuntimeError("ipc_aggregate baseline r1 changed; re-verify scenario anchors")
    after = before.replace(_POLICY_ANCHOR, _POLICY_ANCHOR + _POLICY_BLOCK, 1)
    after = after.replace(_NEIGHBOR_ANCHOR, _NEIGHBOR_ANCHOR + _NEIGHBOR_LINE, 1)
    return after


def change_patch() -> str:
    """Unified diff on r1 adding the outbound aggregate-permit filter (round-trips)."""
    before = agg.baseline_configs()["r1"]
    after = _post_r1_config()
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="r1.conf", tofile="r1.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError("ipc_aggregate change patch does not round-trip")
    return patch
