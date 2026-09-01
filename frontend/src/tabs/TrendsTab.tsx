import { useEffect, useRef, useState } from 'react'
import {
  type FilterOptions, type SearchFilters, type TrendsData,
  fetchTrends, trendAskStream,
} from '../lib/api'

interface Props { filterOptions: FilterOptions | null }

const compact = (n: number) =>
  new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n)

const compactUsd = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 }).format(n)

// ── Inline SVG line chart ─────────────────────────────────────────────────────

function LineChart({ data }: { data: { year: number; total_amount: number }[] }) {
  if (!data.length) return null
  const W = 560, H = 140
  const pad = { t: 8, r: 12, b: 28, l: 52 }
  const iW = W - pad.l - pad.r
  const iH = H - pad.t - pad.b

  const minX = data[0].year, maxX = data[data.length - 1].year
  const maxY = Math.max(...data.map(d => d.total_amount)) * 1.1 || 1

  const x = (yr: number) => pad.l + ((yr - minX) / (maxX - minX || 1)) * iW
  const y = (c: number)  => pad.t + iH - (c / maxY) * iH

  const linePts = data.map(d => `${x(d.year)},${y(d.total_amount)}`).join(' ')
  const areaPts =
    `${x(data[0].year)},${y(0)} ` +
    data.map(d => `${x(d.year)},${y(d.total_amount)}`).join(' ') +
    ` ${x(data[data.length - 1].year)},${y(0)}`

  const yTicks = [0, 0.5, 1].map(t => Math.round(t * maxY))
  // x-axis: show ~6 labels spaced evenly
  const step = Math.ceil(data.length / 6)
  const xLabels = data.filter((_, i) => i % step === 0 || i === data.length - 1)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }}>
      {/* y-axis gridlines */}
      {yTicks.map(v => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)}
            stroke="rgba(0,0,0,0.06)" strokeWidth="1" />
          <text x={pad.l - 6} y={y(v) + 4} textAnchor="end"
            fontSize="10" fill="#aeaeb2">{compactUsd(v)}</text>
        </g>
      ))}
      {/* Area fill */}
      <polygon points={areaPts} fill="#0071e3" fillOpacity="0.06" />
      {/* Line */}
      <polyline points={linePts} fill="none" stroke="#0071e3"
        strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      {/* Dots */}
      {data.map(d => (
        <circle key={d.year} cx={x(d.year)} cy={y(d.total_amount)} r="2.5"
          fill="#fff" stroke="#0071e3" strokeWidth="2" />
      ))}
      {/* x-axis labels */}
      {xLabels.map(d => (
        <text key={d.year} x={x(d.year)} y={H - 6} textAnchor="middle"
          fontSize="10" fill="#aeaeb2">{d.year}</text>
      ))}
    </svg>
  )
}

// ── Horizontal bar chart ──────────────────────────────────────────────────────

