"""Scenario registry: bundles a baseline + change + the probes the oracle needs.

A ``Scenario`` is the single object the unified oracle (ExtendedOracle.compute)
and the runner consume. It declares the pre-change configs, the change patch, and
the per-dimension probe sets (which flows/intents/targets to evaluate). The oracle
computes ALL declared dimensions on one pair of snapshots.

Add a new scenario by writing a builder that returns a Scenario and registering
it in REGISTRY. The probe lists decide which dimensions get ground truth:
  * watched_prefixes   -> D2 prefixes_lost is scored over these
  * reachability_flows -> D3 reachability_lost is scored over these (src, dst)
  * waypoint_intents   -> D4 (src, dst, must-transit-node)
  * redundancy_targets -> D5 (node, dst) ECMP-width drop
  * forwarding_flows   -> D7 (src, dst) blackhole/null/loop
D1 sessions_lost is always computed (cheap, whole-network).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from netbrace.tasks.safety import baseline_ecmp4 as ec
from netbrace.tasks.safety import baseline_ipc3 as ipc_base
from netbrace.tasks.safety import baseline_waypoint4 as wp
from netbrace.tasks.safety import scenario_blackhole as bh
from netbrace.tasks.safety import scenario_clos_summary as clos
from netbrace.tasks.safety import scenario_ipc as ipc
from netbrace.tasks.safety import scenario_ipc_aggregate as ipc_agg
from netbrace.tasks.safety import scenario_ipc_fanout as ipc_fan
from netbrace.tasks.safety import scenario_leak_ms as leak_ms
from netbrace.tasks.safety import scenario_lp_waypoint as lp_wp
from netbrace.tasks.safety import scenario_mgmt_lockout as mgmt_lock
from netbrace.tasks.safety import scenario_scale_deagg as scale_deagg
from netbrace.topology.patches import apply_unified_diff


@dataclass
class IntentInvariant:
    """An ORACLE-SIDE policy invariant the network must satisfy, evaluated PRE and
    POST by ExtendedOracle to produce D10 IntentViolation ground truth.

    CRITICAL PROMPT HYGIENE: ``intent_invariants`` are GROUND TRUTH and are NEVER
    shown to the model. The model sees only the scenario's ``intents_text`` PROSE
    and must DERIVE any violation from the diff + configs. The structured invariant
    (especially ``note``) must never appear in the model-visible prompt — same leak
    rule the red-team enforced for outcome statements.

    Fields (only the ones a given ``kind`` needs are set; the rest stay None):
      * ``kind``          — the invariant family (see IntentViolation docstring).
      * ``src``           — source node (None = any/origin-agnostic, e.g. te_pin
                            evaluated at a specific client uses src=that client).
      * ``dst``           — destination prefix (te_pin/reachability) or node
                            (isolation forbidden target).
      * ``waypoint``      — required transit node (kind="waypoint").
      * ``floor``         — minimum installed paths (kind="redundancy_floor").
      * ``forbidden_peer``— peer that must stay unreachable (kind="isolation").
      * ``note``          — human-readable oracle bookkeeping; NEVER graded, NEVER
                            shown to the model.
    """

    kind: Literal["reachability", "waypoint", "isolation", "redundancy_floor", "te_pin"]
    dst: str
    src: Optional[str] = None
    waypoint: Optional[str] = None
    floor: Optional[int] = None
    forbidden_peer: Optional[str] = None
    note: str = ""


@dataclass
class Scenario:
    name: str
    nodes: list[str]
    pre_configs: dict[str, str]
    change_target: str
    patch: str
    description: str
    intents_text: str = ""
    watched_prefixes: list[str] = field(default_factory=list)
    reachability_flows: list[tuple[str, str]] = field(default_factory=list)
    waypoint_intents: list[tuple[str, str, str]] = field(default_factory=list)
    redundancy_targets: list[tuple[str, str]] = field(default_factory=list)
    forwarding_flows: list[tuple[str, str]] = field(default_factory=list)
    # D7 scoring mode. Default (False) = "flow-level": a forwarding anomaly fires
    # only when the flow goes from fully DELIVERED to fully UN-delivered (the
    # total-loss signature of leak_ms / blackhole). True = "set-wise": a NEW
    # blackhole/null/loop trace appears in the post all-traces SET that was absent
    # pre — the determinism-spec ECMP invariant ("a blackhole trace EXISTS"),
    # required for partial (1/n) ECMP blackholes where one path still delivers so a
    # flow-level check would wrongly stay silent. Opt-in so existing scenarios are
    # unchanged. See docs/oracle_determinism_spec_v1.md.
    forwarding_setwise: bool = False
    # D9 control-plane probe: prefixes whose BGP-RIB BEST withdrawal is scored.
    # Default empty => D9 is opt-in; existing scenarios (e.g. ipc) are unchanged.
    bgp_watch_prefixes: list[str] = field(default_factory=list)
    # D8 scale/resource budget annotation: {node: {resource: limit}}, e.g.
    # {"edge1": {"fib": 50}}. The oracle counts installed routes on each node in
    # the POST snapshot and emits a ScaleViolation when the count CROSSES the
    # limit (count > limit). Default empty => D8 is opt-in; existing scenarios are
    # unchanged. The limit is a fixed spec annotation (Batfish gives the count, the
    # ceiling is platform spec) and the key omits the live count, so the ground
    # truth is deterministic. NOTE: this scores the count-vs-limit THRESHOLD only,
    # never which specific routes a TCAM would evict (eviction is platform/live).
    resource_limits: dict[str, dict[str, int]] = field(default_factory=dict)
    # Multi-node change support (default empty => single-target behavior unchanged).
    # When a single config edit is in fact a fabric-wide template that touches more
    # than one node (e.g. summarize on BOTH spines), set ``patches`` to a per-node
    # {node: unified_diff} map. ``self.patch`` is then the human-readable COMBINED
    # diff shown to the model (concat of all per-node diffs), while ``post_configs``
    # applies each per-node diff to its own node. If ``patches`` is empty the legacy
    # path (apply ``self.patch`` to ``change_target``) is used verbatim.
    patches: dict[str, str] = field(default_factory=dict)
    # Trap label: True when the change is consequential YET the naive "a BGP session
    # will drop" answer is WRONG (sessions stay up). Passed to grade_extended so the
    # false-alarm metrics are attributed; the per-dimension `false_session_alarm`
    # fires regardless, but `is_trap` marks where it is the intended failure mode.
    is_trap: bool = False
    # D10 intent/policy invariants: ORACLE-SIDE GROUND TRUTH only. The oracle
    # evaluates each invariant PRE and POST and emits an IntentViolation when it HELD
    # pre but is VIOLATED post. Default empty => D10 is opt-in (existing scenarios
    # unchanged: no invariants => no-op). NEVER shown to the model — the model reads
    # only `intents_text` prose and must derive violations from the diff + configs.
    intent_invariants: list[IntentInvariant] = field(default_factory=list)
    # Contamination-split tag. "handauthored" (default) = the GROUNDED, incident-
    # anchored hand-built scenarios (all existing ones keep this). "templated" =
    # emitted by a parameterized generator with per-seed randomized ASN/addressing/
    # names/prefix — the PRIMARY decontaminated split (novel instances even for a
    # public mechanism). Never shown to the model; used only by reporting to split
    # results into the GROUNDED vs templated buckets.
    provenance: str = "handauthored"

    def post_configs(self) -> dict[str, str]:
        """Baseline with the change applied to the target node(s)."""
        post = dict(self.pre_configs)
        if self.patches:
            for node, diff in self.patches.items():
                post[node] = apply_unified_diff(post[node], diff)
        else:
            post[self.change_target] = apply_unified_diff(post[self.change_target], self.patch)
        return post


def waypoint_scenario() -> Scenario:
    return Scenario(
        name="waypoint4",
        nodes=list(wp.NODES),
        pre_configs=wp.baseline_configs(),
        change_target=wp.CHANGE_TARGET,
        patch=wp.change_patch(),
        description="Change src's routing toward 10.0.0.4/32 (see the diff).",
        intents_text="src->10.0.0.4/32 MUST transit `way` (inspection node).",
        watched_prefixes=list(wp.WATCHED_PREFIXES),
        reachability_flows=[(s, d) for (s, d, _w) in wp.WAYPOINT_INTENTS],
        waypoint_intents=list(wp.WAYPOINT_INTENTS),
    )


def blackhole_scenario() -> Scenario:
    # TRUE blast radius (verified live, HANDOFF.md): D1=2 (r1<->r4 iBGP session, both
    # endpoints — the removed static is also r1's route to r4's loopback peering addr),
    # D2 (r1 loses 10.0.0.4/32), D3 + D7 (NO_ROUTE blackhole at r1). See
    # scenario_blackhole.py for the full mechanism. reachability_flows == forwarding_flows
    # is a DELIBERATE, disclosed D3+D7 overlap to show D7's classification/localization
    # value over D3 (the opposite choice from ipc_scenario, which is D3-only to avoid the
    # double-count). Do not read the overlap as two independent damage events.
    return Scenario(
        name="square4",
        nodes=list(bh.baseline_configs().keys()),
        pre_configs=bh.baseline_configs(),
        change_target=bh.CHANGE_TARGET,
        patch=bh.change_patch(),
        description="Remove r1's static route to 10.0.0.4/32 (looks redundant).",
        intents_text="All loopbacks must remain reachable from every node.",
        watched_prefixes=list(bh.WATCHED_PREFIXES),
        reachability_flows=list(bh.PROBE_FLOWS),
        forwarding_flows=list(bh.PROBE_FLOWS),
    )


def ecmp_scenario() -> Scenario:
    return Scenario(
        name="ecmp4",
        nodes=list(ec.NODES),
        pre_configs=ec.baseline_configs(),
        change_target=ec.CHANGE_TARGET,
        patch=ec.change_patch(),
        description="Remove one of src's two equal-cost static routes to 10.0.0.4/32.",
        intents_text="src->10.0.0.4/32 must keep 2 equal-cost paths for resilience.",
        watched_prefixes=list(ec.WATCHED_PREFIXES),
        reachability_flows=list(ec.REDUNDANCY_TARGETS),
        redundancy_targets=list(ec.REDUNDANCY_TARGETS),
    )


def ipc_scenario() -> Scenario:
    """S-IPC-01 — Class 1: internal routing-policy collapse (FLAGSHIP).

    An iBGP outbound prefix-list "cleanup" on the route reflector (r1) withdraws
    the customer prefix 203.0.113.0/24 from client r2. Sessions stay ESTABLISHED
    (D1 = ∅, the trap); r2's RIB loses the prefix (D2); r2 can no longer reach it
    (D3). Loopbacks survive via static backup, so the network "looks fine."
    Grounded in the Maintenance-Type-2 "implicit deny-all" trap (operational lore;
    FB-2021 at the prefix level) — NOT Rogers Jul-2022 (a filter removal → route
    flood → overload, which grounds the scale class). Probes r1/r3 too, to confirm
    they are unaffected (the customer prefix loss is localized to r2).
    """
    return Scenario(
        name="ipc3",
        nodes=list(ipc.baseline_configs().keys()),
        pre_configs=ipc.baseline_configs(),
        change_target=ipc.CHANGE_TARGET,
        patch=ipc.change_patch(),
        description=(
            "Attach an outbound prefix-list (CLEANUP_OUT) + route-map (TO_R2_OUT) "
            "to r1's iBGP session toward r2, to stop advertising internal "
            "infrastructure noise. Permits 10.0.0.0/8 (loopbacks) and 192.0.2.0/24 "
            "(link nets) outbound."
        ),
        intents_text=(
            "Reduce advertisement noise from the route reflector (r1) to the access "
            "router (r2): r2 should only need the backbone loopbacks and link nets. "
            "All customer/service reachability MUST be preserved."
        ),
        watched_prefixes=list(ipc.WATCHED_PREFIXES),
        reachability_flows=list(ipc.REACHABILITY_FLOWS),
        # D7 deliberately not declared: the NO_ROUTE at r2 is scored as a D3
        # reachability loss per the Class-1 oracle contract (D1/D2/D3), not as a
        # D7 forwarding anomaly. (It IS a NO_ROUTE blackhole; declaring D7 would
        # double-count the same effect under a second dimension.)
    )


def ipc_static_scenario() -> Scenario:
    """ipc_static — Class-1 has-static SIBLING (the discriminator / "looks like the
    collapse but isn't").

    Same outbound CLEANUP filter on r1 as S-IPC-01, but r2 has a STATIC backup to
    the customer prefix 203.0.113.0/24. The withdrawal still removes the prefix
    from r2's BGP RIB (D9 bgp_withdrawn fires) — but the static keeps r2's FIB
    populated (D2 prefixes_lost = ∅) and reachability alive (D3 = ∅). So the
    ground truth is {bgp_withdrawn=✓, D2=∅, D3=∅, D1=∅}: a CONTROL-PLANE-only
    event. A no-op would yield an empty D9 set, so the two are NOT scored alike.

    Declares ``bgp_watch_prefixes`` (only this sibling enables D9). The r1 change
    is reused verbatim from scenario_ipc, so this is purely a baseline variant.
    """
    pre = ipc_base.baseline_configs_static()
    return Scenario(
        name="ipc3_static",
        nodes=list(pre.keys()),
        pre_configs=pre,
        change_target=ipc.CHANGE_TARGET,
        patch=ipc.change_patch(),
        # Prompt = config edit + intent only (no outcome). The model sees r2's
        # static backup in the configs and must reason about its effect itself.
        description=(
            "Attach an outbound prefix-list (CLEANUP_OUT) + route-map (TO_R2_OUT) "
            "to r1's iBGP session toward r2 to stop advertising internal "
            "infrastructure noise (permits 10.0.0.0/8 + 192.0.2.0/24 outbound). "
            "See the diff and the per-node configs."
        ),
        intents_text=(
            "Reduce advertisement noise from r1 to r2. All customer/service "
            "reachability MUST be preserved."
        ),
        watched_prefixes=list(ipc.WATCHED_PREFIXES),
        reachability_flows=list(ipc.REACHABILITY_FLOWS),
        bgp_watch_prefixes=list(ipc.WATCHED_PREFIXES),
    )


def ipc_fanout_scenario() -> Scenario:
    """S-IPC-02 — Class 1 mechanism #3: all-clients withdrawal (multi-node blast).

    The same outbound CLEANUP filter as S-IPC-01, but attached to r1 toward THREE
    leaf clients (r2, r3, r4) at once on a 5-node RR fanout. The customer prefix is
    withdrawn from all three -> D2/D3 cardinality = 3 nodes (a different blast
    STRUCTURE than the single-node flagship, not a clone). r1 and r5 keep the
    prefix (negative controls); sessions stay ESTABLISHED (D1 = ∅, the trap).
    """
    return Scenario(
        name="ipc_fanout",
        nodes=list(ipc_fan.baseline_configs().keys()),
        pre_configs=ipc_fan.baseline_configs(),
        change_target=ipc_fan.CHANGE_TARGET,
        patch=ipc_fan.change_patch(),
        description=(
            "Attach an outbound prefix-list (CLEANUP_OUT) + route-map "
            "(TO_CLIENTS_OUT) to r1's iBGP sessions toward r2, r3 AND r4 (a "
            "peer-group-wide 'cleanup' template). Permits 10.0.0.0/8 + 192.0.2.0/24 "
            "outbound; the customer prefix is not permitted."
        ),
        intents_text=(
            "Apply the standard advertisement-cleanup template to all access "
            "routers (r2, r3, r4). All customer/service reachability MUST be "
            "preserved."
        ),
        watched_prefixes=list(ipc_fan.WATCHED_PREFIXES),
        reachability_flows=list(ipc_fan.REACHABILITY_FLOWS),
    )


def ipc_aggregate_scenario() -> Scenario:
    """ipc_aggregate — Class 1 mechanism #4: aggregate survives, more-specifics
    withdrawn (the "looks fine because the /24 is still there" trap).

    An aggregation router (r3) advertises a /24 supernet AND two more-specific /25
    prefixes (multihoming / traffic engineering). A "cleanup" outbound route-map on
    the RR (r1) toward client r2 permits the /24 aggregate (+ loopbacks + link nets)
    but implicit-denies the two /25s. The aggregate SURVIVES on r2 while the two
    more-specifics are WITHDRAWN — so D2 fires on the /25s, but D3 reachability to
    an address inside a /25 may be SILENT because the surviving /24 still covers it.
    Whether D3 fires is empirical; reachability_flows let the oracle decide per flow.
    Distinct from S-IPC-01 (no covering aggregate → clean NO_ROUTE) and S-IPC-02
    (multi-node single-prefix withdrawal). Grounded in RFC 4632 §5.3 de-aggregation
    / BGP TE-pinning operational practice.
    """
    return Scenario(
        name="ipc_aggregate",
        nodes=list(ipc_agg.baseline_configs().keys()),
        pre_configs=ipc_agg.baseline_configs(),
        change_target=ipc_agg.CHANGE_TARGET,
        patch=ipc_agg.change_patch(),
        description=(
            "Attach an outbound prefix-list (CLEANUP_OUT) + route-map (TO_R2_OUT) "
            "to r1's iBGP session toward r2. CLEANUP_OUT permits the 203.0.113.0/24 "
            "aggregate exactly, plus 10.0.0.0/8 (loopbacks) and 192.0.2.0/24 (link "
            "nets). The two /25 more-specifics (203.0.113.0/25, 203.0.113.128/25) "
            "are not permitted, so the route-map's implicit deny-all drops them."
        ),
        intents_text=(
            "Reduce advertisement noise from the route reflector (r1) to the access "
            "router (r2): r2 should only need the covering customer aggregate, the "
            "backbone loopbacks, and the link nets. All customer reachability MUST "
            "be preserved."
        ),
        watched_prefixes=list(ipc_agg.WATCHED_PREFIXES),
        reachability_flows=list(ipc_agg.REACHABILITY_FLOWS),
        # D10 (oracle-side ground truth, NEVER shown to the model): the two /25
        # more-specifics are TE pins r3 advertised for multihoming. The CLEANUP
        # filter withdraws them from r2, so at r2 traffic to each /25 collapses onto
        # the surviving /24 aggregate. Reachability survives (D3=∅, the /24 covers
        # it) but the TE pin is broken -> this is the dimension D1-D3 cannot catch.
        # The model must DERIVE this from the intents_text prose + the diff/configs.
        intent_invariants=[
            IntentInvariant(
                kind="te_pin", src="r2", dst=ipc_agg.SPECIFIC_LOW,
                note="r3 pins 203.0.113.0/25 for inbound TE; CLEANUP withdraws it "
                     "from r2, collapsing it onto the /24 (reachable but de-pinned).",
            ),
            IntentInvariant(
                kind="te_pin", src="r2", dst=ipc_agg.SPECIFIC_HIGH,
                note="r3 pins 203.0.113.128/25 for inbound TE; same collapse onto "
                     "the /24 aggregate at r2.",
            ),
        ],
    )


def leak_ms_scenario() -> Scenario:
    """leak_ms — Class 2: more-specific route leak -> longest-prefix-match blackhole.

    The change ADDS a route (the leaker originates a /25 more-specific of the
    victim's /24), so the naive "count prefixes lost" view is BLIND: D1
    sessions_lost = ∅ AND D2 prefixes_lost = ∅. Yet transit's traffic to the
    victim host 203.0.113.1 is pulled to the leaker by longest-prefix-match and
    blackholed there (D7 forwarding anomaly + D3 reachability loss). The cleanest
    justification for multi-dimensional scoring. Grounded in Cloudflare-Jun-2019
    and Telekom-Malaysia-2015 (knowledge/corpus/noc/).
    """
    return Scenario(
        name="leak_ms",
        nodes=list(leak_ms.baseline_configs().keys()),
        pre_configs=leak_ms.baseline_configs(),
        change_target=leak_ms.CHANGE_TARGET,
        patch=leak_ms.change_patch(),
        description=(
            "On the leaker (AS65003), originate a more-specific /25 of the victim's "
            "/24 (network 203.0.113.0/25), backed by a discard static. See the diff."
        ),
        intents_text=(
            "The leaker (AS65003) should only advertise prefixes it legitimately "
            "serves (198.51.100.0/24). All traffic toward the victim's customer "
            "space 203.0.113.0/24 MUST continue to reach the victim (AS65001)."
        ),
        watched_prefixes=list(leak_ms.WATCHED_PREFIXES),
        reachability_flows=list(leak_ms.REACHABILITY_FLOWS),
        forwarding_flows=list(leak_ms.FORWARDING_FLOWS),
    )


def lp_waypoint_scenario() -> Scenario:
    """lp_waypoint — Class 5: LOCAL_PREF-driven waypoint (D4) shift; empty-blast trap.

    src reaches the customer prefix 203.0.113.0/24 (originated by external customer
    dst, dual-homed via way and alt). Pre-state: an inbound route-map on `way` sets
    LOCAL_PREF=200 vs `alt`'s 100, so src's best path transits the inspection node
    `way`. The change RAISES alt's inbound LOCAL_PREF 100->300, flipping src's best
    path to the alt egress — traffic stops transiting `way`. NO session resets
    (D1=∅, the documented LLM trap), NO prefix lost (D2=∅), dst still reachable
    (D3=∅): ONLY D4 (waypoint) fires. Mechanistically distinct from `waypoint4`
    (a static-route reroute) — here the egress flip is a BGP best-path LOCAL_PREF
    decision. Grounded in knowledge/corpus/noc/network_change_management.md
    ("sessions don't drop on LP changes") and RFC 4271 §9.1.1 best-path order.
    """
    return Scenario(
        name="lp_waypoint",
        nodes=list(lp_wp.baseline_configs().keys()),
        pre_configs=lp_wp.baseline_configs(),
        change_target=lp_wp.CHANGE_TARGET,
        patch=lp_wp.change_patch(),
        # NOTE: the prompt states ONLY the config edit + the policy intent — never
        # the routing OUTCOME. Saying "this makes alt preferred / bypasses way"
        # lets a model score by parroting; it must derive the path shift from the
        # diff + configs itself. (Authoring rule: config edit only, no outcome.)
        description=(
            "On `alt` (an AS65000 egress router), change the inbound eBGP "
            "local-preference value set by the FROM_DST_IN route-map from 100 to "
            "300 (a one-line value edit). See the diff."
        ),
        intents_text=(
            "All traffic from src to the customer space 203.0.113.0/24 MUST transit "
            "the inspection node `way`. The customer prefix MUST remain reachable. "
            "The operator's stated goal for the change is to reduce egress cost."
        ),
        watched_prefixes=list(lp_wp.WATCHED_PREFIXES),
        reachability_flows=list(lp_wp.REACHABILITY_FLOWS),
        waypoint_intents=list(lp_wp.WAYPOINT_INTENTS),
    )


def clos_summary_scenario() -> Scenario:
    """clos_summary — DC underlay route-summarization blackhole (RFC 7938 §5.2.3).

    A 2-spine/3-leaf eBGP Clos with a FIXED asymmetry: spine2 has no path to
    leaf3's server prefix 10.3.0.0/24. The change is a fabric-wide "summarize the
    underlay" template on BOTH spines: originate the covering 10.0.0.0/8 (discard-
    backed) and advertise it INSTEAD of the specific toward the leaves. The naive
    review passes it clean — D1 sessions_lost = ∅ and the server space still looks
    covered (the /8 is present-and-best in every RIB) — yet a SUBSET of each remote
    leaf's traffic to 10.3.0.1 now ECMPs onto spine2 and is blackholed there
    (NULL_ROUTED), because spine2 advertises the summary it cannot deliver. D7
    fires (a blackhole trace exists); D3 may stay quiet because spine1 still
    delivers the other ECMP half — the partial-loss signature RFC 7938 §5.2.3
    warns about. Distinct mechanism from every other scenario in the suite (no
    session/prefix removed; the blast is a summary MASKING a pre-existing missing
    path, surfaced only by ECMP fan-out onto the summarizing spine).

    Grounded: RFC 7938 §5.2.3 + §3.2.2 + §6.2; knowledge/corpus/dc/
    dc_summarization_ecmp_pitfalls.md; ipSpace "Avoid summarization in leaf-and-spine".
    """
    return Scenario(
        name="clos_summary",
        nodes=list(clos.baseline_configs().keys()),
        pre_configs=clos.baseline_configs(),
        change_target=clos.CHANGE_TARGET,
        patch=clos.change_patch(),
        patches=clos.patches(),
        # AUTHORING RULE: state ONLY the config edit + the policy intent — NEVER the
        # routing outcome. Do NOT say "this blackholes via spine2" or "the summary
        # masks the failure"; the model must derive the blast from the diff+configs.
        description=(
            "On BOTH spines (spine1, spine2), summarize the underlay toward the "
            "leaves to shrink the leaf FIBs: originate the covering aggregate "
            "10.0.0.0/8 (a discard-backed `network 10.0.0.0/8`) and attach an "
            "outbound prefix-list (SUMMARIZE_OUT) to every leaf-facing eBGP neighbor "
            "that advertises the /8 and suppresses the more-specific 10.3.0.0/24. "
            "See the combined diff."
        ),
        intents_text=(
            "Reduce the leaf forwarding tables by advertising a single covering "
            "summary (10.0.0.0/8) from the spines instead of every server subnet. "
            "All servers in 10.0.0.0/8 — including the 10.3.0.0/24 service behind "
            "leaf3 — MUST remain reachable from every leaf. The operator's stated "
            "goal is FIB optimization."
        ),
        watched_prefixes=list(clos.WATCHED_PREFIXES),
        reachability_flows=list(clos.REACHABILITY_FLOWS),
        forwarding_flows=list(clos.FORWARDING_FLOWS),
        # Partial (1/n) ECMP blackhole: one path still delivers, so score the
        # all-traces SET invariant ("a blackhole trace exists"), not flow-level.
        forwarding_setwise=True,
    )


def scale_deagg_scenario() -> Scenario:
    """scale_deagg — Class 8: de-aggregation / table-flood -> FIB resource overflow.

    The D8 scale class, grounded in Rogers Jul-2022 (filter/summary removal ->
    route flood -> downstream capacity exceeded). The change REMOVES the upstream's
    single covering summary (100.64.0.0/16) and originates the many /24
    more-specifics inside it, so the edge installs many more routes and crosses its
    stated FIB budget.

    Honest thesis (the "loss view is blind to the real blast" trap on the scale
    axis): the only *loss* signal is a benign-looking supernet->specifics SWAP — the
    /16 summary IS withdrawn from the edge's RIB (so D2 honestly fires on
    100.64.0.0/16, which is in the watch set), but the constituent /24s cover the
    SAME destination space, so reachability is unchanged (D3 = ∅, no destination
    lost). The REAL blast — the D8 FIB overflow — is invisible to every
    connectivity/loss view: D1 = ∅ (session stays ESTABLISHED) and a reachability
    review sees nothing wrong.

    Expected ground truth (confirmed live via the oracle, 2026-06-08):
      * D1 sessions_lost = ∅
      * D2 prefixes_lost = {(edge, 100.64.0.0/16), (upstream, 100.64.0.0/16)}
        — the /16 supernet row leaves BOTH RIBs (upstream stops originating it; the
        edge stops learning it). The 24 /24s that replace it are ADDED, not lost, so
        they do not appear in D2. This is the benign supernet->specifics SWAP, the
        only loss signal in the change.
      * D3 reachability_lost = ∅  (the /24s cover the same destination space)
      * D8 scale_violations = {(edge, fib)}  (installed-route count 27 > budget 20)
    Only the edge carries a resource_limits budget (it is the overflow victim);
    upstream's table also grows but it is the originator, not a budgeted victim.
    """
    return Scenario(
        name="scale_deagg",
        nodes=list(scale_deagg.baseline_configs().keys()),
        pre_configs=scale_deagg.baseline_configs(),
        change_target=scale_deagg.CHANGE_TARGET,
        patch=scale_deagg.change_patch(),
        # AUTHORING RULE: state ONLY the config edit + the policy/budget intent —
        # NEVER the resulting count or the outcome. Do NOT say "24 /24s" or "this
        # overflows the FIB": stating the de-agg COUNT lets a model solve it by
        # `count > budget` arithmetic with zero config reasoning. The model must
        # DERIVE the post-change route count from the diff + configs (count the
        # originated more-specifics plus the edge's own connected/loopback routes)
        # and compare it against the stated budget. The diff itself enumerates the
        # added `network` lines (legitimate known context); the prose does not.
        description=(
            "On the upstream (AS65010), remove the single covering aggregate "
            "`network 100.64.0.0/16` (and its backing discard static) and instead "
            "originate the constituent more-specific /24s inside that block, each "
            "backed by its own discard static. See the diff for the exact lines."
        ),
        intents_text=(
            "Advertise the customer block 100.64.0.0/16 to the edge router (the "
            "operator's stated goal is finer-grained traffic engineering by "
            "advertising the constituent /24s instead of the summary). POLICY/"
            "RESOURCE BUDGET: the edge router's forwarding table (FIB) has a ceiling "
            "of 20 installed routes — the change MUST keep the edge within that "
            "budget. (A device's FIB ceiling is legitimate known context; the "
            "resulting post-change route count is NOT stated and must be derived "
            "from the diff + configs.)"
        ),
        watched_prefixes=list(scale_deagg.WATCHED_PREFIXES),
        # D8 budget annotation: only the edge is constrained (the overflow victim).
        resource_limits=dict(scale_deagg.RESOURCE_LIMITS),
    )


def mgmt_lockout_scenario() -> Scenario:
    """mgmt_lockout — management-plane / OOB lockout, graded against a stated
    management-reachability INTENT (D10). The noc-veteran's top-ranked missing
    class (4 post-mortems).

    SAME MECHANISM AS `ipc`, A DIFFERENT GRADED SURFACE. This reuses the Class-1
    `ipc` mechanism verbatim — an outbound iBGP prefix-list "cleanup" whose implicit
    deny-all silently withdraws prefixes from a downstream peer while every BGP
    session stays ESTABLISHED (D1=∅). It is NOT a new failure mechanism. Its
    distinct value is that the withdrawn prefixes are the managed devices'
    MANAGEMENT subnets and the scenario is SCORED against a stated "the NOC jump-host
    MUST retain management reachability to every device" intent via the D10
    dimension. This is the deliberate-sibling pattern of `ipc_static` (same Class-1
    withdrawal, value is the D9 control-plane dimension) — here the value is the D10
    intent/severity grading.

    A routine-looking "advertisement cleanup" on the aggregation router (`core`)
    toward the NOC jump-host (`jump`) keeps advertising the customer prefix and the
    backbone infra, but its implicit deny-all stops advertising BOTH managed
    devices' MANAGEMENT subnets (172.16.0.0/24 on edge, 172.16.1.0/24 on edge2).
    The jump-host's only path to each mgmt-IP is that BGP advertisement (in-band
    OOB, no static backup), so the NOC is locked out of BOTH devices. Ground truth:
      * D1 sessions_lost = ∅ (loopbacks have static backup; iBGP stays up)
      * D2 prefixes_lost = ∅ — and HONEST: the WATCHED set is the customer prefix +
        all four loopbacks, every one a survivor (negative control), so a model that
        false-positives on any of them loses D2 precision. The mgmt prefixes are not
        hidden from a watch set to fake the trap; they fire on D3/D10.
      * D3 reachability_lost = {(jump, 172.16.0.1), (jump, 172.16.1.1)} (>= 2 losses)
      * D10 intent_violations = {reachability jump->172.16.0.0/24,
        reachability jump->172.16.1.0/24} (>= 2 management-reachability violations)
    A "no customer prefixes -> safe" review misses it entirely; a model that flags
    the reachability loss but NOT the management-intent violation scores only
    PARTIAL (it misses D10). Grounded in Facebook Oct-2021, AWS us-east-1 Dec-2021,
    Rogers Jul-2022, Cloudflare Jun-2022 (OOB depended on the production control
    plane); knowledge/corpus/noc/mgmt_plane_lockout.md.

    Mechanism is a CONTROL-PLANE severance (stop advertising the mgmt prefixes
    toward jump) expressed as prefix-list + route-map ONLY — NOT an interface ACL,
    which Batfish does not model as a packet filter (docs/oracle_determinism_spec_v1.md).
    """
    return Scenario(
        name="mgmt_lockout",
        nodes=list(mgmt_lock.baseline_configs().keys()),
        pre_configs=mgmt_lock.baseline_configs(),
        change_target=mgmt_lock.CHANGE_TARGET,
        patch=mgmt_lock.change_patch(),
        # AUTHORING RULE (hard): state ONLY the config edit + the policy intent —
        # NEVER the outcome. Do NOT say "this locks out mgmt / the NOC can't reach
        # the device". The model must derive the lockout from the diff + configs
        # (it can SEE the mgmt prefixes are not in the permit list and have no static
        # backup, and that the jump-host depends on the advertisement).
        description=(
            "On the aggregation router `core`, attach an outbound prefix-list "
            "(MGMT_CLEANUP_OUT) + route-map (TO_JUMP_OUT) to its iBGP session toward "
            "the NOC jump-host `jump`, to stop advertising internal infrastructure "
            "noise. MGMT_CLEANUP_OUT permits 10.0.0.0/8 (loopbacks), 192.0.2.0/24 "
            "(link nets), and 203.0.113.0/24 (the customer prefix). See the diff and "
            "the per-node configs."
        ),
        intents_text=(
            "Reduce advertisement noise from the aggregation router (`core`) to the "
            "NOC jump-host (`jump`). The NOC jump-host MUST retain management "
            "reachability to every device's management address, and all customer "
            "reachability MUST be preserved. The operator's stated goal is to trim "
            "infrastructure advertisements toward the jump-host."
        ),
        watched_prefixes=list(mgmt_lock.WATCHED_PREFIXES),
        reachability_flows=list(mgmt_lock.REACHABILITY_FLOWS),
        # D10 (ORACLE-SIDE GROUND TRUTH, NEVER shown to the model): the stated
        # management-reachability intent, made gradeable. For each managed device the
        # jump-host must be able to reach the device's mgmt subnet; the cleanup filter
        # breaks both. The model sees ONLY the intents_text prose above and must
        # DERIVE the violation from the diff + configs. This is the key fix: a model
        # that lists the D3 reachability loss but does NOT grade it as an intent
        # violation now misses D10 and scores PARTIAL (the set-subtraction heuristic
        # no longer gets a perfect score).
        intent_invariants=[
            IntentInvariant(
                kind="reachability", src=src, dst=dst,
                note=f"NOC jump-host must retain mgmt reachability to {dst}; the "
                     f"MGMT_CLEANUP_OUT filter withdraws it toward jump (in-band OOB, "
                     f"no static backup) -> management-plane lockout.",
            )
            for (src, dst) in mgmt_lock.INTENT_MGMT_TARGETS
        ],
        # D7 deliberately NOT declared: the NO_ROUTE at jump is scored as a D3
        # reachability loss (the class contract), not double-counted as a D7
        # forwarding anomaly.
    )


REGISTRY = {
    "waypoint": waypoint_scenario,
    "lp_waypoint": lp_waypoint_scenario,
    "blackhole": blackhole_scenario,
    "ecmp": ecmp_scenario,
    "ipc": ipc_scenario,
    "ipc_static": ipc_static_scenario,
    "ipc_fanout": ipc_fanout_scenario,
    "ipc_aggregate": ipc_aggregate_scenario,
    "leak_ms": leak_ms_scenario,
    "clos_summary": clos_summary_scenario,
    "scale_deagg": scale_deagg_scenario,
    "mgmt_lockout": mgmt_lockout_scenario,
}


# Scenarios where the change touches BGP policy/attributes, so the naive "a BGP
# session will drop" answer is the tempting-but-WRONG prediction (sessions stay up).
# These are the documented-LLM-failure traps; the static-route scenarios
# (blackhole/ecmp/waypoint) are not in this set.
TRAP_SCENARIOS = {
    "ipc", "ipc_static", "ipc_fanout", "ipc_aggregate",
    "leak_ms", "lp_waypoint", "clos_summary", "scale_deagg",
    "mgmt_lockout",
}


def build(name: str) -> Scenario:
    if name not in REGISTRY:
        raise KeyError(f"unknown scenario {name!r}; choose from {sorted(REGISTRY)}")
    scn = REGISTRY[name]()
    if name in TRAP_SCENARIOS:
        scn.is_trap = True
    return scn


# --------------------------------------------------------------------------- #
# Generated (templated) instances — the PRIMARY decontaminated split.
#
# These are NOT in REGISTRY (REGISTRY holds the hand-authored GROUNDED scenarios so
# existing callers, the determinism gate, and the registry tests are unchanged). The
# runner + sweep enumerate generated instances through ``build_generated_suite`` /
# ``build_generated`` instead. Each emitted Scenario sets ``provenance="templated"``
# and is consumed by ExtendedOracle.compute + grade_extended exactly like a
# hand-authored one (same dataclass, same dimensions, same determinism gate).
# --------------------------------------------------------------------------- #
def build_generated_suite(n: int, *, base_seed: int = 0) -> list[Scenario]:
    """Enumerate ``n`` Class-1 generated instances (lazy import of the generator)."""
    from netbrace.tasks.safety import generator_ipc

    return generator_ipc.generate_ipc_suite(n, base_seed=base_seed)


def build_generated(seed: int) -> Scenario:
    """Build a single Class-1 generated instance by seed (axis chosen from seed)."""
    from netbrace.tasks.safety import generator_ipc

    return generator_ipc.generate_ipc_withdrawal(seed)


def build_generated_suite_multi(n: int, *, base_seed: int = 0) -> list[Scenario]:
    """Enumerate ``n`` generated instances across ALL FOUR mechanism generators.

    Audit 2026-06-10 K3: the templated split must cover MULTIPLE mechanisms, not
    96 photocopies of Class-1. Allocation: n is split evenly across
    ipc (Class-1 silent withdrawal), leak (Class-2 route leak/hijack),
    lp (Class-5 attribute path-shift + no-op trap), scale (Class-8 de-agg
    overflow); any remainder goes to ipc (the largest axis space). The result is
    round-robin interleaved so a truncated prefix (small --n-generated) still
    spans all four mechanisms. Additive: ``build_generated_suite`` (Class-1 only)
    is unchanged for callers/tests pinned to its behavior.
    """
    from netbrace.tasks.safety import (generator_ipc, generator_leak,
                                       generator_lp, generator_scale)

    each, rem = divmod(n, 4)
    suites = [
        generator_ipc.generate_ipc_suite(each + rem, base_seed=base_seed),
        generator_leak.generate_leak_suite(each, base_seed=base_seed),
        generator_lp.generate_lp_suite(each, base_seed=base_seed),
        generator_scale.generate_scale_suite(each, seed=base_seed),
    ]
    out: list[Scenario] = []
    i = 0
    while len(out) < n:
        for s in suites:
            if i < len(s):
                out.append(s[i])
                if len(out) == n:
                    break
        i += 1
    return out
