"""Model-independent baselines the sweep grades alongside every model.

Why baselines: without them "LLMs fail at multi-dimensional blast radius" is
unfalsifiable (critique_2026-06-08.md, finding #3). Each baseline is a dumb,
model-free predictor a real model MUST beat for the benchmark to be measuring
reasoning rather than a harness artifact.

The set:
  * ``empty``            — predict nothing. The recall floor. On a trap (sessions
    stay up, GT often empty on D1 but non-empty elsewhere) it gets the D1-correct
    "no session loss" for free, so it does NOT trip false_session_alarm — that is
    the point: the trap discriminates the NAIVE heuristic, not silence.
  * ``naive_session_loss`` — the documented LLM reflex: "a BGP change -> a session
    drops." Predicts ONE session loss on the change target and nothing else. On
    NetHELM traps (sessions actually stay ESTABLISHED) this is a pure false alarm:
    it scores ~0 on the real dimensions AND trips false_session_alarm. This is the
    strawman the thesis figure (false_session_alarm RATE) is contrasted against.
  * ``naive_count``      — the "obvious direct effects only" strawman: predict the
    directly-named customer prefix lost AT the change target (D2) + its reachability
    loss there (D3), and NOTHING second-order (no fan-out to other clients, no
    control-plane D9, no intent D10). Gets first-order effects, misses the blast
    STRUCTURE. A model must beat this to claim it reasons past the obvious.
  * ``modal_by_class``   — the VALIDITY FLOOR (fight_synthesis must-fix #3). For each
    scenario CLASS, predict the MODAL ground-truth element-set (the per-dimension keys
    that appear in the MAJORITY of instances of that class). If a real model cannot
    beat modal_by_class, the benchmark measures template-memorization of the modal
    blast, not reasoning. Computed in two passes over the sweep's ground truth; the
    "class" is derived WITHOUT editing scenarios.py (see ``scenario_class``).
    UNDEFINED for singleton classes (n=1 member): the modal set would equal that
    instance's own ground truth — floor == ceiling, a vacuous comparison (audit
    2026-06-10 K1). The sweep SKIPS modal_by_class on singleton-class instances and
    reports it as undefined rather than printing a degenerate 1.00 row.
  * ``syntactic_diff``   — the ZERO-ROUTING-KNOWLEDGE floor (audit 2026-06-10, red-team
    finding #4): regex the prefixes out of the diff text, predict each one lost (D2 +
    D3) at every NON-target node, predict a session loss iff the literal word
    "shutdown" appears in the diff. No topology, no protocol semantics. Measured at
    ~0.0 on the grounded traps — the strongest evidence the task is not solvable by
    syntactic diff-parroting; published as a formal floor so the claim is a number,
    not an assertion.
  * ``oracle_ceiling``   — the achievable topline: echo the ground truth (== the
    fake-oracle model). Always scores 1.0; bounds the table so modal_by_class < ceiling
    is a visible sanity check.

All baselines operate on per-dimension KEY SETS (the grader's native currency) and
are graded by ``grade_keysets`` here, which mirrors ``graders.extended.grade_extended``
exactly (same frozen ``sets.py`` arithmetic, same active-type rule, same
false_session_alarm definition) — it does not re-implement P/R/F1.
"""

from __future__ import annotations

from typing import Optional

from netbrace.core.dimensions import EXT_ELEMENT_TYPES
from netbrace.core.schemas import canon_node, canon_prefix
from netbrace.graders.extended import (
    PASS_F1_THRESHOLD,
    SCORED_TYPES,
    ExtendedScoreRecord,
)
from netbrace.graders.sets import SetScore, macro_f1, micro_f1, score_sets

KeySets = dict[str, set[str]]

BASELINE_NAMES = (
    "empty",
    "naive_session_loss",
    "naive_count",
    "syntactic_diff",
    "modal_by_class",
    "oracle_ceiling",
)


def empty_keysets() -> KeySets:
    """All dimensions empty."""
    return {t: set() for t in EXT_ELEMENT_TYPES}


