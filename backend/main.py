"""
Voice Authenticity Dataset Collector - FastAPI Backend Entrypoint.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.routes.config_routes import router as config_router
from backend.routes.contributor_routes import router as contributor_router

app = FastAPI(
    title="Voice Authenticity Dataset API",
    description="API for collecting human speech recordings and generating synthetic audio pairs for voice fraud detection research.",
    version="2.0.0",
)

# ── CORS Configuration ───────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ── Include Routers ──────────────────────────────────────────────────────────
app.include_router(config_router)
app.include_router(contributor_router)

# ── Serve Built Frontend in Production (Single Unified Service) ──────────────
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend_spa(full_path: str):
        # Allow static files in root of dist (favicon, manifest, etc.)
        target = FRONTEND_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(str(target))

        # Default fallback to React SPA index.html
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(
                str(index_file),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )

        return {"error": "Frontend build index.html not found"}
else:
    @app.get("/")
    async def root():
        return {
            "status": "online",
            "service": "Voice Authenticity Dataset Collector API",
            "version": "2.0.0",
            "docs_url": "/docs",
        }


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
