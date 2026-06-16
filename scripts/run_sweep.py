#!/usr/bin/env python
"""One-command model sweep over the NetHELM blast-radius benchmark.

Runs N samples per (instance, model) through the oracle + grader, aggregates AT THE
SCENARIO LEVEL (per-instance = mean over the N samples; population = mean +/- std
ACROSS instances — never pooling N x instances as i.i.d.; the adjudicator's binding
ruling, fight_synthesis_2026-06-08.md must-fix #4), and reports:

  * a per-dimension P/R/F1 table (dims x models) with mean +/- std,
  * the false_session_alarm RATE +/- std (the thesis figure),
  * every model-independent baseline (empty / naive_session_loss / naive_count /
    modal_by_class / oracle_ceiling), and
  * the templated vs grounded splits REPORTED SEPARATELY (never pooled).

Default ``--models fake`` is the ZERO-API / zero-Batfish validation path (synthetic
ground truth from reporting.fake_oracle; do NOT report its numbers). ``anthropic/<id>``
is the PAID path and requires both ``--oracle batfish`` (a running Batfish) and
ANTHROPIC_API_KEY; it is NEVER spent by default. Pinned model IDs + per-run cost are
written to the run manifest.

Examples
--------
    # zero-API validation (fake model, synthetic oracle):
    python scripts/run_sweep.py --models fake --samples 3 --split both --n-generated 12

    # the real sweep (PAID — needs Batfish + provider API keys; do not run unprompted).
    # --coarsen-class is ON by default (audit 2026-06-10 K1: without it modal_by_class
    # degenerates to the oracle ceiling and the validity floor is vacuous):
    python scripts/run_sweep.py \
        --models anthropic/claude-opus-4-8,openai/gpt-5.5,gemini/gemini-3.5-flash \
        --oracle batfish --samples 5 --split both --n-generated 96 --seed 0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from netbrace.graders.semantic_sets import (
    config_visible_prefixes,
    grade_keysets_semantic,
)
from netbrace.reporting import baselines as bl
from netbrace.reporting.baselines import KeySets, grade_keysets
from netbrace.reporting.sweep_aggregate import (
    aggregate_scenario_level, reroute_detection_scores, reroute_family_of)
from netbrace.tasks.safety import scenarios

# Pinned model IDs + their per-1M-token USD prices (input, output) for cost logging.
# These are the FLEET the paper sweep targets; prices are list rates at pin time and
# are recorded in the manifest so a reported cost is traceable. Update with care.
# Verified 2026-06-10 (ml-eval registry research; sources in audit_2026-06-10):
#   * Anthropic 4.6-gen IDs (claude-opus-4-8, claude-sonnet-4-6) are DATELESS but
#     PINNED snapshots, not evergreen aliases. Opus 4.8 list price is $5/$25 — the
#     previous $15/$75 entry was the retired Opus 4.1 rate (3x overstatement).
#     NOTE: Opus 4.8 / Sonnet 4.6 use the new tokenizer (~30-35% more tokens for
#     the same text) — budget input cost accordingly.
#   * OpenAI GPT-5.5 = GA flagship (~April 2026), $5/$30; no dated snapshot ID is
#     published ("gpt-5.5" IS the pin). Responses API bills the same per-model rate.
#   * Gemini 3.5 PRO is NOT GA on the API (only 3.5 Flash shipped at I/O 2026;
#     3.1 Pro is still Preview = not reproducibility-safe). Flash is the pin.
#   * vllm/qwen3-32b is billed by GPU-hour (RunPod H100 ~$2.39-2.69/hr), not per
#     token — log wall-clock + hourly rate in the manifest for its cost.
MODEL_REGISTRY = {
    "fake": {"id": "fake-sweep-v0", "price_in": 0.0, "price_out": 0.0, "paid": False},
    "fake-oracle": {"id": "fake-oracle-echo", "price_in": 0.0, "price_out": 0.0, "paid": False},
    # sampling=False (Opus 4.8): temperature/top_p/top_k are REMOVED on Opus 4.7+
    # — sending any of them returns a 400 (verified against the live Anthropic docs
    # 2026-06-10). Haiku 4.5 / Sonnet 4.6 still accept temperature. N>1 samples on
    # Opus 4.8 rely on the model's inherent nondeterminism (temperature not tunable).
    "anthropic/claude-opus-4-8": {
        "id": "claude-opus-4-8", "price_in": 5.0, "price_out": 25.0, "paid": True,
        "sampling": False},
    "anthropic/claude-sonnet-4-6": {
        "id": "claude-sonnet-4-6", "price_in": 3.0, "price_out": 15.0, "paid": True},
    "anthropic/claude-haiku-4-5-20251001": {
        "id": "claude-haiku-4-5-20251001", "price_in": 1.0, "price_out": 5.0, "paid": True},
    "openai/gpt-5.5": {
        "id": "gpt-5.5", "price_in": 5.0, "price_out": 30.0, "paid": True},
    "openai/gpt-5.4-mini": {
        "id": "gpt-5.4-mini", "price_in": 0.75, "price_out": 4.5, "paid": True},
    "gemini/gemini-3.5-flash": {
        "id": "gemini-3.5-flash", "price_in": 1.5, "price_out": 9.0, "paid": True},
    # Open-weight local serving (vLLM); cost = GPU-hours, recorded separately.
    "vllm/qwen3-32b": {
        "id": "Qwen/Qwen3-32B", "price_in": 0.0, "price_out": 0.0, "paid": True},
    # Open-weight via hosted OpenAI-compatible endpoints (paid; $ tracked via _usd).
    # No "sampling" key -> resolve_temperature returns None (no temperature sent),
    # same as the other reasoning models; nondeterminism drives N>1 variance.
    # Prices are estimates for cost logging; the hard cap is the provider account.
    "deepseek/deepseek-v4-pro": {
        "id": "deepseek-v4-pro", "base_url": "https://api.deepseek.com",
        "key_env": "DEEPSEEK_API_KEY", "price_in": 0.6, "price_out": 2.2, "paid": True},
    "kimi/kimi-k2.6": {
        "id": "kimi-k2.6", "base_url": "https://api.moonshot.ai/v1",
        "key_env": "KIMI_API_KEY", "price_in": 0.6, "price_out": 3.4, "paid": True},
}

# The prompt template whose sha256 is recorded in every run manifest so the
# exact contract sent to every model is auditable without re-running anything.
_PROMPT_MD = Path(__file__).resolve().parents[1] / "netbrace/prompts/safety_extended_v0.md"


def _git_provenance() -> dict:
    """Return git commit hash + dirty flag. Degrades to UNKNOWN if git is absent."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=Path(__file__).resolve().parents[1],
        ).stdout.strip() or "UNKNOWN"
        porcelain = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
            cwd=Path(__file__).resolve().parents[1],
        ).stdout.strip()
        return {"git_commit": commit, "git_dirty": bool(porcelain)}
    except Exception as e:  # noqa: BLE001 — git absent in some CI environments
        return {"git_commit": f"UNKNOWN ({e})", "git_dirty": None}


def _engine_fingerprint() -> dict:
    """Pin the engine stack (Batfish image digest + pybatfish version).

    Mirrors scripts/verify_determinism.py::_engine_fingerprint — kept in sync
    so the sweep manifest and the determinism report use the same probe logic.
    Degrades gracefully when docker/pybatfish is absent (CI / unit-test runs).
    """
    fp: dict = {}
    digest = ""
    for cmd in (
        ["docker", "inspect", "--format", "{{index .RepoDigests 0}}",
         "batfish/allinone:nethelm"],
        ["docker", "inspect", "--format", "{{index .RepoDigests 0}}", "batfish"],
    ):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            digest = (out.stdout or "").strip()
            if digest:
                break
        except Exception:  # noqa: BLE001 — docker absent in CI
            continue
    fp["batfish_image"] = digest or "UNKNOWN (docker inspect failed)"
    try:
        import pybatfish  # noqa: PLC0415
        fp["pybatfish_version"] = getattr(pybatfish, "__version__", "unknown")
    except Exception as e:  # noqa: BLE001
        fp["pybatfish_version"] = f"unknown ({e})"
    return fp


