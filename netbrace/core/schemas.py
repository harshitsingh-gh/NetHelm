"""Pydantic data contracts for NetHELM safety tasks.

These models are the SINGLE SOURCE OF TRUTH for every artifact written to disk.
Everything else (generator, oracle, grader, reporter) reads and writes these.

Design rules (see plan.md §4):
  * Blast-radius elements use a stable string ``key`` for set comparison.
    The key is computed canonically from the fields; never hand-build a key.
  * Node names are lowercased; prefixes are canonical CIDR.
  * Lists that represent sets are sorted+deduped via ``BlastRadius.normalized()``.

If you (a later model) need to add a field, add it as Optional with a default so
old task JSON still validates. Bump ``schema_version`` only for breaking changes.
"""

from __future__ import annotations

import ipaddress
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------- #
# Canonicalization helpers (used by validators and key builders)
# --------------------------------------------------------------------------- #
def canon_node(node: str) -> str:
    """Lowercase, strip a node name. Single source of node canonicalization."""
    return node.strip().lower()


def canon_prefix(prefix: str) -> str:
    """Canonical CIDR. A bare IP (no '/') is treated as a host route (/32 or /128)."""
    s = prefix.strip()
    if "/" not in s:
        ip = ipaddress.ip_address(s)
        s = f"{s}/{32 if ip.version == 4 else 128}"
    return str(ipaddress.ip_network(s, strict=False))


def canon_ip(ip: str) -> str:
    """Canonical bare IP address (no prefix length)."""
    return str(ipaddress.ip_address(ip.strip()))


# --------------------------------------------------------------------------- #
# Blast-radius elements. Each has a deterministic `key` property used for
# set arithmetic in the grader. NEVER compare elements by object identity.
# --------------------------------------------------------------------------- #
class SessionLost(BaseModel):
    node: str
    peer_ip: str
    vrf: str = "default"

    @field_validator("node")
    @classmethod
    def _node(cls, v: str) -> str:
        return canon_node(v)

    @field_validator("peer_ip")
    @classmethod
    def _peer(cls, v: str) -> str:
        return canon_ip(v)

    @property
    def key(self) -> str:
        return f"bgp|vrf={self.vrf}|node={self.node}|peer_ip={self.peer_ip}"


class PrefixLost(BaseModel):
    node: str
    prefix: str
    vrf: str = "default"

    @field_validator("node")
    @classmethod
    def _node(cls, v: str) -> str:
        return canon_node(v)

    @field_validator("prefix")
    @classmethod
    def _prefix(cls, v: str) -> str:
        return canon_prefix(v)

    @property
    def key(self) -> str:
        return f"route|node={self.node}|vrf={self.vrf}|prefix={self.prefix}"


class ReachabilityLost(BaseModel):
    src_node: str
    dst_prefix: str
    vrf: str = "default"

    @field_validator("src_node")
    @classmethod
    def _src(cls, v: str) -> str:
        return canon_node(v)

    @field_validator("dst_prefix")
    @classmethod
    def _dst(cls, v: str) -> str:
        return canon_prefix(v)

    @property
    def key(self) -> str:
        return f"reach|src={self.src_node}|dst={self.dst_prefix}|vrf={self.vrf}"


# The three element types we score in v0. interfaces/services are intentionally
# omitted here (see plan.md §4.3) — add them later without breaking the grader.
ELEMENT_TYPES = ("sessions", "prefixes", "reachability")


class BlastRadius(BaseModel):
    """Canonical ground-truth (or model prediction) of what a change breaks."""

    sessions_lost: list[SessionLost] = Field(default_factory=list)
    prefixes_lost: list[PrefixLost] = Field(default_factory=list)
    reachability_lost: list[ReachabilityLost] = Field(default_factory=list)

    def normalized(self) -> "BlastRadius":
        """Return a copy with each list deduped (by key) and sorted (by key).

        Call this before persisting ground truth or comparing sets so that
        equality and key-set operations are order-independent.
        """
        def dedupe_sort(items):
            by_key = {it.key: it for it in items}
            return [by_key[k] for k in sorted(by_key)]

        return BlastRadius(
            sessions_lost=dedupe_sort(self.sessions_lost),
            prefixes_lost=dedupe_sort(self.prefixes_lost),
            reachability_lost=dedupe_sort(self.reachability_lost),
        )

    def key_sets(self) -> dict[str, set[str]]:
        """Map element-type -> set of stable keys. This is what the grader consumes."""
        return {
            "sessions": {e.key for e in self.sessions_lost},
            "prefixes": {e.key for e in self.prefixes_lost},
            "reachability": {e.key for e in self.reachability_lost},
        }

    def is_empty(self) -> bool:
        return not (self.sessions_lost or self.prefixes_lost or self.reachability_lost)


