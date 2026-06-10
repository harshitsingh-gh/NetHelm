"""End-to-end (fake oracle, fake model, zero-API) smoke test for the sweep, plus
the fake_oracle structural-GT checks. Confirms the spec invariants: scenario-level
aggregation (not pooled), splits reported separately, all baselines present,
modal_by_class < oracle_ceiling, naive_session_loss trips false_session_alarm."""

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
