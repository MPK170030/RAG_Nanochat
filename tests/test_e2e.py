"""
End-to-end smoke test against the live deployed API.

Skipped in the normal test run — opt in with:
    pytest -m e2e
"""
import pytest
import requests

API_URL = "https://coderagapi.manavpkothari.dev"


@pytest.mark.e2e
def test_health():
    response = requests.get(f"{API_URL}/health", timeout=10)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.e2e
def test_ask_happy_path():
    response = requests.post(
        f"{API_URL}/ask",
        json={"query": "what does the forward method do in gpt.py", "k": 3},
        timeout=60,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["answer"], "answer should be non-empty"
    assert len(data["sources"]) > 0, "should return at least one source"
    assert data["model_used"], "model_used should be present"
