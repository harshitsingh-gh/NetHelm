"""scale_deagg — Class 8: de-aggregation / table-flood -> FIB resource overflow.

The D8 scale class, grounded in Rogers Jul-2022: a maintenance change REMOVES the
upstream summarization (a filter/summary removal), so the more-specifics that the
summary was hiding now propagate, multiplying the routes the downstream edge must
install past its FIB budget. Re-cast as a clean, Batfish-static experiment on the
verified ``scale_deagg`` eBGP pair (upstream AS65010 -- edge AS65020).

The change is made on the UPSTREAM: it stops originating the single covering
summary ``100.64.0.0/16`` and instead originates the ``DEAGG_COUNT`` more-specific
/24s inside that block (each backed by its own discard static so BGP can source
it). The edge installs all of them.

Causal chain (the model must DERIVE this from the diff + configs + the budget):
  1. Pre-change the edge hears ONE route for the block (100.64.0.0/16), so its
     installed-route count is small -- comfortably under its FIB budget.
  2. Post-change the edge hears DEAGG_COUNT separate /24s instead of the one /16,
     so its installed-route count jumps by ~DEAGG_COUNT routes.
  3. With the stated edge FIB budget of EDGE_FIB_BUDGET routes, the post count
     CROSSES the budget -> a D8 ScaleViolation fires on the edge (resource=fib).

Thesis property (the "loss view is blind to the real blast" trap, on the scale
axis), to confirm via the oracle:
  * D1 sessions_lost = ∅   (the eBGP session stays ESTABLISHED -- no session churn)
  * D2 prefixes_lost = {(edge, 100.64.0.0/16), (upstream, 100.64.0.0/16)}  (the /16
    supernet row leaves BOTH RIBs -- upstream stops originating it, the edge stops
    learning it -- but this is a benign supernet->specifics SWAP: the constituent
    /24s that replace it are ADDED, not lost, and cover the same space)
  * D3 reachability_lost = ∅  (the /24s cover the same destination space the /16
    did, so NO destination is lost -- a connectivity review sees nothing wrong)
  * D8 scale_violations != ∅  (the edge's installed-route count > its FIB budget)

The honest trap: the ONLY loss signal is a benign-looking supernet->specifics swap
(D2 fires on the /16, D3 stays ∅), while the REAL blast -- the D8 FIB overflow that
the de-aggregation causes -- is invisible to every loss/connectivity view. This
mirrors leak_ms's "naive blast signals miss the real harm" property, now on the
scale axis.

Negative control (must NOT fire):
  * the UPSTREAM has no declared budget, so no ScaleViolation is emitted for it
    even though its own table grows (it is the originator, not the victim). Only
    the edge carries a budget -> only the edge can overflow.

Modeling limits (honest):
  * The oracle scores the count-vs-limit THRESHOLD only (does the edge's
    installed-route count cross its budget?), NOT which specific routes a TCAM
    would evict on overflow -- eviction is platform/runtime-dependent and Batfish
    cannot model it (docs/oracle_determinism_spec_v1.md, scale class).
  * ``_installed_route_count`` is the main-RIB row count (connected + static + BGP,
    single VRF) -- an UPPER-BOUND proxy for FIB/TCAM pressure, NOT the exact
    longest-prefix-match-entry count the Trident grounding refers to. It is valid
    only as an fib/rib proxy; a label (MPLS) or acl_tcam ceiling would need a
    vendor/MPLS model and is NOT computed from this count (see _scale_violations).
  * The FIB budget (EDGE_FIB_BUDGET) is a lab-scaled stand-in for a real datasheet
    ceiling (Trident-2 ~= 64-72k IPv4 LPM entries), deliberately small so the
    overflow is observable in a 2-node lab. The violation is STRUCTURAL: the
    de-aggregation adds ~DEAGG_COUNT routes regardless of the exact budget value;
    see EDGE_FIB_BUDGET for the audited threshold sweep.
The route count is deterministic and the limit is a fixed spec annotation, so the
overflow FLAG is fully static-deterministic. Verify >=2x byte-identical.

Grounding: Rogers Jul-2022 (knowledge/corpus/noc/rogers_canada_outage_jul2022.md:
filter removal -> route flood -> core capacity exceeded -> crash; the fix was an
overload/max-routes limit) + merchant-silicon FIB ceilings (knowledge/corpus/dc/
hyperscaler_dc_failure_modes.md §3, Trident-2 ~64-72k IPv4; de-aggregation listed
as a trigger).
"""