def _prompt_template_hash() -> dict:
    """sha256 over the raw bytes of the prompt contract (safety_extended_v0.md).

    Every model call in the sweep uses _prompt_for -> _build_prompt which reads
    this file; pinning its hash makes the exact contract reproducible without
    re-running anything.  Returns {"prompt_file": path_str, "sha256": hex}.
    """
    try:
        raw = _PROMPT_MD.read_bytes()
        return {
            "prompt_file": str(_PROMPT_MD),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    except Exception as e:  # noqa: BLE001 — file missing in edge cases
        return {"prompt_file": str(_PROMPT_MD), "sha256": f"UNKNOWN ({e})"}


# --------------------------------------------------------------------------- #
# Instance assembly: templated (generated) + grounded (registry), tagged by split.
# --------------------------------------------------------------------------- #
@dataclass
class Instance:
    scn: object
    instance_id: str
    split: str          # "templated" | "grounded"
    cls: str            # modal_by_class class label
    is_trap: bool


# Grounded scenarios that are NOT traps (static-route sanity anchors) — for honest
# false_session_alarm attribution in fake mode.
_GROUNDED_NONTRAP = {"square4", "ecmp4", "waypoint4"}

# Output-token budget for the anthropic/vllm paths (openai/gemini already run at
# 16000/uncapped). 4000 was the 2026-06-10 freeze value; it hard-truncated 6/55
# Sonnet 4.6 grounded samples mid-reasoning (regrade_semantic_2026-06-12.md), so
# re-runs may raise it via --max-output-tokens. Recorded in the manifest via args.
MAX_OUTPUT_TOKENS = 4000


def resolve_temperature(model: str, override: float | None) -> float | None:
    """Per-family sampling temperature (freeze gate 2026-06-10, binding decision):
    stochastic chat models (anthropic/, vllm/, the fake paths — thinking off) sample
    at 0.7 so N>1 samples carry real variance (temp 0.0 would return near-identical
    samples = wasted paid spend + fake ±0.00 CIs); reasoning models (openai/,
    gemini/) do not accept temperature and get None (never sent). Registry entries
    with ``sampling: False`` (Opus 4.8 — temperature is REMOVED on Opus 4.7+ and
    400s) also get None regardless of family. --temperature overrides the
    temperature-accepting families only (diagnostics)."""
    if not MODEL_REGISTRY.get(model, {}).get("sampling", True):
        return None
    if override is not None:
        return override
    if model.startswith(("anthropic/", "vllm/")) or model in ("fake", "fake-oracle"):
        return 0.7
    return None


_REROUTE_PREFIXES = tuple(p for (_m, _f, p) in scenarios.REROUTE_GENERATORS)

# Families HELD OUT of the NetBrace-Detect HEADLINE because a zero-reasoning mechanical probe
# separates their bypass/no_op twins (they remain scored in the reroute_detect_all13
# diagnostic). origin_code is held out: its ORIGIN tiebreak edits DIFFERENT route-map clauses
# (the customer clause for the bypass, an inert decoy clause for the no_op) at different
# positions, so its unified-diff GEOMETRY is asymmetric (bypass = 1 hunk / 18 lines, no_op =
# 2 hunks / 20 lines) — a single-feature probe on n_hunks separates it at 1.0 (the gate-3
# finding; the +/- changed lines ARE symmetric, the hunk structure is not). The other 12
# families are verified leak-free under single AND 2-feature probes INCLUDING diff-geometry
# (n_hunks, n_total_lines) by tests/unit/test_reroute_probe_leak.py. A future symmetrization
# of origin_code's generator (single edit locus, position-balanced) would remove it here.
REROUTE_DIFFSHAPE_LEAKY = frozenset({"origin_code"})


def _is_reroute_instance(instance_id: str) -> bool:
    """True if this templated instance is one of the 13 quiet-reroute mechanisms."""
    return instance_id.startswith(_REROUTE_PREFIXES)


def _grade_instance(pred: KeySets, truth: KeySets, *,
                    instance_id: str,
                    is_trap: bool,
                    task_id: str,
                    valid_prediction: bool = True,
                    cfg_prefixes: set[str] | None = None) -> tuple[object, str]:
    """Route to the correct grader based on instance type.

    Reroute instances (those with hidden /32 D4/D10 probes) are graded with
    grade_keysets_semantic: a /24-naming reasoner that correctly names the
    config-visible covering prefix scores ~1.0 on waypoint/intent instead of 0.0
    under the exact grader. All other instances use grade_keysets (exact).

    Returns (ExtendedScoreRecord, grader_name_str) so the caller can record
    grader provenance per-record.
    """
    if _is_reroute_instance(instance_id):
        sr = grade_keysets_semantic(
            pred, truth,
            config_prefixes=cfg_prefixes if cfg_prefixes is not None else set(),
            is_trap=is_trap,
            task_id=task_id,
            valid_prediction=valid_prediction,
        )
        return sr, "grade_keysets_semantic"
    sr = grade_keysets(
        pred, truth,
        is_trap=is_trap,
        task_id=task_id,
        valid_prediction=valid_prediction,
    )
    return sr, "grade_keysets"


def build_instances(split: str, n_generated: int, seed: int,
                    coarsen_class: bool = False,
                    exclude: frozenset[str] = frozenset(),
                    templated_set: str = "legacy",
                    include_noop: bool = True) -> list[Instance]:
    insts: list[Instance] = []
    if split in ("templated", "both"):
        # `templated_set` selects the mechanism family for the templated split:
        #   legacy   -> ipc/leak/lp/scale (build_generated_suite_multi; audit K3)
        #   reroutes -> the 13 quiet-reroute generators (bypass + no_op twins)
        #   both     -> both, concatenated
        gen_scns = []
        if templated_set in ("legacy", "both"):
            gen_scns += scenarios.build_generated_suite_multi(n_generated, base_seed=seed)
        if templated_set in ("reroutes", "both"):
            gen_scns += scenarios.build_generated_suite_reroutes(
                n_generated, base_seed=seed, include_noop=include_noop)
        for scn in gen_scns:
            insts.append(Instance(
                scn=scn, instance_id=scn.name, split="templated",
                cls=bl.scenario_class(scn.name, scn.provenance, coarsen=coarsen_class),
                is_trap=getattr(scn, "is_trap", False),
            ))
    if split in ("grounded", "both"):
        for name in sorted(scenarios.REGISTRY):
            if name in exclude:
                continue
            scn = scenarios.build(name)
            insts.append(Instance(
                scn=scn, instance_id=scn.name, split="grounded",
                cls=bl.scenario_class(scn.name, scn.provenance, coarsen=coarsen_class),
                is_trap=getattr(scn, "is_trap", False),
            ))
    return insts


# --------------------------------------------------------------------------- #
# Ground truth: fake (synthetic, zero-Batfish) or batfish (real, paid path).
# --------------------------------------------------------------------------- #
class OracleQuarantineError(RuntimeError):
    """Ground truth could not be computed reliably for an instance — the instance
    is QUARANTINED (excluded + logged), never silently scored (audit 2026-06-10 K4)."""


def ground_truth(scn, oracle: str, host: str, *, det_runs: int = 2,
                 max_attempts: int = 3) -> KeySets:
    """Compute the instance's ground truth with flake-retry + in-sweep determinism.

    Batfish has a known non-deterministic snapshot-contention flake ("Work
    terminated abnormally" / "Found no active locations") that previously crashed
    paid runs mid-sweep (audit 2026-06-10 K4). Each attempt uses a FRESH Batfish
    network name (contention is network-state-scoped); ``det_runs >= 2`` routes
    through ``compute_checked`` so every scored instance is at least lightly
    determinism-checked in-sweep (the full >=10x gate remains
    scripts/verify_determinism.py's job). Raises OracleQuarantineError after
    ``max_attempts`` failures.
    """
    if oracle == "fake":
        from netbrace.reporting.fake_oracle import fake_ground_truth
        return fake_ground_truth(scn)
    from netbrace.batfish.extended_oracle import ExtendedOracle
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            o = ExtendedOracle(host=host, network=f"sweep_{scn.name}_a{attempt}")
            truth = (o.compute_checked(scn, runs=det_runs) if det_runs >= 2
                     else o.compute(scn))
            return {t: set(v) for t, v in truth.normalized().key_sets().items()}
        except Exception as e:  # noqa: BLE001 — Batfish raises broad exception types
            last_err = e
            print(f"[oracle-retry] {scn.name} attempt {attempt + 1}/{max_attempts} "
                  f"failed: {e}", flush=True)
    raise OracleQuarantineError(
        f"{scn.name}: ground truth failed {max_attempts}x (last: {last_err})")


# --------------------------------------------------------------------------- #
# Model predictions (one per sample). fake = deterministic perturbation of GT so the
# aggregation exercises real cross-sample/cross-instance variance.
# --------------------------------------------------------------------------- #
def fake_model_keysets(truth: KeySets, instance_id: str, sample_idx: int,
                       temperature: float) -> KeySets:
    """A deterministic stand-in 'model' for zero-API validation.

    It is a plausibly-imperfect predictor: it usually recovers the data-plane
    dimensions (D2/D3/D7) but, with temperature-scaled probability, (a) DROPS a
    second-order control-plane/intent key (D9/D10 miss) and (b) HALLUCINATES a
    session loss (the trap false alarm) on some samples. This yields non-trivial
    per-instance means AND cross-instance std so the two-stage aggregator is
    actually tested. NOT a model; never reported.
    """
    rng = random.Random(f"{instance_id}|{sample_idx}")
    pred: KeySets = {t: set(v) for t, v in truth.items()}

    p_miss_2nd = min(0.6, 0.2 + temperature * 0.4)
    p_false_session = min(0.5, 0.1 + temperature * 0.4)

    # miss second-order dims sometimes
    for t in ("bgp_withdrawn", "intent", "forwarding"):
        if pred.get(t) and rng.random() < p_miss_2nd:
            pred[t] = set()
    # hallucinate a session loss sometimes (trips false_session_alarm when truth=∅)
    if rng.random() < p_false_session:
        any_node = next(iter(
            k.split("|node=")[1].split("|")[0]
            for ks in truth.values() for k in ks if "|node=" in k
        ), "r1")
        pred["sessions"] = {f"bgp|vrf=default|node={any_node}|peer_ip=0.0.0.0"}
    return pred


def predict_keysets(model: str, scn, truth: KeySets, instance_id: str,
                    sample_idx: int, temperature: float,
                    pre_state: str | None = None) -> tuple[KeySets, dict, str | None]:
    """Return (prediction keysets, cost dict {tokens_in, tokens_out, usd}, raw text).

    ``raw`` is the verbatim model output (None for the fake paths) — persisted to
    responses.jsonl so invalid outputs are auditable (formatting-failure vs
    reasoning-failure must be disentangleable; audit 2026-06-10 M6).

    ``pre_state`` is the TOOLS-AUGMENTED condition's PRE-state observation (None =
    the no_tools condition). The fake model ignores it (it predicts off the truth);
    the real path passes it into the prompt builder.
    """
    if model in ("fake", "fake-oracle"):
        ks = (truth if model == "fake-oracle"
              else fake_model_keysets(truth, instance_id, sample_idx, temperature))
        return ks, {"tokens_in": 0, "tokens_out": 0, "usd": 0.0}, None

    if model.startswith(("anthropic/", "openai/", "gemini/", "vllm/",
                         "deepseek/", "kimi/")):
        if model.startswith("anthropic/"):
            raw, cost = _call_anthropic(model, scn, temperature, pre_state)
        elif model.startswith("openai/"):
            raw, cost = _call_openai(model, scn, temperature, pre_state)
        elif model.startswith("vllm/"):
            raw, cost = _call_vllm(model, scn, temperature, pre_state)
        elif model.startswith(("deepseek/", "kimi/")):
            raw, cost = _call_oai_compat(model, scn, temperature, pre_state)
        else:
            raw, cost = _call_gemini(model, scn, temperature, pre_state)
        from netbrace.evals.extended_parser import parse_extended_prediction
        pred = parse_extended_prediction(raw)
        if pred is None:
            return None, cost, raw  # invalid output -> grade_keysets marks invalid
        return {t: set(v) for t, v in pred.key_sets().items()}, cost, raw

    raise SystemExit(f"unsupported --models entry {model!r}")


def _prompt_for(scn, pre_state: str | None) -> str:
    """Build the SAME prompt used by every provider (single contract)."""
    import sys
    from pathlib import Path as _Path
    _repo = str(_Path(__file__).resolve().parents[1])
    if _repo not in sys.path:
        sys.path.insert(0, _repo)
    from scripts.run_extended_scenario import _build_prompt
    return _build_prompt(scn, pre_state)


def _usd(model: str, tin: int, tout: int) -> float:
    reg = MODEL_REGISTRY[model]
    return round(tin / 1e6 * reg["price_in"] + tout / 1e6 * reg["price_out"], 6)


def _call_anthropic(model: str, scn, temperature: float,
                    pre_state: str | None = None) -> tuple[str, dict]:
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set — required for the PAID path.")
    import anthropic  # lazy

    model_id = MODEL_REGISTRY[model]["id"]
    # Bounded timeout + retries so a transient stall cannot hang the whole sweep
    # (a single call must not block the cost-guarded run indefinitely).
    # max_tokens=4000 (freeze gate 2026-06-10): pure answer budget (thinking is off
    # by default on Opus 4.8/Sonnet 4.6) but the 4.6-gen tokenizer emits ~30-35%
    # more tokens and a truncated 9-list JSON = invalid = scored 0.
    # temperature is OMITTED when resolve_temperature returned None (Opus 4.8
    # removed sampling params — sending temperature returns a 400).
    client = anthropic.Anthropic(timeout=120.0, max_retries=2)
    kwargs = dict(
        model=model_id, max_tokens=MAX_OUTPUT_TOKENS,
        messages=[{"role": "user", "content": _prompt_for(scn, pre_state)}],
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    msg = client.messages.create(**kwargs)
    raw = "".join(getattr(b, "text", "") for b in msg.content)
    tin, tout = msg.usage.input_tokens, msg.usage.output_tokens
    usd = _usd(model, tin, tout)
    return raw, {"tokens_in": tin, "tokens_out": tout, "usd": usd}


def _call_openai(model: str, scn, temperature: float,
                 pre_state: str | None = None) -> tuple[str, dict]:
    """OpenAI path (uses OPENAI_API_KEY). Mirrors _call_anthropic: same prompt
    contract via _prompt_for, same return shape (raw, cost). Hard-checks the key so
    a keyless run fails FAST, not mid-sweep."""
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set — required for the openai/ PAID path.")
    from openai import OpenAI  # lazy

    model_id = MODEL_REGISTRY[model]["id"]
    client = OpenAI(timeout=300.0, max_retries=2)
    # Responses API; GPT-5.x are reasoning models: temperature is unsupported (never
    # sent). Freeze gate 2026-06-10: the gpt-5.5 flagship REJECTS max_output_tokens
    # outright (400 Bad Request) — use reasoning effort + verbosity instead; for the
    # mini tier max_output_tokens IS accepted but includes reasoning tokens, so the
    # cap must be far above the visible answer (truncation = invalid = scored 0).
    kwargs = dict(
        model=model_id,
        input=[{"role": "user", "content": _prompt_for(scn, pre_state)}],
    )
    if model_id.startswith("gpt-5.5"):
        kwargs["reasoning"] = {"effort": "medium"}
        kwargs["text"] = {"verbosity": "low"}
    else:
        kwargs["max_output_tokens"] = 16000
    resp = client.responses.create(**kwargs)
    raw = getattr(resp, "output_text", "") or ""
    u = resp.usage
    tin = getattr(u, "input_tokens", 0)
    tout = getattr(u, "output_tokens", 0)
    usd = _usd(model, tin, tout)
    return raw, {"tokens_in": tin, "tokens_out": tout, "usd": usd}


def _call_vllm(model: str, scn, temperature: float,
               pre_state: str | None = None) -> tuple[str, dict]:
    """Open-weight path via a vLLM OpenAI-compatible endpoint (VLLM_BASE_URL, e.g.
    a RunPod pod's http://<host>:8000/v1). Cost is GPU-hours, not per-token — token
    counts are still logged; the $ figure stays 0.0 and the GPU wall-clock + hourly
    rate must be recorded in the run notes."""
    import os
    base = os.environ.get("VLLM_BASE_URL")
    if not base:
        raise SystemExit("VLLM_BASE_URL not set — required for the vllm/ path.")
    from openai import OpenAI  # lazy; vLLM speaks the OpenAI chat API

    model_id = MODEL_REGISTRY[model]["id"]
    client = OpenAI(base_url=base, api_key=os.environ.get("VLLM_API_KEY", "EMPTY"),
                    timeout=180.0, max_retries=2)
    resp = client.chat.completions.create(
        model=model_id, temperature=temperature, max_tokens=MAX_OUTPUT_TOKENS,
        messages=[{"role": "user", "content": _prompt_for(scn, pre_state)}],
    )
    raw = resp.choices[0].message.content or ""
    u = resp.usage
    tin = getattr(u, "prompt_tokens", 0) or 0
    tout = getattr(u, "completion_tokens", 0) or 0
    return raw, {"tokens_in": tin, "tokens_out": tout, "usd": 0.0}


def _call_oai_compat(model: str, scn, temperature: float,
                     pre_state: str | None = None) -> tuple[str, dict]:
    """Hosted OpenAI-compatible open-weight providers (DeepSeek api.deepseek.com,
    Moonshot/Kimi api.moonshot.ai). base_url + key_env come from the registry;
    same prompt contract as every other model; $ cost tracked via _usd.

    STREAMS the completion (2026-06-14). These are reasoning models whose hidden
    chain-of-thought can run to many thousands of tokens, so a NON-streaming call
    blocks until the server has computed the ENTIRE response before sending ANY
    bytes. On the big grounded prompts Kimi k2.6's first call never returned
    response headers inside the socket read timeout and wedged a whole run (26 min,
    0 completions). Streaming makes headers arrive in ~1 s and the per-CHUNK read
    timeout resets on every token, so a long-but-steady generation completes while a
    genuinely stalled socket still fails fast (-> _retrying backoff -> SKIP). Any
    separate reasoning_content is ignored; the tolerant parser pulls the final JSON
    object from the accumulated message content."""
    import os
    import httpx
    from openai import OpenAI  # lazy; both speak the OpenAI chat API
    reg = MODEL_REGISTRY[model]
    key = os.environ.get(reg["key_env"])
    if not key:
        raise SystemExit(f"{reg['key_env']} not set --- required for {model}.")
    # Per-CHUNK read timeout (NOT a total deadline): 180 s of silence => fail; an
    # actively streaming generation resets it on every token.
    client = OpenAI(base_url=reg["base_url"], api_key=key,
                    timeout=httpx.Timeout(connect=15.0, read=180.0,
                                          write=15.0, pool=15.0),
                    max_retries=2)
    kwargs = dict(model=reg["id"], max_tokens=MAX_OUTPUT_TOKENS,
                  messages=[{"role": "user", "content": _prompt_for(scn, pre_state)}],
                  stream=True, stream_options={"include_usage": True})
    if temperature is not None:
        kwargs["temperature"] = temperature
    content = ""
    tin = tout = 0
    for chunk in client.chat.completions.create(**kwargs):
        if not chunk.choices:                       # final usage-only chunk
            u = getattr(chunk, "usage", None)
            if u:
                tin = getattr(u, "prompt_tokens", 0) or 0
                tout = getattr(u, "completion_tokens", 0) or 0
            continue
        piece = getattr(chunk.choices[0].delta, "content", None)
        if piece:
            content += piece
    if tout == 0 and content:                       # provider omitted usage chunk
        tout = len(content) // 4
    return content, {"tokens_in": tin, "tokens_out": tout,
                     "usd": _usd(model, tin, tout)}


def _call_gemini(model: str, scn, temperature: float,
                 pre_state: str | None = None) -> tuple[str, dict]:
    """Gemini path (uses GEMINI_API_KEY or GOOGLE_API_KEY via google-genai). Mirrors
    _call_anthropic. Hard-checks the key so a keyless run fails FAST."""
    import os
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise SystemExit(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) not set — required for the gemini/ "
            "PAID path.")
    from google import genai  # lazy
    from google.genai import types as gtypes

    model_id = MODEL_REGISTRY[model]["id"]
    # Per-request timeout (ms) so a wedged socket can't hang the whole sweep. The
    # other providers set timeout+max_retries on their clients; the Gemini path had
    # NO timeout, so a stalled first call blocked a 2 h run on 2026-06-11 (the SDK
    # never raised, so _retrying's backoff never fired). 120 s is generous for a
    # thinking model; on timeout the SDK raises -> _retrying retries -> then SKIP.
    client = genai.Client(api_key=key,
                          http_options=gtypes.HttpOptions(timeout=120_000))
    # Freeze gate 2026-06-10: Gemini 3.5 thinks by default and the thinking tokens
    # count against max_output_tokens (default 8192) — a tight cap truncates the
    # visible answer (finishReason MAX_TOKENS -> invalid -> scored 0). 16000 gives
    # answer + thinking headroom. Temperature is NOT sent (thinking-model contract).
    resp = client.models.generate_content(
        model=model_id,
        contents=_prompt_for(scn, pre_state),
        config=gtypes.GenerateContentConfig(max_output_tokens=16000),
    )
    raw = getattr(resp, "text", "") or ""
    if not raw.strip():
        # An empty body is NOT a model answer. Distinguish two cases:
        #   * finish_reason MAX_TOKENS — a real (truncated) output: grade it as
        #     invalid like any other unparseable answer; retrying would bias the
        #     invalid_rate measurement.
        #   * anything else (empty candidates / safety block / silent 200 during
        #     an overload window) — a provider anomaly: raise retryable so
        #     _retrying backs off instead of paying for a vacuous "invalid".
        cands = getattr(resp, "candidates", None) or []
        fr = str(getattr(cands[0], "finish_reason", "")) if cands else ""
        if "MAX_TOKENS" not in fr.upper():
            raise _RetryableProviderError(
                f"gemini returned an empty body (finish_reason={fr or 'none'}, "
                f"candidates={len(cands)})")
    um = getattr(resp, "usage_metadata", None)
    tin = getattr(um, "prompt_token_count", 0) or 0
    # total - prompt = output (+thinking); thinking is billed at the output rate on 2.5.
    total = getattr(um, "total_token_count", 0) or 0
    tout = max(total - tin, getattr(um, "candidates_token_count", 0) or 0)
    usd = _usd(model, tin, tout)
    return raw, {"tokens_in": tin, "tokens_out": tout, "usd": usd}


class _ModelCallFailed(RuntimeError):
    """A model call failed after all retries (provider outage / persistent error)."""


# Consecutive post-backoff sample losses before a (model, condition) is declared
# down and its remaining work skipped (each loss already cost up to ~10 min of
# backoff — 5 in a row is a sustained outage, not flakiness).
_ABORT_AFTER = 5


def _completeness_report(models, conditions, instances, samples,
                         collected: dict[str, dict[str, int]]) -> dict:
    """Expected-vs-collected ledger for every (model, condition) cell. A cell is
    one instance; ``missing`` maps instance_id -> number of samples still owed.
    ``complete`` is the run-level verdict the manifest carries."""
    report: dict = {"samples_per_instance": samples, "cells": {},
                    "incomplete_cells": [], "complete": True}
    for model in models:
        if model in ("fake", "fake-oracle"):
            continue  # zero-API paths can't lose samples to a provider
        for cond in conditions:
            key = f"{model} @ {cond}"
            got = collected.get(key, {})
            missing = {i.instance_id: samples - got.get(i.instance_id, 0)
                       for i in instances
                       if got.get(i.instance_id, 0) < samples}
            cell = {"expected": len(instances) * samples,
                    "collected": sum(got.values()),
                    "missing": missing}
            report["cells"][key] = cell
            if missing:
                report["incomplete_cells"].append(key)
                report["complete"] = False
    return report


def _print_completeness(report: dict, args) -> None:
    if report["complete"]:
        print("[completeness] OK — every (model, condition, instance) cell has "
              f"all {report['samples_per_instance']} samples.", flush=True)
        return
    print("\n" + "=" * 76, flush=True)
    print("[completeness] *** RUN IS INCOMPLETE — do not report it as final ***",
          flush=True)
    for key in report["incomplete_cells"]:
        cell = report["cells"][key]
        print(f"  {key}: {cell['collected']}/{cell['expected']} samples; "
              f"{len(cell['missing'])} instances short", flush=True)
        ids = sorted(cell["missing"])
        model = key.split(" @ ")[0]
        print(f"    top-up: python scripts/run_sweep.py --models {model} "
              f"--oracle batfish --samples {args.samples} "
              f"--split {args.split} --n-generated {args.n_generated} "
              f"--seed {args.seed} --include {','.join(ids)}", flush=True)
    print("  then pool post-freeze runs (see scripts/build_clean_gemini.py for "
          "the audited pattern).", flush=True)
    print("=" * 76 + "\n", flush=True)


class _RetryableProviderError(RuntimeError):
    """A provider returned a degenerate response that is NOT a model answer
    (e.g. a 200 with an empty body) — retry it like a 503, never grade it."""


# Errors where retrying is pointless (mis-set key, bad request, gone model):
# fail FAST so a misconfigured paid run dies on call 1, not after 8 backoffs.
_FATAL_MARKERS = (
    "api key", "api_key", "401", "403", "permission", "unauthorized",
    "invalid_request", "400", "not found", "404", "model_not_found",
    "unsupported", "billing",
)


def _is_fatal(e: Exception) -> bool:
    msg = f"{type(e).__name__}: {e}".lower()
    return any(m in msg for m in _FATAL_MARKERS)


def _retrying(fn, *args, attempts: int = 8, base: float = 5.0, cap: float = 120.0,
              **kwargs):
    """Call ``fn`` with TRUE exponential backoff + jitter on transient errors
    (5,10,20,40,80,120,120s x uniform(0.5,1.5) — worst case ~10 min/sample,
    sized for Gemini's multi-minute 503 'high demand' windows that the old
    3x15/30/45s ladder could not outlast, which is what left runs incomplete
    on 2026-06-11 and forced the pooling workaround). Fatal errors (auth/bad
    request/unknown model) raise immediately — retrying those only burns time.
    Raises _ModelCallFailed after ``attempts`` transient failures."""
    last: Exception | None = None
    for a in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — provider SDKs raise varied types
            if _is_fatal(e):
                raise _ModelCallFailed(f"[fatal, not retried] {e}") from e
            last = e
            wait = min(cap, base * (2 ** a)) * random.uniform(0.5, 1.5)
            print(f"[model-retry] attempt {a + 1}/{attempts} failed "
                  f"({type(e).__name__}: {e}); sleeping {wait:.0f}s", flush=True)
            time.sleep(wait)
    raise _ModelCallFailed(str(last))


# --------------------------------------------------------------------------- #
# The sweep.
# --------------------------------------------------------------------------- #
def run_sweep(args) -> dict:
    exclude = frozenset(
        x.strip() for x in getattr(args, "exclude", "").split(",") if x.strip())
    instances = build_instances(args.split, args.n_generated, args.seed,
                                coarsen_class=getattr(args, "coarsen_class", False),
                                exclude=exclude,
                                templated_set=getattr(args, "templated_set", "reroutes"),
                                include_noop=(getattr(args, "bypass_fraction", 0.5) == 0.5))
    if getattr(args, "limit", 0):
        instances = instances[:args.limit]  # pre-flight cap (CLAUDE.md --limit rule)
    # --include: surgical top-up of EXACTLY the missing cells from an incomplete
    # run (paste the id list from its completeness.json). Same split/seed args ->
    # same instances + same frozen prompt -> the new draws are poolable i.i.d.
    # samples of the same condition (the build_clean_gemini.py contract).
    include = [x.strip() for x in getattr(args, "include", "").split(",") if x.strip()]
    if include:
        known = {i.instance_id for i in instances}
        unknown = sorted(set(include) - known)
        if unknown:
            raise SystemExit(
                f"--include ids not found in the built instance set: {unknown}\n"
                f"(check --split/--n-generated/--seed match the original run)")
        instances = [i for i in instances if i.instance_id in set(include)]
        print(f"[include] top-up mode: {len(instances)} instance(s) selected",
              flush=True)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    for m in models:
        if m not in MODEL_REGISTRY:
            raise SystemExit(f"unknown model {m!r}; known: {sorted(MODEL_REGISTRY)}")

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f"runs/sweep_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    # buffering=1 -> line-buffered: every record (each ends in "\n") is flushed to
    # disk immediately. Without this the handles are block-buffered (~8 KB), so a
    # crash/kill loses all completed-but-unflushed samples — the exact failure that
    # left a 2 h run with 0-byte outputs on 2026-06-11. Paid work must survive a crash.
    results_fh = (out_dir / "results.jsonl").open("w", buffering=1, encoding="utf-8")
    # Verbatim model outputs (real models only) — required so invalid/odd outputs
    # are auditable after the run (audit 2026-06-10 M6).
    responses_fh = (out_dir / "responses.jsonl").open("w", buffering=1, encoding="utf-8")

    # 1) compute ground truth once per instance (shared across models + baselines).
    # Flake-retried + lightly determinism-checked per instance; persistent failures
    # are QUARANTINED (excluded + logged to quarantine.jsonl), never silently scored
    # and never allowed to crash a paid run (audit 2026-06-10 K4).
    truth_by_instance: dict[str, KeySets] = {}
    quarantined: list[dict] = []
    for inst in instances:
        try:
            truth_by_instance[inst.instance_id] = ground_truth(
                inst.scn, args.oracle, args.host,
                det_runs=getattr(args, "det_runs", 2))
        except OracleQuarantineError as e:
            quarantined.append({"instance": inst.instance_id, "split": inst.split,
                                "error": str(e)})
            print(f"[QUARANTINE] {inst.instance_id}: {e}", flush=True)
    if quarantined:
        (out_dir / "quarantine.jsonl").write_text(
            "".join(json.dumps(q) + "\n" for q in quarantined), encoding="utf-8")
        instances = [i for i in instances if i.instance_id in truth_by_instance]
    class_of = {inst.instance_id: inst.cls for inst in instances}
    split_of = {inst.instance_id: inst.split for inst in instances}
    trap_of = {inst.instance_id: inst.is_trap for inst in instances}
    # modal_by_class is UNDEFINED for singleton classes (floor == ceiling, audit K1):
    # count members so the baseline can skip them instead of printing a vacuous 1.00.
    from collections import Counter as _Counter
    class_member_count = _Counter(class_of.values())
    # Calibration instances (freeze gate 2026-06-10 #5): some templated combos have
    # an EMPTY ground truth by construction (lp no_op, scale under-kept) — the
    # correct answer is "no blast". They are scored normally, but the headline
    # damage-detection macro must not blend them in (an empty predictor passes them
    # for free), so every record is tagged and a damage-only macro is aggregated.
    gt_empty = {iid: not any(ts.values()) for iid, ts in truth_by_instance.items()}

    # 1b) PRE-state observation per instance — only needed for the tools condition.
    # Computed once per instance (deterministic, shared across models + samples).
    conditions = [c.strip() for c in getattr(args, "condition", "no_tools").split(",")
                  if c.strip()] or ["no_tools"]
    pre_state_by_instance: dict[str, str | None] = {i.instance_id: None for i in instances}
    if "tools" in conditions and args.oracle == "batfish":
        from netbrace.batfish.extended_oracle import ExtendedOracle
        oracle = ExtendedOracle(host=args.host)
        for inst in instances:
            pre_state_by_instance[inst.instance_id] = oracle.pre_state_text(inst.scn)

    # 1c) Post-mortem artifact (freeze gate follow-up): persist, per instance, the
    # EXACT rendered prompt(s) sent and the ground truth graded against — so any
    # paid result can be audited end-to-end (prompt -> raw response -> grade)
    # without re-running anything. responses.jsonl holds the raw model text;
    # instances.jsonl holds the question + the answer key.
    #
    # Also cache the no_tools prompt text so reroute instances can extract their
    # config-visible prefixes for semantic grading in step 2 (M-A: grade reroute
    # instances with grade_keysets_semantic, which needs the prompt to extract the
    # credit band — the /32 probes are hidden from the prompt, so a /24-naming
    # reasoner scores ~1.0 under the semantic grader instead of 0.5 under exact).
    prompt_cache: dict[str, str] = {}  # instance_id -> no_tools prompt text
    for inst in instances:
        prompt_cache[inst.instance_id] = _prompt_for(inst.scn, None)
    # config-visible prefix set per instance — pre-computed once, shared across all
    # model samples and the baseline grading step (zero extra overhead per sample).
    cfg_prefixes_by_instance: dict[str, set[str]] = {
        iid: config_visible_prefixes(prompt)
        for iid, prompt in prompt_cache.items()
    }
    with (out_dir / "instances.jsonl").open("w", encoding="utf-8") as fh:
        for inst in instances:
            fh.write(json.dumps({
                "instance": inst.instance_id,
                "split": inst.split,
                "class": inst.cls,
                "is_trap": inst.is_trap,
                "gt_empty": gt_empty[inst.instance_id],
                "truth": {t: sorted(ks) for t, ks in
                          truth_by_instance[inst.instance_id].items() if ks},
                "prompts": {c: _prompt_for(inst.scn, pre_state_by_instance[inst.instance_id]
                                           if c == "tools" else None)
                            for c in conditions},
            }) + "\n")

    total_cost = 0.0

    # 2) model predictions: N samples per (instance, model, condition).
    # records[(model, condition)][split] = {instance_id: [score_dict, ...]}
    model_records: dict[tuple[str, str], dict[str, dict[str, list[dict]]]] = {}
    # collected["model @ cond"][instance_id] = n graded samples — feeds the
    # end-of-run completeness report (a run must never LOOK complete silently).
    collected: dict[str, dict[str, int]] = {}
    for model in models:
        temp = resolve_temperature(model, args.temperature)
        for cond in conditions:
            per_split: dict[str, dict[str, list[dict]]] = {"templated": {}, "grounded": {}}
            pre = (lambda iid: pre_state_by_instance[iid]) if cond == "tools" else (lambda iid: None)
            # Circuit breaker: _ABORT_AFTER consecutive post-backoff sample losses
            # means the provider (or this key/model) is down for the count — stop
            # burning ~10 min of backoff per remaining sample, mark the rest
            # missing, and let the completeness report drive a surgical top-up.
            consec_failed = 0
            aborted = False
            for inst in instances:
                if aborted:
                    break
                truth = truth_by_instance[inst.instance_id]
                recs: list[dict] = []
                for s in range(args.samples):
                    # Provider-outage guard (learned live 2026-06-10: a Gemini 503
                    # crashed a run after other providers' calls were already paid).
                    # Retry with backoff; on persistent failure SKIP this sample
                    # (logged, excluded from grading — a provider outage is neither
                    # an invalid output nor a reason to void the paid run).
                    try:
                        pred, cost, raw = _retrying(
                            predict_keysets, model, inst.scn, truth,
                            inst.instance_id, s, temp,
                            pre_state=pre(inst.instance_id))
                    except _ModelCallFailed as e:
                        consec_failed += 1
                        print(f"[SKIP] {model} {cond} {inst.instance_id} s{s}: {e}",
                              flush=True)
                        results_fh.write(json.dumps(
                            {"kind": "model_call_failed", "model": model,
                             "condition": cond, "instance": inst.instance_id,
                             "sample": s, "error": str(e)}) + "\n")
                        if consec_failed >= _ABORT_AFTER:
                            aborted = True
                            print(f"[ABORT] {model} @ {cond}: {consec_failed} "
                                  f"consecutive samples failed after full backoff — "
                                  f"provider down; skipping its remaining work. "
                                  f"Re-run the missing cells via completeness.json "
                                  f"+ --include.", flush=True)
                            results_fh.write(json.dumps(
                                {"kind": "model_aborted", "model": model,
                                 "condition": cond,
                                 "after_instance": inst.instance_id,
                                 "consecutive_failures": consec_failed}) + "\n")
                            break
                        continue
                    consec_failed = 0
                    total_cost += cost["usd"]
                    if raw is not None:
                        responses_fh.write(json.dumps(
                            {"model": model, "condition": cond,
                             "instance": inst.instance_id, "sample": s,
                             "valid": pred is not None, "raw": raw}) + "\n")
                    # M-A: reroute instances use the SEMANTIC grader (D4/D10 truth is
                    # hidden /32 probes; a /24-naming reasoner must not be penalised
                    # for naming the config-visible covering prefix). All other
                    # instances use grade_keysets (exact). Provenance is recorded in
                    # the result row ("grader" field) and in the manifest.
                    sr, _grader = _grade_instance(
                        pred if pred is not None else bl.empty_keysets(),
                        truth,
                        instance_id=inst.instance_id,
                        is_trap=inst.is_trap,
                        task_id=f"{inst.instance_id}|{model}|{cond}|s{s}",
                        valid_prediction=pred is not None,
                        cfg_prefixes=cfg_prefixes_by_instance.get(inst.instance_id),
                    )
                    d = sr.model_dump()
                    d["cost"] = cost
                    d["gt_empty"] = gt_empty[inst.instance_id]
                    d["grader"] = _grader
                    recs.append(d)
                    if MODEL_REGISTRY[model]["paid"]:
                        print(f"[call] {model} {cond} {inst.instance_id} s{s} "
                              f"f1={sr.macro_f1:.2f} ${cost['usd']:.4f} tot=${total_cost:.3f}",
                              flush=True)
                    results_fh.write(json.dumps(
                        {"kind": "model", "model": model, "condition": cond,
                         "instance": inst.instance_id, "split": inst.split,
                         "class": inst.cls, "sample": s, **d}) + "\n")
                per_split[inst.split][inst.instance_id] = recs
                collected.setdefault(f"{model} @ {cond}", {})[inst.instance_id] = len(recs)
            model_records[(model, cond)] = per_split

    # 2b) completeness report — incomplete paid data must be LOUD, never silent.
    # (The 2026-06-11 Gemini 503 runs looked finished until post-hoc inspection;
    # this makes expected-vs-collected a first-class artifact of every run.)
    completeness = _completeness_report(models, conditions, instances,
                                        args.samples, collected)
    (out_dir / "completeness.json").write_text(
        json.dumps(completeness, indent=2) + "\n", encoding="utf-8")
    if models != ["fake"] or completeness["incomplete_cells"]:
        _print_completeness(completeness, args)

    # 3) baselines (model-free), per split. modal_by_class needs the per-class GT.
    # modal_by_class SKIPS singleton-class instances (floor undefined there — it
    # would equal the oracle ceiling; audit 2026-06-10 K1). The table reports it as
    # undefined for any split where every class is a singleton (e.g. grounded).
    modal_by_class = bl.modal_keysets_by_class(truth_by_instance, class_of)
    baseline_records: dict[str, dict[str, dict[str, list[dict]]]] = {}
    for bname in bl.BASELINE_NAMES:
        per_split = {"templated": {}, "grounded": {}}
        for inst in instances:
            if bname == "modal_by_class" and class_member_count[inst.cls] < 2:
                continue  # undefined: modal of a single instance == its own GT
            truth = truth_by_instance[inst.instance_id]
            pred = _baseline_pred(bname, inst, truth, modal_by_class)
            sr, _grader = _grade_instance(
                pred, truth,
                instance_id=inst.instance_id,
                is_trap=inst.is_trap,
                task_id=f"{inst.instance_id}|baseline_{bname}",
                cfg_prefixes=cfg_prefixes_by_instance.get(inst.instance_id),
            )
            d = sr.model_dump()
            d["gt_empty"] = gt_empty[inst.instance_id]
            d["grader"] = _grader
            # baselines are deterministic -> N=1 "sample" per instance.
            per_split[inst.split][inst.instance_id] = [d]
            results_fh.write(json.dumps(
                {"kind": "baseline", "baseline": bname, "instance": inst.instance_id,
                 "split": inst.split, "class": inst.cls, **d}) + "\n")
        baseline_records[bname] = per_split
    results_fh.close()
    responses_fh.close()

    # 4) two-stage scenario-level aggregation, PER SPLIT (never pooled).
    summary = {
        "manifest": _manifest(args, models, instances, total_cost, ts, quarantined),
        "models": {},
        "baselines": {},
    }
    # A summary built from an incomplete run carries the stain in its manifest —
    # downstream tooling (dashboard, results docs) must be able to refuse it.
    summary["manifest"]["data_complete"] = completeness["complete"]
    summary["manifest"]["incomplete_cells"] = completeness["incomplete_cells"]
    splits = [s for s in ("templated", "grounded") if any(
        i.split == s for i in instances)]
    # model rows are keyed "model @ condition" so the no_tools/tools contrast is
    # visible side by side in the headline table.
    def _agg(recs: dict[str, list[dict]]) -> dict:
        """Full aggregate + the damage-only macro (gt_empty calibration instances
        excluded — freeze gate 2026-06-10 #5: an empty predictor passes them for
        free, so they must never inflate the damage-detection headline)."""
        stats = aggregate_scenario_level(recs)
        dmg = {i: r for i, r in recs.items() if r and not r[0].get("gt_empty")}
        stats["macro_f1_damage"] = (
            aggregate_scenario_level(dmg)["macro_f1"] if dmg else None)
        stats["n_damage_instances"] = len(dmg)
        # Non-gameable reroute headline (NetBrace-Detect + Youden's J). macro_f1_damage
        # is GAMEABLE for the quiet-reroute split: it drops the no_op calibration twins,
        # so an always-predict-{D4,D10} predictor scores a perfect 1.0. The paired
        # detector below pins any constant/label-independent predictor to 0.5 / J=0.
        rr_rows = []
        for iid, rows in recs.items():
            if not _is_reroute_instance(iid):
                continue
            fam = reroute_family_of(iid)
            for r in rows:
                rr_rows.append({**r, "family": fam, "instance": iid})
        # HEADLINE pools the leak-free families only; the diff-shape-leaky families are
        # held out (still measured below as the all-13 diagnostic).
        clean = [r for r in rr_rows if r["family"] not in REROUTE_DIFFSHAPE_LEAKY]
        stats["reroute_detect"] = reroute_detection_scores(clean) if clean else None
        stats["reroute_detect_all13"] = (
            reroute_detection_scores(rr_rows) if rr_rows else None)
        return stats

    model_rows = [f"{m} @ {c}" for m in models for c in conditions]
    for model in models:
        for cond in conditions:
            summary["models"][f"{model} @ {cond}"] = {
                s: _agg(model_records[(model, cond)][s]) for s in splits}
    for bname in bl.BASELINE_NAMES:
        summary["baselines"][bname] = {
            s: _agg(baseline_records[bname][s]) for s in splits}

    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    # Canonical provenance artifact — the single source of truth for auditing a run.
    # Written as a SEPARATE file (not only embedded in summary.json) so audit tooling
    # can load it without parsing the full summary. This resolves blocker B1 / M1:
    # the paper claims "per-call costs and the Batfish digest are logged in every run
    # manifest" — this is now true for every run that calls run_sweep.
    (out_dir / "run_manifest.json").write_text(
        json.dumps(summary["manifest"], indent=2) + "\n", encoding="utf-8")
    table = render_table(summary, model_rows, splits)
    (out_dir / "summary.md").write_text(table, encoding="utf-8")
    print(table)
    print(f"\nwrote {out_dir}/  (results.jsonl, summary.json, summary.md, run_manifest.json)")
    if any(MODEL_REGISTRY[m]["paid"] for m in models):
        print(f"[cost] estimated spend this run: ${total_cost:.4f}")
    return summary


def _baseline_pred(bname, inst, truth, modal_by_class) -> KeySets:
    if bname == "empty":
        return bl.empty_keysets()
    if bname == "naive_session_loss":
        return bl.naive_session_loss_keysets(inst.scn.change_target)
    if bname == "naive_count":
        named = next((p for p in reversed(inst.scn.watched_prefixes)
                      if not p.endswith("/32")), None)
        return bl.naive_count_keysets(inst.scn.change_target, named)
    if bname == "syntactic_diff":
        return bl.syntactic_diff_keysets(
            inst.scn.nodes, inst.scn.change_target, inst.scn.patch)
    if bname == "modal_by_class":
        return modal_by_class.get(inst.cls, bl.empty_keysets())
    if bname == "oracle_ceiling":
        return truth
    raise ValueError(bname)


def _manifest(args, models, instances, total_cost, ts, quarantined=()) -> dict:
    """Build the canonical sweep run manifest.

    This is the SWEEP manifest — a richer, sweep-specific provenance record that
    lives as ``run_manifest.json`` in the run directory (written by ``run_sweep``
    after this function returns).  It is also embedded verbatim in ``summary.json``
    under the ``"manifest"`` key for backwards-compatibility with ``render_table``
    and existing downstream tooling.

    It is DISTINCT from ``netbrace.storage.run_store.write_run_manifest``, which
    writes a ``RunManifest`` (``nethelm.run_manifest.v0``) scoped to a SINGLE
    v0-suite task run (one scenario, one model call).  The two are not
    interchangeable and must not be conflated.  See run_store.py for details.

    Fields recorded here (all required for a paid run to be auditably reproducible):
        schema_version          — "netbrace.sweep_manifest.v1"
        timestamp               — run start, UTC strftime "%Y%m%d_%H%M%S"
        command / argv          — sys.argv so the exact invocation is recoverable
        git_commit              — HEAD sha1 (or UNKNOWN if git absent)
        git_dirty               — bool: working tree had uncommitted changes
        engine                  — Batfish image digest + pybatfish version
        prompt_hash             — sha256 of safety_extended_v0.md (the prompt contract)
        models                  — registry entries for every model used
        temperature             — resolved per-model (None = not sent)
        instance_ids            — sorted list of every instance graded
        n_instances / n_templated / n_grounded
        samples_per_instance    — N samples per (instance, model)
        conditions              — ["no_tools"] / ["tools"] / both
        oracle / oracle_det_runs_in_sweep
        coarsen_class
        excluded_scenarios      — sorted list
        n_quarantined / quarantined
        estimated_cost_usd      — sum of per-sample usd (cross-check against results.jsonl)
        aggregation             — free-text description of the two-stage aggregation
        grader_routing          — per-record grader provenance
        templated_set           — reroutes / legacy / both
        bypass_fraction         — reroute bypass:no_op mix
        max_output_tokens       — output-token budget for anthropic/vllm paths
    """
    import sys as _sys
    git = _git_provenance()
    return {
        "schema_version": "netbrace.sweep_manifest.v1",
        "timestamp": ts,
        # Full argv so the run is re-runnable with a copy-paste.
        "argv": _sys.argv,
        "command": vars(args),
        # Reproducibility provenance (B1 / M1 freeze-readiness blockers).
        "git_commit": git["git_commit"],
        "git_dirty": git["git_dirty"],
        "engine": _engine_fingerprint(),
        "prompt_hash": _prompt_template_hash(),
        # Model fleet: registry entries carry pinned id, prices, paid flag.
        "models": {m: MODEL_REGISTRY[m] for m in models},
        # per-model resolved temperature (None = not sent; reasoning-model contract)
        "temperature": {m: resolve_temperature(m, args.temperature) for m in models},
        # Instance enumeration — the EXACT set graded, sorted for stable diffs.
        "instance_ids": sorted(i.instance_id for i in instances),
        "n_instances": len(instances),
        "n_templated": sum(1 for i in instances if i.split == "templated"),
        "n_grounded": sum(1 for i in instances if i.split == "grounded"),
        "samples_per_instance": args.samples,
        "conditions": [c.strip() for c in getattr(args, "condition", "no_tools").split(",")
                       if c.strip()] or ["no_tools"],
        "oracle": args.oracle,
        "oracle_det_runs_in_sweep": getattr(args, "det_runs", 2),
        "coarsen_class": getattr(args, "coarsen_class", True),
        "excluded_scenarios": sorted(
            x.strip() for x in getattr(args, "exclude", "").split(",") if x.strip()),
        "n_quarantined": len(quarantined),
        "quarantined": [q["instance"] for q in quarantined],
        "estimated_cost_usd": round(total_cost, 6),
        "aggregation": "scenario-level two-stage (per-instance mean over N samples, "
                       "then mean+/-std across instances); splits reported separately; "
                       "NOT pooled-i.i.d.",
        # M-A grader provenance: reroute instances (gen_*) use grade_keysets_semantic
        # so a /24-naming reasoner is credited for naming the config-visible covering
        # prefix of the hidden /32 probe. All other instances use grade_keysets (exact).
        # Each result row also carries a "grader" field for per-record auditability.
        "grader_routing": {
            "reroute_instances": "grade_keysets_semantic",
            "all_other_instances": "grade_keysets",
            "reroute_detect_grader": "grade_keysets_semantic",
        },
        "templated_set": getattr(args, "templated_set", "reroutes"),
        "bypass_fraction": getattr(args, "bypass_fraction", 0.5),
        "max_output_tokens": getattr(args, "max_output_tokens", 4000),
    }


# --------------------------------------------------------------------------- #
# Markdown rendering.
# --------------------------------------------------------------------------- #
_DIMS = ("sessions", "prefixes", "reachability", "waypoint", "redundancy",
         "forwarding", "scale", "bgp_withdrawn", "intent")


def _cell(stats: dict, dim: str) -> str:
    bd = stats.get("by_dimension", {})
    if dim not in bd:
        return "  -  "
    d = bd[dim]
    if d.get("n_instances", 0) == 1:
        # single-instance dimension: a point estimate, NOT a population statistic —
        # never dress it as mean±std (audit 2026-06-10 K3).
        return f"{d['mean_f1']:.2f} (n=1)"
    return f"{d['mean_f1']:.2f}±{d['std_f1']:.2f}"


def render_table(summary: dict, models: list[str], splits: list[str]) -> str:
    out: list[str] = ["# NetHELM model sweep — scenario-level results\n"]
    man = summary["manifest"]
    out.append(f"oracle=`{man['oracle']}`  samples/instance={man['samples_per_instance']}  "
               f"instances={man['n_instances']} "
               f"(templated={man['n_templated']}, grounded={man['n_grounded']})  "
               f"temperature={man['temperature']}\n")
    out.append(f"aggregation: {man['aggregation']}\n")
    out.append(f"estimated cost: ${man['estimated_cost_usd']:.4f}\n")
    if man.get("n_quarantined"):
        out.append(f"QUARANTINED instances (oracle failed {man['n_quarantined']}x — "
                   f"see quarantine.jsonl): {man['quarantined']}\n")

    rows_models = [(m, "model") for m in models]
    rows_base = [(b, "baseline") for b in bl.BASELINE_NAMES]

    for split in splits:
        out.append(f"\n## Split: {split} (reported separately — never pooled)\n")
        # per-dimension F1 table
        header = ("| system | " + " | ".join(_DIMS)
                  + " | macro_f1 | macro dmg | macro ci95 | FSA_rate | invalid |")
        sep = "|" + "---|" * (len(_DIMS) + 6)  # system+dims+macro/dmg/ci95/FSA/invalid
        out.append(header)
        out.append(sep)
        for name, kind in rows_models + rows_base:
            store = summary["models"] if kind == "model" else summary["baselines"]
            stats = store[name].get(split, {})
            if not stats or stats.get("n_instances", 0) == 0:
                if name == "modal_by_class":
                    out.append(
                        f"| {name} | " + " | ".join("-" for _ in _DIMS)
                        + " | undefined | - | - | - | - |")
                continue
            cells = " | ".join(_cell(stats, d) for d in _DIMS)
            macro = stats.get("macro_f1", {})
            fsa = stats.get("false_session_alarm_rate", {})
            inv = stats.get("invalid_rate", {})
            dmg = stats.get("macro_f1_damage")
            dmg_cell = f"{dmg['mean']:.2f}±{dmg['std']:.2f}" if dmg else "-"
            mean, sem = macro.get("mean", 0), macro.get("sem", 0)
            ci = f"[{max(0.0, mean - 1.96 * sem):.2f},{min(1.0, mean + 1.96 * sem):.2f}]"
            out.append(
                f"| {name} | {cells} | "
                f"{mean:.2f}±{macro.get('std', 0):.2f} | {dmg_cell} | {ci} | "
                f"{fsa.get('mean', 0):.2f}±{fsa.get('std', 0):.2f} | "
                f"{inv.get('mean', 0):.2f} |")
        out.append("")
        # Reroute detection headline (only when the templated split carries reroutes).
        def _f2(x):
            return f"{x:.2f}" if isinstance(x, (int, float)) else "-"
        rr_systems = [(n, k) for n, k in rows_models + rows_base
                      if (summary["models"] if k == "model" else summary["baselines"])[n]
                      .get(split, {}).get("reroute_detect")]
        if rr_systems:
            out.append("### Reroute detection — NON-GAMEABLE headline "
                       "(balanced bypass-vs-no_op accuracy)")
            out.append("| system | NetBrace-Detect | Youden_J | trap_recall [ci95] | "
                       "no_op_FAR [ci95] | n_byp/n_noop |")
            out.append("|" + "---|" * 6)
            for name, kind in rr_systems:
                store = summary["models"] if kind == "model" else summary["baselines"]
                rr = store[name][split]["reroute_detect"]
                det = rr.get("detail", {})
                trc, farc = det.get("trap_recall", {}), det.get("no_op_far", {})
                tr_ci = (f" [{_f2(trc.get('ci_lo'))},{_f2(trc.get('ci_hi'))}]"
                         if trc.get("ci_lo") is not None else "")
                far_ci = (f" [{_f2(farc.get('ci_lo'))},{_f2(farc.get('ci_hi'))}]"
                          if farc.get("ci_lo") is not None else "")
                out.append(
                    f"| {name} | {_f2(rr.get('netbrace_detect'))} | "
                    f"{_f2(rr.get('youden_j'))} | {_f2(rr.get('trap_recall'))}{tr_ci} | "
                    f"{_f2(rr.get('no_op_far'))}{far_ci} | "
                    f"{rr.get('n_bypass', '-')}/{rr.get('n_noop', '-')} |")
            out.append("")
            out.append("NetBrace-Detect = (trap_recall + (1-no_op_FAR))/2; any constant or "
                       "label-independent predictor is pinned to 0.50 (Youden_J=0). "
                       "trap_recall = recall-where-truth over D4/D10 on the bypass twins; "
                       "no_op_FAR = false-alarm rate on the diff-shape-identical no_op "
                       "calibration twins. THIS is the reroute headline — macro_f1_damage "
                       "is gameable for this split (it drops the no_op twins). Headline is "
                       "MACRO-averaged over the 12 leak-free families (equal family weight; "
                       "each verified <= permutation-null p99 against single, 2-feature AND "
                       "diff-geometry probes, test_reroute_probe_leak.py); origin_code is "
                       "HELD OUT (asymmetric diff hunk-geometry) and scored only in "
                       "reroute_detect_all13. Grader: grade_keysets_semantic (reroute instances) "
                       "— D4/D10 truth is hidden /32 probes; config-visible prefix credit "
                       "is required for a valid score. Provenance: manifest[grader_routing].")
            out.append("")
        out.append("FSA_rate = false_session_alarm rate: fraction of samples that "
                   "hallucinate a BGP session loss when none occurred. "
                   "macro dmg = damage-detection macro-F1 over instances with a "
                   "NON-EMPTY ground truth only (calibration instances — lp no_op / "
                   "scale under-kept, where the correct answer is 'no blast' — are "
                   "scored but reported via FSA/calibration, never blended into the "
                   "damage headline). invalid = unparseable-output rate (formatting "
                   "failure, scored 0 — reported separately so it is never conflated "
                   "with reasoning failure). '(n=1)' cells are single-instance point "
                   "estimates. modal_by_class 'undefined' = every class in this "
                   "split has one instance, so the memorization floor is not "
                   "computable (it would equal the oracle ceiling).")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", default="fake",
                    help="comma-separated; 'fake'/'fake-oracle' (zero-API) or "
                         "'anthropic/<id>' (PAID). Default fake.")
    ap.add_argument("--samples", type=int, default=5, help="N samples per (instance, model)")
    ap.add_argument("--split", default="both", choices=["templated", "grounded", "both"])
    ap.add_argument("--n-generated", type=int, default=12,
                    help="number of templated (generated) instances")
    ap.add_argument("--seed", type=int, default=0, help="base seed for generated instances")
    ap.add_argument("--templated-set", default="reroutes",
                    choices=["legacy", "reroutes", "both"], dest="templated_set",
                    help="which templated mechanism family to sweep: legacy "
                         "(ipc/leak/lp/scale), reroutes (the 13 quiet-reroute generators "
                         "— the bypass+no_op detection split, the default), or both.")
    ap.add_argument("--bypass-fraction", type=float, default=0.5, dest="bypass_fraction",
                    help="reroute bypass:no_op mix. 0.5 = paired calibration twins "
                         "(include_noop=True, the anti-gaming control); 1.0 = bypass-only. "
                         "NetBrace-Detect is balanced accuracy so the floor stays 0.5 "
                         "regardless of mix.")
    ap.add_argument("--temperature", type=float, default=None,
                    help="OVERRIDE only (diagnostics). Default: per-family policy "
                         "(freeze gate 2026-06-10) — anthropic/vllm/fake sample at "
                         "0.7; openai/gemini reasoning models are never sent a "
                         "temperature. See resolve_temperature().")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap total instances (pre-flight smoke; e.g. --limit 1 "
                         "for the mandatory single-call sanity check per provider)")
    ap.add_argument("--include", default="",
                    help="comma-separated instance_ids to run EXCLUSIVELY — the "
                         "surgical top-up mode for an incomplete run (paste the "
                         "ids from its completeness.json; keep --split/"
                         "--n-generated/--seed identical to the original run so "
                         "the instance set and prompts match).")
    ap.add_argument("--exclude", default="blackhole",
                    help="comma-separated grounded scenario names to EXCLUDE. "
                         "Default 'blackhole' (freeze gate 2026-06-10: CONTRIVED — "
                         "the static-underlay crutch is the manufactured bug; "
                         "excluded from paid runs until the IGP rebuild lands).")
    ap.add_argument("--condition", default="no_tools",
                    help="comma-separated: 'no_tools' (configs+diff+intent only) and/or "
                         "'tools' (SAME prompt + PRE-change observed state: show ip bgp "
                         "summary / show ip route from the PRE snapshot). 'tools' requires "
                         "--oracle batfish. Default no_tools.")
    ap.add_argument("--oracle", default="fake", choices=["fake", "batfish"],
                    help="'fake' = synthetic zero-Batfish GT (validation only); "
                         "'batfish' = real ExtendedOracle (required for paid models)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--coarsen-class", action=argparse.BooleanOptionalAction,
                    default=True, dest="coarsen_class",
                    help="coarsen templated modal_by_class to the {prefix}-{match} "
                         "structural pair so instances share a class at modest n "
                         "(makes modal_by_class a REAL memorization floor instead of "
                         "the degenerate one-instance-per-class ceiling). DEFAULT ON "
                         "(audit 2026-06-10 K1); --no-coarsen-class only for "
                         "diagnostics — never for reported figures.")
    ap.add_argument("--max-output-tokens", type=int, default=4000,
                    dest="max_output_tokens",
                    help="output-token budget for the anthropic/vllm call paths "
                         "(default 4000 = the 2026-06-10 freeze value; raise for "
                         "models that hard-truncate, e.g. Sonnet 4.6 at 12000). "
                         "Recorded in the run manifest.")
    ap.add_argument("--det-runs", type=int, default=2, dest="det_runs",
                    help="in-sweep oracle determinism check: compute the ground "
                         "truth this many times per instance and require "
                         "byte-identical results (>=2; 0/1 disables — the full "
                         ">=10x gate remains scripts/verify_determinism.py).")
    args = ap.parse_args()

    global MAX_OUTPUT_TOKENS
    MAX_OUTPUT_TOKENS = args.max_output_tokens

    if any(MODEL_REGISTRY.get(m.strip(), {}).get("paid") for m in args.models.split(",")):
        if args.oracle != "batfish":
            raise SystemExit(
                "a PAID model requires --oracle batfish (the fake oracle is "
                "validation-only and would grade real spend against synthetic GT).")
    conds = [c.strip() for c in args.condition.split(",") if c.strip()]
    if "tools" in conds and args.oracle != "batfish":
        raise SystemExit(
            "--condition tools requires --oracle batfish (the PRE-state observation "
            "is extracted from the real PRE snapshot).")
    if any(c not in ("no_tools", "tools") for c in conds):
        raise SystemExit(f"--condition values must be no_tools/tools; got {conds}")
    run_sweep(args)


if __name__ == "__main__":
    main()
