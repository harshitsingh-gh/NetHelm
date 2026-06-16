#!/usr/bin/env python3
"""
Query the knowledge base.

Usage:
    python -m knowledge.tools.query "what is a waypoint violation in BGP?"
    python -m knowledge.tools.query "Batfish traceroute disposition" --top 5
    python -m knowledge.tools.query "RFC 4271 UPDATE message format" --source rfcs

Options:
    --top N      Return top-N results (default 5)
    --source S   Filter to chunks whose source path contains S (e.g. 'rfcs', 'batfish')
    --quiet      Machine-readable JSON output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT        = Path(__file__).resolve().parents[2]
INDEX_DIR   = ROOT / "knowledge" / "index"
MODEL_NAME  = "all-MiniLM-L6-v2"


def _load_index():
    try:
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError:
        sys.exit("Missing dependencies. Run: pip install -e '.[knowledge]'")

    index_path  = INDEX_DIR / "embeddings.faiss"
    chunks_path = INDEX_DIR / "chunks.jsonl"
    if not index_path.exists():
        sys.exit(
            f"Index not found at {index_path}.\n"
            "Run: python -m knowledge.tools.build_index"
        )

    index  = faiss.read_index(str(index_path))
    chunks = [json.loads(l) for l in chunks_path.read_text().splitlines() if l.strip()]
    model  = SentenceTransformer(MODEL_NAME)
    return index, chunks, model, np


def query(q: str, top: int = 5, source_filter: str | None = None,
          quiet: bool = False, silent: bool = False) -> list[dict]:
    """Return top-N KB chunks matching q.

    Args:
        silent: if True, suppress all stdout (for programmatic callers).
        quiet:  if True (and silent=False), emit compact JSON instead of human output.
    """
    index, chunks, model, np = _load_index()

    vec = model.encode([q], normalize_embeddings=True)
    vec = np.array(vec, dtype="float32")
    scores, idxs = index.search(vec, min(top * 4, len(chunks)))  # overfetch for filter

    results = []
    for score, idx in zip(scores[0], idxs[0]):
        if idx < 0:
            continue
        c = chunks[idx]
        if source_filter and source_filter not in c["source"]:
            continue
        results.append({"score": float(score), "source": c["source"], "text": c["text"]})
        if len(results) >= top:
            break

    if not silent:
        if quiet:
            print(json.dumps(results, indent=2))
        else:
            for i, r in enumerate(results, 1):
                bar = "#" * int(r["score"] * 30)
                print(f"\n─── [{i}] {r['source']}  score={r['score']:.3f}  {bar}")
                print(r["text"][:600] + ("…" if len(r["text"]) > 600 else ""))

    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Query the NetHELM knowledge base")
    ap.add_argument("query", help="Natural-language query")
    ap.add_argument("--top",    type=int, default=5)
    ap.add_argument("--source", default=None, help="Filter by source path substring")
    ap.add_argument("--quiet",  action="store_true", help="JSON output only")
    args = ap.parse_args()
    query(args.query, top=args.top, source_filter=args.source, quiet=args.quiet)


if __name__ == "__main__":
    main()
