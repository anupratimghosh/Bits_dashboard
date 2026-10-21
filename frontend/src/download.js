import { get } from './api'

/** One CSV cell. Text that a spreadsheet would read as a formula (a title
 *  starting with `=`, `+`, `-` or `@`) is prefixed with `'` so it opens as text. */
function cell(v) {
  if (v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v))) return ''
  let s = String(v)
  if (typeof v === 'string' && /^[=+\-@]/.test(s)) s = `'${s}`
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** `columns` is [{ key, label }] -- the order and headers of the file. */
export function toCsv(rows, columns) {
  const head = columns.map((c) => cell(c.label)).join(',')
  const body = rows.map((r) => columns.map((c) => cell(r[c.key])).join(','))
  return [head, ...body].join('\r\n')
}

/** Save rows as a CSV file. The BOM makes Excel read it as UTF-8, so
 *  non-ASCII author names and journal titles survive the round trip. */
export function saveCsv(name, rows, columns) {
  const blob = new Blob(['﻿', toCsv(rows, columns)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${name}-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Every row of a paginated list endpoint, not just the page on screen. */
export async function fetchAll(path, params, pageSize) {
  const items = []
  for (let page = 1; ; page++) {
    const d = await get(path, { ...params, page, page_size: pageSize })
    items.push(...d.items)
    if (!d.items.length || items.length >= d.total) return items
  }
}
