# Publication-Safety Audit — Fresh Fleet Panel (2026-06-10)

> Six-agent independent panel convened by the new lead model (Fable 5):
> red-team-critic, research-standards-reviewer, ml-eval-engineer,
> batfish-oracle-engineer, noc-veteran, network-architect. Each agent was
> instructed to verify claims against actual code/runs (not docs) and to hunt
> for flaws the 06-08 fight and 06-09 scrutiny missed. They were not shown each
> other's output; convergent findings below were found independently by ≥2
> agents. Disputed facts were adjudicated by the lead with primary sources.
>
> **Question asked:** is the current progress, strategy, and implementation
> actually good — and is it SAFE TO PUBLISH?

---

## 0. Executive verdict

**The science is real; the reporting of it is not yet safe.** The oracle is
sound (all 9 scored dimensions verified SOUND or SOUND-WITH-DISCLOSURE, one
end-to-end live re-verification of `leak_ms` agreed exactly), the grading
pipeline is methodologically above the field bar, the novelty/moat is intact,
and the task is provably not gameable by syntactic diff-reading. But **the
project is currently configured to produce a paper a reviewer dismantles in
one paragraph**, for five reasons, all fixable, most cheap:

1. The designated validity-floor baseline (`modal_by_class`) is **degenerate —
   it equals the oracle ceiling (1.00)** in every sweep produced so far.
2. The decided headline narrative is **contradicted by the project's own data
   already on disk** (FSA_rate = 0.00; tools-gap ≈ 0.01) — and the project's
   self-assessment ("only 4 Haiku smokes exist") is stale: real N=3/N=5
   two-condition sweeps exist in `runs/` and nobody has looked at them
   strategically.
3. The instance count is inflated: **7–8 distinct mechanisms, not 12; 96 of
   ~108 instances are one mechanism.** Half the per-dimension "mean±std" cells
   on the grounded split are computed over **n=1 instance**.
4. The determinism doctrine is **not enforced on the split the paper plans to
   report**: the 96 generated instances were never gated, the gate script
   itself wedges Batfish when re-run, and the sweep harness calls the
   unchecked oracle with no retry.
5. Two scenarios' realism does not survive an FRR-literate reviewer:
   `blackhole` is CONTRIVED (the non-idiomatic static underlay *is* the
   manufactured bug), and `clos_summary` rests on a fabric asymmetry no one
   runs.

**Strategy verdict: sound and on-trend — the blast-radius/trap axis remains
novel and the verification-wall framing is well-supported. Implementation
verdict: infrastructure publication-grade, evidence pipeline not yet.**
**HotNets July 16 with full results: ~20–30% feasible. HotNets position paper
with honestly scoped claims + arXiv preprint: ~60–70% and is the recommended
play.** Detailed plan in §6.

---

## 1. What is genuinely solid (verified fresh, keep and defend)

- **Oracle soundness.** Per-dimension audit of `ExtendedOracle`
  (`netbrace/batfish/extended_oracle.py`): D1, D2, D4, D5, D9, D10 **SOUND**;
  D3, D7, D8 **SOUND-WITH-DISCLOSURE** (total-loss semantics; the
  `forwarding_setwise` footgun; the FIB-count proxy). D6 correctly deferred
  end-to-end (excluded from `SCORED_TYPES` *and* from the prompt — models are
  never penalized against an ungraded axis). The oracle engineer re-ran all 12
  registry scenarios 10× with isolated networks: **12/12 byte-identical**, and
  live-verified `leak_ms` end-to-end against his own config reading: **exact
  agreement**, including the thesis-carrying property (D1=∅, D2=∅, /25 ADDED,
  yet D3+D7 fire).
- **The grading machinery is fair.** The parser
  (`evals/extended_parser.py`) was explicitly checked for Claude-format
  favoritism and found **genuinely format-agnostic** (fenced JSON, raw JSON,
  arrays, tool-call wrappers all accepted). Canonicalization is robust
  (`10.0.0.4` ≡ `10.0.0.4/32`, `R1` ≡ `r1`). Two-stage scenario-level
  aggregation in `sweep_aggregate.py` is arithmetically correct, splits are
  separated, temperature/model-IDs/cost are manifested. `false_session_alarm`
  is correctly wired and not gameable by the empty baseline.
