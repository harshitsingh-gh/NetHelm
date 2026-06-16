"""leak_ms — Class 2: more-specific route leak -> longest-prefix-match blackhole.

The flagship demonstration that the naive blast signals are BLIND. Reuses the
verified `leak_ms` eBGP baseline (victim AS65001 -- transit AS65002 -- leaker
AS65003). The change is made on the LEAKER: it starts originating a more-specific
/25 of the victim's /24 (203.0.113.0/25), backed by a blackhole (null) static so
BGP can originate it but the leaker has NO real path to the victim's hosts.

Causal chain:
  1. transit now hears 203.0.113.0/25 (from leaker, AS-path 65003) IN ADDITION to
     203.0.113.0/24 (from victim, AS-path 65001). Both routes are installed -> the
     legit /24 is NOT lost from any RIB (D2 prefixes_lost = ∅; a route is ADDED).
  2. For destination 203.0.113.1 (inside both prefixes), longest-prefix-match at
     transit selects the /25 -> next-hop leaker. AS-path length is irrelevant; LPM
     wins. (Cloudflare-2019 mechanism.)
  3. At the leaker, 203.0.113.0/25 resolves to the blackhole static -> the packet
     is dropped (Batfish disposition NULL_ROUTED). transit's traffic to the victim
     space is blackholed.

Thesis property (to confirm via the oracle):
  * D1 sessions_lost = ∅   (no session changes; eBGP stays ESTABLISHED -- the trap)
  * D2 prefixes_lost = ∅   (the /24 stays in every RIB; the /25 is ADDED, not lost)
  * D7 forwarding_anomalies != ∅  (transit -> 203.0.113.1 NULL_ROUTED at leaker)
  * D3 reachability_lost != ∅     (transit -> 203.0.113.1 was DELIVERED, now dropped)

Negative controls (must NOT fire):
  * transit -> 198.51.100.1 (leaker's own legit /24): unaffected.
  * victim -> 203.0.113.1: the victim itself serves the host directly (connected),
    so it is never pulled toward the leaker.

The change is filtering-free and policy-free (a single `network` + blackhole
static), so there is no equal-cost tie to perturb the chosen path; router-ids are
pinned in the baseline. STATIC-DETERMINISTIC per docs/oracle_determinism_spec_v1.md
(class 2: score the data-plane SET via traceroute disposition; never chosen-path).

Grounding: Cloudflare global outage, Jun-24-2019 (knowledge/corpus/noc/
cloudflare_bgp_leak_jun2019.md) -- Noction BGP Optimizer re-announced more-specific
/24s of victim space, longest-prefix-match pulled traffic, blackhole/congestion.
Also Telekom-Malaysia-2015 (telekom_malaysia_route_leak_2015.md): "BGP-level
metrics (session count, prefix count) give no signal."
"""

from __future__ import annotations

import difflib

from netbrace.tasks.safety import baseline_leak_ms as base
from netbrace.topology.patches import apply_unified_diff

CHANGE_TARGET = base.CHANGE_TARGET  # "leaker"

VICTIM_PREFIX = base.VICTIM_PREFIX
VICTIM_IP = base.VICTIM_IP
LEAK_PREFIX = base.LEAK_PREFIX

WATCHED_PREFIXES = list(base.WATCHED_PREFIXES)

# D7 forwarding probe + D3 reachability probe: transit toward the victim HOST (the
# flow that gets blackholed) and toward the leaker's own legit host (neg control).
# The victim itself is a neg control source (it serves the host connected).
#
# Probes carry the HOST /32 (203.0.113.1, 198.51.100.1), NOT the bare /24. The
# oracle traceroutes toward dst.split("/")[0]; the /24 network address (.0) is not
# a deliverable host in Batfish's connected-subnet model, so a /24-form probe would
# spuriously blackhole at the victim too (the .0 address has no connected accept).
# Pinning the real host IP makes the victim a clean negative control: victim->.1 is
# DELIVERED connected in both snapshots, while transit->.1 is pulled by LPM to the
# /25 and null-routed at the leaker.
VICTIM_HOST = base.VICTIM_IP + "/32"      # 203.0.113.1/32 (inside both /24 and /25)
LEAKER_HOST = base.LEAKER_IP + "/32"      # 198.51.100.1/32 (leaker's real host)
FORWARDING_FLOWS = [
    ("transit", VICTIM_HOST),   # blackholed by the leak (the blast)
    ("transit", LEAKER_HOST),   # neg control: leaker's real prefix, fine
    ("victim", VICTIM_HOST),    # neg control: victim serves it connected
]
REACHABILITY_FLOWS = list(FORWARDING_FLOWS)

# Blackhole static so BGP can originate the /25 while the leaker has NO real path
# to the victim's hosts (the "advertise but discard" leak). Inserted before the
# `router bgp` block; the `network` statement is added inside the address-family.
_STATIC_LINE = "ip route 203.0.113.0/25 blackhole\n"
_STATIC_ANCHOR = " ip address 198.51.100.1/24\n!\n"

_NETWORK_LINE = "  network 203.0.113.0/25\n"
_NETWORK_ANCHOR = "  network 198.51.100.0/24\n"


def baseline_configs() -> dict[str, str]:
    """The (frozen) leak_ms baseline — reused verbatim."""
    return base.baseline_configs()


def _post_leaker_config() -> str:
    """leaker with the more-specific /25 originated (blackhole static + network)."""
    before = base.baseline_configs()["leaker"]
    if _STATIC_ANCHOR not in before or _NETWORK_ANCHOR not in before:
        raise RuntimeError("leak_ms baseline leaker changed; re-verify scenario anchors")
    after = before.replace(_STATIC_ANCHOR, _STATIC_ANCHOR + _STATIC_LINE, 1)
    after = after.replace(_NETWORK_ANCHOR, _NETWORK_ANCHOR + _NETWORK_LINE, 1)
    return after


def change_patch() -> str:
    """Unified diff on the leaker originating the more-specific /25 (round-trips)."""
    before = base.baseline_configs()["leaker"]
    after = _post_leaker_config()
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="leaker.conf", tofile="leaker.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError("leak_ms change patch does not round-trip")
    return patch
