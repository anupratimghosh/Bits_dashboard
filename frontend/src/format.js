// NaN is treated as absent: with a filter that matches nothing the API returns
// null counts over a zero total, and `null / 0` reaches these as NaN -- which
// used to render literally, e.g. "NaN% of output" on the Overview cards.
const blank = (v) => v === null || v === undefined || v === '' || Number.isNaN(Number(v))

export const num = (v) => (blank(v) ? '--' : Number(v).toLocaleString('en-IN'))

export const dec = (v, digits = 2) => (blank(v) ? '--' : Number(v).toFixed(digits))

export const pct = (v) => (v === null || v === undefined ? '--' : `${v > 0 ? '+' : ''}${v}%`)

/** Very large year-on-year swings are real but meaningless on a partial-year
 *  dataset -- show the raw counts rather than a four-digit percentage. */
export const growthLabel = (v) => {
  if (v === null || v === undefined) return null
  if (Math.abs(v) >= 1000) return v > 0 ? 'sharp increase' : 'sharp decrease'
  return pct(v)
}

export const QUARTILE_COLORS = {
  Q1: 'var(--q1)',
  Q2: 'var(--q2)',
  Q3: 'var(--q3)',
  Q4: 'var(--q4)',
  Unranked: 'var(--q-unranked)',
}

export const SERIES = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)']

// Indian financial year: FY 2026-27 runs Apr 2026 - Mar 2027
export const FY_QUARTERS = [
  { q: 1, label: 'Q1 · Apr–Jun' },
  { q: 2, label: 'Q2 · Jul–Sep' },
  { q: 3, label: 'Q3 · Oct–Dec' },
  { q: 4, label: 'Q4 · Jan–Mar' },
]
