# Semantic Grading Spec v1 — prefix-canonicalization + kind-equivalence regrade

**Status: FROZEN at authoring (2026-06-12, before any per-model number was computed).**
**Author: ml-eval-engineer. Applies to: the honest regrade of the 810-sample sweep.**

This spec defines a NEW grader (`netbrace/graders/semantic_sets.py`) that replaces
the exact-string set intersection (`netbrace/graders/sets.py::score_sets`) for the
prefix-carrying dimensions, WITHOUT touching the frozen v0 core. The exact-string
grader stays in place and is reported side-by-side; this grader is the second column.

---

## 0. Why a regrade is needed (the artifact, in one paragraph)

The benchmark's headline "D7 forwarding-anomaly F1 = 0.00 on all 810 samples" is a
**grader artifact, not a model failure**. The oracle encodes D4/D7/D9-intent ground
truth as **hidden /32 flow-probes** (e.g. `anomaly|null_routed|node=spine2|dst=10.3.0.1/32`),
but (a) the prompt never discloses the probe targets — it asks for `dst_prefix: "<CIDR>"`
and lists only config-visible prefixes; and (b) the grader is literal string-set
intersection. A model that reasons correctly — names the right node, the right
anomaly kind, and the config-visible covering prefix `10.3.0.0/24` — scores 0.00
because `10.3.0.0/24 != 10.3.0.1/32`. Verified on real data: GPT-5.5, Opus 4.8, and
Gemini 3.5 all predicted `null_routed|spine2|10.3.0.0/24` on clos_summary (node-correct,
kind-correct, prefix == the most-specific config-visible cover of the probe) and all
scored 0.00 on D7. Haiku did the same on `gen_leak_ms_blackhole` (`blackhole|site3|192.0.2.0/25`
vs probe `null_routed|site3|192.0.2.1/32`). This is the literal benchmark grading its
own undisclosed sampling convention, not a measure of model reasoning.

The fix is a grader that scores predictions **at the granularity the prompt actually
exposes**, while remaining un-gameable (no credit for over-broad aggregates, exact on
all non-prefix fields). The exact-string grader is retained and reported alongside so
the delta is fully auditable.

---

## 1. Audit findings (the empirical basis — frozen before design)

Census over all 59 distinct instances (48 templated + 11 grounded) carrying a `truth`
block in the three authoritative dirs. "config-visible" = the CIDR literally appears in
the rendered prompt (configs + diff + intents + watched-prefixes line). "probe-/32" =
a /32 whose covering, more-specific prefix is config-visible but the /32 itself is not.

| Dim (truth dimension name)     | key grammar (non-prefix fields exact)                                   | CIDR field | granularity                              | artifact applies? |
|--------------------------------|-------------------------------------------------------------------------|------------|------------------------------------------|-------------------|
| `prefixes` (D2)                | `route\|node=N\|vrf=V\|prefix=P`                                         | `prefix=`  | **all 33 config-visible** (0 /32)        | **No** — canon is a no-op |
| `bgp_withdrawn` (D9)           | `bgp_withdrawn\|node=N\|vrf=V\|network=P`                                | `network=` | **all 5 config-visible** (0 /32)         | **No** — canon is a no-op |
| `reachability` (D3)            | `reach\|src=S\|dst=P\|vrf=V`                                             | `dst=`     | 10 config-CIDR + **11 probe-/32**        | **Yes** (the 11)  |
| `forwarding` (D7)              | `anomaly\|KIND\|node=N\|vrf=V\|dst=P`                                    | `dst=`     | **all 10 probe-/32** + KIND synonymy     | **Yes** (all)     |
| `waypoint` (D4)                | `waypoint\|src=S\|dst=P\|via=W\|vrf=V`                                   | `dst=`     | 1 config-/32 (loopback) + **15 probe-/32** | **Yes** (the 15)  |
| `intent` (D10)                 | `intent\|kind=K\|src=S\|dst=P`                                           | `dst=`     | 8 config-CIDR (te_pin /25, reach /24) + **8 probe-/32** (waypoint-kind) | **Yes** (the 8) |
| `redundancy` (D5)              | `redundancy\|node=N\|vrf=V\|prefix=P`                                    | `prefix=`  | **1 config-visible /32** (loopback 10.0.0.4/32) | **No** — config-/32, exact |
| `scale` (D8)                   | `scale\|node=N\|resource=R`                                             | (none)     | no CIDR at all                           | **No**            |
| `sessions` (D1)                | `bgp\|vrf=V\|node=N\|peer_ip=IP`                                         | (IP, exact)| no prefix                                | **No**            |

**Decisive facts that make the canonicalization well-defined and safe:**

1. **Every probe-/32 truth key (44 total) has a config-visible covering prefix.** Zero
   probe-/32 keys lack a cover. So canonicalization never has to invent a target.
   - Most-specific cover distribution: **34 keys cover at /25**, **10 cover at /24**.
   - The /25 covers are the `gen_leak_ms` more-specific halves (a leak-more-specific
     mechanism deliberately splits a /24 into /25 halves; the watched-prefixes line
     lists BOTH the /24 and the relevant /25 → /25 is the correct, most-specific cover).

