# RAG Nanochat — 4 Day Build Plan

Goal: chatbot that answers questions about the `nanochat` codebase (Karpathy's repo), with source citations.

## Stack decisions

| Component | Choice | Notes |
|---|---|---|
| Chunking | `ast`-based, hand-rolled | Done — `chunker.py` |
| Embeddings | `BAAI/bge-small-en-v1.5` (via `sentence-transformers`) | CPU-friendly, no API key |
| Vector store | Chroma | Local, file-based, zero setup |
| LLM | Groq free tier (`llama-3.3-70b`) primary, Ollama (`qwen2.5-coder:7b`) fallback | Groq = better quality, rate-limited; Ollama = fully offline |
| Orchestration | Hand-rolled Python | Skipping LangChain/LlamaIndex for MVP simplicity |
| UI | React + Vite + Tailwind CSS | Full-stack portfolio signal; full styling control |

---

## Day 1 — Ingestion pipeline ✅ (chunker built)

- [x] Clone nanochat, inventory files
- [x] Build `ast`-based Python chunker (function/class level, docstring + context)
- [x] Build fallback chunker for markdown (`README.md` split by `##` headers)
- [x] Attach metadata to every chunk (file path, name, lines, type)
- [x] Add file-level module summary chunk (docstring + defined names + import graph)
- [x] Add import-graph extraction ("imported by" per file)
- [x] Write chunks to `chunks.jsonl` incrementally
- [x] Verify: line-number slicing matches source exactly (spot-checked, no off-by-one)
- [x] Verify: import graph matches `grep` ground truth
- [ ] Run chunker against your actual local clone (not just the sandbox test) and re-verify
- [ ] Decide: keep full 400-line `GPT` class chunk as-is, or deprioritize it in favor of the already-extracted method-level chunks + module summary (flagged during testing — full class chunk may be large for some embedding context limits)

## Day 2 — Embeddings + retrieval

- [ ] Install `sentence-transformers`, `chromadb`
- [ ] Load `chunks.jsonl`, embed every chunk with `bge-small-en-v1.5`
- [ ] Load embeddings + metadata into a persistent Chroma collection
- [ ] Write `retrieve(query, k=5) -> list[chunk]` function
- [ ] Write 10–15 test questions with known correct source file/function, for eval later
  - e.g. "how does nanochat do rotary embeddings", "what does speedrun.sh do", "what is gpt.py's role in the codebase"
- [ ] Manually test retrieval against the 15 questions — confirm right chunk lands in top-3
- [ ] Decide chunk-type weighting if needed (e.g. boost `module_summary` chunks for "what does file X do" style queries)

## Day 3 — Generation

- [ ] Set up Groq API key (free) and/or install + pull Ollama model
- [ ] Write system prompt: answer only from provided context, cite file/line, say "not found in context" if unanswerable
- [ ] Add context token budget / truncation (cap retrieved chunks to ~3-4k tokens)
- [ ] Write `answer(query) -> (response, sources)` combining retrieval + generation
- [ ] Run the 15 test questions through both Groq and Ollama, compare quality
- [ ] Pick primary model, keep the other as fallback

## Day 4 — Pipeline improvements, UI, serving, deployment

### Pipeline improvements (priority — do before UI)
- [ ] Diagnose and fix eval misses: Hit@1=26.7%, Hit@5=66.7%, MRR=0.410
  - [ ] Hybrid retrieval: BM25 + dense vector search, fuse with RRF
  - [ ] HyDE (Hypothetical Document Embeddings): LLM generates a fake answer, embed that instead of raw query
  - [ ] Cross-encoder re-ranking: retrieve top-20 dense, re-rank to top-5 with a cross-encoder
  - [ ] Re-run eval after each improvement to measure delta

### Backend — FastAPI (`api.py`)
- [ ] `POST /ask` — body: `{query: str, k: int = 5}`, response: `{answer: str, sources: [...]}`
- [ ] `GET /health` — liveness check for Docker
- [ ] Pydantic `AskRequest` / `AskResponse` / `Source` models
- [ ] CORS middleware (allow `localhost:5173` in dev)
- [ ] Confirm OpenAPI docs render at `/docs`

### Frontend — React + Vite + Tailwind CSS (`frontend/`)
- [ ] `npm create vite@latest frontend -- --template react`
- [ ] Install Tailwind CSS
- [ ] Components:
  - `ChatWindow` — scrollable message history, auto-scroll to bottom
  - `MessageBubble` — user (right-aligned) vs assistant (left-aligned) with distinct styling
  - `SourceCard` — collapsible card per source: file path, chunk type, name, line range, score badge
  - `ChatInput` — fixed bottom bar, send on Enter or button click, disabled while loading
  - `Sidebar` — k-slider (1–10), clear conversation button, model/index info
- [ ] Loading state: typing indicator while awaiting API response
- [ ] Error state: inline error message if API call fails
- [ ] Fetch: `POST http://localhost:8000/ask`, parse `{answer, sources}`

### Deployment — Docker Compose
- [ ] `Dockerfile.api` — Python image, installs `requirements.txt`, runs `uvicorn`
- [ ] `Dockerfile.ui` — Node build stage (Vite build), Nginx serve stage (static files)
- [ ] `docker-compose.yml`:
  - `api` service: bind-mount `chroma_db/`, env `GROQ_API_KEY` from `.env`
  - `ui` service: depends_on `api`, serves built React app via Nginx
  - `ui` Nginx config: proxy `/api/*` to `http://api:8000` (eliminates CORS in prod)
- [ ] `.dockerignore`: exclude `myenv/`, `node_modules/`, `__pycache__/`, `.env`
- [ ] `requirements.txt`: pin all Python deps

### Polish
- [ ] README: setup steps, how to re-index when nanochat updates upstream
- [ ] (Optional) Incremental re-index script: `git pull` nanochat + re-embed changed files only

---

## Open items / reminders

- [ ] Rotate the OpenAI API key that was exposed in the `.env` screenshot earlier in this project, if not already done
- [ ] Confirm `.env` is listed in `.gitignore` before any commits/pushes