- **The task is not gameable by syntax.** The red-team built a pure regex
  diff-reader baseline: it scored **0.0 on 6/8 grounded traps, ≤0.06 on the
  rest** — the blast lands on a different node than the diff, so parroting
  fails. **This is strong unused evidence; add it as a formal baseline.**
- **The thesis is the right thing to test.** The noc-veteran defends both
  halves from operational experience (attribute changes don't drop sessions —
  RFC 4271 best-path recompute in place; silent withdrawal IS the 3am outage)
  and confirms the FSA metric is the genuine moat: no competing benchmark
  scores hallucinated damage.
- **The Haiku smokes do NOT uniformly floor.** Verified from
  `runs/run_ext_*haiku*/score.json`: ecmp 1.0, blackhole 0.5, waypoint 0.5,
  clos 0.27, ipc_static 0.33, leak_ms 0.0, lp_waypoint 0.0. A frontier fleet
  will spread across this — the "task impossible for everyone →
  non-discriminating → paper dead" risk is **unlikely**.
- **Novelty intact, but the moat is narrowing.** No benchmark scores an LLM's
  predicted, typed, false-positive-penalized damage set from a static diff.
  NIKA's own future-work section names Batfish-validated remediation
  prediction — its authors are the most likely group to scoop this. Velocity
  matters; ship the arXiv preprint on submission day regardless of accept.

---

## 2. KILL-level findings (paper dies if any number ships as-is)

### K1 — The validity floor equals the ceiling (found independently by 3 agents)
`modal_by_class` — the baseline the whole "this isn't memorization" argument
rests on — scores **1.00 on every dimension** in every sweep on disk
(`runs/sweep_20260609_023904/summary.md:19`,
`runs/sweep_20260609_012857/summary.md:21`): without coarsening, every
instance is its own class, so the modal prediction IS that instance's ground
truth. As the figures stand, **a trivial memorizer scores 1.00 and the LLM
scores 0.27** — the figure argues the *opposite* of the thesis. The fix path
(`--coarsen-class`, `scripts/run_sweep.py:515`) is **off by default, absent
from the documented sweep command, and has never been executed with any
model**. The grounded split (12 singleton classes) **cannot be coarsened at
all** (`baselines.py:156-157`).
**Fix:** coarsen ON by default for the templated split; verify
modal_by_class lands well below models on a fake+real probe before any figure
exists; on the grounded split declare modal-by-class undefined (N=1/class) —
never print a 1.00 baseline row next to a model row.

### K2 — The decided headline is contradicted by data already on disk
The 06-09 scrutiny decided the reframe around (a) the FSA/hallucination rate
and (b) the tools-allowed GAP. The real sweeps in `runs/` show, for
Haiku/Sonnet on the grounded split: **FSA_rate = 0.00** (models do NOT
hallucinate session loss; only the `naive_session_loss` strawman does, 0.92)
and **tools-gap ≈ 0.01** (0.27 vs 0.26; 0.32 vs 0.31). Additionally the
"tools" condition is not a tool loop — it only prepends pre-state text
(`run_sweep.py:314`) — so it cannot support an autonomy-ladder claim either
way. The scrutiny doc's premise ("only 4 single-shot Haiku smokes exist") was
stale when written.
**Fix:** treat the headline as an OPEN EMPIRICAL QUESTION. The data-supported
finding so far is **"models miss second-order control-plane and intent damage
(D9 ≈ 0.12, intent ≈ 0.08) while passing the surface checks"** — that is a
publishable thesis. Run the cheap probe (§6 step 3) across ≥4 frontier models
before locking any narrative; if frontier FSA is also ≈0, re-headline to the
miss-rate and report low FSA honestly (it is itself a calibration finding).
Either build a real tool-query condition or cut the tools-gap from the
framing. **Do not write the intro before the probe.**