# --------------------------------------------------------------------------- #
# Keyset-level grader: mirrors graders.extended.grade_extended exactly, but takes
# the already-computed key sets (so a baseline never needs to build pydantic
# elements from synthetic keys). REUSES the frozen sets.py arithmetic.
# --------------------------------------------------------------------------- #
def grade_keysets(
    pred: KeySets,
    truth: KeySets,
    *,
    is_trap: bool = False,
    task_id: str = "",
    valid_prediction: bool = True,
) -> ExtendedScoreRecord:
    """Grade prediction key sets vs truth key sets. Same status ladder, same
    active-type macro rule, same false_session_alarm definition as grade_extended."""
    from netbrace.core.schemas import TypeMetrics

    per_type: dict[str, TypeMetrics] = {}
    set_scores: list[SetScore] = []
    active_f1s: list[float] = []
    active_types: list[str] = []
    for t in SCORED_TYPES:
        p = pred.get(t, set())
        g = truth.get(t, set())
        s = score_sets(p, g)
        set_scores.append(s)
        per_type[t] = TypeMetrics(
            tp=s.tp, fp=s.fp, fn=s.fn,
            precision=s.precision, recall=s.recall, f1=s.f1,
        )
        if p or g:
            active_f1s.append(s.f1)
            active_types.append(t)

    macro = macro_f1(active_f1s) if active_f1s else 1.0
    micro = micro_f1(set_scores)
    pred_scored = {t: pred.get(t, set()) for t in SCORED_TYPES}
    truth_scored = {t: truth.get(t, set()) for t in SCORED_TYPES}
    exact = pred_scored == truth_scored

    truth_empty = not any(truth_scored.values())
    pred_empty = not any(pred_scored.values())
    false_alarm = is_trap and truth_empty and not pred_empty
    false_session_alarm = (not truth.get("sessions")) and bool(pred.get("sessions"))

    if exact:
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
        exact_match=exact,
        active_types=active_types,
    )


# --------------------------------------------------------------------------- #
# Class derivation (NO scenarios.py edit). Templated instances are named
# ``gen_ipc_<dims_label>_s<seed>`` (generator_ipc); the class is the dims_label
# (the IpcSpec axis tuple, seed-independent) -> all instances sharing a structure
# share a class. Grounded instances keep their builder name; the class is that name
# with any trailing instance suffix stripped. provenance prefixes the class so the
# templated and grounded buckets never collide.
# --------------------------------------------------------------------------- #
def scenario_class(name: str, provenance: str, coarsen: bool = False) -> str:
    """Map a scenario name + provenance to its CLASS label (for modal_by_class).

    ``coarsen`` (templated split only): the full Class-1 label is
    ``k{k}-{filtered}-{direction}-{prefix}-{match}`` — 96 distinct combos, so an
    n<=96 suite has ONE instance per class and modal_by_class degenerates to the
    oracle ceiling (a non-floor). With ``coarsen=True`` the class collapses to the
    ``{prefix}-{match}`` pair — the two axes that determine the blast-radius
    STRUCTURE (what is withdrawn/leaked/blackholed); k/filtered/direction mostly
    rescale that same structure. This makes many instances share a class at modest
    n (e.g. n=24 -> 8 classes x 3 members each), so modal_by_class is a REAL
    template-memorization floor. Grounded classes are never coarsened (each
    hand-authored mechanism is its own class by construction)."""
    if name.startswith("gen_ipc_"):
        # gen_ipc_<dims_label>_s<seed>  ->  class is the dims_label.
        body = name[len("gen_ipc_"):]
        # strip the trailing _s<seed>
        if "_s" in body:
            body = body.rsplit("_s", 1)[0]
        if coarsen:
            # dims_label = k{k}-{filtered}-{direction}-{prefix}-{match}; keep the
            # last two structural axes (prefix, match).
            parts = body.split("-")
            if len(parts) >= 2:
                body = "-".join(parts[-2:])
        return f"templated:{body}"
    if name.startswith("gen_"):
        # Other generators (gen_leak_/gen_lp_/gen_scale_, audit 2026-06-10 K3):
        # name = gen_<gen>_<dims_label>_s<seed>; the class is everything up to the
        # seed suffix. Their label IS the structural combo (6 combos each), already
        # coarse enough that instances share a class at modest n — no further
        # coarsening axis exists, so ``coarsen`` is a no-op here by design.
        body = name[len("gen_"):]
        if "_s" in body:
            body = body.rsplit("_s", 1)[0]
        return f"templated:{body}"
    return f"{provenance}:{name}"


