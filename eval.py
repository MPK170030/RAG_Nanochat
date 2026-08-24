"""
Retrieval eval against eval_questions.jsonl.

For each question, checks whether the expected chunk (by file_path + name)
appears in the top-k retrieved results.

Metrics reported:
  Hit@1  - expected chunk was the top result
  Hit@5  - expected chunk appeared anywhere in top 5
  MRR    - mean reciprocal rank (1/rank if found, 0 if not)

Usage:
    python eval.py
    python eval.py --k 8 --questions eval_questions.jsonl
"""
import argparse
import json
from pathlib import Path

from retrieve import retrieve


def run_eval(questions: list[dict], k: int) -> None:
    hits1 = 0
    hits_k = 0
    reciprocal_ranks = []
    misses = []

    for q in questions:
        query = q["query"]
        exp_file = q["expected_file"]
        exp_name = q["expected_name"]

        chunks = retrieve(query, k=k)

        rank = None
        for i, chunk in enumerate(chunks, 1):
            file_match = chunk["file_path"] == exp_file
            # name match: exact or the chunk name starts with expected name
            # (handles "ClassName.method_name" vs "method_name" style)
            name_match = chunk["name"] == exp_name or chunk["name"].endswith(f".{exp_name}")
            if file_match and name_match:
                rank = i
                break

        if rank == 1:
            hits1 += 1
        if rank is not None:
            hits_k += 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)
            misses.append({"query": query, "expected_file": exp_file, "expected_name": exp_name})

    n = len(questions)
    mrr = sum(reciprocal_ranks) / n

    print(f"\n{'='*50}")
    print(f"RETRIEVAL EVAL  (k={k}, n={n} questions)")
    print(f"{'='*50}")
    print(f"  Hit@1  : {hits1}/{n}  ({100*hits1/n:.1f}%)")
    print(f"  Hit@{k:<2} : {hits_k}/{n}  ({100*hits_k/n:.1f}%)")
    print(f"  MRR    : {mrr:.3f}")

    if misses:
        print(f"\nMISSES (not in top {k}):")
        for m in misses:
            print(f"  - \"{m['query']}\"")
            print(f"    expected: {m['expected_file']} :: {m['expected_name']}")
    else:
        print(f"\nNo misses — all expected chunks found in top {k}.")


def main():
    parser = argparse.ArgumentParser(description="Eval retrieval against labelled questions.")
    parser.add_argument("--questions", default="eval_questions.jsonl")
    parser.add_argument("--k", type=int, default=5, help="Number of results to retrieve")
    args = parser.parse_args()

    lines = [l for l in Path(args.questions).read_text(encoding="utf-8").splitlines() if l.strip()]
    questions = [json.loads(l) for l in lines]
    print(f"Loaded {len(questions)} questions from {args.questions}")

    run_eval(questions, k=args.k)


if __name__ == "__main__":
    main()
