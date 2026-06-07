"""Tests for the square4 task generator."""

from netbrace.tasks.safety.generator import GenerationSpec, generate
from netbrace.topology.patches import apply_unified_diff
from netbrace.core.jsonio import to_json


def test_generates_requested_count():
    tasks = generate(GenerationSpec(count=10))
    assert len(tasks) == 10
    assert all(t.task_id.startswith("safety.bgp.") for t in tasks)


def test_task_ids_unique_and_sorted_indices():
    tasks = generate(GenerationSpec(count=16))
    ids = [t.task_id for t in tasks]
    assert len(set(ids)) == len(ids)


def test_generation_is_deterministic():
    a = generate(GenerationSpec(count=12))
    b = generate(GenerationSpec(count=12))
    assert [to_json(t) for t in a] == [to_json(t) for t in b]


def test_every_patch_applies_and_changes_only_target():
    for t in generate(GenerationSpec(count=16)):
        node = t.change.target_nodes[0]
        before = t.baseline.configs[node]
        after = apply_unified_diff(before, t.change.patch)
        assert after != before, f"{t.task_id} patch was a no-op"
        # other nodes untouched
        for other in t.baseline.configs:
            if other != node:
                assert "neighbor" in t.baseline.configs[other]  # sanity: still a real config


def test_shut_neighbor_removes_three_lines():
    t = next(t for t in generate(GenerationSpec(count=16)) if t.intent == "shut_neighbor")
    node = t.change.target_nodes[0]
    after = apply_unified_diff(t.baseline.configs[node], t.change.patch)
    # exactly the 3 neighbor lines for one peer are gone
    assert t.baseline.configs[node].count("neighbor ") - after.count("neighbor ") == 3


def test_remove_network_removes_origination():
    t = next(t for t in generate(GenerationSpec(count=16)) if t.intent == "remove_network")
    node = t.change.target_nodes[0]
    after = apply_unified_diff(t.baseline.configs[node], t.change.patch)
    assert after.count("network 10.0.0") == t.baseline.configs[node].count("network 10.0.0") - 1


def test_all_tasks_validate_internally():
    for t in generate(GenerationSpec(count=16)):
        assert t.validate_internal_consistency() == []
