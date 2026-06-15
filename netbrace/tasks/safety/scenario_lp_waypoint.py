"""lp_waypoint — Class 5: LOCAL_PREF-driven waypoint (D4) shift; the empty-blast trap.

⚠️ LEGACY / NON-CANONICAL (audit 2026-06-15 finding #14): this registered scenario
reuses the DEPRECATED static-crutch `baseline_lp_waypoint` (see its header). The
CANONICAL, PUBLISHED LOCAL_PREF-waypoint path the model sweep scores is the
idiomatic all-eBGP `generator_lp.generate_lp_suite`. This scenario is kept only for
registry / determinism-gate continuity; do not treat it as the published base.

Reuses the verified `lp_waypoint` BGP baseline (internal AS65000 src/way/alt +
external customer AS65004 dst, dual-homed via way and alt). Pre-state: an inbound
eBGP route-map on `way` sets local-preference 200 on all routes learned from dst
(the route-map has no match clause, so it also covers dst's loopback — this keeps
best-path strict and avoids a tie) while the matching route-map on `alt` sets 100,
so src's BGP best path to 203.0.113.0/24 is via `way` — src->dst transits the
inspection node.

The change is made on `alt`: it RAISES the inbound local-preference from 100 to
300 (a one-line `set local-preference` edit in alt's FROM_DST_IN route-map). Now
at src the alt path (LP=300) strictly beats the way path (LP=200), so the best
path flips to alt and traffic STOPS transiting `way`.

Causal chain:
  1. alt re-advertises 203.0.113.0/24 into iBGP with LOCAL_PREF=300 (was 100);
     way still advertises it with LOCAL_PREF=200.
  2. At src, BGP best-path selects on LOCAL_PREF first (RFC 4271 §9.1.1 step 1;
     "weight" is Cisco-proprietary and not modeled here): 300 > 200,
     so src installs the ALT path (next-hop alt's loopback) instead of the WAY
     path. STRICT gap -> single best path, no ECMP, deterministic.
  3. src's forwarding to 203.0.113.1 now egresses via alt -> dst, BYPASSING way.
     The route is NOT lost (D2=∅) and the host is STILL reachable (D3=∅) — it just
     no longer transits the inspection node (D4 fires).

Thesis property (to confirm via the oracle) — THE TRAP:
  * D1 sessions_lost = ∅   (a LOCAL_PREF/attribute change does NOT reset a BGP
    session: RFC 4271 §8 the BGP FSM leaves Established only on NOTIFICATION,
    hold-timer expiry, or TCP teardown — never on a policy/attribute change. The
    documented LLM failure is predicting a session drop here.)
  * D2 prefixes_lost = ∅   (203.0.113.0/24 stays in every RIB; only its LOCAL_PREF
    and chosen next-hop change)
  * D3 reachability_lost = ∅  (src still reaches 203.0.113.1, via alt)
  * D4 waypoint_violations != ∅  (src->203.0.113.1 no longer transits `way`)

Negative controls (must NOT fire): all loopbacks stay in every RIB; sessions stay
ESTABLISHED; reachability to 203.0.113.1 is preserved.

Determinism per oracle_determinism_spec_v1.md class 5: STRICT preference both pre
(200 vs 100) and post (300 vs 200) -> exactly one best path at src in each
snapshot, no equal-cost tie, no ECMP (maximum-paths default 1). Router-ids pinned.
D4 is scored as the all-traces-transit invariant by ExtendedOracle._waypoint_diff;
never chosen-path identity.

Grounding: knowledge/corpus/noc/network_change_management.md — "Modify LOCAL_PREF:
Traffic shift; no session/prefix loss" (risk table) and the explicit observed LLM
failure "Predicting session loss for LOCAL_PREF changes (sessions don't drop on LP
changes)". Mechanism class: BGP best-path LOCAL_PREF tie-break (RFC 4271 §9.1.1).
Waypoint/inspection-intent framing follows NetConfEval waypoint policy and Forward
Networks intent checks.
"""

from __future__ import annotations

import difflib

from netbrace.tasks.safety import baseline_lp_waypoint as base
from netbrace.topology.patches import apply_unified_diff

CHANGE_TARGET = base.CHANGE_TARGET  # "alt"

CUSTOMER_PREFIX = base.CUSTOMER_PREFIX
CUSTOMER_IP = base.CUSTOMER_IP

WATCHED_PREFIXES = list(base.WATCHED_PREFIXES)
WAYPOINT_INTENTS = list(base.WAYPOINT_INTENTS)
REACHABILITY_FLOWS = list(base.REACHABILITY_FLOWS)

# The one-line attribute change: raise alt's inbound local-preference 100 -> 300,
# flipping src's best path from the way egress to the alt egress.
_LP_BEFORE = " set local-preference 100\n"
_LP_AFTER = " set local-preference 300\n"


def baseline_configs() -> dict[str, str]:
    """The (frozen) lp_waypoint baseline — reused verbatim."""
    return base.baseline_configs()


def _post_alt_config() -> str:
    """alt with the inbound local-preference raised from 100 to 300."""
    before = base.baseline_configs()["alt"]
    if _LP_BEFORE not in before:
        raise RuntimeError("lp_waypoint baseline alt changed; re-verify scenario anchor")
    return before.replace(_LP_BEFORE, _LP_AFTER, 1)


def change_patch() -> str:
    """Unified diff on alt raising the inbound LOCAL_PREF 100->300 (round-trips)."""
    before = base.baseline_configs()["alt"]
    after = _post_alt_config()
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="alt.conf", tofile="alt.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError("lp_waypoint change patch does not round-trip")
    return patch
