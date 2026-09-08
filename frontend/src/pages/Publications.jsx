import { Link, useSearchParams } from 'react-router-dom'
import FilterBar from '../components/FilterBar'
import { Card, ErrorBox, Pager, Quartile, Spinner, Th } from '../components/UI'
import { dec, num } from '../format'
import { useApi, useFilters } from '../useData'

const COLUMNS = [
  { key: 'year', label: 'Year', num: true },
  { key: 'title', label: 'Title' },
  { key: 'journal', label: 'Journal / source' },
  { key: 'document_type', label: 'Type' },
  { key: 'quartile', label: 'Quartile' },
  { key: 'citescore', label: 'CiteScore', num: true },
  { key: 'sjr', label: 'SJR', num: true },
  { key: 'impact_factor', label: 'JIF', num: true },
  { key: 'cited_by', label: 'Cited by', num: true },
]

export default function Publications() {
  const { filters, setFilter, reset } = useFilters()
  const [params, setParams] = useSearchParams()
  const sort = params.get('sort') || 'year'
  const order = params.get('order') || 'desc'
  const page = Number(params.get('page') || 1)

  const { data, error, loading } = useApi('/publications', {
    ...filters, sort, order, page, page_size: 25,
  })

  const patch = (obj) => {
    const next = new URLSearchParams(params)
    Object.entries(obj).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)))
    setParams(next, { replace: true })
  }
  const onSort = (field) => {
    const nextOrder = field === sort && order === 'desc' ? 'asc' : 'desc'
    patch({ sort: field, order: nextOrder, page: '' })
  }

  const unattributed = filters.unmatched_only === 'true' || filters.unmatched_only === '1'

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Publications</h1>
        <p className="page-sub">
          Every BITS-affiliated record in the database, with its journal metrics
          joined in. Sorting and filtering run server-side across all results.
        </p>
      </div>

      <FilterBar filters={filters} setFilter={setFilter} reset={reset} />

      <div className="row" style={{ marginBottom: 12 }}>
        <button
          className={unattributed ? 'btn btn-primary' : 'btn'}
          onClick={() => setFilter({ unmatched_only: unattributed ? '' : 'true' })}
        >
          {unattributed ? 'Showing unattributed only' : 'Show unattributed only'}
        </button>
        <button
          className={filters.has_if ? 'btn btn-primary' : 'btn'}
          onClick={() => setFilter({ has_if: filters.has_if ? '' : 'true' })}
        >
          Has impact factor
        </button>
        <button
          className={filters.open_access ? 'btn btn-primary' : 'btn'}
          onClick={() => setFilter({ open_access: filters.open_access ? '' : 'true' })}
        >
          Open access
        </button>
      </div>

      <ErrorBox error={error} />

      <Card title={data ? `${num(data.total)} publications` : 'Publications'}>
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
                  <td><span className="chip chip-plain">{p.document_type}</span></td>
                  <td><Quartile value={p.quartile} /></td>
                  <td className="num">{p.citescore === null ? <span className="muted">--</span> : dec(p.citescore, 1)}</td>
                  <td className="num">{p.sjr === null ? <span className="muted">--</span> : dec(p.sjr, 3)}</td>
                  <td className="num">{p.impact_factor === null ? <span className="muted">--</span> : dec(p.impact_factor, 2)}</td>
                  <td className="num">{num(p.cited_by)}</td>
                  <td className="t-narrow">
                    {p.bits_authors || <span className="muted">not attributed</span>}
                    {p.campuses && <div className="t-sub">{p.campuses}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data && data.items.length === 0 && <div className="empty">No publications match these filters</div>}
        {data && <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => patch({ page: p > 1 ? p : '' })} />}
      </Card>
    </div>
  )
}