def modal_keysets_by_class(
    truth_by_instance: dict[str, KeySets],
    class_of: dict[str, str],
) -> dict[str, KeySets]:
    """Compute the MODAL ground-truth key set per class.

    For each (class, dimension): a key is in the modal set iff it appears in a
    STRICT MAJORITY (> half) of the class's instances for that dimension. This is the
    per-element modal prediction — the most-common blast a memorizer would emit for
    the class. Ties / <=half are excluded (the modal predictor does not gamble on
    rare keys). Returns class -> modal KeySets.
    """
    from collections import Counter, defaultdict

    members: dict[str, list[str]] = defaultdict(list)
    for inst_id in truth_by_instance:
        members[class_of[inst_id]].append(inst_id)

    out: dict[str, KeySets] = {}
    for cls, insts in members.items():
        n = len(insts)
        modal: KeySets = {t: set() for t in EXT_ELEMENT_TYPES}
        for t in EXT_ELEMENT_TYPES:
            counts: Counter = Counter()
            for inst_id in insts:
                for k in truth_by_instance[inst_id].get(t, set()):
                    counts[k] += 1
            for k, c in counts.items():
                if c * 2 > n:  # strict majority
                    modal[t].add(k)
        out[cls] = modal
    return out


# --------------------------------------------------------------------------- #
# Per-instance baseline predictions (model-free). naive_count needs the scenario's
# directly-named target/prefix; we read them off a light scenario descriptor so this
# module never imports the heavy oracle.
# --------------------------------------------------------------------------- #
def naive_session_loss_keysets(change_target: str) -> KeySets:
    """One session loss on the change target, nothing else (the LLM reflex)."""
    ks = empty_keysets()
    tgt = canon_node(change_target)
    # peer_ip 0.0.0.0 is a deliberate placeholder: the heuristic does not know WHICH
    # peer; it just asserts "a session here drops" -> a guaranteed false alarm vs the
    # real (empty) D1 truth set, which is the whole point.
    ks["sessions"] = {f"bgp|vrf=default|node={tgt}|peer_ip=0.0.0.0"}
    return ks


def naive_count_keysets(change_target: str, named_prefix: Optional[str]) -> KeySets:
    """Direct effects only: the directly-named prefix lost at the change target (D2)
    + its reachability loss there (D3). No second-order fan-out, no D9/D10."""
    ks = empty_keysets()
    if named_prefix:
        tgt = canon_node(change_target)
        pfx = canon_prefix(named_prefix)
        ks["prefixes"] = {f"route|node={tgt}|vrf=default|prefix={pfx}"}
        ks["reachability"] = {f"reach|src={tgt}|dst={pfx}|vrf=default"}
    return ks


_PREFIX_RE = None  # compiled lazily so `re` stays a function-local import


def syntactic_diff_keysets(nodes: list[str], change_target: str,
                           patch_text: str) -> KeySets:
    """The zero-routing-knowledge floor (audit 2026-06-10, red-team finding #4).

    Recipe — deliberately dumb, NO topology or protocol semantics:
      * regex every ``a.b.c.d/len`` out of the diff text; keep "customer-ish"
        prefixes (drop /30 and /31 link nets — the one whitelist a config-grepper
        would also apply);
      * predict each kept prefix LOST (D2) and unreachable (D3) at every node
        EXCEPT the change target ("the change breaks it for everyone else");
      * predict one session loss at the target iff the literal word ``shutdown``
        appears in the diff (the only D1 signal visible to grep).

    The grader keys on (node, prefix) and the real blast usually lands on a
    DIFFERENT node than the diff names, so this floor measures whether the task is
    solvable by syntactic diff-parroting. Red-team measurement: ~0.0 on 6/8
    grounded traps, <=0.06 on the rest — publish the number, not the assertion.
    """
    import re
    ks = empty_keysets()
    tgt = canon_node(change_target)

    prefixes: set[str] = set()
    for m in re.finditer(r"\b(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\b", patch_text):
        pfx = m.group(1)
        plen = int(pfx.rsplit("/", 1)[1])
        if plen in (30, 31):  # link nets — not "customer-ish"
            continue
        try:
            prefixes.add(canon_prefix(pfx))
        except Exception:
            continue  # malformed octets etc. — a grepper would drop them too

    others = [canon_node(n) for n in nodes if canon_node(n) != tgt]
    for pfx in prefixes:
        for n in others:
            ks["prefixes"].add(f"route|node={n}|vrf=default|prefix={pfx}")
            ks["reachability"].add(f"reach|src={n}|dst={pfx}|vrf=default")

    if "shutdown" in patch_text:
        ks["sessions"].add(f"bgp|vrf=default|node={tgt}|peer_ip=0.0.0.0")
    return ks
