"""Tests for the core data contracts and canonicalization."""

from netbrace.core.schemas import (
    BlastRadius,
    PrefixLost,
    ReachabilityLost,
    SessionLost,
    TaskSpec,
    canon_prefix,
)
from netbrace.core.jsonio import to_json, read_model
from netbrace.core import schemas


def test_canon_prefix_bare_ip_becomes_host_route():
    assert canon_prefix("10.0.0.2") == "10.0.0.2/32"
    assert canon_prefix("10.0.0.0/24") == "10.0.0.0/24"


def test_session_key_canonicalizes_node_and_ip():
    a = SessionLost(node="R1", peer_ip="10.0.0.2")
    b = SessionLost(node="r1", peer_ip="10.0.0.2")
    assert a.key == b.key == "bgp|vrf=default|node=r1|peer_ip=10.0.0.2"


def test_prefix_key_uses_canonical_cidr():
    e = PrefixLost(node="r3", prefix="10.0.0.2")
    assert e.key == "route|node=r3|vrf=default|prefix=10.0.0.2/32"


def test_blastradius_normalized_dedupes_and_sorts():
    br = BlastRadius(
        prefixes_lost=[
            PrefixLost(node="r3", prefix="10.0.0.2/32"),
            PrefixLost(node="r3", prefix="10.0.0.2/32"),  # dup
            PrefixLost(node="r1", prefix="10.0.0.4/32"),
        ]
    )
    norm = br.normalized()
    keys = [e.key for e in norm.prefixes_lost]
    assert len(keys) == 2
    assert keys == sorted(keys)


def test_blastradius_key_sets_shape():
    br = BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")])
    ks = br.key_sets()
    assert set(ks) == {"sessions", "prefixes", "reachability"}
    assert ks["sessions"] == {"bgp|vrf=default|node=r1|peer_ip=10.0.0.2"}
    assert ks["prefixes"] == set()


def test_blastradius_is_empty():
    assert BlastRadius().is_empty()
    assert not BlastRadius(
        reachability_lost=[ReachabilityLost(src_node="r1", dst_prefix="10.0.0.2/32")]
    ).is_empty()


def _minimal_task() -> TaskSpec:
    return TaskSpec(
        task_id="safety.bgp.shut_neighbor.square4.0001",
        family="bgp",
        intent="shut_neighbor",
        topology=schemas.Topology(name="square4", nodes=["r1", "r2"]),
        baseline=schemas.Baseline(configs={"r1": "hostname r1\n", "r2": "hostname r2\n"}),
        change=schemas.ConfigChange(
            change_id="c1", description="shut", target_nodes=["r1"],
            patch="@@ -1,1 +1,2 @@\n hostname r1\n+! changed\n",
        ),
        watched_prefixes=["10.0.0.1/32"],
    )


def test_task_round_trips_through_json():
    t = _minimal_task()
    s = to_json(t)
    again = TaskSpec.model_validate_json(s)
    assert again.task_id == t.task_id
    assert to_json(again) == s  # stable bytes


def test_task_consistency_flags_unknown_node():
    t = _minimal_task()
    t.change.target_nodes = ["r9"]
    problems = t.validate_internal_consistency()
    assert any("r9" in p for p in problems)


def test_task_consistency_flags_empty_ready_oracle_without_trap():
    t = _minimal_task()
    t.oracle.status = "ready"  # empty blast radius, is_trap False
    problems = t.validate_internal_consistency()
    assert any("is_trap" in p for p in problems)
    t.meta.is_trap = True
    assert t.validate_internal_consistency() == []
