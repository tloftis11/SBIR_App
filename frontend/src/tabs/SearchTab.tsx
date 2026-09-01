import { useRef, useState } from 'react'
import {
  type FilterOptions, type SearchFilters,
  askStream,
} from '../lib/api'

interface Props { filterOptions: FilterOptions | null }

const SUGGESTIONS = [
  'autonomous vehicle safety',
  'mRNA cancer therapeutics',
  'quantum sensing defense',
  'climate resilient agriculture',
  'AI-powered cybersecurity',
]

// Horizontal filter chips — replaces sidebar entirely
function FilterChips({
  options,
  filters,
  onChange,
}: {
  options: FilterOptions | null
  filters: SearchFilters
  onChange: (f: SearchFilters) => void
}) {
  const set = (patch: Partial<SearchFilters>) => onChange({ ...filters, ...patch })
  const hasAny = Object.values(filters).some(v => v !== undefined)

  const chipBase =
    'inline-flex items-center gap-1.5 text-[12px] font-medium px-3 py-1 rounded-full border transition-colors cursor-pointer select-none whitespace-nowrap'
  const chipOff = 'bg-white text-apple-secondary border-[rgba(0,0,0,0.10)] hover:border-[rgba(0,0,0,0.2)]'
  const chipOn  = 'bg-apple-text text-white border-apple-text'

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Phase toggles */}
      {['Phase I', 'Phase II'].map(p => (
        <button
          key={p}
          className={`${chipBase} ${filters.phase === p ? chipOn : chipOff}`}
          onClick={() => set({ phase: filters.phase === p ? undefined : p })}
        >
          {p}
        </button>
      ))}

      {/* Agency dropdown-chip */}
      <div className="relative">
        <select
          className={`${chipBase} appearance-none pr-6 ${filters.agency ? chipOn : chipOff}`}
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='${filters.agency ? '%23fff' : '%236e6e73'}' d='M5 7L1 3h8z'/%3E%3C/svg%3E")`,
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'right 8px center',
            cursor: 'pointer',
          }}
          value={filters.agency ?? ''}
          onChange={e => set({ agency: e.target.value || undefined })}
        >
          <option value="">Agency</option>
          {options?.agencies.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>

      {/* State dropdown-chip */}
      <div className="relative">
        <select
          className={`${chipBase} appearance-none pr-6 ${filters.state ? chipOn : chipOff}`}
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='${filters.state ? '%23fff' : '%236e6e73'}' d='M5 7L1 3h8z'/%3E%3C/svg%3E")`,
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'right 8px center',
            cursor: 'pointer',
          }}
          value={filters.state ?? ''}
          onChange={e => set({ state: e.target.value || undefined })}
        >
          <option value="">State</option>
          {options?.states.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* Year range inline */}
      <div className={`${chipBase} gap-1.5 ${chipOff}`}>
        <input
          type="number"
          placeholder={String(options?.year_min ?? 1983)}
          className="w-14 bg-transparent text-apple-secondary placeholder-apple-tertiary focus:outline-none"
          value={filters.year_min ?? ''}
          onClick={e => e.stopPropagation()}
          onChange={e => set({ year_min: e.target.value ? Number(e.target.value) : undefined })}
        />
        <span className="text-apple-tertiary">–</span>
        <input
          type="number"
          placeholder={String(options?.year_max ?? 2024)}
          className="w-14 bg-transparent text-apple-secondary placeholder-apple-tertiary focus:outline-none"
          value={filters.year_max ?? ''}
          onClick={e => e.stopPropagation()}
          onChange={e => set({ year_max: e.target.value ? Number(e.target.value) : undefined })}
        />
      </div>

      {hasAny && (
        <button
          className="text-[12px] text-apple-blue hover:underline ml-1"
          onClick={() => onChange({})}
        >
          Clear
        </button>
      )}
    </div>
  )
}