from __future__ import annotations

import difflib

from netbrace.tasks.safety import baseline_scale_deagg as base
from netbrace.topology.patches import apply_unified_diff

CHANGE_TARGET = base.CHANGE_TARGET  # "upstream"

BLOCK_PREFIX = base.BLOCK_PREFIX
DEAGG_COUNT = base.DEAGG_COUNT

WATCHED_PREFIXES = list(base.WATCHED_PREFIXES)

# The edge's modeled FIB budget (the D8 spec annotation). Chosen so the BASELINE
# edge route count is comfortably UNDER it and the post-change (de-aggregated)
# count is OVER it. The baseline edge installs only a handful of routes (its own
# loopback + connected link nets + the single /16 it hears). With DEAGG_COUNT (24)
# more-specifics added in place of the one /16, the post count is ~23 routes higher.
#
# Threshold sweep (audited so the budget is not cherry-picked — verified live, see
# tests/unit/test_scale_deagg_scenario.py::test_budget_sweep_brackets_observed_counts):
#   * baseline edge installed-route count  = BASELINE_EDGE_COUNT  (4)
#   * post-change edge installed-route count = POST_EDGE_COUNT     (27)
#   * ANY budget in [BASELINE_EDGE_COUNT, POST_EDGE_COUNT) makes the violation fire
#     post-change and stay silent on the baseline. 20 sits cleanly in that band.
# The violation is STRUCTURAL: de-agg swaps the one /16 for DEAGG_COUNT (24) /24s,
# a net +23 routes, so the result is robust to the precise placement in the band.
EDGE_FIB_BUDGET = 20

# Observed installed-route counts (live Batfish, frr 10.6.1, single default VRF),
# pinned here so the budget placement is auditable from source. Confirmed by
# scripts/run_extended_scenario.py --scenario scale_deagg (2026-06-08). The edge's
# baseline main-RIB rows: its own lo /32, the connected link /30 (+ its /32 local),
# and the one /16 it learns over BGP = 4. Post-change the /16 is replaced by the 24
# /24s it learns = 27 (baseline 4 - 1 /16 + 24 /24s = 27).
BASELINE_EDGE_COUNT = 4
POST_EDGE_COUNT = 27

# The D8 budget annotation passed to the Scenario.resource_limits. ONLY the edge
# carries a budget (it is the overflow victim); the upstream is unconstrained.
RESOURCE_LIMITS = {"edge": {"fib": EDGE_FIB_BUDGET}}

# The /24 more-specifics the de-aggregation originates (in place of the /16).
_DEAGG_PREFIXES = [f"100.64.{i}.0/24" for i in range(DEAGG_COUNT)]

# The single covering summary lines we REMOVE from the baseline upstream.
_SUMMARY_NETWORK = "  network 100.64.0.0/16\n"
_SUMMARY_STATIC = "ip route 100.64.0.0/16 blackhole\n"


def baseline_configs() -> dict[str, str]:
    """The (frozen) scale_deagg baseline — reused verbatim."""
    return base.baseline_configs()


def _post_upstream_config() -> str:
    """upstream with the summary removed and the /24 more-specifics originated.

    Replaces the single ``network 100.64.0.0/16`` with one ``network 100.64.i.0/24``
    per more-specific, and the single covering blackhole static with one per /24 (so
    BGP can source each de-aggregated route).
    """
    before = base.baseline_configs()["upstream"]
    if _SUMMARY_NETWORK not in before or _SUMMARY_STATIC not in before:
        raise RuntimeError("scale_deagg baseline upstream changed; re-verify anchors")

    deagg_networks = "".join(f"  network {p}\n" for p in _DEAGG_PREFIXES)
    deagg_statics = "".join(f"ip route {p} blackhole\n" for p in _DEAGG_PREFIXES)

    after = before.replace(_SUMMARY_NETWORK, deagg_networks, 1)
    after = after.replace(_SUMMARY_STATIC, deagg_statics, 1)
    return after


def change_patch() -> str:
    """Unified diff on the upstream de-aggregating the block (round-trips)."""
    before = base.baseline_configs()["upstream"]
    after = _post_upstream_config()
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="upstream.conf", tofile="upstream.conf", lineterm="",
    )
    patch = "\n".join(diff) + "\n"
    if apply_unified_diff(before, patch) != after:
        raise RuntimeError("scale_deagg change patch does not round-trip")
    return patch
