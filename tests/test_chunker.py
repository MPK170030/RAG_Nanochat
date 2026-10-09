import tempfile
from pathlib import Path
from chunker import (
    chunk_markdown_file,
    chunk_shell_file,
    chunk_python_file,
    build_imported_by_map,
    EXCLUDE_MD_SECTIONS,
)


def make_file(root: Path, name: str, content: str) -> Path:
    p = root / name
    p.write_text(content, encoding="utf-8")
    return p


# --- Markdown chunker ---

def test_markdown_sections_split():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "doc.md", "# Alpha\nContent A.\n\n# Beta\nContent B.")
        chunks = chunk_markdown_file(f, root)
    assert len(chunks) == 2
    assert chunks[0]["name"] == "Alpha"
    assert chunks[1]["name"] == "Beta"


def test_markdown_excluded_sections_dropped():
    for section in EXCLUDE_MD_SECTIONS:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = make_file(root, "doc.md", f"# {section}\nBoilerplate.\n\n# Usage\nReal content.")
            chunks = chunk_markdown_file(f, root)
        names = [c["name"] for c in chunks]
        assert section not in names
        assert "Usage" in names


def test_markdown_chunk_type():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "doc.md", "# Intro\nHello.")
        chunks = chunk_markdown_file(f, root)
    assert all(c["chunk_type"] == "markdown_section" for c in chunks)


def test_markdown_empty_sections_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "doc.md", "# Empty\n\n# HasContent\nSome text.")
        chunks = chunk_markdown_file(f, root)
    names = [c["name"] for c in chunks]
    assert "HasContent" in names


# --- Shell chunker ---

def test_shell_single_chunk():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "run.sh", "#!/bin/bash\necho hello")
        chunks = chunk_shell_file(f, root)
    assert len(chunks) == 1
    assert chunks[0]["chunk_type"] == "shell_script"
    assert chunks[0]["name"] == "run"


def test_shell_empty_file_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "empty.sh", "   \n  ")
        chunks = chunk_shell_file(f, root)
    assert chunks == []


# --- Python chunker ---

def test_python_function_chunk():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "mod.py", "def foo():\n    return 1\n")
        chunks, names, _ = chunk_python_file(f, root)
    assert any(c["name"] == "foo" and c["chunk_type"] == "function" for c in chunks)
    assert "foo" in names


def test_python_class_chunk():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "mod.py", "class Bar:\n    pass\n")
        chunks, names, _ = chunk_python_file(f, root)
    assert any(c["name"] == "Bar" and c["chunk_type"] == "class" for c in chunks)


def test_python_syntax_error_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "bad.py", "def (broken syntax")
        chunks, names, imports = chunk_python_file(f, root)
    assert chunks == [] and names == [] and imports == []


def test_python_imports_collected():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "mod.py", "import os\nfrom pathlib import Path\n")
        _, _, imports = chunk_python_file(f, root)
    assert "os" in imports
    assert "pathlib" in imports


# --- build_imported_by_map ---

def test_imported_by_basic():
    file_imports = {
        "api.py": ["answer"],
        "answer.py": ["retrieve"],
        "retrieve.py": [],
    }
    dotted = {"answer": "answer.py", "retrieve": "retrieve.py", "api": "api.py"}
    result = build_imported_by_map(file_imports, dotted)
    assert "api.py" in result["answer.py"]
    assert "answer.py" in result["retrieve.py"]
    assert result["api.py"] == []


def test_imported_by_no_self_import():
    file_imports = {"a.py": ["a"]}
    dotted = {"a": "a.py"}
    result = build_imported_by_map(file_imports, dotted)
    assert "a.py" not in result["a.py"]


def test_imported_by_unknown_module_ignored():
    file_imports = {"a.py": ["nonexistent_module"]}
    dotted = {"a": "a.py"}
    result = build_imported_by_map(file_imports, dotted)
    assert result["a.py"] == []
