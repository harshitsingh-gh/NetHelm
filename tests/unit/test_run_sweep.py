"""End-to-end (fake oracle, fake model, zero-API) smoke test for the sweep, plus
the fake_oracle structural-GT checks. Confirms the spec invariants: scenario-level
aggregation (not pooled), splits reported separately, all baselines present,
modal_by_class < oracle_ceiling, naive_session_loss trips false_session_alarm.

Also includes the M-A grader-routing gate: oracle_ceiling under the reroute sweep
must score NetBrace-Detect = 1.0 / Youden_J = 1.0, which requires the semantic
grader to be wired in-sweep for reroute instances (hidden /32 probes)."""

import importlib.util
import sys
from pathlib import Path

from netbrace.reporting.baselines import BASELINE_NAMES
from netbrace.reporting.fake_oracle import fake_ground_truth
from netbrace.tasks.safety import scenarios

# load scripts/run_sweep.py as a module (scripts/ is not a package).
_SPEC = importlib.util.spec_from_file_location(
    "run_sweep", Path(__file__).resolve().parents[2] / "scripts" / "run_sweep.py")
run_sweep = importlib.util.module_from_spec(_SPEC)
sys.modules["run_sweep"] = run_sweep  # dataclass type resolution needs this
_SPEC.loader.exec_module(run_sweep)


# --------------------------------------------------------------------------- #
# fake_oracle: structural GT, D1 always empty (the trap invariant).
# --------------------------------------------------------------------------- #
def test_fake_oracle_d1_always_empty_on_traps():
    for scn in scenarios.build_generated_suite(20, base_seed=0):
        ks = fake_ground_truth(scn)
        assert ks["sessions"] == set(), f"{scn.name} should keep sessions up"


def test_fake_oracle_plain_couples_d2_d3():
    suite = scenarios.build_generated_suite(96, base_seed=0)
    plain = [s for s in suite if "-plain-" in s.name][0]
    ks = fake_ground_truth(plain)
    assert ks["prefixes"] and ks["reachability"]


def test_fake_oracle_static_is_control_plane_only():
    suite = scenarios.build_generated_suite(96, base_seed=0)
    static = [s for s in suite if "-static-" in s.name][0]
    ks = fake_ground_truth(static)
    assert ks["bgp_withdrawn"]
    assert ks["prefixes"] == set() and ks["reachability"] == set()


def test_fake_oracle_aggregate_fires_intent():
    suite = scenarios.build_generated_suite(96, base_seed=0)
    agg = [s for s in suite if "-aggregate-" in s.name][0]
    ks = fake_ground_truth(agg)
    assert ks["intent"] and ks["prefixes"]


def test_fake_oracle_handauthored_flagship():
    ks = fake_ground_truth(scenarios.build("ipc"))
    assert ks["sessions"] == set()
    assert ks["prefixes"] and ks["reachability"]


# --------------------------------------------------------------------------- #
# build_instances tags splits + classes.
# --------------------------------------------------------------------------- #
def test_build_instances_both_splits():
    insts = run_sweep.build_instances("both", n_generated=12, seed=0)
    splits = {i.split for i in insts}
    assert splits == {"templated", "grounded"}
    assert all(i.cls for i in insts)


# --------------------------------------------------------------------------- #
# Full sweep run (fake model + fake oracle), large enough that classes repeat so
# modal_by_class is a real floor below the oracle ceiling.
# --------------------------------------------------------------------------- #
def test_sweep_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = run_sweep.argparse.Namespace(
        models="fake", samples=3, split="templated", n_generated=200,
        seed=0, temperature=0.0, oracle="fake", host="127.0.0.1",
        condition="no_tools")
    summary = run_sweep.run_sweep(args)

    # model rows are keyed "model @ condition" now.
    mkey = "fake @ no_tools"
    # all baselines present
    assert set(summary["baselines"]) == set(BASELINE_NAMES)
    # splits reported separately (templated only here)
    assert "templated" in summary["models"][mkey]
    assert "grounded" not in summary["models"][mkey]

    tmpl = "templated"
    modal = summary["baselines"]["modal_by_class"][tmpl]["macro_f1"]["mean"]
    ceiling = summary["baselines"]["oracle_ceiling"][tmpl]["macro_f1"]["mean"]
    fake = summary["models"][mkey][tmpl]["macro_f1"]["mean"]

    # oracle ceiling is the achievable topline
    assert ceiling == 1.0
    # with randomized numbering across repeated classes, modal memorization collapses
    assert modal < ceiling
    # the fake stand-in model beats the modal floor
    assert fake > modal

    # naive_session_loss trips the trap (false_session_alarm rate == 1.0)
    fsa = summary["baselines"]["naive_session_loss"][tmpl]["false_session_alarm_rate"]
    assert fsa["mean"] == 1.0
    # empty does NOT trip it (silence is not a false alarm)
    assert summary["baselines"]["empty"][tmpl]["false_session_alarm_rate"]["mean"] == 0.0

    # scenario-level: n_instances is the instance count, NOT n_instances*samples
    assert summary["models"][mkey][tmpl]["n_instances"] == 200


