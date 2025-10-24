# AI Image Studio (Streamlit)

A modern Streamlit app to generate images using an AI image generator API.  
Supports **prompt**, **negative prompt**, **aspect ratio**, preview, **download**, and a **Pandas**-powered history table with CSV export.

## Features
- Provider architecture (default: OpenAI Images)
- Prompt + Negative prompt (fallback injection for providers without native negative prompt)
- Aspect ratio presets (1:1, 16:9, 9:16, 4:3, 3:4)
- Download generated image as PNG
- History (in-memory) with CSV export via Pandas DataFrame

## Setup

1. **Clone** and create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
