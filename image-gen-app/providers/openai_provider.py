import os
import base64
from typing import Optional, Dict

try:
    # OpenAI SDK (>=1.0 style)
    from openai import OpenAI
except Exception:
    OpenAI = None


class OpenAIImageProvider:
    """
    Simple OpenAI Images provider using the current Python SDK.

    Set environment variable:
      OPENAI_API_KEY=your_key_here

    NOTE: Negative prompts are not a native, explicit parameter here.
    We inject them into the text prompt (see app.py combine_prompts()).
    """

    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key
        if self.api_key and OpenAI:
            self.client = OpenAI(api_key=self.api_key)
        else:
            self.client = None

    def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        guidance: float = 7.0,
        seed: Optional[int] = None,
        model: str = "gpt-image-1"
    ) -> Dict:
        if not self.api_key:
            raise RuntimeError("Missing OPENAI_API_KEY in environment.")
        if self.client is None:
            raise RuntimeError("OpenAI SDK not available. Check installation.")

        size = f"{width}x{height}"

        # OpenAI Images API (b64 JSON output)
        resp = self.client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            # OpenAI Images may not expose CFG/guidance/seed in all models.
            # Including optional 'seed' when available is harmless, otherwise ignored.
            # Extra params can be added if the SDK supports them in your environment.
        )

        b64 = resp.data[0].b64_json
        return {
            "b64": b64,
            "mime": "image/png",
            "meta": {
                "model": model,
                "size": size,
                "seed": seed,
                "guidance": guidance
            }
        }
