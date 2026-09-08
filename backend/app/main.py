from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import q
from .routers import admin, analytics, faculty, publications

app = FastAPI(
    title="BITS Research Publication Analytics",
    description="Scopus + IRINS + SJR + CiteScore + Web of Science",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analytics.router)
app.include_router(faculty.router)
app.include_router(publications.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "publications": q("SELECT COUNT(*) AS n FROM publication")[0]["n"]}


# serve the built React app when it exists, so a single process runs in production
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # an unknown /api route must 404, not fall through to the SPA shell:
        # the frontend calls res.json() on it and would die on a JSON parse
        # error instead of showing the real status
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not found")

        # real files in the build root (favicon.svg, icons.svg, anything else
        # dropped into frontend/public) are served as themselves. Only /assets
        # is mounted, so without this they came back as the index.html shell
        # with a text/html content type. resolve() + is_relative_to keeps a
        # crafted ../ path from escaping the build directory.
        if full_path:
            candidate = (DIST / full_path).resolve()
            if candidate.is_relative_to(DIST.resolve()) and candidate.is_file():
                return FileResponse(candidate)

        return FileResponse(DIST / "index.html")
