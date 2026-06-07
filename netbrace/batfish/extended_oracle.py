"""Batfish ground-truth oracle for the extended blast-radius dimensions (D4-).

Companion to ``batfish/oracle.py`` (which fills the v0 D1-D3 BlastRadius). This
module computes the NEW dimensions from ``core.dimensions`` using Batfish's
forwarding model. Today it implements **D4 (waypoint)** end-to-end; D5/D7 hooks
are sketched with the same pattern (pre/post snapshot + a Batfish question).

D4 is computed from traceroute paths: a waypoint intent (src, dst_prefix, W) is
*satisfied* in a snapshot when every accepted src->dst trace transits node W. A
``WaypointViolation`` is emitted when the intent was satisfied in `pre` but not
in `post` — i.e. the change rerouted traffic off the required node while leaving
the destination reachable (so D1-D3 see nothing).

pybatfish is imported lazily so the package imports cleanly without it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from netbrace.batfish.oracle import _materialize_snapshot
from netbrace.core.dimensions import (
    ExtendedBlastRadius,
    ForwardingAnomaly,
    WaypointViolation,
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

    def _init(self, snapshot_dir: Path, name: str) -> None:
        self.bf.init_snapshot(str(snapshot_dir), name=name, overwrite=True)
        parse = self.bf.q.fileParseStatus().answer(snapshot=name).frame()
        bad = parse[parse["Status"] != "PASSED"]
        if not bad.empty:
            raise RuntimeError(f"snapshot {name} failed to parse:\n{bad.to_string()}")

    def _accepted_traces(self, snapshot: str, src_node: str, dst_ip: str) -> list[set[str]]:
        """Node sets of every ACCEPTED/DELIVERED src->dst trace in a snapshot."""
        df = self.bf.q.traceroute(
            startLocation=src_node, headers={"dstIps": dst_ip}
        ).answer(snapshot=snapshot).frame()
        out: list[set[str]] = []
        for _, row in df.iterrows():
            for tr in (row.get("Traces") or []):
                disp = str(getattr(tr, "disposition", ""))
                if "ACCEPTED" in disp or "DELIVERED" in disp:
                    nodes = {str(getattr(h, "node", None)) for h in getattr(tr, "hops", [])}
                    out.append(nodes)
        return out

    def _transits(self, snapshot: str, src_node: str, dst_ip: str, waypoint: str) -> bool:
        """True iff src can reach dst AND every accepted trace transits the waypoint."""
        traces = self._accepted_traces(snapshot, src_node, dst_ip)
        if not traces:
            return False  # not reachable -> intent vacuously unsatisfied
        return all(waypoint in nodes for nodes in traces)

    def _flow_outcome(self, snapshot: str, src_node: str, dst_ip: str):
        """Return (delivered?, (kind, dropping_node) | None) for a src->dst flow.

        ``delivered`` is True if any trace is accepted. The anomaly tuple is taken
        from the first failing trace whose disposition is a forwarding anomaly.
        """
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

    def compute_forwarding(
        self,
        pre_configs: dict[str, str],
        post_configs: dict[str, str],
        flows: list[tuple[str, str]],
    ) -> ExtendedBlastRadius:
        """Return an ExtendedBlastRadius whose forwarding_anomalies is the D7 truth.

        ``flows`` is a list of (src_node, dst_prefix). A ForwardingAnomaly is
        emitted for a flow that was delivered pre-change but post-change is dropped
        by a forwarding anomaly (blackhole / null-route / loop), localized to the
        dropping node.
        """
        with tempfile.TemporaryDirectory(prefix="netbrace_ext_") as tmp:
            tmp = Path(tmp)
            self._init(_materialize_snapshot(pre_configs, tmp / "pre"), "pre")
            self._init(_materialize_snapshot(post_configs, tmp / "post"), "post")

            anomalies: list[ForwardingAnomaly] = []
            for src, dst_prefix in flows:
                dst = _dst_ip(dst_prefix)
                pre_delivered, _ = self._flow_outcome("pre", src, dst)
                post_delivered, post_anom = self._flow_outcome("post", src, dst)
                if pre_delivered and not post_delivered and post_anom is not None:
                    kind, node = post_anom
                    anomalies.append(
                        ForwardingAnomaly(node=node, dst_prefix=dst_prefix, kind=kind)
                    )

        return ExtendedBlastRadius(forwarding_anomalies=anomalies).normalized()

    def compute_waypoint(
        self,
        pre_configs: dict[str, str],
        post_configs: dict[str, str],
        intents: list[tuple[str, str, str]],
    ) -> ExtendedBlastRadius:
        """Return an ExtendedBlastRadius whose waypoint_violations is the D4 ground truth.

        ``intents`` is a list of (src_node, dst_prefix, waypoint_node). A violation
        is emitted when the waypoint was transited pre-change but not post-change.
        """
        with tempfile.TemporaryDirectory(prefix="netbrace_ext_") as tmp:
            tmp = Path(tmp)
            self._init(_materialize_snapshot(pre_configs, tmp / "pre"), "pre")
            self._init(_materialize_snapshot(post_configs, tmp / "post"), "post")

            violations: list[WaypointViolation] = []
            for src, dst_prefix, waypoint in intents:
                dst = _dst_ip(dst_prefix)
                pre_ok = self._transits("pre", src, dst, waypoint)
                post_ok = self._transits("post", src, dst, waypoint)
                if pre_ok and not post_ok:
                    violations.append(
                        WaypointViolation(src_node=src, dst_prefix=dst_prefix, waypoint=waypoint)
                    )

        return ExtendedBlastRadius(waypoint_violations=violations).normalized()
