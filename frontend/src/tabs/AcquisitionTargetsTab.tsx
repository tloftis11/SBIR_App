import { useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  type AcquisitionCriteria,
  type CompanyTarget,
  type CompanyAward,
  acquisitionTargetsStream,
  fetchCompanyAwards,
} from '../lib/api'

// ── Static option lists ───────────────────────────────────────────────────────

const DOMAIN_OPTIONS = [
  'Air domain (UAV/UAS, aircraft, missiles)',
  'Maritime (surface, subsurface, autonomous)',
  'Land / ground systems (armored, robotics)',
  'Space (launch, on-orbit, PNT, SATCOM)',
  'Cyber / electronic warfare / signals',
  'C3 / command, control & communications',
  'ISR / sensor fusion / surveillance',
  'Healthcare / medical devices / diagnostics',
  'Biodefense / CBRN / public health',
  'Agriculture / food security / environment',
  'Energy, power & propulsion',
  'Transportation / autonomous systems',
  'Climate / sustainability / clean tech',
  'Dual-use / commercial-defense crossover',
]

const AGENCY_OPTIONS = [
  'Air Force', 'Army', 'Navy', 'DARPA', 'MDA', 'SOCOM', 'OSD', 'DLA',
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

const STEP_LABELS = [
  'Database search',
  'Loading candidates',
  'Fetching portfolios',
  'Online research & analysis',
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(0)}K`
  return `$${n}`
}

function phaseColor(phase?: string) {
  if (!phase) return 'bg-gray-100 text-gray-600'
  const p = phase.toUpperCase()
  if (p.includes('II')) return 'bg-blue-50 text-blue-700'
  return 'bg-green-50 text-green-700'
}

// ── Spinner ───────────────────────────────────────────────────────────────────

function Spinner({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 14 14"
      className="animate-spin shrink-0"
      style={{ animationDuration: '0.75s' }}
    >
      <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.5"
        strokeDasharray="24" strokeDashoffset="8" strokeLinecap="round" opacity="0.3" />
      <path d="M7 1.5A5.5 5.5 0 0 1 12.5 7" fill="none" stroke="currentColor" strokeWidth="1.5"
        strokeLinecap="round" />
    </svg>
  )
}

// ── Step tracker ─────────────────────────────────────────────────────────────

function StepTracker({ step }: { step: number }) {
  return (
    <div className="flex items-center gap-1 mt-3">
      {STEP_LABELS.map((label, i) => {
        const idx = i + 1
        const done    = idx < step
        const current = idx === step
        return (
          <div key={label} className="flex items-center gap-1">
            <div className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-all ${
              done    ? 'bg-[#0071e3] text-white'
              : current ? 'bg-[#0071e3]/10 text-[#0071e3] ring-1 ring-[#0071e3]/30'
              : 'bg-[rgba(0,0,0,0.04)] text-apple-secondary'
            }`}>
              {current && <Spinner size={9} />}
              {done && <svg width="9" height="9" viewBox="0 0 9 9" className="shrink-0">
                <path d="M1.5 4.5 3.5 6.5 7.5 2.5" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>}
              {label}
            </div>
            {i < STEP_LABELS.length - 1 && (
              <div className={`h-px w-3 ${done ? 'bg-[#0071e3]' : 'bg-[rgba(0,0,0,0.1)]'}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Portfolio list ─────────────────────────────────────────────────────────────

function AwardRow({ award }: { award: CompanyAward }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-[rgba(0,0,0,0.05)] last:border-0 py-2.5">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full text-left"
      >
        <div className="flex items-start gap-2">
          <span className={`shrink-0 mt-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded ${phaseColor(award.phase)}`}>
            {award.phase || 'N/A'}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-[12px] font-medium text-apple-text leading-snug line-clamp-2">
              {award.title || 'Untitled'}
            </p>
            <p className="text-[11px] text-apple-secondary mt-0.5">
              {[award.agency, award.award_year, award.award_amount ? fmt(award.award_amount) : null]
                .filter(Boolean).join(' · ')}
            </p>
          </div>
          <svg
            width="12" height="12" viewBox="0 0 12 12" className={`shrink-0 mt-1 text-apple-secondary transition-transform ${open ? 'rotate-180' : ''}`}
          >
            <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </button>
      {open && award.abstract && (
        <p className="mt-2 ml-9 text-[11px] text-apple-secondary leading-relaxed">
          {award.abstract}
        </p>
      )}
    </div>
  )
}

// ── TargetCard ────────────────────────────────────────────────────────────────

function TargetCard({ company, isSearching }: { company: CompanyTarget; isSearching: boolean }) {
  const [expanded,     setExpanded]     = useState(false)
  const [awards,       setAwards]       = useState<CompanyAward[] | null>(null)
  const [loadingPf,    setLoadingPf]    = useState(false)

  const funding = company.total_funding ? fmt(company.total_funding) : 'N/A'
  const years   = company.year_first && company.year_last
    ? `${company.year_first}–${company.year_last}`
    : company.year_last ? `–${company.year_last}` : '—'

  async function togglePortfolio() {
    if (!expanded && awards === null) {
      setLoadingPf(true)
      try {
        const data = await fetchCompanyAwards(company.firm)
        const sorted = [...data].sort((a, b) => (b.award_year ?? 0) - (a.award_year ?? 0))
        setAwards(sorted)
      } catch {
        setAwards([])
      } finally {
        setLoadingPf(false)
      }
    }
    setExpanded(e => !e)
  }

  return (
    <div
      className={`rounded-xl border bg-white transition-all duration-300 ${
        isSearching ? 'border-[rgba(0,0,0,0.08)]' : 'border-[rgba(0,0,0,0.1)] shadow-sm'
      }`}
    >
      <div className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[14px] font-semibold text-apple-text">{company.firm}</p>
            {(company.state || company.primary_agency) && (
              <p className="text-[12px] text-apple-secondary mt-0.5">
                {[company.state, company.primary_agency].filter(Boolean).join(' · ')}
              </p>
            )}
          </div>
          <span className="shrink-0 text-[10px] font-semibold text-apple-secondary bg-[rgba(0,0,0,0.04)] px-2 py-0.5 rounded-full">
            score {company.fit_score}
          </span>
        </div>

        {/* SBIR metrics */}
        <div className="mt-3 flex flex-wrap gap-4">
          {([
            ['Awards', `${company.award_count}`],
            ['Phase II', `${company.phase_2_rate}%`],
            ['SBIR Funding', funding],
            ['Active', years],
          ] as [string, string][]).map(([lbl, val]) => (
            <div key={lbl} className="flex flex-col">
              <span className="text-[10px] text-apple-secondary uppercase tracking-wide leading-tight">{lbl}</span>
              <span className="text-[13px] font-medium text-apple-text">{val}</span>
            </div>
          ))}
        </div>

        {/* Portfolio toggle */}
        <button
          type="button"
          onClick={togglePortfolio}
          className="mt-3 flex items-center gap-1.5 text-[12px] text-[#0071e3] hover:underline"
        >
          {loadingPf ? (
            <><Spinner size={11} /> Loading portfolio…</>
          ) : expanded ? (
            <>
              <svg width="11" height="11" viewBox="0 0 11 11"><path d="M1 7l4.5-4.5L10 7" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
              Hide SBIR portfolio
            </>
          ) : (
            <>
              <svg width="11" height="11" viewBox="0 0 11 11"><path d="M1 4l4.5 4.5L10 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
              View SBIR portfolio ({company.award_count} awards)
            </>
          )}
        </button>
      </div>

      {/* Portfolio panel */}
      {expanded && awards !== null && (
        <div className="border-t border-[rgba(0,0,0,0.06)] px-4 pb-2 max-h-72 overflow-y-auto">
          {awards.length === 0 ? (
            <p className="py-4 text-[12px] text-apple-secondary text-center">No awards found.</p>
          ) : (
            awards.map(a => <AwardRow key={a.id} award={a} />)
          )}
        </div>
      )}
    </div>
  )
}

// ── AcquiredCard ──────────────────────────────────────────────────────────────

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

// ── Form components ────────────────────────────────────────────────────────────

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

// ── Main tab ──────────────────────────────────────────────────────────────────

type Phase = 'form' | 'searching' | 'results'

export default function AcquisitionTargetsTab() {
  const [phase, setPhase] = useState<Phase>('form')

  const [criteria, setCriteria] = useState<AcquisitionCriteria>({
    domains: [],
    technology_query: '',
    agencies: [],
    company_profile: 'either',
    rationale: [],
    open_criteria: '',
  })

  const [progressMsg,  setProgressMsg]  = useState('')
  const [progressStep, setProgressStep] = useState(1)
  const [synthesis,    setSynthesis]    = useState('')
  const [targets,      setTargets]      = useState<CompanyTarget[]>([])
  const [acquiredList, setAcquiredList] = useState<CompanyTarget[]>([])
  const [error,        setError]        = useState('')

  const cancelRef = useRef<() => void>(() => {})

  function reset() {
    cancelRef.current()
    setPhase('form')
    setProgressMsg('')
    setProgressStep(1)
    setSynthesis('')
    setTargets([])
    setAcquiredList([])
    setError('')
  }

  function handleSubmit() {
    if (!criteria.technology_query.trim() && criteria.domains.length === 0) return

    setPhase('searching')
    setProgressMsg('Starting search…')
    setProgressStep(1)
    setSynthesis('')
    setTargets([])
    setAcquiredList([])
    setError('')

    const cancel = acquisitionTargetsStream(
      criteria,
      (ev) => {
        if (ev.type === 'progress') {
          setProgressMsg(ev.data.message)
          if (ev.data.step) setProgressStep(ev.data.step)
        } else if (ev.type === 'company') {
          if (ev.data.already_acquired) {
            setAcquiredList(prev => [...prev, ev.data])
          } else {
            setTargets(prev => [...prev, ev.data])
          }
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

  const isSearching = phase === 'searching'

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
            candidate online and generates a strategic analysis.
          </p>
        </div>

        <div className="space-y-8">
          <MultiCheck
            label="1. Which end markets are you targeting?"
            options={DOMAIN_OPTIONS}
            selected={criteria.domains}
            onChange={v => setCriteria(c => ({ ...c, domains: v }))}
          />

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

          <MultiCheck
            label="3. Which agency customer relationships are you prioritizing?"
            options={AGENCY_OPTIONS}
            selected={criteria.agencies}
            onChange={v => setCriteria(c => ({ ...c, agencies: v }))}
          />

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

          <MultiCheck
            label="5. What is driving your acquisition interest?"
            options={RATIONALE_OPTIONS}
            selected={criteria.rationale}
            onChange={v => setCriteria(c => ({ ...c, rationale: v }))}
          />

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

  return (
    <div className="max-w-3xl mx-auto px-8 py-8">
      {/* Header + reset */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-[22px] font-semibold text-apple-text tracking-tight">
          Potential Acquisition Targets
          <span className="ml-2 text-[12px] font-medium text-apple-secondary">Experimental</span>
        </h1>
        <button type="button" onClick={reset} className="text-[13px] text-[#0071e3] hover:underline">
          ← New search
        </button>
      </div>

      {/* Progress panel */}
      {isSearching && (
        <div className="mb-6 rounded-xl border border-[rgba(0,0,0,0.08)] bg-white p-4">
          <div className="flex items-center gap-2">
            <Spinner size={14} />
            <p className="text-[13px] text-apple-secondary">{progressMsg || 'Starting…'}</p>
          </div>
          <StepTracker step={progressStep} />
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
          <p className="text-[14px] text-apple-secondary">No candidates found.</p>
          {progressMsg ? (
            <p className="mt-1 text-[12px] text-apple-secondary opacity-70 max-w-sm mx-auto">{progressMsg}</p>
          ) : (
            <p className="mt-1 text-[12px] text-apple-secondary opacity-60">
              Try broadening your technology description or removing agency filters.
            </p>
          )}
        </div>
      )}

      {/* Target cards */}
      {targets.length > 0 && (
        <section className="mb-8">
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-[15px] font-semibold text-apple-text">
              Acquisition Targets
            </h2>
            {isSearching && targets.length > 0 && (
              <span className="flex items-center gap-1 text-[11px] text-apple-secondary">
                <Spinner size={10} /> loading
              </span>
            )}
          </div>
          <div className="space-y-3">
            {[...targets]
              .sort((a, b) => b.fit_score - a.fit_score)
              .map(c => <TargetCard key={c.firm} company={c} isSearching={isSearching} />)}
          </div>
        </section>
      )}

      {/* Strategic analysis */}
      {(synthesis || isSearching) && (
        <section className="mb-8">
          <h2 className="text-[15px] font-semibold text-apple-text mb-3">Strategic Analysis</h2>
          <div className="rounded-xl border border-[rgba(0,0,0,0.08)] bg-white p-5">
            {synthesis ? (
              <div className="prose prose-sm max-w-none text-apple-text">
                <ReactMarkdown>{synthesis}</ReactMarkdown>
              </div>
            ) : (
              <div className="flex flex-col gap-2.5 py-2">
                <div className="flex items-center gap-2 text-[13px] text-apple-secondary">
                  <Spinner size={13} />
                  <span>Claude is researching each company online…</span>
                </div>
                {/* Pulsing placeholder lines */}
                {[90, 75, 85, 60].map((w, i) => (
                  <div
                    key={i}
                    className="h-2.5 rounded-full bg-[rgba(0,0,0,0.06)] animate-pulse"
                    style={{ width: `${w}%`, animationDelay: `${i * 150}ms` }}
                  />
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Already acquired */}
      {acquiredList.length > 0 && (
        <section>
          <h2 className="text-[15px] font-semibold text-apple-text mb-1">Already Acquired</h2>
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
