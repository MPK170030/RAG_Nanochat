# Technical Decisions

Every non-obvious architectural or design choice made during this build, with reasoning.

---

## Day 1 — Ingestion / Chunker

### AST-based chunking for Python, not text-splitting
Chunk boundaries follow Python AST node boundaries (functions, classes) rather than
fixed token counts. This keeps semantically coherent units together and makes
`file_path + name + line range` metadata exact rather than approximate.
- **Trade-off**: means non-Python files (shell, markdown) fall back to simpler heuristics.

### Two-pass architecture for Python files
First pass collects all `.py` chunks + imports. Second pass builds the reverse import
map (`imported_by`) across the whole repo before writing any output. A single pass
can't build `imported_by` because the importer file may not have been seen yet.

### Methods > 15 lines get their own `function` chunk (in addition to the parent `class` chunk)
`METHOD_SIZE_THRESHOLD = 15`. Short methods (trivial getters etc.) aren't worth
duplicating. Long methods (where someone actually asks "how does X work") benefit from
being retrievable in isolation without pulling in the entire class.
- **Trade-off**: large class methods appear twice in `chunks.jsonl` (once inside the
  class chunk, once as their own function chunk). Accepted for MVP; can deduplicate
  at retrieval time if it causes noise.

### `module_summary` chunk per `.py` file (docstring + defined names + import graph)
One synthetic chunk per file captures the file-level "what does this module do" signal
that no single function/class chunk carries. Intended to be the top hit for queries
like "what is gpt.py's role in the codebase".

### Chunks written to `chunks.jsonl` (newline-delimited JSON), not a database
Simple and inspectable. The embedding step (Day 2) can stream the file without
loading it all into memory. Easy to re-generate without any teardown.

---

## Day 2 — Embeddings + Retrieval

### Model: `BAAI/bge-small-en-v1.5` via `sentence-transformers`
- CPU-friendly (33M params, ~130MB), no API key required.
- Strong performance on BEIR retrieval benchmarks relative to its size.
- **Trade-off vs. `bge-base` or `bge-large`**: lower quality ceiling, but fast enough
  to embed the entire nanochat corpus in seconds on CPU and query in <100ms.
  Upgrade path is a one-line model name change + re-run of `embed.py`.

### Asymmetric retrieval: documents get no prefix, queries get the BGE retrieval prefix
BGE-family models are trained asymmetrically. Documents are embedded as-is.
Queries are prefixed with `"Represent this sentence for searching relevant passages: "`.
Not doing this correctly would leave ~5-10% retrieval quality on the table.
Handled explicitly in `retrieve.py` rather than via Chroma's embedding function, so
the prefix only applies to queries, not indexed chunks.

### Embed metadata header + content, store raw content in Chroma's `documents` field
Each chunk is embedded as `[chunk_type] file_path :: name\n<content>`. This gives the
embedding model richer signal (knowing something is a `function` in `gpt.py` vs. a
`shell_script`) without polluting the stored text that the LLM will read in Day 3.
The `documents` field in Chroma stores only the raw `content`.

### Vector store: Chroma with cosine distance, persisted to `chroma_db/`
- Local, file-based, zero infrastructure. Fits the "hand-rolled, no managed services"
  constraint from the project brief.
- Cosine distance chosen over L2 because embeddings are L2-normalized anyway
  (`normalize_embeddings=True`), making cosine and dot-product equivalent — but
  declaring it explicitly keeps the Chroma HNSW index tuned for that metric.

### Re-index strategy: delete collection + recreate (no incremental updates)
`embed.py` deletes the existing Chroma collection before re-inserting. Simpler than
tracking which chunks changed. The full corpus is small enough (~minutes on CPU) that
this is fine. An incremental re-index script is listed as optional in `TODO.md` (Day 4).

### Chunk ID scheme: `file_path::name::start_line`
Stable and human-readable. Collision-free within a repo because (file, name, start_line)
uniquely identifies any chunk the chunker can produce. Avoids needing a UUID.

### Module-level singleton for model + collection in `retrieve.py`
`_model` and `_collection` are module-level globals, initialized lazily on first call
to `retrieve()`. This avoids reloading the 130MB model on every call when `retrieve.py`
is imported by the Day 3 generation layer. In the Streamlit app (Day 4), the process
stays alive between requests, so the singleton is loaded once per session.

### No chunk-type boosting at retrieval time (deferred to Day 4 eval)
`module_summary` chunks may deserve a score boost for file-level queries. Holding off
until the 15 eval questions reveal whether flat cosine retrieval already surfaces them
correctly at rank ≤ 3. Don't fix what isn't broken.

