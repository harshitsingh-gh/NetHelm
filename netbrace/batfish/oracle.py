"""Batfish ground-truth oracle for blast-radius.

  ⚠️  NOT YET RUN AGAINST A LIVE BATFISH. The pure-Python pieces (snapshot
      materialization, set diffing) are straightforward, but the pybatfish query
      column names and FRR modeling behavior MUST be verified on the lab host
      before trusting the output. See plan.md §14 open questions Q2/Q3/Q4.
      The first task for whoever runs this on the lab: run
      `nethelm safety oracle ... --debug` on ONE shut_neighbor task and confirm
      the reported sessions_lost matches `show ip bgp summary` reality.

Design (plan.md §5): we compute the baseline state (S0) and post-change state
(S1) and diff them. We query each snapshot SEPARATELY and diff in Python rather
than using Batfish differential mode — the result is identical but the mechanism
is unambiguous and easy to debug. (Differential mode is a later optimization.)

pybatfish and pandas are imported lazily so the rest of nethelm imports cleanly
on machines without them (unit tests never touch this module).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from netbrace.core.schemas import (
    BlastRadius,
    PrefixLost,
    ReachabilityLost,
    SessionLost,
    TaskSpec,
    canon_prefix,
)
from netbrace.topology.patches import apply_unified_diff


def _materialize_snapshot(configs: dict[str, str], root: Path) -> Path:
    """Write {node: cfg} into <root>/configs/<node>.cfg and return <root>."""
    cfg_dir = root / "configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    for node, text in configs.items():
        (cfg_dir / f"{node}.cfg").write_text(text, encoding="utf-8")
    return root


def _post_configs(task: TaskSpec) -> dict[str, str]:
    """Apply the task's patch to its target node(s); return the post-change config set."""
    post = dict(task.baseline.configs)
    for node in task.change.target_nodes:
        post[node] = apply_unified_diff(post[node], task.change.patch)
    return post


class BatfishOracle:
    """Wraps a pybatfish Session. One instance can grade many tasks."""

    def __init__(self, host: str = "127.0.0.1", network: str = "netbrace_safety"):
        from pybatfish.client.session import Session  # lazy

        self.bf = Session(host=host)
        self.bf.set_network(network)

    # -- low-level per-snapshot queries (return plain Python structures) --
    def _init(self, snapshot_dir: Path, name: str) -> None:
        self.bf.init_snapshot(str(snapshot_dir), name=name, overwrite=True)
        parse = self.bf.q.fileParseStatus().answer().frame()
        bad = parse[parse["Status"] != "PASSED"]
        if not bad.empty:
            raise RuntimeError(f"snapshot {name} failed to parse:\n{bad.to_string()}")

    def _established_sessions(self, snapshot: str) -> set[tuple[str, str, str]]:
        """Set of (node, remote_ip, vrf) for ESTABLISHED sessions in a snapshot."""
        df = self.bf.q.bgpSessionStatus().answer(snapshot=snapshot).frame()
        out = set()
        for _, row in df.iterrows():
            if str(row.get("Established_Status")) == "ESTABLISHED":
                out.add((str(row["Node"]), str(row["Remote_IP"]),
                         str(row.get("VRF", "default"))))
        return out

    def _rib_prefixes(self, snapshot: str) -> set[tuple[str, str, str]]:
        """Set of (node, network, vrf) present in the main RIB."""
        df = self.bf.q.routes().answer(snapshot=snapshot).frame()
        out = set()
        for _, row in df.iterrows():
            out.add((str(row["Node"]), str(row["Network"]), str(row.get("VRF", "default"))))
        return out

    # -- the public entry point --
    def compute(self, task: TaskSpec, *, with_reachability: bool = False) -> BlastRadius:
        watched = set(task.watched_prefixes)
        with tempfile.TemporaryDirectory(prefix=f"netbrace_{task.task_id}_") as tmp:
            tmp = Path(tmp)
            pre = _materialize_snapshot(task.baseline.configs, tmp / "pre")
            post = _materialize_snapshot(_post_configs(task), tmp / "post")
            self._init(pre, "pre")
            self._init(post, "post")

            sess_pre = self._established_sessions("pre")
            sess_post = self._established_sessions("post")
            sessions_lost = [
                SessionLost(node=n, peer_ip=ip, vrf=vrf)
                for (n, ip, vrf) in (sess_pre - sess_post)
            ]

            rib_pre = self._rib_prefixes("pre")
            rib_post = self._rib_prefixes("post")
            prefixes_lost = [
                PrefixLost(node=n, prefix=net, vrf=vrf)
                for (n, net, vrf) in (rib_pre - rib_post)
                if canon_prefix(net) in watched
            ]

            reachability_lost: list[ReachabilityLost] = []
            if with_reachability:
                reachability_lost = self._reachability_diff(task, watched)

        return BlastRadius(
            sessions_lost=sessions_lost,
            prefixes_lost=prefixes_lost,
            reachability_lost=reachability_lost,
        ).normalized()

    def _reachability_diff(self, task: TaskSpec, watched: set[str]) -> list[ReachabilityLost]:
        """Pairwise traceroute over (node, watched-loopback) on pre vs post.

        Expensive (one traceroute per src/dst pair per snapshot). Only run when
        --reachability is passed. Returns pairs that succeeded pre and fail post.
        """
        lost: list[ReachabilityLost] = []
        nodes = task.topology.nodes
        for src in nodes:
            for dst in sorted(watched):
                ok_pre = self._traceroute_ok("pre", src, dst)
                ok_post = self._traceroute_ok("post", src, dst)
                if ok_pre and not ok_post:
                    lost.append(ReachabilityLost(src_node=src, dst_prefix=dst))
        return lost

    def _traceroute_ok(self, snapshot: str, src_node: str, dst_prefix: str) -> bool:
        dst_ip = dst_prefix.split("/")[0]
        df = self.bf.q.traceroute(
            startLocation=src_node, headers={"dstIps": dst_ip}
        ).answer(snapshot=snapshot).frame()
        # A flow is reachable if any trace disposition is ACCEPTED/DELIVERED.
        for _, row in df.iterrows():
            traces = row.get("Traces") or []
            for tr in traces:
                disp = str(getattr(tr, "disposition", "")) or str(tr)
                if "ACCEPTED" in disp or "DELIVERED" in disp:
                    return True
        return False


def compute_with_determinism_check(
    oracle: BatfishOracle, task: TaskSpec, *, runs: int = 3, with_reachability: bool = False
) -> tuple[BlastRadius, bool]:
    """Compute the blast radius `runs` times; return (result, deterministic?).

    The determinism gate from plan.md §5. A task whose result is not identical
    across runs should be quarantined (not shipped).
    """
    from netbrace.core.jsonio import to_json

    results = [oracle.compute(task, with_reachability=with_reachability) for _ in range(runs)]
    sigs = {to_json(r) for r in results}
    return results[0], len(sigs) == 1
