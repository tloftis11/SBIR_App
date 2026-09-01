from pydantic import BaseModel, Field
from typing import Optional


class SearchFilters(BaseModel):
    agency: Optional[str] = None
    phase: Optional[str] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    state: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    limit: int = Field(default=20, ge=1, le=50)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    limit: int = Field(default=25, ge=1, le=50)


class AwardResult(BaseModel):
    id: str
    firm: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    agency: Optional[str] = None
    phase: Optional[str] = None
    award_year: Optional[int] = None
    award_amount: Optional[int] = None
    state_code: Optional[str] = None
    similarity: float


class SearchResponse(BaseModel):
    results: list[AwardResult]
    total: int
    query: str


class FilterOptions(BaseModel):
    agencies: list[str]
    phases: list[str]
    states: list[str]
    year_min: Optional[int]
    year_max: Optional[int]
