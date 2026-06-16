"""Tolerant parser: raw LLM text -> ExtendedBlastRadius (8 dimensions) or None.

Mirrors evals/parser.py exactly — same forgiving philosophy (we grade prediction
quality, not JSON skill) — and REUSES that module's JSON extraction and the three
v0 element parsers, then adds parsers for the five extended element types
(waypoint / redundancy / filter / forwarding / scale).

Malformed elements (missing keys, bad enum values for ``transition`` / ``kind`` /
``resource``) are dropped individually; the rest are kept. Returns None only when
no JSON object can be extracted at all (-> grader marks ``invalid``).
"""

from __future__ import annotations

from typing import Any, Optional

from netbrace.core.dimensions import (
    BgpRouteWithdrawn,
    ExtendedBlastRadius,
    FilterDelta,
    ForwardingAnomaly,
    IntentViolation,
    RedundancyLoss,
    ScaleViolation,
    WaypointViolation,
)
from netbrace.core.schemas import BlastRadius
from netbrace.evals.parser import (
    _extract_json_object,
    _prefixes,
    _reach,
    _sessions,
)


def _int_or_none(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _waypoints(raw: Any) -> list[WaypointViolation]:
    out: list[WaypointViolation] = []
    for item in raw or []:
        try:
            out.append(WaypointViolation(
                src_node=str(item["src_node"]),
                dst_prefix=str(item["dst_prefix"]),
                waypoint=str(item["waypoint"]),
                vrf=str(item.get("vrf", "default")),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _redundancies(raw: Any) -> list[RedundancyLoss]:
    out: list[RedundancyLoss] = []
    for item in raw or []:
        try:
            out.append(RedundancyLoss(
                node=str(item["node"]),
                dst_prefix=str(item["dst_prefix"]),
                vrf=str(item.get("vrf", "default")),
                before_paths=_int_or_none(item.get("before_paths")),
                after_paths=_int_or_none(item.get("after_paths")),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _filters(raw: Any) -> list[FilterDelta]:
    out: list[FilterDelta] = []
    for item in raw or []:
        try:
            out.append(FilterDelta(
                node=str(item["node"]),
                src_ip=str(item["src_ip"]),
                dst_ip=str(item["dst_ip"]),
                transition=str(item["transition"]),  # Literal-validated -> drops if bad
                protocol=str(item.get("protocol", "ip")),
                dst_port=_int_or_none(item.get("dst_port")),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _anomalies(raw: Any) -> list[ForwardingAnomaly]:
    out: list[ForwardingAnomaly] = []
    for item in raw or []:
        try:
            out.append(ForwardingAnomaly(
                node=str(item["node"]),
                dst_prefix=str(item["dst_prefix"]),
                kind=str(item["kind"]),  # Literal-validated
                vrf=str(item.get("vrf", "default")),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _scales(raw: Any) -> list[ScaleViolation]:
    out: list[ScaleViolation] = []
    for item in raw or []:
        try:
            out.append(ScaleViolation(
                node=str(item["node"]),
                resource=str(item["resource"]),  # Literal-validated
                limit=_int_or_none(item.get("limit")),
                observed=_int_or_none(item.get("observed")),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _bgp_withdrawals(raw: Any) -> list[BgpRouteWithdrawn]:
    out: list[BgpRouteWithdrawn] = []
    for item in raw or []:
        try:
            out.append(BgpRouteWithdrawn(
                node=str(item["node"]),
                network=str(item["network"]),
                vrf=str(item.get("vrf", "default")),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _intents(raw: Any) -> list[IntentViolation]:
    out: list[IntentViolation] = []
    for item in raw or []:
        try:
            src = item.get("src")
            out.append(IntentViolation(
                kind=str(item["kind"]),  # Literal-validated -> drops if bad
                dst=str(item["dst"]),
                src=None if src in (None, "", "*") else str(src),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def parse_extended_prediction(text: str) -> Optional[ExtendedBlastRadius]:
    """Main entry point. Returns a normalized ExtendedBlastRadius, or None."""
    obj = _extract_json_object(text)
    if obj is None:
        return None
    base = BlastRadius(
        sessions_lost=_sessions(obj.get("sessions_lost")),
        prefixes_lost=_prefixes(obj.get("prefixes_lost")),
        reachability_lost=_reach(obj.get("reachability_lost")),
    )
    return ExtendedBlastRadius(
        base=base,
        waypoint_violations=_waypoints(obj.get("waypoint_violations")),
        redundancy_losses=_redundancies(obj.get("redundancy_losses")),
        filter_deltas=_filters(obj.get("filter_deltas")),
        forwarding_anomalies=_anomalies(obj.get("forwarding_anomalies")),
        scale_violations=_scales(obj.get("scale_violations")),
        bgp_withdrawals=_bgp_withdrawals(obj.get("bgp_withdrawals")),
        intent_violations=_intents(obj.get("intent_violations")),
    ).normalized()
