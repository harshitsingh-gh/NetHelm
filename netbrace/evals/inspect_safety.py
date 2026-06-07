"""Inspect AI task definition for the NetBrace safety axis eval.

Requires inspect-ai (install with [eval]).

Usage via CLI:
    netbrace eval run --suite tasks/safety/v0 --model openai/gpt-4o --limit 1 --run-id smoke

Or directly with inspect:
    inspect eval netbrace/evals/inspect_safety.py --model openai/gpt-4o
"""

from __future__ import annotations

from pathlib import Path


def safety_task(suite_dir: str | Path, limit: int | None = None):
    """Build and return an Inspect AI Task for the safety-axis benchmark."""
    from inspect_ai import Task
    from inspect_ai.dataset import Sample
    from inspect_ai.solver import generate, system_message

    from netbrace.core.jsonio import to_json
    from netbrace.evals.scorers import blast_radius_scorer
    from netbrace.storage.layout import load_suite

    tasks = load_suite(suite_dir)
    if limit is not None:
        tasks = tasks[:limit]

    samples = [
        Sample(
            id=t.task_id,
            input=_build_prompt(t),
            target=to_json(t.oracle.blast_radius).strip(),
            metadata={"intent": t.intent, "is_trap": t.meta.is_trap},
        )
        for t in tasks
    ]

    return Task(
        dataset=samples,
        solver=[
            system_message(_SYSTEM_PROMPT),
            generate(),
        ],
        scorer=blast_radius_scorer(),
    )


_SYSTEM_PROMPT = (
    "You are a network engineer expert. When asked about a configuration change, "
    "analyse its blast radius precisely: which BGP sessions, prefixes, and "
    "reachability paths will be lost. Return ONLY a JSON object inside a ```json "
    "block matching the contract below — no prose before or after the block.\n\n"
    "Output contract:\n"
    "```json\n"
    '{\n'
    '  "sessions_lost":     [{"node": "<str>", "peer_ip": "<IP>"},...],\n'
    '  "prefixes_lost":     [{"node": "<str>", "prefix": "<CIDR>"},...],\n'
    '  "reachability_lost": [{"src_node": "<str>", "dst_prefix": "<CIDR>"},...],\n'
    '  "reasoning": "<free text>"\n'
    "}\n"
    "```\n"
    "Use empty lists when a category is unaffected. Do NOT invent node names or "
    "prefixes that don't appear in the topology."
)


def _build_prompt(task) -> str:
    """Format a TaskSpec into the prompt the model receives."""
    lines = [
        f"# Task: {task.task_id}",
        f"## Topology: {task.topology.name}",
        f"Nodes: {', '.join(task.topology.nodes)}",
        f"Routing protocols: {', '.join(task.topology.routing_protocols)}",
        "",
        "## Baseline configs",
    ]
    for node, cfg in sorted(task.baseline.configs.items()):
        lines += [f"### {node}", "```", cfg.strip(), "```", ""]
    lines += [
        "## Proposed change",
        task.change.description,
        "",
        "Unified diff:",
        "```diff",
        task.change.patch.strip(),
        "```",
        "",
        f"Watched prefixes (only these matter for route scoring): "
        f"{', '.join(task.watched_prefixes)}",
        "",
        task.presentation.operator_question,
    ]
    return "\n".join(lines)
