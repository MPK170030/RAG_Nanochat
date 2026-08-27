"""
Generation layer: retrieves relevant chunks and calls Groq to produce an answer.

    answer(query) -> (response_text, sources)
    answer_stream(query) -> generator of ("token", str) | ("sources", list)

sources is a list of dicts with: file_path, chunk_type, name, start_line, end_line, score.

CLI usage:
    python answer.py "how does nanochat implement rotary embeddings"
    python answer.py "what does speedrun.sh do" --k 8
"""
import argparse
import os
import re
import sys
from collections.abc import Generator

from dotenv import load_dotenv
from groq import Groq

from retrieve import retrieve

load_dotenv()

MODEL = "qwen/qwen3.6-27b"
SYSTEM_PROMPT = """\
You are a code assistant that answers questions about the nanochat codebase.
You are given a set of retrieved code chunks as context. Use them to answer \
the question accurately and concisely. Always mention which file and \
function/section your answer comes from. If the context does not contain \
enough information to answer, say so clearly rather than guessing.\
"""


class _ThinkStripper:
    """State machine that strips <think>...</think> blocks from a token stream."""

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    def feed(self, token: str) -> str:
        self._buf += token
        out: list[str] = []
        while True:
            if self._in_think:
                end = self._buf.find("</think>")
                if end >= 0:
                    self._in_think = False
                    self._buf = self._buf[end + 8:]
                else:
                    # Keep last 7 chars as a partial-tag guard (len("</think>") - 1)
                    self._buf = self._buf[-7:] if len(self._buf) > 7 else self._buf
                    break
            else:
                start = self._buf.find("<think>")
                if start >= 0:
                    out.append(self._buf[:start])
                    self._in_think = True
                    self._buf = self._buf[start + 7:]
                else:
                    # Emit everything except the last 6 chars (partial <think> guard)
                    safe = max(0, len(self._buf) - 6)
                    out.append(self._buf[:safe])
                    self._buf = self._buf[safe:]
                    break
        return "".join(out)

    def flush(self) -> str:
        if self._in_think:
            return ""
        result, self._buf = self._buf, ""
        return result


def _format_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        header = f"[{i}] {c['file_path']} :: {c['name']} ({c['chunk_type']}, lines {c['start_line']}-{c['end_line']}, score={c['score']:.3f})"
        parts.append(f"{header}\n{c['content']}")
    return "\n\n---\n\n".join(parts)


def answer_stream(query: str, k: int = 5) -> Generator[tuple[str, object], None, None]:
    """Yield (\"token\", str) events while streaming, then a final (\"sources\", list) event."""
    chunks = retrieve(query, k=k)
    context = _format_context(chunks)
    sources = [{key: v for key, v in c.items() if key != "content"} for c in chunks]

    user_message = f"Context:\n\n{context}\n\nQuestion: {query}"

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
        stream=True,
    )

    stripper = _ThinkStripper()
    for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            visible = stripper.feed(token)
            if visible:
                yield "token", visible

    tail = stripper.flush()
    if tail:
        yield "token", tail

    yield "sources", sources


def answer(query: str, k: int = 5) -> tuple[str, list[dict]]:
    chunks = retrieve(query, k=k)
    context = _format_context(chunks)

    user_message = f"Context:\n\n{context}\n\nQuestion: {query}"

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
    )

    answer_text = re.sub(r"<think>.*?</think>", "", response.choices[0].message.content, flags=re.DOTALL).strip()
    sources = [
        {k: v for k, v in c.items() if k != "content"}
        for c in chunks
    ]
    return answer_text, sources


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask a question about nanochat.")
    parser.add_argument("query", help="Natural-language question")
    parser.add_argument("--k", type=int, default=5, help="Chunks to retrieve")
    args = parser.parse_args()

    response_text, sources = answer(args.query, k=args.k)

    print("\n" + "=" * 60)
    print("ANSWER")
    print("=" * 60)
    print(response_text.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))

    print("\n" + "=" * 60)
    print("SOURCES")
    print("=" * 60)
    for i, s in enumerate(sources, 1):
        print(f"  [{i}] {s['file_path']} :: {s['name']} (lines {s['start_line']}-{s['end_line']}, score={s['score']:.3f})")
