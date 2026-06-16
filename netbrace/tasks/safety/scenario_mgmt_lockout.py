"""mgmt_lockout — management-plane / OOB lockout: the change breaks the tools
needed to fix it, graded against a stated management-reachability INTENT (D10).

SAME MECHANISM AS `ipc`, DELIBERATELY POINTED AT A MANAGEMENT INTENT.
This scenario reuses the EXACT Class-1 mechanism of the `ipc` flagship: an outbound
iBGP prefix-list "cleanup" whose implicit deny-all silently withdraws prefixes from
a downstream peer while every BGP session stays ESTABLISHED. It is NOT a new
mechanism. Its distinct, graded contribution is the D10 INTENT dimension: the
withdrawn prefixes are the managed devices' MANAGEMENT subnets, and the scenario is
scored against a stated "the NOC jump-host MUST retain management reachability to
every device" intent. A model that lists the reachability loss but does NOT
recognize it as a violation of that management-reachability intent is incomplete
(it misses D10). This is the same deliberate-sibling design as `ipc_static` (whose
value is the D9 control-plane dimension): a familiar mechanism graded on a new
surface, not a new failure class. (knowledge/corpus/noc/mgmt_plane_lockout.md.)

The change (a routine-looking "advertisement cleanup" on the aggregation router
`core` toward the NOC jump-host `jump`) keeps advertising the customer/data prefix
and the backbone infra prefixes, but its implicit deny-all stops advertising BOTH
managed devices' MANAGEMENT subnets 172.16.0.0/24 (edge) and 172.16.1.0/24 (edge2).
Because the jump-host's only path to each device's management address is that BGP
advertisement (in-band OOB — no static backup), the change removes the NOC's
ability to reach either device's mgmt-IP. Yet:
  * D1 sessions_lost = ∅  (loopbacks have static backup; iBGP stays ESTABLISHED)
  * D2 prefixes_lost = ∅  (the WATCHED set — customer prefix 203.0.113.0/24 + all
    four loopbacks — is provably untouched; D2=∅ is HONEST, not hidden: the mgmt
    prefixes are simply scored on D3/D10 where they fire, and a false-positive on a
    watched survivor costs D2 precision)
  * D3 reachability_lost = {(jump, 172.16.0.1), (jump, 172.16.1.1)}  (jump -> each
    device mgmt-IP collapses — >= 2 management losses, not a single 1-bit key)
  * D10 intent_violations = {reachability jump->172.16.0.0/24,
    reachability jump->172.16.1.0/24}  (the stated management-reachability intent
    held pre and is violated post for BOTH devices)

The trap: a model/operator reasoning "no customer prefixes affected, no sessions
dropped -> safe" is catastrophically wrong, and even a model that notices the
reachability loss but fails to grade it as a management-INTENT violation is
incomplete — in every grounding incident (Facebook Oct-2021, AWS us-east-1
Dec-2021, Rogers Jul-2022, Cloudflare Jun-2022) the management-plane dependency is
exactly what turned a quick rollback into a multi-hour, physical-access recovery.

Mechanism (DELIBERATELY a routing/policy severance, NOT an interface ACL): Batfish
does not model FRR access-lists as packet filters, so per
docs/oracle_determinism_spec_v1.md the management path is cut at the CONTROL plane
(stop advertising the mgmt prefixes toward the jump-host) — fully FRR-gradeable via
traceroutes that go ACCEPTED -> NO_ROUTE at `jump`.

The change (on `core`, toward `jump` only):
  + ip prefix-list MGMT_CLEANUP_OUT seq 5  permit 10.0.0.0/8 le 32
  + ip prefix-list MGMT_CLEANUP_OUT seq 10 permit 192.0.2.0/24 le 30
  + ip prefix-list MGMT_CLEANUP_OUT seq 15 permit 203.0.113.0/24
  + route-map TO_JUMP_OUT permit 10
  +  match ip address prefix-list MGMT_CLEANUP_OUT
  + neighbor 10.0.0.1 route-map TO_JUMP_OUT out

The three permit clauses cover the loopbacks (10/8), the link nets (192.0.2.0/24)
and the customer prefix (203.0.113.0/24). They do NOT cover EITHER management
prefix (172.16.0.0/24, 172.16.1.0/24) — so the route-map's implicit deny-all drops
both toward `jump`. Filtering is prefix-list + route-map ONLY (no FRR access-list),
per the determinism spec.

Verified ground truth is computed live by scripts/run_extended_scenario.py
--scenario mgmt_lockout.

FOLLOW-UP (not built; noted per the review): a true-negative "has-OOB-backup"
sibling — the same cleanup change but with a real out-of-band static route to each
mgmt prefix, so management reachability and the D10 intent SURVIVE (D3=∅, D10=∅).
That would discriminate "recognized OOB backup matters" from "always-fires." Left
as a follow-up to keep this fix bounded.
"""

