#!/usr/bin/env python3
"""
Ingest the knowledge/corpus/ tree into a FAISS index.

Usage:
    python -m knowledge.tools.build_index [--corpus-dir PATH] [--index-dir PATH]

Each .txt / .md file under corpus/ is split into chunks (~400 tokens each,
with 50-token overlap). Chunks are embedded with all-MiniLM-L6-v2 and stored
in a FAISS flat-IP index alongside a chunks.jsonl manifest.

Run this once after adding new corpus files; re-running rebuilds from scratch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = ROOT / "knowledge" / "corpus"
DEFAULT_INDEX  = ROOT / "knowledge" / "index"

CHUNK_WORDS  = 300   # target words per chunk
OVERLAP_WORDS = 40   # word overlap between consecutive chunks
MODEL_NAME   = "all-MiniLM-L6-v2"


def _split_chunks(text: str, src: str) -> list[dict]:
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        end = min(start + CHUNK_WORDS, len(words))
        chunk_text = " ".join(words[start:end])
        chunks.append({"text": chunk_text, "source": src})
        if end == len(words):
            break
        start += CHUNK_WORDS - OVERLAP_WORDS
    return chunks


def _gather_corpus(corpus_dir: Path) -> list[dict]:
    records = []
    for path in sorted(corpus_dir.rglob("*")):
        if path.suffix not in {".txt", ".md"}:
            continue
        rel = str(path.relative_to(corpus_dir))
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        records.extend(_split_chunks(text, rel))
    return records


def build(corpus_dir: Path, index_dir: Path, quiet: bool = False) -> None:
    try:
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError:
        sys.exit(
            "Missing dependencies. Run:\n"
            "  pip install -e '.[knowledge]'\n"
        )

    index_dir.mkdir(parents=True, exist_ok=True)

    if not quiet:
        print(f"[build_index] scanning {corpus_dir} ...")
    chunks = _gather_corpus(corpus_dir)
    if not chunks:
        sys.exit(f"No .txt/.md files found under {corpus_dir}. Add corpus files first.")

    if not quiet:
        print(f"[build_index] {len(chunks)} chunks from {len({c['source'] for c in chunks})} files")
        print(f"[build_index] loading model {MODEL_NAME!r} ...")

    model = SentenceTransformer(MODEL_NAME)
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=not quiet,
                               normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype="float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    index_path  = index_dir / "embeddings.faiss"
    chunks_path = index_dir / "chunks.jsonl"
    faiss.write_index(index, str(index_path))
    with chunks_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    if not quiet:
        print(f"[build_index] wrote {index_path}")
        print(f"[build_index] wrote {chunks_path}")
        print(f"[build_index] done — {len(chunks)} chunks, dim={dim}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build FAISS index from corpus/")
    ap.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--index-dir",  type=Path, default=DEFAULT_INDEX)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    build(args.corpus_dir, args.index_dir, quiet=args.quiet)


if __name__ == "__main__":
    main()
