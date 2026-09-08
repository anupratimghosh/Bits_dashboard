import { useState } from 'react'
import { Card, ErrorBox, Spinner, Stat } from '../components/UI'
import { num } from '../format'
import { post, upload } from '../api'
import { useApi } from '../useData'

const MASTERS = [
  { kind: 'irins', label: 'IRINS faculty master', hint: 'faculty name, campus, department, Scopus Author ID' },
  { kind: 'sjr', label: 'SJR journal master', hint: 'SJR score, best quartile, h-index' },
  { kind: 'citescore', label: 'CiteScore master', hint: 'CiteScore, SNIP, ASJC subject areas' },
  { kind: 'wos', label: 'Web of Science master', hint: 'Journal Impact Factor, JIF quartile, index type' },
]

export default function Upload() {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  // which card the outcome belongs to -- without this a master upload's result
  // and errors render under the weekly Scopus card
  const [target, setTarget] = useState(null)
  const [reload, setReload] = useState(0)
  const batches = useApi('/upload/batches', { limit: 15, _r: reload })
  const stats = useApi('/admin/stats', { _r: reload })

  const runResync = async () => {
    setBusy(true); setError(null); setResult(null); setTarget('masters')
    try {
      const r = await post('/admin/resync')
      setResult({ resync: r })
      setReload((x) => x + 1)
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  const send = async (path, file, extra = {}, where = 'scopus') => {
    setBusy(true); setError(null); setResult(null); setTarget(where)
    try {
      const fd = new FormData()
      fd.append('file', file)
      Object.entries(extra).forEach(([k, v]) => fd.append(k, v))
      setResult(await upload(path, fd))
      setReload((r) => r + 1)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const s = stats.data

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Data upload</h1>
        <p className="page-sub">
          Drop this week's Scopus export here. Records are matched on their Scopus
          EID, so re-uploading the same file or an overlapping export refreshes
          existing publications instead of duplicating them.
        </p>
      </div>

      {s && (
        <div className="grid cols-4" style={{ marginBottom: 16 }}>
          <Stat label="Publications in database" value={num(s.bits_publications)}
            meta={`${num(s.attributed_publications)} attributed to faculty`} />
          <Stat label="Faculty on roster" value={num(s.faculty)}
            meta={`${num(s.faculty_with_scopus_id)} with a Scopus ID`} />
          <Stat label="Journals with metrics" value={num(s.journals)} meta="SJR + CiteScore + WoS" />
          <Stat label="Awaiting review" value={num(s.open_queue)} meta="unattributed BITS authors" />
        </div>
      )}

      <div className="stack">
        <Card title="Weekly Scopus export" note="the routine upload">
          <input
            type="file" accept=".xlsx,.xls" disabled={busy}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) send('/upload/scopus', f); e.target.value = '' }}
          />
          <div className="note" style={{ marginTop: 10 }}>
            The file must be a Scopus export containing at least
            <strong> Authors</strong>, <strong>Title</strong>, <strong>Year</strong>,
            <strong> Source title</strong> and <strong>EID</strong>. Citation counts
            are snapshotted on every upload, which is what builds the citation trend
            over time.
          </div>
          {busy && target === 'scopus' && <Spinner label="Processing…" />}
          {target === 'scopus' && <ErrorBox error={error} />}
          {target === 'scopus' && result?.resync && (
            <div className="note" style={{ marginTop: 10, borderColor: 'var(--good)' }}>
              ✓ Re-matched {num(result.resync.authors_checked)} author records —
              {' '}<strong>{num(result.resync.authors_relinked)}</strong> relinked
              across <strong>{num(result.resync.publications_touched)}</strong> publications.
            </div>
          )}
          {target === 'scopus' && result && result.total !== undefined && (
            <div className="note" style={{ marginTop: 10, borderColor: 'var(--good)' }}>
              ✓ {num(result.total)} rows processed — <strong>{num(result.new)}</strong> new,
              {' '}<strong>{num(result.updated)}</strong> updated,
              {' '}<strong>{num(result.unmatched)}</strong> without a faculty match
              {result.non_bits ? `, ${num(result.non_bits)} with no BITS affiliation` : ''}.
            </div>
          )}
        </Card>

        <Card title="Reference masters" note="annual refresh, not weekly">
          <div className="grid cols-2">
            {MASTERS.map((m) => (
              <div key={m.kind} style={{ padding: '8px 0' }}>
                <div className="t-title">{m.label}</div>
                <div className="t-sub" style={{ marginBottom: 6 }}>{m.hint}</div>
                <input
                  type="file" accept=".xlsx,.xls" disabled={busy}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) send(`/upload/master/${m.kind}`, f, { metric_year: 2025 }, 'masters'); e.target.value = '' }}
                />
              </div>
            ))}
          </div>
          {busy && target === 'masters' && <Spinner label="Processing…" />}
          {target === 'masters' && <ErrorBox error={error} />}
          {target === 'masters' && result && (
            <div className="note" style={{ marginTop: 10, borderColor: 'var(--good)' }}>
              ✓ {result.resync
                ? `Loaded, and re-matched ${num(result.resync.authors_checked)} author records (${num(result.resync.authors_relinked)} relinked).`
                : 'Loaded.'}
            </div>
          )}
          <div className="note" style={{ marginTop: 10 }}>
            An IRINS upload re-runs author matching automatically, so transfers and
            newly-added faculty take effect immediately across existing publications.
            A master whose columns have been renamed is <strong>refused</strong> rather
            than loaded — the error names the column that moved.
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn" onClick={runResync} disabled={busy}>
              Re-run faculty matching now
            </button>
            <span className="muted" style={{ fontSize: 12.5 }}>
              Only needed if a master was loaded from the command line.
            </span>
          </div>
        </Card>

        <Card title="Upload history">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">#</th><th>File</th><th>Kind</th><th>When</th>
                  <th className="num">Rows</th><th className="num">New</th>
                  <th className="num">Updated</th><th className="num">Unmatched</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {(batches.data || []).map((b) => (
                  <tr key={b.id}>
                    <td className="num">{b.id}</td>
                    <td className="t-title">{b.filename}</td>
                    <td><span className="chip chip-plain">{b.kind}</span></td>
                    <td className="t-sub">{b.uploaded_at}</td>
                    <td className="num">{num(b.rows_total)}</td>
                    <td className="num">{num(b.rows_new)}</td>
                    <td className="num">{num(b.rows_updated)}</td>
                    <td className="num">{num(b.rows_unmatched)}</td>
                    <td style={{ color: b.status === 'success' ? 'var(--good)' : 'var(--critical)' }}>{b.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  )
}
