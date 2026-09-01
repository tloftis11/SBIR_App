import { useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  type AcquisitionCriteria,
  type CompanyTarget,
  acquisitionTargetsStream,
} from '../lib/api'

// ── Static option lists ───────────────────────────────────────────────────────

const DOMAIN_OPTIONS = [
  // Defense & national security
  'Air domain (UAV/UAS, aircraft, missiles)',
  'Maritime (surface, subsurface, autonomous)',
  'Land / ground systems (armored, robotics)',
  'Space (launch, on-orbit, PNT, SATCOM)',
  'Cyber / electronic warfare / signals',
  'C3 / command, control & communications',
  'ISR / sensor fusion / surveillance',
  // Civilian / health / science
  'Healthcare / medical devices / diagnostics',
  'Biodefense / CBRN / public health',
  'Agriculture / food security / environment',
  'Energy, power & propulsion',
  'Transportation / autonomous systems',
  'Climate / sustainability / clean tech',
  'Dual-use / commercial-defense crossover',
]

const AGENCY_OPTIONS = [
  // DOD
  'Air Force', 'Army', 'Navy', 'DARPA', 'MDA', 'SOCOM', 'OSD', 'DLA',
  // Civilian / other
  'HHS', 'NSF', 'DOE', 'NASA', 'DHS', 'USDA', 'DOT', 'EPA', 'NGA', 'DOC',
]

const RATIONALE_OPTIONS = [
  'Expand government customer relationships',
  'Acquire Phase II pipeline / near-term contract revenue',
  'Gain technical IP or patented technology',
  'Access specialized talent / technical team',
  'Enter a new domain or market',
  'Strengthen AI / software capabilities',
  'Accelerate internal R&D programs',
  'Enter federal health / civilian market',
  'Geographic market expansion',
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(0)}K`
  return `$${n}`
}

function confidenceColor(c?: string) {
  if (c === 'high')   return 'text-green-600'
  if (c === 'medium') return 'text-amber-600'
  return 'text-apple-secondary'
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MultiCheck({
  label, options, selected, onChange,
}: {
  label: string
  options: string[]
  selected: string[]
  onChange: (v: string[]) => void
}) {
  const toggle = (opt: string) =>
    onChange(selected.includes(opt) ? selected.filter(x => x !== opt) : [...selected, opt])
  return (
    <div>
      <p className="text-[13px] font-medium text-apple-text mb-2">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map(opt => (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={`px-3 py-1 rounded-full text-[12px] font-medium border transition-all ${
              selected.includes(opt)
                ? 'bg-[#0071e3] text-white border-[#0071e3]'
                : 'bg-white text-apple-secondary border-[rgba(0,0,0,0.12)] hover:border-[rgba(0,0,0,0.25)]'
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  )
}

function TargetCard({ company }: { company: CompanyTarget }) {
  const [open, setOpen] = useState(false)
  const funding = company.total_funding ? fmt(company.total_funding) : 'N/A'
  const years   = company.year_first && company.year_last
    ? `${company.year_first}–${company.year_last}`
    : company.year_last ?? '—'

  return (
    <div
      className="rounded-xl border border-[rgba(0,0,0,0.08)] bg-white p-4 cursor-pointer hover:shadow-sm transition-shadow"
      onClick={() => setOpen(o => !o)}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-[14px] font-semibold text-apple-text truncate">{company.firm}</p>
          <p className="text-[12px] text-apple-secondary mt-0.5">
            {company.state && <span className="mr-2">{company.state}</span>}
            {company.primary_agency && <span>{company.primary_agency}</span>}
          </p>
        </div>
        {/* Revenue badge */}
        {company.revenue_estimate && company.revenue_estimate !== 'unknown' && (
          <span className="shrink-0 text-[11px] font-medium bg-[rgba(0,0,0,0.05)] text-apple-text px-2 py-0.5 rounded-full">
            {company.revenue_estimate}
          </span>
        )}
      </div>

      {/* Metrics row */}
      <div className="mt-3 flex flex-wrap gap-3">
        {[
          ['Awards', `${company.award_count}`],
          ['Phase II', `${company.phase_2_rate}%`],
          ['Total Funding', funding],
          ['Active', `${years}`],
        ].map(([lbl, val]) => (
          <div key={lbl} className="flex flex-col">
            <span className="text-[10px] text-apple-secondary uppercase tracking-wide">{lbl}</span>
            <span className="text-[13px] font-medium text-apple-text">{val}</span>
          </div>
        ))}
      </div>

      {/* Recent news (always shown) */}
      {company.recent_news && company.recent_news !== 'No information found.' && (
        <p className="mt-3 text-[12px] text-apple-secondary leading-relaxed border-t border-[rgba(0,0,0,0.06)] pt-3">
          {company.recent_news}
        </p>
      )}

      {/* Expanded: employee count + confidence */}
      {open && (
        <div className="mt-2 pt-2 border-t border-[rgba(0,0,0,0.06)] flex items-center gap-4">
          {company.employee_count && (
            <span className="text-[12px] text-apple-secondary">~{company.employee_count} employees</span>
          )}
          <span className={`text-[11px] font-medium ${confidenceColor(company.web_confidence)}`}>
            Web confidence: {company.web_confidence ?? 'low'}
          </span>
        </div>
      )}
    </div>
  )
}

