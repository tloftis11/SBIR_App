"""
SBIR Explorer API

Endpoints:
  GET  /health          — Render health check
  GET  /filters         — Dropdown options for the frontend
  POST /search          — Semantic search, returns JSON
  POST /ask             — Semantic search + Claude synthesis, streams SSE
"""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .models import SearchRequest, SearchResponse, AskRequest, FilterOptions
from .search import semantic_search, get_filter_options
from .synthesize import stream_synthesis

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(
    title="SBIR Explorer",
    description="Semantic search and AI synthesis over 200k+ SBIR/STTR awards",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your frontend domain in production
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/filters", response_model=FilterOptions)
def filters():
    """Return distinct agencies, phases, states and year range for UI dropdowns."""
    return get_filter_options()


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    """
    Semantic search over award embeddings.
    Returns ranked awards with similarity scores.
    """
    try:
        results = semantic_search(req.query, req.filters, req.limit)
    except Exception as e:
        log.error("Search error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return SearchResponse(results=results, total=len(results), query=req.query)


@app.post("/ask")
def ask(req: AskRequest):
    """
    Semantic search + Claude synthesis, streamed as Server-Sent Events.

    SSE event format:
      data: {"type": "results", "data": [...awards...]}
      data: {"type": "text",    "data": "token..."}
      ...
      data: {"type": "done"}
    """
    try:
        results = semantic_search(req.question, req.filters, req.limit)
    except Exception as e:
        log.error("Search error in /ask: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return StreamingResponse(
        stream_synthesis(req.question, results),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disables Nginx buffering on Render
        },
    )
