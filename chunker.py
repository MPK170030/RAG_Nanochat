"""
Code-aware chunker for the nanochat repo.

Produces chunks.jsonl with one JSON object per line. Each chunk has:
  file_path, chunk_type, name, start_line, end_line, content

chunk_type is one of:
  "function"           - a top-level or nested function
  "class"              - a whole class (docstring + all methods)
  "module_summary"     - one per .py file: docstring + defined names + import graph
  "markdown_section"   - one per "## Header" section in .md files
  "shell_script"       - one per .sh file, whole file as one chunk
  "project_metadata"   - one per pyproject.toml, parsed fields
  "notebook_cell_pair" - one per markdown+code cell pair in .ipynb files

Usage:
    python chunker.py /path/to/nanochat/repo
"""

import ast
import json
import re
import sys
import tomllib 
from pathlib import Path

EXCLUDE_DIRS = {".git", "__pycache__", "myenv", "venv", ".venv", "node_modules", ".claude"}
EXCLUDE_FILES = {"LOG.md", "LEADERBOARD.md"}  # dev/experiment files, not source material
EXCLUDE_MD_SECTIONS = {  # boilerplate README sections with no implementation content
    "Acknowledgements", "Cite", "License", "Contributing", "Guides",
}
METHOD_SIZE_THRESHOLD = 15  # methods longer than this many lines also get their own chunk
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp"}

