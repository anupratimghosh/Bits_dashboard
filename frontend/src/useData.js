import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { get } from './api'

/** Fetch a single endpoint, re-running whenever the serialised params change. */
export function useApi(path, params, enabled = true) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(enabled)
  const key = JSON.stringify([path, params])
  const latest = useRef(0)

  useEffect(() => {
    if (!enabled) { setLoading(false); return }
    const run = ++latest.current
    setLoading(true)
    get(path, params)
      .then((d) => { if (run === latest.current) { setData(d); setError(null) } })
      .catch((e) => { if (run === latest.current) setError(e) })
      .finally(() => { if (run === latest.current) setLoading(false) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled])

  return { data, error, loading }
}

/** Fetch several endpoints at once; returns { key: data }. */
export function useApiAll(spec, params) {
  // keyed on the whole spec, not just its keys: a spec whose paths change while
  // its keys stay the same would otherwise keep fetching the old paths
  const entries = useMemo(() => Object.entries(spec), [JSON.stringify(spec)]) // eslint-disable-line
  const [data, setData] = useState({})
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const key = JSON.stringify([Object.values(spec), params])
  const latest = useRef(0)

  useEffect(() => {
    const run = ++latest.current
    setLoading(true)
    Promise.all(entries.map(([, p]) => get(p, params)))
      .then((results) => {
        if (run !== latest.current) return
        setData(Object.fromEntries(entries.map(([k], i) => [k, results[i]])))
        setError(null)
      })
      .catch((e) => { if (run === latest.current) setError(e) })
      .finally(() => { if (run === latest.current) setLoading(false) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return { data, error, loading }
}

/** Dashboard filters live in the URL, so any view is linkable and survives a
 *  refresh -- and the filter set is shared by every page. */
export function useFilters() {
  const [search, setSearch] = useSearchParams()

  const filters = useMemo(() => {
    const f = {}
    for (const k of ['year_from', 'year_to', 'campus_id', 'department_id', 'quartile',
                     'document_type', 'search', 'subject', 'metric_year']) {
      const v = search.get(k)
      if (v) f[k] = v
    }
    if (search.get('open_access')) f.open_access = search.get('open_access')
    if (search.get('has_if')) f.has_if = search.get('has_if')
    if (search.get('unmatched_only')) f.unmatched_only = search.get('unmatched_only')
    return f
  }, [search])

  const setFilter = useCallback((patch) => {
    const next = new URLSearchParams(search)
    Object.entries(patch).forEach(([k, v]) => {
      if (v === '' || v === null || v === undefined) next.delete(k)
      else next.set(k, v)
    })
    next.delete('page')
    setSearch(next, { replace: true })
  }, [search, setSearch])

  const reset = useCallback(() => setSearch(new URLSearchParams(), { replace: true }), [setSearch])

  return { filters, setFilter, reset, search, setSearch }
}
