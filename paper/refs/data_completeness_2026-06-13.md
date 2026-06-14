# NetBrace data-completeness manifest

Generated 2026-06-13 by a full audit of on-disk run artifacts. Every paper
number traces to the artifacts listed here. "Authoritative" = the data the
regrade/figures actually consume; dev/iteration sweeps are ignored.

## 1. Core backbone — 810 graded samples (regrade_semantic_20260613_101508)

| model | split | samples | instances | invalid | status |
|---|---|---|---|---|---|
| anthropic/claude-haiku-4-5-20251001 | grounded | 55 | 11 | 0 | COMPLETE |
| anthropic/claude-haiku-4-5-20251001 | templated | 240 | 48 | 0 | COMPLETE |
| anthropic/claude-opus-4-8 | grounded | 55 | 11 | 0 | COMPLETE |
| anthropic/claude-sonnet-4-6 | grounded | 55 | 11 | 0 | COMPLETE |
| gemini/gemini-3.5-flash | grounded | 55 | 11 | 0 | COMPLETE |
| openai/gpt-5.4-mini | grounded | 55 | 11 | 0 | COMPLETE |
| openai/gpt-5.4-mini | templated | 240 | 48 | 1 | COMPLETE |
| openai/gpt-5.5 | grounded | 55 | 11 | 0 | COMPLETE |
| **TOTAL** | | **810** | | | expect 810 |

Sonnet grounded = the 12k-cap re-run (sweep_20260613_093307, 0 invalid), superseding
the 4k-cap run. Gemini grounded = clean N=5 pooled from sweep_20260611_{000024,065948,
100408}; all 55 verified raw-backed (regrade gemini reconstruction: 0 missing).

## 2. Reroute extensions (templated leak_ms_reroute, 6 instances x 5)

| model | samples | invalid | source | status |
|---|---|---|---|---|
| anthropic/claude-opus-4-8 | 30 | 0 | sweep_20260613_110402 | stored |
| anthropic/claude-sonnet-4-6 | 30 | 0 | sweep_20260613_110402 | stored |
| gemini/gemini-3.5-flash | 1 | 0 | sweep_20260613_210801 | stored |
| openai/gpt-5.5 | 1 | 0 | sweep_20260613_210801 | stored |
| gpt-5.5 + gemini (full) | (collecting) | | sweep_20260613_2108xx | IN PROGRESS |

## 3. Determinism + oracle integrity
- Standalone >=10x byte-identical determinism reports: 4 on disk (latest runs/determinism_20260610_213818/report.json).
- Every authoritative sweep ran with --oracle batfish and in-sweep det_runs=2.
- Ground truth byte-identical across the Sonnet 4k vs 12k runs (regrade determinism PASS).
- Raw model outputs (responses.jsonl) preserved for every authoritative sample -> fully regradeable.

## 4. Known gaps (NOT in current paper claims)
- **Cross-vendor reroute**: GPT-5.5 + Gemini on the 6 reroute instances — COLLECTING NOW
  (closes the 'Anthropic-only reroute' limitation). Once done, all 6 models cover the reroute.
- **Full templated fleet**: Opus/GPT-5.5/Gemini/Sonnet on the 42 non-reroute templated
  instances — DISCLOSED future work (paper claims templated = Haiku+mini for the
  contamination/floor control only). ~$90 + budget; not needed for current claims.