def discover_files(repo_root: Path):
    files = {"py": [], "md": [], "sh": [], "toml": [], "ipynb": []}
    for path in repo_root.rglob("*"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.name in EXCLUDE_FILES:
            continue
        if path.suffix in IMAGE_EXTENSIONS:
            continue
        if path.suffix == ".py":
            files["py"].append(path)
        elif path.suffix == ".md":
            files["md"].append(path)
        elif path.suffix == ".sh":
            files["sh"].append(path)
        elif path.suffix == ".toml":
            files["toml"].append(path)
        elif path.suffix == ".ipynb":
            files["ipynb"].append(path)
    for key in files:
        files[key] = sorted(files[key])
    return files

def slice_lines(source_lines, start_line, end_line):
    return "\n".join(source_lines[start_line - 1:end_line])


def chunk_python_file(path: Path, repo_root: Path):
    """Returns (chunks, imports) for one .py file."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    source_lines = text.splitlines()
    rel_path = str(path.relative_to(repo_root)).replace("\\", "/")

    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        print(f"  [skip - syntax error] {rel_path}: {e}")
        return [], [], []

    chunks = []
    top_level_names = []
    imports = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_level_names.append(node.name)
            start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
            chunks.append({
                "file_path": rel_path,
                "chunk_type": "function",
                "name": node.name,
                "start_line": start,
                "end_line": node.end_lineno,
                "content": slice_lines(source_lines, start, node.end_lineno),
            })

        elif isinstance(node, ast.ClassDef):
            top_level_names.append(node.name)
            start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
            content = slice_lines(source_lines, start, node.end_lineno)

            # For @dataclass classes, prepend a structured field summary so the
            # embedding captures field names and inline comments directly.
            is_dataclass = any(
                (isinstance(d, ast.Name) and d.id == "dataclass") or
                (isinstance(d, ast.Attribute) and d.attr == "dataclass")
                for d in node.decorator_list
            )
            if is_dataclass:
                field_lines = []
                for item in ast.walk(node):
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        src_line = source_lines[item.lineno - 1]
                        comment = ""
                        if "#" in src_line:
                            comment = "  #" + src_line.split("#", 1)[1].rstrip()
                        field_lines.append(f"  {item.target.id}{comment}")
                header = f"@dataclass {node.name} — fields:\n" + "\n".join(field_lines) + "\n\n"
                content = header + content

            chunks.append({
                "file_path": rel_path,
                "chunk_type": "class",
                "name": node.name,
                "start_line": start,
                "end_line": node.end_lineno,
                "content": content,
            })

            for sub in ast.iter_child_nodes(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    length = sub.end_lineno - sub.lineno
                    if length > METHOD_SIZE_THRESHOLD:
                        sub_start = sub.decorator_list[0].lineno if sub.decorator_list else sub.lineno
                        chunks.append({
                            "file_path": rel_path,
                            "chunk_type": "function",
                            "name": f"{node.name}.{sub.name}",
                            "start_line": sub_start,
                            "end_line": sub.end_lineno,
                            "content": slice_lines(source_lines, sub_start, sub.end_lineno),
                        })

    return chunks, top_level_names, imports

def build_imported_by_map(file_imports: dict, dotted_to_relpath: dict):
    """
    file_imports: {rel_path: [imported dotted module strings, e.g. "nanochat.gpt"]}
    dotted_to_relpath: {dotted module name: rel_path} for every internal file,
                        e.g. {"nanochat.gpt": "nanochat/gpt.py", "gpt": "nanochat/gpt.py"}
                        (registered under both its full dotted path and its bare stem,
                        so both "import nanochat.gpt" and "from nanochat.gpt import X"
                        style references resolve.)
    Returns: {rel_path: [rel_paths that import it]}
    """
    imported_by = {rel_path: [] for rel_path in set(dotted_to_relpath.values())}
    for importer_rel_path, imports in file_imports.items():
        for imp in imports:
            # try exact dotted match first, then fall back to last component
            target = dotted_to_relpath.get(imp) or dotted_to_relpath.get(imp.split(".")[-1])
            if target and target != importer_rel_path:
                if importer_rel_path not in imported_by[target]:
                    imported_by[target].append(importer_rel_path)
    return imported_by

def build_module_summary_chunk(path: Path, repo_root: Path, defined_names, imported_by_this_file):
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
    try:
        tree = ast.parse(text)
        docstring = ast.get_docstring(tree)
    except SyntaxError:
        docstring = None

    lines = [f"File: {rel_path}"]
    if docstring:
        lines.append(f"Docstring: {docstring.strip()}")
    if defined_names:
        lines.append(f"Defines: {', '.join(defined_names)}")
    else:
        lines.append("Defines: (no top-level functions or classes)")
    if imported_by_this_file:
        lines.append(f"Imported by: {', '.join(imported_by_this_file)}")
    else:
        lines.append("Imported by: (no other file in this repo imports it directly)")

    content = "\n".join(lines)
    return {
        "file_path": rel_path,
        "chunk_type": "module_summary",
        "name": path.stem,
        "start_line": 1,
        "end_line": len(text.splitlines()),
        "content": content,
    }


HEADER_RE = re.compile(r"^#{1,6}\s+.*$")

def chunk_markdown_file(path: Path, repo_root: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
    lines = text.splitlines()

    chunks = []
    current_header = "(intro)"
    current_start = 1
    buffer = []

    def flush(end_line):
        if buffer and current_header not in EXCLUDE_MD_SECTIONS:
            chunks.append({
                "file_path": rel_path,
                "chunk_type": "markdown_section",
                "name": current_header,
                "start_line": current_start,
                "end_line": end_line,
                "content": "\n".join(buffer).strip(),
            })

    for i, line in enumerate(lines, start=1):
        if HEADER_RE.match(line):
            flush(i - 1)
            current_header = line.strip("# ").strip()
            current_start = i
            buffer = [line]
        else:
            buffer.append(line)
    flush(len(lines))

    return [c for c in chunks if c["content"]]

def chunk_shell_file(path: Path, repo_root: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
    lines = text.splitlines()
    if not text.strip():
        return []
    return [{
        "file_path": rel_path,
        "chunk_type": "shell_script",
        "name": path.stem,
        "start_line": 1,
        "end_line": len(lines),
        "content": text,
    }]

def chunk_toml_file(path: Path, repo_root: Path):
    rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
    with path.open("rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    name = project.get("name", "(unknown)")
    description = project.get("description", "")
    requires_python = project.get("requires-python", "")
    dependencies = project.get("dependencies", [])

    lines = [f"Project: {name}"]
    if description:
        lines.append(f"Description: {description}")
    if requires_python:
        lines.append(f"Requires Python: {requires_python}")
    if dependencies:
        lines.append("Dependencies: " + ", ".join(dependencies))
    else:
        lines.append("Dependencies: (none listed under [project.dependencies])")

    # optional dependency groups (e.g. [project.optional-dependencies])
    optional = project.get("optional-dependencies", {})
    for group_name, deps in optional.items():
        lines.append(f"Optional dependencies ({group_name}): " + ", ".join(deps))

    # PEP 735 dependency groups (e.g. [dependency-groups], used for dev/test deps)
    dependency_groups = data.get("dependency-groups", {})
    for group_name, deps in dependency_groups.items():
        # entries can be plain strings or {"include-group": "..."} refs; keep it simple
        flat = [d if isinstance(d, str) else str(d) for d in deps]
        lines.append(f"Dependency group ({group_name}): " + ", ".join(flat))

    content = "\n".join(lines)
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [{
        "file_path": rel_path,
        "chunk_type": "project_metadata",
        "name": name,
        "start_line": 1,
        "end_line": len(text.splitlines()),
        "content": content,
    }]

def cell_source_to_text(cell):
    source = cell.get("source", [])
    if isinstance(source, list):
        return "".join(source)
    return source  # some notebooks store source as a single string


def chunk_notebook_file(path: Path, repo_root: Path):
    rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
    with path.open(encoding="utf-8", errors="ignore") as f:
        nb = json.load(f)

    cells = nb.get("cells", [])
    chunks = []
    content_parts = []   
    raw_markdown_texts = [] 
    pair_start_idx = None

    def flush(end_idx):
        nonlocal content_parts, raw_markdown_texts, pair_start_idx
        if pair_start_idx is None:
            return
        content = "\n\n".join(content_parts)
        if not content.strip():
            content_parts, raw_markdown_texts, pair_start_idx = [], [], None
            return
        if raw_markdown_texts:
            first_line = raw_markdown_texts[0].strip().splitlines()[0]
        else:
            first_line = f"cell_{pair_start_idx}"
        chunks.append({
            "file_path": rel_path,
            "chunk_type": "notebook_cell_pair",
            "name": first_line.strip("# ").strip()[:60] or f"cell_{pair_start_idx}",
            "start_line": pair_start_idx,  # cell index, not a true line number
            "end_line": end_idx,           # cell index range - notebooks have no unified line numbering
            "content": content,
        })
        content_parts, raw_markdown_texts, pair_start_idx = [], [], None

    for i, cell in enumerate(cells):
        cell_type = cell.get("cell_type")
        text = cell_source_to_text(cell)
        if not text.strip():
            continue

        if cell_type == "markdown":
            if pair_start_idx is None:
                pair_start_idx = i
            content_parts.append(f"[markdown]\n{text}")
            raw_markdown_texts.append(text)
        elif cell_type == "code":
            if pair_start_idx is None:
                pair_start_idx = i
            content_parts.append(f"[code]\n{text}")
            flush(i)  # a code cell always closes out the current pair

    flush(len(cells) - 1)  # trailing markdown with no following code cell
    return chunks

def main(repo_root_str, out_path_str="chunks.jsonl"):
    repo_root = Path(repo_root_str).resolve()
    out_path = Path(out_path_str)

    files = discover_files(repo_root)
    py_files, md_files, sh_files, toml_files, ipynb_files = files["py"], files["md"], files["sh"], files["toml"], files["ipynb"]
    print(f"Found {len(py_files)} .py, {len(md_files)} .md, {len(sh_files)} .sh, "
          f"{len(toml_files)} .toml, {len(ipynb_files)} .ipynb files")

    # First pass: parse every .py file, collect chunks + imports + defined names
    all_py_chunks = {}      # rel_path -> chunks (functions/classes)
    all_defined_names = {}  # rel_path -> [names]
    all_imports = {}        # rel_path -> [imported module names]

    for path in py_files:
        chunks, names, imports = chunk_python_file(path, repo_root)
        rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
        all_py_chunks[rel_path] = chunks
        all_defined_names[rel_path] = names
        all_imports[rel_path] = imports
        
    dotted_to_relpath = {}
    for path in py_files:
        rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
        dotted = rel_path[:-3].replace("/", ".")  # strip ".py", "/" -> "."
        if dotted.endswith(".__init__"):
            dotted = dotted[: -len(".__init__")]
        dotted_to_relpath[dotted] = rel_path
        dotted_to_relpath[path.stem] = rel_path  # also allow bare stem match

    imported_by_by_relpath = build_imported_by_map(all_imports, dotted_to_relpath)

    # Second pass: write everything out incrementally
    total = 0
    skipped = {"sh": 0, "toml": 0, "ipynb": 0}
    with out_path.open("w", encoding="utf-8") as f:
        for path in py_files:
            rel_path = str(path.relative_to(repo_root)).replace("\\", "/")

            # function/class chunks
            for chunk in all_py_chunks[rel_path]:
                f.write(json.dumps(chunk) + "\n")
                total += 1

            # module summary chunk
            summary = build_module_summary_chunk(
                path, repo_root,
                all_defined_names[rel_path],
                imported_by_by_relpath[rel_path],
            )
            f.write(json.dumps(summary) + "\n")
            total += 1

        for path in md_files:
            for chunk in chunk_markdown_file(path, repo_root):
                f.write(json.dumps(chunk) + "\n")
                total += 1

        for path in sh_files:
            for chunk in chunk_shell_file(path, repo_root):
                f.write(json.dumps(chunk) + "\n")
                total += 1

        for path in toml_files:
            try:
                for chunk in chunk_toml_file(path, repo_root):
                    f.write(json.dumps(chunk) + "\n")
                    total += 1
            except Exception as e:
                print(f"  [skip - toml parse error] {path.name}: {e}")
                skipped["toml"] += 1

        for path in ipynb_files:
            try:
                for chunk in chunk_notebook_file(path, repo_root):
                    f.write(json.dumps(chunk) + "\n")
                    total += 1
            except (json.JSONDecodeError, KeyError) as e:
                print(f"  [skip - notebook parse error] {path.name}: {e}")
                skipped["ipynb"] += 1

    print(f"Wrote {total} chunks to {out_path}")
    if any(skipped.values()):
        print(f"Skipped due to parse errors: {skipped}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python chunker.py /path/to/nanochat/repo [output.jsonl]")
        sys.exit(1)
    repo_arg = sys.argv[1]
    out_arg = sys.argv[2] if len(sys.argv) > 2 else "chunks.jsonl"
    main(repo_arg, out_arg)