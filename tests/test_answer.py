import os
import pytest
from answer import _ThinkStripper, _format_context, _model_chain, MODEL, FALLBACK_MODELS


# --- _ThinkStripper ---

def _run(tokens: list[str]) -> str:
    s = _ThinkStripper()
    out = "".join(s.feed(t) for t in tokens)
    return out + s.flush()


def test_no_think_block():
    assert _run(["hello world"]) == "hello world"


def test_think_block_stripped():
    assert _run(["<think>reasoning</think>answer"]) == "answer"


def test_think_block_with_prefix():
    assert _run(["before<think>reasoning</think>after"]) == "beforeafter"


def test_multiple_think_blocks():
    assert _run(["<think>r1</think>part1<think>r2</think>part2"]) == "part1part2"


def test_partial_think_tag_across_tokens():
    assert _run(["<thi", "nk>reasoning</think>answer"]) == "answer"


def test_partial_close_tag_across_tokens():
    assert _run(["<think>reasoning</thi", "nk>answer"]) == "answer"


def test_empty_input():
    assert _run([""]) == ""


def test_no_think_block_streaming():
    # content arrives token by token; all should be emitted
    tokens = list("hello world")
    assert _run(tokens) == "hello world"


# --- _model_chain ---

def test_model_chain_default(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    chain = _model_chain()
    assert chain[0] == MODEL


def test_model_chain_env_override(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "custom/model")
    chain = _model_chain()
    assert chain[0] == "custom/model"


def test_model_chain_empty_string_falls_back(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "")
    chain = _model_chain()
    assert chain[0] == MODEL


def test_model_chain_capped_at_3(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    assert len(_model_chain()) <= 3


def test_model_chain_no_duplicates(monkeypatch):
    # env var already in FALLBACK_MODELS — should not appear twice
    monkeypatch.setenv("OPENROUTER_MODEL", FALLBACK_MODELS[1])
    chain = _model_chain()
    assert len(chain) == len(set(chain))


# --- _format_context ---

CHUNK = {
    "file_path": "nanochat/gpt.py",
    "name": "forward",
    "chunk_type": "function",
    "start_line": 10,
    "end_line": 20,
    "score": 0.95,
    "content": "def forward(x):\n    return x",
}


def test_format_context_contains_header():
    result = _format_context([CHUNK])
    assert "[1] nanochat/gpt.py :: forward" in result
    assert "function" in result
    assert "lines 10-20" in result


def test_format_context_contains_content():
    result = _format_context([CHUNK])
    assert "def forward(x):" in result


def test_format_context_multiple_chunks_separator():
    chunk2 = {**CHUNK, "name": "backward", "start_line": 30, "end_line": 40}
    result = _format_context([CHUNK, chunk2])
    assert "[1]" in result
    assert "[2]" in result
    assert "---" in result


def test_format_context_empty():
    assert _format_context([]) == ""
