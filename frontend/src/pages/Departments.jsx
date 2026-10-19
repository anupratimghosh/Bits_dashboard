import { useState } from 'react'
import { Link } from 'react-router-dom'
import FilterBar from '../components/FilterBar'
import { QuartileBar, QuartileStack, RankedBars, TimeBars } from '../components/Charts'
import { BarCell, Card, ErrorBox, Pager, Quartile, Spinner, Stat, Th } from '../components/UI'
import { dec, num } from '../format'
import { useApi, useApiAll, useFilters } from '../useData'

const COLUMNS = [
  { key: 'name', label: 'Department' },
  { key: 'publications', label: 'Pubs', num: true },
  { key: 'citations', label: 'Citations', num: true },
  { key: 'h_index', label: 'h-index', num: true },
  { key: 'faculty', label: 'Faculty', num: true },
  { key: 'q1', label: 'Q1', num: true },
  { key: 'q2', label: 'Q2', num: true },
  { key: 'q3', label: 'Q3', num: true },
  { key: 'q4', label: 'Q4', num: true },
  { key: 'with_if', label: 'With JIF', num: true },
  { key: 'avg_sjr', label: 'Avg SJR', num: true, digits: 3 },
  { key: 'avg_citescore', label: 'Avg CiteScore', num: true, digits: 2 },
  { key: 'avg_impact_factor', label: 'Avg JIF', num: true, digits: 3 },
]

const PUB_COLUMNS = [
  { key: 'year', label: 'Year', num: true },
  { key: 'title', label: 'Title' },
  { key: 'journal', label: 'Journal / source' },
  { key: 'quartile', label: 'Quartile' },
  { key: 'impact_factor', label: 'JIF', num: true },
  { key: 'cited_by', label: 'Cited by', num: true },
]

/** Every publication of the selected department, under the same filters as the
 *  rest of the page. Sorted and paged server-side by the /publications API. */