2. **The 2 config-visible /32 loopbacks** (`ecmp4` redundancy, `waypoint4` waypoint →
   `10.0.0.4/32`) have **no broader config-visible cover** — the only covering
   config-visible prefix is the /32 itself. So "most-specific config-visible covering
   prefix" maps a config-/32 to itself, and the containment rule degenerates to
   **exact /32 match** for them automatically. **No per-instance or per-dimension
   special-casing is required**: the single canonicalization rule handles config-/32
   loopbacks and probe-/32s correctly.

3. **D2 (`prefixes`) and D9 (`bgp_withdrawn`) carry only config-visible CIDRs.** Their
   canonical map is the identity, so the semantic grader **must not move them** — this
   is the cross-check that the regrade is conservative (D2 mean F1 must be unchanged).

---

## 2. The semantic matching rules (FROZEN)

### 2.1 Key parsing

Each truth/prediction key is parsed back into a typed record:
`(dim, ordered-fixed-fields..., cidr_or_None)`. The fixed (non-prefix) fields per dim:

- `prefixes`:     `(node, vrf)` + prefix
- `bgp_withdrawn`:`(node, vrf)` + network
- `reachability`: `(src, vrf)` + dst
- `forwarding`:   `(node, vrf, KIND_CLASS)` + dst   — see 2.3 for KIND_CLASS
- `waypoint`:     `(src, via, vrf)` + dst
- `intent`:       `(kind, src)` + dst                — `dst` may be a prefix OR a node
- `redundancy`:   `(node, vrf)` + prefix
- `scale`:        `(node, resource)` + (no cidr)     — graded by exact string, unchanged
- `sessions`:     `(node, peer_ip, vrf)` + (no cidr) — graded by exact string, unchanged

All fixed fields are matched **exactly** (string equality on the already-canonicalized
node/src/via/vrf/kind values). Only the single CIDR slot gets prefix-semantic matching.
`scale` and `sessions` have no CIDR slot → they fall through to exact-string set
intersection, identical to the old grader (must be bit-identical — unit-tested).

`intent` `dst` may be a node (for `isolation`-kind) rather than a prefix. The parser
tries CIDR parse; on failure the slot is treated as a non-CIDR exact-match token (so
node-dst intents are graded exactly, never canonicalized). None of the 16 observed
intent keys are node-dst, but the rule is defined so it is total.

### 2.2 Canonicalization (truth side only)

Given the instance's set of **config-visible prefixes** `CFG` (every CIDR that
literally appears in the rendered prompt: configs, diff, intents prose, watched line),
the **canonical prefix** of a truth CIDR `t` is:

> `canon(t)` = the **most-specific** prefix in `CFG` that **contains or equals** `t`.
> If no prefix in `CFG` covers `t`, `canon(t) = t` itself (degenerate; does not occur
> in this dataset — all 44 probe-/32 keys have a cover).

This is computed **per instance**, from that instance's own prompt. It is purely a
function of the saved artifacts — no oracle, no API, deterministic.

Predictions are **never** canonicalized — only the truth target's allowed-credit
granularity is set by `canon`. This is deliberate: the model is judged against the
coarsest granularity the prompt let it reach, but it cannot widen its OWN prediction.

### 2.3 Forwarding-kind equivalence

For `forwarding` (D7) only, the `KIND` field is mapped to a **KIND_CLASS** before
fixed-field matching:

> `{blackhole, null_routed}` → class `"drop"`;  `loop` → class `"loop"`.

Justification (from the prompt's own contract, `safety_extended_v0.md` line 37):
> "forwarding_anomalies — traffic silently dropped (`blackhole` = no route,
> `null_routed`, `loop`), localized to the dropping node."

The prompt's gloss **conflates** `blackhole` and `null_routed` (it literally defines
`blackhole` as "no route", which is what `null_routed` is on FRR — a default discard /
unresolved route). A model cannot distinguish them from the prompt, so penalizing the
choice is grading an undisclosed labeling convention. `loop` is a **structurally
different** failure (traffic forwarded in a cycle, not dropped) and the prompt lists it
separately → it stays its own class. No truth key in the dataset uses `loop`, so this
equivalence cannot leak credit between distinct truth elements; it only collapses the
two drop-synonyms the prompt told the model are the same.

This equivalence is applied to BOTH truth and prediction kinds (it is a relabeling of
the fixed field, not a containment relaxation).

### 2.4 The match predicate (per element type, per instance)

A predicted record `p` **matches** a truth record `t` iff:

1. **All fixed fields equal** (after KIND→KIND_CLASS relabel for forwarding), AND
2. For the CIDR slot, with `c = canon(t.cidr)` and `q = p.cidr`:
   - `q` is **within-or-equal-to** `c`  (i.e. `c` contains-or-equals `q`: the prediction
     is **no broader than** the canonical cover), AND
   - `q` **contains-or-equals** `t.cidr` (the prediction is **at least as broad as the
     actual probe point** — it must actually cover the probed host/prefix).