### K3 — N-inflation: the benchmark is 7–8 mechanisms, not 12/108
The noc-veteran's honest count: **7 distinct failure mechanisms** (8 if
static-vs-attribute waypoint is split). Five of twelve scenarios are the M1
implicit-deny withdrawal with different graded surfaces (`mgmt_lockout`'s own
docstring admits it); all 96 generated instances are M1; only ~3 of the
generator's 5 axes carry real signal (direction, prefix-class, match-type —
not k). On the grounded split, waypoint/redundancy/scale/forwarding/intent
each fire in **exactly one scenario**, so the per-dimension table prints
`0.00±0.00` cells that are single points dressed as statistics
(`sweep_aggregate.py:34-37` returns std=0.0 for n=1 with no warning).
**Fix:** report "7–8 mechanisms; ~100 contamination-controlled instances
concentrated in the policy-withdrawal class" — never "108 scenarios." Drop or
flag mean±std where n_instances=1. Generate held-out variants for 2–3 more
mechanisms (leak_ms, lp_waypoint, clos — the generator infra exists); this
single move rescues the stats, the modal floor, and the contamination story
for those mechanisms simultaneously.

### K4 — Determinism doctrine not enforced where it matters
(a) `scripts/verify_determinism.py:64` gates **only the 12 hand-authored**
scenarios; the 96-instance PRIMARY split the paper plans to report was never
gated (a 4-instance spot check passed — encouraging, not a gate).
(b) The gate script itself is **not re-runnable**: it reuses one Batfish
network/session across 240 snapshot inits and **wedges the coordinator**
(reproduced twice: `Found no active locations matching` → cascading 400s);
the green 11/11 artifact cannot currently be regenerated by a reviewer.
(c) `run_sweep.py:304` calls bare `compute`, never `compute_checked`, with no
retry — the red-team hit a **non-deterministic Batfish flake**
(`Work terminated abnormally` on `build_generated(2)`, then 3/3 clean on
retry) that would abort a paid sweep mid-run.
(d) The generated split's dependence on the next-hop-self workaround is
undisclosed and unverified per-seed; one bad seed → silently wrong GT.
**Fix:** per-scenario fresh networks in the gate (the oracle engineer's
isolated-network run completed 12/12 clean); gate every instance that enters
the sweep at ≥10×; wrap oracle calls in retry+quarantine; disclose the
workaround for the generated split.

---

## 3. MAJOR findings (reviewer rejects; fix before submission)

- **M1 — `blackhole` (D7) is CONTRIVED.** The architect's sharpest finding:
  the recursive-next-hop blackhole exists *only because* the lab replaced the
  IGP with hand-written statics (the disclosed Batfish next-hop-self
  workaround). In a real FRR network the removed static wouldn't exist; the
  change would be a no-op. The scenario tests an artifact of the harness's own
  crutch. Rebuild it on an IGP underlay where the change removes
  `next-hop-self` or summarizes the /32 out of the IGP — or drop it and let
  leak_ms/clos carry D7. Note this also voids the noc-veteran's earlier ruling
  that "class 3 recursive next-hop is already covered by `blackhole`."
- **M2 — `clos_summary` premise.** The baked-in spine2↔leaf3 asymmetry is a
  fabric no one builds; the honest §3.2.2 relabel is disclosed but the proper
  fix (symmetric Clos + `fork_snapshot` link-down = the real RFC 7938 §5.2.3
  hazard) is worth doing — it also proves the harness handles dynamic
  triggers. The ipc family, by contrast, is **IDIOMATIC** — the withdrawn
  prefix is internally originated, so its ground truth is invariant to the
  static-underlay choice (the architect verified this explicitly; say so in
  the limitations section).
- **M3 — `lp_waypoint` / `leak_ms` realism.** lp_waypoint's statics carry
  *external* next-hops (no operator writes this) — outcome robust, config
  non-idiomatic; build the eBGP twin or re-home the LP trap onto an all-eBGP
  topology. leak_ms's transit has zero inbound policy; one benign inbound
  route-map on the victim-facing session turns "toy transit" into "transit
  forgot one filter" (a strictly better scenario).
- **M4 — Prompt-hygiene CI is theater.** `test_prompt_hygiene.py:23-34` is a
  17-word substring blocklist; the red-team wrote 10 outcome-leaking sentences
  and **all 10 passed**. It catches only the exact past phrasings. Replace
  with a real leak check (manual review of all 12 + an LLM-judge leak detector
  or held-out keyword families).
