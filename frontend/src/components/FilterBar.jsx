import { useEffect, useState } from 'react'

import { FY_QUARTERS } from '../format'
import { useApi } from '../useData'

const SEARCH_DELAY_MS = 350

/** One filter row above the charts. Every control writes to the URL, so the
 *  whole dashboard -- KPIs, charts and tables -- moves together. */
export default function FilterBar({ filters, setFilter, show = {} }) {
  const { data: opts } = useApi('/filters')
  // Controlled, so any URL change (back/forward, a link) updates the box. The
  // reset is done during render rather than in an effect -- an effect would
  // repaint the stale value first and cost an extra render pass.
  const urlSearch = filters.search || ''
  const [term, setTerm] = useState(urlSearch)
  const [syncedTo, setSyncedTo] = useState(urlSearch)
  if (syncedTo !== urlSearch) {
    setSyncedTo(urlSearch)
    setTerm(urlSearch)
  }

  // Search as you type, once typing pauses. syncedTo is set to what we send,
  // so when the URL catches up the block above does not overwrite letters
  // typed in the meantime; other URL changes still reset the box.
  const commitSearch = (value) => {
    if (value === urlSearch) return
    setSyncedTo(value)
    setFilter({ search: value })
  }
  useEffect(() => {
    if (term === urlSearch) return undefined
    const t = setTimeout(() => commitSearch(term), SEARCH_DELAY_MS)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [term, urlSearch])
  const cfg = {
    year: true, quarter: true, campus: true, department: true, quartile: true,
    docType: true, search: true, metricYear: true, ...show,
  }
  if (!opts) return <div className="filterbar"><span className="muted">Loading filters…</span></div>

  // departments are scoped to the selected campus, as the brief requires
  const depts = filters.campus_id
    ? opts.campus_departments
        .filter((d) => String(d.campus_id) === String(filters.campus_id))
        .map((d) => ({ id: d.department_id, name: d.name }))
    : opts.departments

  return (
    <div className="filterbar">
      {cfg.campus && (
        <div className="field">
          <label htmlFor="f-campus">Campus</label>
          <select
            id="f-campus" value={filters.campus_id || ''}
            onChange={(e) => setFilter({ campus_id: e.target.value, department_id: '' })}
          >
            <option value="">All campuses</option>
            {opts.campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      )}

      {cfg.department && (
        <div className="field">
          <label htmlFor="f-dept">Department</label>
          <select
            id="f-dept" value={filters.department_id || ''}
            onChange={(e) => setFilter({ department_id: e.target.value })}
          >
            <option value="">All departments</option>
            {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>
      )}

      {cfg.year && (
        <>
          <div className="field">
            <label htmlFor="f-yf">Year from</label>
            <select id="f-yf" value={filters.year_from || ''} onChange={(e) => setFilter({ year_from: e.target.value })}>
              <option value="">Earliest</option>
              {opts.years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="f-yt">Year to</label>
            <select id="f-yt" value={filters.year_to || ''} onChange={(e) => setFilter({ year_to: e.target.value })}>
              <option value="">Latest</option>
              {opts.years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        </>
      )}

      {cfg.quarter && opts.financial_years.length > 0 && (
        <div className="field">
          <label htmlFor="f-fq">Financial quarter</label>
          <select
            id="f-fq"
            value={filters.fy ? (filters.fq ? `${filters.fy}-${filters.fq}` : filters.fy) : ''}
            onChange={(e) => {
              const [fy, fq] = e.target.value.split('-')
              setFilter({ fy: fy || '', fq: fq || '' })
            }}
            title={`Quarters use the publication date from Crossref. ${opts.undated_publications} publications have no month-level date and are left out while a quarter is selected.`}
          >
            <option value="">Any period</option>
            {opts.financial_years.map(({ fy, label }) => (
              <optgroup key={fy} label={`FY ${label}`}>
                <option value={fy}>FY {label} · full year</option>
                {FY_QUARTERS.map(({ q, label: ql }) => (
                  <option key={q} value={`${fy}-${q}`}>FY {label} · {ql}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
      )}

      {cfg.quartile && (
        <div className="field">
          <label htmlFor="f-q">Journal quartile</label>
          <select id="f-q" value={filters.quartile || ''} onChange={(e) => setFilter({ quartile: e.target.value })}>
            <option value="">Any quartile</option>
            {opts.quartiles.map((q) => <option key={q} value={q}>{q}</option>)}
          </select>
        </div>
      )}

      {cfg.docType && (
        <div className="field">
          <label htmlFor="f-dt">Document type</label>
          <select id="f-dt" value={filters.document_type || ''} onChange={(e) => setFilter({ document_type: e.target.value })}>
            <option value="">All types</option>
            {opts.document_types.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      )}

      {/* only worth showing once a second vintage of journal metrics is loaded */}
      {cfg.metricYear && opts.metric_years.length > 1 && (
        <div className="field">
          <label htmlFor="f-my">Metrics year</label>
          <select
            id="f-my" value={filters.metric_year || opts.default_metric_year || opts.metric_years[0]}
            onChange={(e) => setFilter({ metric_year: e.target.value })}
          >
            {opts.metric_years.map((y) => (
              <option key={y} value={y}>{y} metrics</option>
            ))}
          </select>
        </div>
      )}

      {cfg.search && (
        <div className="field" style={{ flex: 1, minWidth: 200 }}>
          <label htmlFor="f-s">Search title, journal, author or DOI</label>
          <input
            id="f-s" type="search" style={{ width: '100%' }}
            placeholder="e.g. supercapacitor"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') commitSearch(term) }}
          />
        </div>
      )}

    </div>
  )
}
