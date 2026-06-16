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
# D9 — Control-plane BGP-RIB withdrawal (advertised-but-unresolvable signal)
# --------------------------------------------------------------------------- #
class BgpRouteWithdrawn(BaseModel):
    """A ``(node, vrf, network)`` that left the BGP-RIB BEST set across the change.

    This is a CONTROL-PLANE fact, deliberately distinct from D2 ``PrefixLost``
    (a main-RIB/FIB loss) and D3 ``ReachabilityLost`` (a data-plane loss). The two
    can move together (the flagship S-IPC-01: the prefix leaves the BGP RIB AND the
    FIB) or independently:

      * has-static sibling: prefix leaves the BGP BEST set (D9 fires) but a static
        backup keeps the FIB populated (D2 silent) and reachability alive (D3
        silent). D9 is what makes that sibling distinguishable from a no-op.
      * next-hop-self / recursive (class 3): the prefix can be present in the BGP
        RIB yet absent from the FIB; characterising it needs both RIBs.

    Computed from Batfish ``bgpRib`` rows whose ``Status`` contains ``BEST``,
    diffed pre→post. Deterministic by construction on a pinned snapshot pair.
    """

    node: str
    network: str
    vrf: str = "default"

    @field_validator("node")
    @classmethod
    def _node(cls, v: str) -> str:
        return canon_node(v)

    @field_validator("network")
    @classmethod
    def _network(cls, v: str) -> str:
        return canon_prefix(v)

    @property
    def key(self) -> str:
        return f"bgp_withdrawn|node={self.node}|vrf={self.vrf}|network={self.network}"


# --------------------------------------------------------------------------- #
# D10 — Intent / policy-invariant violation
# --------------------------------------------------------------------------- #
class IntentViolation(BaseModel):
    """A declared POLICY INVARIANT that HELD pre-change but is VIOLATED post-change.

    This is the dimension the connectivity/loss axes (D1-D3) structurally cannot
    catch: a change where reachability SURVIVES (D3 = ∅) yet a policy intent the
    network was carrying is broken. The flagship case is ``ipc_aggregate`` — the
    /25 more-specifics (multihoming / traffic-engineering pins) are withdrawn from
    the client while the covering /24 aggregate keeps coarse reachability alive. The
    /24 answers a ping, so D3 stays silent, but the TE intent those /25s served is
    dead.

    The ``kind`` Literal names the invariant family the oracle evaluated:
      * ``reachability``     — src must be able to reach dst (a D3-style invariant
                               but declared as a named intent the model must honor).
      * ``waypoint``         — src->dst must transit a required node.
      * ``isolation``        — src must NOT be able to reach dst (segmentation).
      * ``redundancy_floor`` — (node, dst) must keep >= ``floor`` installed paths.
      * ``te_pin``           — traffic to dst must follow the pinned more-specific
                               route (the specific prefix must be present/best at
                               src), not fall back onto a covering aggregate.

    The ``.key`` is deterministic and carries ONLY the invariant's identity
    (kind/src/dst) — NOT the free-text ``note`` (oracle-side prose) nor any live
    payload — so set-grading is stable across runs and the note never leaks into a
    graded key. ``note`` exists for human-readable oracle bookkeeping only.
    """

    kind: Literal[
        "reachability", "waypoint", "isolation", "redundancy_floor", "te_pin"
    ]
    dst: str
    src: Optional[str] = None

    @field_validator("src")
    @classmethod
    def _src(cls, v: Optional[str]) -> Optional[str]:
        return canon_node(v) if v else v

    @field_validator("dst")
    @classmethod
    def _dst(cls, v: str) -> str:
        # dst may be a prefix (te_pin / reachability) or a node (isolation): try the
        # prefix canonicalizer and fall back to the node canonicalizer so either is
        # stable. canon_prefix accepts a bare IP -> /32.
        try:
            return canon_prefix(v)
        except Exception:
            return canon_node(v)

    @property
    def key(self) -> str:
        src = "*" if self.src is None else self.src
        return f"intent|kind={self.kind}|src={src}|dst={self.dst}"


# --------------------------------------------------------------------------- #
# D8 — Scale / resource overflow
# --------------------------------------------------------------------------- #
class ScaleViolation(BaseModel):
    """A device resource that crosses its modeled limit after the change.

    The ``resource`` Literal keeps all four element types so a model MAY predict a
    ``label`` (MPLS LFIB) or ``acl_tcam`` overflow and the parser will accept it.
    But the current Batfish oracle (``ExtendedOracle._scale_violations``) only
    COMPUTES ``fib``/``rib`` ground truth — those are the resources the installed
    main-RIB route count is a valid proxy for. ``label``/``acl_tcam`` would need a
    vendor/MPLS model Batfish does not provide, so no scenario should declare a
    budget for them until such a model exists (the oracle skips them rather than
    firing the IPv4 route count against an MPLS/TCAM ceiling). See
    ``_ROUTE_COUNT_RESOURCES`` in extended_oracle.py.
    """

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


# The NEW element types, in a fixed order. The full grading surface is the
# v0 types followed by these (see EXT_ELEMENT_TYPES below). ``bgp_withdrawn`` (D9)
# precedes ``intent`` (D10), each appended at the end so every prior ordering is
# preserved as a prefix (no existing index shifts).
NEW_ELEMENT_TYPES = (
    "waypoint", "redundancy", "filter", "forwarding", "scale", "bgp_withdrawn", "intent",
)
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
    bgp_withdrawals: list[BgpRouteWithdrawn] = Field(default_factory=list)
    intent_violations: list[IntentViolation] = Field(default_factory=list)

    def normalized(self) -> "ExtendedBlastRadius":
        """Return a copy with the base and every new list deduped+sorted by key."""
        return ExtendedBlastRadius(
            base=self.base.normalized(),
            waypoint_violations=_dedupe_sort(self.waypoint_violations),
            redundancy_losses=_dedupe_sort(self.redundancy_losses),
            filter_deltas=_dedupe_sort(self.filter_deltas),
            forwarding_anomalies=_dedupe_sort(self.forwarding_anomalies),
            scale_violations=_dedupe_sort(self.scale_violations),
            bgp_withdrawals=_dedupe_sort(self.bgp_withdrawals),
            intent_violations=_dedupe_sort(self.intent_violations),
        )

    def key_sets(self) -> dict[str, set[str]]:
        """Map all 8 element-types -> set of stable keys (what the grader consumes)."""
        ks = dict(self.base.key_sets())  # sessions, prefixes, reachability
        ks["waypoint"] = {e.key for e in self.waypoint_violations}
        ks["redundancy"] = {e.key for e in self.redundancy_losses}
        ks["filter"] = {e.key for e in self.filter_deltas}
        ks["forwarding"] = {e.key for e in self.forwarding_anomalies}
        ks["scale"] = {e.key for e in self.scale_violations}
        ks["bgp_withdrawn"] = {e.key for e in self.bgp_withdrawals}
        ks["intent"] = {e.key for e in self.intent_violations}
        return ks

    def is_empty(self) -> bool:
        return self.base.is_empty() and not (
            self.waypoint_violations
            or self.redundancy_losses
            or self.filter_deltas
            or self.forwarding_anomalies
            or self.scale_violations
            or self.bgp_withdrawals
            or self.intent_violations
        )
