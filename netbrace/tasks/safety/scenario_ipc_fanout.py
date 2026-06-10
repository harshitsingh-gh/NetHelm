"""S-IPC-02 — Class 1 mechanism #3: all-clients withdrawal (multi-node blast).

A DISTINCT blast STRUCTURE from the flagship S-IPC-01 (not a clone): instead of
one client losing the prefix, the same "cleanup" outbound filter is attached to r1
toward THREE leaf clients (r2, r3, r4) at once, so the customer prefix is withdrawn
from every one of them. The blast radius is the SAME prefix on N=3 nodes — a
different affected-node set and D2/D3 cardinality 3, not 1.

Topology: `baseline_ipc_fanout` (RR r1 with clients r2/r3/r4 + origin r5). The
filter is NOT applied toward r5 (the origin/transit) — leaving r5 keeps the prefix
in r1's own RIB, so this is purely advertisement-suppression toward the three leaf
clients.

The change (on r1): the CLEANUP_OUT prefix-list + TO_CLIENTS_OUT route-map (permits
10/8 + 192.0.2.0/24, implicit-denies the customer prefix) attached outbound toward
r2, r3 AND r4. Filtering is prefix-list + route-map ONLY (no FRR access-list), per
docs/oracle_determinism_spec_v1.md.

Expected ground truth (static, deterministic; confirm via the oracle):
  * D1 sessions_lost = ∅            — all sessions stay ESTABLISHED (the trap)
  * D2 prefixes_lost = {(r2,/24), (r3,/24), (r4,/24)} — multi-node blast
  * D3 reachability_lost = {(r2→/24), (r3→/24), (r4→/24)}
  * r1 and r5 keep the prefix (negative controls); loopbacks survive (static backup).

Grounding: the "implicit deny-all" maintenance trap (Maintenance Type 2) applied
peer-group-wide — the realistic case where a "cleanup" template is pushed to all
clients at once. NOT the Rogers Jul-2022 mechanism (that was a filter removal →
route flood → overload; it grounds the scale class).
"""

from __future__ import annotations

import difflib

from netbrace.tasks.safety import baseline_ipc_fanout as fan
from netbrace.topology.patches import apply_unified_diff

CHANGE_TARGET = fan.CHANGE_TARGET  # "r1"

CUSTOMER_PREFIX = fan.CUSTOMER_PREFIX

# D2: the customer prefix (lost on the 3 leaf clients) + all loopbacks (negative
# controls — must NOT be collateral damage; a false positive costs precision).
WATCHED_PREFIXES = list(fan.WATCHED_PREFIXES)

# D2/D3 probes. r2/r3/r4 lose the prefix; r1/r5 are negative-control sources that
# must stay reachable (the prefix survives in r1's RIB because r5 is unfiltered).
REACHABILITY_FLOWS = [
    ("r2", CUSTOMER_PREFIX),
    ("r3", CUSTOMER_PREFIX),
    ("r4", CUSTOMER_PREFIX),
    ("r1", CUSTOMER_PREFIX),
    ("r5", CUSTOMER_PREFIX),
]

# Policy objects inserted after r1's static-route block (before `router bgp`).
_POLICY_BLOCK = (
    "ip prefix-list CLEANUP_OUT seq 5 permit 10.0.0.0/8 le 32\n"
    "ip prefix-list CLEANUP_OUT seq 10 permit 192.0.2.0/24 le 30\n"
    "route-map TO_CLIENTS_OUT permit 10\n"
    " match ip address prefix-list CLEANUP_OUT\n"
    "!\n"
)
_POLICY_ANCHOR = "ip route 10.0.0.5/32 192.0.2.14\n!\n"

# Outbound route-map attachment toward the three leaf clients, inserted inside the
# address-family after r4's next-hop-self line (before r5's clauses).
_NEIGHBOR_LINES = (
    "  neighbor 10.0.0.2 route-map TO_CLIENTS_OUT out\n"
    "  neighbor 10.0.0.3 route-map TO_CLIENTS_OUT out\n"
    "  neighbor 10.0.0.4 route-map TO_CLIENTS_OUT out\n"
)
_NEIGHBOR_ANCHOR = "  neighbor 10.0.0.4 next-hop-self\n"


def baseline_configs() -> dict[str, str]:
    """The (frozen) ipc_fanout baseline — reused verbatim."""
    return fan.baseline_configs()


def _post_r1_config() -> str:
    """r1 with the outbound CLEANUP route-map attached toward r2/r3/r4."""
    before = fan.baseline_configs()["r1"]
    if _POLICY_ANCHOR not in before or _NEIGHBOR_ANCHOR not in before:
        raise RuntimeError("ipc_fanout baseline r1 changed; re-verify scenario anchors")
    after = before.replace(_POLICY_ANCHOR, _POLICY_ANCHOR + _POLICY_BLOCK, 1)
    after = after.replace(_NEIGHBOR_ANCHOR, _NEIGHBOR_ANCHOR + _NEIGHBOR_LINES, 1)
    return after


def change_patch() -> str:
    """Unified diff on r1 adding the outbound filter toward 3 clients (round-trips)."""
    before = fan.baseline_configs()["r1"]
    after = _post_r1_config()
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="r1.conf", tofile="r1.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError("ipc_fanout change patch does not round-trip")
    return patch