def test_sweep_both_conditions_produce_separate_rows(tmp_path, monkeypatch):
    # The fake model ignores pre_state, so both conditions are computed; the point
    # is the harness emits a separate "model @ condition" row for each (the contrast
    # the real sweep reports). 'tools' is allowed with the fake oracle here ONLY
    # because run_sweep() does not gate it (the CLI does); pre_state stays None.
    monkeypatch.chdir(tmp_path)
    args = run_sweep.argparse.Namespace(
        models="fake", samples=2, split="grounded", n_generated=0,
        seed=0, temperature=0.0, oracle="fake", host="127.0.0.1",
        condition="no_tools,tools")
    summary = run_sweep.run_sweep(args)
    assert "fake @ no_tools" in summary["models"]
    assert "fake @ tools" in summary["models"]
    assert summary["manifest"]["conditions"] == ["no_tools", "tools"]


def test_reroute_sweep_semantic_grader_in_sweep(tmp_path, monkeypatch):
    """M-A gate: oracle_ceiling must score reroute_detect = 1.0 / Youden_J = 1.0
    on a reroute sweep, which requires the semantic grader to be wired in-sweep
    for reroute instances (the /32 probes are hidden from the prompt, so the exact
    grader would pin the oracle ceiling to 0.5 / 0.0).

    Also verifies:
    - manifest carries grader_routing provenance
    - every reroute result row has a "grader" field = "grade_keysets_semantic"
    - non-reroute rows (grounded) carry "grader" = "grade_keysets"
    """
    monkeypatch.chdir(tmp_path)
    args = run_sweep.argparse.Namespace(
        models="fake", samples=2, split="templated", n_generated=26,
        seed=0, temperature=0.0, oracle="fake", host="127.0.0.1",
        condition="no_tools", templated_set="reroutes",
        coarsen_class=True, exclude="", bypass_fraction=0.5, det_runs=2,
        limit=0, include="")
    summary = run_sweep.run_sweep(args)

    # 1. oracle_ceiling must score 1.0/1.0 (the test of correct semantic grading)
    tmpl = "templated"
    rr = summary["baselines"]["oracle_ceiling"][tmpl].get("reroute_detect")
    assert rr is not None, "reroute_detect must be populated for a reroute sweep"
    assert rr["netbrace_detect"] == 1.0, (
        f"oracle_ceiling NetBrace-Detect={rr['netbrace_detect']:.3f}; expected 1.0 "
        f"(semantic grader must be wired for reroute instances)")
    assert rr["youden_j"] == 1.0, (
        f"oracle_ceiling Youden_J={rr['youden_j']:.3f}; expected 1.0")

    # 2. empty predictor must be pinned to 0.5 / 0.0 (constant-predictor floor)
    rr_empty = summary["baselines"]["empty"][tmpl].get("reroute_detect")
    assert rr_empty is not None
    assert rr_empty["netbrace_detect"] == 0.5
    assert rr_empty["youden_j"] == 0.0

    # 3. manifest grader_routing provenance is recorded
    gr = summary["manifest"].get("grader_routing", {})
    assert gr.get("reroute_instances") == "grade_keysets_semantic"
    assert gr.get("all_other_instances") == "grade_keysets"

    # 4. check per-row grader field in results.jsonl
    import json
    results_file = tmp_path / "runs" / sorted((tmp_path / "runs").iterdir())[-1].name / "results.jsonl"
    reroute_graders, other_graders = set(), set()
    for line in results_file.open():
        r = json.loads(line)
        if r.get("kind") != "model":
            continue
        grader = r.get("grader")
        if run_sweep._is_reroute_instance(r.get("instance", "")):
            reroute_graders.add(grader)
        else:
            other_graders.add(grader)
    # All reroute rows must use the semantic grader
    assert reroute_graders == {"grade_keysets_semantic"}, (
        f"Expected all reroute rows to use grade_keysets_semantic, got {reroute_graders}")
    # No non-reroute rows in this templated-reroutes-only run, but assert set is empty or exact
    if other_graders:
        assert other_graders == {"grade_keysets"}
