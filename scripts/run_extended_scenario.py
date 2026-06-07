#!/usr/bin/env python
"""Run an extended-dimension scenario end to end: prompt -> model -> parse -> grade.

Default model is the zero-API ExtendedFakeModel (proves the full loop). The same
command runs a REAL model (e.g. Claude) by passing --model anthropic/<id> with
ANTHROPIC_API_KEY set — that path calls a paid API, so it is never the default.

Examples
--------
    # zero API: prove the loop on the live waypoint oracle
    python scripts/run_extended_scenario.py --scenario waypoint

    # real model (PAID — needs ANTHROPIC_API_KEY; do --limit-style single runs)
    python scripts/run_extended_scenario.py --scenario blackhole --model anthropic/claude-sonnet-4-6

Requires a running Batfish (for the oracle) and the [oracle] extra.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from netbrace.batfish.extended_oracle import ExtendedOracle
from netbrace.core.dimensions import ExtendedBlastRadius
from netbrace.evals.extended_parser import parse_extended_prediction
from netbrace.graders.extended import grade_extended
from netbrace.models.fake_extended import ExtendedFakeModel
from netbrace.tasks.safety import baseline_ecmp4 as ec
from netbrace.tasks.safety import baseline_waypoint4 as wp
from netbrace.tasks.safety import scenario_blackhole as bh
from netbrace.topology.patches import apply_unified_diff

_PROMPT_MD = Path(__file__).resolve().parents[1] / "netbrace/prompts/safety_extended_v0.md"


def _oracle_truth(scenario: str, host: str) -> tuple[ExtendedBlastRadius, dict]:
    """Compute live Batfish ground truth + the prompt context for a scenario."""
    oracle = ExtendedOracle(host=host)
    if scenario == "waypoint":
        pre = wp.baseline_configs()
        post = dict(pre)
        post[wp.CHANGE_TARGET] = apply_unified_diff(post[wp.CHANGE_TARGET], wp.change_patch())
        truth = oracle.compute_waypoint(pre, post, wp.WAYPOINT_INTENTS)
        ctx = {
            "name": "waypoint4", "nodes": wp.NODES, "configs": pre,
            "description": "Reroute src->dst (10.0.0.4/32) off the `way` node onto `alt`.",
            "patch": wp.change_patch(), "watched": wp.WATCHED_PREFIXES,
            "intents": "src->10.0.0.4/32 MUST transit `way` (inspection node).",
        }
    elif scenario == "blackhole":
        pre = bh.baseline_configs()
        post = dict(pre)
        post[bh.CHANGE_TARGET] = apply_unified_diff(post[bh.CHANGE_TARGET], bh.change_patch())
        truth = oracle.compute_forwarding(pre, post, bh.PROBE_FLOWS)
        ctx = {
            "name": "square4", "nodes": bh.baseline_configs().keys(), "configs": pre,
            "description": "Remove r1's static route to 10.0.0.4/32 (looks redundant).",
            "patch": bh.change_patch(), "watched": bh.WATCHED_PREFIXES,
            "intents": "All loopbacks must remain reachable from every node.",
        }
    elif scenario == "ecmp":
        pre = ec.baseline_configs()
        post = dict(pre)
        post[ec.CHANGE_TARGET] = apply_unified_diff(post[ec.CHANGE_TARGET], ec.change_patch())
        truth = oracle.compute_redundancy(pre, post, ec.REDUNDANCY_TARGETS)
        ctx = {
            "name": "ecmp4", "nodes": ec.NODES, "configs": pre,
            "description": "Remove one of src's two equal-cost static routes to 10.0.0.4/32.",
            "patch": ec.change_patch(), "watched": ec.WATCHED_PREFIXES,
            "intents": "src->10.0.0.4/32 must keep 2 equal-cost paths for resilience.",
        }
    else:
        raise SystemExit(f"unknown scenario {scenario!r} (use waypoint|blackhole|ecmp)")
    return truth, ctx


def _build_prompt(ctx: dict) -> str:
    """System contract (from the template md) + a concrete task block."""
    md = _PROMPT_MD.read_text(encoding="utf-8")
    system = md.split("## TASK TEMPLATE")[0].strip()
    cfgs = "\n".join(f"#### {n}\n```\n{c}\n```" for n, c in sorted(ctx["configs"].items()))
    task = (
        f"## TASK\n\n### Topology: {ctx['name']}\n"
        f"Nodes: {', '.join(ctx['nodes'])}\n\n"
        f"### Intents\n{ctx['intents']}\n\n"
        f"### Baseline configuration\n{cfgs}\n\n"
        f"### Proposed change\n{ctx['description']}\n\n```diff\n{ctx['patch']}```\n\n"
        f"Watched prefixes: {', '.join(ctx['watched'])}\n\n"
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
    ap.add_argument("--scenario", required=True, choices=["waypoint", "blackhole", "ecmp"])
    ap.add_argument("--model", default="fake",
                    help="'fake' (zero API) or 'anthropic/<id>' / 'openai/<id>' (PAID)")
    ap.add_argument("--mode", default="oracle", choices=["oracle", "empty", "garbage"],
                    help="ExtendedFakeModel mode (only used when --model fake)")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    truth, ctx = _oracle_truth(args.scenario, args.host)
    prompt = _build_prompt(ctx)

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
