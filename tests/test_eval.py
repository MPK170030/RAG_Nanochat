from unittest.mock import patch
from eval import run_eval


def _chunk(file_path: str, name: str) -> dict:
    return {"file_path": file_path, "name": name, "score": 0.9}


QUESTION = {
    "query": "how does forward work",
    "expected_file": "nanochat/gpt.py",
    "expected_name": "forward",
}


# --- Hit@1 / Hit@k ---

def test_hit_at_1(capsys):
    chunks = [_chunk("nanochat/gpt.py", "forward"), _chunk("nanochat/gpt.py", "backward")]
    with patch("eval.retrieve", return_value=chunks):
        run_eval([QUESTION], k=5)
    assert "Hit@1  : 1/1" in capsys.readouterr().out


def test_hit_at_k_not_rank_1(capsys):
    chunks = [_chunk("nanochat/gpt.py", "other"), _chunk("nanochat/gpt.py", "forward")]
    with patch("eval.retrieve", return_value=chunks):
        run_eval([QUESTION], k=5)
    out = capsys.readouterr().out
    assert "Hit@1  : 0/1" in out
    assert "Hit@5  : 1/1" in out


def test_miss(capsys):
    with patch("eval.retrieve", return_value=[_chunk("nanochat/gpt.py", "unrelated")]):
        run_eval([QUESTION], k=5)
    out = capsys.readouterr().out
    assert "Hit@1  : 0/1" in out
    assert "Hit@5  : 0/1" in out
    assert "MISSES" in out


# --- MRR ---

def test_mrr_rank_1(capsys):
    with patch("eval.retrieve", return_value=[_chunk("nanochat/gpt.py", "forward")]):
        run_eval([QUESTION], k=5)
    assert "MRR    : 1.000" in capsys.readouterr().out


def test_mrr_rank_2(capsys):
    chunks = [_chunk("nanochat/gpt.py", "other"), _chunk("nanochat/gpt.py", "forward")]
    with patch("eval.retrieve", return_value=chunks):
        run_eval([QUESTION], k=5)
    assert "MRR    : 0.500" in capsys.readouterr().out


def test_mrr_all_miss(capsys):
    with patch("eval.retrieve", return_value=[_chunk("nanochat/gpt.py", "unrelated")]):
        run_eval([QUESTION], k=5)
    assert "MRR    : 0.000" in capsys.readouterr().out


# --- Name matching ---

def test_name_match_exact(capsys):
    with patch("eval.retrieve", return_value=[_chunk("nanochat/gpt.py", "forward")]):
        run_eval([QUESTION], k=5)
    assert "Hit@1  : 1/1" in capsys.readouterr().out


def test_name_match_dotted_suffix(capsys):
    # "CausalSelfAttention.forward" should match expected_name "forward"
    with patch("eval.retrieve", return_value=[_chunk("nanochat/gpt.py", "CausalSelfAttention.forward")]):
        run_eval([QUESTION], k=5)
    assert "Hit@1  : 1/1" in capsys.readouterr().out


def test_file_path_must_match(capsys):
    # correct name but wrong file — should miss
    with patch("eval.retrieve", return_value=[_chunk("nanochat/train.py", "forward")]):
        run_eval([QUESTION], k=5)
    out = capsys.readouterr().out
    assert "Hit@1  : 0/1" in out
    assert "MISSES" in out


# --- Multi-question aggregation ---

def test_multiple_questions_aggregation(capsys):
    q1 = {"query": "q1", "expected_file": "a.py", "expected_name": "foo"}
    q2 = {"query": "q2", "expected_file": "b.py", "expected_name": "bar"}

    def mock_retrieve(query, k):
        return [_chunk("a.py", "foo")] if query == "q1" else [_chunk("b.py", "unrelated")]

    with patch("eval.retrieve", side_effect=mock_retrieve):
        run_eval([q1, q2], k=5)
    out = capsys.readouterr().out
    assert "n=2 questions" in out
    assert "Hit@1  : 1/2" in out
    assert "Hit@5  : 1/2" in out
    assert "MRR    : 0.500" in out


# --- Output messages ---

def test_no_misses_message(capsys):
    with patch("eval.retrieve", return_value=[_chunk("nanochat/gpt.py", "forward")]):
        run_eval([QUESTION], k=5)
    assert "No misses" in capsys.readouterr().out
