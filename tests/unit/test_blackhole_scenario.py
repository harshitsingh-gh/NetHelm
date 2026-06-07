"""Pure tests for the blackhole (D7) scenario (no Batfish needed).

The live D7 oracle is exercised by scripts/demo_extended_blackhole.py; here we
check the change patch applies and only removes the intended static route.
"""

from netbrace.tasks.safety import baseline_square4 as sq4
from netbrace.tasks.safety import scenario_blackhole as bh
from netbrace.topology.patches import apply_unified_diff


def test_patch_round_trips_and_removes_only_one_route():
    before = sq4.baseline_configs()["r1"]
    after = apply_unified_diff(before, bh.change_patch())
    assert "ip route 10.0.0.4/32 192.0.2.10" in before
    assert "ip route 10.0.0.4/32 192.0.2.10" not in after
    # the other two static routes on r1 survive
    assert "ip route 10.0.0.2/32 192.0.2.2" in after
    assert "ip route 10.0.0.3/32 192.0.2.6" in after


def test_change_targets_r1_only():
    assert bh.CHANGE_TARGET == "r1"
    # baseline is the unmodified square4 set
    assert bh.baseline_configs() == sq4.baseline_configs()


def test_probe_flows_well_formed():
    for src, dst in bh.PROBE_FLOWS:
        assert src in sq4.NODES
        assert dst.endswith("/32")
