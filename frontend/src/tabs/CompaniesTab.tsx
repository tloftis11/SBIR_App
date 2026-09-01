import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  type CompanyAward,
  type CompanySummary,
  type FilterOptions,
  companyAskStream,
  fetchCompanyAwards,
  searchCompanies,
} from '../lib/api'

interface Props { filterOptions: FilterOptions | null }

// ── Formatting helpers ────────────────────────────────────────────────────────

const compactUsd = (n: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD',
    notation: 'compact', maximumFractionDigits: 1,
  }).format(n)

const compact = (n: number) =>
  new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n)

function Dot() {
  return <span style={{ color: '#d1d1d6', fontSize: 10, margin: '0 2px' }}>·</span>
}

function Spinner() {
  return (
    <svg className="animate-spin w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" style={{ color: '#aeaeb2' }}>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeOpacity="0.3" />
      <path d="M12 2a10 10 0 0110 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

// ── Company list row ──────────────────────────────────────────────────────────

function CompanyRow({
  company,
  selected,
  onClick,
}: {
  company: CompanySummary
  selected: boolean
  onClick: () => void
}) {
  const p2Rate = company.award_count > 0
    ? Math.round((company.phase_2_count / company.award_count) * 100)
    : 0

  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-3.5 transition-colors"
      style={{
        background: selected ? 'rgba(0,113,227,0.06)' : 'transparent',
        borderLeft: selected ? '2px solid #0071e3' : '2px solid transparent',
      }}
    >
      <p className="text-[13px] font-semibold text-apple-text leading-snug truncate pr-2">
        {company.firm}
      </p>
      <div className="flex items-center gap-1 mt-0.5 flex-wrap">
        <span className="text-[11px] text-apple-secondary">
          {compact(company.award_count)} award{company.award_count !== 1 ? 's' : ''}
        </span>
        {company.total_funding > 0 && (
          <><Dot /><span className="text-[11px] text-apple-secondary">{compactUsd(company.total_funding)}</span></>
        )}
        {company.year_first && (
          <><Dot /><span className="text-[11px] text-apple-tertiary">
            {company.year_first}{company.year_last && company.year_last !== company.year_first ? `–${company.year_last}` : ''}
          </span></>
        )}
        {p2Rate > 0 && (
          <><Dot /><span className="text-[11px] text-apple-tertiary">{p2Rate}% Ph II</span></>
        )}
      </div>
    </button>
  )
}

// ── Company detail panel ──────────────────────────────────────────────────────

function AwardRow({ award }: { award: CompanyAward }) {
  const [open, setOpen] = useState(false)
  return (
    <div
      className="cursor-pointer"
      style={{ borderBottom: '1px solid rgba(0,0,0,0.05)' }}
      onClick={() => setOpen(v => !v)}
    >
      <div className="px-5 py-3.5 flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-medium text-apple-text leading-snug">
            {award.title ?? 'Untitled'}
          </p>
          <div className="flex items-center gap-1 mt-0.5 flex-wrap">
            {award.agency && <span className="text-[11px] text-apple-secondary">{award.agency}</span>}
            {award.phase && <><Dot /><span className="text-[11px] text-apple-secondary">{award.phase}</span></>}
            {award.award_year && <><Dot /><span className="text-[11px] text-apple-tertiary">{award.award_year}</span></>}
            {award.award_amount != null && (
              <><Dot /><span className="text-[11px] font-medium text-apple-secondary">{compactUsd(award.award_amount)}</span></>
            )}
          </div>
        </div>
        <svg
          width="14" height="14" viewBox="0 0 14 14" fill="none"
          className={`shrink-0 mt-1 transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
          style={{ color: '#aeaeb2' }}
        >
          <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      {open && award.abstract && (
        <div className="px-5 pb-4">
          <p className="text-[12px] text-apple-secondary leading-relaxed">{award.abstract}</p>
        </div>
      )}
    </div>
  )
}

function CompanyDetail({ company }: { company: CompanySummary }) {
  const [awards, setAwards]     = useState<CompanyAward[]>([])
  const [loading, setLoading]   = useState(true)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer]     = useState('')
  const [streaming, setStreaming] = useState(false)
  const [sortAwards, setSortAwards] = useState<'year' | 'amount'>('year')
  const cancelRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    setLoading(true)
    setAwards([])
    setAnswer('')
    fetchCompanyAwards(company.firm)
      .then(setAwards)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [company.firm])

  function handleAsk() {
    if (!question.trim()) return
    cancelRef.current?.()
    setAnswer(''); setStreaming(true)
    cancelRef.current = companyAskStream(
      company.firm, question,
      ev => {
        if (ev.type === 'text') setAnswer(s => s + ev.data)
        else if (ev.type === 'done') setStreaming(false)
      },
      () => setStreaming(false),
    )
  }

  // Compute agency breakdown from awards
  const agencyMap: Record<string, number> = {}
  for (const a of awards) {
    if (a.agency) agencyMap[a.agency] = (agencyMap[a.agency] ?? 0) + 1
  }
  const agencyBreakdown = Object.entries(agencyMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
  const maxAgency = agencyBreakdown[0]?.[1] ?? 1

  const sorted = [...awards].sort((a, b) => {
    if (sortAwards === 'amount') return (b.award_amount ?? 0) - (a.award_amount ?? 0)
    return (b.award_year ?? 0) - (a.award_year ?? 0)
  })

  const p2Rate = company.award_count > 0
    ? Math.round((company.phase_2_count / company.award_count) * 100)
    : 0

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Company header */}
      <div className="px-6 pt-6 pb-5" style={{ borderBottom: '1px solid rgba(0,0,0,0.07)' }}>
        <h2 className="text-[18px] font-semibold text-apple-text tracking-tight leading-tight">
          {company.firm}
        </h2>

        {/* Stat pills */}
        <div className="flex flex-wrap gap-2 mt-3">
          {[
            { label: 'Awards',   value: compact(company.award_count) },
            { label: 'Funding',  value: compactUsd(company.total_funding) },
            { label: 'Phase II', value: `${p2Rate}%` },
            ...(company.year_first ? [{ label: 'Active',
              value: `${company.year_first}–${company.year_last ?? ''}` }] : []),
          ].map(stat => (
            <div
              key={stat.label}
              className="px-3 py-1.5 rounded-lg"
              style={{ background: 'rgba(0,0,0,0.04)' }}
            >
              <p className="text-[10px] font-semibold text-apple-tertiary uppercase tracking-wider">{stat.label}</p>
              <p className="text-[14px] font-semibold text-apple-text">{stat.value}</p>
            </div>
          ))}
        </div>

        {/* Agency breakdown mini-chart */}
        {agencyBreakdown.length > 0 && (
          <div className="mt-4 space-y-1.5">
            <p className="text-[10px] font-semibold text-apple-tertiary uppercase tracking-wider mb-2">
              Top Funding Agencies
            </p>
            {agencyBreakdown.map(([agency, count]) => (
              <div key={agency} className="flex items-center gap-2">
                <span className="text-[11px] text-apple-secondary w-36 truncate shrink-0">{agency}</span>
                <div className="flex-1 bg-[#f5f5f7] rounded-full h-3 overflow-hidden">
                  <div
                    className="h-3 rounded-full"
                    style={{
                      width: `${(count / maxAgency) * 100}%`,
                      background: '#0071e3',
                    }}
                  />
                </div>
                <span className="text-[11px] text-apple-tertiary w-6 text-right">{count}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Claude ask */}
      <div className="px-6 py-4" style={{ borderBottom: '1px solid rgba(0,0,0,0.07)' }}>
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAsk()}
            placeholder={`Ask Claude about ${company.firm.split(' ')[0]}…`}
            className="flex-1 text-[13px] bg-[#f5f5f7] text-apple-text rounded-lg px-3 py-2 placeholder-apple-tertiary"
            style={{ border: '1px solid rgba(0,0,0,0.09)' }}
          />
          <button
            onClick={handleAsk}
            disabled={streaming || !question.trim()}
            className="px-4 py-2 bg-apple-blue text-white text-[12px] font-semibold rounded-lg hover:bg-apple-bluehover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {streaming ? '…' : 'Ask'}
          </button>
        </div>
        {(answer || streaming) && (
          <div className="mt-3 p-3 rounded-lg" style={{ background: 'rgba(0,113,227,0.04)', border: '1px solid rgba(0,113,227,0.12)' }}>
            <div className="flex items-center gap-1.5 mb-1.5">
              <p className="text-[10px] font-semibold text-apple-tertiary uppercase tracking-wider">Claude</p>
              {streaming && <span className="w-1.5 h-1.5 rounded-full bg-apple-blue animate-pulse" />}
            </div>
            <div className="overflow-y-auto prose prose-sm max-w-none text-[13px] text-apple-text" style={{ maxHeight: 240 }}>
              <ReactMarkdown>{answer}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>

      {/* Awards list */}
      <div className="flex-1 overflow-y-auto">
        {/* Sort controls */}
        <div
          className="px-5 py-2.5 flex items-center justify-between sticky top-0 bg-white"
          style={{ borderBottom: '1px solid rgba(0,0,0,0.05)', zIndex: 1 }}
        >
          <p className="text-[11px] font-semibold text-apple-tertiary uppercase tracking-wider">
            {loading ? 'Loading…' : 'Funding'}
          </p>
          <div className="flex gap-2">
            {(['year', 'amount'] as const).map(s => (
              <button
                key={s}
                onClick={() => setSortAwards(s)}
                className={`text-[11px] font-medium transition-colors ${
                  sortAwards === s ? 'text-apple-blue' : 'text-apple-tertiary hover:text-apple-secondary'
                }`}
              >
                {s === 'year' ? 'Recent' : 'Largest'}
              </button>
            ))}
          </div>
        </div>

        {loading && (
          <div className="flex items-center gap-2 px-5 py-4 text-[13px] text-apple-tertiary">
            <Spinner /> Loading…
          </div>
        )}

        {sorted.map(a => <AwardRow key={a.id} award={a} />)}
      </div>
    </div>
  )
}

// ── Main tab ──────────────────────────────────────────────────────────────────

export default function CompaniesTab({ filterOptions }: Props) {
  const [query,    setQuery]    = useState('')
  const [sortBy,   setSortBy]   = useState<'count' | 'funding'>('count')
  const [agency,   setAgency]   = useState('')
  const [state,    setState_]   = useState('')
  const [phase,    setPhase]    = useState('')
  const [yearMin,  setYearMin]  = useState('')
  const [yearMax,  setYearMax]  = useState('')
  const [companies, setCompanies] = useState<CompanySummary[]>([])
  const [selected,  setSelected]  = useState<CompanySummary | null>(null)
  const [loading,   setLoading]   = useState(true)

  const inputRef = useRef<HTMLInputElement>(null)

  function load(q = query, sb = sortBy, ag = agency, st = state, ph = phase, ym = yearMin, ymx = yearMax) {
    setLoading(true)
    searchCompanies({
      query: q, sort_by: sb,
      filter_agency: ag || undefined,
      filter_state: st || undefined,
      filter_phase: ph || undefined,
      filter_year_min: ym ? Number(ym) : undefined,
      filter_year_max: ymx ? Number(ymx) : undefined,
      limit: 100,
    })
      .then(setCompanies)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  // Initial load — top companies by award count
  useEffect(() => { load() }, [])

  function handleSearch() { load() }

  return (
    <div className="max-w-6xl mx-auto px-8 py-6">
      <div
        className="bg-white rounded-card overflow-hidden flex"
        style={{
          boxShadow: '0 2px 12px rgba(0,0,0,0.09)',
          height: 'calc(100vh - 120px)',
          minHeight: 520,
        }}
      >
        {/* ── Left: list panel ── */}
        <div
          className="flex flex-col"
          style={{
            width: selected ? 320 : '100%',
            borderRight: '1px solid rgba(0,0,0,0.08)',
            transition: 'width 0.25s ease',
            minWidth: 260,
          }}
        >
          {/* Search + controls */}
          <div className="p-4 space-y-3" style={{ borderBottom: '1px solid rgba(0,0,0,0.07)' }}>
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder="Search companies…"
                className="flex-1 text-[13px] bg-[#f5f5f7] text-apple-text rounded-lg px-3 py-2 placeholder-apple-tertiary"
                style={{ border: '1px solid rgba(0,0,0,0.09)' }}
              />
              <button
                onClick={handleSearch}
                className="px-3 py-2 bg-apple-blue text-white text-[12px] font-semibold rounded-lg hover:bg-apple-bluehover transition-colors"
              >
                Go
              </button>
            </div>

            {/* Sort + filters */}
            <div className="flex items-center gap-2 flex-wrap">
              {/* Sort toggle */}
              <div
                className="flex rounded-md p-0.5"
                style={{ background: 'rgba(0,0,0,0.06)' }}
              >
                {([['count', 'Most Awards'], ['funding', 'Most Funding']] as const).map(([v, label]) => (
                  <button
                    key={v}
                    onClick={() => { setSortBy(v); load(query, v, agency, state, phase, yearMin, yearMax) }}
                    className={`px-2.5 py-1 text-[11px] font-medium rounded-md transition-all ${
                      sortBy === v ? 'bg-white text-apple-text shadow-sm' : 'text-apple-secondary'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Filter row */}
            <div className="flex gap-1.5 flex-wrap">
              <select
                className="text-[11px] bg-[#f5f5f7] text-apple-secondary rounded-md px-2 py-1"
                style={{ border: '1px solid rgba(0,0,0,0.09)' }}
                value={agency}
                onChange={e => { setAgency(e.target.value); load(query, sortBy, e.target.value, state, phase, yearMin, yearMax) }}
              >
                <option value="">All agencies</option>
                {filterOptions?.agencies.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
              <select
                className="text-[11px] bg-[#f5f5f7] text-apple-secondary rounded-md px-2 py-1"
                style={{ border: '1px solid rgba(0,0,0,0.09)' }}
                value={state}
                onChange={e => { setState_(e.target.value); load(query, sortBy, agency, e.target.value, phase, yearMin, yearMax) }}
              >
                <option value="">All states</option>
                {filterOptions?.states.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              {['Phase I', 'Phase II'].map(p => (
                <button
                  key={p}
                  onClick={() => { const nv = phase === p ? '' : p; setPhase(nv); load(query, sortBy, agency, state, nv, yearMin, yearMax) }}
                  className={`text-[11px] px-2.5 py-1 rounded-md font-medium transition-colors ${
                    phase === p ? 'bg-apple-text text-white' : 'bg-[#f5f5f7] text-apple-secondary'
                  }`}
                  style={{ border: '1px solid rgba(0,0,0,0.09)' }}
                >
                  {p.replace('Phase ', 'Ph ')}
                </button>
              ))}
              {/* Year range */}
              <div
                className="flex items-center gap-1 text-[11px] bg-[#f5f5f7] text-apple-secondary rounded-md px-2 py-1"
                style={{ border: '1px solid rgba(0,0,0,0.09)' }}
              >
                <input
                  type="number"
                  placeholder="From"
                  value={yearMin}
                  onChange={e => { setYearMin(e.target.value); load(query, sortBy, agency, state, phase, e.target.value, yearMax) }}
                  className="w-12 bg-transparent placeholder-apple-tertiary focus:outline-none text-center"
                />
                <span className="text-apple-tertiary">–</span>
                <input
                  type="number"
                  placeholder="To"
                  value={yearMax}
                  onChange={e => { setYearMax(e.target.value); load(query, sortBy, agency, state, phase, yearMin, e.target.value) }}
                  className="w-12 bg-transparent placeholder-apple-tertiary focus:outline-none text-center"
                />
              </div>
            </div>
          </div>

          {/* Company list */}
          <div className="flex-1 overflow-y-auto">
            {loading && (
              <div className="flex items-center gap-2 px-4 py-4 text-[13px] text-apple-tertiary">
                <Spinner /> Loading…
              </div>
            )}

            {!loading && companies.length === 0 && (
              <p className="text-[13px] text-apple-tertiary px-4 py-6 text-center">No companies found</p>
            )}

            {companies.map(c => (
              <CompanyRow
                key={c.firm}
                company={c}
                selected={selected?.firm === c.firm}
                onClick={() => setSelected(c)}
              />
            ))}
          </div>

          {/* Count footer */}
          {!loading && companies.length > 0 && (
            <div
              className="px-4 py-2.5"
              style={{ borderTop: '1px solid rgba(0,0,0,0.06)' }}
            >
              <p className="text-[11px] text-apple-tertiary">
                {companies.length} companies shown
              </p>
            </div>
          )}
        </div>

        {/* ── Right: detail panel ── */}
        {selected && (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Close button */}
            <button
              onClick={() => setSelected(null)}
              className="absolute right-10 mt-2 p-1.5 rounded-full hover:bg-[#f5f5f7] transition-colors"
              style={{ alignSelf: 'flex-end', marginTop: 8, marginRight: 12, position: 'relative' }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ color: '#aeaeb2' }}>
                <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
            <CompanyDetail company={selected} />
          </div>
        )}

        {/* Empty detail state */}
        {!selected && (
          <div className="flex-1 flex flex-col items-center justify-center text-center" style={{ display: 'none' }} />
        )}
      </div>
    </div>
  )
}
