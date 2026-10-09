import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    from api import app
    return TestClient(app)


# --- /health ---

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- /ask ---

def test_ask_missing_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from api import app
    with TestClient(app) as c:
        response = c.post("/ask", json={"query": "test", "k": 3})
    assert response.status_code == 503


def test_ask_success(client):
    with patch("api.rag_answer", return_value=("The answer", [], "qwen/qwen3-30b-a3b")):
        response = client.post("/ask", json={"query": "how does nanochat work", "k": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "The answer"
    assert data["model_used"] == "qwen/qwen3-30b-a3b"
    assert data["sources"] == []


def test_ask_with_sources(client):
    sources = [{
        "file_path": "nanochat/gpt.py",
        "chunk_type": "function",
        "name": "forward",
        "start_line": 10,
        "end_line": 20,
        "score": 0.95,
    }]
    with patch("api.rag_answer", return_value=("answer", sources, "qwen/qwen3-30b-a3b")):
        response = client.post("/ask", json={"query": "test", "k": 3})
    assert response.status_code == 200
    assert len(response.json()["sources"]) == 1


def test_ask_empty_query_rejected(client):
    response = client.post("/ask", json={"query": "", "k": 3})
    assert response.status_code == 422


def test_ask_k_too_large_rejected(client):
    response = client.post("/ask", json={"query": "test", "k": 25})
    assert response.status_code == 422


def test_ask_k_zero_rejected(client):
    response = client.post("/ask", json={"query": "test", "k": 0})
    assert response.status_code == 422


# --- /ask/stream ---

def test_ask_stream_missing_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from api import app
    with TestClient(app) as c:
        response = c.post("/ask/stream", json={"query": "test", "k": 3})
    assert response.status_code == 503


def test_ask_stream_events(client):
    def mock_stream(query, k):
        yield "token", "Hello"
        yield "token", " world"
        yield "sources", {"sources": [], "model": "qwen/qwen3-30b-a3b"}

    with patch("api.answer_stream", side_effect=mock_stream):
        with client.stream("POST", "/ask/stream", json={"query": "test", "k": 3}) as r:
            assert r.status_code == 200
            content = r.read().decode()

    assert 'data: {"token": "Hello"}' in content
    assert 'data: {"token": " world"}' in content
    assert '"done": true' in content
    assert '"model": "qwen/qwen3-30b-a3b"' in content
