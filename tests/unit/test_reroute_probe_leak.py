"""DURABLE GUARD against surface-token / positional / diff-shape LABEL LEAKS in the 13
quiet-reroute generators (the FB-3..FB-6 / M-D / line-count leak class).

THE INVARIANT this codifies. Every reroute family emits a BYPASS twin (is_trap=True) and a
diff-shape-identical NO_OP twin (is_trap=False). The ONLY legitimate discriminator is "does
the edit move traffic off the inspection waypoint", which requires reading WHICH element the
config places on the inspection path (routing reasoning). NO single MECHANICAL feature of the
diff/config -- changed-line tokens, prefix mask lengths, edited-node identity/octet/name/index,
diff +/- line counts, prepend-token counts, route-map/clause/list identifiers, address-family
of the touched prefix -- may separate bypass from no_op above chance.

HOW it is measured (honest, overfitting-resistant). For each family we build the suite EXACTLY
as the production sweep does (the same per-family seed band `base_seed + idx*_REROUTE_SEED_STRIDE`
and a production-scale per-family count), extract a broad mechanical feature set, and compute the
BEST single-feature held-out balanced-accuracy probe via STRATIFIED 2-fold cross-fit (so a
constant/label-independent predictor pins to 0.5 and a feature that only fits one fold by chance
does not pass). Because a FREE feature search overfits at finite n, we calibrate against a
LABEL-PERMUTATION NULL: a family LEAKS iff its observed held-out separability exceeds BOTH a 0.65
floor AND the p99 of the permutation null (the overfitting envelope of the same search on shuffled
labels). A real deterministic separator (e.g. `summary-only` present in only the bypass) scores
~1.0, far above any null; finite-sample nuisance correlations (a random customer-pool octet, a
3-valued community bucket) sit inside the null and do NOT fail the test.

This runs WITHOUT Batfish (pure generator output + diff inspection). The live oracle equivalence
(bypass -> {D4 waypoint, D10 intent} ONLY; no_op -> EMPTY; runs=2 byte-identical) is verified
separately in runs/oracle_verify_leakfix2_20260615/.

Provenance: closes FB-3 (clause_fallthrough AS_WAY name), FB-4 (redistribute_ad /24 mask),
FB-5 (community_lp octet/swap), M-D (agg_collapse summary-only), and the line-count holdout for
far_as_prepend / remove_dead_prepend / origin_code (now matched-count / set-origin-balanced).
"""

from __future__ import annotations

import importlib
import random
import re

import pytest

from netbrace.tasks.safety import scenarios as S

# --------------------------------------------------------------------------- #
# Production-scale build (mirrors build_generated_suite_reroutes' per-family band).
# --------------------------------------------------------------------------- #
_STRIDE = S._REROUTE_SEED_STRIDE
_GENS = S.REROUTE_GENERATORS

# Per-family instance count. The paid sweep runs n-generated >= 260 across 13 families
# round-robin, i.e. ~20 per family. We test at 20 (the production per-family scale) where
# the leaks were measured, AND at 40 (a larger draw) so a leak that only shows at one n is
# still caught. Both must pass for every family.
_EACH = (20, 40)

# Leak threshold: observed held-out separability must not exceed a 0.65 floor (a real
# discriminator clears it by a wide margin) AND must not exceed the permutation-null p99.
_FLOOR = 0.65


def _family_suite(idx: int, each: int, base_seed: int = 0):
    mod_slug, fn_name, prefix = _GENS[idx]
    mod = importlib.import_module(f"netbrace.tasks.safety.{mod_slug}")
    suite = getattr(mod, fn_name)(each, base_seed=base_seed + idx * _STRIDE)
    return suite, prefix


# --------------------------------------------------------------------------- #
# Mechanical feature extraction over the diff + the change_target's PRE config ONLY.
# (No routing reasoning, no oracle, no PRE/POST RIB -- exactly what a zero-reasoning
#  probe sees.)
# --------------------------------------------------------------------------- #
def _changed_lines(scn) -> list[str]:
    return [l for l in scn.patch.splitlines()
            if l[:1] in "+-" and l[:3] not in ("---", "+++")]


