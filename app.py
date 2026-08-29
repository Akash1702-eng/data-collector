"""
Voice Authenticity Dataset Collector
Main entrypoint for Hugging Face Spaces (Gradio SDK + ZeroGPU).

Architecture: Gradio is the primary server (required by ZeroGPU).
FastAPI routes are mounted into Gradio's underlying ASGI app.
The React frontend is served from frontend/dist/ via FastAPI static file mounts.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import gradio as gr

# ── Import FastAPI routes ────────────────────────────────────────────────────
from backend.routes.config_routes import router as config_router
from backend.routes.contributor_routes import router as contributor_router

# ── ZeroGPU decorator ───────────────────────────────────────────────────────
try:
    import spaces
    @spaces.GPU(duration=10)
    def gpu_status():
        return "ZeroGPU is active"
except ImportError:
    def gpu_status():
        return "Running on CPU"

# ── Build Gradio interface ──────────────────────────────────────────────────
with gr.Blocks(title="Voice Authenticity Dataset Studio") as demo:
    gr.Markdown("# 🎙️ Voice Authenticity Dataset Studio")
    gr.Markdown("Open the full studio interface below:")

    # Hidden button + textbox to register the @spaces.GPU function in the event graph
    with gr.Row(visible=False):
        status_btn = gr.Button("Check GPU")
        status_out = gr.Textbox()
        status_btn.click(fn=gpu_status, outputs=status_out)

# ── Mount FastAPI API routes into Gradio's underlying FastAPI app ────────────
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

gradio_app = demo.app

# CORS
gradio_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
gradio_app.include_router(config_router)
gradio_app.include_router(contributor_router)

# ── Serve the built React frontend from frontend/dist/ ──────────────────────
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    # Serve static assets (JS, CSS)
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        gradio_app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    # Catch-all for React SPA — serve index.html for any non-API, non-Gradio path
    @gradio_app.get("/app")
    @gradio_app.get("/app/{full_path:path}")
    async def serve_react_spa(full_path: str = ""):
        # Check if it's a real file in dist
        target = FRONTEND_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(FRONTEND_DIST / "index.html"))

# ── Launch ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
