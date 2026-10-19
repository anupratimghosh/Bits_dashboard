import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, ErrorBox, Spinner, Pager } from '../components/UI'
import { num } from '../format'
import { post } from '../api'
import { useApi } from '../useData'

/** Resolves one queue entry by picking a faculty member. The search hits the
 *  full IRINS roster, not just faculty who already have publications. */
function Resolver({ item, onDone }) {
  const [term, setTerm] = useState(item.raw_name?.split(' ')[0] || '')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  // deliberately NOT scoped to the guessed campus: the guess comes from parsing
  // the affiliation string and can be wrong, which would hide the right person
  const results = useApi('/faculty', {
    name: query, publishing_only: false, page_size: 8,
  }, query.length >= 2)

  // search as you type, once typing pauses -- same delay as the other search boxes
  useEffect(() => {
    if (term === query) return undefined
    const t = setTimeout(() => setQuery(term), 350)
    return () => clearTimeout(t)
  }, [term, query])

  const resolve = async (facultyId) => {
    setBusy(true); setError(null)
    try {
      await post(`/admin/unmatched/${item.id}/resolve`, { faculty_id: facultyId })
      onDone()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }
  const ignore = async () => {
    setBusy(true); setError(null)
    try {
      await post(`/admin/unmatched/${item.id}/ignore`)
      onDone()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  return (
    <div style={{ padding: '10px 0' }}>
      <div className="row">
        <input
          type="search" placeholder="Search IRINS faculty by name" value={term}
          onChange={(e) => setTerm(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') setQuery(e.target.value) }}
          style={{ minWidth: 240 }}
        />
        <button className="btn" onClick={ignore} disabled={busy}>Not a faculty member</button>
      </div>
      <ErrorBox error={error} />
      {query.length >= 2 && (
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table>
            <tbody>
              {(results.data?.items || []).map((f) => (
                <tr key={f.id}>
                  <td className="t-title">{f.name}</td>
                  <td className="t-sub">{f.designation}</td>
                  <td>{f.campus}</td>
                  <td>{f.department}</td>
                  <td className="num">{num(f.publications)} pubs</td>
                  <td><button className="btn btn-primary" disabled={busy} onClick={() => resolve(f.id)}>Match</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {results.data && !results.data.items.length && <div className="empty">No faculty match that name</div>}
        </div>
      )}
    </div>
  )
}

export default function Review() {
  const [page, setPage] = useState(1)
  const [priorityOnly, setPriorityOnly] = useState(true)
  const [open, setOpen] = useState(null)
  const [reload, setReload] = useState(0)
  const { data, error, loading } = useApi('/admin/unmatched', {
    page, page_size: 25, priority_only: priorityOnly, _r: reload,
  })

  const refresh = () => { setOpen(null); setReload((r) => r + 1) }

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Attribution review</h1>
        <p className="page-sub">
          BITS-affiliated authors whose Scopus Author ID is not in the IRINS master.
          Their publications count towards institute and campus totals but cannot
          appear in faculty or department views until they are matched here. A match
          is stored against the Scopus Author ID, so it applies to every past and
          future publication by that author.
        </p>
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        <button
          className={priorityOnly ? 'btn btn-primary' : 'btn'}
          onClick={() => { setPriorityOnly(!priorityOnly); setPage(1) }}
        >
          {priorityOnly ? 'Priority only: papers with no matched author' : 'Showing all unmatched authors'}
        </button>
        <span className="muted" style={{ fontSize: 12.5 }}>
          {priorityOnly
            ? 'These publications are missing from every faculty and department view.'
            : 'Includes co-authors on already-attributed papers — mostly research scholars.'}
        </span>
      </div>

      <ErrorBox error={error} />

      <Card title={data ? `${num(data.total)} entries in the queue` : 'Queue'}>
        {loading && !data && <Spinner />}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Author on paper</th><th>Scopus ID</th><th>Affiliation</th>
                <th>Campus (parsed)</th><th>Publication</th><th></th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((item) => (
                <Fragment key={item.id}>
                  <tr>
                    <td className="t-title">{item.raw_name || '--'}</td>
                    <td className="t-sub">{item.scopus_author_id || '--'}</td>
                    <td className="t-wide t-sub">{item.raw_affiliation || '--'}</td>
                    <td>{item.guessed_campus || <span className="muted">--</span>}</td>
                    <td className="t-wide">
                      <Link to={`/publications/${item.publication_id}`} className="t-title">{item.title}</Link>
                      <div className="t-sub">{item.year}</div>
                    </td>
                    <td>
                      <button className="btn" onClick={() => setOpen(open === item.id ? null : item.id)}>
                        {open === item.id ? 'Close' : 'Resolve'}
                      </button>
                    </td>
                  </tr>
                  {open === item.id && (
                    <tr>
                      <td colSpan={6} style={{ background: 'var(--surface-2)' }}>
                        <Resolver item={item} onDone={refresh} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        {data && !data.items.length && <div className="empty">Queue is clear — every BITS author is matched.</div>}
        {data && <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
      </Card>
    </div>
  )
}
