import { Link, useParams } from 'react-router-dom'
import { Card, ErrorBox, FieldGrid, Quartile, Spinner, Stat } from '../components/UI'
import { dec, num } from '../format'
import { useApi } from '../useData'

const ext = (href, text) => (
  <a href={href} target="_blank" rel="noreferrer" style={{ color: 'var(--series-1)' }}>{text}</a>
)

const yesNo = (v) => (v === null || v === undefined ? null : v ? 'Yes' : 'No')

export default function PublicationDetail() {
  const { id } = useParams()
  const { data: p, error, loading } = useApi(`/publications/${id}`)

  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  if (!p) return null

  // Every column of the publication record, in a fixed order. Identical for
  // every paper -- FieldGrid prints a dash where the Scopus export had nothing,
  // so no record silently drops a row that another record shows.
  const recordFields = [
    { label: 'Title', value: p.title, full: true },
    { label: 'Year', value: p.year },
    { label: 'Document type', value: p.document_type },
    { label: 'Scopus EID', value: p.eid },
    { label: 'DOI', value: p.doi ? ext(`https://doi.org/${p.doi}`, p.doi) : null },
    { label: 'Scopus link', value: p.link ? ext(p.link, 'open in Scopus') : null },
    { label: 'Source title (as printed)', value: p.source_title },
    { label: 'Journal (master record)', value: p.journal_title },
    { label: 'Publisher (record)', value: p.publisher },
    { label: 'Publisher (master)', value: p.journal_publisher },
    { label: 'ISSN (as printed)', value: p.issn_raw },
    { label: 'ISSN (normalised)', value: p.issn_norm },
    { label: 'ISBN', value: p.isbn },
    { label: 'Volume', value: p.volume },
    { label: 'Issue', value: p.issue },
    { label: 'Article number', value: p.art_no },
    { label: 'Page start', value: p.page_start },
    { label: 'Page end', value: p.page_end },
    { label: 'Open access (as printed)', value: p.open_access },
    { label: 'Open access', value: yesNo(p.is_open_access) },
    { label: 'Cited by', value: num(p.cited_by) },
    { label: 'Publication record ID', value: p.id },
  ]

  const journalFields = [
    { label: 'Journal', value: p.journal_title, full: true },
    { label: 'Journal ISSN', value: p.journal_issn },
    { label: 'Scopus source ID', value: p.scopus_source_id },
    { label: 'SJR', value: p.sjr === null || p.sjr === undefined ? null : dec(p.sjr, 3) },
    { label: 'SJR quartile', value: p.sjr_quartile ? <Quartile value={p.sjr_quartile} /> : null },
    { label: 'Journal h-index', value: p.h_index },
    { label: 'CiteScore', value: p.citescore === null || p.citescore === undefined ? null : dec(p.citescore, 1) },
    { label: 'CiteScore quartile', value: p.cs_quartile },
    { label: 'CiteScore percentile', value: p.cs_percentile === null || p.cs_percentile === undefined ? null : dec(p.cs_percentile, 0) },
    { label: 'SNIP', value: p.snip === null || p.snip === undefined ? null : dec(p.snip, 3) },
    { label: 'Impact factor (JIF)', value: p.impact_factor === null || p.impact_factor === undefined ? null : dec(p.impact_factor, 3) },
    { label: 'JIF quartile', value: p.jif_quartile },
    { label: 'Web of Science index', value: p.wos_type },
    { label: 'Journal open access', value: p.journal_open_access },
  ]

  const provenanceFields = [
    { label: 'BITS affiliated', value: yesNo(p.is_bits) },
    {
      label: 'Attribution',
      value: p.faculty_matched
        ? 'matched to IRINS faculty'
        : <span style={{ color: 'var(--critical)' }}>awaiting review</span>,
    },
    { label: 'First seen in', value: p.first_seen_file },
    { label: 'First seen at', value: p.first_seen_at },
    { label: 'Last updated by', value: p.last_batch_file },
    { label: 'Last upload at', value: p.last_batch_at },
    { label: 'Row created', value: p.created_at },
    { label: 'Row updated', value: p.updated_at },
  ]

  const textFields = [
    { label: 'Funding details', value: p.funding_details, full: true },
    { label: 'Correspondence address', value: p.correspondence, full: true },
    { label: 'Affiliations (as exported)', value: p.affiliations_raw, full: true },
  ]

  return (
    <div>
      <div className="crumb"><Link to="/publications">Publications</Link> / {p.eid}</div>
      <div className="page-head">
        <h1 className="page-title" style={{ fontSize: 19, lineHeight: 1.35 }}>{p.title}</h1>
        <p className="page-sub">
          {[p.journal_title || p.source_title, p.year, p.document_type, p.publisher]
            .filter(Boolean).join(' · ')}
        </p>
      </div>

      <div className="stack">
        <div className="grid cols-4">
          <Stat label="Citations" value={num(p.cited_by)} meta="as of the latest upload" />
          <Stat label="Journal quartile" value={p.sjr_quartile || '--'} meta={`SJR ${dec(p.sjr, 3)} · h-index ${num(p.h_index)}`} />
          <Stat label="CiteScore" value={dec(p.citescore, 1)} meta={`SNIP ${dec(p.snip, 3)}`} />
          <Stat label="Impact factor" value={dec(p.impact_factor, 2)} meta={p.wos_type ? `${p.wos_type} · JIF ${p.jif_quartile || '--'}` : 'not in Web of Science'} />
        </div>

        <Card title="Record" note="every field on the Scopus record">
          <FieldGrid items={recordFields} />
        </Card>

        <div className="grid cols-2">
          <Card title="Journal metrics" note="SJR · CiteScore · Web of Science">
            <FieldGrid items={journalFields} min={170} />
          </Card>

          <Card title="Subject areas" note="CiteScore ASJC percentile">
            {p.subjects?.length ? (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Subject</th><th className="num">Percentile</th><th>Quartile</th></tr></thead>
                  <tbody>
                    {p.subjects.map((s) => (
                      <tr key={s.subject}>
                        <td>{s.subject}</td>
                        <td className="num">{s.percentile === null ? <span className="muted">--</span> : dec(s.percentile, 0)}</td>
                        <td><Quartile value={s.quartile} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="empty">Journal not in the CiteScore master</div>}
          </Card>
        </div>

        <Card title={`Authors (${num(p.authors.length)})`} note="BITS authors resolved against the IRINS master">
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th className="num">#</th><th>Author</th><th>Scopus ID</th><th>Affiliation</th><th>Campus</th><th>Department</th></tr>
              </thead>
              <tbody>
                {p.authors.map((a) => (
                  <tr key={a.author_seq} style={a.is_bits ? undefined : { opacity: 0.65 }}>
                    <td className="num">{a.author_seq}</td>
                    <td>
                      {a.faculty_id
                        ? <Link to={`/faculty/${a.faculty_id}`} className="t-title">{a.faculty_name}</Link>
                        : <span className="t-title">{a.full_name || a.raw_name || <span className="muted">--</span>}</span>}
                      {a.is_bits && !a.faculty_id && <div className="t-sub">BITS author, not in IRINS</div>}
                    </td>
                    <td className="t-sub">{a.scopus_author_id || '--'}</td>
                    <td className="t-wide t-sub">{a.raw_affiliation || '--'}</td>
                    <td>{a.campus || <span className="muted">--</span>}</td>
                    <td>{a.department || <span className="muted">--</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!p.authors.length && <div className="empty">No authors recorded on this publication</div>}
        </Card>

        <Card title="Abstract">
          {p.abstract
            ? <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.65 }}>{p.abstract}</p>
            : <div className="empty">No abstract in the Scopus export</div>}
        </Card>

        <Card title="Funding, correspondence and affiliations" note="as exported from Scopus">
          <FieldGrid items={textFields} />
        </Card>

        <div className="grid cols-2">
          <Card title="Provenance" note="which upload this record came from">
            <FieldGrid items={provenanceFields} min={170} />
          </Card>

          <Card title="Citation history" note="one point per weekly upload">
            {p.citation_history?.length ? (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Snapshot</th><th className="num">Cited by</th></tr></thead>
                  <tbody>
                    {p.citation_history.map((c) => (
                      <tr key={c.snapshot_date}><td>{c.snapshot_date}</td><td className="num">{num(c.cited_by)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="empty">No citation snapshots yet</div>}
          </Card>
        </div>
      </div>
    </div>
  )
}
