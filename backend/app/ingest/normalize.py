"""Shared cleaning helpers for every ingest path.

The single most important one is `norm_issn`: Excel strips leading zeros from
ISSNs (02194988 arrives as 2194988) and the three journal masters each store
them differently -- WoS hyphenates, SJR and CiteScore pack several into one
semicolon-separated cell. Everything is reduced to the same 8-character key.
"""
import re
from datetime import date

import pandas as pd

# Scopus records the institute both ways: spelled out, and abbreviated. The
# abbreviation is matched case-sensitively so the English word "bits" cannot
# masquerade as an affiliation.
BIRLA_RE = re.compile(r"birla\s+institute", re.I)
BITS_ABBR_RE = re.compile(r"\bB\.?\s?I\.?\s?T\.?\s?S\.?\b")

# order matters: "Pilani" appears in the institute's name on every campus record,
# so the distinctive campuses have to be tested first.
_CAMPUS_TOKENS = [
    ("dubai", "Dubai"),
    ("goa", "Goa"),
    ("hyderabad", "Hyderabad"),
    ("telangana", "Hyderabad"),
    ("pilani", "Pilani"),
    ("rajasthan", "Pilani"),
]

CAMPUSES = ["Pilani", "Goa", "Hyderabad", "Dubai"]


def clean_str(v, maxlen=None):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s in ("", "nan", "NaN", "None", "-", "N/A", "n/a"):
        return None
    return s[:maxlen] if maxlen else s


def clean_numlike(v, maxlen=None):
    """For fields Scopus stores as numbers but we keep as text (volume, issue,
    pages, article number). pandas types a column with blanks as float64, so
    issue 3 arrives as 3.0 and would be stored as the string "3.0"."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return clean_str(v, maxlen)


def to_int(v):
    s = clean_str(v)
    if s is None:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def to_float(v):
    s = clean_str(v)
    if s is None:
        return None
    s = s.replace(",", "")
    # WoS writes "<0.1" for tiny impact factors
    m = re.match(r"^[<>]\s*([0-9.]+)$", s)
    if m:
        return float(m.group(1))
    try:
        return float(s)
    except ValueError:
        return None


def norm_issn(v):
    """'0219-4988' / 2194988 / '2194988 ' -> '02194988'. None if unusable."""
    s = clean_str(v)
    if s is None:
        return None
    s = re.sub(r"[^0-9Xx]", "", s).upper()
    if not s or len(s) > 8:
        return None
    return s.zfill(8)


def split_issns(v):
    """Master files pack multiple ISSNs into one cell: '15424863; 00079235'."""
    s = clean_str(v)
    if s is None:
        return []
    out = []
    for part in re.split(r"[;,/|]", s):
        n = norm_issn(part)
        if n and n not in out:
            out.append(n)
    return out


def split_scopus_ids(v):
    """Scopus Author IDs from one master cell -> (ids, rejected).

    pandas types an all-numeric column that has a blank cell as float64, so
    60123665900 arrives as 60123665900.0 and, kept as text, would never match a
    paper. IRINS also packs several IDs into one cell for an author Scopus has
    split: '56094610300;60580463600'. Anything that is not all digits (a
    spreadsheet's 6.01E+10, a stray name) is returned as rejected, not guessed."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return [], []
    if isinstance(v, (int, float)) or hasattr(v, "is_integer"):
        f = float(v)
        return ([str(int(f))], []) if f.is_integer() and f > 0 else ([], [str(v)])
    ids, bad = [], []
    for part in re.split(r"[;,|/\s]+", str(v).strip()):
        part = re.sub(r"\.0+$", "", part)
        if not part:
            continue
        if part.isdigit():
            if part not in ids:
                ids.append(part)
        else:
            bad.append(part)
    return ids, bad


def norm_quartile(v):
    s = clean_str(v)
    if s is None:
        return None
    m = re.search(r"Q\s*([1-4])", s, re.I)
    return f"Q{m.group(1)}" if m else None


def is_bits_affiliation(text_):
    s = clean_str(text_)
    return bool(s and (BIRLA_RE.search(s) or BITS_ABBR_RE.search(s)))


def campus_from_affiliation(text_):
    """Best-effort campus for a BITS affiliation string. 100% resolution on the
    sample data; only consulted when IRINS has no answer."""
    s = clean_str(text_)
    if s is None:
        return None
    t = s.lower()
    for token, campus in _CAMPUS_TOKENS:
        if token in t:
            return campus
    return None


def split_semicolon(v):
    s = clean_str(v)
    return [p.strip() for p in s.split(";")] if s else []


def parse_authors_with_affiliations(cell):
    """Scopus packs 'Name, Affiliation; Name, Affiliation' into one cell. The
    affiliation itself contains commas, so we split on ';' and then take the
    first comma as the name/affiliation boundary."""
    out = []
    for seg in split_semicolon(cell):
        if not seg:
            continue
        name, _, affil = seg.partition(",")
        out.append((name.strip(), affil.strip() or None))
    return out


def parse_author_full_names(cell):
    """'Jayakumar, Megha (59301573300); Shukla, Suyash (57646019200)'."""
    out = []
    for seg in split_semicolon(cell):
        m = re.match(r"^(.*?)\s*\((\d+)\)\s*$", seg)
        if m:
            out.append((m.group(1).strip(), m.group(2)))
        else:
            out.append((seg.strip(), None))
    return out


def open_access_flag(v):
    s = clean_str(v)
    return 1 if s and "open access" in s.lower() else 0


def today():
    return date.today()


# --------------------------------------------------------------- column drift

def _norm_header(h):
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


class ColumnMap:
    """Resolves a spreadsheet's headers against the names a loader expects.

    Master files are re-issued every year with columns added, removed and
    renamed. Extra columns are harmless -- they are simply ignored. A *renamed*
    column is not: without this check, `SJR Best Quartile` becoming
    `Best Quartile` silently writes NULL over every quartile in the database and
    the load still reports success.

    So required columns are resolved up front and refused loudly, optional ones
    are reported back to the caller, and headers are matched case- and
    punctuation-insensitively (`H index` == `H-Index` == `h_index`).
    """

    def __init__(self, df, spec, required, source="file"):
        self.source = source
        self.actual = {}
        by_norm = {}
        for c in df.columns:
            by_norm.setdefault(_norm_header(c), c)

        for canon, aliases in spec.items():
            for candidate in (canon, *aliases):
                hit = by_norm.get(_norm_header(candidate))
                if hit is not None:
                    self.actual[canon] = hit
                    break

        missing = [c for c in required if c not in self.actual]
        if missing:
            raise ValueError(
                f"{source}: expected column(s) not found: {', '.join(missing)}. "
                f"The file has: {', '.join(str(c) for c in df.columns)}. "
                "If the column was renamed, add the new name to the loader's "
                "column spec."
            )

        self.missing_optional = [c for c in spec if c not in self.actual]
        self.extra = [
            str(c) for c in df.columns
            if _norm_header(c) not in {_norm_header(v) for v in self.actual.values()}
        ]

    def get(self, row, canon, default=None):
        col = self.actual.get(canon)
        if col is None:
            return default
        return row.get(col, default)

    def report(self):
        r = {}
        if self.missing_optional:
            r["columns_not_found"] = self.missing_optional
        if self.extra:
            r["columns_ignored"] = len(self.extra)
        return r
