APP_TITLE = "Multi-LLM Chat (Streamlit)"

DEFAULT_SYSTEM_PROMPT = """You are a helpful, concise AI assistant.
- Prefer clear bullet points when listing.
- If the user uploads a CSV, you will receive its schema and a small preview in a separate system message.
- Do NOT hallucinate facts about data that isn’t shown; ask for more details or files if needed.
"""

SIDEBAR_INFO = """
**Tips**
- Set your API keys via environment variables:
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`
- You can switch **Provider** and **Model** at any time.
- Each (provider, model) pair has its **own chat history**.
"""