function DepartmentPublications({ filters, search, name }) {
  const [sort, setSort] = useState('year')
  const [order, setOrder] = useState('desc')
  const [page, setPage] = useState(1)
  const { data, error, loading } = useApi('/publications', {
    ...filters, sort, order, page, page_size: 15,
  })

  const onSort = (field) => {
    if (field === sort) setOrder(order === 'asc' ? 'desc' : 'asc')
    else { setSort(field); setOrder(['title', 'journal', 'quartile'].includes(field) ? 'asc' : 'desc') }
    setPage(1)
  }

  return (
    <Card
      title={data ? `${num(data.total)} publications in ${name}` : `Publications in ${name}`}
      note={<Link to={`/publications?${search}`} style={{ color: 'var(--series-1)' }}>Open in Publications →</Link>}
    >
      <ErrorBox error={error} />
      {loading && !data && <Spinner />}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {PUB_COLUMNS.map((c) => (
                <Th key={c.key} field={c.key} sort={sort} order={order} onSort={onSort} num={c.num}>
                  {c.label}
                </Th>
              ))}
              <th>BITS authors</th>
            </tr>
          </thead>
          <tbody>
            {(data?.items || []).map((p) => (
              <tr key={p.id}>
                <td className="num">{p.year}</td>
                <td className="t-wide">
                  <Link to={`/publications/${p.id}`} className="t-title">{p.title}</Link>
                  {p.is_open_access ? <span className="chip chip-oa" style={{ marginLeft: 6 }}>OA</span> : null}
                </td>
                <td className="t-med">{p.journal}</td>
                <td><Quartile value={p.quartile} /></td>
                <td className="num">{p.impact_factor === null ? <span className="muted">--</span> : dec(p.impact_factor, 2)}</td>
                <td className="num">{num(p.cited_by)}</td>
                <td className="t-narrow">{p.bits_authors || <span className="muted">not attributed</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data && data.items.length === 0 && <div className="empty">No publications match these filters</div>}
      {data && <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
    </Card>
  )
}

export default function Departments() {
  const { filters, setFilter, search } = useFilters()
  const [sort, setSort] = useState('publications')
  const [order, setOrder] = useState('desc')

  // the roster is the navigation control, so it ignores department_id -- it must
  // keep listing every department on the campus while one of them is selected
  const { department_id: _sel, ...rosterFilters } = filters
  const { data, error, loading } = useApiAll({
    depts: '/analytics/by-department',
  }, rosterFilters)

  // one department selected -> show its drill-down alongside the roster
  const selected = filters.department_id
  const detail = useApi(`/departments/${selected}`, filters, Boolean(selected))
  const faculty = useApi('/analytics/top-faculty', { ...filters, limit: 10 }, Boolean(selected))
  const journals = useApi('/analytics/top-journals', { ...filters, limit: 8 }, Boolean(selected))
  const subjects = useApi('/analytics/top-subjects', { ...filters, limit: 8 }, Boolean(selected))

  const facultyMax = Math.max(1, ...(faculty.data || []).map((f) => f.publications || 0))
  const journalsMax = Math.max(1, ...(journals.data || []).map((j) => j.publications || 0))

  const deptMax = Math.max(1, ...(data.depts || []).map((d2) => d2.publications || 0))

  const rows = [...(data.depts || [])].sort((a, b) => {
    const av = a[sort], bv = b[sort]
    if (av === bv) return 0
    if (av === null || av === undefined) return 1
    if (bv === null || bv === undefined) return -1
    const cmp = typeof av === 'string' ? av.localeCompare(bv) : av - bv
    return order === 'asc' ? cmp : -cmp
  })

  const onSort = (field) => {
    if (field === sort) setOrder(order === 'asc' ? 'desc' : 'asc')
    else { setSort(field); setOrder(field === 'name' ? 'asc' : 'desc') }
  }

  const d = detail.data

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Department analysis</h1>
        <p className="page-sub">
          Pick a campus to see only its departments, or select a department for a
          full drill-down. Every column is sortable.
        </p>
      </div>

      <FilterBar filters={filters} setFilter={setFilter} />
      <ErrorBox error={error} />
      {loading && !rows.length && <Spinner />}

      {selected && d && (
        <div className="stack" style={{ marginBottom: 18 }}>
          <div className="grid cols-4">
            <Stat label="Publications" value={num(d.summary.publications)} meta={d.department.name} />
            <Stat label="Citations" value={num(d.summary.citations)} meta={`${num(d.summary.journals)} journals`} />
            <Stat label="Q1 publications" value={num(d.summary.q1)}
              meta={`${num(d.summary.with_if)} with impact factor`} />
            <Stat label="Average CiteScore" value={dec(d.summary.avg_citescore)}
              meta={`avg SJR ${dec(d.summary.avg_sjr, 3)} · avg JIF ${dec(d.summary.avg_impact_factor)}`} />
          </div>

          <div className="grid cols-2">
            <Card title="Publications by year" note={d.department.name}>
              <TimeBars data={d.by_year} xKey="year" yKey="publications" name="Publications" />
            </Card>
            <Card title="Quartile mix" note={d.department.name}>
              <QuartileBar counts={Object.fromEntries(d.quartiles.map((q) => [q.quartile, q.publications]))} />
              {d.by_year.length > 1 && (
                <div style={{ marginTop: 18 }}>
                  <QuartileStack data={d.by_year} xKey="year" height={170} />
                </div>
              )}
            </Card>
          </div>

          <div className="grid cols-3">
            <Card title="Top publishing faculty">
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Faculty</th><th className="num">Pubs</th><th className="num">Q1</th></tr></thead>
                  <tbody>
                    {(faculty.data || []).map((f) => (
                      <tr key={f.id}>
                        <td><Link to={`/faculty/${f.id}`} className="t-title">{f.name}</Link></td>
                        <td className="num"><BarCell value={f.publications} max={facultyMax} /></td>
                        <td className="num">{num(f.q1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card title="Top journals">
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Journal</th><th className="num">Pubs</th></tr></thead>
                  <tbody>
                    {(journals.data || []).map((j, i) => (
                      <tr key={i}><td className="t-wide">{j.journal}</td><td className="num"><BarCell value={j.publications} max={journalsMax} /></td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card title="Top subject areas">
              <RankedBars data={subjects.data} labelKey="subject" valueKey="publications" name="Publications" />
            </Card>
          </div>

          {/* keyed on the filters so sorting and paging start over when they change */}
          <DepartmentPublications
            key={JSON.stringify(filters)} filters={filters} search={search}
            name={d.department.name}
          />
        </div>
      )}

      <Card
        title={filters.campus_id ? 'Departments on this campus' : 'All departments'}
        note="click a row to drill in"
      >
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
              {rows.map((r) => (
                <tr
                  key={r.id} className="row-link"
                  onClick={() => setFilter({ department_id: String(r.id) === String(selected) ? '' : r.id })}
                  style={String(r.id) === String(selected) ? { background: 'var(--surface-2)' } : undefined}
                >
                  {COLUMNS.map((c) => (
                    <td key={c.key} className={c.num ? 'num' : 't-title'}>
                      {c.key === 'name'
                        ? r.name
                        : c.key === 'publications'
                          ? <BarCell value={r.publications} max={deptMax} />
                          : r[c.key] === null || r[c.key] === undefined
                            ? <span className="muted">--</span>
                            : c.digits ? dec(r[c.key], c.digits) : num(r[c.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rows.length && !loading && <div className="empty">No departments match this selection</div>}
      </Card>
    </div>
  )
}
