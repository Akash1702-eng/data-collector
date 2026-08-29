"""
Voice Authenticity Dataset Collector
Main entrypoint for Hugging Face Spaces and local/cloud execution.
Launches the unified FastAPI backend + React Studio on port 7860 (Hugging Face standard) or $PORT.
"""

import os
import uvicorn
from backend.main import app

if __name__ == "__main__":
    # Hugging Face Spaces defaults to port 7860, cloud providers use $PORT
    port = int(os.environ.get("PORT", 7860))
    print(f"Starting Voice Authenticity Studio on port {port}...")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