# --------------------------------------------------------------------------- #
# Topology / change / task
# --------------------------------------------------------------------------- #
class Link(BaseModel):
    a_node: str
    a_intf: str
    b_node: str
    b_intf: str


class Topology(BaseModel):
    name: str
    nodes: list[str]
    links: list[Link] = Field(default_factory=list)
    routing_protocols: list[str] = Field(default_factory=lambda: ["bgp"])

    @field_validator("nodes")
    @classmethod
    def _nodes(cls, v: list[str]) -> list[str]:
        return [canon_node(n) for n in v]


class Baseline(BaseModel):
    config_format: Literal["frr"] = "frr"
    # node name -> full device config text (the BASELINE the model sees)
    configs: dict[str, str]


class ConfigChange(BaseModel):
    change_id: str
    description: str
    format: Literal["unified_diff"] = "unified_diff"
    target_nodes: list[str]
    patch: str

    @field_validator("target_nodes")
    @classmethod
    def _targets(cls, v: list[str]) -> list[str]:
        return [canon_node(n) for n in v]


class Presentation(BaseModel):
    prompt_template_id: str = "safety_direct_v0"
    operator_question: str = (
        "Which BGP sessions and prefixes will be lost after this proposed change?"
    )


class Oracle(BaseModel):
    status: Literal["pending", "ready", "error"] = "pending"
    engine: str = "batfish"
    engine_version: Optional[str] = None
    computed_at: Optional[str] = None
    deterministic: Optional[bool] = None
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    error: Optional[str] = None


class TaskMeta(BaseModel):
    is_trap: bool = False           # True => correct answer is "no impact" (empty G)
    hand_validated: bool = False
    source: str = "generated"
    notes: str = ""


class TaskSpec(BaseModel):
    schema_version: Literal["nethelm.task.v0"] = "nethelm.task.v0"
    task_id: str
    family: str                      # e.g. "bgp"
    intent: str                      # e.g. "shut_neighbor"
    difficulty: str = "easy"
    seed: int = 0
    topology: Topology
    baseline: Baseline
    change: ConfigChange
    # Only these prefixes are compared in the route diff (kills transit/connected noise).
    watched_prefixes: list[str] = Field(default_factory=list)
    presentation: Presentation = Field(default_factory=Presentation)
    oracle: Oracle = Field(default_factory=Oracle)
    meta: TaskMeta = Field(default_factory=TaskMeta)

    @field_validator("watched_prefixes")
    @classmethod
    def _watched(cls, v: list[str]) -> list[str]:
        return sorted({canon_prefix(p) for p in v})

    def validate_internal_consistency(self) -> list[str]:
        """Return a list of human-readable problems; empty list == OK.

        This is the structural validation referenced in plan.md §4.2. It does NOT
        touch Batfish — it only checks the task is self-consistent.
        """
        problems: list[str] = []
        topo_nodes = set(self.topology.nodes)

        for n in self.baseline.configs:
            if canon_node(n) not in topo_nodes:
                problems.append(f"baseline config for unknown node {n!r}")
        for n in self.change.target_nodes:
            if n not in topo_nodes:
                problems.append(f"change targets unknown node {n!r}")
        if self.oracle.status == "ready" and self.oracle.blast_radius.is_empty():
            if not self.meta.is_trap:
                problems.append(
                    "oracle is ready with empty blast radius but meta.is_trap is False"
                )
        return problems


# --------------------------------------------------------------------------- #
# Model prediction (what the LLM emits, before grading)
# --------------------------------------------------------------------------- #
class ModelPrediction(BaseModel):
    schema_version: Literal["nethelm.prediction.v0"] = "nethelm.prediction.v0"
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    rationale: str = ""


# --------------------------------------------------------------------------- #
# Run / score records
# --------------------------------------------------------------------------- #
class RunManifest(BaseModel):
    schema_version: Literal["nethelm.run_manifest.v0"] = "nethelm.run_manifest.v0"
    run_id: str
    suite_id: str
    suite_hash: str
    git_commit: Optional[str] = None
    git_dirty: Optional[bool] = None
    model: dict = Field(default_factory=dict)
    prompt_id: Optional[str] = None
    usage: dict = Field(default_factory=dict)
    environment: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    command: Optional[str] = None


ScoreStatus = Literal["pass", "partial", "fail", "invalid", "error"]


class TypeMetrics(BaseModel):
    tp: int = 0
    fp: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0


class ScoreRecord(BaseModel):
    schema_version: Literal["nethelm.score.v0"] = "nethelm.score.v0"
    task_id: str
    status: ScoreStatus
    valid_prediction: bool = True
    is_trap: bool = False
    false_alarm: bool = False        # trap task where the model predicted impact
    per_type: dict[str, TypeMetrics] = Field(default_factory=dict)
    macro_f1: float = 0.0
    micro_f1: float = 0.0
    exact_match: bool = False
    hallucinated_refs: int = 0       # predicted nodes/prefixes not in the topology
