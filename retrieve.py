"""
Semantic retrieval over the embedded nanochat chunks.

    retrieve(query, k=5) -> list of chunk dicts, ordered by relevance

Each returned dict has: content, file_path, chunk_type, name,
start_line, end_line, score (cosine similarity, higher = better).

Model and Chroma collection are loaded once on first call (module-level singletons).

CLI usage:
    python retrieve.py "how does nanochat do rotary embeddings"
    python retrieve.py "what does speedrun.sh do" --k 8
"""
import argparse

import chromadb
from sentence_transformers import SentenceTransformer

COLLECTION_NAME = "nanochat"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
# BGE asymmetric retrieval: queries need this prefix, indexed documents do not.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model: SentenceTransformer | None = None
_collection = None


def _load(db_path: str = "chroma_db") -> None:
    global _model, _collection
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    if _collection is None:
        client = chromadb.PersistentClient(path=db_path)
        _collection = client.get_collection(COLLECTION_NAME)


def retrieve(query: str, k: int = 5, db_path: str = "chroma_db") -> list[dict]:
    """Return the k most relevant chunks for query."""
    _load(db_path)
    q_vec = _model.encode(
        BGE_QUERY_PREFIX + query,
        normalize_embeddings=True,
    ).tolist()
    results = _collection.query(query_embeddings=[q_vec], n_results=k)

    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append(
            {
                "content": results["documents"][0][i],
                **results["metadatas"][0][i],
                "score": 1.0 - results["distances"][0][i],  # cosine distance → similarity
            }
        )
    return chunks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query the nanochat RAG index.")
    parser.add_argument("query", help="Natural-language question")
    parser.add_argument("--k", type=int, default=5, help="Number of results")
    parser.add_argument("--db", default="chroma_db", help="Chroma persistence directory")
    args = parser.parse_args()

    results = retrieve(args.query, k=args.k, db_path=args.db)
    for i, chunk in enumerate(results, 1):
        bar = "=" * 60
        print(f"\n{bar}")
        print(
            f"#{i}  score={chunk['score']:.3f}  [{chunk['chunk_type']}]  "
            f"{chunk['file_path']} :: {chunk['name']}  "
            f"(lines {chunk['start_line']}-{chunk['end_line']})"
        )
        preview = chunk["content"]
        if len(preview) > 500:
            preview = preview[:500] + "..."
        print(preview)