function BarChart({ data, valueKey, labelKey, color = '#0071e3' }: {
  data: Record<string, unknown>[]
  valueKey: string
  labelKey: string
  color?: string
}) {
  if (!data.length) return null
  const max = Math.max(...data.map(d => d[valueKey] as number))

  return (
    <div className="space-y-2">
      {data.slice(0, 10).map(row => {
        const val = row[valueKey] as number
        const pct = max > 0 ? (val / max) * 100 : 0
        const label = String(row[labelKey])
        return (
          <div key={label} className="flex items-center gap-3">
            <span
              className="text-[12px] text-apple-secondary shrink-0 text-right w-32 truncate"
              title={label}
            >
              {label}
            </span>
            <div className="flex-1 bg-[#f5f5f7] rounded-full h-4 overflow-hidden">
              <div
                className="h-4 rounded-full transition-all duration-500 flex items-center justify-end pr-2"
                style={{ width: `${Math.max(pct, 4)}%`, backgroundColor: color }}
              >
                <span className="text-white text-[10px] font-semibold">{compact(val)}</span>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── KPI card ─────────────────────────────────────────────────────────────────

function KPI({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="bg-white rounded-card px-5 py-4"
      style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}
    >
      <p className="text-[11px] font-semibold text-apple-tertiary uppercase tracking-wider mb-1">
        {label}
      </p>
      <p className="text-[22px] font-semibold text-apple-text tracking-tight">{value}</p>
    </div>
  )
}

// ── Section card ─────────────────────────────────────────────────────────────

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="bg-white rounded-card p-5"
      style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}
    >
      <p className="text-[13px] font-semibold text-apple-text mb-4">{title}</p>
      {children}
    </div>
  )
}

// ── Spinner ───────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <svg className="animate-spin w-4 h-4 text-apple-tertiary" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeOpacity="0.25"/>
      <path d="M12 2a10 10 0 0110 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/>
    </svg>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function TrendsTab({ filterOptions }: Props) {
  const [trends,  setTrends]  = useState<TrendsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)
  const [filters, setFilters] = useState<SearchFilters>({})

  const [question,  setQuestion]  = useState('')
  const [answer,    setAnswer]    = useState('')
  const [streaming, setStreaming] = useState(false)
  const cancelRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchTrends(filters)
      .then(setTrends)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters)])

  function handleAsk() {
    if (!question.trim()) return
    cancelRef.current?.()
    setAnswer(''); setStreaming(true)
    cancelRef.current = trendAskStream(
      question,
      ev => {
        if (ev.type === 'text') setAnswer(s => s + ev.data)
        else if (ev.type === 'done') setStreaming(false)
      },
      err => { setError(err.message); setStreaming(false) },
    )
  }

  const totalAwards  = trends?.by_year.reduce((s, d) => s + d.count, 0) ?? 0
  const totalFunding = trends?.by_year.reduce((s, d) => s + d.total_amount, 0) ?? 0
  const topAgency    = trends?.by_agency[0]?.agency ?? '—'

  const hasFilters = Object.values(filters).some(Boolean)

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">

      {/* Filter strip */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[12px] font-semibold text-apple-tertiary uppercase tracking-wider">Filter</span>
        <select
          className="text-[13px] bg-white text-apple-text rounded-input px-3 py-1.5"
          style={{ border: '1px solid rgba(0,0,0,0.12)', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}
          value={filters.agency ?? ''}
          onChange={e => setFilters(f => ({ ...f, agency: e.target.value || undefined }))}
        >
          <option value="">All agencies</option>
          {filterOptions?.agencies.map(a => <option key={a} value={a}>{a}</option>)}
        </select>

        {['Phase I', 'Phase II'].map(p => (
          <button
            key={p}
            onClick={() => setFilters(f => ({ ...f, phase: f.phase === p ? undefined : p }))}
            className={`text-[12px] px-3 py-1.5 rounded-btn font-medium transition-colors ${
              filters.phase === p
                ? 'bg-apple-blue text-white'
                : 'bg-white text-apple-secondary'
            }`}
            style={filters.phase !== p ? { border: '1px solid rgba(0,0,0,0.12)' } : {}}
          >
            {p}
          </button>
        ))}

        {hasFilters && (
          <button
            onClick={() => setFilters({})}
            className="text-[12px] text-apple-blue hover:underline"
          >
            Clear
          </button>
        )}
      </div>

      {/* Claude Q&A */}
      <div
        className="bg-white rounded-card p-5 space-y-4"
        style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}
      >
        <div>
          <p className="text-[13px] font-semibold text-apple-text">Ask about SBIR trends</p>
          <p className="text-[12px] text-apple-tertiary mt-0.5">
            Ask about funding shifts, top performers, agency priorities, or any pattern across the data.
          </p>
        </div>

        <div className="flex gap-2.5">
          <input
            type="text"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAsk()}
            placeholder='e.g. "Which agencies have grown the most since 2010?"'
            className="flex-1 text-[14px] bg-[#f5f5f7] text-apple-text rounded-input px-4 py-2.5 placeholder-apple-tertiary"
            style={{ border: '1px solid rgba(0,0,0,0.10)', boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.04)' }}
          />
          <button
            onClick={handleAsk}
            disabled={streaming || !question.trim()}
            className="px-5 py-2.5 bg-apple-blue text-white text-[13px] font-semibold rounded-btn hover:bg-apple-bluehover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            style={{ boxShadow: '0 1px 3px rgba(0,113,227,0.35)' }}
          >
            {streaming ? '…' : 'Ask'}
          </button>
        </div>

        {(answer || streaming) && (
          <div style={{ borderTop: '1px solid rgba(0,0,0,0.06)' }} className="pt-4">
            <div className="flex items-center gap-2 mb-2">
              <p className="text-[11px] font-semibold text-apple-tertiary uppercase tracking-wider">
                Claude
              </p>
              {streaming && <span className="w-1.5 h-1.5 rounded-full bg-apple-blue animate-pulse" />}
            </div>
            <p className="text-[14px] text-apple-text leading-relaxed whitespace-pre-wrap">{answer}</p>
          </div>
        )}
      </div>

      {error && (
        <div
          className="bg-white rounded-card px-5 py-4 text-[13px] text-red-500"
          style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}
        >
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2.5 py-4 text-[13px] text-apple-tertiary">
          <Spinner /> Loading trends…
        </div>
      )}

      {trends && !loading && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-3 gap-4">
            <KPI label="Total Awards" value={compact(totalAwards)} />
            <KPI label="Total Funding" value={compactUsd(totalFunding)} />
            <KPI label="Top Agency" value={topAgency.split(' ').slice(-2).join(' ')} />
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-2 gap-4">
            <Card title="Funding Over Time">
              <div className="col-span-2">
                <LineChart data={trends.by_year} />
              </div>
            </Card>

            <Card title="By Phase">
              <BarChart
                data={trends.by_phase}
                valueKey="count"
                labelKey="phase"
                color="#0071e3"
              />
            </Card>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Card title="Awards by Agency">
              <BarChart
                data={trends.by_agency}
                valueKey="count"
                labelKey="agency"
                color="#0071e3"
              />
            </Card>

            <Card title="Top States">
              <BarChart
                data={trends.top_states}
                valueKey="count"
                labelKey="state"
                color="#34c759"
              />
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
