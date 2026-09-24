import { useEffect, useState } from 'react'
import { dec, num } from '../format'

export function Stat({ label, value, meta, delta }) {
  return (
    <div className="card stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {(meta || delta) && (
        <div className="stat-meta">
          {delta && <span className={delta.up ? 'delta-up' : 'delta-down'}>{delta.up ? '▲' : '▼'} {delta.text}</span>}
          {delta && meta && ' · '}
          {meta}
        </div>
      )}
    </div>
  )
}

export function Card({ title, note, children, className = '' }) {
  return (
    <div className={`card ${className}`}>
      {(title || note) && (
        <div className="card-head">
          <h3 className="card-title">{title}</h3>
          {note && <span className="card-note">{note}</span>}
        </div>
      )}
      {children}
    </div>
  )
}

/** True for values that have nothing to show. 0 and false are real values. */
const isBlank = (v) =>
  v === null || v === undefined || (typeof v === 'string' && v.trim() === '')

/** Renders one labelled field per column of the underlying table. The label is
 *  always emitted, so every professor -- and every publication -- gets exactly
 *  the same template: a column with no value shows a dash instead of vanishing
 *  and shifting the layout around. */
export function FieldGrid({ items, min = 200 }) {
  return (
    <div className="field-grid" style={{ '--field-min': `${min}px` }}>
      {items.map(({ label, value, full }) => (
        <div className={`field${full ? ' field-full' : ''}`} key={label}>
          <div className="field-label">{label}</div>
          <div className="field-value">
            {isBlank(value) ? <span className="muted">--</span> : value}
          </div>
        </div>
      ))}
    </div>
  )
}

export function Quartile({ value }) {
  const v = value || 'Unranked'
  const cls = { Q1: 'chip-q1', Q2: 'chip-q2', Q3: 'chip-q3', Q4: 'chip-q4' }[v] || 'chip-none'
  return (
    <span className={`chip ${cls}`} title={v === 'Unranked' ? 'Journal not ranked in SJR' : `SJR ${v}`}>
      <span className="chip-dot" />
      {v === 'Unranked' ? '--' : v}
    </span>
  )
}

export function Spinner({ label = 'Loading…' }) {
  return <div className="spinner">{label}</div>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return <div className="note" style={{ borderColor: 'var(--critical)' }}>⚠ {String(error.message || error)}</div>
}

/** Sortable header cell. Sorting is server-side, so it works across the whole
 *  result set rather than just the current page. */
export function Th({ children, field, sort, order, onSort, num: isNum }) {
  const active = sort === field
  return (
    <th
      className={`${field ? 'sortable' : ''} ${isNum ? 'num' : ''}`}
      onClick={field ? () => onSort(field) : undefined}
      title={field ? 'Sort by this column' : undefined}
    >
      {children}
      {active && <span className="arrow">{order === 'asc' ? '▲' : '▼'}</span>}
    </th>
  )
}

export function Pager({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total === 0) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  return (
    <div className="pager">
      <span>{num(from)}–{num(to)} of {num(total)}</span>
      <button className="btn" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
      <button className="btn" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
    </div>
  )
}

export function Metric({ value, digits = 2 }) {
  return <span className="num">{value === null || value === undefined ? <span className="muted">--</span> : dec(value, digits)}</span>
}

/** Bar-in-cell magnitude cue for a ranked table column -- one hue, no rank
 *  coloring, since the bar length already encodes the rank. `max` is the
 *  largest value in the column so bars stay comparable across rows. */
export function BarCell({ value, max }) {
  if (value === null || value === undefined) return <span className="muted">--</span>
  const pct = max > 0 ? Math.max((value / max) * 100, 3) : 0
  return (
    <div style={{ minWidth: 64 }}>
      <div style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{num(value)}</div>
      <div className="minibar-track"><div className="minibar" style={{ width: `${pct}%` }} /></div>
    </div>
  )
}

export function ThemeToggle() {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'system')
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])
  const next = { system: 'light', light: 'dark', dark: 'system' }
  const icon = { system: '◑ System', light: '☀ Light', dark: '☾ Dark' }
  return (
    <button className="toggle-theme" onClick={() => setTheme(next[theme])}>
      {icon[theme]}
    </button>
  )
}
