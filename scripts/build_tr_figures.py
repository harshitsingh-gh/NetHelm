#!/usr/bin/env python
"""Build the figures for the arXiv technical report from the v1 sweep artifacts.

Reads ONLY committed/saved run artifacts (no hand-typed numbers): the
consolidated semantic regrade pointed to by REGRADE below (summary.json +
per-sample results.jsonl), in which Sonnet's grounded rows are the 12k-cap
re-run (Disclosure ii). All figures report the SEMANTIC grader ("new"); the
exact-string grader is the appendix lower bound and is not plotted. The
gradient figure plots F1 where each consequence dimension is the ground
truth (not active-convention dimensional means, which are precision-dragged).

Writes paper/draft/figs/{fig_heatmap,fig_gradient,fig_floors}.pdf and prints paths.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "draft" / "figs"

REGRADE = ROOT / "runs/regrade_semantic_20260613_101508"  # 12k Sonnet baked in
# When the 12k-cap Sonnet grounded re-run is regraded, point this at that regrade
# dir; Sonnet's grounded cells are then read from it instead of REGRADE.
SONNET_OVERRIDE: Path | None = None

SONNET_KEY = "anthropic/claude-sonnet-4-6 @ no_tools"

# display order: descending grounded macro (matches Table 2 / appendix)
MODELS = [
    ("Opus-4.8",       "anthropic/claude-opus-4-8 @ no_tools"),
    ("Gemini-3.5-F",   "gemini/gemini-3.5-flash @ no_tools"),
    ("GPT-5.5",        "openai/gpt-5.5 @ no_tools"),
    ("Sonnet-4.6",     SONNET_KEY),
    ("Haiku-4.5",      "anthropic/claude-haiku-4-5-20251001 @ no_tools"),
    ("GPT-5.4-mini",   "openai/gpt-5.4-mini @ no_tools"),
]
DIMS = ["sessions", "prefixes", "reachability", "waypoint", "redundancy",
        "forwarding", "scale", "bgp_withdrawn", "intent"]
DIM_LABELS = ["sessions\n(D1)", "prefixes\n(D2)", "reach.\n(D3)", "waypoint\n(D4)",
              "redund.\n(D5)", "forward.\n(D7)", "scale\n(D8)", "bgp-rib\n(D9)",
              "intent\n(D10)"]
FLOORS = ["empty", "naive_session_loss", "naive_count", "syntactic_diff",
          "modal_by_class"]
FLOOR_LABELS = ["empty", "naive\nsession-loss", "naive\ncount", "syntactic\ndiff",
                "modal-by-class\n(memorizer)"]

# Grounded instances whose D7 ground truth is non-empty (the loud anomalies).
D7_TRUTH_INSTANCES = ("leak_ms", "clos_summary")


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def _summary_for(key: str) -> dict:
    if key == SONNET_KEY and SONNET_OVERRIDE is not None:
        return _load(SONNET_OVERRIDE / "summary.json")
    return _load(REGRADE / "summary.json")


def _grounded_new(label: str, key: str) -> dict:
    s = _summary_for(key)["models"][key]
    if "grounded" not in s:
        raise SystemExit(f"{label}: no grounded split in regrade summary")
    return s["grounded"]["new"]


def _recall(dim: str, instances: set[str]) -> dict[str, float]:
    """Per-model F1 on `dim` over the given grounded instances (per-instance mean
    over N=5, then mean over instances) — F1 where the dimension is the ground
    truth; on these single-truth instances F1 tracks recall. Sonnet comes from
    REGRADE, which already bakes in the 12k run."""
    acc: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for line in (REGRADE / "results.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["kind"] != "model" or r["split"] != "grounded":
            continue
        if r["instance"] not in instances:
            continue
        key = f"{r['model']} @ {r['condition']}"
        acc[key][r["instance"]].append(r["new_per_type"][dim])
    return {k: float(np.mean([np.mean(v) for v in insts.values()]))
            for k, insts in acc.items()}


def fig_heatmap() -> Path:
    grid = np.full((len(MODELS), len(DIMS)), np.nan)
    n1 = np.zeros_like(grid, dtype=bool)  # n=1 point-estimate cells (audit K3)
    for i, (label, key) in enumerate(MODELS):
        bd = _grounded_new(label, key)["by_dimension"]
        for j, d in enumerate(DIMS):
            if d in bd:
                grid[i, j] = bd[d]["mean_f1"]
                n1[i, j] = bd[d].get("n_instances", 0) == 1
    fig, ax = plt.subplots(figsize=(8.2, 3.4))
    masked = np.ma.masked_invalid(grid)
    cmap = plt.cm.RdYlGn.copy()
    cmap.set_bad("#e8e8e8")
    im = ax.imshow(masked, vmin=0, vmax=1, cmap=cmap, aspect="auto")
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            if np.isnan(grid[i, j]):
                txt = "–"
            else:
                txt = f"{grid[i, j]:.2f}" + ("†" if n1[i, j] else "")
            ax.text(j, i, txt, ha="center", va="center", fontsize=7.5,
                    color="black")
    ax.set_xticks(range(len(DIMS)), DIM_LABELS, fontsize=7.5)
    ax.set_yticks(range(len(MODELS)), [m[0] for m in MODELS], fontsize=8.5)
    ax.set_title("Per-dimension F1, grounded split, semantic grader (N=5 per "
                 "instance; † = single-instance point estimate; – = dimension "
                 "never active)", fontsize=8.5)
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    fig.tight_layout()
    out = OUT / "fig_heatmap.pdf"
    fig.savefig(out)
    plt.close(fig)
    return out


def fig_gradient() -> Path:
    """F1 where each consequence dimension is the ground truth (grounded,
    semantic grader; on single-truth instances F1 tracks recall). The loud half---blackhole, masked withdrawal, lockout---is
    caught by the stronger models; the aggregate-preservation intent is missed.
    The sharpest quiet case, the templated silent reroute, is missed at 57/60
    (Haiku/mini only) and is reported in the text, not plotted here."""
    series = {
        "blackhole (D7)":            _recall("forwarding", {"leak_ms", "clos_summary"}),
        "masked withdrawal (D9)":    _recall("bgp_withdrawn", {"ipc3_static"}),
        "mgmt lockout (D10)":        _recall("intent", {"mgmt_lockout"}),
        "aggregate-intent (D10) — MISSED": _recall("intent", {"ipc_aggregate"}),
    }
    x = np.arange(len(MODELS))
    w = 0.2
    colors = ["#2b8cbe", "#238b45", "#41ab5d", "#d7301f"]
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    for k, (name, rec) in enumerate(series.items()):
        vals = [rec.get(key, np.nan) for _, key in MODELS]
        ax.bar(x + (k - 1.5) * w, vals, w, label=name, color=colors[k])
    ax.set_xticks(x, [m[0] for m in MODELS], fontsize=8)
    ax.set_ylabel("F1 where dimension\nis ground truth", fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=6.5, loc="upper right", ncols=2)
    ax.set_title("Loud consequence damage caught; aggregate-intent missed "
                 "(silent reroute also missed, F3)", fontsize=7.5)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out = OUT / "fig_gradient.pdf"
    fig.savefig(out)
    plt.close(fig)
    return out


def fig_floors() -> Path:
    """Templated-split damage macro-F1 (semantic grader): models vs floors."""
    s = _load(REGRADE / "summary.json")
    rows, vals, errs, colors = [], [], [], []
    for label, key in MODELS:
        st = s["models"].get(key, {}).get("templated")
        if not st:
            continue
        dmg = st["new"]["macro_f1_damage"]
        rows.append(label)
        vals.append(dmg["mean"])
        errs.append(dmg["std"])
        colors.append("#2b8cbe")
    for fl, fl_label in zip(FLOORS, FLOOR_LABELS):
        st = s["floors"][fl].get("templated", {})
        dmg = st.get("new", {}).get("macro_f1_damage")
        if dmg is None:
            continue
        rows.append(fl_label)
        vals.append(dmg["mean"])
        errs.append(dmg["std"])
        colors.append("#999999")
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    ax.bar(x, vals, 0.6, yerr=errs, capsize=3, color=colors)
    ax.set_xticks(x, rows, fontsize=7.5)
    ax.set_ylabel("damage macro-F1\n(templated, non-empty GT)", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Models vs model-free floors, templated split, semantic grader "
                 "(48 instances, N=5)", fontsize=8.5)
    fig.tight_layout()
    out = OUT / "fig_floors.pdf"
    fig.savefig(out)
    plt.close(fig)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (fig_heatmap, fig_gradient, fig_floors):
        print(fn())


if __name__ == "__main__":
    main()
