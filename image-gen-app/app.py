import io
import os
import base64
from datetime import datetime
from typing import Tuple, Dict

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from utils.image_utils import decode_base64_to_bytes
from providers.openai_provider import OpenAIImageProvider
# from providers.stability_provider import StabilityImageProvider  # optional

# --- Load environment variables (.env) ---
load_dotenv()

# --- Streamlit page config ---
st.set_page_config(
    page_title="AI Image Studio",
    page_icon="🎨",
    layout="wide"
)

# --- Minimal modern styling ---
st.markdown("""
<style>
/* Tighten the main block width slightly for a sleek look */
.block-container { max-width: 1200px; }
/* Card-like look for the preview */

.download-row { display: flex; gap: 1rem; align-items: center; }
.caption-slim { color: rgba(128,128,128,0.8); font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# --- Providers registry (easily add more) ---
PROVIDERS = {
    "OpenAI": OpenAIImageProvider(api_key=os.getenv("OPENAI_API_KEY")),
    # "Stability (stub)": StabilityImageProvider(api_key=os.getenv("STABILITY_API_KEY"))
}

def aspect_ratio_to_size(ar_label: str) -> Tuple[int, int]:
    """
    Map user-friendly aspect ratios to pixel sizes supported by common image APIs.
    Feel free to adjust these if your provider supports arbitrary dimensions.
    """
    mapping = {
        "1:1 (Square)": (1024, 1024),
        "16:9 (Landscape)": (1280, 720),
        "9:16 (Portrait)": (720, 1280),
        "4:3 (Landscape)": (1024, 768),
        "3:4 (Portrait)": (768, 1024),
    }
    return mapping[ar_label]

def combine_prompts(prompt: str, negative: str, provider_name: str) -> str:
    """
    Some providers support negative prompts natively; others don't.
    For providers without native negative prompts, a safe fallback is to
    append a natural-language exclusion.
    """
    prompt = prompt.strip()
    negative = negative.strip()
    if not negative:
        return prompt

    # OpenAI (as of now) does not have a formal "negative prompt" field for images.
    # We’ll add a polite exclusion to the text prompt itself.
    if provider_name == "OpenAI":
        return f"{prompt}\n\nAvoid: {negative}."
    # Example: if your other provider has a native negative field, you would pass it separately there.
    return f"{prompt}\n\nAvoid: {negative}."

# --- App state init ---
if "history" not in st.session_state:
    st.session_state.history = []  # list of dict rows for DataFrame
if "last_image_bytes" not in st.session_state:
    st.session_state.last_image_bytes = None

# --- Sidebar (controls) ---
with st.sidebar:
    st.title("🎨 AI Image Studio")
    provider_name = st.selectbox("Image Provider", list(PROVIDERS.keys()))
    st.caption("Tip: set your API keys in `.env` (see README).")

    st.subheader("Inputs")
    prompt = st.text_area("Prompt", height=120, placeholder="e.g., ultra-detailed photo of a red vintage road bike on a mountain pass at sunrise")
    negative_prompt = st.text_area("Negative prompt (optional)", height=80, placeholder="e.g., blur, low resolution, watermark")

    st.subheader("Display")
    preview_size = st.slider("Preview size (px)", 300, 1200, 720, 10)

    ar_label = st.selectbox(
        "Aspect Ratio",
        ["1:1 (Square)", "16:9 (Landscape)", "9:16 (Portrait)", "4:3 (Landscape)", "3:4 (Portrait)"],
        index=0,
    )

    colA, colB = st.columns(2)
    with colA:
        guidance = st.slider("Guidance / CFG (if supported)", 1.0, 15.0, 7.0, 0.5)
    with colB:
        seed = st.number_input("Seed (optional)", min_value=0, max_value=2_000_000_000, value=0, step=1)

    st.divider()
    generate = st.button("Generate Image", type="primary", use_container_width=True)

# --- Main layout ---
st.title("AI Image Studio")
st.write("Generate images from text prompts. Supports prompt, negative prompt, aspect ratio, and download.")

provider = PROVIDERS[provider_name]
width, height = aspect_ratio_to_size(ar_label)

if generate:
    if not prompt.strip():
        st.warning("Please enter a prompt.")
    else:
        with st.spinner("Generating image..."):
            # Combine prompts depending on provider abilities
            merged_prompt = combine_prompts(prompt, negative_prompt, provider_name)
            result = provider.generate_image(
                prompt=merged_prompt,
                width=width,
                height=height,
                guidance=guidance,
                seed=seed if seed != 0 else None
            )
            # result is expected: {"b64": "...", "mime": "image/png" or "image/jpeg", "meta": {...}}
            img_bytes = decode_base64_to_bytes(result["b64"])
            st.session_state.last_image_bytes = img_bytes

            # Add to history (Pandas demo)
            st.session_state.history.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "provider": provider_name,
                "prompt": prompt,
                "negative": negative_prompt,
                "aspect_ratio": ar_label,
                "size": f"{width}x{height}",
                "seed": seed if seed != 0 else None,
                "guidance": guidance
            })

# --- Preview / Download ---
with st.container():
    st.subheader("Result")
    if st.session_state.last_image_bytes:
       
        st.image(
            st.session_state.last_image_bytes,
            caption=f"{width}×{height} • {ar_label}",
            width=preview_size,             # NEW: controls image width
            use_container_width=False       # ensure the width is respected
        )
        

        mime = "image/png"  # we set PNG in provider; switch if you choose JPEG
        st.markdown('<div class="download-row">', unsafe_allow_html=True)
        st.download_button(
            label="Download image",
            data=st.session_state.last_image_bytes,
            file_name=f"ai-image-{width}x{height}.png",
            mime=mime
        )
        st.caption("Images are generated on demand. Download to keep a local copy.")
        
    else:
        st.info("Your generated image will appear here. Use the sidebar to enter your prompt and click **Generate Image**.")

# --- History / DataFrame + CSV export ---
st.divider()
st.subheader("Generation History")
if len(st.session_state.history) == 0:
    st.write("No generations yet.")
else:
    df = pd.DataFrame(st.session_state.history)
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download history CSV", data=csv, file_name="generation_history.csv", mime="text/csv")
    st.caption("History is in-memory for this session; export CSV to persist it.")
