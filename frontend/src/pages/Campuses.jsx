import { Link } from 'react-router-dom'
import FilterBar from '../components/FilterBar'
import { QuartileBar, RankedBars } from '../components/Charts'
import { Card, ErrorBox, Spinner } from '../components/UI'
import { dec, num } from '../format'
import { useApiAll, useFilters } from '../useData'

const MEASURES = [
  { key: 'publications', label: 'Publications', digits: 0 },
  { key: 'citations', label: 'Citations', digits: 0 },
  { key: 'h_index', label: 'h-index', digits: 0 },
  { key: 'q1', label: 'Q1 publications', digits: 0 },
  { key: 'with_if', label: 'With impact factor', digits: 0 },
  { key: 'avg_sjr', label: 'Average SJR', digits: 3 },
  { key: 'avg_citescore', label: 'Average CiteScore', digits: 2 },
  { key: 'avg_impact_factor', label: 'Average impact factor', digits: 3 },
]

export default function Campuses() {
  const { filters, setFilter } = useFilters()
  const { data, error, loading } = useApiAll({
    campuses: '/analytics/by-campus',
    years: '/analytics/by-year',
  }, filters)

  const campuses = data.campuses || []

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Campus comparison</h1>
        <p className="page-sub">
          Pilani, Goa, Hyderabad and Dubai side by side. A publication co-authored
          across campuses is credited in full to each, so campus figures sum to
          more than the institute total.
        </p>
      </div>

      <FilterBar filters={filters} setFilter={setFilter} show={{ campus: false, department: false }} />
      <ErrorBox error={error} />
      {loading && !campuses.length && <Spinner />}

      {campuses.length > 0 && (
        <div className="stack">
          <div className="grid cols-3">
            <Card title="Publications by campus">
              <RankedBars data={campuses} labelKey="name" valueKey="publications" name="Publications" />
            </Card>
            <Card title="Q1 journal publications by campus">
              <RankedBars data={campuses} labelKey="name" valueKey="q1" name="Q1 publications" />
            </Card>
            <Card title="h-index by campus" note="over each campus's publications held here">
              <RankedBars data={campuses} labelKey="name" valueKey="h_index" name="h-index" />
            </Card>
          </div>

          <Card title="Every measure, by campus" note="click a campus to drill into its departments">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Campus</th>
                    {MEASURES.map((m) => <th key={m.key} className="num">{m.label}</th>)}
                    <th className="num">Faculty</th>
                    <th className="num">Open access</th>
                  </tr>
                </thead>
                <tbody>
                  {campuses.map((c) => (
                    <tr key={c.id}>
                      <td className="t-title">
                        <Link to={`/departments?campus_id=${c.id}`}>{c.name}</Link>
                      </td>
                      {MEASURES.map((m) => (
                        <td key={m.key} className="num">
                          {c[m.key] === null || c[m.key] === undefined
                            ? <span className="muted">--</span>
                            : m.digits === 0 ? num(c[m.key]) : dec(c[m.key], m.digits)}
                        </td>
                      ))}
                      <td className="num">{num(c.faculty)}</td>
                      <td className="num">{num(c.open_access)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Quartile mix by campus" note="SJR best quartile of the publishing journal">
            <div className="stack">
              {campuses.map((c) => (
                <div key={c.id}>
                  <div className="t-title" style={{ marginBottom: 6 }}>{c.name}</div>
                  <QuartileBar
                    counts={{
                      Q1: c.q1, Q2: c.q2, Q3: c.q3, Q4: c.q4,
                      Unranked: c.publications - c.q1 - c.q2 - c.q3 - c.q4,
                    }}
                  />
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
