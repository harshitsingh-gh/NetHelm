"""Tolerant parser: raw LLM text -> BlastRadius (or None if unparseable).

We grade *prediction quality*, not *JSON skill*. So this parser is forgiving:
  * pulls the last ```json ... ``` fenced block, else the last {...} span;
  * accepts elements as dicts {"node":..,"peer_ip":..} OR as 2-item lists
    [node, peer_ip] (the compact form some models emit);
  * coerces a bare IP to a host prefix, lowercases nodes (the schema validators
    do the canonicalization, so we just feed them strings);
  * a missing key -> empty list for that type.

Returns None ONLY when no JSON object can be extracted at all. That maps to the
grader's `invalid` status. Partial/garbled-but-JSON output still parses (and will
simply score poorly), which is what we want — invalid != wrong.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from netbrace.core.schemas import (
    BlastRadius,
    PrefixLost,
    ReachabilityLost,
    SessionLost,
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(text: str) -> Optional[dict]:
    """Return the most likely JSON object dict from arbitrary model text."""
    if not text:
        return None
    # 1) Prefer the LAST fenced ```json block (models often think first, answer last).
    fenced = _FENCE_RE.findall(text)
    candidates: list[str] = list(fenced)
    # 2) Fall back to the last balanced {...} span.
    if not candidates:
        span = _last_balanced_object(text)
        if span:
            candidates.append(span)
    for raw in reversed(candidates):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _last_balanced_object(text: str) -> Optional[str]:
    """Find the last top-level {...} with balanced braces (string-aware)."""
    end = text.rfind("}")
    while end != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(end, -1, -1):
            c = text[i]
            if esc:
                esc = False
                continue
            if c == "\\":
                esc = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "}":
                depth += 1
            elif c == "{":
                depth -= 1
                if depth == 0:
                    return text[i : end + 1]
        end = text.rfind("}", 0, end)
    return None


def _as_pair(item: Any) -> Optional[tuple[str, str]]:
    """Accept ['r1','10.0.0.2'] or {'node':'r1','peer_ip':'10.0.0.2'} style."""
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        return str(item[0]), str(item[1])
    return None


def _sessions(raw: Any) -> list[SessionLost]:
    out: list[SessionLost] = []
    for item in raw or []:
        try:
            if isinstance(item, dict):
                out.append(SessionLost(node=str(item["node"]), peer_ip=str(item["peer_ip"]),
                                        vrf=str(item.get("vrf", "default"))))
            else:
                pair = _as_pair(item)
                if pair:
                    out.append(SessionLost(node=pair[0], peer_ip=pair[1]))
        except (KeyError, ValueError, TypeError):
            continue  # drop malformed elements, keep the rest
    return out


def _prefixes(raw: Any) -> list[PrefixLost]:
    out: list[PrefixLost] = []
    for item in raw or []:
        try:
            if isinstance(item, dict):
                out.append(PrefixLost(node=str(item["node"]), prefix=str(item["prefix"]),
                                      vrf=str(item.get("vrf", "default"))))
            else:
                pair = _as_pair(item)
                if pair:
                    out.append(PrefixLost(node=pair[0], prefix=pair[1]))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _reach(raw: Any) -> list[ReachabilityLost]:
    out: list[ReachabilityLost] = []
    for item in raw or []:
        try:
            if isinstance(item, dict):
                out.append(ReachabilityLost(src_node=str(item.get("src_node") or item["src"]),
                                            dst_prefix=str(item.get("dst_prefix") or item["dst"]),
                                            vrf=str(item.get("vrf", "default"))))
            else:
                pair = _as_pair(item)
                if pair:
                    out.append(ReachabilityLost(src_node=pair[0], dst_prefix=pair[1]))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def parse_prediction(text: str) -> Optional[BlastRadius]:
    """Main entry point. Returns a normalized BlastRadius, or None if no JSON found."""
    obj = _extract_json_object(text)
    if obj is None:
        return None
    return BlastRadius(
        sessions_lost=_sessions(obj.get("sessions_lost")),
        prefixes_lost=_prefixes(obj.get("prefixes_lost")),
        reachability_lost=_reach(obj.get("reachability_lost")),
    ).normalized()
