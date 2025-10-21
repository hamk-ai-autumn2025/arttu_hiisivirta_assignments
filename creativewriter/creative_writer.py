#!/usr/bin/env python3
"""
creawrite.py — CLI tool for SEO-optimized creative writing with OpenAI.

Examples:
  python creawrite.py -p "Launch copy for a smartwatch for cyclists" -m marketing --keywords "GPS, heart-rate, Strava" --audience "endurance athletes"
  python creawrite.py -p "A playful meme about Monday mornings" -m meme
  python creawrite.py -p "Lo-fi hip hop lyrics about winter sunsets" -m lyrics --language fi
  python creawrite.py -p "Blog post: how to choose a road bike" -m blog --keywords "aero, endurance geometry, carbon frame" --variants 5 --out-dir ./out

Requires:
  pip install openai python-slugify rich
  Set OPENAI_API_KEY in your environment.
"""

import os
import sys
import json
import textwrap
import argparse
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from openai import OpenAI
from slugify import slugify
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

MODE_CHOICES = ["marketing", "meme", "lyrics", "poem", "blog"]

SYSTEM_BASE = """You are a top-tier, award-winning creative writer and SEO strategist.
Write with originality, clarity, and a distinct voice. Always avoid plagiarism.
When the mode is BLOG or MARKETING, ensure on-page SEO best practices:
- Include a compelling Meta Title (<= 60 chars) and Meta Description (<= 155 chars).
- Provide an SEO-friendly slug (lowercase, hyphenated).
- Use a clear H1 and scannable H2/H3 structure.
- Naturally weave in provided keywords; never stuff them.
- End with a succinct call to action when appropriate.
When the mode is MEME, provide: caption, alt-text, and 5-8 short hashtags.
When the mode is LYRICS, provide: Title, Verse(s), Chorus, and Bridge if helpful.
When the mode is POEM, provide: Title and the poem (consistent form or intentional variation).
Always return clean, publication-ready Markdown.
"""

PROMPT_TEMPLATE = """Task:
Write in MODE="{mode}" for the following prompt:

PROMPT:
{user_prompt}

Audience (optional): {audience}
Brand/Voice (optional): {brand_voice}
Language: {language}
Target Keywords (comma-separated): {keywords}

SEO constraints (when applicable):
- Meta Title <= 60 chars
- Meta Description <= 155 chars
- Natural keyword usage
- Clear structure and readability

Output format:
- Start with a single-line header: "### Version {index}"
- Then provide the content in Markdown according to MODE guidelines.
- If BLOG or MARKETING, include:
  - Meta Title:
  - Meta Description:
  - Slug:
  - H1:
  - Body with H2/H3:
  - CTA (short):
  - Keywords used:
"""

def build_messages(mode: str,
                   user_prompt: str,
                   audience: Optional[str],
                   brand_voice: Optional[str],
                   language: str,
                   keywords: List[str]) -> List[Dict[str, str]]:
    sys_msg = {"role": "system", "content": SYSTEM_BASE}
    user_msg = {
        "role": "user",
        "content": PROMPT_TEMPLATE.format(
            mode=mode.upper(),
            user_prompt=user_prompt.strip(),
            audience=audience or "—",
            brand_voice=brand_voice or "—",
            language=language,
            keywords=", ".join(keywords) if keywords else "—",
            index="{index}"  # will replace after generation
        )
    }
    return [sys_msg, user_msg]

