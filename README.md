# NetBrace

**NetBrace** is a safety benchmark for LLMs and AI agents on network-engineering
tasks. Given a proposed config diff, NetBrace scores the model's prediction of the
*typed blast-radius set* — the BGP sessions, prefixes, reachability flows, waypoint
paths, redundancy paths, forwarding states, and scale limits that an oracle (pinned
Batfish) predicts will be damaged.

The central finding: session/prefix metrics alone let models score near-perfect on
changes that silently reroute traffic without breaking reachability
(NetBrace-Detect). Models that look strong on D1–D3 collapse when scored on the
full D1–D10 surface, particularly on quiet-reroute scenarios where connectivity
survives but policy intent breaks.

---

## Scoring surface

| Dim | What it scores | Oracle |
|-----|----------------|--------|
| D1  | BGP/IGP sessions lost | live |
| D2  | Prefixes lost/withdrawn from RIB/FIB | live |
| D3  | Reachability lost (data-plane) | live |
| D4  | Waypoint / path-policy violations | live |
| D5  | Redundancy / ECMP path loss | live |
| D6  | Filter (ACL) permit-deny transitions | deferred — Batfish does not model FRR ACLs as interface packet filters; needs vendor config (Arista/IOS) |
| D7  | Forwarding anomaly (blackhole / loop) | live |
| D8  | Scale / resource limit (FIB/RIB/TCAM) overflow | live |
| D9  | BGP-RIB BEST withdrawal (control-plane signal) | live |
| D10 | Intent / policy-invariant violation (quiet reroute) | live |

**NetBrace-Detect** (the quiet-reroute headline): D10 + D9 scenarios where D1–D3
are all empty (connectivity survives) but routing intent breaks. This is the axis
where current frontier models fail most visibly.

---

## Quick start

```bash
# 1. Build the reproducible environment (creates harness/venvs/nethelm/)
bash scripts/repro_setup.sh

# 2. Verify the unit suite (no Docker/Batfish/API keys required)
harness/venvs/nethelm/bin/python -m pytest tests/unit -q
# Expected: 887 passed, 5 skipped

# 3. Query the knowledge base
./kb "blast radius"

# 4. Oracle paths need Batfish (pinned digest — see CLAUDE.md)
docker run -d --name batfish -p 9996:9996 -p 9997:9997 \
    batfish/allinone:nethelm
```

For the canonical run recipe (sweep, grade, report), see
`paper/refs/netbrace_v1_run_recipe.md` (generated alongside experiment outputs).

---

## Repository layout

```
netbrace/          Python package: core schemas, graders, oracle, CLI, tasks
  core/            Frozen v0 schemas (BlastRadius, element types) + extensions
  graders/         Precision/recall scoring over typed element sets
  batfish/         ExtendedOracle.compute() — unified D1-D10 on one snapshot pair
  tasks/safety/    Scenario generators (loud half + quiet-reroute half)
  reporting/       Sweep aggregation, figure generation
  cli.py           netbrace CLI (safety generate|oracle|grade|report)
scripts/           repro_setup.sh, sweep runners, determinism gate
tests/unit/        887 unit tests; no Docker or API keys required
harness/lab/       Containerlab topology files (gitignored venvs)
knowledge/         Local FAISS knowledge base (corpus/ + index/)
paper/refs/        Scenario catalog, sweep results, critique docs
```

---

## Reproducibility

- **Pinned Batfish image**: `batfish/allinone:nethelm@sha256:09817554db90...`
  (full digest in `CLAUDE.md`). All ground truth computed against this digest.
- **Determinism gate**: `scripts/verify_determinism.py` — 11/11 scenarios
  byte-identical across 10 repeated oracle calls.
- **Lockfile**: `requirements-lock.txt` (`pip freeze` of canonical venv, audited
  2026-06-10). Artifact reviewers: `pip install -r requirements-lock.txt`.
- **One-command setup**: `bash scripts/repro_setup.sh` (idempotent).

---

## v2 vision (NetHELM)

The harness is architected to import NetConfEval, Cornetto, NIKA, and TeleQnA/NetEval
as additional task categories. That holistic umbrella is parked as v2; v1 ships the
blast-radius axis as a standalone, citable benchmark.
