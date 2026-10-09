# RAG Nanochat

A retrieval-augmented generation (RAG) chatbot that answers natural-language questions about Andrej Karpathy's [nanochat](https://github.com/karpathy/nanochat) codebase — with source citations down to the exact file, function, and line range.

**[Live Demo](https://coderag.manavpkothari.dev)**

---

## How it works

```
User question
     │
     ▼
Embed query (BGE)
     │
     ▼
ChromaDB vector search → top-k code chunks
     │
     ▼
OpenRouter LLM (Qwen3 + fallback chain)
     │
     ▼
Streamed answer + source citations
```

The codebase is chunked via AST (not naive text splitting) — functions, classes, and methods each become their own retrievable unit with metadata.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, Tailwind CSS v4 |
| Backend | FastAPI, Python 3.11 |
| Embeddings | BGE-small-en-v1.5 (sentence-transformers) |
| Vector store | ChromaDB |
| LLM | OpenRouter (Qwen3-30B + Llama / DeepSeek fallbacks) |
| Deployment | Docker, AWS EC2, ECR, Nginx, Let's Encrypt |
| CI/CD | GitHub Actions (test → build → deploy → smoke test) |

---

## Features

- **Streaming responses** — tokens stream to the UI via SSE as they're generated
- **Source citations** — every answer links back to the exact file, chunk type, and line range
- **AST-based chunking** — Python files are parsed into function/class/method chunks, not arbitrary text windows
- **Model fallback chain** — if the primary model is unavailable, OpenRouter automatically falls back to the next in the chain
- **50 unit tests + E2E smoke tests** — pytest suite covering the RAG pipeline, API endpoints, chunker, and retrieval eval metrics

---

## Local development

```bash
# Backend
cp .env.example .env          # add your OPENROUTER_API_KEY
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn api:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Requires a populated `chroma_db/`. To rebuild it from the nanochat source:

```bash
python chunker.py /path/to/nanochat
python embed.py
```

---

## Tests

```bash
pytest                  # 50 unit tests
pytest -m e2e           # smoke tests against the live API
```

---

## Architecture

```
chunker.py ──→ chunks.jsonl ──→ embed.py ──→ chroma_db/
                                                  │
User question ──→ api.py ──→ answer.py ──→ retrieve.py
                                │                 │
                        OpenRouter LLM      ChromaDB + BGE
```

The backend runs in Docker on AWS EC2 behind Nginx with TLS. The frontend is deployed on Vercel. The `chroma_db/` is baked into the Docker image at build time. The OpenRouter API key is injected at container startup from AWS SSM Parameter Store.
