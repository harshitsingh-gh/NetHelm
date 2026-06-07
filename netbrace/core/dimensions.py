"""Extended blast-radius dimensions (D4-D8) — the multi-dimensional scoring surface.

The v0 core (``schemas.BlastRadius``) scores three element types: sessions (D1),
prefixes (D2), reachability (D3). Real network changes break things along more
axes (see ``paper/refs/blast_radius_scenario_catalog.md``). This module adds the
five additional typed elements WITHOUT touching the frozen v0 schema:

  * D4 WaypointViolation  — a required transit node is no longer on the path.
  * D5 RedundancyLoss     — an (node, prefix) lost >=1 ECMP/redundant path.
  * D6 FilterDelta        — a flow's ACL/filter action flipped (permit<->deny).
  * D7 ForwardingAnomaly  — a loop / blackhole / null-route was introduced.
  * D8 ScaleViolation     — a device resource (fib/rib/label/tcam) exceeds limit.

Each element follows the exact v0 contract: canonicalized fields + a deterministic
``key`` property for set arithmetic. ``ExtendedBlastRadius`` composes the v0
``BlastRadius`` (D1-D3) with these five lists and exposes the same
``normalized()`` / ``key_sets()`` / ``is_empty()`` surface, now over 8 types.

Grade these with ``netbrace.graders.extended.grade_extended``.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from netbrace.core.schemas import (
    BlastRadius,
    canon_ip,
    canon_node,
    canon_prefix,
)


# --------------------------------------------------------------------------- #
# D4 — Path / waypoint / intent
# --------------------------------------------------------------------------- #
class WaypointViolation(BaseModel):
    """Flow (src_node -> dst_prefix) that should transit ``waypoint`` but no longer
    does (or, for a bypass, newly does — encode that as a separate truth set)."""

    src_node: str
    dst_prefix: str
    waypoint: str
    vrf: str = "default"

    @field_validator("src_node", "waypoint")
    @classmethod
    def _node(cls, v: str) -> str:
        return canon_node(v)

    @field_validator("dst_prefix")
    @classmethod
    def _dst(cls, v: str) -> str:
        return canon_prefix(v)

    @property
    def key(self) -> str:
        return f"waypoint|src={self.src_node}|dst={self.dst_prefix}|via={self.waypoint}|vrf={self.vrf}"


# --------------------------------------------------------------------------- #
# D5 — Redundancy / capacity
# --------------------------------------------------------------------------- #
class RedundancyLoss(BaseModel):
    """An (node, dst_prefix) whose installed multipath/ECMP count dropped.

    ``before_paths``/``after_paths`` are reported for analysis but are NOT part of
    the key — set membership means "this prefix lost at least one path on this
    node". (A change from 3->2 and 3->1 are the same *element*; the magnitudes are
    attributes a finer-grained metric can compare separately.)
    """

    node: str
    dst_prefix: str
    vrf: str = "default"
    before_paths: Optional[int] = None
    after_paths: Optional[int] = None

    @field_validator("node")
    @classmethod
    def _node(cls, v: str) -> str:
        return canon_node(v)

    @field_validator("dst_prefix")
    @classmethod
    def _dst(cls, v: str) -> str:
        return canon_prefix(v)

    @property
    def key(self) -> str:
        return f"redundancy|node={self.node}|vrf={self.vrf}|prefix={self.dst_prefix}"


# --------------------------------------------------------------------------- #
# D6 — Security / segmentation (filter delta)
# --------------------------------------------------------------------------- #
class FilterDelta(BaseModel):
    """A representative flow whose filter action flipped at ``node``.

    ``transition`` distinguishes a newly-blocked flow (availability regression)
    from a newly-allowed flow (security regression / segmentation leak), so the
    two are scored as different elements.
    """

    node: str
    src_ip: str
    dst_ip: str
    transition: Literal["permit_to_deny", "deny_to_permit"]
    protocol: str = "ip"
    dst_port: Optional[int] = None

    @field_validator("node")
    @classmethod
    def _node(cls, v: str) -> str:
        return canon_node(v)

    @field_validator("src_ip", "dst_ip")
    @classmethod
    def _ip(cls, v: str) -> str:
        return canon_ip(v)

    @field_validator("protocol")
    @classmethod
    def _proto(cls, v: str) -> str:
        return v.strip().lower()

    @property
    def key(self) -> str:
        port = "*" if self.dst_port is None else self.dst_port
        return (
            f"filter|node={self.node}|{self.transition}|proto={self.protocol}"
            f"|src={self.src_ip}|dst={self.dst_ip}|dport={port}"
        )


# --------------------------------------------------------------------------- #
# D7 — Forwarding anomaly
# --------------------------------------------------------------------------- #
class ForwardingAnomaly(BaseModel):
    """A loop / blackhole / null-route introduced for traffic toward ``dst_prefix``."""

    node: str
    dst_prefix: str
    kind: Literal["loop", "blackhole", "null_routed"]
    vrf: str = "default"

    @field_validator("node")
    @classmethod
    def _node(cls, v: str) -> str:
        return canon_node(v)

    @field_validator("dst_prefix")
    @classmethod
    def _dst(cls, v: str) -> str:
        return canon_prefix(v)

    @property
    def key(self) -> str:
        return f"anomaly|{self.kind}|node={self.node}|vrf={self.vrf}|dst={self.dst_prefix}"


# --------------------------------------------------------------------------- #
# D8 — Scale / resource overflow
# --------------------------------------------------------------------------- #
class ScaleViolation(BaseModel):
    """A device resource that crosses its modeled limit after the change."""

    node: str
    resource: Literal["fib", "rib", "label", "acl_tcam"]
    limit: Optional[int] = None
    observed: Optional[int] = None

    @field_validator("node")
    @classmethod
    def _node(cls, v: str) -> str:
        return canon_node(v)

    @property
    def key(self) -> str:
        return f"scale|node={self.node}|resource={self.resource}"


# The five NEW element types, in a fixed order. The full grading surface is the
# v0 types followed by these (see EXT_ELEMENT_TYPES below).
NEW_ELEMENT_TYPES = ("waypoint", "redundancy", "filter", "forwarding", "scale")
EXT_ELEMENT_TYPES = ("sessions", "prefixes", "reachability") + NEW_ELEMENT_TYPES


def _dedupe_sort(items: list) -> list:
    """Dedupe by ``.key`` and sort by key — identical convention to BlastRadius."""
    by_key = {it.key: it for it in items}
    return [by_key[k] for k in sorted(by_key)]


class ExtendedBlastRadius(BaseModel):
    """v0 blast radius (D1-D3) composed with the D4-D8 dimensions.

    Holds the original ``BlastRadius`` as ``base`` and adds five typed lists. The
    grading surface (``key_sets``) spans all 8 element types, so one grade covers
    sessions/prefixes/reachability/waypoint/redundancy/filter/forwarding/scale.
    """

    base: BlastRadius = Field(default_factory=BlastRadius)
    waypoint_violations: list[WaypointViolation] = Field(default_factory=list)
    redundancy_losses: list[RedundancyLoss] = Field(default_factory=list)
    filter_deltas: list[FilterDelta] = Field(default_factory=list)
    forwarding_anomalies: list[ForwardingAnomaly] = Field(default_factory=list)
    scale_violations: list[ScaleViolation] = Field(default_factory=list)

    def normalized(self) -> "ExtendedBlastRadius":
        """Return a copy with the base and every new list deduped+sorted by key."""
        return ExtendedBlastRadius(
            base=self.base.normalized(),
            waypoint_violations=_dedupe_sort(self.waypoint_violations),
            redundancy_losses=_dedupe_sort(self.redundancy_losses),
            filter_deltas=_dedupe_sort(self.filter_deltas),
            forwarding_anomalies=_dedupe_sort(self.forwarding_anomalies),
            scale_violations=_dedupe_sort(self.scale_violations),
        )

    def key_sets(self) -> dict[str, set[str]]:
        """Map all 8 element-types -> set of stable keys (what the grader consumes)."""
        ks = dict(self.base.key_sets())  # sessions, prefixes, reachability
        ks["waypoint"] = {e.key for e in self.waypoint_violations}
        ks["redundancy"] = {e.key for e in self.redundancy_losses}
        ks["filter"] = {e.key for e in self.filter_deltas}
        ks["forwarding"] = {e.key for e in self.forwarding_anomalies}
        ks["scale"] = {e.key for e in self.scale_violations}
        return ks

    def is_empty(self) -> bool:
        return self.base.is_empty() and not (
            self.waypoint_violations
            or self.redundancy_losses
            or self.filter_deltas
            or self.forwarding_anomalies
            or self.scale_violations
        )