export default function SearchTab({ filterOptions }: Props) {
  const [query,   setQuery]   = useState('')
  const [filters, setFilters] = useState<SearchFilters>({})

  const [synthesis, setSynthesis] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error,     setError]     = useState<string | null>(null)
  const [searched,  setSearched]  = useState(false)

  const cancelRef = useRef<(() => void) | null>(null)

  function cancel() { cancelRef.current?.(); cancelRef.current = null }

  function handleSearch(q = query) {
    if (!q.trim()) return
    setQuery(q)
    cancel()
    setError(null); setSynthesis(''); setSearched(true)
    setStreaming(true)
    cancelRef.current = askStream(
      q, filters, 25,
      ev => {
        if (ev.type === 'text') setSynthesis(s => s + ev.data)
        else if (ev.type === 'done') setStreaming(false)
      },
      err => { setError(err.message); setStreaming(false) },
    )
  }

  const busy = streaming

  return (
    <div className="max-w-5xl mx-auto px-8">

      {/* ── Hero / search area ── */}
      <div className={`transition-all duration-300 ${searched ? 'pt-6 pb-4' : 'pt-20 pb-8'}`}>

        {!searched && (
          <p className="text-[28px] font-semibold text-apple-text tracking-tight text-center mb-8 leading-tight">
            Explore federal innovation funding.
          </p>
        )}

        {/* Search input — floats directly on page bg, no card wrapper */}
        <div className="flex gap-2.5">
          <div className="flex-1 relative">
            <input
              autoFocus
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="Search by concept, technology, or research area…"
              className="w-full text-[15px] bg-white text-apple-text rounded-card px-5 py-3 placeholder-apple-tertiary"
              style={{
                boxShadow: '0 2px 8px rgba(0,0,0,0.09), 0 1px 2px rgba(0,0,0,0.06)',
                border: '1px solid rgba(0,0,0,0.07)',
              }}
            />
          </div>

          <button
            onClick={() => handleSearch()}
            disabled={busy || !query.trim()}
            className="px-5 py-3 bg-apple-blue text-white text-[14px] font-semibold rounded-card hover:bg-apple-bluehover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            style={{ boxShadow: '0 2px 8px rgba(0,113,227,0.4)' }}
          >
            {busy ? '…' : 'Ask Claude'}
          </button>
        </div>

        {/* Filter row */}
        <div className="mt-3 flex items-center gap-4 flex-wrap">
          <FilterChips options={filterOptions} filters={filters} onChange={setFilters} />
        </div>

        {/* Pre-search suggestions */}
        {!searched && (
          <div className="flex flex-wrap gap-2 justify-center mt-10">
            {SUGGESTIONS.map(s => (
              <button
                key={s}
                onClick={() => handleSearch(s)}
                className="text-[13px] bg-white text-apple-secondary px-4 py-2 rounded-full transition-colors hover:text-apple-blue"
                style={{
                  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                  border: '1px solid rgba(0,0,0,0.07)',
                }}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Results area ── */}
      {searched && (
        <div className="pb-16 space-y-4">

          {error && (
            <p className="text-[13px] text-red-500 py-2">{error}</p>
          )}

          {/* Claude synthesis */}
          {(synthesis || streaming) && (
            <div
              className="bg-white rounded-card px-6 py-5"
              style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.07)' }}
            >
              <div className="flex items-center gap-2 mb-3">
                <p className="text-[11px] font-semibold text-apple-tertiary uppercase tracking-widest">
                  Claude's Analysis
                </p>
                {streaming && (
                  <span className="w-1.5 h-1.5 rounded-full bg-apple-blue animate-pulse" />
                )}
              </div>
              <p className="text-[14px] text-apple-text leading-relaxed whitespace-pre-wrap">{synthesis}</p>
            </div>
          )}

          {/* No results */}
          {!streaming && !synthesis && !error && (
            <div className="text-center py-16">
              <p className="text-[14px] text-apple-secondary">No results found</p>
              <p className="text-[13px] text-apple-tertiary mt-1">Try a broader or different query</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
