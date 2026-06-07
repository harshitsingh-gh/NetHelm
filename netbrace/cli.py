"""netbrace CLI — one entry point, argparse subcommands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cmd_safety_generate(args: argparse.Namespace) -> None:
    from netbrace.storage.layout import write_suite
    from netbrace.tasks.safety.generator import GenerationSpec, generate

    tasks = generate(GenerationSpec(count=args.count))
    root = write_suite(tasks, args.out)
    print(root)


def _cmd_safety_validate(args: argparse.Namespace) -> None:
    from netbrace.storage.layout import load_suite

    tasks = load_suite(args.suite)
    errors: list[str] = []
    for t in tasks:
        if args.require_oracle and t.oracle.status != "ready":
            errors.append(f"{t.task_id}: oracle.status={t.oracle.status!r} (not ready)")
        for p in t.validate_internal_consistency():
            errors.append(f"{t.task_id}: {p}")
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)
    print(f"OK — {len(tasks)} tasks valid")


def _cmd_safety_oracle(args: argparse.Namespace) -> None:
    from datetime import datetime, timezone

    from netbrace.batfish.oracle import BatfishOracle, compute_with_determinism_check
    from netbrace.storage.layout import load_suite, write_task

    tasks = load_suite(args.suite)
    oracle = BatfishOracle(host=args.host)
    for task in tasks:
        try:
            br, det = compute_with_determinism_check(
                oracle, task, with_reachability=args.reachability
            )
            task.oracle.status = "ready"
            task.oracle.blast_radius = br
            task.oracle.deterministic = det
            task.oracle.computed_at = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            task.oracle.status = "error"
            task.oracle.error = str(exc)
            print(f"ERROR {task.task_id}: {exc}", file=sys.stderr)
        write_task(task, args.suite)
    print(Path(args.suite).resolve())


def _cmd_eval_fake(args: argparse.Namespace) -> None:
    from netbrace.evals.run_fake import run_fake

    run_dir = run_fake(args.suite, args.run_id, mode=args.mode)
    print(run_dir)


def _cmd_eval_run(args: argparse.Namespace) -> None:
    from inspect_ai import eval as inspect_eval

    from netbrace.evals.inspect_safety import safety_task
    from netbrace.storage.run_store import create_run

    run_dir = create_run(args.run_id)
    log_dir = run_dir / "logs"
    t = safety_task(args.suite, limit=args.limit)
    inspect_eval(t, model=args.model, log_dir=str(log_dir))
    print(run_dir)


def _cmd_grade(args: argparse.Namespace) -> None:
    from netbrace.storage.run_store import write_results_csv

    csv_path = write_results_csv(Path(args.run))
    print(csv_path)


def _cmd_report(args: argparse.Namespace) -> None:
    from netbrace.reporting.summarize import summarize
    from netbrace.reporting.figures import f1_by_intent

    run_dir = Path(args.run)
    summarize(run_dir)
    out_pdf = Path(args.figures) / "safety_f1_by_intent.pdf"
    f1_by_intent(run_dir, out_pdf)
    print(out_pdf)


def main() -> None:
    parser = argparse.ArgumentParser(prog="netbrace")
    sub = parser.add_subparsers(dest="group", required=True)

    # --- safety group ---
    safety = sub.add_parser("safety")
    ssub = safety.add_subparsers(dest="command", required=True)

    gen_p = ssub.add_parser("generate")
    gen_p.add_argument("--count", type=int, default=20)
    gen_p.add_argument("--out", required=True)
    gen_p.set_defaults(func=_cmd_safety_generate)

    val_p = ssub.add_parser("validate")
    val_p.add_argument("--suite", required=True)
    val_p.add_argument("--require-oracle", action="store_true")
    val_p.set_defaults(func=_cmd_safety_validate)

    orc_p = ssub.add_parser("oracle")
    orc_p.add_argument("--suite", required=True)
    orc_p.add_argument("--host", default="127.0.0.1")
    orc_p.add_argument("--reachability", action="store_true")
    orc_p.set_defaults(func=_cmd_safety_oracle)

    # --- eval group ---
    eval_p = sub.add_parser("eval")
    esub = eval_p.add_subparsers(dest="command", required=True)

    fake_p = esub.add_parser("fake")
    fake_p.add_argument("--suite", required=True)
    fake_p.add_argument("--run-id", required=True)
    fake_p.add_argument("--mode", default="oracle",
                        choices=["oracle", "empty", "garbage"])
    fake_p.set_defaults(func=_cmd_eval_fake)

    run_p = esub.add_parser("run")
    run_p.add_argument("--suite", required=True)
    run_p.add_argument("--model", required=True)
    run_p.add_argument("--run-id", required=True)
    run_p.add_argument("--limit", type=int)
    run_p.set_defaults(func=_cmd_eval_run)

    # --- grade ---
    grade_p = sub.add_parser("grade")
    grade_p.add_argument("--run", required=True)
    grade_p.set_defaults(func=_cmd_grade)

    # --- report ---
    report_p = sub.add_parser("report")
    report_p.add_argument("--run", required=True)
    report_p.add_argument("--figures", required=True)
    report_p.set_defaults(func=_cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
