"""Batfish ground-truth oracle for the extended blast-radius dimensions.

Companion to ``batfish/oracle.py``. The headline entry point is
``ExtendedOracle.compute(scenario)``: it initialises the pre/post snapshots
ONCE and fills every relevant dimension on the SAME snapshots, returning a
complete ``ExtendedBlastRadius`` spanning:

  * D1 sessions_lost, D2 prefixes_lost, D3 reachability_lost  (the v0 base)
  * D4 waypoint_violations   (traceroute transit check)
  * D5 redundancy_losses     (installed next-hop / ECMP-width drop)
  * D7 forwarding_anomalies  (traceroute disposition: blackhole/null/loop)
  * D8 scale_violations      (installed-route count vs a resource_limits budget;
                              opt-in via Scenario.resource_limits)
  * D9 bgp_withdrawals       (BGP-RIB BEST withdrawal; opt-in via bgp_watch_prefixes)

Computing all dimensions together matters: a single-dimension oracle reports
ground truth for one axis only, so a model that *correctly* predicts a related
axis is wrongly penalised as a false alarm. The unified oracle fixes that.

(D6 filter is not computed here — it needs a vendor config; see
paper/refs/blast_radius_scenario_catalog.md.)

The per-dimension ``compute_waypoint`` / ``compute_forwarding`` /
``compute_redundancy`` helpers are kept for focused demos and tests.
pybatfish is imported lazily so the package imports cleanly without it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from netbrace.batfish.oracle import _materialize_snapshot
from netbrace.core.dimensions import (
    BgpRouteWithdrawn,
    ExtendedBlastRadius,
    ForwardingAnomaly,
    IntentViolation,
    RedundancyLoss,
    ScaleViolation,
    WaypointViolation,
)
from netbrace.core.schemas import (
    BlastRadius,
    PrefixLost,
    ReachabilityLost,
    SessionLost,
    canon_prefix,
)

# Batfish traceroute dispositions that mean the flow was delivered.
_DELIVERED = {"ACCEPTED", "DELIVERED_TO_SUBNET", "EXITS_NETWORK"}
# Failure dispositions that are *forwarding* anomalies (D7). A DENIED_IN/OUT drop
# is a filter effect (D6), not a forwarding anomaly, so it is deliberately absent.
_ANOMALY_KIND = {"NO_ROUTE": "blackhole", "NULL_ROUTED": "null_routed", "LOOP": "loop"}


def _dst_ip(prefix: str) -> str:
    """The address to traceroute toward, from a CIDR or bare IP."""
    return prefix.split("/")[0]


def _format_pre_state(sess_df, routes_df) -> str:
    """Render BGP session + routing-table dataframes as plain ``show``-style text.

    Pure (no Batfish/IO) so it is unit-testable with synthetic frames. Groups the
    output per node — ``show ip bgp summary`` then ``show ip route`` — sorted for a
    byte-stable rendering. Only PRE-state facts an operator could observe are shown
    (session up/down + installed routes); nothing about the proposed change.
    """
    nodes = sorted(set(sess_df["Node"].astype(str)) | set(routes_df["Node"].astype(str)))
    blocks: list[str] = []
    for node in nodes:
        lines = [f"=== {node} ==="]
        # show ip bgp summary
        lines.append("--- show ip bgp summary ---")
        srows = sess_df[sess_df["Node"].astype(str) == node]
        if len(srows):
            lines.append("Neighbor        Remote_AS  State")
            for _, r in srows.sort_values("Remote_IP").iterrows():
                lines.append(
                    f"{str(r['Remote_IP']):<15} {str(r.get('Remote_AS','?')):<10} "
                    f"{str(r.get('Established_Status','?'))}")
        else:
            lines.append("(no BGP neighbors)")
        # show ip route
        lines.append("--- show ip route ---")
        rrows = routes_df[routes_df["Node"].astype(str) == node]
        for _, r in rrows.sort_values(["Network"]).iterrows():
            nh = str(r.get("Next_Hop_IP", ""))
            nh = "" if nh in ("AUTO/NONE(-1l)", "nan", "None") else f" via {nh}"
            proto = str(r.get("Protocol", "?"))
            iface = str(r.get("Next_Hop_Interface", "") or "")
            iface = f" dev {iface}" if iface and iface != "dynamic" else ""
            lines.append(f"{proto:<10} {str(r['Network']):<18}{nh}{iface}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


class ExtendedOracle:
    """Wraps a pybatfish Session to compute extended-dimension ground truth."""

    def __init__(self, host: str = "127.0.0.1", network: str = "netbrace_extended"):
        from pybatfish.client.session import Session  # lazy

        self.bf = Session(host=host)
        self.bf.set_network(network)

    # ----- snapshot setup --------------------------------------------------- #
    def _init(self, snapshot_dir: Path, name: str) -> None:
        self.bf.init_snapshot(str(snapshot_dir), name=name, overwrite=True)
        parse = self.bf.q.fileParseStatus().answer(snapshot=name).frame()
        bad = parse[parse["Status"] != "PASSED"]
        if not bad.empty:
            raise RuntimeError(f"snapshot {name} failed to parse:\n{bad.to_string()}")

    def _setup(self, pre_configs: dict[str, str], post_configs: dict[str, str], tmp: Path) -> None:
        """Materialise + init both snapshots as 'pre' and 'post'."""
        self._init(_materialize_snapshot(pre_configs, tmp / "pre"), "pre")
        self._init(_materialize_snapshot(post_configs, tmp / "post"), "post")

    # ----- low-level per-snapshot queries ----------------------------------- #
    def _established_sessions(self, snapshot: str) -> set[tuple[str, str, str]]:
        df = self.bf.q.bgpSessionStatus().answer(snapshot=snapshot).frame()
        out = set()
        for _, row in df.iterrows():
            if str(row.get("Established_Status")) == "ESTABLISHED":
                out.add((str(row["Node"]), str(row["Remote_IP"]), str(row.get("VRF", "default"))))
        return out

    def _rib_prefixes(self, snapshot: str) -> set[tuple[str, str, str]]:
        df = self.bf.q.routes().answer(snapshot=snapshot).frame()
        return {(str(r["Node"]), str(r["Network"]), str(r.get("VRF", "default")))
                for _, r in df.iterrows()}

    def _bgp_rib_prefixes(self, snapshot: str) -> set[tuple[str, str, str]]:
        """Set of ``(node, vrf, network)`` for BGP-RIB **BEST** routes in a snapshot.

        The control-plane discriminator from oracle_determinism_spec_v1.md (item 1):
        the "advertised-but-unresolvable / withdrawn-from-bgp" signal for classes
        1/3/4. Live-verified on batfish/allinone (2026-06-08, ipc3 snapshot): the
        ``bgpRib`` ``Status`` column is a **list** (e.g. ``['BEST']``), NOT a scalar
        string, so BEST is tested by membership — a literal ``Status == "BEST"``
        filter would match nothing. Columns confirmed present: ``Node, VRF, Network,
        Status, AS_Path`` (and Next_Hop/Local_Pref/Communities/...).
        """
        df = self.bf.q.bgpRib().answer(snapshot=snapshot).frame()
        out: set[tuple[str, str, str]] = set()
        for _, r in df.iterrows():
            status = r.get("Status")
            is_best = "BEST" in status if isinstance(status, (list, tuple, set)) else str(status) == "BEST"
            if is_best:
                out.add((str(r["Node"]), str(r.get("VRF", "default")), str(r["Network"])))
        return out

    def _accepted_traces(self, snapshot: str, src_node: str, dst_ip: str) -> list[set[str]]:
        df = self.bf.q.traceroute(
            startLocation=src_node, headers={"dstIps": dst_ip}
        ).answer(snapshot=snapshot).frame()
        out: list[set[str]] = []
        for _, row in df.iterrows():
            for tr in (row.get("Traces") or []):
                disp = str(getattr(tr, "disposition", ""))
                if disp in _DELIVERED:  # consistent w/ _flow_outcome (incl. EXITS_NETWORK)
                    out.append({str(getattr(h, "node", None)) for h in getattr(tr, "hops", [])})
        return out

    def _flow_outcome(self, snapshot: str, src_node: str, dst_ip: str):
        """Return (delivered?, (kind, dropping_node) | None) for a src->dst flow."""
        df = self.bf.q.traceroute(
            startLocation=src_node, headers={"dstIps": dst_ip}
        ).answer(snapshot=snapshot).frame()
        delivered = False
        anomaly = None
        for _, row in df.iterrows():
            for tr in (row.get("Traces") or []):
                disp = str(getattr(tr, "disposition", ""))
                if disp in _DELIVERED:
                    delivered = True
                elif anomaly is None and disp in _ANOMALY_KIND:
                    hops = getattr(tr, "hops", [])
                    drop_node = str(getattr(hops[-1], "node", src_node)) if hops else src_node
                    anomaly = (_ANOMALY_KIND[disp], drop_node)
        return delivered, anomaly

    def _nexthop_count(self, snapshot: str, node: str, prefix: str) -> int:
        df = self.bf.q.routes(nodes=node, network=prefix).answer(snapshot=snapshot).frame()
        return len({str(row["Next_Hop_IP"]) for _, row in df.iterrows()})

    def _installed_route_count(self, snapshot: str, node: str) -> int:
        """Count of installed (main-RIB/FIB) routes on ``node`` in ``snapshot``.

        This is the row count of ``routes(nodes=node)`` — every route Batfish
        models as installed in the device's main RIB (the FIB-equivalent count).
        Deterministic: the route set on a pinned snapshot does not depend on any
        per-flow hash or timer, so the count is byte-identical across runs.
        """
        df = self.bf.q.routes(nodes=node).answer(snapshot=snapshot).frame()
        return len(df)

    # ----- per-dimension diffs (operate on the current pre/post snapshots) --- #
    def _base_diff(self, watched_prefixes, reachability_flows) -> BlastRadius:
        watched = {canon_prefix(p) for p in (watched_prefixes or [])}
        sess_pre, sess_post = self._established_sessions("pre"), self._established_sessions("post")
        sessions = [SessionLost(node=n, peer_ip=ip, vrf=v) for (n, ip, v) in (sess_pre - sess_post)]

        rib_pre, rib_post = self._rib_prefixes("pre"), self._rib_prefixes("post")
        prefixes = [PrefixLost(node=n, prefix=net, vrf=v)
                    for (n, net, v) in (rib_pre - rib_post) if canon_prefix(net) in watched]

        reachability = []
        for src, dst_prefix in (reachability_flows or []):
            dst = _dst_ip(dst_prefix)
            pre_ok, _ = self._flow_outcome("pre", src, dst)
            post_ok, _ = self._flow_outcome("post", src, dst)
            if pre_ok and not post_ok:
                reachability.append(ReachabilityLost(src_node=src, dst_prefix=dst_prefix))
        return BlastRadius(sessions_lost=sessions, prefixes_lost=prefixes,
                           reachability_lost=reachability)

    def _bgp_withdrawn_diff(self, watched_prefixes) -> list[BgpRouteWithdrawn]:
        """D9: ``(node, vrf, network)`` that left the BGP-RIB BEST set, pre→post.

        Scoped to ``watched_prefixes`` (same convention as D2) so transit/connected
        churn is not counted. This is a CONTROL-PLANE fact independent of D2/D3:
        for the has-static sibling it fires while D2/D3 stay silent (the static
        backup keeps the FIB + reachability), which is precisely what tells that
        sibling apart from a no-op. Deterministic by construction on a pinned pair.
        """
        watched = {canon_prefix(p) for p in (watched_prefixes or [])}
        if not watched:
            return []
        best_pre = self._bgp_rib_prefixes("pre")
        best_post = self._bgp_rib_prefixes("post")
        return [BgpRouteWithdrawn(node=n, network=net, vrf=v)
                for (n, v, net) in (best_pre - best_post) if canon_prefix(net) in watched]

    def _waypoint_diff(self, intents) -> list[WaypointViolation]:
        out = []
        for src, dst_prefix, waypoint in (intents or []):
            dst = _dst_ip(dst_prefix)
            traces_pre = self._accepted_traces("pre", src, dst)
            traces_post = self._accepted_traces("post", src, dst)
            pre_ok = bool(traces_pre) and all(waypoint in n for n in traces_pre)
            post_ok = bool(traces_post) and all(waypoint in n for n in traces_post)
            if pre_ok and not post_ok:
                out.append(WaypointViolation(src_node=src, dst_prefix=dst_prefix, waypoint=waypoint))
        return out

    def _redundancy_diff(self, targets) -> list[RedundancyLoss]:
        out = []
        for node, prefix in (targets or []):
            before = self._nexthop_count("pre", node, prefix)
            after = self._nexthop_count("post", node, prefix)
            if before > after >= 1:
                out.append(RedundancyLoss(node=node, dst_prefix=prefix,
                                          before_paths=before, after_paths=after))
        return out

    # Resources the installed-route-count proxy is VALID for. The main-RIB row
    # count is a legitimate (upper-bound) proxy for IPv4 FIB/RIB pressure ONLY. It
    # is NOT a label (MPLS LFIB) count nor an ACL-TCAM entry count, so emitting a
    # violation for those off the route count would be wrong (an IPv4 route count
    # firing a `label`/`acl_tcam` budget). Those need a vendor/MPLS model Batfish
    # does not provide here, so they are deliberately NOT computed.
    _ROUTE_COUNT_RESOURCES = {"fib", "rib"}

    def _scale_violations(self, resource_limits) -> list[ScaleViolation]:
        """D8: a device whose POST installed-route count crosses its fib/rib budget.

        ``resource_limits`` is ``{node: {resource: limit}}``. For each
        (node, resource, limit) where ``resource`` is one the installed-route count
        is a valid proxy for (``fib``/``rib`` — see ``_ROUTE_COUNT_RESOURCES``), we
        count the installed routes on ``node`` in the POST snapshot; if
        ``count > limit`` we emit a ScaleViolation carrying the observed count +
        limit as PAYLOAD (the ``.key`` is just (node, resource), so the violated
        element — not the live count — is what set-grading scores).

        Resources OUTSIDE the proxy's validity (``label`` MPLS LFIB depth,
        ``acl_tcam`` ACL-entry pressure) are SKIPPED, not scored against the IPv4
        route count — that would be a category error (an IPv4 row count firing an
        MPLS/TCAM budget). Computing them would need a vendor/MPLS model Batfish
        does not provide here; the count proxy is fib/rib only.

        Scope/limit of the model: this is a count-vs-limit THRESHOLD oracle. It
        does NOT model WHICH specific routes a TCAM evicts on overflow (eviction is
        platform/runtime-dependent and Batfish cannot model it). The route count is
        deterministic and the limit is a fixed spec annotation, so the overflow
        flag is fully static-deterministic. Grounded in Rogers Jul-2022 (filter
        removal -> route flood -> core capacity exceeded) and merchant-silicon FIB
        ceilings (Trident-2 ~64-72k IPv4); see knowledge/corpus.
        """
        out: list[ScaleViolation] = []
        for node, resources in (resource_limits or {}).items():
            # Defer the (potentially expensive) route count until we know at least
            # one resource on this node is a fib/rib proxy that needs it.
            scored = {r: lim for r, lim in resources.items()
                      if r in self._ROUTE_COUNT_RESOURCES}
            if not scored:
                continue
            count = self._installed_route_count("post", node)
            for resource, limit in scored.items():
                if count > limit:
                    out.append(ScaleViolation(
                        node=node, resource=resource, limit=limit, observed=count,
                    ))
        return out

    def _forwarding_diff(self, flows) -> list[ForwardingAnomaly]:
        out = []
        for src, dst_prefix in (flows or []):
            dst = _dst_ip(dst_prefix)
            pre_ok, _ = self._flow_outcome("pre", src, dst)
            post_ok, post_anom = self._flow_outcome("post", src, dst)
            if pre_ok and not post_ok and post_anom is not None:
                kind, node = post_anom
                out.append(ForwardingAnomaly(node=node, dst_prefix=dst_prefix, kind=kind))
        return out

    def _anomaly_set(self, snapshot: str, src_node: str, dst_ip: str) -> set[tuple[str, str]]:
        """All-traces SET of ``(kind, dropping_node)`` anomalies for a src->dst flow.

        Unlike ``_flow_outcome`` (which collapses to a single delivered/anomaly
        verdict and is thus blind when ONE of several ECMP traces still delivers),
        this returns EVERY blackhole/null/loop trace observed across the full set of
        traces Batfish returns. It is the determinism-spec invariant for ECMP: the
        membership of this set is independent of which path a per-flow hash would
        pick, so it is stable across runs. Used for partial (1/n) blackholes.
        """
        df = self.bf.q.traceroute(
            startLocation=src_node, headers={"dstIps": dst_ip}
        ).answer(snapshot=snapshot).frame()
        anomalies: set[tuple[str, str]] = set()
        for _, row in df.iterrows():
            for tr in (row.get("Traces") or []):
                disp = str(getattr(tr, "disposition", ""))
                if disp in _ANOMALY_KIND:
                    hops = getattr(tr, "hops", [])
                    drop_node = str(getattr(hops[-1], "node", src_node)) if hops else src_node
                    anomalies.add((_ANOMALY_KIND[disp], drop_node))
        return anomalies

    def _forwarding_diff_setwise(self, flows) -> list[ForwardingAnomaly]:
        """Set-wise D7: a NEW (kind, dropping-node) anomaly appears post for a flow.

        Fires for partial ECMP blackholes (one path delivers, another blackholes) —
        the RFC 7938 §5.2.3 signature where a flow-level delivered/undelivered check
        stays silent. The reported ``node`` is the dropping node (deterministic),
        not the chosen ECMP path. Only the anomalies ABSENT pre but PRESENT post are
        reported, so a pre-existing blackhole is not double-counted.
        """
        out = []
        for src, dst_prefix in (flows or []):
            dst = _dst_ip(dst_prefix)
            # Pre-delivery gate (consistent with _forwarding_diff): only a flow that
            # WAS delivered pre and acquires a NEW blackhole/null/loop post counts.
            # Without this a flow already broken pre that merely changes drop-node
            # would report a spurious "new" anomaly.
            pre_ok, _ = self._flow_outcome("pre", src, dst)
            if not pre_ok:
                continue
            new_anoms = self._anomaly_set("post", src, dst) - self._anomaly_set("pre", src, dst)
            for kind, node in sorted(new_anoms):
                out.append(ForwardingAnomaly(node=node, dst_prefix=dst_prefix, kind=kind))
        return out

    def _prefix_present(self, snapshot: str, node: str, prefix: str) -> bool:
        """True iff ``node`` has an installed route for the EXACT ``prefix`` in
        ``snapshot`` (the te_pin discriminator: the more-specific is present, not
        merely covered by an aggregate). ``_nexthop_count`` queries
        ``routes(network=prefix)`` which is an exact-prefix match in Batfish, so a
        covering /24 does NOT satisfy a /25 lookup — exactly the signal we need."""
        return self._nexthop_count(snapshot, node, prefix) >= 1

    def _intent_diff(self, intent_invariants) -> list[IntentViolation]:
        """D10: emit an IntentViolation for each invariant that HELD pre but is
        VIOLATED post. Deterministic by construction (reuses the same pinned-snapshot
        helpers as the other dimensions). The note is oracle-side only — it never
        enters the IntentViolation key, so grading scores the invariant IDENTITY
        (kind/src/dst), not any prose.

        Each ``kind`` reuses an existing helper:
          * reachability     -> _flow_outcome (delivered?)
          * waypoint         -> _accepted_traces transit check (same as _waypoint_diff)
          * isolation        -> _flow_outcome NEGATED (must NOT deliver)
          * redundancy_floor -> _nexthop_count vs floor
          * te_pin           -> _prefix_present (the pinned more-specific is installed)
        """
        out: list[IntentViolation] = []
        for inv in (intent_invariants or []):
            kind = inv.kind
            src = inv.src
            dst = inv.dst
            held_pre = False
            violated_post = False

            if kind == "reachability":
                dst_ip = _dst_ip(dst)
                pre_ok, _ = self._flow_outcome("pre", src, dst_ip)
                post_ok, _ = self._flow_outcome("post", src, dst_ip)
                held_pre, violated_post = pre_ok, (not post_ok)

            elif kind == "isolation":
                # dst (or forbidden_peer) is the target src must NOT reach.
                target = inv.forbidden_peer or dst
                dst_ip = _dst_ip(target)
                pre_ok, _ = self._flow_outcome("pre", src, dst_ip)
                post_ok, _ = self._flow_outcome("post", src, dst_ip)
                # held = isolated pre (not delivered); violated = reachable post.
                held_pre, violated_post = (not pre_ok), post_ok

            elif kind == "waypoint":
                wp = inv.waypoint
                dst_ip = _dst_ip(dst)
                traces_pre = self._accepted_traces("pre", src, dst_ip)
                traces_post = self._accepted_traces("post", src, dst_ip)
                held_pre = bool(traces_pre) and all(wp in n for n in traces_pre)
                post_ok = bool(traces_post) and all(wp in n for n in traces_post)
                violated_post = not post_ok

            elif kind == "redundancy_floor":
                floor = inv.floor or 0
                before = self._nexthop_count("pre", src, dst)
                after = self._nexthop_count("post", src, dst)
                held_pre = before >= floor
                violated_post = after < floor

            elif kind == "te_pin":
                # The pinned more-specific (dst is the specific prefix) must be the
                # installed route at src. Pre: present; post: gone (collapsed onto a
                # covering aggregate). Reachability can survive via the aggregate, so
                # this is exactly the "reachable but intent broken" signal.
                pre_present = self._prefix_present("pre", src, dst)
                post_present = self._prefix_present("post", src, dst)
                held_pre, violated_post = pre_present, (not post_present)

            if held_pre and violated_post:
                out.append(IntentViolation(kind=kind, src=src, dst=dst))
        return out

    # ----- the unified entry point ------------------------------------------ #
    def compute(self, scenario) -> ExtendedBlastRadius:
        """Compute the FULL extended blast radius for a Scenario, all dims at once.

        ``scenario`` is a tasks.safety.scenarios.Scenario (or any object exposing
        pre_configs, post_configs(), watched_prefixes, reachability_flows,
        waypoint_intents, redundancy_targets, forwarding_flows).
        """
        with tempfile.TemporaryDirectory(prefix="netbrace_ext_") as tmp:
            self._setup(scenario.pre_configs, scenario.post_configs(), Path(tmp))
            return ExtendedBlastRadius(
                base=self._base_diff(scenario.watched_prefixes, scenario.reachability_flows),
                waypoint_violations=self._waypoint_diff(scenario.waypoint_intents),
                redundancy_losses=self._redundancy_diff(scenario.redundancy_targets),
                # D7: set-wise (partial ECMP blackhole) when the scenario opts in,
                # else the default flow-level (total-loss) diff. Both are additive;
                # scenarios that don't set the flag are unchanged.
                forwarding_anomalies=(
                    self._forwarding_diff_setwise(scenario.forwarding_flows)
                    if getattr(scenario, "forwarding_setwise", False)
                    else self._forwarding_diff(scenario.forwarding_flows)
                ),
                # D9 is opt-in per scenario via bgp_watch_prefixes (default empty), so
                # scenarios that don't declare it (e.g. S-IPC-01) are unchanged.
                bgp_withdrawals=self._bgp_withdrawn_diff(
                    getattr(scenario, "bgp_watch_prefixes", None)
                ),
                # D8 is opt-in per scenario via resource_limits (default empty), so
                # scenarios that don't declare a budget are unchanged. Skips the
                # (potentially expensive) per-node route count when no budget is set.
                scale_violations=(
                    self._scale_violations(getattr(scenario, "resource_limits", None))
                    if getattr(scenario, "resource_limits", None)
                    else []
                ),
                # D10 is opt-in per scenario via intent_invariants (default empty),
                # so scenarios that declare no invariants are unchanged (no-op).
                intent_violations=self._intent_diff(
                    getattr(scenario, "intent_invariants", None)
                ),
            ).normalized()

    # ----- tools-condition: PRE-state observation the operator would gather --- #
    def pre_state_text(self, scenario) -> str:
        """Render the PRE-change OBSERVED network state as plain ``show``-style text.

        This is the input for the TOOLS-AUGMENTED condition (the key experiment):
        the current BGP session status (``show ip bgp summary``) and the routing
        table (``show ip route``) the operator would gather BEFORE deciding whether
        to trust a proposed change — extracted from the SAME pinned PRE snapshot the
        oracle grades against. It is the answer to "can't recall current state",
        isolated from "can't simulate the change". CRUCIALLY it is the PRE state
        only — never the post-state (which would leak the answer).

        Deterministic: a pinned snapshot's session/route set does not depend on any
        per-flow hash or timer, so this text is stable across runs.
        """
        with tempfile.TemporaryDirectory(prefix="netbrace_pre_") as tmp:
            self._init(_materialize_snapshot(scenario.pre_configs, Path(tmp) / "pre"), "pre")
            sess = self.bf.q.bgpSessionStatus().answer(snapshot="pre").frame()
            routes = self.bf.q.routes().answer(snapshot="pre").frame()
        return _format_pre_state(sess, routes)

    # ----- focused per-dimension helpers (demos / tests) -------------------- #
    def compute_waypoint(self, pre_configs, post_configs, intents) -> ExtendedBlastRadius:
        with tempfile.TemporaryDirectory(prefix="netbrace_ext_") as tmp:
            self._setup(pre_configs, post_configs, Path(tmp))
            return ExtendedBlastRadius(waypoint_violations=self._waypoint_diff(intents)).normalized()

    def compute_forwarding(self, pre_configs, post_configs, flows) -> ExtendedBlastRadius:
        with tempfile.TemporaryDirectory(prefix="netbrace_ext_") as tmp:
            self._setup(pre_configs, post_configs, Path(tmp))
            return ExtendedBlastRadius(forwarding_anomalies=self._forwarding_diff(flows)).normalized()

    def compute_redundancy(self, pre_configs, post_configs, targets) -> ExtendedBlastRadius:
        with tempfile.TemporaryDirectory(prefix="netbrace_ext_") as tmp:
            self._setup(pre_configs, post_configs, Path(tmp))
            return ExtendedBlastRadius(redundancy_losses=self._redundancy_diff(targets)).normalized()

    # ----- determinism gate -------------------------------------------------- #
    def compute_checked(self, scenario, *, runs: int = 10) -> ExtendedBlastRadius:
        """Compute the FULL extended blast radius ``runs`` times and assert stability.

        The project doctrine (oracle_determinism_spec_v1.md) demands a ground-truth
        oracle be byte-identical across >=10 runs or be quarantined. The v0
        ``BatfishOracle`` already has ``compute_with_determinism_check``; this is the
        equivalent gate for the unified ``ExtendedOracle.compute`` over all 8(+D9)
        dimensions on the SAME pre/post snapshot pair.

        Each call to ``compute`` re-materialises and re-inits the snapshots with
        ``overwrite=True`` (see ``_init``), so there is no cross-run state
        accumulation — every run starts from the same configs on a clean snapshot.

        Returns the stable ``ExtendedBlastRadius`` (the first run, which equals all
        others) if every run is byte-identical. RAISES ``NonDeterministicOracleError``
        naming the scenario and the differing dimension(s) if any run diverges.

        Additive: ``compute`` is unchanged; this only calls it ``runs`` times.
        """
        if runs < 2:
            raise ValueError("compute_checked needs runs >= 2 to detect divergence")
        results = [self.compute(scenario) for _ in range(runs)]
        name = getattr(scenario, "name", repr(scenario))
        return assert_extended_deterministic(results, scenario_name=name)


class NonDeterministicOracleError(RuntimeError):
    """Raised when an ExtendedOracle run set is not byte-identical across runs."""


def _diff_key_sets(a: ExtendedBlastRadius, b: ExtendedBlastRadius) -> list[str]:
    """Return the dimension names whose key sets differ between two results."""
    ka, kb = a.key_sets(), b.key_sets()
    return sorted(d for d in (set(ka) | set(kb)) if ka.get(d, set()) != kb.get(d, set()))


def assert_extended_deterministic(
    results: list[ExtendedBlastRadius], *, scenario_name: str = "<unknown>"
) -> ExtendedBlastRadius:
    """Assert every ``ExtendedBlastRadius`` in ``results`` is identical; return it.

    Pure comparison logic — no Batfish, no I/O — so it is unit-testable anywhere.
    Two results are "identical" iff their canonical JSON (``to_json``, which is
    sorted-key + stable) is byte-for-byte equal. This is strictly stronger than a
    ``key_sets()`` match (it also catches payload drift like before/after path
    counts), which is exactly the doctrine's "byte-identical" bar.

    On divergence raises ``NonDeterministicOracleError`` naming the scenario and the
    specific dimension(s) whose key sets differ (falling back to "<payload-only>"
    when the bytes differ but every key set still matches).
    """
    from netbrace.core.jsonio import to_json

    if not results:
        raise ValueError("assert_extended_deterministic needs at least one result")
    ref = results[0]
    ref_json = to_json(ref)
    for i, other in enumerate(results[1:], start=1):
        if to_json(other) == ref_json:
            continue
        dims = _diff_key_sets(ref, other) or ["<payload-only>"]
        raise NonDeterministicOracleError(
            f"scenario {scenario_name!r} is NON-DETERMINISTIC: run 0 vs run {i} "
            f"differ in dimension(s): {', '.join(dims)}. "
            f"Doctrine requires >=10x byte-identical or quarantine."
        )
    return ref


def compute_extended_with_determinism_check(
    oracle: ExtendedOracle, scenario, *, runs: int = 10
) -> tuple[ExtendedBlastRadius, bool]:
    """Non-raising variant: return ``(result, deterministic?)``.

    Mirrors ``oracle.compute_with_determinism_check`` (the v0 helper) for callers
    that want a boolean rather than an exception (e.g. a PASS/FAIL report table).
    """
    results = [oracle.compute(scenario) for _ in range(runs)]
    try:
        stable = assert_extended_deterministic(
            results, scenario_name=getattr(scenario, "name", repr(scenario))
        )
        return stable, True
    except NonDeterministicOracleError:
        return results[0], False
