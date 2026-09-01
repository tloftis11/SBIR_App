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

from pydantic import BaseModel

from .models import SearchRequest, SearchResponse, AskRequest, FilterOptions, SearchFilters
from .search import semantic_search, get_filter_options
from .synthesize import stream_synthesis
from .trends import get_trends, stream_trend_analysis
from .companies import search_companies, get_company_awards, stream_company_analysis
from .acquisition import get_acquisition_info

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


@app.post("/trends")
def trends(filters: SearchFilters):
    """Aggregate award counts and amounts by year, agency, phase, and state."""
    try:
        return get_trends(filters)
    except Exception as e:
        log.error("Trends error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class TrendAskRequest(BaseModel):
    question: str


@app.post("/trends/ask")
def trends_ask(req: TrendAskRequest):
    """Stream Claude's analysis of SBIR trends."""
    return StreamingResponse(
        stream_trend_analysis(req.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class CompanySearchRequest(BaseModel):
    query: str = ""
    sort_by: str = "count"
    filter_agency: str | None = None
    filter_state: str | None = None
    filter_phase: str | None = None
    filter_year_min: int | None = None
    filter_year_max: int | None = None
    limit: int = 30


class CompanyAskRequest(BaseModel):
    firm: str
    question: str = "Summarize this company's SBIR portfolio and research focus."


@app.post("/companies/search")
def companies_search(req: CompanySearchRequest):
    try:
        return search_companies(
            req.query, req.sort_by, req.filter_agency,
            req.filter_state, req.filter_phase,
            req.filter_year_min, req.filter_year_max, req.limit,
        )
    except Exception as e:
        log.error("Company search error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/companies/{firm_name}/acquisition")
def company_acquisition_route(firm_name: str):
    try:
        awards = get_company_awards(firm_name)
        return get_acquisition_info(firm_name, awards)
    except Exception as e:
        log.error("Acquisition error for %s: %s", firm_name, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/companies/{firm_name}/awards")
def company_awards_route(firm_name: str):
    try:
        return get_company_awards(firm_name)
    except Exception as e:
        log.error("Company awards error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/companies/ask")
def company_ask(req: CompanyAskRequest):
    awards = get_company_awards(req.firm)
    return StreamingResponse(
        stream_company_analysis(req.firm, awards, req.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        results = semantic_search(req.question, req.filters, 75)
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
