#!/usr/bin/env python
"""Run an extended-dimension scenario end to end: prompt -> model -> parse -> grade.

Ground truth comes from the UNIFIED oracle (ExtendedOracle.compute), which fills
every dimension on one pair of snapshots. Default model is the zero-API
ExtendedFakeModel; pass --model anthropic/<id> (with ANTHROPIC_API_KEY) to score
a real model like Claude — that path calls a paid API, so it is never the default.

Examples
--------
    python scripts/run_extended_scenario.py --scenario waypoint
    python scripts/run_extended_scenario.py --scenario blackhole --model anthropic/claude-haiku-4-5-20251001

Requires a running Batfish (for the oracle) and the [oracle] extra.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from netbrace.batfish.extended_oracle import ExtendedOracle
from netbrace.core.dimensions import ExtendedBlastRadius
from netbrace.core.schemas import BlastRadius, SessionLost
from netbrace.evals.extended_parser import parse_extended_prediction
from netbrace.graders.extended import grade_extended
from netbrace.models.fake_extended import ExtendedFakeModel
from netbrace.tasks.safety import scenarios


def _baseline_predictions(scn: scenarios.Scenario) -> dict[str, ExtendedBlastRadius]:
    """Dumb, model-independent baselines that a real model must beat.

    * empty           — predict nothing (recall floor).
    * naive_session_loss — the documented LLM reflex: "a BGP change → a session
      drops." Predicts one session loss on the change target and nothing else. On
      every NetHELM scenario (sessions actually stay up) this is a pure false alarm,
      so it should score macro_f1≈0 AND trip false_session_alarm — demonstrating the
      trap discriminates against the naive heuristic.
    """
    target = scn.change_target or scn.nodes[0]
    return {
        "empty": ExtendedBlastRadius(),
        "naive_session_loss": ExtendedBlastRadius(
            base=BlastRadius(sessions_lost=[
                SessionLost(node=target, peer_ip="0.0.0.0", vrf="default")
            ])
        ),
    }

_PROMPT_MD = Path(__file__).resolve().parents[1] / "netbrace/prompts/safety_extended_v0.md"


# The verification-gate reframe (scrutiny_2026-06-09.md change #1): frame the task
# as the pre-deployment trust gate / autonomy-rung-2->3 graduation test. States the
# ROLE of the prediction (an operator decides whether to trust the change BEFORE
# applying it) — NOT the outcome of any specific change, so prompt-hygiene holds.
_GATE_FRAMING = (
    "You are the verification gate reviewing a proposed configuration change "
    "BEFORE it is applied to a live, already-converged network. An operator will "
    "use your prediction to decide whether the change is safe to apply or must be "
    "held for manual review. Predict the change's BLAST RADIUS — the full set of "
    "typed damage it will cause once the network reconverges — so that decision is "
    "well-founded. Predicting damage that will NOT occur (a false alarm) erodes "
    "trust just as predicting too little (a missed harm) does; be precise on both."
)


def _build_prompt(scn: scenarios.Scenario, pre_state: str | None = None) -> str:
    """System contract (from the template md) + a concrete task block.

    ``pre_state`` (the TOOLS-AUGMENTED condition): if given, the PRE-change observed
    network state (``show ip bgp summary`` / ``show ip route``) the operator would
    gather is appended — a ONE-SHOT retrieval, not an agentic loop. It is the PRE
    state only (never the post-state, which would be the answer). When ``None`` this
    is the no-tools condition (the original prompt). Both conditions are graded by
    the identical oracle + grader.
    """
    system = _PROMPT_MD.read_text(encoding="utf-8").split("## TASK TEMPLATE")[0].strip()
    system = f"{system}\n\n## REVIEW CONTEXT\n\n{_GATE_FRAMING}"
    cfgs = "\n".join(f"#### {n}\n```\n{c}\n```" for n, c in sorted(scn.pre_configs.items()))
    tools_block = ""
    if pre_state is not None:
        tools_block = (
            "### Observed PRE-change network state\n"
            "Before deciding, you gathered the CURRENT (pre-change) state from the "
            "devices. This is the live state BEFORE the change is applied — it does "
            "NOT reflect the proposed change. Use it to ground your prediction.\n\n"
            f"```\n{pre_state}\n```\n\n"
        )
    # PROMPT HYGIENE (red-team freeze gate 2026-06-10, INVALIDATOR #1): the scenario
    # name encodes the answer category (e.g. generator dims_labels like "no_op",
    # "ms_blackhole", "under-kept") and must NEVER reach the model. The model sees a
    # content-free deterministic label; the name stays in run artifacts only.
    import hashlib as _hashlib
    neutral = f"topology_{_hashlib.sha256(scn.name.encode()).hexdigest()[:8]}"
    task = (
        f"## TASK\n\n### Topology: {neutral}\n"
        f"Nodes: {', '.join(scn.nodes)}\n\n"
        f"### Intents\n{scn.intents_text}\n\n"
        f"### Baseline configuration\n{cfgs}\n\n"
        f"{tools_block}"
        f"### Proposed change\n{scn.description}\n\n```diff\n{scn.patch}```\n\n"
        f"Watched prefixes: {', '.join(scn.watched_prefixes)}\n\n"
        f"What is the blast radius across all eight dimensions?"
    )
    return f"{system}\n\n{task}"


def _call_anthropic(model_id: str, prompt: str) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set — required for a real model run.")
    import anthropic  # lazy; only needed for the paid path

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model_id, max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(getattr(b, "text", "") for b in msg.content)


def _run_one(scn: scenarios.Scenario, args) -> None:
    """Run + grade a single scenario (hand-authored or generated) and write artifacts."""
    truth = ExtendedOracle(host=args.host).compute(scn)
    prompt = _build_prompt(scn)

    if args.model == "fake":
        raw = ExtendedFakeModel(args.mode).respond(truth)
    elif args.model.startswith("anthropic/"):
        print(f"[paid] calling {args.model} ...")
        raw = _call_anthropic(args.model.split("/", 1)[1], prompt)
    else:
        raise SystemExit(f"unsupported --model {args.model!r}")

    pred = parse_extended_prediction(raw)
    sr = grade_extended(pred, truth, is_trap=scn.is_trap,
                        task_id=f"{scn.name}_{args.model.replace('/', '_')}")

    print(f"scenario={scn.name} provenance={getattr(scn, 'provenance', 'handauthored')} "
          f"model={args.model} is_trap={scn.is_trap}")
    print("ground truth :", sorted(k for ks in truth.key_sets().values() for k in ks))
    print(f"status={sr.status} macro_f1={sr.macro_f1} micro_f1={sr.micro_f1} "
          f"exact={sr.exact_match} false_session_alarm={sr.false_session_alarm} "
          f"active={sr.active_types}")

    for bname, bpred in _baseline_predictions(scn).items():
        bsr = grade_extended(bpred, truth, is_trap=scn.is_trap,
                             task_id=f"{scn.name}_baseline_{bname}")
        gap = sr.macro_f1 - bsr.macro_f1
        print(f"baseline[{bname}]: macro_f1={bsr.macro_f1} "
              f"false_session_alarm={bsr.false_session_alarm} "
              f"-> model beats by {gap:+.2f}")

    out = Path(f"runs/run_ext_{scn.name}_{args.model.replace('/', '_')}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "response.raw.txt").write_text(raw, encoding="utf-8")
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    (out / "score.json").write_text(sr.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {out}/")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=sorted(scenarios.REGISTRY),
                    help="a hand-authored (GROUNDED) scenario from the registry")
    ap.add_argument("--generated", type=int, default=0,
                    help="run N GENERATED (templated) Class-1 instances instead")
    ap.add_argument("--seed", type=int, default=0,
                    help="base seed for --generated (reproducible numbering)")
    ap.add_argument("--model", default="fake",
                    help="'fake' (zero API) or 'anthropic/<id>' (PAID)")
    ap.add_argument("--mode", default="oracle", choices=["oracle", "empty", "garbage"],
                    help="ExtendedFakeModel mode (only used when --model fake)")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    # GENERATED path: enumerate N templated Class-1 instances and run each.
    if args.generated > 0:
        suite = scenarios.build_generated_suite(args.generated, base_seed=args.seed)
        print(f"running {len(suite)} GENERATED Class-1 instances "
              f"(base_seed={args.seed}, model={args.model})")
        for scn in suite:
            _run_one(scn, args)
        return

    if not args.scenario:
        raise SystemExit("pass --scenario <name> or --generated N")

    scn = scenarios.build(args.scenario)
    _run_one(scn, args)


if __name__ == "__main__":
    main()
