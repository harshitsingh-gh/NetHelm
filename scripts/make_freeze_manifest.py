#!/usr/bin/env python
"""Generate the NetBrace v1 FREEZE MANIFEST — the auditable, byte-reproducible
record of EXACTLY which instances constitute v1, how each is graded, and which
split each headline/diagnostic dataset version draws from.

WHY THIS EXISTS (freeze-readiness blockers B2 + M5):
  * B2 — there was NO frozen v1 instance manifest. A reviewer (or a future re-run)
    had no auditable "what is v1" artifact: the instance ids, their provenance,
    seeds, families, trap labels, grader route, the pinned oracle digest, and
    headline membership were implicit in code paths that are actively edited.
  * M5 — the run recipe was DRIFTING. scripts/run_sweep.py's CLI default is now
    ``--templated-set reroutes`` (the v1 direction: the 13-family quiet-reroute
    split, origin_code held out of the headline -> 12 families), while the paper's
    older protocol paragraph still described the legacy-48 templated split
    (ipc/leak/lp/scale). A paid run relying on defaults would NOT reproduce the
    paper protocol as written. The manifest pins the truth; the run recipe
    (paper/refs/netbrace_v1_run_recipe.md) pins the COMMANDS that reproduce it.

DESIGN (so it is auditable and never lies):
  * Instances are enumerated DIRECTLY from ``netbrace.tasks.safety.scenarios`` — NOT
    from run_sweep.build_instances (which is being edited). The reroute split is
    ``scenarios.build_generated_suite_reroutes(N, base_seed=0)``; the grounded split
    is ``scenarios.build`` over ``sorted(scenarios.REGISTRY)`` minus ``{"blackhole"}``.
  * Headline membership mirrors run_sweep exactly: a reroute family NOT in
    ``run_sweep.REROUTE_DIFFSHAPE_LEAKY`` is in the HEADLINE; ``origin_code`` is the
    one held-out (diff-geometry-leaky) family -> DIAGNOSTIC-ONLY.
  * The grader route mirrors run_sweep._grade_instance: reroute instances ->
    ``grade_keysets_semantic``; grounded -> ``grade_keysets``.
  * The pinned oracle digest is recorded on every instance so the ground truth is
    bound to ``sha256:09817554db90`` (the only digest v1 GT is valid against).

REPRODUCIBILITY: the JSON is sorted-keys, contains NO timestamps inside the
instance/dataset payload, and re-generates BYTE-IDENTICAL on a second run. A
human-readable ``generated_on`` date is accepted via ``--date`` (default a fixed
placeholder) and lives ONLY in the top-level ``meta`` block so a deliberate
date-stamp never breaks byte-reproducibility of an un-stamped re-run.

OUTPUT: paper/refs/netbrace_v1_freeze_manifest.json  (a COMMITTED artifact — it is
the answer key for "what is v1", so it lives in the repo, NOT under gitignored runs/).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the repo root importable so ``scripts`` is a package even when this file is
# run directly (python scripts/make_freeze_manifest.py). run_sweep.py uses the same
# trick for its own cross-script import.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from netbrace.reporting.sweep_aggregate import reroute_family_of
from netbrace.tasks.safety import scenarios

# Import run_sweep ONLY for the two frozen membership constants (the held-out family
# set + the reroute-prefix tuple). We do NOT call build_instances (it is being
# edited); we re-derive the instances ourselves from scenarios. Keeping these two as
# the single source of truth means the manifest can never drift from the sweep's own
# headline definition.
from scripts.run_sweep import REROUTE_DIFFSHAPE_LEAKY, _REROUTE_PREFIXES

# The pinned Batfish image digest. ALL v1 ground truth is computed against this and
# only this digest (knowledge/corpus/batfish/batfish_verified_facts.md; CLAUDE.md).
PINNED_ORACLE_DIGEST = "sha256:09817554db90"

# v1 reroute split size: 13 families x 4 instances = 52, base_seed=0. This is the
# size the determinism gate (verify_determinism.py --generated 52) and the sweep
# (--n-generated 52) use, and it gives every family exactly 4 instances (2 bypass +
# 2 no_op) — full, balanced coverage of all 13 mechanisms.
V1_REROUTE_N = 52
V1_BASE_SEED = 0

# Grounded scenarios held OUT of the v1 grounded split. blackhole/square4 is the
# static-route sanity anchor the sweep excludes by default (--exclude blackhole);
# the manifest mirrors that exclusion so "grounded11" means the same 11 instances
# the paid run scores.
GROUNDED_EXCLUDE = frozenset({"blackhole"})

# Grader routes (mirror run_sweep._grade_instance).
GRADER_REROUTE = "grade_keysets_semantic"
GRADER_GROUNDED = "grade_keysets"


def _is_reroute_instance(instance_id: str) -> bool:
    """True iff the instance id is one of the 13 quiet-reroute mechanisms (mirrors
    run_sweep._is_reroute_instance, re-derived locally so the manifest does not
    depend on a private helper that may move)."""
    return instance_id.startswith(_REROUTE_PREFIXES)


def _seed_of(instance_id: str) -> int | None:
    """Recover the per-instance seed from a ``..._s<digits>`` suffix (the generators
    stamp their draw seed into the name). None for grounded (un-seeded) instances."""
    if "_s" in instance_id:
        _head, tail = instance_id.rsplit("_s", 1)
        if tail.isdigit():
            return int(tail)
    return None


def _reroute_instances() -> list[dict]:
    """Enumerate the v1 reroute split directly from the scenarios module."""
    suite = scenarios.build_generated_suite_reroutes(
        V1_REROUTE_N, base_seed=V1_BASE_SEED, include_noop=True)
    out: list[dict] = []
    for scn in suite:
        iid = scn.name
        family = reroute_family_of(iid)
        held_out = family in REROUTE_DIFFSHAPE_LEAKY
        out.append({
            "instance_id": iid,
            "split": "templated",
            "provenance": scn.provenance,  # "templated"
            "family": family,
            "base_seed": V1_BASE_SEED,
            "seed": _seed_of(iid),
            "is_trap": bool(scn.is_trap),       # bypass=True, no_op=False
            "twin": "bypass" if scn.is_trap else "no_op",
            "grader": GRADER_REROUTE,
            "oracle_digest": PINNED_ORACLE_DIGEST,
            "in_headline": not held_out,
            "diagnostic_only": held_out,
            "headline_note": (
                "diff-geometry-leaky (origin_code): a single-feature n_hunks probe "
                "separates its bypass/no_op twins -> held out of the headline, scored "
                "only in the reroute_detect_all13 diagnostic"
                if held_out else
                "leak-free under single + 2-feature probes incl diff-geometry "
                "(test_reroute_probe_leak) -> in the NetBrace-Detect headline"
            ),
        })
    return out


def _grounded_instances() -> list[dict]:
    """Enumerate the v1 grounded split directly from the registry (minus blackhole)."""
    out: list[dict] = []
    for name in sorted(scenarios.REGISTRY):
        if name in GROUNDED_EXCLUDE:
            continue
        scn = scenarios.build(name)
        out.append({
            "instance_id": scn.name,
            "registry_key": name,            # may differ from scn.name (e.g. ipc->ipc3)
            "split": "grounded",
            "provenance": scn.provenance,    # "handauthored"
            "family": name,                  # grounded family == its registry key
            "base_seed": None,
            "seed": None,
            "is_trap": bool(scn.is_trap),
            "twin": None,                    # grounded instances are not twinned
            "grader": GRADER_GROUNDED,
            "oracle_digest": PINNED_ORACLE_DIGEST,
            "in_headline": True,             # the whole grounded split is reported
            "diagnostic_only": False,
            "headline_note": "grounded incident-anchored instance (exact grader)",
        })
    return out


def _dataset_versions(reroute: list[dict], grounded: list[dict]) -> dict:
    """The three NAMED v1 dataset versions + their instance-id manifests.

    * netbrace-v1-grounded11        — the 11 grounded instances (blackhole excluded).
    * netbrace-v1-reroute-headline  — the leak-free reroute FAMILIES (origin_code +
      far_as_prepend held out). The instances that compose the headline. The family/instance
      COUNT is derived (not hard-coded in the name) so it never drifts from the held-out set.
    * netbrace-v1-reroute-all13-diag — all 13 reroute families (held-out families included);
      the DIAGNOSTIC superset (reroute_detect_all13).
    """
    head = [r for r in reroute if r["in_headline"]]
    head_fams = sorted({r["family"] for r in head})
    all_fams = sorted({r["family"] for r in reroute})
    held_fams = sorted({r["family"] for r in reroute if r["diagnostic_only"]})
    g_ids = sorted(g["instance_id"] for g in grounded)

    return {
        "netbrace-v1-grounded11": {
            "split": "grounded",
            "grader": GRADER_GROUNDED,
            "n_instances": len(grounded),
            "n_families": len({g["family"] for g in grounded}),
            "excluded_registry_keys": sorted(GROUNDED_EXCLUDE),
            "instance_ids": g_ids,
        },
        "netbrace-v1-reroute-headline": {
            "split": "templated",
            "grader": GRADER_REROUTE,
            "scored_as": "reroute_detect (NetBrace-Detect, Youden's J)",
            "n_instances": len(head),
            "n_families": len(head_fams),
            "families": head_fams,
            "held_out_families": held_fams,
            "instance_ids": sorted(r["instance_id"] for r in head),
        },
        "netbrace-v1-reroute-all13-diag": {
            "split": "templated",
            "grader": GRADER_REROUTE,
            "scored_as": "reroute_detect_all13 (diagnostic superset; NOT the headline)",
            "n_instances": len(reroute),
            "n_families": len(all_fams),
            "families": all_fams,
            "diagnostic_only_families": held_fams,
            "instance_ids": sorted(r["instance_id"] for r in reroute),
        },
    }


def build_manifest(date: str) -> dict:
    reroute = _reroute_instances()
    grounded = _grounded_instances()
    instances = sorted(reroute + grounded, key=lambda r: (r["split"], r["instance_id"]))

    n_head = sum(1 for r in reroute if r["in_headline"])
    n_diag_only = sum(1 for r in reroute if r["diagnostic_only"])

    manifest = {
        # The only date-bearing block. Kept OUT of the instance/dataset payload so an
        # un-stamped re-run is byte-identical; pass --date to stamp a release date.
        "meta": {
            "artifact": "netbrace_v1_freeze_manifest",
            "schema_version": 1,
            "generated_on": date,
            "generator": "scripts/make_freeze_manifest.py",
            "reproducible": "byte-identical on re-run (sorted keys, no internal timestamps)",
            "run_recipe": "paper/refs/netbrace_v1_run_recipe.md",
        },
        "pinned_oracle": {
            "image": "batfish/allinone:nethelm",
            "digest": PINNED_ORACLE_DIGEST,
            "note": (
                "ALL v1 ground truth is valid ONLY against this digest. Re-running "
                "the oracle on any other image invalidates the frozen GT."
            ),
        },
        "graders": {
            "reroute": {
                "fn": GRADER_REROUTE,
                "why": (
                    "reroute D4/D10 truth is HIDDEN /32 probes; a /24-naming reasoner "
                    "that names the config-visible covering prefix must score ~1.0, "
                    "not 0.5 under an exact grader"
                ),
            },
            "grounded": {
                "fn": GRADER_GROUNDED,
                "why": "exact key-set grader for the hand-authored grounded instances",
            },
        },
        "dataset_versions": _dataset_versions(reroute, grounded),
        "counts": {
            "grounded": len(grounded),
            "reroute_total": len(reroute),
            "reroute_headline": n_head,
            "reroute_diagnostic_only": n_diag_only,
            "reroute_families_total": len({r["family"] for r in reroute}),
            "reroute_families_headline": len(
                {r["family"] for r in reroute if r["in_headline"]}),
            "reroute_bypass": sum(1 for r in reroute if r["is_trap"]),
            "reroute_no_op": sum(1 for r in reroute if not r["is_trap"]),
            "v1_total_instances": len(instances),
        },
        "build_args": {
            "reroute": {
                "fn": "scenarios.build_generated_suite_reroutes",
                "n": V1_REROUTE_N,
                "base_seed": V1_BASE_SEED,
                "include_noop": True,
            },
            "grounded": {
                "fn": "scenarios.build over sorted(scenarios.REGISTRY)",
                "excluded": sorted(GROUNDED_EXCLUDE),
            },
            "held_out_families": sorted(REROUTE_DIFFSHAPE_LEAKY),
        },
        "instances": instances,
    }
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--date", default="FROZEN-PLACEHOLDER",
        help="human-readable release date stamped ONLY into meta.generated_on "
             "(default a fixed placeholder so an un-stamped re-run is byte-identical)")
    ap.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1]
                    / "paper" / "refs" / "netbrace_v1_freeze_manifest.json"),
        help="output path (default paper/refs/netbrace_v1_freeze_manifest.json)")
    args = ap.parse_args()

    manifest = build_manifest(args.date)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # sort_keys=True + trailing newline => byte-deterministic given the same --date.
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")

    c = manifest["counts"]
    print(f"wrote {out}")
    print(f"  grounded-11        : {c['grounded']} instances")
    print(f"  reroute-headline   : {c['reroute_headline']} instances "
          f"({c['reroute_families_headline']} families; "
          f"held out: {', '.join(sorted(REROUTE_DIFFSHAPE_LEAKY))})")
    print(f"  reroute-all-13-diag: {c['reroute_total']} instances "
          f"({c['reroute_families_total']} families)")
    print(f"  v1 total           : {c['v1_total_instances']} instances "
          f"(bypass={c['reroute_bypass']}, no_op={c['reroute_no_op']})")


if __name__ == "__main__":
    main()
