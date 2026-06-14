"""Semantic set grading: prefix-canonicalization + kind-equivalence over key sets.

This is the SECOND grader column (the first is the exact-string
``graders/sets.py::score_sets``). It exists because the oracle encodes D4/D7/D10-intent
ground truth as hidden /32 flow-probes the prompt never discloses, so the exact-string
grader scores node-correct, kind-correct, config-visible-prefix predictions as 0.00.

The full design, audit, and anti-gaming analysis are FROZEN in
``docs/semantic_grading_spec_v1.md``. This module implements §2 of that spec EXACTLY:

  * non-prefix dimensions (sessions D1, scale D8) -> exact-string set intersection,
    bit-identical to score_sets (delegated to it);
  * prefix dimensions -> bipartite one-to-one matching where a prediction matches a
    truth iff all fixed fields are equal AND the predicted prefix lies in the credit
    band [probe, canonical], where canonical = the most-specific config-visible
    covering prefix of the probe for that instance;
  * forwarding kind {blackhole, null_routed} collapse to one class "drop"; loop distinct.

It does NOT touch the frozen v0 core (schemas.py / sets.py / dimensions.py): it parses
the same stable key strings those modules emit, reuses the SetScore arithmetic from
sets.py, and reuses canon_prefix from schemas.py. Nothing here is imported by the
frozen grading path.

Deterministic by construction (sorted tie-breaks in the bipartite matcher).
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from netbrace.core.schemas import canon_prefix
from netbrace.graders.sets import SetScore, score_sets

# Dimensions whose key carries a CIDR slot that gets prefix-semantic matching, and the
# name of the field that holds the CIDR. Everything else -> exact-string (delegated).
_CIDR_FIELD = {
    "prefixes": "prefix",
    "bgp_withdrawn": "network",
    "reachability": "dst",
    "forwarding": "dst",
    "waypoint": "dst",
    "intent": "dst",
    "redundancy": "prefix",
}

# Forwarding kind equivalence class (spec §2.3): blackhole == null_routed (the prompt's
# own gloss conflates them); loop is structurally distinct.
_KIND_CLASS = {"blackhole": "drop", "null_routed": "drop", "loop": "loop"}


def _net(cidr: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
    try:
        return ipaddress.ip_network(canon_prefix(cidr), strict=False)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Config-visible prefix extraction (per instance). The credit band is anchored to
# what the rendered prompt actually exposes.
# --------------------------------------------------------------------------- #
_CIDR_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\b")


def config_visible_prefixes(prompt_text: str) -> set[str]:
    """Every canonical CIDR that literally appears in the rendered prompt text.

    This is the ``CFG`` set of spec §2.2 — configs + diff + intents prose + the
    watched-prefixes line are all inside ``prompt_text``, so one regex over the whole
    prompt is the complete, deterministic source. Bare IPs are NOT treated as /32 here
    (only explicit CIDRs are config-visible prefixes); a bare loopback IP that needs to
    be a /32 cover would have appeared with its mask in an FRR ``ip address`` line.
    """
    out: set[str] = set()
    for m in _CIDR_RE.finditer(prompt_text or ""):
        n = _net(m.group(1))
        if n is not None:
            out.add(str(n))
    return out


def canonical_prefix(probe_cidr: str, cfg: set[str]) -> str:
    """The most-specific config-visible prefix that contains-or-equals ``probe_cidr``.

    Falls back to the probe itself if nothing in ``cfg`` covers it (degenerate; spec
    §2.2 notes this does not occur in the dataset). Deterministic.
    """
    pnet = _net(probe_cidr)
    if pnet is None:
        return probe_cidr
    best: tuple[int, str] | None = None
    for c in cfg:
        cnet = _net(c)
        if cnet is None or cnet.version != pnet.version:
            continue
        # cnet contains-or-equals pnet
        if pnet.subnet_of(cnet):
            cand = (cnet.prefixlen, str(cnet))
            if best is None or cand[0] > best[0]:
                best = cand
    return best[1] if best is not None else str(pnet)


# --------------------------------------------------------------------------- #
# Key parsing: stable key string -> (fixed-fields tuple, cidr-or-None).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Parsed:
    fixed: tuple  # the non-prefix identity (matched exactly)
    cidr: str | None  # the prefix slot (None for sessions/scale or unparseable)
    raw: str  # original key (tie-break + audit)


def _kv(key: str) -> dict[str, str]:
    """Parse a ``a|k1=v1|k2=v2|...`` key into {field: value}. The leading bare token
    (e.g. ``anomaly``/``route``) and any other bare token are ignored here; callers
    that need a positional token (forwarding KIND) read it separately."""
    out: dict[str, str] = {}
    for part in key.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


def parse_key(dim: str, key: str) -> _Parsed:
    """Parse one stable key of dimension ``dim`` into fixed fields + cidr slot.

    Mirrors the ``.key`` builders in core/schemas.py and core/dimensions.py. The fixed
    tuple is matched EXACTLY; only the cidr slot gets prefix-semantic matching.
    """
    kv = _kv(key)
    cfield = _CIDR_FIELD.get(dim)
    cidr = kv.get(cfield) if cfield else None

    if dim == "prefixes":
        fixed = ("prefixes", kv.get("node"), kv.get("vrf"))
    elif dim == "bgp_withdrawn":
        fixed = ("bgp_withdrawn", kv.get("node"), kv.get("vrf"))
    elif dim == "reachability":
        fixed = ("reachability", kv.get("src"), kv.get("vrf"))
    elif dim == "forwarding":
        # key shape: anomaly|KIND|node=..|vrf=..|dst=..  -> KIND is the bare 2nd token.
        toks = key.split("|")
        kind = toks[1] if len(toks) > 1 else ""
        fixed = ("forwarding", kv.get("node"), kv.get("vrf"),
                 _KIND_CLASS.get(kind, kind))
    elif dim == "waypoint":
        fixed = ("waypoint", kv.get("src"), kv.get("via"), kv.get("vrf"))
    elif dim == "intent":
        fixed = ("intent", kv.get("kind"), kv.get("src"))
    elif dim == "redundancy":
        fixed = ("redundancy", kv.get("node"), kv.get("vrf"))
    else:
        fixed = (dim, key)  # shouldn't happen for CIDR dims
        cidr = None

    # Normalize the cidr slot; if it doesn't parse as a network, treat it as a
    # non-CIDR exact token folded into the fixed tuple (spec §2.1 intent node-dst case).
    if cidr is not None:
        n = _net(cidr)
        if n is None:
            fixed = fixed + ("dst_token", cidr)
            cidr = None
        else:
            cidr = str(n)
    return _Parsed(fixed=fixed, cidr=cidr, raw=key)


# --------------------------------------------------------------------------- #
# The match predicate + deterministic bipartite one-to-one matching.
# --------------------------------------------------------------------------- #
def _cidr_credit(pred_cidr: str, truth_cidr: str, canon: str) -> bool:
    """Spec §2.4 condition 2: pred prefix is in the credit band [probe, canonical].

    pred q matches iff:  canon contains-or-equals q  (q no broader than canonical)
                    AND  q contains-or-equals probe   (q covers the actual probe point).
    For config-visible truths canon == probe, so this collapses to q == probe (exact).
    """
    q = _net(pred_cidr)
    t = _net(truth_cidr)
    c = _net(canon)
    if q is None or t is None or c is None or q.version != t.version or q.version != c.version:
        return False
    no_broader_than_canon = q.subnet_of(c)  # c contains-or-equals q
    covers_probe = t.subnet_of(q)           # q contains-or-equals probe t
    return no_broader_than_canon and covers_probe


def _matches(p: _Parsed, t: _Parsed, canon_by_truth: dict[str, str]) -> bool:
    if p.fixed != t.fixed:
        return False
    if t.cidr is None and p.cidr is None:
        return True  # no CIDR slot (or both folded) -> fixed equality already decided it
    if t.cidr is None or p.cidr is None:
        return False
    return _cidr_credit(p.cidr, t.cidr, canon_by_truth[t.raw])


def _max_bipartite(pred: list[_Parsed], truth: list[_Parsed],
                   canon_by_truth: dict[str, str]) -> int:
    """Deterministic maximum bipartite matching size (TP).

    Augmenting-path (Kuhn) over predictions, iterated in SORTED key order on both sides
    so the result is reproducible regardless of input ordering. Sizes here are tiny
    (<= a handful per dimension), so the simple O(V*E) algorithm is more than adequate
    and avoids a heavyweight dependency.
    """
    preds = sorted(pred, key=lambda x: x.raw)
    truths = sorted(truth, key=lambda x: x.raw)
    # adjacency: pred index -> list of truth indices it can match (sorted)
    adj: list[list[int]] = [
        [j for j, t in enumerate(truths) if _matches(p, t, canon_by_truth)]
        for p in preds
    ]
    match_truth = [-1] * len(truths)  # truth idx -> pred idx

    def try_assign(pi: int, seen: list[bool]) -> bool:
        for tj in adj[pi]:
            if not seen[tj]:
                seen[tj] = True
                if match_truth[tj] == -1 or try_assign(match_truth[tj], seen):
                    match_truth[tj] = pi
                    return True
        return False

    tp = 0
    for pi in range(len(preds)):
        if try_assign(pi, [False] * len(truths)):
            tp += 1
    return tp


def score_sets_semantic(
    predicted: set[str],
    expected: set[str],
    *,
    dim: str,
    config_prefixes: set[str],
) -> SetScore:
    """Semantic analogue of sets.score_sets for ONE dimension of ONE instance.

    ``dim`` selects the key grammar; ``config_prefixes`` is the instance's config-visible
    prefix set (the credit-band anchor). For non-CIDR dims (sessions/scale, or any dim
    not in _CIDR_FIELD) this delegates to the frozen exact-string score_sets so the
    result is bit-identical there.
    """
    if dim not in _CIDR_FIELD:
        return score_sets(predicted, expected)

    pred = [parse_key(dim, k) for k in predicted]
    truth = [parse_key(dim, k) for k in expected]
    canon_by_truth = {
        t.raw: (canonical_prefix(t.cidr, config_prefixes) if t.cidr else "")
        for t in truth
    }
    tp = _max_bipartite(pred, truth, canon_by_truth)
    fp = len(pred) - tp
    fn = len(truth) - tp
    precision = tp / (tp + fp) if pred else 1.0
    recall = tp / (tp + fn) if truth else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return SetScore(tp, fp, fn, precision, recall, f1)


def grade_keysets_semantic(
    pred: dict[str, set[str]],
    truth: dict[str, set[str]],
    *,
    config_prefixes: set[str],
    is_trap: bool = False,
    task_id: str = "",
    valid_prediction: bool = True,
):
    """Keyset-level semantic grader — the semantic mirror of
    ``baselines.grade_keysets``. Same status ladder, same active-type macro rule, same
    false_alarm / false_session_alarm definitions, same SCORED_TYPES; the ONLY
    difference is per-dimension scoring goes through ``score_sets_semantic`` (prefix
    canonicalization + kind class + bipartite 1:1) instead of exact-string score_sets.

    Returns an ``ExtendedScoreRecord`` (same schema the sweep persists). Imports are
    function-local to keep this module's import graph minimal and to avoid any cycle
    with the frozen grader package.
    """
    from netbrace.core.schemas import TypeMetrics
    from netbrace.graders.extended import (
        PASS_F1_THRESHOLD,
        SCORED_TYPES,
        ExtendedScoreRecord,
    )
    from netbrace.graders.sets import macro_f1, micro_f1

    per_type: dict[str, TypeMetrics] = {}
    set_scores: list[SetScore] = []
    active_f1s: list[float] = []
    active_types: list[str] = []
    # Semantic exact-cover bookkeeping for the redefined exact_match (spec §2.6).
    semantic_exact = True
    for t in SCORED_TYPES:
        p = pred.get(t, set())
        g = truth.get(t, set())
        s = score_sets_semantic(p, g, dim=t, config_prefixes=config_prefixes)
        set_scores.append(s)
        per_type[t] = TypeMetrics(
            tp=s.tp, fp=s.fp, fn=s.fn,
            precision=s.precision, recall=s.recall, f1=s.f1,
        )
        if p or g:
            active_f1s.append(s.f1)
            active_types.append(t)
        if s.fp or s.fn:
            semantic_exact = False

    macro = macro_f1(active_f1s) if active_f1s else 1.0
    micro = micro_f1(set_scores)

    truth_empty = not any(truth.get(t) for t in SCORED_TYPES)
    pred_empty = not any(pred.get(t) for t in SCORED_TYPES)
    false_alarm = is_trap and truth_empty and not pred_empty
    # sessions has no CIDR slot -> identical to the exact grader (FSA provably unchanged).
    false_session_alarm = (not truth.get("sessions")) and bool(pred.get("sessions"))

    if semantic_exact:
        status = "pass"
    elif macro >= PASS_F1_THRESHOLD:
        status = "pass"
    elif macro > 0.0:
        status = "partial"
    else:
        status = "fail"

    return ExtendedScoreRecord(
        task_id=task_id,
        status=status,
        valid_prediction=valid_prediction,
        is_trap=is_trap,
        false_alarm=false_alarm,
        false_session_alarm=false_session_alarm,
        per_type=per_type,
        macro_f1=macro,
        micro_f1=micro,
        exact_match=semantic_exact,
        active_types=active_types,
    )
