"""Pure tests for the scenario registry (no Batfish needed)."""

from netbrace.tasks.safety import scenarios
from netbrace.topology.patches import apply_unified_diff


def test_registry_builds_all():
    for name in scenarios.REGISTRY:
        scn = scenarios.build(name)
        assert scn.change_target in scn.pre_configs
        # the patch applies cleanly to the target's baseline config
        post = scn.post_configs()
        assert post[scn.change_target] != scn.pre_configs[scn.change_target]
        # untargeted nodes are unchanged
        for n in scn.pre_configs:
            if n != scn.change_target:
                assert post[n] == scn.pre_configs[n]


def test_probe_references_are_valid_nodes():
    for name in scenarios.REGISTRY:
        scn = scenarios.build(name)
        nodes = set(scn.nodes)
        for src, _dst in scn.reachability_flows:
            assert src in nodes
        for s, _d, w in scn.waypoint_intents:
            assert s in nodes and w in nodes
        for node, _dst in scn.redundancy_targets:
            assert node in nodes
        for src, _dst in scn.forwarding_flows:
            assert src in nodes


def test_unknown_scenario_raises():
    try:
        scenarios.build("does-not-exist")
        assert False, "expected KeyError"
    except KeyError:
        pass