- **M5 — Model registry stale + single-vendor-heavy.**
  `run_sweep.py:49-70` pins `openai/gpt-5-2025-08-07` (two generations old;
  GPT-5.5 GA April 2026) and `gemini-2.5-pro` (Gemini 3.5 Pro is the June 2026
  frontier). Anthropic IDs are current. Refresh IDs + prices, add one
  open-weight local model (current Llama-4/Qwen3 tier via vLLM — the
  CLAUDE.md fleet list is itself stale), and report Claude-vs-non-Claude
  separation explicitly to neutralize the structural circularity charge
  (benchmark authored by Claude models, topline model is Claude).
- **M6 — Sweep observability gaps.** Raw model text is not persisted by
  `run_sweep.py` (only parsed scores) — "what did the invalids look like?" is
  unanswerable; `invalid_rate` is computed but absent from the headline table,
  so format-failure and reasoning-failure are conflated in the figure. Persist
  raw responses; add the invalid_rate column; print mean±1.96·SEM (already
  computed) not bare std. Parser hard edges: YAML and prose-bullet answers →
  scored 0; disclose.
- **M7 — D1 exact-match brittleness.** Session key requires the exact
  configured `Remote_IP`; a model naming the right adjacency via the peer's
  loopback scores 0 on D1. Doesn't bite the traps (D1 truth = ∅ → FSA is
  key-independent). Disclose rather than re-key, given the deadline.
- **M8 — Unpinned Python deps.** `pyproject.toml` has no lockfile pins
  (`pybatfish`, `pandas`, `anthropic`; `pydantic>=2` is a floor). The Batfish
  image digest pin is the important half, but a D&B artifact reviewer will
  want a lockfile. Pin before submission.

---

## 4. Citation adjudication (lead-verified against arXiv, 2026-06-10)

Two panel agents disagreed with the prior fleet on NetPress/NetArena. The
lead fetched both abstracts:

- **arXiv 2506.03231 is titled "NetArena: Dynamic Benchmarks for AI Agents in
  Network Automation."** The prior fleet's NetPress→NetArena retitle
  correction **stands**; the standards reviewer's counter-claim this round was
  the error. Cite it once, as NetArena (formerly NetPress), 2506.03231.
- **arXiv 2512.16381 (NIKA) is titled "A Network Arena for Benchmarking AI
  Agents on Network Troubleshooting"** — a *second*, distinct arena-named
  paper. This is the root of the recurring confusion. **Rule: cite both by
  arXiv ID, never by the word "Arena."**
- **arXiv 2605.12729 (agentic-NetOps survey):** the verbatim quote attributed
  to it in `scrutiny_2026-06-09.md` ("predictive blast-radius estimation for
  LLM proposals remains underspecified") **is a paraphrase, not a quote** —
  the survey mentions blast radius only as operator practice. It DOES contain
  the autonomy-ladder / verification-wall / non-bypassable-gate language.
  Cite it for the framing, not as naming our gap. Fix the scrutiny doc and
  any draft text before a reviewer checks.
- NetConfBench is at **draft-01**; landscape_table still cites -00. Update.

---

## 5. Coverage gaps (noc-veteran, for the question-base roadmap — AFTER the probe)

Ranked omissions a practitioner-reviewer will name:
1. **RPKI/ROV validity flip** — was Class 9 in the LOCKED plan, deterministic,
   cheap, modern, and never built. Highest value per unit effort.
2. **eBGP edge policy** — the registry is iBGP/RR-centric; the real blast
   lives at the edge. One customer/peer egress-filter scenario + one
   `maximum-prefix` teardown (the warning-only-vs-teardown keyword trap).
3. **Any IGP/underlay mechanism** — zero OSPF/IS-IS content today; an IGP
   scenario also retires the static-underlay crutch (fixes M1 for free).
4. **One ≥10-node topology** where the affected set can't be eyeballed (RR
   hierarchy partial-visibility, or the rebuilt symmetric Clos at larger
   scale). Renumbering 4-node topologies answers contamination, not scale.