def _features(scn) -> dict:
    cl = _changed_lines(scn)
    plus = [l for l in cl if l.startswith("+")]
    minus = [l for l in cl if l.startswith("-")]
    txt = " ".join(cl)
    f: dict = {}
    # diff +/- line counts + edit kind
    f["n_plus"] = len(plus)
    f["n_minus"] = len(minus)
    f["n_changed"] = len(cl)
    f["edit_kind"] = "add" if (plus and not minus) else ("del" if (minus and not plus) else "mod")
    # prefix mask lengths present in the changed lines
    masks = re.findall(r"/(\d+)", txt)
    for m in ("24", "25", "26", "30"):
        f[f"has_{m}"] = m in masks
    f["max_mask"] = max((int(m) for m in masks), default=-1)
    f["min_mask"] = min((int(m) for m in masks), default=-1)
    # edited-node identity / loopback octet / node-list index / name suffix
    ct = scn.change_target
    pre = scn.pre_configs[ct]
    mo = re.search(r"router-id \d+\.\d+\.\d+\.(\d+)", pre)
    f["edited_octet"] = mo.group(1) if mo else "?"
    f["ct_index"] = scn.nodes.index(ct) if ct in scn.nodes else -1
    sm = re.search(r"(\d+)$", ct)
    f["ct_name_suffix"] = sm.group(1) if sm else "?"
    # surface keyword tells
    f["has_summary_only"] = "summary-only" in txt
    f["has_set_origin"] = "set origin" in txt
    # route-map / as-path-list / prefix-list identifier tokens + role-stripped prefixes
    ids = set(re.findall(
        r"\b(?:AS_[A-Z]+|RM_[A-Z0-9_]+|REDIST_[A-Z]+|CL_[A-Z]+|[A-Z]+_PL|[A-Z]+_IN|[A-Z]+_OUT)\w*",
        txt))
    f["id_tokens"] = frozenset(ids)
    f["id_prefixes"] = frozenset(re.sub(r"_?\d+$", "", t) for t in ids)
    # community local-admin bucket on the changed line
    comms = re.findall(r":(\d)\d\d\b", txt)
    f["comm_bucket"] = comms[0] if comms else "?"
    # added-/24 first octet (a customer-pool vs decoy-pool address-family tell)
    add24 = [re.match(r"\+.*?(\d+)\.\d+\.\d+\.\d+/24", l) for l in plus]
    o1 = [m.group(1) for m in add24 if m]
    f["added24_oct1"] = o1[0] if o1 else "?"
    # added / removed as-path-prepend token COUNT + delta (the prepend-count vector)
    def _pc(lines):
        for l in lines:
            if "as-path prepend" in l:
                return len(l.split("prepend", 1)[1].split())
        return -1
    f["added_prepend_n"] = _pc(plus)
    f["removed_prepend_n"] = _pc(minus)
    f["prepend_delta"] = (f["added_prepend_n"] - f["removed_prepend_n"]) \
        if (f["added_prepend_n"] >= 0 and f["removed_prepend_n"] >= 0) else 0
    return f


_SCALAR = [
    "n_plus", "n_minus", "n_changed", "edit_kind", "has_24", "has_25", "has_26", "has_30",
    "max_mask", "min_mask", "edited_octet", "ct_index", "ct_name_suffix", "has_summary_only",
    "has_set_origin", "comm_bucket", "added24_oct1", "added_prepend_n", "removed_prepend_n",
    "prepend_delta",
]


# --------------------------------------------------------------------------- #
# The probe: best single-feature held-out balanced accuracy via stratified cross-fit.
# --------------------------------------------------------------------------- #
def _rules(train):
    for k in _SCALAR:
        for v in {it[0][k] for it in train}:
            yield ("eq", k, v)
    toks = set().union(*[it[0]["id_tokens"] for it in train]) if train else set()
    for t in toks:
        yield ("tok", None, t)
    pfx = set().union(*[it[0]["id_prefixes"] for it in train]) if train else set()
    for t in pfx:
        yield ("pfx", None, t)


def _pred(rule, feat):
    kind, k, v = rule
    if kind == "eq":
        return feat[k] == v
    if kind == "tok":
        return v in feat["id_tokens"]
    return v in feat["id_prefixes"]