function AcquiredCard({ company }: { company: CompanyTarget }) {
  return (
    <div className="rounded-xl border border-[rgba(0,0,0,0.08)] bg-[rgba(0,0,0,0.02)] p-4 opacity-75">
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-semibold text-apple-text truncate line-through">
            {company.firm}
          </p>
          <p className="text-[12px] text-apple-secondary mt-0.5">
            Acquired by <span className="font-medium text-apple-text">{company.acquirer ?? 'unknown acquirer'}</span>
            {company.acquisition_year ? ` (${company.acquisition_year})` : ''}
          </p>
        </div>
        <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
          Acquired
        </span>
      </div>
      <div className="mt-2 flex gap-3">
        <span className="text-[11px] text-apple-secondary">{company.award_count} awards</span>
        <span className="text-[11px] text-apple-secondary">{company.phase_2_rate}% Phase II</span>
        {company.primary_agency && (
          <span className="text-[11px] text-apple-secondary">{company.primary_agency}</span>
        )}
      </div>
    </div>
  )
}

// ── Main tab ──────────────────────────────────────────────────────────────────

type Phase = 'form' | 'searching' | 'results'

export default function AcquisitionTargetsTab() {
  const [phase, setPhase] = useState<Phase>('form')

  // Form state
  const [criteria, setCriteria] = useState<AcquisitionCriteria>({
    domains: [],
    technology_query: '',
    agencies: [],
    company_profile: 'either',
    rationale: [],
    open_criteria: '',
  })

  // Results state
  const [progressMsg,  setProgressMsg]  = useState('')
  const [progressPct,  setProgressPct]  = useState(0)
  const [synthesis,    setSynthesis]    = useState('')
  const [targets,      setTargets]      = useState<CompanyTarget[]>([])
  const [acquiredList, setAcquiredList] = useState<CompanyTarget[]>([])
  const [error,        setError]        = useState('')

  const cancelRef = useRef<() => void>(() => {})

  function reset() {
    cancelRef.current()
    setPhase('form')
    setProgressMsg('')
    setProgressPct(0)
    setSynthesis('')
    setTargets([])
    setAcquiredList([])
    setError('')
  }

  function handleSubmit() {
    if (!criteria.technology_query.trim() && criteria.domains.length === 0) return

    setPhase('searching')
    setProgressMsg('Starting search…')
    setProgressPct(0)
    setSynthesis('')
    setTargets([])
    setAcquiredList([])
    setError('')

    const cancel = acquisitionTargetsStream(
      criteria,
      (ev) => {
        if (ev.type === 'progress') {
          setProgressMsg(ev.data.message)
          setProgressPct(
            ev.data.total > 0
              ? Math.round((ev.data.current / ev.data.total) * 100)
              : 0
          )
        } else if (ev.type === 'targets') {
          setTargets(ev.data)
        } else if (ev.type === 'acquired') {
          setAcquiredList(ev.data)
        } else if (ev.type === 'text') {
          setSynthesis(prev => prev + ev.data)
        } else if (ev.type === 'done') {
          setPhase('results')
        }
      },
      (err) => {
        setError(err.message)
        setPhase('results')
      }
    )
    cancelRef.current = cancel
  }

  // ── Form view ────────────────────────────────────────────────────────────────

  if (phase === 'form') {
    return (
      <div className="max-w-3xl mx-auto px-8 py-8">
        <div className="mb-8">
          <h1 className="text-[22px] font-semibold text-apple-text tracking-tight">
            Potential Acquisition Targets
          </h1>
          <p className="mt-1 text-[13px] text-apple-secondary leading-relaxed">
            Experimental · Identify SBIR companies that match your acquisition criteria across
            defense, health, energy, and other federal R&amp;D markets. Claude researches each
            candidate and generates a strategic analysis.
          </p>
        </div>

        <div className="space-y-8">
          {/* Q1: Domains */}
          <MultiCheck
            label="1. Which end markets are you targeting?"
            options={DOMAIN_OPTIONS}
            selected={criteria.domains}
            onChange={v => setCriteria(c => ({ ...c, domains: v }))}
          />

          {/* Q2: Technology focus */}
          <div>
            <label className="text-[13px] font-medium text-apple-text block mb-2">
              2. Describe the specific technologies or capabilities you are seeking
              <span className="text-apple-secondary font-normal ml-1">(required)</span>
            </label>
            <textarea
              value={criteria.technology_query}
              onChange={e => setCriteria(c => ({ ...c, technology_query: e.target.value }))}
              placeholder="e.g. autonomous underwater vehicle sensors, AI-based target recognition, directed energy systems…"
              rows={3}
              className="w-full rounded-xl border border-[rgba(0,0,0,0.12)] bg-white px-4 py-3
                text-[13px] text-apple-text placeholder-apple-secondary resize-none
                focus:outline-none focus:ring-2 focus:ring-[#0071e3]/40 focus:border-[#0071e3]"
            />
          </div>

          {/* Q3: Agency relationships */}
          <MultiCheck
            label="3. Which agency customer relationships are you prioritizing?"
            options={AGENCY_OPTIONS}
            selected={criteria.agencies}
            onChange={v => setCriteria(c => ({ ...c, agencies: v }))}
          />

          {/* Q4: Company profile */}
          <div>
            <p className="text-[13px] font-medium text-apple-text mb-2">
              4. What company profile are you looking for?
            </p>
            <div className="flex gap-2 flex-wrap">
              {(['specialist', 'platform', 'either'] as const).map(opt => {
                const labels: Record<string, string> = {
                  specialist: 'Technology specialist — narrow, deep expertise',
                  platform: 'Platform integrator — broad, multi-domain capabilities',
                  either: 'Either / open to both',
                }
                return (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setCriteria(c => ({ ...c, company_profile: opt }))}
                    className={`px-3 py-1.5 rounded-full text-[12px] font-medium border transition-all ${
                      criteria.company_profile === opt
                        ? 'bg-[#0071e3] text-white border-[#0071e3]'
                        : 'bg-white text-apple-secondary border-[rgba(0,0,0,0.12)] hover:border-[rgba(0,0,0,0.25)]'
                    }`}
                  >
                    {labels[opt]}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Q5: Strategic rationale */}
          <MultiCheck
            label="5. What is driving your acquisition interest?"
            options={RATIONALE_OPTIONS}
            selected={criteria.rationale}
            onChange={v => setCriteria(c => ({ ...c, rationale: v }))}
          />

          {/* Q6: Open-ended criteria */}
          <div>
            <label className="text-[13px] font-medium text-apple-text block mb-2">
              6. Any other requirements or context for Claude to consider
              <span className="text-apple-secondary font-normal ml-1">(optional)</span>
            </label>
            <textarea
              value={criteria.open_criteria}
              onChange={e => setCriteria(c => ({ ...c, open_criteria: e.target.value }))}
              placeholder="e.g. must have cleared personnel, prefer companies outside of CONUS, avoid overlapping with existing portfolio…"
              rows={2}
              className="w-full rounded-xl border border-[rgba(0,0,0,0.12)] bg-white px-4 py-3
                text-[13px] text-apple-text placeholder-apple-secondary resize-none
                focus:outline-none focus:ring-2 focus:ring-[#0071e3]/40 focus:border-[#0071e3]"
            />
          </div>

          {/* Submit */}
          <button
            type="button"
            disabled={!criteria.technology_query.trim() && criteria.domains.length === 0}
            onClick={handleSubmit}
            className="px-6 py-2.5 rounded-xl bg-[#0071e3] text-white text-[14px] font-medium
              hover:bg-[#0077ed] active:bg-[#006ddb] transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Find Acquisition Targets
          </button>
        </div>
      </div>
    )
  }

  // ── Searching / Results view ─────────────────────────────────────────────────

  const isSearching = phase === 'searching'

  return (
    <div className="max-w-3xl mx-auto px-8 py-8">
      {/* Header + reset */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-[22px] font-semibold text-apple-text tracking-tight">
          Potential Acquisition Targets
          <span className="ml-2 text-[12px] font-medium text-apple-secondary">Experimental</span>
        </h1>
        <button
          type="button"
          onClick={reset}
          className="text-[13px] text-[#0071e3] hover:underline"
        >
          ← New search
        </button>
      </div>

      {/* Progress bar */}
      {isSearching && (
        <div className="mb-6 rounded-xl border border-[rgba(0,0,0,0.08)] bg-white p-4">
          <p className="text-[13px] text-apple-secondary mb-3">{progressMsg}</p>
          <div className="h-1.5 rounded-full bg-[rgba(0,0,0,0.06)] overflow-hidden">
            <div
              className="h-full rounded-full bg-[#0071e3] transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          {progressPct > 0 && (
            <p className="mt-1.5 text-[11px] text-apple-secondary text-right">{progressPct}%</p>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-6 rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-[13px] text-red-700">
          <p className="font-medium">Search failed</p>
          <p className="mt-0.5 opacity-75">{error}</p>
          {progressMsg && (
            <p className="mt-1 opacity-60 text-[11px]">Last status: {progressMsg}</p>
          )}
        </div>
      )}

      {/* No results */}
      {!isSearching && !error && targets.length === 0 && acquiredList.length === 0 && !synthesis && (
        <div className="mb-6 rounded-xl border border-[rgba(0,0,0,0.08)] bg-white px-5 py-8 text-center">
          <p className="text-[14px] text-apple-secondary">
            No candidates found matching your criteria.
          </p>
          <p className="mt-1 text-[12px] text-apple-secondary opacity-60">
            Try broadening your technology description or removing agency filters.
          </p>
        </div>
      )}

      {/* Top 5 target cards */}
      {targets.length > 0 && (
        <section className="mb-8">
          <h2 className="text-[15px] font-semibold text-apple-text mb-3">
            Top Acquisition Targets
          </h2>
          <div className="space-y-3">
            {targets.map(c => <TargetCard key={c.firm} company={c} />)}
          </div>
        </section>
      )}

      {/* Claude strategic analysis */}
      {(synthesis || isSearching) && (
        <section className="mb-8">
          <h2 className="text-[15px] font-semibold text-apple-text mb-3">
            Strategic Analysis
          </h2>
          <div className="rounded-xl border border-[rgba(0,0,0,0.08)] bg-white p-5">
            {synthesis ? (
              <div className="prose prose-sm max-w-none text-apple-text">
                <ReactMarkdown>{synthesis}</ReactMarkdown>
              </div>
            ) : (
              <p className="text-[13px] text-apple-secondary italic">Generating analysis…</p>
            )}
          </div>
        </section>
      )}

      {/* Already acquired section */}
      {acquiredList.length > 0 && (
        <section>
          <h2 className="text-[15px] font-semibold text-apple-text mb-1">
            Already Acquired
          </h2>
          <p className="text-[12px] text-apple-secondary mb-3">
            These companies matched your criteria but have already been acquired.
          </p>
          <div className="space-y-2">
            {acquiredList.map(c => <AcquiredCard key={c.firm} company={c} />)}
          </div>
        </section>
      )}
    </div>
  )
}
