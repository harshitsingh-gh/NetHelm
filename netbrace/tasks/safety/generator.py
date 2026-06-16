"""Deterministic task generator for the square4 suite.

Produces TaskSpec objects with `oracle.status == "pending"`. The oracle
(nethelm/batfish/oracle.py) fills in ground truth afterwards.

Patches are produced with difflib.unified_diff against the mutated config, so
they are guaranteed to apply via nethelm.topology.patches.apply_unified_diff.
Generation is a pure function of (intents, count) — no randomness — so the same
inputs always yield byte-identical task JSON.

v0 intents implemented here (the "easy two" from plan.md §11):
  * shut_neighbor : remove a node's three `neighbor <peer>` lines (drops the
    session in Batfish; see plan.md §14 Q2 — removal is the Batfish-safe form).
  * remove_network: remove a node's `network 10.0.0.X/32` origination line.
    ⚠️ OPT-IN ONLY — removed from the default intents (freeze-review B3): under the v0
    main-RIB-only oracle it is a FALSE-QUIET (the static backup masks the BGP-RIB
    withdrawal, so the oracle reports an empty blast radius and rewards the wrong answer).
    Grade prefix-withdrawal via the D9 path (ExtendedOracle with bgp_watch_prefixes, e.g.
    the `ipc` scenario). The committed v0 suite is shut_neighbor-only
    (tests/unit/test_v0_remove_network_guard.py pins this).

A later model can add intents (deny_prefix, change_local_pref trap, ...) by
adding a mutation function and an entry to INTENTS. Keep each mutation a pure
str->str transform; the rest of the machinery is intent-agnostic.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from netbrace.core import ids
from netbrace.core.schemas import (
    Baseline,
    ConfigChange,
    Presentation,
    TaskSpec,
    Topology,
    Link,
)
from netbrace.tasks.safety import baseline_square4 as sq4
from netbrace.topology.patches import apply_unified_diff


@dataclass
class GenerationSpec:
    count: int = 20
    # remove_network is OPT-IN only — it is a v0-oracle FALSE-QUIET (freeze-review B3),
    # so it is NOT in the default; request it explicitly only with a D9-aware oracle.
    intents: list[str] = field(default_factory=lambda: ["shut_neighbor"])


# --------------------------------------------------------------------------- #
# Mutations: pure str -> str transforms of one device config.
# --------------------------------------------------------------------------- #
def _mutate_shut_neighbor(config: str, peer_ip: str) -> str:
    """Remove the three `neighbor <peer_ip> ...` lines for the target peer."""
    keep = [ln for ln in config.splitlines() if f"neighbor {peer_ip} " not in ln]
    out = "\n".join(keep)
    return out + "\n" if config.endswith("\n") else out


def _mutate_remove_network(config: str, prefix: str) -> str:
    """Remove the `network <prefix>` origination line."""
    keep = [ln for ln in config.splitlines() if ln.strip() != f"network {prefix}"]
    out = "\n".join(keep)
    return out + "\n" if config.endswith("\n") else out


def _unified_patch(node: str, before: str, after: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"{node}.conf",
        tofile=f"{node}.conf",
        lineterm="",
    )
    return "\n".join(diff) + "\n"


# --------------------------------------------------------------------------- #
# Build the ordered list of (intent, params) combos. Deterministic order.
# --------------------------------------------------------------------------- #
def _combos(intents: list[str]) -> list[tuple[str, dict]]:
    combos: list[tuple[str, dict]] = []
    if "shut_neighbor" in intents:
        for node in sq4.NODES:
            for peer in sq4.NODES:
                if peer == node:
                    continue
                combos.append(("shut_neighbor",
                               {"node": node, "peer_ip": sq4.LOOPBACK_IP[peer], "peer_node": peer}))
    if "remove_network" in intents:
        for node in sq4.NODES:
            combos.append(("remove_network",
                           {"node": node, "prefix": f"{sq4.LOOPBACK_IP[node]}/32"}))
    return combos


def _topology() -> Topology:
    return Topology(
        name="square4",
        nodes=list(sq4.NODES),
        links=[Link(a_node=a, a_intf=ai, b_node=b, b_intf=bi)
               for (a, ai, b, bi) in sq4.LINKS],
        routing_protocols=["bgp"],
    )


def _build_task(index: int, intent: str, params: dict) -> TaskSpec:
    base = sq4.baseline_configs()
    node = params["node"]

    if intent == "shut_neighbor":
        peer_ip = params["peer_ip"]
        after = _mutate_shut_neighbor(base[node], peer_ip)
        desc = (f"On {node}, remove the BGP neighbor {peer_ip} "
                f"(peer {params['peer_node']}) to take the session down.")
        change_id = f"change.{node}.shut_{peer_ip.replace('.', '_')}"
    elif intent == "remove_network":
        prefix = params["prefix"]
        after = _mutate_remove_network(base[node], prefix)
        desc = f"On {node}, remove `network {prefix}` so {node} stops originating its loopback in BGP."
        change_id = f"change.{node}.remove_network_{prefix.replace('.', '_').replace('/', '_')}"
    else:
        raise ValueError(f"unknown intent {intent!r}")

    patch = _unified_patch(node, base[node], after)
    # Self-check: the patch must reproduce `after` exactly, or generation is buggy.
    if apply_unified_diff(base[node], patch) != after:
        raise RuntimeError(f"generated patch does not round-trip for {intent} on {node}")

    return TaskSpec(
        task_id=ids.task_id("bgp", intent, "square4", index),
        family="bgp",
        intent=intent,
        difficulty="easy",
        seed=index,
        topology=_topology(),
        baseline=Baseline(configs=base),
        change=ConfigChange(
            change_id=change_id, description=desc, target_nodes=[node], patch=patch,
        ),
        watched_prefixes=list(sq4.WATCHED_PREFIXES),
        presentation=Presentation(),
    )


def generate(spec: GenerationSpec) -> list[TaskSpec]:
    combos = _combos(spec.intents)
    chosen = combos[: spec.count]
    tasks = [_build_task(i + 1, intent, params) for i, (intent, params) in enumerate(chosen)]
    # Structural validation: every task must be internally consistent.
    for t in tasks:
        problems = t.validate_internal_consistency()
        if problems:
            raise RuntimeError(f"{t.task_id}: {problems}")
    return tasks