def _bal_acc(rule, items, inv):
    pos = [f for f, l in items if l]
    neg = [f for f, l in items if not l]
    if not pos or not neg:
        return None
    tpr = sum((_pred(rule, f) ^ inv) for f in pos) / len(pos)
    tnr = sum((not (_pred(rule, f) ^ inv)) for f in neg) / len(neg)
    return 0.5 * (tpr + tnr)


def _stratified(items):
    pos = [it for it in items if it[1]]
    neg = [it for it in items if not it[1]]
    return pos[0::2] + neg[0::2], pos[1::2] + neg[1::2]


def _crossfit(items) -> float:
    """Max over ALL rules of the held-out balanced accuracy (an attacker picks the feature
    that GENERALIZES). Symmetric (0.0 == 1.0). Averaged over the two fold directions."""
    A, B = _stratified(items)
    per_dir = []
    for train, test in ((A, B), (B, A)):
        dir_best = 0.5
        for r in set(_rules(train)):
            for inv in (False, True):
                tr = _bal_acc(r, train, inv)
                if tr is None or (tr <= 0.5 and (1 - tr) <= 0.5):
                    continue  # require it separate on TRAIN, else it is test-fold noise
                te = _bal_acc(r, test, inv)
                if te is None:
                    continue
                dir_best = max(dir_best, max(te, 1 - te))
        per_dir.append(dir_best)
    return sum(per_dir) / len(per_dir) if per_dir else 0.5


def _perm_null_p99(items, n_perm: int = 300, seed: int = 12345) -> float:
    feats = [f for f, _ in items]
    labs = [l for _, l in items]
    rng = random.Random(seed)
    out = []
    for _ in range(n_perm):
        pl = labs[:]
        rng.shuffle(pl)
        out.append(_crossfit(list(zip(feats, pl))))
    out.sort()
    return out[min(len(out) - 1, int(0.99 * len(out)))]


# --------------------------------------------------------------------------- #
# The per-family test.
# --------------------------------------------------------------------------- #
_FAMILY_IDS = [p for (_s, _f, p) in _GENS]


@pytest.mark.parametrize("idx", range(len(_GENS)), ids=_FAMILY_IDS)
@pytest.mark.parametrize("each", _EACH, ids=[f"n{n}" for n in _EACH])
def test_no_single_feature_label_leak(idx, each):
    """For EVERY reroute family at the production seed band/size, the best single mechanical
    feature must NOT separate bypass from no_op above chance (held-out balanced accuracy must
    not exceed the 0.65 floor AND must not exceed the permutation-null p99)."""
    suite, prefix = _family_suite(idx, each)
    # sanity: a balanced 50/50 bypass/no_op suite is what the metric (balanced accuracy)
    # assumes; the probe test is only meaningful on a balanced suite.
    n_trap = sum(1 for s in suite if s.is_trap)
    assert abs(n_trap - (len(suite) - n_trap)) <= 1, (prefix, "suite not ~balanced")

    items = [(_features(s), bool(s.is_trap)) for s in suite]
    obs = _crossfit(items)
    null = _perm_null_p99(items)
    leaks = obs > _FLOOR and obs > null + 1e-9
    assert not leaks, (
        f"{prefix} LEAKS at each={each}: best single-feature held-out balanced accuracy "
        f"{obs:.3f} exceeds floor {_FLOOR} AND permutation-null p99 {null:.3f}. A "
        f"zero-reasoning probe can recover the bypass/no_op label from the diff/config alone."
    )


def test_probe_fires_on_a_planted_leak():
    """Guard against a toothless probe: a synthetic suite where `summary-only` is present in
    exactly the bypass twins MUST be flagged as a leak (obs >> null)."""
    class _Fake:
        def __init__(self, trap, i):
            self.is_trap = trap
            self.change_target = "r2"
            self.pre_configs = {"r2": "router bgp 100\n bgp router-id 10.0.0.2\n"}
            tok = " summary-only" if trap else ""
            self.patch = f"+  aggregate-address 100.64.{i}.0/24{tok}\n"
            self.nodes = ["r1", "r2", "r3", "r4"]

    suite = [_Fake(i % 2 == 0, i) for i in range(20)]
    items = [(_features(s), bool(s.is_trap)) for s in suite]
    obs = _crossfit(items)
    null = _perm_null_p99(items)
    assert obs > _FLOOR and obs > null, (
        f"probe is toothless: planted summary-only leak scored obs={obs:.3f} null={null:.3f}"
    )
