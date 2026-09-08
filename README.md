# BITS Research Publication Analytics Dashboard

A web dashboard over BITS Pilani's Scopus publication record, enriched with IRINS
faculty data and journal metrics from SJR, CiteScore and Web of Science. Built
around a weekly Scopus upload: drop the file in, and every KPI, chart and table
updates.

**Stack** — MySQL · FastAPI · SQLAlchemy Core · pandas · React · Vite · Recharts

![Executive summary](docs/img/overview.png)

---

## Contents

- [Quick start](#quick-start)
- [The weekly workflow](#the-weekly-workflow)
- [What the dashboard shows](#what-the-dashboard-shows)
- [How the data joins together](#how-the-data-joins-together)
- [Database schema](#database-schema)
- [Two decisions worth knowing about](#two-decisions-worth-knowing-about)
- [Updating the master sheets](#updating-the-master-sheets)
- [API reference](#api-reference)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Before this goes on a server](#before-this-goes-on-a-server)

---

## Quick start

### Prerequisites

| Need | Version | Check with |
|---|---|---|
| Python | 3.11+ | `python3 --version` |
| Node.js | 20+ | `node --version` |
| MySQL | 8.0+ | `mysql --version` |

On macOS, MySQL comes from Homebrew:

```bash
brew install mysql
brew services start mysql
```

### First-time setup

```bash
# 1. Python environment
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# 2. Point the app at your MySQL (skip the password line if root has none)
cp .env.example .env
# then edit .env and set BITS_DB_PASSWORD to your MySQL root password

# 3. Create the database and its 14 tables
mysql -u root -p < backend/sql/schema.sql

# 4. Load the reference masters and the sample Scopus file (~50 seconds)
.venv/bin/python backend/load_data.py --all

# 5. Build the frontend
cd frontend && npm install && npm run build && cd ..
```

Step 4 reads from the `Master File/` directory and `Scopus_raw.xlsx`. Expected
output:

```
Loading BITS research data
  IRINS faculty  ... {'faculty_rows': 1094, 'with_scopus_id': 1030}
  SJR master     ... {'journals': 32186}
  CiteScore      ... {'journals': 32075, 'subject_rows': 78810}
  Web of Science ... {'journals': 22643}
  Scopus export  ... {'total': 140, 'new': 140, 'updated': 0, 'unmatched': 28}
```

### Running it

```bash
./run.sh          # one process: API + built UI on http://localhost:8000
./run.sh dev      # API on :8000, Vite hot-reload UI on :5173
```

Use `dev` while changing frontend code; use the default for everything else.
Interactive API docs live at <http://localhost:8000/docs>.

To load individual files rather than everything:

```bash
.venv/bin/python backend/load_data.py --scopus path/to/export.xlsx
.venv/bin/python backend/load_data.py --irins path/to/faculty.xlsx
.venv/bin/python backend/load_data.py --citescore path/to/cs.xlsx --year 2026
```

---

## The weekly workflow

1. Export the week's BITS-affiliated records from Scopus as `.xlsx`.
2. Open **Upload**, drop the file in.
3. If the **Attribution review** badge shows new entries, work through them.

Publications are upserted on their **Scopus EID**. Re-uploading the same file, or
uploading an export that overlaps last week's, refreshes existing records rather
than duplicating them — so there is no need to trim the export first, and a
mistaken double-upload is harmless.

Every upload also writes a **dated citation snapshot**. This matters: a Scopus
export only ever reports today's citation count, so without snapshots there is no
way to show citation growth. The "Citations over time" card appears on the
executive summary once you have two or more uploads.

Each upload is recorded in `upload_batch` with counts of new, updated and
unmatched rows — visible as an audit trail at the bottom of the Upload page.

### Refreshing the reference masters

IRINS, SJR, CiteScore and Web of Science change **annually**, not weekly. They
have their own upload controls on the same page. After refreshing IRINS,
re-upload the latest Scopus file so newly-added faculty pick up their existing
publications — author matching re-runs on every Scopus ingest.

`journal_metric` is keyed by year, so loading CiteScore 2026 sits alongside 2025
rather than overwriting it.

---

## What the dashboard shows

**Executive summary** — headline KPIs (total publications, this year vs last,
citations, faculty publishing, Q1/Q2 counts, publications with an impact factor,
average CiteScore and SJR), publications by year, quartile mix by year, campus and
document-type breakdowns, top subject areas and top journals.

**Campuses** — Pilani, Goa, Hyderabad and Dubai side by side across every measure,
plus the quartile mix per campus.

**Departments** — pick a campus to see only its departments; pick a department for
a full drill-down with publications by year, quartile mix, top publishing faculty,
top journals and top subject areas.

![Department analysis](docs/img/department.png)

**Faculty** — search the roster, then open any professor's profile: publications,
citations, h-index, quartile mix, document types, top journals, subject areas,
frequent BITS co-authors, and the full sortable publication list.

![Faculty profile](docs/img/faculty.png)

**Publications** — every record with its journal metrics joined in. Sorting and
filtering run server-side across the whole result set, not just the visible page.

**Attribution review** — the queue of BITS authors who could not be matched to
IRINS (see [below](#two-decisions-worth-knowing-about)).

![Attribution review](docs/img/review.png)

Filters live in the URL, so any view can be bookmarked or pasted into an email and
it reopens exactly as you left it.

---

## How the data joins together

```
Scopus export (.xlsx)
  │
  ├── Author(s) ID ────────► faculty.scopus_author_id (IRINS) ──► campus, department
  │                          └── no match? → attribution review queue
  │
  └── ISSN (normalised) ───► journal ──┬─► journal_metric  ──► SJR, quartile, h-index
                                       │                       CiteScore, SNIP
                                       │                       Impact Factor, JIF quartile
                                       └─► journal_subject ──► ASJC subject areas
```

Two normalisations do the heavy lifting, and both were needed to make the joins
land:

**ISSN.** Excel strips leading zeros, so `02194988` arrives as `2194988`. The three
masters each store ISSNs differently — Web of Science hyphenates them, SJR and
CiteScore pack several into one semicolon-separated cell. Everything is reduced to
one zero-padded 8-character key, and every variant a master lists is pointed at the
same journal row through `journal_issn`. That is what lets a Scopus record carrying
only a print ISSN pick up metrics filed under the e-ISSN.

**BITS affiliation.** Scopus writes the institute both as "Birla Institute of
Technology and Science" and as "BITS Pilani". Both forms are matched — the
abbreviation case-sensitively, so the ordinary English word "bits" cannot
masquerade as an affiliation. Matching only the spelled-out form silently drops
real BITS papers.

**Subject areas** are not in the Scopus export at all. They come from the CiteScore
master, which ships one row per journal per ASJC subject area — 78,844 rows in the
file, 78,806 after ISSN resolution, covering 32,075 journals. Per-subject
percentiles and quartiles go to `journal_subject`; the best-percentile subject
becomes the journal's headline CiteScore quartile.

### Verification

On the supplied data this reproduces the hand-built `analysed.xlsx` exactly:

| Column | Matched |
|---|---|
| SJR | 121 / 121 |
| CiteScore | 123 / 123 |
| SNIP | 121 / 121 |
| h-index | 122 / 122 |
| Impact Factor | 95 / 95 |
| WoS index type | 140 / 140 |
| Faculty attribution | 112 of 140 publications |

---

## Database schema

| Table | Rows (sample) | Holds |
|---|---|---|
| `campus`, `department` | 4, 16 | lookups |
| `faculty` | 1,094 | IRINS roster, keyed on `scopus_author_id` |
| `journal` | 35,392 | one row per journal |
| `journal_issn` | — | every ISSN variant → one journal |
| `journal_metric` | 35,392 | metrics per journal **per year** |
| `journal_subject` | 78,806 | CiteScore ASJC subject areas |
| `publication` | 140 | one row per paper, unique on `eid` |
| `publication_author` | 623 | **one row per author per paper** |
| `publication_citation` | 140 | dated citation snapshots |
| `upload_batch` | 1 | audit trail for every upload |
| `unmatched_author` | — | review queue |
| `author_alias` | — | permanent Scopus ID → faculty fixes |
| `author_ignored` | — | permanent "not a faculty member" rulings |

### Why `publication_author` matters

The source spreadsheet flattens multi-author papers into delimited strings:

```
BITS_Author:  Arshad Javed, Sanket Goel, Satish Kumar Dubey
Campus:       Hyderabad
Department:   Electrical and Electronics Engineering/Mechanical Engineering
```

Three faculty, two departments, two different delimiters, and the lists are
de-duplicated — so it is impossible to recover which author belongs to which
department. Storing one row per author per paper is what makes campus totals,
department drill-downs and the per-professor page all answerable from the same
data, and it is why the counting rule below is a query change rather than a
migration.

---

## Two decisions worth knowing about

### Collaborations get full credit to each campus

A Goa–Hyderabad paper counts as **one publication for Goa and one for Hyderabad**.
Campus figures therefore sum to more than the institute total (147 vs 140 on the
sample data), and the UI says so on the relevant cards.

This is standard bibliometric practice and keeps every count an integer. Because
`publication_author` stores the raw (author, publication) pairs, switching to
fractional credit later is an analytics-layer change.

### Unattributed publications are kept, not dropped

28 of the 140 sample publications are genuine BITS papers whose author is not in
IRINS, or whose IRINS record has no Scopus Author ID. They:

- **are counted** in institute and campus totals (campus is parsed from the
  affiliation string, which resolves for 100% of the sample)
- **are excluded** from faculty and department views, which would otherwise be wrong
- **appear** in the Attribution review queue for an admin to map

Dropping them would understate BITS output by roughly 20%. A mapping is stored
against the Scopus Author ID in `author_alias`, so it applies retroactively to
every past publication by that author and automatically to every future one. A
dismissal is stored the same way, in `author_ignored`, so it is equally
permanent.

The queue defaults to **priority only** — publications where *no* author could be
matched, i.e. the ones missing entirely from faculty and department views. Turning
that off also lists co-authors on already-attributed papers, most of whom are
research scholars rather than faculty and can be dismissed with "Not a faculty
member".

---

## Updating the master sheets

The masters get re-issued with columns added, columns renamed and values
corrected. Here is exactly what each of those does.

### Columns added

**Ignored, safely.** Loaders read the columns they know by name, so anything
extra is skipped and reported back as a count:

```
SJR master ... {'journals': 32186, 'metric_year': 2025, 'columns_ignored': 20}
```

A new column is not *used*, though. To capture one, add it in three places: a
column in `journal_metric` (or `faculty`), an entry in the loader's `_SPEC`, and
the field in the loader's row dict.

### Columns renamed

Headers are matched case- and punctuation-insensitively against a list of known
aliases, so `H index` → `H-Index` → `h_index` all resolve to the same field.

If a **required** column cannot be resolved under any alias, the load is
**refused** and nothing is written:

```
SJR master: expected column(s) not found: quartile.
The file has: Rank, Sourceid, Title, Type, Issn, Publisher, ...
If the column was renamed, add the new name to the loader's column spec.
```

This matters more than it looks. Without the check, `SJR Best Quartile` becoming
`Best Quartile` writes NULL over all 31,086 quartiles, the load reports success,
and every Q1/Q2 figure on the dashboard silently drops to zero. Refusing the file
is the safe failure. The fix is one line — add the new header to the relevant
`_SPEC` list in `backend/app/ingest/masters.py`:

```python
_SJR_SPEC = {
    "quartile": ["SJR Best Quartile", "Best Quartile", "Quartile"],   # add here
    ...
}
```

Required columns per master:

| Master | Must resolve |
|---|---|
| IRINS | `name`, `scopus_id`, `campus`, `department` |
| SJR | `issn`, `sjr`, `quartile`, `h_index` |
| CiteScore | `citescore`, `snip`, and at least one ISSN column |
| Web of Science | `jif`, and at least one ISSN column |

Failed uploads are recorded in `upload_batch` with `status = 'failed'` and the
error message, so a rejected file is visible in the upload history rather than
silently absent.

### Values modified

Corrections propagate on reload. Each master owns only its own columns in
`journal_metric` — reloading SJR updates `sjr`, `sjr_quartile` and `h_index` and
leaves CiteScore's and WoS's columns untouched. Journals are matched by ISSN, so
no duplicate rows appear.

### Faculty moved, added or removed (IRINS)

`publication_author` stores each author's campus and department alongside the
faculty link — that is what makes campus and department aggregates a single join.
Those copies have to be rewritten when IRINS changes, or a professor's profile
would say Goa while their publications still credited Pilani.

**An IRINS upload does this automatically.** After loading, faculty matching
re-runs across every publication already in the database:

```
irins  ... {'faculty_rows': 1096, 'with_scopus_id': 1032}
resync ... {'authors_checked': 623, 'authors_relinked': 6, 'publications_touched': 6}
```

So:

- **A professor transfers campus or department** → their existing publications
  move with them.
- **A professor is added to IRINS** → their publications are attributed
  immediately and they leave the attribution review queue. No Scopus re-upload.
- **A Scopus Author ID is reassigned** to a different person → handled; the ID is
  released from its previous owner before the new mapping is written.
- **A professor is removed from IRINS** → their publications return to the review
  queue rather than vanishing.
- **Entries dismissed as "Not a faculty member"** stay dismissed — across a
  re-sync *and* across the weekly Scopus upload. The ruling is recorded in
  `author_ignored` against the Scopus Author ID, the same way a match is
  recorded in `author_alias`, because the weekly ingest rebuilds
  `publication_author` wholesale and the queue row is deleted with it. Neither
  path ever reopens an admin's judgement call.

If a master was loaded from the command line rather than the web page, run the
re-sync yourself — **Upload → Re-run faculty matching now**, or:

```bash
curl -X POST localhost:8000/api/admin/resync
```

### A new metrics year

Load the file with a year and it sits alongside the existing one rather than
replacing it:

```bash
.venv/bin/python backend/load_data.py --citescore "CiteScore 2026.xlsx" --year 2026
```

A **Metrics year** dropdown then appears in the filter bar (it stays hidden while
only one vintage is loaded). Historical publications keep whatever vintage you
select, so you can compare a paper against 2025 and 2026 journal metrics without
reloading anything. To change the default, set `BITS_METRIC_YEAR`.

### Recommended order

1. Upload the master.
2. Read the response — check `columns_ignored` and any `columns_not_found`.
3. For a metrics master, switch the **Metrics year** filter to the new vintage.
4. For IRINS, check whether the **Attribution review** badge dropped.

---

## API reference

Interactive docs at `/docs`. Every analytics endpoint accepts the same filter set:

`year_from` · `year_to` · `campus_id` · `department_id` · `faculty_id` ·
`quartile` · `document_type` · `open_access` · `has_if` · `subject` ·
`journal_id` · `search` · `unmatched_only` · `metric_year`

| Endpoint | Returns |
|---|---|
| `GET /api/health` | liveness + publication count |
| `GET /api/filters` | dropdown options (campuses, departments per campus, years, types) plus `default_metric_year`, the vintage the API uses when the caller sends none |
| `GET /api/overview` | executive KPIs |
| `GET /api/analytics/by-year` | publications, citations, quartiles and growth per year |
| `GET /api/analytics/by-campus` | every measure per campus |
| `GET /api/analytics/by-department` | every measure per department |
| `GET /api/analytics/by-quartile` | quartile distribution |
| `GET /api/analytics/by-document-type` | document-type distribution |
| `GET /api/analytics/by-open-access` | open access vs subscription |
| `GET /api/analytics/top-journals` | ranked journals |
| `GET /api/analytics/top-subjects` | ranked ASJC subject areas |
| `GET /api/analytics/top-faculty` | ranked faculty (scoped to the selected campus/department) |
| `GET /api/analytics/citation-trend` | citations per upload snapshot |
| `GET /api/faculty` | roster; `sort`, `order`, `page`, `name`, `publishing_only` |
| `GET /api/faculty/{id}` | full profile: summary, by year, quartiles, journals, subjects, co-authors, publications |
| `GET /api/publications` | sortable list; `sort`, `order`, `page`, `page_size` |
| `GET /api/publications/{id}` | full record with authors, subjects, citation history |
| `GET /api/departments/{id}` | department drill-down |
| `GET /api/journals/{id}` | journal with metrics and subject areas |
| `POST /api/upload/scopus` | weekly upload (multipart `file`) |
| `POST /api/upload/master/{kind}` | `irins` \| `sjr` \| `citescore` \| `wos` |
| `GET /api/upload/batches` | upload history |
| `POST /api/admin/resync` | re-apply faculty matching to all stored publications |
| `GET /api/admin/stats` | database counts and last upload |
| `GET /api/admin/unmatched` | review queue |
| `POST /api/admin/unmatched/{id}/resolve` | map to a faculty member (body: `{"faculty_id": N}`) |
| `POST /api/admin/unmatched/{id}/ignore` | dismiss permanently (every publication by that author, and all future uploads) |

---

## Project layout

```
TA_Project/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app; also serves the built frontend
│   │   ├── config.py          env-driven settings
│   │   ├── db.py              engine + query helper (coerces MySQL Decimals)
│   │   ├── filters.py         the shared WHERE-clause builder
│   │   ├── deps.py            filter query params
│   │   ├── ingest/
│   │   │   ├── normalize.py   ISSN, campus, BITS-affiliation, numeric cleaning
│   │   │   ├── masters.py     IRINS / SJR / CiteScore / WoS loaders
│   │   │   └── scopus.py      the weekly upsert
│   │   └── routers/
│   │       ├── analytics.py   KPIs and grouped aggregates
│   │       ├── faculty.py     roster and profile
│   │       ├── publications.py list, record, department, journal
│   │       └── admin.py       uploads and review queue
│   ├── sql/schema.sql         the full schema
│   ├── load_data.py           CLI loader
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx            routing and sidebar
│       ├── api.js             fetch wrapper
│       ├── useData.js         data hooks + URL-backed filters
│       ├── format.js          number formatting and palette roles
│       ├── index.css          design tokens, light and dark
│       ├── components/        Charts, FilterBar, UI primitives
│       └── pages/             one file per screen
├── Master File/               IRINS, SJR, CiteScore, WoS sources
├── Scopus_raw.xlsx            sample weekly export
├── analysed.xlsx              the manual output this replaces
└── run.sh
```

---

## Configuration

Read from the environment, or from a `.env` file in the project root (copy
`.env.example`). Real environment variables win over `.env`, and `.env` is
gitignored so credentials never get committed.

| Variable | Default | Purpose |
|---|---|---|
| `BITS_DB_USER` | `root` | MySQL user |
| `BITS_DB_PASSWORD` | *(empty)* | MySQL password |
| `BITS_DB_HOST` | `127.0.0.1` | MySQL host |
| `BITS_DB_PORT` | `3306` | MySQL port |
| `BITS_DB_NAME` | `bits_research` | database name |
| `BITS_METRIC_YEAR` | `2025` | metrics vintage the dashboard reads by default |

---

## Troubleshooting

**`Can't connect to MySQL server`** — `brew services start mysql`, then confirm
with `mysqladmin -u root ping`.

**`Access denied for user 'root'`** — set `BITS_DB_PASSWORD` in `.env` (or in the
environment) to your MySQL root password. The `mysql` CLI needs `-p` as well:
`mysql -u root -p < backend/sql/schema.sql`.

**`Not a Scopus export - missing columns: …`** — the upload must contain at least
`Authors`, `Title`, `Year`, `Source title` and `EID`. Export from Scopus with all
fields selected.

**A publication shows no SJR / CiteScore / impact factor** — the journal's ISSN is
not in that master, or the record has no ISSN at all (common for book chapters and
some conference proceedings). 16 of the 140 sample records have no ISSN.

**A professor's page is empty** — they may be in the review queue rather than
matched. Check **Attribution review**, or confirm their Scopus Author ID is filled
in on their IRINS record.

**"Citations over time" is missing** — it needs at least two uploads. It appears
after your second weekly file.

**A master upload was refused with "expected column(s) not found"** — a column
was renamed in the new file. Add the new header to that loader's `_SPEC` list in
`backend/app/ingest/masters.py` and re-upload. See
[Updating the master sheets](#updating-the-master-sheets).

**A professor's campus or department looks wrong after an IRINS update** — run
**Upload → Re-run faculty matching now**. This happens only when IRINS was loaded
from the command line; the web upload re-syncs automatically.

**Frontend changes aren't showing** — `./run.sh` serves the *built* bundle. Either
re-run `npm run build`, or use `./run.sh dev` for hot reload.

**Starting over** — to wipe and reload from scratch:

```bash
mysql -u root -p -e "DROP DATABASE IF EXISTS bits_research;"
mysql -u root -p < backend/sql/schema.sql
.venv/bin/python backend/load_data.py --all
```

---

## Before this goes on a server

Two things are fine on a laptop and not fine on a shared machine:

1. **`/api/upload/*` and `/api/admin/*` are unauthenticated.** Anyone who can reach
   the page can overwrite the publication data. Put authentication in front of them.
2. **MySQL root has no password** in a default Homebrew install. Run
   `mysql_secure_installation` and set `BITS_DB_PASSWORD`.

Also worth knowing:

- The per-faculty **h-index is computed over the publications held in this
  database**, and is labelled as such in the UI. It is not the author's lifetime
  Scopus h-index, which would need the full publication history.
- **"Quartile" means the SJR best quartile** throughout the dashboard. CiteScore
  and JIF quartiles are stored separately and shown on the publication page.
- CORS currently allows `localhost:5173` only; add your server's origin in
  `backend/app/main.py` if the frontend is served from a different host.