from __future__ import annotations

import difflib

from netbrace.tasks.safety import baseline_mgmt_lockout as mgmt
from netbrace.topology.patches import apply_unified_diff

CHANGE_TARGET = mgmt.CHANGE_TARGET  # "core"

# Watched prefixes (D2): the customer prefix + the four loopbacks. ALL survive the
# change, so D2 = ∅ is the ground truth — and it is HONEST: every watched prefix is
# a NEGATIVE CONTROL that is watched-and-correctly-NOT-lost, so a model that falsely
# flags the customer prefix or a loopback as lost is penalized via D2 precision. The
# management prefixes are NOT hidden from this set to fake the trap; they are simply
# scored on D3 (reachability) + D10 (intent), the dimensions where the class fires.
WATCHED_PREFIXES = list(mgmt.WATCHED_PREFIXES)

# D3 reachability probes. THE scored losses are the first TWO flows (jump -> each
# device mgmt-IP); the rest are NEGATIVE CONTROLS that MUST stay reachable
# post-change:
#   * (jump, customer-IP)   — the NOC still reaches the customer/data prefix
#   * (jump, edge-loopback) — backbone reachability to a device loopback survives
#   * (core, edge-mgmt-IP)  — the mgmt prefix is only filtered TOWARD jump; core (and
#                             anyone not behind that route-map) still reaches it
# A model that flags any negative-control flow as lost is penalized via D3 precision.
REACHABILITY_FLOWS = [
    ("jump", mgmt.MGMT_IPS["edge"]),    # <-- management path #1 that breaks (D3)
    ("jump", mgmt.MGMT_IPS["edge2"]),   # <-- management path #2 that breaks (D3)
    ("jump", mgmt.CUSTOMER_IP),         # negative control: data plane intact
    ("jump", mgmt.LOOPBACK_IP["edge"] + "/32"),  # negative control: backbone intact
    ("core", mgmt.MGMT_IPS["edge"]),    # negative control: filter is jump-only
]

# D10 intent invariants (ORACLE-SIDE GROUND TRUTH — NEVER shown to the model). The
# model reads ONLY the intents_text prose ("the NOC jump-host MUST retain management
# reachability to every device") and must DERIVE the violation from the diff +
# configs. The oracle evaluates each invariant PRE and POST and emits an
# IntentViolation when management reachability HELD pre but is VIOLATED post.
# Defined in scenarios.py (needs the IntentInvariant type); the prefixes/IPs live
# here so the baseline stays the single source of truth.
INTENT_MGMT_TARGETS = [
    ("jump", mgmt.MGMT_PREFIXES["edge"]),
    ("jump", mgmt.MGMT_PREFIXES["edge2"]),
]

# The lines added to core's config by the change. Policy objects are anchored after
# the `ip route ...` block (before `router bgp`); the neighbor attachment is anchored
# inside the address-family. Built by exact string insertion against the frozen
# baseline so the unified diff always round-trips.
_POLICY_BLOCK = (
    "ip prefix-list MGMT_CLEANUP_OUT seq 5 permit 10.0.0.0/8 le 32\n"
    "ip prefix-list MGMT_CLEANUP_OUT seq 10 permit 192.0.2.0/24 le 30\n"
    "ip prefix-list MGMT_CLEANUP_OUT seq 15 permit 203.0.113.0/24\n"
    "route-map TO_JUMP_OUT permit 10\n"
    " match ip address prefix-list MGMT_CLEANUP_OUT\n"
    "!\n"
)
_POLICY_ANCHOR = "ip route 10.0.0.4/32 192.0.2.10\n!\n"
_NEIGHBOR_LINE = "  neighbor 10.0.0.1 route-map TO_JUMP_OUT out\n"
_NEIGHBOR_ANCHOR = "  neighbor 10.0.0.1 next-hop-self\n"


def baseline_configs() -> dict[str, str]:
    """The (frozen) mgmt_lockout baseline — reused verbatim."""
    return mgmt.baseline_configs()


def _post_core_config() -> str:
    """core with the outbound MGMT_CLEANUP route-map attached toward jump."""
    before = mgmt.baseline_configs()["core"]
    if _POLICY_ANCHOR not in before or _NEIGHBOR_ANCHOR not in before:
        raise RuntimeError("mgmt_lockout baseline core changed; re-verify anchors")
    after = before.replace(_POLICY_ANCHOR, _POLICY_ANCHOR + _POLICY_BLOCK, 1)
    after = after.replace(_NEIGHBOR_ANCHOR, _NEIGHBOR_ANCHOR + _NEIGHBOR_LINE, 1)
    return after


def change_patch() -> str:
    """Unified diff on core adding the outbound filter. Guaranteed to round-trip."""
    before = mgmt.baseline_configs()["core"]
    after = _post_core_config()
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="core.conf", tofile="core.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError("mgmt_lockout change patch does not round-trip")
    return patch