In plain terms: **credit is granted for any prediction from the exact probe `/32` up to
(and including) the most-specific config-visible covering prefix, and for nothing
broader.** Predicting the canonical cover (`/25` or `/24`) = full credit. Predicting the
exact probe `/32` = full credit. Predicting an intermediate prefix that sits between
them and covers the probe = full credit. Predicting `0.0.0.0/0`, `10.0.0.0/8`, or the
broader `/24` when the canonical is a `/25` = **no credit** (over-broad aggregate).

For config-visible truth keys (D2, D9, te_pin /25, reachability /24, the two loopback
/32s), `canon(t.cidr) = t.cidr`, so the two conditions collapse to `q == t.cidr` —
**exact match, identical to the old grader.** This is why D2/D9 are provably unchanged.

### 2.5 Set semantics — bipartite one-to-one matching

Predictions and truths within one (instance, dimension) are matched by a
**deterministic maximum bipartite matching** (one prediction satisfies at most one
truth, and vice versa):

- Build the bipartite graph: edge `(p, t)` iff `p` matches `t` per 2.4.
- Compute a maximum matching (Hopcroft–Karp; deterministic tie-break by sorted key
  order so the result is reproducible).
- `TP` = size of the matching; `FP` = (#predictions − TP) = unmatched predictions;
  `FN` = (#truths − TP) = unmatched truths.
- Precision / recall / F1 from (TP, FP, FN) **using the exact frozen arithmetic in
  `sets.py`** (vacuous-truth convention preserved: empty pred → P=1; empty truth → R=1).

One-to-one matching prevents a single over-eager prediction from covering multiple
truths or vice versa (e.g. one `/24` prediction cannot satisfy two distinct `/25`
truths — at most one, and only if the /24 is not broader than that truth's canonical;
since the leak_ms canonicals ARE /25, a /24 prediction is over-broad and matches
neither). This is strictly more conservative than "count any covered truth."

### 2.6 Everything else is byte-identical to the old grader

- The active-type rule (a type empty in both truth & prediction is excluded from the
  macro), the macro/micro definitions, the status ladder, `exact_match`,
  `false_alarm`, and `false_session_alarm` are all **unchanged** and reuse the same
  helpers. `false_session_alarm` keys on the `sessions` dimension, which has no CIDR
  slot and is graded exactly → **FSA is provably unchanged by this grader.**
- `exact_match` is redefined to mean "every dimension's match predicate yields a
  perfect bipartite cover (TP == #pred == #truth for all dims)" — i.e. semantic exact.
  Reported separately; not part of any headline number.

---

## 3. Anti-gaming analysis (why this is not "grading on a curve")

1. **Over-broad aggregates earn nothing.** The single most dangerous gaming move —
   predict `0.0.0.0/0` everywhere and claim you "covered" every probe — earns ZERO,
   because `0.0.0.0/0` is broader than every canonical cover (rule 2.4 condition 1).
   The credit ceiling is the *most-specific* config-visible cover, not any cover.

2. **Wrong node / src / via / kind-class / vrf still fails.** Only the CIDR slot is
   relaxed. Haiku predicting `blackhole|leaf1|...` and `blackhole|leaf2|...` on
   clos_summary (truth is `spine2`) still scores those as 2 FP + 1 FN → real signal
   preserved (verified: Haiku stays materially below the frontier models on D7).

3. **The relaxation is bounded by the prompt's own disclosure.** A model can only be
   credited at a granularity the prompt actually exposed (a config-visible prefix).
   It is never credited for guessing the hidden /32 — the /32 is just the *floor* of
   the credit band, not a requirement. This makes the metric measure reasoning the
   prompt made reachable, not probe-target clairvoyance.

4. **One-to-one matching prevents double-counting.** A model cannot inflate TP by
   emitting one broad prediction that "covers" several truths; bipartite matching caps
   TP at min(#pred, #truth) and the over-broad rule already blocks the broad-cover.

5. **D2/D9 are provably untouched** (canon = identity there) → the new grader cannot
   silently inflate the dimensions that were already honest. This is the conservatism
   audit: if D2 moves, the implementation is wrong and the run must stop.

6. **FSA and the trap metric are untouched** (sessions has no CIDR slot). The
   contamination-control story (modal_by_class floor) is recomputed under the same
   grader for all systems including baselines, so the floor moves with the models — a
   relaxation that helped only models and not the floor would be suspect; we report
   both.

---

## 4. Freeze discipline

These rules are frozen as of this commit, BEFORE any per-model number is computed. If
a rule proves ambiguous mid-computation, the procedure is: STOP, document the
ambiguity here in the changelog, resolve it from first principles, and RESTART the
full computation (never patch numbers in place).

### Changelog
- **v1 (2026-06-12, initial freeze):** rules 2.1–2.6 as above. Canonical = most-specific
  config-visible covering prefix; containment credit band = [probe, canonical];
  forwarding kind class {blackhole,null_routed}=drop, loop distinct; bipartite 1:1;
  D1/D8 exact (no CIDR); D2/D9 provably identity. No ambiguity encountered in the
  audit; all 44 probe-/32 keys have a unique most-specific cover.
