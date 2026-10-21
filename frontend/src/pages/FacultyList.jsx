import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import FilterBar from '../components/FilterBar'
import { Card, DownloadButton, ErrorBox, Pager, Spinner, Th } from '../components/UI'
import { fetchAll } from '../download'
import { dec, num } from '../format'
import { useApi, useFilters } from '../useData'

const COLUMNS = [
  { key: 'name', label: 'Faculty' },
  { key: 'campus', label: 'Campus' },
  { key: 'department', label: 'Department' },
  { key: 'publications', label: 'Pubs', num: true },
  { key: 'citations', label: 'Citations', num: true },
  { key: 'h_index', label: 'h-index', num: true },
  { key: 'q1', label: 'Q1', num: true },
  { key: 'avg_citescore', label: 'Avg CiteScore', num: true, digits: 2 },
  { key: 'avg_impact_factor', label: 'Avg JIF', num: true, digits: 3 },
]

const CSV_COLUMNS = [
  { key: 'name', label: 'Faculty' },
  { key: 'designation', label: 'Designation' },
  { key: 'campus', label: 'Campus' },
  { key: 'department', label: 'Department' },
  { key: 'publications', label: 'Publications' },
  { key: 'citations', label: 'Citations' },
  { key: 'h_index', label: 'h-index' },
  { key: 'q1', label: 'Q1' },
  { key: 'q2', label: 'Q2' },
  { key: 'avg_citescore', label: 'Avg CiteScore' },
  { key: 'avg_impact_factor', label: 'Avg JIF' },
  { key: 'scopus_author_id', label: 'Scopus author ID' },
]

export default function FacultyList() {
  const { filters, setFilter } = useFilters()
  const [params, setParams] = useSearchParams()
  const [sort, setSort] = useState('publications')
  const [order, setOrder] = useState('desc')
  const [name, setName] = useState(params.get('name') || '')
  const page = Number(params.get('page') || 1)
  const publishingOnly = params.get('all') !== '1'

  const { data, error, loading } = useApi('/faculty', {
    ...filters, name: params.get('name') || '', sort, order, page,
    page_size: 25, publishing_only: publishingOnly,
  })

  const onSort = (field) => {
    if (field === sort) setOrder(order === 'asc' ? 'desc' : 'asc')
    else { setSort(field); setOrder(['name', 'campus', 'department'].includes(field) ? 'asc' : 'desc') }
    setPage(1)
  }
  const setPage = (p) => {
    const next = new URLSearchParams(params)
    if (p <= 1) next.delete('page'); else next.set('page', p)
    setParams(next, { replace: true })
  }
  const submitName = (v) => {
    const next = new URLSearchParams(params)
    if (v) next.set('name', v); else next.delete('name')
    next.delete('page')
    setParams(next, { replace: true })
  }
  // search as you type, once typing pauses -- same delay as the main search box
  const urlName = params.get('name') || ''
  useEffect(() => {
    if (name === urlName) return undefined
    const t = setTimeout(() => submitName(name), 350)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, urlName])

  const toggleAll = () => {
    const next = new URLSearchParams(params)
    if (publishingOnly) next.set('all', '1'); else next.delete('all')
    next.delete('page')
    setParams(next, { replace: true })
  }

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Faculty</h1>
        <p className="page-sub">
          Search any BITS Pilani faculty member and open their full publication
          profile. Sorting runs across the whole result set, not just this page.
        </p>
      </div>

      <FilterBar filters={filters} setFilter={setFilter} show={{ search: false }} />

      <div className="filterbar">
        <div className="field" style={{ flex: 1, minWidth: 240 }}>
          <label htmlFor="fac-name">Faculty name</label>
          <input
            id="fac-name" type="search" style={{ width: '100%' }}
            placeholder="Start typing a name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submitName(e.target.value) }}
          />
        </div>
        <button className="btn" onClick={toggleAll}>
          {publishingOnly ? 'Include faculty with no publications' : 'Only faculty with publications'}
        </button>
      </div>

      <ErrorBox error={error} />

      <Card
        title={data ? `${num(data.total)} faculty` : 'Faculty'}
        note={publishingOnly ? 'with publications matching the current filter' : 'entire IRINS roster'}
        action={data?.total ? (
          <DownloadButton
            name="bits-faculty" columns={CSV_COLUMNS}
            rows={() => fetchAll('/faculty', {
              ...filters, name: params.get('name') || '', sort, order, publishing_only: publishingOnly,
            }, 200)}
          />
        ) : null}
      >
        {loading && !data && <Spinner />}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {COLUMNS.map((c) => (
                  <Th key={c.key} field={c.key} sort={sort} order={order} onSort={onSort} num={c.num}>
                    {c.label}
                  </Th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((f) => (
                <tr key={f.id}>
                  <td>
                    <Link to={`/faculty/${f.id}`} className="t-title">{f.name}</Link>
                    {f.designation && <div className="t-sub">{f.designation}</div>}
                  </td>
                  <td>{f.campus || <span className="muted">--</span>}</td>
                  <td>{f.department || <span className="muted">--</span>}</td>
                  <td className="num">{num(f.publications)}</td>
                  <td className="num">{num(f.citations)}</td>
                  <td className="num">{num(f.h_index)}</td>
                  <td className="num">{num(f.q1)}</td>
                  <td className="num">{f.avg_citescore === null ? <span className="muted">--</span> : dec(f.avg_citescore)}</td>
                  <td className="num">{f.avg_impact_factor === null ? <span className="muted">--</span> : dec(f.avg_impact_factor, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && data.items.length === 0 && <div className="empty">No faculty match this search</div>}
        {data && <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
      </Card>
    </div>
  )
}
