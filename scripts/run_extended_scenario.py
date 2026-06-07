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
from netbrace.evals.extended_parser import parse_extended_prediction
from netbrace.graders.extended import grade_extended
from netbrace.models.fake_extended import ExtendedFakeModel
from netbrace.tasks.safety import scenarios

_PROMPT_MD = Path(__file__).resolve().parents[1] / "netbrace/prompts/safety_extended_v0.md"


def _build_prompt(scn: scenarios.Scenario) -> str:
    """System contract (from the template md) + a concrete task block."""
    system = _PROMPT_MD.read_text(encoding="utf-8").split("## TASK TEMPLATE")[0].strip()
    cfgs = "\n".join(f"#### {n}\n```\n{c}\n```" for n, c in sorted(scn.pre_configs.items()))
    task = (
        f"## TASK\n\n### Topology: {scn.name}\n"
        f"Nodes: {', '.join(scn.nodes)}\n\n"
        f"### Intents\n{scn.intents_text}\n\n"
        f"### Baseline configuration\n{cfgs}\n\n"
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, choices=sorted(scenarios.REGISTRY))
    ap.add_argument("--model", default="fake",
                    help="'fake' (zero API) or 'anthropic/<id>' (PAID)")
    ap.add_argument("--mode", default="oracle", choices=["oracle", "empty", "garbage"],
                    help="ExtendedFakeModel mode (only used when --model fake)")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    scn = scenarios.build(args.scenario)
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
    sr = grade_extended(pred, truth, task_id=f"{args.scenario}_{args.model.replace('/', '_')}")

    print(f"scenario={args.scenario} model={args.model}")
    print("ground truth :", sorted(k for ks in truth.key_sets().values() for k in ks))
    print(f"status={sr.status} macro_f1={sr.macro_f1} micro_f1={sr.micro_f1} "
          f"exact={sr.exact_match} active={sr.active_types}")

    out = Path(f"runs/run_ext_{args.scenario}_{args.model.replace('/', '_')}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "response.raw.txt").write_text(raw, encoding="utf-8")
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    (out / "score.json").write_text(sr.model_dump_json(indent=2), encoding="utf-8")
    print(f"wrote {out}/")


if __name__ == "__main__":
    main()
