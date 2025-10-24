# Multi-LLM Chat (Streamlit)

A modern, minimal chat UI in Python that lets users choose between **OpenAI** and **Anthropic** models at runtime. It supports separate histories per model, CSV upload with DataFrame preview, and streamed responses.

## Quick start

```bash
git clone <your-repo> multi-llm-chat
cd multi-llm-chat

# Create and activate a virtual env (Windows PowerShell shown)
python -m venv .venv
. .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# Optional: set keys via .env
copy .env.example .env
# edit .env with your keys

# Or set env vars directly:
# $env:OPENAI_API_KEY="sk-..."
# $env:ANTHROPIC_API_KEY="sk-ant-..."

streamlit run app.py
