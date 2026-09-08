# The project in three phases

The dashboard in this repository was built in three stages. Each stage lives in
its own folder, runs on its own, holds its own copy of the data, and does one
thing the previous one could not.

The original project is untouched in the repository root; the three phase folders
are independent of it and of each other.

| | [Phase 1](phase%201/) | [Phase 2](phase%202/) | [Phase 3](phase%203/) |
|---|---|---|---|
| **What it is** | an automated pipeline | an interactive dashboard | a production system |
| **The upgrade** | replaces the manual Excel work | ask any question, not the ones the script anticipated | built for a server, not a laptop |
| **Storage** | SQLite | SQLite | MySQL 8 |
| **Interface** | a static HTML dashboard + a workbook | a live dashboard, zero-build HTML/CSS/JS | React · Vite · Recharts |
| **Setup needed** | nothing | nothing | MySQL |
| **Run it** | `./run.sh` | `./run.sh` | `./run.sh setup && ./run.sh` |
| **Lines of code** | ~1,600 | ~3,400 | ~5,800 |

Every phase reproduces the same verified numbers: 140 publications, 623 author
rows, 35,392 journals, 78,806 subject rows, 112 of 140 papers attributed to
faculty.

---

## Phase 1 — the automated pipeline

**Problem it solves:** the analysis was being done by hand in Excel. For each of
140 publications someone looked the journal up in the SJR master, the CiteScore
master and the Web of Science master, copied across six metrics, then worked out
which BITS faculty wrote it and which campus and department to credit.

**What it does:** one command, about 25 seconds. Loads the four masters and the
Scopus export into SQLite, writes a ten-sheet `output/analysed.xlsx` and a
**dashboard at `output/dashboard.html`** — one self-contained file, charts and
all, that opens by double-clicking it — and checks its own answers against the
hand-built spreadsheet, where every comparable value agrees.

The hard parts are the joins. Excel strips leading zeros from ISSNs, the three
masters each store them differently, and a journal is filed under its print ISSN
in one and its e-ISSN in another. Scopus writes the institute both as "Birla
Institute of Technology and Science" and as "BITS Pilani". Subject areas are not
in the Scopus export at all — they come from the CiteScore master's ASJC
taxonomy.

```bash
cd "phase 1" && ./run.sh
```

## Phase 2 — the interactive dashboard

**Problem it solves:** phase 1's dashboard is a snapshot. It answers the
questions someone thought of when the script was written; seeing only Hyderabad,
or only Q1 papers, or only 2026 means editing Python and re-running it.

**What it does:** puts the same data behind a filterable web dashboard. Filter by
campus, department, year, quartile, subject or document type and every KPI, chart
and table re-computes. The weekly file goes in through the browser. Every upload
writes a dated citation snapshot — which is the only way to show citation growth,
because a Scopus export only ever reports today's count.

Filters live in the URL, so a view can be bookmarked or pasted into an email.
Still no database server and no build step: the interface is plain HTML, CSS and
JavaScript, and the five chart types are drawn as SVG by hand.

```bash
cd "phase 2" && ./run.sh      # http://localhost:8000
```

## Phase 3 — the production system

**Problem it solves:** phase 2 works for one administrator on one laptop. Its
upload endpoints are open to anyone who can reach the page, its unattributed
authors can be seen but not fixed, and a new metrics vintage would overwrite the
old one.

**What it does:** MySQL, a React interface, and four new capabilities —

1. an **attribution review queue** where an admin maps an unmatched author to a
   faculty member, or rules that they are not one, with the decision stored
   against the Scopus Author ID so it applies to every past and future paper;
2. **journal metrics keyed by year**, so CiteScore 2026 sits alongside 2025 and a
   paper can be scored against either;
3. **an API key** in front of every endpoint that writes, with a banner on every
   page while one is not configured;
4. **CSV and Excel export** on every view, taking the same filters as the page,
   so the file is what you were looking at.

```bash
cd "phase 3" && ./run.sh setup && ./run.sh
```

---

## What carries through all three

**Collaborations get full credit to each campus.** A Goa–Hyderabad paper counts
as one publication for Goa and one for Hyderabad, so campus figures sum to more
than the institute total — 147 against 140 on the sample data. Standard
bibliometric practice, and it keeps every count a whole number. Each phase says
so where it prints the figures.

**Unattributed publications are kept, not dropped.** 28 of the 140 are genuine
BITS papers whose author is not in IRINS. They are counted in the institute and
campus totals, excluded from the faculty and department views that would
otherwise be wrong, and — from phase 3 — queued for an admin to map. Dropping
them would understate BITS output by about 20%.

**One row per author per paper.** The source spreadsheet flattens a multi-author
paper into delimited strings, so it cannot say which of three co-authors sits in
which of two departments. Storing the raw (author, publication) pairs is what
makes campus totals, department drill-downs and per-professor pages all
answerable from the same data.
