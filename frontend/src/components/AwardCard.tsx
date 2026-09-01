import { useState } from 'react'
import type { AwardResult } from '../lib/api'

interface Props { award: AwardResult }

const usd = (n: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD',
    notation: 'compact', maximumFractionDigits: 1,
  }).format(n)

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="14" height="14" viewBox="0 0 14 14" fill="none"
      className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      style={{ color: '#aeaeb2' }}
    >
      <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.5"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function Dot() {
  return <span style={{ color: '#d1d1d6', fontSize: 10 }}>·</span>
}

export default function AwardCard({ award }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div
      className="bg-white rounded-card overflow-hidden cursor-pointer select-none"
      style={{
        boxShadow: open
          ? '0 4px 16px rgba(0,0,0,0.09), 0 1px 3px rgba(0,0,0,0.06)'
          : '0 1px 3px rgba(0,0,0,0.07)',
        transition: 'box-shadow 0.15s ease',
      }}
      onClick={() => setOpen(v => !v)}
    >
      <div className="px-6 py-5 flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0 space-y-1.5">
          {/* Title — the anchor */}
          <p className="text-[14px] font-semibold text-apple-text leading-snug">
            {award.title ?? 'Untitled Award'}
          </p>

          {/* Company — prominent, dark, not blue (blue = interactive only) */}
          {award.firm && (
            <p className="text-[13px] font-semibold text-apple-text opacity-70">
              {award.firm}
            </p>
          )}

          {/* Metadata — tight, secondary */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            {award.agency && (
              <span className="text-[12px] text-apple-secondary">{award.agency}</span>
            )}
            {award.phase && <><Dot /><span className="text-[12px] text-apple-secondary">{award.phase}</span></>}
            {award.award_year && <><Dot /><span className="text-[12px] text-apple-secondary">{award.award_year}</span></>}
            {award.state_code && <><Dot /><span className="text-[12px] text-apple-tertiary">{award.state_code}</span></>}
            {award.award_amount != null && (
              <><Dot /><span className="text-[12px] font-medium text-apple-secondary">{usd(award.award_amount)}</span></>
            )}
          </div>
        </div>

        {/* Right side: match score + chevron */}
        <div className="flex items-center gap-2 shrink-0 pt-0.5">
          <span className="text-[12px] font-medium tabular-nums text-apple-tertiary">
            {Math.round(award.similarity * 100)}%
          </span>
          <Chevron open={open} />
        </div>
      </div>

      {/* Abstract — revealed on expand */}
      {open && (
        <div
          className="px-6 pb-5"
          style={{ borderTop: '1px solid rgba(0,0,0,0.05)' }}
          onClick={e => e.stopPropagation()}
        >
          <p className="text-[13px] text-apple-secondary leading-relaxed pt-4">
            {award.abstract ?? 'No abstract available.'}
          </p>
        </div>
      )}
    </div>
  )
}
