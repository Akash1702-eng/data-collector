"""
Voice Authenticity Dataset Collector
Main entrypoint for Hugging Face Spaces (Gradio SDK) and cloud deployments.
"""

import os
import uvicorn
from backend.main import app as fastapi_app

app = fastapi_app

try:
    import gradio as gr
    with gr.Blocks(title="Voice Authenticity Dataset Studio") as demo:
        gr.Markdown("# 🎙️ Voice Authenticity Dataset Studio")
    app = gr.mount_gradio_app(fastapi_app, demo, path="/gradio")
except Exception:
    app = fastapi_app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print(f"Starting Voice Authenticity Studio on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
