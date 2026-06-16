"""Unit tests for the ExtendedOracle determinism gate.

Covers the pure comparison logic (``assert_extended_deterministic`` and the
non-raising ``compute_extended_with_determinism_check``) using synthetic
``ExtendedBlastRadius`` objects — NO Batfish required, so these run anywhere.

The gate's contract: identical results pass and return the stable value;
divergent results raise ``NonDeterministicOracleError`` naming the differing
dimension. This is the doctrine's ">=10x byte-identical or quarantine" check for
the unified oracle, mirroring the v0 ``compute_with_determinism_check``.
"""

import pytest

from netbrace.batfish.extended_oracle import (
    NonDeterministicOracleError,
    assert_extended_deterministic,
    compute_extended_with_determinism_check,
)
from netbrace.core.dimensions import (
    BgpRouteWithdrawn,
    ExtendedBlastRadius,
    ForwardingAnomaly,
    RedundancyLoss,
    WaypointViolation,
)
from netbrace.core.schemas import BlastRadius, SessionLost


def _truth() -> ExtendedBlastRadius:
    return ExtendedBlastRadius(
        base=BlastRadius(sessions_lost=[SessionLost(node="r1", peer_ip="10.0.0.2")]),
        waypoint_violations=[
            WaypointViolation(src_node="src", dst_prefix="10.0.0.4/32", waypoint="way")
        ],
        redundancy_losses=[
            RedundancyLoss(node="leaf1", dst_prefix="10.1.0.0/24", before_paths=4, after_paths=2)
        ],
        forwarding_anomalies=[
            ForwardingAnomaly(node="r1", dst_prefix="10.0.0.9/32", kind="loop")
        ],
        bgp_withdrawals=[BgpRouteWithdrawn(node="r2", network="10.0.0.4/32")],
    ).normalized()


def test_identical_runs_pass_and_return_stable():
    truth = _truth()
    runs = [truth.model_copy(deep=True) for _ in range(10)]
    stable = assert_extended_deterministic(runs, scenario_name="synthetic")
    assert stable.key_sets() == truth.key_sets()


def test_single_result_is_accepted():
    truth = _truth()
    assert assert_extended_deterministic([truth], scenario_name="solo") is truth


def test_empty_results_rejected():
    with pytest.raises(ValueError):
        assert_extended_deterministic([], scenario_name="none")


def test_divergent_key_set_raises_and_names_dimension():
    a = _truth()
    b = a.model_copy(deep=True)
    # Drop the forwarding anomaly in one run -> a NON-deterministic forwarding dim.
    b.forwarding_anomalies = []
    b = b.normalized()
    with pytest.raises(NonDeterministicOracleError) as ei:
        assert_extended_deterministic([a, b], scenario_name="flaky")
    msg = str(ei.value)
    assert "flaky" in msg
    assert "forwarding" in msg
    assert "NON-DETERMINISTIC" in msg


def test_divergent_session_dim_named():
    a = _truth()
    b = a.model_copy(deep=True)
    b.base = BlastRadius(sessions_lost=[])  # a session appears in a only -> sessions diverge
    b = b.normalized()
    with pytest.raises(NonDeterministicOracleError) as ei:
        assert_extended_deterministic([a, b], scenario_name="flaky2")
    assert "sessions" in str(ei.value)


def test_payload_only_drift_still_flagged():
    # Same key set (redundancy key omits path counts) but different payload bytes.
    a = ExtendedBlastRadius(
        redundancy_losses=[
            RedundancyLoss(node="leaf1", dst_prefix="10.1.0.0/24", before_paths=4, after_paths=2)
        ]
    ).normalized()
    b = ExtendedBlastRadius(
        redundancy_losses=[
            RedundancyLoss(node="leaf1", dst_prefix="10.1.0.0/24", before_paths=4, after_paths=1)
        ]
    ).normalized()
    # key_sets are equal (key excludes path counts) but JSON bytes differ.
    assert a.key_sets() == b.key_sets()
    with pytest.raises(NonDeterministicOracleError) as ei:
        assert_extended_deterministic([a, b], scenario_name="payload")
    assert "payload-only" in str(ei.value)


def test_non_raising_wrapper_reports_bool():
    truth = _truth()
    stable, ok = compute_extended_with_determinism_check(
        _FakeOracle([truth.model_copy(deep=True) for _ in range(10)]), object(), runs=10
    )
    assert ok is True
    assert stable.key_sets() == truth.key_sets()

    flaky = [truth.model_copy(deep=True), ExtendedBlastRadius()]
    _, ok2 = compute_extended_with_determinism_check(_FakeOracle(flaky), object(), runs=2)
    assert ok2 is False


class _FakeOracle:
    """Stand-in for ExtendedOracle: hands out pre-baked results in order, then repeats
    the last one. Lets us exercise the wrapper without a Batfish session."""

    def __init__(self, results):
        self._results = results
        self._i = 0

    def compute(self, scenario):
        r = self._results[min(self._i, len(self._results) - 1)]
        self._i += 1
        return r
