import os
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv():
    """Read KEY=VALUE lines from a project-root .env so the DB password stays out of the repo.

    Real environment variables win, so `BITS_DB_PASSWORD=... ./run.sh` still overrides the file.
    """
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()

DB_USER = os.getenv("BITS_DB_USER", "root")
DB_PASSWORD = os.getenv("BITS_DB_PASSWORD", "")
DB_HOST = os.getenv("BITS_DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("BITS_DB_PORT", "3306")
DB_NAME = os.getenv("BITS_DB_NAME", "bits_research")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)

# metrics vintage the dashboard reads by default
CURRENT_METRIC_YEAR = int(os.getenv("BITS_METRIC_YEAR", "2025"))
