"""
FastAPI backend for the nanochat RAG chatbot.

Endpoints:
    GET  /health        — liveness check
    POST /ask           — retrieve + generate an answer with source citations
    POST /ask/stream    — same, but streams tokens as SSE

Run with:
    uvicorn api:app --reload --port 8000
"""
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from answer import answer as rag_answer, answer_stream

load_dotenv()

app = FastAPI(
    title="nanochat RAG API",
    description="Answers questions about the nanochat codebase with source citations.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- Pydantic models ---

class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language question about the nanochat codebase")
    k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")


class Source(BaseModel):
    file_path: str
    chunk_type: str
    name: str
    start_line: int
    end_line: int
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]


# --- Endpoints ---

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    if not os.environ.get("GROQ_API_KEY"):
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")

    response_text, sources = rag_answer(request.query, k=request.k)
    return AskResponse(answer=response_text, sources=[Source(**s) for s in sources])


@app.post("/ask/stream")
def ask_stream(request: AskRequest):
    if not os.environ.get("GROQ_API_KEY"):
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")

    def sse_events():
        for event_type, data in answer_stream(request.query, k=request.k):
            if event_type == "token":
                yield f"data: {json.dumps({'token': data})}\n\n"
            else:
                yield f"data: {json.dumps({'sources': data, 'done': True})}\n\n"

    return StreamingResponse(
        sse_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
