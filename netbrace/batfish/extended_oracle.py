"""Batfish ground-truth oracle for the extended blast-radius dimensions.

Companion to ``batfish/oracle.py``. The headline entry point is
``ExtendedOracle.compute(scenario)``: it initialises the pre/post snapshots
ONCE and fills every relevant dimension on the SAME snapshots, returning a
complete ``ExtendedBlastRadius`` spanning:

  * D1 sessions_lost, D2 prefixes_lost, D3 reachability_lost  (the v0 base)
  * D4 waypoint_violations   (traceroute transit check)
  * D5 redundancy_losses     (installed next-hop / ECMP-width drop)
  * D7 forwarding_anomalies  (traceroute disposition: blackhole/null/loop)

Computing all dimensions together matters: a single-dimension oracle reports
ground truth for one axis only, so a model that *correctly* predicts a related
axis is wrongly penalised as a false alarm. The unified oracle fixes that.

(D6 filter and D8 scale are not computed here — they need a vendor config /
resource spec respectively; see paper/refs/blast_radius_scenario_catalog.md.)

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
    ExtendedBlastRadius,
    ForwardingAnomaly,
    RedundancyLoss,
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

    def _accepted_traces(self, snapshot: str, src_node: str, dst_ip: str) -> list[set[str]]:
        df = self.bf.q.traceroute(
            startLocation=src_node, headers={"dstIps": dst_ip}
        ).answer(snapshot=snapshot).frame()
        out: list[set[str]] = []
        for _, row in df.iterrows():
            for tr in (row.get("Traces") or []):
                disp = str(getattr(tr, "disposition", ""))
                if "ACCEPTED" in disp or "DELIVERED" in disp:
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
                forwarding_anomalies=self._forwarding_diff(scenario.forwarding_flows),
            ).normalized()

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