def save_variants(variants: List[str], out_dir: str, base_slug: str, ext: str = "md") -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, content in enumerate(variants, start=1):
        filename = f"{base_slug}-v{i}.{ext}"
        path = os.path.join(out_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        paths.append(path)
    return paths

def decorate_markdown(md_text: str, title: str):
    console.print(Panel.fit(title, style="bold cyan"))
    console.print(Markdown(md_text))

def main():
    parser = argparse.ArgumentParser(
        description="Generate SEO-optimized creative writing with OpenAI (multiple variants by default).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("-p", "--prompt", required=False, help="Your creative brief / prompt.")
    parser.add_argument("-m", "--mode", choices=MODE_CHOICES, default="blog", help="Creative mode.")
    parser.add_argument("--keywords", type=str, default="", help="Comma-separated SEO keywords.")
    parser.add_argument("--audience", type=str, default="", help="Intended audience (optional).")
    parser.add_argument("--brand", dest="brand_voice", type=str, default="", help="Brand/voice tone (optional).")
    parser.add_argument("--language", type=str, default="en", help="Output language (e.g., en, fi, sv).")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="OpenAI model name.")
    parser.add_argument("--variants", type=int, default=3, help="How many versions to produce.")
    parser.add_argument("--temperature", type=float, default=0.9, help="Sampling temperature.")
    parser.add_argument("--top-p", dest="top_p", type=float, default=1.0, help="Top-p nucleus sampling.")
    parser.add_argument("--presence-penalty", type=float, default=0.4, help="Encourage novelty across variants.")
    parser.add_argument("--frequency-penalty", type=float, default=0.0, help="Reduce repetition.")
    parser.add_argument("--max-tokens", type=int, default=1200, help="Max tokens for each variant.")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed for reproducibility.")
    parser.add_argument("--out-dir", type=str, default="", help="If set, saves each variant as a Markdown file.")
    parser.add_argument("--json", dest="save_json", action="store_true", help="Also save a JSON with all variants.")
    args = parser.parse_args()

    if not args.prompt:
        try:
            args.prompt = input("What do you want me to write? ").strip()
        except (EOFError, KeyboardInterrupt):
            print("No prompt provided; exiting.")
            sys.exit(2)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        console.print("[red]Error:[/red] OPENAI_API_KEY not set.")
        sys.exit(1)

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    messages = build_messages(args.mode, args.prompt, args.audience, args.brand_voice, args.language, keywords)

    # Initialize client
    client = OpenAI()  # reads OPENAI_API_KEY from env

    # Request 'n' variants in one call; use penalties to encourage diversity
    try:
        completion = client.chat.completions.create(
            model=args.model,
            messages=messages,
            n=args.variants,
            temperature=args.temperature,
            top_p=args.top_p,
            presence_penalty=args.presence_penalty,
            frequency_penalty=args.frequency_penalty,
            max_tokens=args.max_tokens,
            seed=args.seed
        )
    except Exception as e:
        console.print(f"[red]OpenAI API error:[/red] {e}")
        sys.exit(2)

    # Extract variants
    variants = []
    for idx, choice in enumerate(completion.choices, start=1):
        text = (choice.message.content or "").strip()

    # Remove any model-made "Version ..." header on the first line
    # (handles headings like "### Version 2" or "## Version 1 – ..." etc.)
        lines = text.splitlines()
        if lines and re.match(r"^\s{0,3}#{1,6}\s*Version\b", lines[0], flags=re.IGNORECASE):
            text = "\n".join(lines[1:]).lstrip()

    # Prepend our own canonical header
        text = f"### Version {idx}\n\n{text}"
        variants.append(text)

    # Display nicely
    title = f"Creative {args.mode.capitalize()} — {args.variants} Variant(s) — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    decorate_markdown("\n\n".join(variants), title)

    # Save files if requested
    if args.out_dir:
        base_slug = slugify(f"{args.mode}-{args.prompt[:48]}")
        paths = save_variants(variants, args.out_dir, base_slug, ext="md")
        console.print(Panel.fit("Saved:\n" + "\n".join(paths), title="Files", style="green"))

    if args.save_json:
        payload = {
            "meta": {
                "mode": args.mode,
                "prompt": args.prompt,
                "model": args.model,
                "variants": args.variants,
                "temperature": args.temperature,
                "top_p": args.top_p,
                "presence_penalty": args.presence_penalty,
                "frequency_penalty": args.frequency_penalty,
                "max_tokens": args.max_tokens,
                "language": args.language,
                "keywords": keywords,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            },
            "variants": raw_texts
        }
        name = slugify(f"{args.mode}-{args.prompt[:48]}") + ".json"
        path = name if not args.out_dir else os.path.join(args.out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        console.print(Panel.fit(path, title="JSON saved", style="cyan"))

if __name__ == "__main__":
    main()
