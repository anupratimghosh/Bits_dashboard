-- BITS Research Publication Analytics Dashboard
-- MySQL 8+/9+  |  utf8mb4 throughout (author names, titles, abstracts)

CREATE DATABASE IF NOT EXISTS bits_research
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE bits_research;

-- ---------------------------------------------------------------- lookups

CREATE TABLE IF NOT EXISTS campus (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  name      VARCHAR(64) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS department (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  name      VARCHAR(160) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- faculty (IRINS)

CREATE TABLE IF NOT EXISTS faculty (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  expert_id         INT NULL UNIQUE,               -- IRINS Expert_ID
  scopus_author_id  VARCHAR(32) NULL UNIQUE,       -- primary matching key
  name              VARCHAR(255) NOT NULL,
  title             VARCHAR(32) NULL,
  designation       VARCHAR(96) NULL,
  email             VARCHAR(255) NULL,
  campus_id         INT NULL,
  department_id     INT NULL,
  orcid_id          VARCHAR(64) NULL,
  researcher_id     VARCHAR(64) NULL,
  google_scholar_id VARCHAR(96) NULL,
  expertise         TEXT NULL,
  qualification     VARCHAR(128) NULL,
  is_active         TINYINT(1) NOT NULL DEFAULT 1,
  CONSTRAINT fk_fac_campus FOREIGN KEY (campus_id) REFERENCES campus(id),
  CONSTRAINT fk_fac_dept   FOREIGN KEY (department_id) REFERENCES department(id),
  INDEX ix_fac_name (name),
  INDEX ix_fac_campus_dept (campus_id, department_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- journals

CREATE TABLE IF NOT EXISTS journal (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  issn_norm         VARCHAR(8) NULL UNIQUE,        -- normalised, zero-padded
  scopus_source_id  BIGINT NULL,
  title             VARCHAR(512) NOT NULL,
  publisher         VARCHAR(255) NULL,
  INDEX ix_jrnl_title (title(191)),
  INDEX ix_jrnl_source (scopus_source_id)
) ENGINE=InnoDB;

-- every ISSN/E-ISSN variant that points at a journal (masters list several)
CREATE TABLE IF NOT EXISTS journal_issn (
  issn_norm   VARCHAR(8) NOT NULL PRIMARY KEY,
  journal_id  INT NOT NULL,
  CONSTRAINT fk_jissn_journal FOREIGN KEY (journal_id) REFERENCES journal(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- one row per journal per metrics vintage (CiteScore 2025, SJR 2025, WoS 2025 ...)
CREATE TABLE IF NOT EXISTS journal_metric (
  journal_id    INT NOT NULL,
  metric_year   SMALLINT NOT NULL,
  sjr           DECIMAL(10,3) NULL,
  sjr_quartile  VARCHAR(4) NULL,        -- SJR Best Quartile
  h_index       INT NULL,
  citescore     DECIMAL(10,2) NULL,
  snip          DECIMAL(10,3) NULL,
  cs_quartile   VARCHAR(4) NULL,        -- CiteScore quartile (best subject area)
  cs_percentile DECIMAL(5,1) NULL,
  impact_factor DECIMAL(10,3) NULL,     -- WoS JIF
  jif_quartile  VARCHAR(4) NULL,
  wos_type      VARCHAR(16) NULL,       -- SCIE / SSCI / ESCI / AHCI
  open_access   VARCHAR(16) NULL,
  PRIMARY KEY (journal_id, metric_year),
  CONSTRAINT fk_jm_journal FOREIGN KEY (journal_id) REFERENCES journal(id) ON DELETE CASCADE,
  INDEX ix_jm_quartile (metric_year, sjr_quartile)
) ENGINE=InnoDB;

-- CiteScore ships one row per journal x subject area: this is our subject taxonomy
CREATE TABLE IF NOT EXISTS journal_subject (
  journal_id   INT NOT NULL,
  metric_year  SMALLINT NOT NULL,
  asjc_code    INT NOT NULL,
  subject      VARCHAR(160) NOT NULL,
  percentile   DECIMAL(5,1) NULL,
  quartile     VARCHAR(4) NULL,
  PRIMARY KEY (journal_id, metric_year, asjc_code),
  CONSTRAINT fk_js_journal FOREIGN KEY (journal_id) REFERENCES journal(id) ON DELETE CASCADE,
  INDEX ix_js_subject (subject)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- uploads

CREATE TABLE IF NOT EXISTS upload_batch (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  filename       VARCHAR(512) NOT NULL,
  kind           VARCHAR(32) NOT NULL DEFAULT 'scopus',   -- scopus | irins | sjr | citescore | wos
  uploaded_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  uploaded_by    VARCHAR(128) NULL,
  rows_total     INT NOT NULL DEFAULT 0,
  rows_new       INT NOT NULL DEFAULT 0,
  rows_updated   INT NOT NULL DEFAULT 0,
  rows_unmatched INT NOT NULL DEFAULT 0,
  status         VARCHAR(24) NOT NULL DEFAULT 'pending',  -- pending|success|failed
  message        TEXT NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------- publications

CREATE TABLE IF NOT EXISTS publication (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  eid                 VARCHAR(64) NOT NULL UNIQUE,   -- idempotency key for weekly upserts
  title               VARCHAR(1024) NOT NULL,
  year                SMALLINT NULL,
  document_type       VARCHAR(64) NULL,
  doi                 VARCHAR(255) NULL,
  link                VARCHAR(1024) NULL,
  abstract            MEDIUMTEXT NULL,
  cited_by            INT NOT NULL DEFAULT 0,
  journal_id          INT NULL,
  source_title        VARCHAR(512) NULL,             -- as printed on the record
  issn_raw            VARCHAR(64) NULL,
  issn_norm           VARCHAR(8) NULL,
  isbn                VARCHAR(64) NULL,
  volume              VARCHAR(64) NULL,
  issue               VARCHAR(64) NULL,
  art_no              VARCHAR(64) NULL,
  page_start          VARCHAR(32) NULL,
  page_end            VARCHAR(32) NULL,
  publisher           VARCHAR(255) NULL,
  open_access         VARCHAR(255) NULL,
  is_open_access      TINYINT(1) NOT NULL DEFAULT 0,
  funding_details     TEXT NULL,
  correspondence      TEXT NULL,
  affiliations_raw    MEDIUMTEXT NULL,
  is_bits             TINYINT(1) NOT NULL DEFAULT 0,
  faculty_matched     TINYINT(1) NOT NULL DEFAULT 0, -- 0 => shows up in the review queue
  first_seen_batch_id INT NULL,
  last_batch_id       INT NULL,
  created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_pub_journal FOREIGN KEY (journal_id) REFERENCES journal(id),
  CONSTRAINT fk_pub_batch1  FOREIGN KEY (first_seen_batch_id) REFERENCES upload_batch(id),
  CONSTRAINT fk_pub_batch2  FOREIGN KEY (last_batch_id) REFERENCES upload_batch(id),
  INDEX ix_pub_year (year),
  INDEX ix_pub_doctype (document_type),
  INDEX ix_pub_matched (faculty_matched),
  INDEX ix_pub_title (title(191))
) ENGINE=InnoDB;

-- the table that keeps multi-author papers honest: one row per author per paper
CREATE TABLE IF NOT EXISTS publication_author (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  publication_id    INT NOT NULL,
  author_seq        SMALLINT NOT NULL,
  scopus_author_id  VARCHAR(32) NULL,
  raw_name          VARCHAR(255) NULL,
  full_name         VARCHAR(255) NULL,
  raw_affiliation   TEXT NULL,
  faculty_id        INT NULL,                -- NULL => not in IRINS
  is_bits           TINYINT(1) NOT NULL DEFAULT 0,
  campus_id         INT NULL,                -- IRINS where matched, parsed otherwise
  department_id     INT NULL,
  UNIQUE KEY uq_pa (publication_id, author_seq),
  CONSTRAINT fk_pa_pub  FOREIGN KEY (publication_id) REFERENCES publication(id) ON DELETE CASCADE,
  CONSTRAINT fk_pa_fac  FOREIGN KEY (faculty_id) REFERENCES faculty(id),
  CONSTRAINT fk_pa_camp FOREIGN KEY (campus_id) REFERENCES campus(id),
  CONSTRAINT fk_pa_dept FOREIGN KEY (department_id) REFERENCES department(id),
  INDEX ix_pa_faculty (faculty_id),
  INDEX ix_pa_scopus (scopus_author_id),
  INDEX ix_pa_bits (is_bits, campus_id, department_id)
) ENGINE=InnoDB;

-- citation counts move every week; keep the trend instead of overwriting it
CREATE TABLE IF NOT EXISTS publication_citation (
  publication_id  INT NOT NULL,
  snapshot_date   DATE NOT NULL,
  cited_by        INT NOT NULL,
  batch_id        INT NULL,
  PRIMARY KEY (publication_id, snapshot_date),
  CONSTRAINT fk_pc_pub FOREIGN KEY (publication_id) REFERENCES publication(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- admin review queue: BITS papers whose author could not be resolved to IRINS
CREATE TABLE IF NOT EXISTS unmatched_author (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  publication_id      INT NOT NULL,
  publication_author_id INT NOT NULL,
  scopus_author_id    VARCHAR(32) NULL,
  raw_name            VARCHAR(255) NULL,
  raw_affiliation     TEXT NULL,
  guessed_campus_id   INT NULL,
  status              VARCHAR(24) NOT NULL DEFAULT 'open',   -- open|resolved|ignored
  resolved_faculty_id INT NULL,
  resolved_at         DATETIME NULL,
  UNIQUE KEY uq_ua (publication_author_id),
  CONSTRAINT fk_ua_pub FOREIGN KEY (publication_id) REFERENCES publication(id) ON DELETE CASCADE,
  CONSTRAINT fk_ua_pa  FOREIGN KEY (publication_author_id) REFERENCES publication_author(id) ON DELETE CASCADE,
  CONSTRAINT fk_ua_fac FOREIGN KEY (resolved_faculty_id) REFERENCES faculty(id),
  INDEX ix_ua_status (status)
) ENGINE=InnoDB;

-- 'not a faculty member' rulings from the review queue.
--
-- The weekly Scopus ingest rebuilds publication_author wholesale, and
-- unmatched_author cascades away with it (fk_ua_pa ON DELETE CASCADE), so a
-- ruling stored only on the queue row would not survive the next upload -- the
-- same research scholars would be back in the queue every week. Keyed on the
-- Scopus Author ID, exactly like author_alias, so the decision is permanent
-- rather than per-publication.
CREATE TABLE IF NOT EXISTS author_ignored (
  scopus_author_id VARCHAR(32) NOT NULL PRIMARY KEY,
  raw_name         VARCHAR(255) NULL,
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- manual Scopus-ID -> faculty overrides created from the review queue
CREATE TABLE IF NOT EXISTS author_alias (
  scopus_author_id VARCHAR(32) NOT NULL PRIMARY KEY,
  faculty_id       INT NOT NULL,
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_alias_fac FOREIGN KEY (faculty_id) REFERENCES faculty(id) ON DELETE CASCADE
) ENGINE=InnoDB;