The 2025 outage record (Cloudflare Nov-25 config-size crash, Azure
empty-array match-nothing) also shows a large *non-routing* config-failure
class — out of scope, but the paper must not claim to cover "config-change
outages" broadly. Coverage of the change-induced *routing* outage space is
honestly ~60–70%.

---

## 6. Is it safe to publish? Verdict and the ordered path

**As configured today: NO.** Running the documented sweep command and writing
the decided narrative would produce: a validity figure where a memorizer
beats every model, a headline (FSA + tools-gap) the project's own runs
contradict, an instance count (108) that decomposes to one mechanism under
review, per-dimension CIs over n=1, ground truth on an ungated split, and two
scenarios an FRR-literate reviewer kills. **Every one of these is fixable,
and none requires new spend to fix.**

**After the fixes below: YES, with scoped claims** — the oracle, grader,
determinism doctrine, trap instrumentation, and contamination design are
genuinely publication-grade, and the moat is real.

### Ordered plan (free until step 4)

1. **[hours] Fix the harness defects:** coarsen-on-by-default + grounded
   modal-by-class undefined (K1); retry/quarantine + `compute_checked` in the
   sweep path, per-scenario fresh networks in the determinism gate (K4);
   persist raw responses + invalid_rate column + SEM (M6); refresh model
   registry + prices (M5); add the regex/syntactic baseline (free win); pin
   deps (M8).
2. **[hours] Fix the reporting frame:** mechanism table (7–8) everywhere;
   kill "108"; pre-register which split carries which claim (CI claims only
   on the coarsened templated split; grounded = descriptive per-mechanism).
3. **[~$10–30] The decisive probe, BEFORE any narrative is locked:** 4
   frontier models (GPT-5.5, Gemini 3.5 Pro, Opus 4.8, one open-weight) ×
   the 12 hand-authored × N=3. Read three numbers: discrimination vs the
   coarsened modal floor, FSA_rate, second-order miss-rate (D9/intent). **The
   headline is whatever this shows.** This resolves K2 for ~1% of the budget.
4. **[~$100–300] The real sweep**, only after 1–3: ≥4 models × N≥5 ×
   (coarsened templated split + grounded split), manifest-pinned. Generate
   held-out variants for 2–3 more mechanisms first if step 3 shows the
   grounded singletons carrying headline weight (K3).
5. **[days, parallel] Validity package:** harden + re-run the determinism
   gate over everything swept; live-FRR verify the three thesis-carriers
   (`clos_summary` highest divergence risk, `leak_ms`, `lp_waypoint`);
   **line up the independent human κ labeler NOW** (longest lead time; κ≥0.7
   on ~30–100 instances; D10/D4 are the dims that need it most).
6. **[days] Config-realism fixes:** rebuild or drop `blackhole` (M1);
   symmetric Clos + link-down fork (M2); leak_ms one-filter edit (M3);
   limitations subsection (static-underlay disclosure + invariance argument
   for the ipc family; D3 total-loss; D8 proxy; FRR-only + cEOS as the
   planned second dialect).
7. **Venue call:** HotNets July 16 as a **position paper** with the probe +
   scoped sweep results, simultaneous arXiv + repo (scoop defense — NIKA's
   group is closest); hold the full benchmark (κ, second dialect, RPKI/eBGP/
   IGP classes, ≥10-node topology) for NeurIPS D&B / the next cycle, where
   the full validity bar will actually be met rather than asserted.

### The one-sentence honest claim available today
*"NetHELM scores the typed damage set an LLM predicts from a config change —
penalizing hallucinated as well as missed damage — on a Batfish-verified,
determinism-gated oracle; across 7–8 incident-grounded failure mechanisms,
current models pass surface-level checks while missing second-order
control-plane and intent damage at high rates."* Everything stronger (FSA
rates, tools-gap, autonomy-ladder) must wait for step 3's data.

---

*Panel artifacts: agent transcripts this session (red-team a2cb9e9a, standards
a4c1879b, ml-eval ab54c9aa, oracle a93001cc, noc a5f968ba, architect
ae73f7fb). Prior panels: `fight_synthesis_2026-06-08.md`,
`scrutiny_2026-06-09.md` — this audit supersedes their headline framing
(K2) and the scrutiny doc's 2605.12729 quote; it confirms their
infrastructure verdict.*
