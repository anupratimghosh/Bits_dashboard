import { Link } from 'react-router-dom'
import FilterBar from '../components/FilterBar'
import { QuartileBar, RankedBars } from '../components/Charts'
import { Card, DownloadButton, ErrorBox, Spinner, Stat } from '../components/UI'
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
    kpi: '/overview',
    campuses: '/analytics/by-campus',
    years: '/analytics/by-year',
  }, filters)

  const campuses = data.campuses || []
  const k = data.kpi
  // campus figures double-count cross-campus papers; the gap to the institute
  // total is how many extra credits collaborations add
  const sumOf = (key) => campuses.reduce((t, c) => t + (c[key] || 0), 0)
  const extra = (key, total) => Math.max(0, sumOf(key) - (total || 0))

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
          {k && (
            <div className="grid cols-5">
              <Stat
                label="Total publications" value={num(k.total_publications)}
                meta={extra('publications', k.total_publications) > 0
                  ? `campus credits sum to ${num(sumOf('publications'))} · ${num(extra('publications', k.total_publications))} from cross-campus papers`
                  : 'no cross-campus double counting'}
              />
              <Stat
                label="Q1 journal publications" value={num(k.q1_publications)}
                meta={`${dec((k.q1_publications / (k.total_publications || 1)) * 100, 1)}% of output`}
              />
              <Stat label="Institution h-index" value={num(k.h_index)} meta={`i10 ${num(k.i10_index)}`} />
              <Stat label="Total citations" value={num(k.total_citations)} meta={`${dec(k.avg_citations)} per publication`} />
              <Stat
                label="Faculty publishing" value={num(k.total_faculty_publishing)}
                meta={`across ${campuses.length} campuses`}
              />
            </div>
          )}

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

          <Card
            title="Every measure, by campus" note="click a campus to drill into its departments"
            action={
              <DownloadButton
                name="bits-campuses" rows={campuses}
                columns={[
                  { key: 'name', label: 'Campus' },
                  ...MEASURES,
                  { key: 'q2', label: 'Q2' }, { key: 'q3', label: 'Q3' }, { key: 'q4', label: 'Q4' },
                  { key: 'faculty', label: 'Faculty' },
                  { key: 'open_access', label: 'Open access' },
                ]}
              />
            }
          >
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
