import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, DownloadButton, ErrorBox, Spinner, Pager } from '../components/UI'
import { fetchAll } from '../download'
import { num } from '../format'
import { post } from '../api'
import { useApi } from '../useData'

/** Resolves one queue entry by picking a faculty member. The search hits the
 *  full IRINS roster, not just faculty who already have publications. */
function Resolver({ item, onDone, allowIgnore = true }) {
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
        {allowIgnore && <button className="btn" onClick={ignore} disabled={busy}>Not a faculty member</button>}
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

const MATCHED_CSV_COLUMNS = [
  { key: 'raw_name', label: 'Author on paper' },
  { key: 'scopus_author_id', label: 'Scopus author ID' },
  { key: 'raw_affiliation', label: 'Affiliation' },
  { key: 'matched_faculty', label: 'Matched to' },
  { key: 'matched_department', label: 'Department' },
  { key: 'matched_campus', label: 'Campus' },
  { key: 'matched_at', label: 'Matched on' },
  { key: 'title', label: 'Publication' },
  { key: 'year', label: 'Year' },
  { key: 'doi', label: 'DOI' },
]

const CSV_COLUMNS = [
  { key: 'raw_name', label: 'Author on paper' },
  { key: 'scopus_author_id', label: 'Scopus author ID' },
  { key: 'raw_affiliation', label: 'Affiliation' },
  { key: 'guessed_campus', label: 'Campus (parsed)' },
  { key: 'title', label: 'Publication' },
  { key: 'year', label: 'Year' },
  { key: 'cited_by', label: 'Cited by' },
  { key: 'doi', label: 'DOI' },
]

export default function Review() {
  const [page, setPage] = useState(1)
  const [priorityOnly, setPriorityOnly] = useState(true)
  // 'open' = still to decide; 'ignored' = ruled "not a faculty member";
  // 'matched' = matched by hand here. The last two stay reviewable so a wrong
  // decision can be found and reversed later.
  const [status, setStatus] = useState('open')
  const [term, setTerm] = useState('')
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(null)
  const [reload, setReload] = useState(0)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)
  const ignored = status === 'ignored'
  const matched = status === 'matched'
  const params = { status, priority_only: status === 'open' ? priorityOnly : false, search }
  const { data, error, loading } = useApi('/admin/unmatched', {
    ...params, page, page_size: 25, _r: reload,
  })

  // search as you type, once typing pauses -- same delay as the other search boxes
  useEffect(() => {
    if (term === search) return undefined
    const t = setTimeout(() => { setSearch(term); setPage(1) }, 350)
    return () => clearTimeout(t)
  }, [term, search])

  const refresh = () => { setOpen(null); setReload((r) => r + 1) }
  const switchTo = (next) => { setStatus(next); setPage(1); setOpen(null) }

  const act = async (item, action) => {
    setBusy(true); setActionError(null)
    try {
      await post(`/admin/unmatched/${item.id}/${action}`)
      refresh()
    } catch (e) { setActionError(e) } finally { setBusy(false) }
  }
  const cols = 6 + (ignored ? 2 : 0) + (matched ? 2 : 0)

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
        <button className={!ignored ? 'btn btn-primary' : 'btn'} onClick={() => switchTo('open')}>
          Open queue
        </button>
        <button className={ignored ? 'btn btn-primary' : 'btn'} onClick={() => switchTo('ignored')}>
          Marked &ldquo;not a faculty member&rdquo;
        </button>
        <button className={matched ? 'btn btn-primary' : 'btn'} onClick={() => switchTo('matched')}>
          Manual matches
        </button>
        <input
          type="search" placeholder="Search author name or paper title" value={term}
          onChange={(e) => setTerm(e.target.value)} style={{ minWidth: 260 }}
        />
      </div>

      {status === 'open' && (
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
      )}
      {matched && (
        <div className="note" style={{ marginBottom: 12 }}>
          Every author matched to a professor on this page, newest first. If a match is wrong,
          use <strong>Change</strong> to move the papers to the right professor, or <strong>Undo
          match</strong> to send the author back to the open queue (or to the professor IRINS lists
          for that Scopus ID, if there is one). Either applies to every paper by that Scopus ID.
        </div>
      )}
      {ignored && (
        <div className="note" style={{ marginBottom: 12 }}>
          Every author ruled &ldquo;not a faculty member&rdquo;, with each of their papers. These papers
          still count for the institute and the campus, but for no professor or department. If one
          of them is in fact a professor already in IRINS, use <strong>Match to faculty</strong>; to
          send them back to the open queue, use <strong>Undo</strong>. Either applies to every paper
          by that Scopus ID.
        </div>
      )}

      <ErrorBox error={error || actionError} />

      <Card
        title={data
          ? (ignored ? `${num(data.total)} papers with an author marked not faculty`
            : matched ? `${num(data.total)} papers with a manually matched author`
              : `${num(data.total)} entries in the queue`)
          : 'Queue'}
        action={data?.total ? (
          <DownloadButton
            name={ignored ? 'bits-marked-not-faculty' : matched ? 'bits-manual-matches' : 'bits-attribution-queue'}
            columns={matched ? MATCHED_CSV_COLUMNS : CSV_COLUMNS}
            rows={() => fetchAll('/admin/unmatched', params, 200)}
          />
        ) : null}
      >
        {loading && !data && <Spinner />}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Author on paper</th><th>Scopus ID</th><th>Affiliation</th>
                <th>Campus (parsed)</th><th>Publication</th>
                {ignored && <th className="num">Cited by</th>}
                {ignored && <th>Marked on</th>}
                {matched && <th>Matched to</th>}
                {matched && <th>Matched on</th>}
                <th></th>
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
                    {ignored && <td className="num">{num(item.cited_by)}</td>}
                    {ignored && <td className="t-sub">{item.ignored_at ? item.ignored_at.slice(0, 10) : '--'}</td>}
                    {matched && (
                      <td>
                        {item.matched_faculty_id
                          ? <Link to={`/faculty/${item.matched_faculty_id}`} className="t-title">{item.matched_faculty}</Link>
                          : '--'}
                        <div className="t-sub">{[item.matched_department, item.matched_campus].filter(Boolean).join(' · ')}</div>
                      </td>
                    )}
                    {matched && <td className="t-sub">{item.matched_at ? item.matched_at.slice(0, 10) : '--'}</td>}
                    <td>
                      <div className="row" style={{ flexWrap: 'nowrap' }}>
                        <button className="btn" onClick={() => setOpen(open === item.id ? null : item.id)}>
                          {open === item.id ? 'Close' : ignored ? 'Match to faculty' : matched ? 'Change' : 'Resolve'}
                        </button>
                        {ignored && (
                          <button className="btn" disabled={busy} onClick={() => act(item, 'reopen')}>Undo</button>
                        )}
                        {matched && (
                          <button className="btn" disabled={busy} onClick={() => act(item, 'unmatch')}>Undo match</button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {open === item.id && (
                    <tr>
                      <td colSpan={cols} style={{ background: 'var(--surface-2)' }}>
                        <Resolver item={item} onDone={refresh} allowIgnore={status === 'open'} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        {data && !data.items.length && (
          <div className="empty">
            {search ? 'Nothing matches this search.'
              : ignored ? 'No author has been marked as not a faculty member.'
                : matched ? 'No author has been matched by hand yet.'
                : 'Queue is clear — every BITS author is matched.'}
          </div>
        )}
        {data && <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
      </Card>
    </div>
  )
}
