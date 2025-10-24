import os
import json
from typing import Dict, List, Tuple, Optional

import streamlit as st
import pandas as pd

from settings import APP_TITLE, SIDEBAR_INFO, DEFAULT_SYSTEM_PROMPT
from llm_providers import (
    PROVIDERS,
    build_provider,
    ProviderName,
    ChatMessage,
)

# ---------- Page / Theme ----------
st.set_page_config(page_title=APP_TITLE, page_icon="💬", layout="wide")

# ---------- Sidebar ----------
with st.sidebar:
    st.title("⚙️ Settings")

    provider_name: ProviderName = st.selectbox(
        "Provider",
        options=list(PROVIDERS.keys()),
        index=0,
        help="Choose which LLM provider to use.",
    )

    default_model = PROVIDERS[provider_name].default_model
    model_name = st.text_input(
        "Model name",
        value=default_model,
        help="You can use the default or type any available model for your keys.",
    )

    temperature = st.slider(
        "Temperature", min_value=0.0, max_value=1.0, value=0.3, step=0.05,
        help="Higher is more creative, lower is more precise."
    )
    max_tokens = st.number_input(
        "Max output tokens", min_value=128, max_value=8192, value=1024, step=64
    )

    st.divider()
    st.caption("Optional: Upload CSV so the assistant can reference its schema/sample.")
    csv_file = st.file_uploader("Upload CSV", type=["csv"])
    df: Optional[pd.DataFrame] = None
    if csv_file is not None:
        try:
            df = pd.read_csv(csv_file)
            st.success(f"Loaded: {csv_file.name} ({len(df)} rows, {len(df.columns)} cols)")
            st.dataframe(df.head(25))
        except Exception as e:
            st.error(f"Failed to parse CSV: {e}")

    st.divider()
    st.markdown(SIDEBAR_INFO)
    if st.button("♻️ Reset this chat"):
        st.session_state.get("chats", {}).pop((provider_name, model_name), None)
        st.rerun()

# ---------- Session State ----------
if "chats" not in st.session_state:
    st.session_state["chats"] = {}  # key: (provider, model) -> List[ChatMessage]

chat_key = (provider_name, model_name)
if chat_key not in st.session_state["chats"]:
    st.session_state["chats"][chat_key] = [
        ChatMessage(role="system", content=DEFAULT_SYSTEM_PROMPT)
    ]

# Inject lightweight table context if available
def dataframe_context(df: pd.DataFrame, max_rows: int = 10) -> str:
    preview = df.head(max_rows)
    schema_lines = [f"- {col}: {str(df[col].dtype)}" for col in df.columns]
    return (
        "You have access to a user-provided CSV (preview included).\n\n"
        "Schema (column: dtype):\n" + "\n".join(schema_lines) + "\n\n"
        f"Preview (first {len(preview)} rows):\n{preview.to_markdown(index=False)}"
    )

# ---------- Header ----------
st.markdown(
    f"""
    <div style="display:flex;align-items:center;gap:.6rem">
      <div style="font-size:1.6rem">💬 {APP_TITLE}</div>
      <span style="opacity:.7">({provider_name} · <code>{model_name}</code>)</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------- Render history ----------
history: List[ChatMessage] = st.session_state["chats"][chat_key]
for m in history:
    if m.role == "system":
        continue
    with st.chat_message(m.role):
        st.markdown(m.content)

# ---------- Input ----------
prompt = st.chat_input("Type your message…")
if prompt:
    # Append user message
    user_msg = ChatMessage(role="user", content=prompt)
    history.append(user_msg)
    with st.chat_message("user"):
        st.markdown(prompt)

    # Compose effective messages (inject DF context if present & not already injected)
    effective_messages: List[ChatMessage] = history.copy()
    if df is not None:
        # Add a lightweight data context as an extra system message
        effective_messages = [
            effective_messages[0],
            ChatMessage(role="system", content=dataframe_context(df)),
            *effective_messages[1:],
        ]

    # Build provider
    provider = build_provider(
        name=provider_name,
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Stream response where supported
    with st.chat_message("assistant"):
        response_container = st.empty()
        chunks: List[str] = []
        for delta in provider.stream_chat(effective_messages):
            chunks.append(delta)
            response_container.markdown("".join(chunks))

        final_text = "".join(chunks).strip()
        if not final_text:
            final_text = "_(No content returned)_"
        history.append(ChatMessage(role="assistant", content=final_text))
