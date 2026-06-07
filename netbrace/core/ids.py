"""Deterministic, readable, sortable ID construction. See plan.md §4.1."""

from __future__ import annotations

import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(s: str) -> str:
    return _SLUG_RE.sub("-", s.strip().lower()).strip("-")


def task_id(protocol: str, intent: str, topo_family: str, index: int) -> str:
    """e.g. task_id('bgp','shut_neighbor','square4',1) -> safety.bgp.shut_neighbor.square4.0001"""
    return f"safety.{protocol}.{intent}.{topo_family}.{index:04d}"


def run_id(date: str, model_slug: str, suite: str, solver: str = "direct") -> str:
    """e.g. 2026-06-14_gpt4o_safety_v0_direct"""
    return f"{date}_{slug(model_slug)}_{slug(suite)}_{slug(solver)}"


def prompt_id(template_name: str, sha256_hex: str) -> str:
    return f"{template_name}:{sha256_hex[:12]}"
