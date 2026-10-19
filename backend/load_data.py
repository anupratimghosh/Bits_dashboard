#!/usr/bin/env python
"""One-shot loader for the reference masters and an initial Scopus file.

    python backend/load_data.py --all
    python backend/load_data.py --scopus Scopus_raw.xlsx
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db import ensure_schema  # noqa: E402
from app.ingest import crossref, masters, scopus  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "Master File"

DEFAULTS = {
    "irins": MASTER_DIR / "data-1785472704.xlsx",
    "sjr": MASTER_DIR / "sjr_data_2025.xlsx",
    "citescore": MASTER_DIR / "CiteScore 2025.xlsx",
    "wos": MASTER_DIR / "wos 2025.xlsx",
    "scopus": ROOT / "Scopus_raw.xlsx",
}


def step(label, fn, *args, **kwargs):
    t0 = time.time()
    print(f"  {label} ... ", end="", flush=True)
    res = fn(*args, **kwargs)
    print(f"{res}  ({time.time() - t0:.1f}s)")
    return res


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="load every master + Scopus")
    p.add_argument("--irins", nargs="?", const=str(DEFAULTS["irins"]))
    p.add_argument("--sjr", nargs="?", const=str(DEFAULTS["sjr"]))
    p.add_argument("--citescore", nargs="?", const=str(DEFAULTS["citescore"]))
    p.add_argument("--wos", nargs="?", const=str(DEFAULTS["wos"]))
    p.add_argument("--scopus", nargs="?", const=str(DEFAULTS["scopus"]))
    p.add_argument("--dates", action="store_true",
                   help="look up publication dates on Crossref (runs after --scopus anyway)")
    p.add_argument("--year", type=int, default=2025, help="metrics vintage")
    a = p.parse_args()

    if a.all:
        for k in DEFAULTS:
            if getattr(a, k) is None:
                setattr(a, k, str(DEFAULTS[k]))

    print("Loading BITS research data")
    ensure_schema()
    if a.irins:
        step("IRINS faculty ", masters.load_irins, a.irins)
    if a.sjr:
        step("SJR master    ", masters.load_sjr, a.sjr, a.year)
    if a.citescore:
        step("CiteScore     ", masters.load_citescore, a.citescore, a.year)
    if a.wos:
        step("Web of Science", masters.load_wos, a.wos, a.year)
    if a.scopus:
        step("Scopus export ", scopus.ingest_scopus, a.scopus,
             filename=Path(a.scopus).name, uploaded_by="bootstrap")
    if a.scopus or a.dates:
        step("Crossref dates", crossref.fill_pub_dates)
    print("done")


if __name__ == "__main__":
    main()
