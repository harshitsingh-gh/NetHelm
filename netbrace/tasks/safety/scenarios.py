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

from netbrace.tasks.safety import baseline_ecmp4 as ec
from netbrace.tasks.safety import baseline_waypoint4 as wp
from netbrace.tasks.safety import scenario_blackhole as bh
from netbrace.topology.patches import apply_unified_diff


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

    def post_configs(self) -> dict[str, str]:
        """Baseline with the change patch applied to the target node."""
        post = dict(self.pre_configs)
        post[self.change_target] = apply_unified_diff(post[self.change_target], self.patch)
        return post


def waypoint_scenario() -> Scenario:
    return Scenario(
        name="waypoint4",
        nodes=list(wp.NODES),
        pre_configs=wp.baseline_configs(),
        change_target=wp.CHANGE_TARGET,
        patch=wp.change_patch(),
        description="Reroute src->dst (10.0.0.4/32) off the `way` node onto `alt`.",
        intents_text="src->10.0.0.4/32 MUST transit `way` (inspection node).",
        watched_prefixes=list(wp.WATCHED_PREFIXES),
        reachability_flows=[(s, d) for (s, d, _w) in wp.WAYPOINT_INTENTS],
        waypoint_intents=list(wp.WAYPOINT_INTENTS),
    )


def blackhole_scenario() -> Scenario:
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


REGISTRY = {
    "waypoint": waypoint_scenario,
    "blackhole": blackhole_scenario,
    "ecmp": ecmp_scenario,
}


def build(name: str) -> Scenario:
    if name not in REGISTRY:
        raise KeyError(f"unknown scenario {name!r}; choose from {sorted(REGISTRY)}")
    return REGISTRY[name]()
