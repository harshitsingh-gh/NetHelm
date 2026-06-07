"""Generate figures from results.csv. Requires matplotlib (install with [report])."""

from __future__ import annotations

import csv
from pathlib import Path


def f1_by_intent(run_dir: str | Path, out_pdf: str | Path) -> Path:
    """Bar chart: x=intent, y=mean macro_f1. Saves PDF.

    Groups by model if results.csv has a 'model' column.
    Title includes '(preliminary)' as required.
    """
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend
    import matplotlib.pyplot as plt
    import numpy as np

    run_dir = Path(run_dir)
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader((run_dir / "results.csv").open(encoding="utf-8")))
    has_model = "model" in (rows[0] if rows else {})

    # Group by (model, intent)
    groups: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        model = r.get("model", "model") if has_model else "model"
        intent = r["intent"]
        groups.setdefault((model, intent), []).append(float(r["macro_f1"]))

    models = sorted({k[0] for k in groups})
    intents = sorted({k[1] for k in groups})
    means = {
        (m, i): sum(v) / len(v) if v else 0.0
        for (m, i), v in groups.items()
    }

    fig, ax = plt.subplots(figsize=(max(6, 2 * len(intents)), 4))
    x = np.arange(len(intents))
    width = 0.8 / max(len(models), 1)
    for idx, model in enumerate(models):
        ys = [means.get((model, intent), 0.0) for intent in intents]
        offset = (idx - (len(models) - 1) / 2) * width
        bars = ax.bar(x + offset, ys, width, label=model)
        for bar in bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{bar.get_height():.2f}",
                ha="center", va="bottom", fontsize=8,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(intents, rotation=20, ha="right")
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Mean macro-F1")
    ax.set_xlabel("Intent")
    ax.set_title("NetBrace Safety Axis: F1 by Intent (preliminary)")
    if len(models) > 1:
        ax.legend()

    fig.tight_layout()
    fig.savefig(out_pdf)
    plt.close(fig)
    return out_pdf
