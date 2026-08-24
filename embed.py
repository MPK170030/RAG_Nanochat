"""
One-shot ingestion: loads chunks.jsonl, embeds every chunk with
BAAI/bge-small-en-v1.5, and stores them in a persistent Chroma collection.

Re-running this script wipes and rebuilds the collection from scratch.

Usage:
    python embed.py [chunks.jsonl] [--db chroma_db] [--batch-size 64]
"""
import argparse
import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

COLLECTION_NAME = "nanochat"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
CHROMA_BATCH_LIMIT = 5000  # Chroma's max items per .add() call


def make_embed_text(chunk: dict) -> str:
    """Prepend a metadata header so the embedding captures chunk type and location."""
    return f"[{chunk['chunk_type']}] {chunk['file_path']} :: {chunk['name']}\n{chunk['content']}"


def make_id(chunk: dict) -> str:
    return f"{chunk['file_path']}::{chunk['name']}::{chunk['start_line']}"


def main():
    parser = argparse.ArgumentParser(description="Embed chunks.jsonl into Chroma.")
    parser.add_argument("chunks", nargs="?", default="chunks.jsonl")
    parser.add_argument("--db", default="chroma_db", help="Chroma persistence directory")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    args = parser.parse_args()

    lines = [l for l in Path(args.chunks).read_text(encoding="utf-8").splitlines() if l.strip()]
    chunks = [json.loads(l) for l in lines]
    print(f"Loaded {len(chunks)} chunks from {args.chunks}")

    print(f"Loading {EMBED_MODEL}...")
    model = SentenceTransformer(EMBED_MODEL)

    texts = [make_embed_text(c) for c in chunks]
    print(f"Embedding {len(texts)} chunks (batch_size={args.batch_size})...")
    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    client = chromadb.PersistentClient(path=args.db)
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing collection '{COLLECTION_NAME}'")
    except Exception:
        pass
    collection = client.create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [make_id(c) for c in chunks]
    metadatas = [
        {
            "file_path": c["file_path"],
            "chunk_type": c["chunk_type"],
            "name": c["name"],
            "start_line": c["start_line"],
            "end_line": c["end_line"],
        }
        for c in chunks
    ]
    documents = [c["content"] for c in chunks]

    for i in range(0, len(chunks), CHROMA_BATCH_LIMIT):
        sl = slice(i, i + CHROMA_BATCH_LIMIT)
        collection.add(
            ids=ids[sl],
            embeddings=embeddings[sl].tolist(),
            metadatas=metadatas[sl],
            documents=documents[sl],
        )
        print(f"  Stored {min(i + CHROMA_BATCH_LIMIT, len(chunks))}/{len(chunks)}")

    print(f"\nDone. '{COLLECTION_NAME}' in {args.db}/ — {collection.count()} items indexed.")


if __name__ == "__main__":
    main()
