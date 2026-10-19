import { Link } from 'react-router-dom'
import FilterBar from '../components/FilterBar'
import { Donut, QuartileStack, RankedBars, TimeBars, Trend } from '../components/Charts'
import { BarCell, Card, ErrorBox, Spinner, Stat } from '../components/UI'
import { dec, growthLabel, num } from '../format'
import { useApiAll, useFilters } from '../useData'

export default function Overview() {
  const { filters, setFilter } = useFilters()
  const { data, error, loading } = useApiAll({
    kpi: '/overview',
    byYear: '/analytics/by-year',
    byCampus: '/analytics/by-campus',
    byType: '/analytics/by-document-type',
    subjects: '/analytics/top-subjects',
    journals: '/analytics/top-journals',
    trend: '/analytics/citation-trend',
  }, { ...filters, limit: 10 })

  const k = data.kpi
  const growth = k ? growthLabel(k.yoy_growth_pct) : null
  const journalsMax = Math.max(1, ...(data.journals || []).map((j) => j.publications || 0))

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Executive summary</h1>
        <p className="page-sub">
          BITS Pilani research output across all four campuses, built from Scopus
          publication records enriched with IRINS faculty, SJR, CiteScore and Web
          of Science journal metrics.
        </p>
      </div>

      <FilterBar filters={filters} setFilter={setFilter} />
      <ErrorBox error={error} />
      {loading && !k && <Spinner />}

      {k && (
        <div className="stack">
          <div className="grid cols-5">
            <Stat
              label="Total publications" value={num(k.total_publications)}
              meta={k.unattributed_publications > 0
                ? `${num(k.unattributed_publications)} awaiting faculty attribution`
                : 'all attributed to faculty'}
            />
            <Stat
              label="Publications this year" value={num(k.publications_this_year)}
              delta={growth ? { up: k.yoy_growth_pct >= 0, text: growth } : null}
              meta={`vs ${num(k.publications_last_year)} last year`}
            />
            <Stat label="Total citations" value={num(k.total_citations)} meta={`${dec(k.avg_citations)} per publication`} />
            <Stat label="Institution h-index" value={num(k.h_index)}
              meta={`i10 ${num(k.i10_index)} · over the publications held here`} />
            <Stat label="Faculty publishing" value={num(k.total_faculty_publishing)} meta={`across ${k.total_departments} departments`} />
          </div>

          <div className="grid cols-4">
            <Stat label="Q1 journal publications" value={num(k.q1_publications)}
              meta={`${dec((k.q1_publications / k.total_publications) * 100, 1)}% of output`} />
            <Stat label="Q2 journal publications" value={num(k.q2_publications)}
              meta={`${dec((k.q2_publications / k.total_publications) * 100, 1)}% of output`} />
            <Stat label="With impact factor" value={num(k.publications_with_if)}
              meta={`avg JIF ${dec(k.avg_impact_factor)}`} />
            <Stat label="Journals published in" value={num(k.total_journals)}
              meta={`avg CiteScore ${dec(k.avg_citescore)} · avg SJR ${dec(k.avg_sjr, 3)}`} />
          </div>

          <div className="grid cols-2">
            <Card title="Publications by year" note="click a bar to filter to that year">
              <TimeBars
                data={data.byYear} xKey="year" yKey="publications" name="Publications"
                onBarClick={(y) => setFilter({ year_from: y, year_to: y })}
              />
            </Card>
            <Card title="Journal quartile mix by year" note="SJR best quartile">
              <QuartileStack data={data.byYear} xKey="year" />
            </Card>
          </div>

          <div className="grid cols-2">
            <Card
              title="Publications by campus"
              note="collaborations count in each campus"
            >
              <RankedBars data={data.byCampus} labelKey="name" valueKey="publications" name="Publications" />
              <div className="note" style={{ marginTop: 10 }}>
                Campus figures sum to more than the institute total: a paper co-authored
                across two campuses is credited in full to both.
              </div>
            </Card>
            <Card title="Publications by document type" note="every publication counts toward exactly one type">
              <Donut data={data.byType} labelKey="document_type" valueKey="publications" />
            </Card>
          </div>

          <div className="grid cols-2">
            <Card title="Top subject areas" note="from the CiteScore ASJC taxonomy">
              <RankedBars data={data.subjects} labelKey="subject" valueKey="publications" name="Publications" />
            </Card>
            <Card title="Top journals" note="by publication count">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Journal</th>
                      <th className="num">Pubs</th>
                      <th className="num">CiteScore</th>
                      <th className="num">JIF</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.journals || []).map((j) => (
                      <tr key={`${j.journal_id}-${j.journal}`}>
                        <td className="t-wide">{j.journal}</td>
                        <td className="num"><BarCell value={j.publications} max={journalsMax} /></td>
                        <td className="num">{dec(j.citescore, 1)}</td>
                        <td className="num">{dec(j.impact_factor, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          {(data.trend || []).length > 1 && (
            <Card
              title="Citations over time"
              note="one point per weekly upload"
            >
              <Trend data={data.trend} xKey="snapshot_date" yKey="citations" name="Total citations" />
              <div className="note" style={{ marginTop: 10 }}>
                A Scopus export only ever reports today's citation count. This series
                is reconstructed from the snapshot taken at each upload, so it grows
                one point per week.
              </div>
            </Card>
          )}

          <Card title="Where to go next">
            <div className="row">
              <Link className="btn" to="/campuses">Compare campuses</Link>
              <Link className="btn" to="/departments">Department analysis</Link>
              <Link className="btn" to="/faculty">Search faculty</Link>
              <Link className="btn" to="/publications">Browse all publications</Link>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
