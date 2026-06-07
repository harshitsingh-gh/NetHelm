"""Tests for the strict unified-diff applier."""

import pytest

from netbrace.topology.patches import PatchError, apply_unified_diff


BASE = "router bgp 65000\n neighbor 10.0.0.2 remote-as 65000\n network 10.0.0.1/32\n"


# NOTE: BASE lines 2 and 3 are indented by one space (FRR style). A unified-diff
# context/removal line is the diff tag char FOLLOWED BY the exact source line, so
# those lines start with TWO spaces here: the tag space + the config's indent.
def test_add_line_after_context():
    patch = (
        "@@ -2,1 +2,2 @@\n"
        "  neighbor 10.0.0.2 remote-as 65000\n"
        "+ neighbor 10.0.0.2 shutdown\n"
    )
    out = apply_unified_diff(BASE, patch)
    assert "neighbor 10.0.0.2 shutdown" in out
    assert out.endswith("\n")
    assert out.count("\n") == BASE.count("\n") + 1


def test_remove_line():
    patch = (
        "@@ -2,1 +1,0 @@\n"
        "- neighbor 10.0.0.2 remote-as 65000\n"
    )
    out = apply_unified_diff(BASE, patch)
    assert "remote-as" not in out


def test_headers_are_ignored():
    patch = (
        "--- r1.conf\n+++ r1.conf\n"
        "@@ -3,1 +3,2 @@\n"
        "  network 10.0.0.1/32\n"
        "+ network 10.0.0.5/32\n"
    )
    out = apply_unified_diff(BASE, patch)
    assert "10.0.0.5/32" in out


def test_context_mismatch_raises():
    patch = (
        "@@ -2,1 +2,2 @@\n"
        "  neighbor 10.0.0.9 remote-as 65000\n"  # wrong context (10.0.0.9)
        "+ neighbor 10.0.0.9 shutdown\n"
    )
    with pytest.raises(PatchError):
        apply_unified_diff(BASE, patch)


def test_malformed_hunk_header_raises():
    with pytest.raises(PatchError):
        apply_unified_diff(BASE, "not a hunk\n+stuff\n")


def test_deterministic():
    patch = "@@ -3,1 +3,2 @@\n  network 10.0.0.1/32\n+ network 10.0.0.5/32\n"
    assert apply_unified_diff(BASE, patch) == apply_unified_diff(BASE, patch)