### `EXCLUDE_FILES`: `LOG.md` and `LEADERBOARD.md` removed from the index
`dev/LOG.md` (1089 lines, Karpathy's experiment journal) generated 110 `markdown_section`
chunks — by far the noisiest source in the index. `dev/LEADERBOARD.md` added 8 more.
Both are development artefacts, not codebase documentation. Indexing them caused them to
rank 1–2 for queries like "what optimizer does nanochat use" and "how does the dataloader
stream data", pushing correct code chunks below k=5.
- **Alternative considered**: post-retrieval score penalty on `markdown_section` chunks.
  Rejected — it papers over a bad indexing decision rather than fixing it. Excluding the
  files upstream is correct and has no downside.

### `EXCLUDE_MD_SECTIONS`: boilerplate README sections excluded from chunking
Sections "Acknowledgements", "Cite", "License", "Contributing", "Guides" have no
implementation content but match almost any codebase query at a high cosine score
(broad vocabulary, many nanochat-adjacent terms). Excluding them removes ~5 chunks of
noise. The README's informative sections (File structure, Setup, Precision/dtype, etc.)
are retained.

### Decorator lines included in function/class chunk content
Previously, `chunk_python_file` used `node.lineno` (the `class`/`def` keyword line) as
the chunk start, so decorators like `@dataclass` or `@torch.no_grad()` were excluded from
the chunk text. Fixed to use `node.decorator_list[0].lineno` when decorators are present.
This means `@dataclass` is now part of the `GPTConfig` chunk, giving the embedding model
correct signal that it is a dataclass.

### Dataclass field summary prepended to `@dataclass` class chunks
Pure dataclass chunks (like `GPTConfig`) contain only field declarations with no docstring,
making their embeddings semantically weak. For classes decorated with `@dataclass`, a
structured header is synthesised and prepended to the chunk content:
```
@dataclass GPTConfig — fields:
  sequence_len
  vocab_size
  n_layer
  n_head  # number of query heads
  n_kv_head  # number of key/value heads (GQA)
  n_embd
  window_pattern
```
This gives the embedding model explicit field-name and inline-comment signal without
altering the stored source code. The raw source still follows the header in the chunk.

---

## Day 3 — Generation

### Model: `qwen/qwen3.6-27b` via Groq (changed from planned `llama-3.3-70b`)
Qwen3 supports extended chain-of-thought reasoning, which improves answer accuracy for
code-explanation queries. The `<think>...</think>` block is stripped before returning
to the caller (`re.sub` in `answer.py`) so downstream consumers always get clean text.
- **Trade-off**: Qwen3 is a newer model; if it gets deprecated on Groq the fallback is
  a one-line `MODEL` constant change.

### System prompt: answer from context only, cite file + function, admit uncertainty
Three constraints baked into the system prompt: (1) use retrieved context, not training
knowledge; (2) always cite which file/function the answer came from; (3) say "not found
in context" rather than hallucinating. Keeps the chatbot honest and its citations auditable.

### `answer()` returns `(response_text, sources)` — sources strip the `content` field
Sources passed back to the UI are chunk metadata only (file, type, name, lines, score),
not the full text. This keeps the API response payload small; the UI shows metadata and
lets the user navigate to the source rather than reproducing it inline.

### Temperature 0.2 — low but not zero
Zero temperature produces deterministic but sometimes stilted answers. 0.2 adds just
enough variance for natural phrasing while keeping factual consistency high.

---

## Day 4 — UI, Serving, Deployment

### Frontend: React + Vite + Tailwind CSS (not Streamlit)
Streamlit was the original plan for speed. Replaced with React + Vite because:
1. **Portfolio signal** — FastAPI + React is a genuine full-stack stack; Streamlit is
   a Python script masquerading as a UI, not representative of how products are built.
2. **Full control** — chat bubbles, source cards, loading states, and responsive layout
   all require real CSS; Streamlit's styling options are heavily constrained.
3. **Frontend/backend separation** — React consumes the FastAPI REST API exactly as any
   other client would, keeping the backend genuinely frontend-agnostic.
- **Trade-off**: more setup (npm, Vite config, component structure) and more code.
  For a portfolio project this is a feature — more to demonstrate.

### FastAPI over direct Python import
FastAPI + Uvicorn as the backend server, rather than having the frontend call Python
functions directly. Reasons:
1. **Portfolio signal** — shows REST API design, Pydantic validation, and OpenAPI docs.
2. **Separation of concerns** — backend is callable from curl, notebooks, or any future
   frontend without modification.
3. **Industry pattern** — this is how production RAG services are structured.

### FastAPI endpoint design: `POST /ask`, `GET /health`
Single action endpoint keeps the API surface minimal. `GET /health` is included for
Docker health checks and load balancer probes. OpenAPI docs auto-generated at `/docs`.

### Pydantic models for request/response
`AskRequest(query: str, k: int = 5)` and `AskResponse(answer: str, sources: list[Source])`.
Provides free input validation (422 on bad input), auto-generated docs, and a clear
contract between frontend and backend.

### CORS: allow localhost origins only (dev), deployed frontend origin (prod)
React dev server runs on `localhost:5173`, FastAPI on `localhost:8000`. CORS middleware
required for cross-origin browser fetches. Restricted to known origins; never wildcard.

### Docker Compose: two services (`api`, `ui`) sharing a bind-mounted `chroma_db/`
`chroma_db/` is bind-mounted so the pre-built vector store is shared without
re-embedding at container start. `GROQ_API_KEY` injected via `.env`, never baked into
the image. React app is built as static files and served by Nginx in the `ui` container.
- **Pre-condition**: `embed.py` must be run locally before `docker-compose up` to
  populate `chroma_db/`. Acceptable for a portfolio project.

### `requirements.txt` added (not just install-as-needed)
Needed for reproducible Docker builds. Pins `sentence-transformers`, `chromadb`,
`fastapi`, `uvicorn`, `groq`, `python-dotenv`.
