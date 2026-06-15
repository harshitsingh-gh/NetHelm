"""Regression guard for the `remove_network` v0-oracle FALSE-QUIET trap.

Audit 2026-06-15 (paper/refs/scenario_validity_audit_2026-06-15.md, finding B1):
the frozen v0 generator's default `GenerationSpec.intents` includes
`remove_network`, but the v0 `BatfishOracle` has no BGP-RIB / D9 term. On the
square4 baseline the loopback prefixes are also backed by static routes
(admin-distance 1), so removing a `network 10.0.0.X/32` origination line leaves
the prefix in the MAIN RIB — the v0 `prefixes_lost` diff sees nothing and grades
the change as a COMPLETELY EMPTY blast radius, even though every peer loses the
prefix from its BGP RIB. A model that *correctly* flags that 4-element BGP-RIB
withdrawal would be scored a false positive against the empty GT — the exact
pathology NetBrace exists to catch.

The shipped v0 suite (`tasks/safety/v0/`) is therefore `shut_neighbor`-only. This
test PINS that invariant so a `remove_network` task can never be silently
committed into the v0 suite (where it would carry wrong, empty ground truth).

The generator itself is frozen (HANDOFF golden rule #1), so the fix is to pin the
safe shipped state here and document the trap (docs/batfish_oracle_runbook.md,
docs/project_guide.md). The correct, gradeable form of a prefix-withdrawal event
is the D9 path: `ExtendedOracle` with `bgp_watch_prefixes` set (see the `ipc`
scenario).
"""

from pathlib import Path

from netbrace.storage.layout import load_suite

_V0_SUITE = Path(__file__).resolve().parents[2] / "tasks" / "safety" / "v0"


def test_committed_v0_suite_has_no_remove_network_tasks():
    """The shipped v0 suite must never contain a `remove_network` task, which the
    v0 oracle grades as a false-quiet (empty GT)."""
    tasks = load_suite(_V0_SUITE)
    offenders = [t.task_id for t in tasks if t.intent == "remove_network"]
    assert offenders == [], (
        "remove_network is a v0-oracle false-quiet (empty GT under the v0 "
        "BatfishOracle); it must not be committed into the v0 suite. Offending "
        f"tasks: {offenders}. Grade prefix-withdrawal via ExtendedOracle + "
        "bgp_watch_prefixes (D9) instead."
    )


def test_committed_v0_suite_is_shut_neighbor_only():
    """Pin the exact shipped state: 12 shut_neighbor tasks, nothing else."""
    tasks = load_suite(_V0_SUITE)
    intents = sorted({t.intent for t in tasks})
    assert intents == ["shut_neighbor"], f"unexpected v0 intents: {intents}"
    assert len(tasks) == 12, f"expected 12 v0 tasks, found {len(tasks)}"
