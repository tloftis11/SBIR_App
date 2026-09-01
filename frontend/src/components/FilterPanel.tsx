import type { FilterOptions, SearchFilters } from '../lib/api'

interface Props {
  options: FilterOptions | null
  filters: SearchFilters
  onChange: (f: SearchFilters) => void
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold text-apple-tertiary uppercase tracking-wider mb-1.5">
      {children}
    </p>
  )
}

export default function FilterPanel({ options, filters, onChange }: Props) {
  const set = (patch: Partial<SearchFilters>) => onChange({ ...filters, ...patch })
  const hasFilters = Object.values(filters).some(v => v !== undefined)

  return (
    <aside className="w-48 shrink-0 space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-[13px] font-semibold text-apple-text">Filters</p>
        {hasFilters && (
          <button
            onClick={() => onChange({})}
            className="text-[12px] text-apple-blue hover:underline"
          >
            Clear
          </button>
        )}
      </div>

      {/* Agency */}
      <div>
        <Label>Agency</Label>
        <select
          className="w-full text-[13px] bg-white text-apple-text rounded-input px-3 py-2"
          style={{ border: '1px solid rgba(0,0,0,0.12)', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}
          value={filters.agency ?? ''}
          onChange={e => set({ agency: e.target.value || undefined })}
        >
          <option value="">All agencies</option>
          {options?.agencies.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>

      {/* Phase */}
      <div>
        <Label>Phase</Label>
        <div className="flex gap-2">
          {['Phase I', 'Phase II'].map(p => (
            <button
              key={p}
              onClick={() => set({ phase: filters.phase === p ? undefined : p })}
              className={`flex-1 text-[12px] py-1.5 rounded-lg font-medium transition-colors ${
                filters.phase === p
                  ? 'bg-apple-blue text-white'
                  : 'bg-white text-apple-secondary'
              }`}
              style={filters.phase !== p ? { border: '1px solid rgba(0,0,0,0.12)' } : {}}
            >
              {p.replace('Phase ', 'Ph ')}
            </button>
          ))}
        </div>
      </div>

      {/* Year range */}
      <div>
        <Label>Year range</Label>
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            placeholder={String(options?.year_min ?? 1983)}
            className="w-full text-[13px] bg-white text-apple-text rounded-input px-3 py-2 placeholder-apple-tertiary"
            style={{ border: '1px solid rgba(0,0,0,0.12)', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}
            value={filters.year_min ?? ''}
            onChange={e => set({ year_min: e.target.value ? Number(e.target.value) : undefined })}
          />
          <span className="text-apple-tertiary text-[12px] shrink-0">–</span>
          <input
            type="number"
            placeholder={String(options?.year_max ?? 2024)}
            className="w-full text-[13px] bg-white text-apple-text rounded-input px-3 py-2 placeholder-apple-tertiary"
            style={{ border: '1px solid rgba(0,0,0,0.12)', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}
            value={filters.year_max ?? ''}
            onChange={e => set({ year_max: e.target.value ? Number(e.target.value) : undefined })}
          />
        </div>
      </div>

      {/* State */}
      <div>
        <Label>State</Label>
        <select
          className="w-full text-[13px] bg-white text-apple-text rounded-input px-3 py-2"
          style={{ border: '1px solid rgba(0,0,0,0.12)', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}
          value={filters.state ?? ''}
          onChange={e => set({ state: e.target.value || undefined })}
        >
          <option value="">All states</option>
          {options?.states.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
    </aside>
  )
}
