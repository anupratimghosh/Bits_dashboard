import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { QuartileBar, RankedBars, TimeBars } from '../components/Charts'
import { Card, ErrorBox, FieldGrid, Quartile, Spinner, Stat, Th } from '../components/UI'
import { dec, FY_QUARTERS, growthLabel, num } from '../format'
import { useApi } from '../useData'

const COLUMNS = [
  { key: 'year', label: 'Year', num: true },
  { key: 'pub_date', label: 'Published' },
  { key: 'title', label: 'Title' },
  { key: 'journal', label: 'Journal / source' },
  { key: 'document_type', label: 'Type' },
  { key: 'quartile', label: 'Quartile' },
  { key: 'citescore', label: 'CiteScore', num: true, digits: 1 },
  { key: 'impact_factor', label: 'JIF', num: true, digits: 2 },
  { key: 'cited_by', label: 'Cited by', num: true },
]

const Q_ORDER = { Q1: 1, Q2: 2, Q3: 3, Q4: 4 }

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
// month + year only: Crossref often has no day, and the stored day is then 1
const monthYear = (iso) => `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`

const ext = (href, text) => (
  <a href={href} target="_blank" rel="noreferrer" style={{ color: 'var(--series-1)' }}>{text}</a>
)

export default function FacultyDetail() {
  const { id } = useParams()
  const { data, error, loading } = useApi(`/faculty/${id}`)
  const [sort, setSort] = useState('year')
  const [order, setOrder] = useState('desc')
  const [fySel, setFySel] = useState(null)

  if (loading) return <Spinner label="Loading profile…" />
  if (error) return <ErrorBox error={error} />
  if (!data) return null

  const { faculty: f, summary: s } = data

  // Every column of the faculty (IRINS) record, in a fixed order. The list is
  // identical for every professor -- FieldGrid prints a dash where the master
  // left a column empty, so no profile is missing a row that another one has.
  const profileFields = [
    { label: 'Full name', value: f.name },
    { label: 'Title', value: f.title },
    { label: 'Designation', value: f.designation },
    { label: 'Qualification', value: f.qualification },
    {
      label: 'Department',
      value: f.department_id
        ? <Link to={`/departments?department_id=${f.department_id}${f.campus_id ? `&campus_id=${f.campus_id}` : ''}`}>{f.department}</Link>
        : f.department,
    },
    { label: 'Campus', value: f.campus },
    { label: 'Email', value: f.email ? ext(`mailto:${f.email}`, f.email) : null },
    {
      label: 'Status',
      value: f.is_active === null || f.is_active === undefined
        ? null
        : (f.is_active ? 'Active' : 'Inactive'),
    },
    { label: 'IRINS expert ID', value: f.expert_id },
    {
      label: 'Scopus author ID',
      value: f.scopus_author_id
        ? ext(`https://www.scopus.com/authid/detail.uri?authorId=${f.scopus_author_id}`, f.scopus_author_id)
        : null,
    },
    { label: 'ORCID', value: f.orcid_id ? ext(`https://orcid.org/${f.orcid_id}`, f.orcid_id) : null },
    { label: 'Researcher ID (WoS)', value: f.researcher_id },
    {
      label: 'Google Scholar',
      value: f.google_scholar_id
        ? ext(`https://scholar.google.com/citations?user=${f.google_scholar_id}`, f.google_scholar_id)
        : null,
    },
    { label: 'Faculty record ID', value: f.id },
    { label: 'Expertise', value: f.expertise, full: true },
  ]

  const sorted = [...data.publications].sort((a, b) => {
    let av = a[sort], bv = b[sort]
    if (sort === 'quartile') { av = Q_ORDER[av] || 9; bv = Q_ORDER[bv] || 9 }
    if (av === bv) return 0
    if (av === null || av === undefined) return 1
    if (bv === null || bv === undefined) return -1
    const cmp = typeof av === 'string' ? av.localeCompare(bv) : av - bv
    return order === 'asc' ? cmp : -cmp
  })

  const onSort = (field) => {
    if (field === sort) setOrder(order === 'asc' ? 'desc' : 'asc')
    else { setSort(field); setOrder(['title', 'journal', 'document_type', 'quartile'].includes(field) ? 'asc' : 'desc') }
  }

  // newest financial year by default; the dropdown switches between them
  const fyRow = data.by_quarter.find((r) => String(r.fy) === String(fySel)) || data.by_quarter[0]
  const quarterBars = fyRow
    ? fyRow.quarters.map((r) => ({ ...r, label: FY_QUARTERS[r.quarter - 1].label }))
    : []

  const quartileCounts = Object.fromEntries(data.quartiles.map((q) => [q.quartile, q.publications]))

  return (
    <div>
      <div className="crumb">
        <Link to="/faculty">Faculty</Link> / {f.name}
      </div>
      <div className="page-head">
        <h1 className="page-title">{f.title ? `${f.title} ` : ''}{f.name}</h1>
        <p className="page-sub">
          {[f.designation, f.department, f.campus].filter(Boolean).join(' · ')}
        </p>
      </div>

      <div className="stack">
        <div className="grid cols-4">
          <Stat label="Publications" value={num(s.publications)}
            meta={s.first_year ? `${s.first_year}–${s.last_year}` : null} />
          <Stat label="Citations" value={num(s.citations)}
            meta={`${dec(s.avg_citations)} per publication · best ${num(s.max_citations)}`} />
          <Stat label="h-index" value={num(s.h_index_from_dataset)}
            meta={`i10 ${num(s.i10_index)} · computed on publications held here`} />
          <Stat label="Q1 publications" value={num(s.q1)}
            meta={`${num(s.with_if)} with impact factor · ${num(s.open_access)} open access`} />
        </div>

        <Card title="Profile" note="IRINS master record">
          <FieldGrid items={profileFields} />
        </Card>

        <div className="grid cols-3">
          <Card title="Research metrics" note="from publications held in this database">
            <dl className="kv">
              <dt>Publications</dt><dd>{num(s.publications)}</dd>
              <dt>Citations</dt><dd>{num(s.citations)}</dd>
              <dt>Avg citations</dt><dd>{dec(s.avg_citations)}</dd>
              <dt>Most cited</dt><dd>{num(s.max_citations)}</dd>
              <dt>Distinct journals</dt><dd>{num(s.journals)}</dd>
              <dt>Q1 / Q2 / Q3 / Q4</dt>
              <dd>{num(s.q1)} / {num(s.q2)} / {num(s.q3)} / {num(s.q4)}</dd>
              <dt>With impact factor</dt><dd>{num(s.with_if)}</dd>
              <dt>Open access</dt><dd>{num(s.open_access)}</dd>
              <dt>Avg SJR</dt><dd>{dec(s.avg_sjr, 3)}</dd>
              <dt>Avg CiteScore</dt><dd>{dec(s.avg_citescore)}</dd>
              <dt>Avg JIF</dt><dd>{dec(s.avg_impact_factor)}</dd>
              <dt>Active years</dt>
              <dd>{s.first_year ? `${s.first_year}–${s.last_year}` : '--'}</dd>
            </dl>
          </Card>

          <Card title="Publications by year">
            <TimeBars data={data.by_year} xKey="year" yKey="publications" name="Publications" height={190} />
          </Card>

          <Card title="Journal quartile mix" note="SJR best quartile">
            <QuartileBar counts={quartileCounts} />
            <div style={{ marginTop: 16 }}>
              <div className="card-title" style={{ marginBottom: 8 }}>Document types</div>
              <RankedBars data={data.document_types} labelKey="document_type" valueKey="publications" name="Publications" height={110} />
            </div>
          </Card>
        </div>

        <div className="grid cols-2">
          <Card title="Year-on-year publications" note="change against the previous year">
            {data.by_year.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th className="num">Publications</th>
                      <th className="num">Change</th>
                      <th className="num">Growth</th>
                      <th className="num">Citations</th>
                      <th className="num">Q1</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...data.by_year].reverse().map((r) => (
                      <tr key={r.year}>
                        <td className="t-title">{r.year}</td>
                        <td className="num">{num(r.publications)}</td>
                        <td className="num">
                          {r.change === null ? <span className="muted">--</span> : `${r.change > 0 ? '+' : ''}${r.change}`}
                        </td>
                        <td className="num">
                          {r.growth_pct === null ? <span className="muted">--</span> : growthLabel(r.growth_pct)}
                        </td>
                        <td className="num">{num(r.citations)}</td>
                        <td className="num">{num(r.q1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="empty">No dated publications</div>}
          </Card>

          <Card title="Quarter-wise publications" note="Indian financial year · Q1 = Apr–Jun">
            {fyRow ? (
              <>
                <div className="field" style={{ marginBottom: 12, maxWidth: 220 }}>
                  <label htmlFor="fd-fy">Financial year</label>
                  <select id="fd-fy" value={fyRow.fy} onChange={(e) => setFySel(e.target.value)}>
                    {data.by_quarter.map((r) => <option key={r.fy} value={r.fy}>FY {r.label}</option>)}
                  </select>
                </div>
                <TimeBars data={quarterBars} xKey="label" yKey="publications" name="Publications" height={170} />
              </>
            ) : <div className="empty">No publication has a month-level date yet</div>}
            {s.undated > 0 && (
              <div className="note" style={{ marginTop: 10 }}>
                {num(s.undated)} of {num(s.publications)} publications have no month-level date on
                Crossref, so they are not placed in a quarter.
              </div>
            )}
          </Card>
        </div>

        <div className="grid cols-3">
          <Card title="Top journals">
            <div className="table-wrap">
              <table>
                <thead><tr><th>Journal</th><th className="num">Pubs</th><th>Q</th></tr></thead>
                <tbody>
                  {data.top_journals.map((j, i) => (
                    <tr key={i}>
                      <td className="t-wide">{j.journal}</td>
                      <td className="num">{num(j.publications)}</td>
                      <td><Quartile value={j.quartile} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Subject areas" note="from CiteScore ASJC">
            {data.top_subjects.length
              ? <RankedBars data={data.top_subjects} labelKey="subject" valueKey="publications" name="Publications" />
              : <div className="empty">No indexed subject areas</div>}
          </Card>

          <Card title="Frequent BITS co-authors">
            {data.collaborators.length ? (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Faculty</th><th>Campus</th><th className="num">Joint</th></tr></thead>
                  <tbody>
                    {data.collaborators.map((c) => (
                      <tr key={c.id}>
                        <td><Link to={`/faculty/${c.id}`} className="t-title">{c.name}</Link>
                          <div className="t-sub">{c.department}</div></td>
                        <td>{c.campus}</td>
                        <td className="num">{num(c.joint_publications)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="empty">No co-authors among BITS faculty</div>}
          </Card>
        </div>

        <Card title={`Publication list — ${num(data.publications.length)} records`} note="every column sortable">
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
                {sorted.map((p) => (
                  <tr key={p.id}>
                    <td className="num">{p.year ?? <span className="muted">--</span>}</td>
                    <td>{p.pub_date ? monthYear(p.pub_date) : <span className="muted">--</span>}</td>
                    <td className="t-wide">
                      <Link to={`/publications/${p.id}`} className="t-title">{p.title}</Link>
                      {p.is_open_access ? <span className="chip chip-oa" style={{ marginLeft: 6 }}>OA</span> : null}
                    </td>
                    <td className="t-med">{p.journal || <span className="muted">--</span>}</td>
                    <td>{p.document_type
                      ? <span className="chip chip-plain">{p.document_type}</span>
                      : <span className="muted">--</span>}</td>
                    <td><Quartile value={p.quartile} /></td>
                    <td className="num">{p.citescore === null ? <span className="muted">--</span> : dec(p.citescore, 1)}</td>
                    <td className="num">{p.impact_factor === null ? <span className="muted">--</span> : dec(p.impact_factor, 2)}</td>
                    <td className="num">{num(p.cited_by)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!sorted.length && <div className="empty">No publications recorded for this faculty member</div>}
        </Card>
      </div>
    </div>
  )
}
