// In production (Render), VITE_API_URL is set to the backend service URL.
// In local dev, Vite proxies /api → localhost:8000 so the empty string works.
const BASE = import.meta.env.VITE_API_URL ?? '/api'

export interface SearchFilters {
  agency?: string
  phase?: string
  year_min?: number
  year_max?: number
  state?: string
}

export interface AwardResult {
  id: string
  firm?: string
  title?: string
  abstract?: string
  agency?: string
  phase?: string
  award_year?: number
  award_amount?: number
  state_code?: string
  similarity: number
}

export interface SearchResponse {
  results: AwardResult[]
  total: number
  query: string
}

export interface FilterOptions {
  agencies: string[]
  phases: string[]
  states: string[]
  year_min?: number
  year_max?: number
}

export async function fetchFilters(): Promise<FilterOptions> {
  const res = await fetch(`${BASE}/filters`)
  if (!res.ok) throw new Error('Failed to load filters')
  return res.json()
}

export async function search(
  query: string,
  filters: SearchFilters,
  limit = 20,
): Promise<SearchResponse> {
  const res = await fetch(`${BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, filters, limit }),
  })
  if (!res.ok) throw new Error('Search failed')
  return res.json()
}

export type SseEvent =
  | { type: 'results'; data: AwardResult[] }
  | { type: 'text'; data: string }
  | { type: 'done' }

export function askStream(
  question: string,
  filters: SearchFilters,
  limit: number,
  onEvent: (e: SseEvent) => void,
  onError: (err: Error) => void,
): () => void {
  let cancelled = false

  fetch(`${BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, filters, limit }),
  })
    .then(async (res) => {
      if (!res.ok) throw new Error('Ask failed')
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done || cancelled) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''
        for (const part of parts) {
          const line = part.replace(/^data: /, '').trim()
          if (!line) continue
          try { onEvent(JSON.parse(line) as SseEvent) } catch {}
        }
      }
    })
    .catch((err) => { if (!cancelled) onError(err) })

  return () => { cancelled = true }
}

// ── Companies ────────────────────────────────────────────────────────────────

export interface CompanySummary {
  firm: string
  award_count: number
  total_funding: number
  phase_1_count: number
  phase_2_count: number
  year_first?: number
  year_last?: number
}

export interface CompanyAward {
  id: string
  title?: string
  abstract?: string
  agency?: string
  phase?: string
  award_year?: number
  award_amount?: number
  state_code?: string
  keywords?: string
}

export interface CompanySearchRequest {
  query?: string
  sort_by?: 'count' | 'funding'
  filter_agency?: string
  filter_state?: string
  filter_phase?: string
  filter_year_min?: number
  filter_year_max?: number
  limit?: number
}

export async function searchCompanies(req: CompanySearchRequest = {}): Promise<CompanySummary[]> {
  const res = await fetch(`${BASE}/companies/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error('Company search failed')
  return res.json()
}

export interface AcquisitionInfo {
  acquired: boolean
  acquired_by: string | null
  acquisition_year: number | null
  confidence: 'high' | 'medium' | 'low'
  notes: string | null
  checked_at?: string
  from_cache?: boolean
}

export async function fetchAcquisition(firm: string): Promise<AcquisitionInfo> {
  const res = await fetch(`${BASE}/companies/${encodeURIComponent(firm)}/acquisition`)
  if (!res.ok) throw new Error('Acquisition check failed')
  return res.json()
}

export async function fetchCompanyAwards(firm: string): Promise<CompanyAward[]> {
  const res = await fetch(`${BASE}/companies/${encodeURIComponent(firm)}/awards`)
  if (!res.ok) throw new Error('Failed to fetch company awards')
  return res.json()
}

export type CompanyAskEvent =
  | { type: 'text'; data: string }
  | { type: 'done' }

export function companyAskStream(
  firm: string,
  question: string,
  onEvent: (e: CompanyAskEvent) => void,
  onError: (err: Error) => void,
): () => void {
  let cancelled = false
  fetch(`${BASE}/companies/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ firm, question }),
  })
    .then(async (res) => {
      if (!res.ok) throw new Error('Company ask failed')
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done || cancelled) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''
        for (const part of parts) {
          const line = part.replace(/^data: /, '').trim()
          if (!line) continue
          try { onEvent(JSON.parse(line) as CompanyAskEvent) } catch {}
        }
      }
    })
    .catch(err => { if (!cancelled) onError(err) })
  return () => { cancelled = true }
}

// ── Trends ──────────────────────────────────────────────────────────────────

export interface TrendPoint { year: number; count: number; total_amount: number; [k: string]: unknown }
export interface AgencyShare { agency: string; count: number; [k: string]: unknown }
export interface TopicCluster { topic: string; count: number; [k: string]: unknown }

export interface TrendsData {
  by_year: TrendPoint[]
  by_agency: AgencyShare[]
  by_phase: { phase: string; count: number; [k: string]: unknown }[]
  top_states: { state: string; count: number; [k: string]: unknown }[]
}

export async function fetchTrends(filters: SearchFilters = {}): Promise<TrendsData> {
  const res = await fetch(`${BASE}/trends`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(filters),
  })
  if (!res.ok) throw new Error('Trends failed')
  return res.json()
}

export type TrendSseEvent =
  | { type: 'text'; data: string }
  | { type: 'done' }

export function trendAskStream(
  question: string,
  onEvent: (e: TrendSseEvent) => void,
  onError: (err: Error) => void,
): () => void {
  let cancelled = false

  fetch(`${BASE}/trends/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
    .then(async (res) => {
      if (!res.ok) throw new Error('Trends ask failed')
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done || cancelled) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''
        for (const part of parts) {
          const line = part.replace(/^data: /, '').trim()
          if (!line) continue
          try { onEvent(JSON.parse(line) as TrendSseEvent) } catch {}
        }
      }
    })
    .catch((err) => { if (!cancelled) onError(err) })

  return () => { cancelled = true }
}
