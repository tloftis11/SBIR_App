import { useEffect, useState } from 'react'
import CompaniesTab from './tabs/CompaniesTab'
import SearchTab from './tabs/SearchTab'
import TrendsTab from './tabs/TrendsTab'
import { type FilterOptions, fetchFilters } from './lib/api'

type Tab = 'search' | 'companies' | 'trends'

export default function App() {
  const [tab, setTab] = useState<Tab>('search')
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null)

  useEffect(() => {
    fetchFilters().then(setFilterOptions).catch(() => {})
  }, [])

  return (
    <div className="min-h-screen bg-apple-bg font-sans">
      <header
        className="bg-white/90 backdrop-blur-md sticky top-0 z-20"
        style={{ borderBottom: '1px solid rgba(0,0,0,0.07)' }}
      >
        <div className="max-w-5xl mx-auto px-8 h-12 flex items-center justify-between">
          <span className="text-[15px] font-semibold text-apple-text tracking-tight select-none">
            SBIR Explorer
          </span>

          {/* Segmented control — Apple's UISegmentedControl pattern */}
          <div
            className="flex rounded-lg p-0.5"
            style={{ background: 'rgba(0,0,0,0.06)' }}
          >
            {([['search', 'Search'], ['companies', 'Companies'], ['trends', 'Trends']] as [Tab, string][]).map(([id, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`px-4 py-1 text-[13px] font-medium rounded-md transition-all duration-150 ${
                  tab === id
                    ? 'bg-white text-apple-text shadow-sm'
                    : 'text-apple-secondary hover:text-apple-text'
                }`}
                style={tab === id ? { boxShadow: '0 1px 3px rgba(0,0,0,0.12)' } : {}}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {tab === 'search'     && <SearchTab    filterOptions={filterOptions} />}
      {tab === 'companies'  && <CompaniesTab  filterOptions={filterOptions} />}
      {tab === 'trends'     && <TrendsTab     filterOptions={filterOptions} />}
    </div>
  )
}
