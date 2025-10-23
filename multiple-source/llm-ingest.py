#!/usr/bin/env python3
"""
LLM Ingest CLI: Convert mixed sources (files/URLs) to Markdown using MarkItDown,
then ask an LLM to summarize or answer a custom query.

Usage examples:
  python llm_ingest.py -i file1.pdf -i https://example.com -q "What changed since 2023?"
  python llm_ingest.py -i notes.docx -i data.csv --out result.md
"""

import argparse
import os
import sys
import textwrap
from typing import List, Tuple
from urllib.parse import urlparse

# --- Conversion (MarkItDown) ---
try:
    from markitdown import MarkItDown
except ImportError:
    print("markitdown is required. Install with: pip install markitdown", file=sys.stderr)
    sys.exit(1)

# --- LLM (OpenAI SDK v1.x) ---
try:
    from openai import OpenAI
except ImportError:
    print("openai is required. Install with: pip install openai", file=sys.stderr)
    sys.exit(1)


def is_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https")
    except Exception:
        return False


def safe_markitdown_convert(md: MarkItDown, src: str) -> str:
    """
    Convert a file path or URL to Markdown/plain text using MarkItDown.
    Be lenient about result shape (object with .text_content or dict).
    """
    result = md.convert(src)
    # Try attributes first
    for attr in ("text_content", "markdown", "content", "text"):
        if hasattr(result, attr):
            value = getattr(result, attr)
            if value:
                return str(value)
    # If dict-like
    if isinstance(result, dict):
        for key in ("text_content", "markdown", "content", "text"):
            if key in result and result[key]:
                return str(result[key])
    # Fallback
    return str(result)


def read_and_convert_sources(inputs: List[str]) -> List[Tuple[str, str]]:
    """
    Returns list of (display_name, markdown_text) for each input.
    """
    md = MarkItDown()
    out: List[Tuple[str, str]] = []
    for src in inputs:
        display = src if is_url(src) else os.path.basename(os.path.abspath(src))
        try:
            if not is_url(src) and not os.path.exists(src):
                raise FileNotFoundError(f"Path not found: {src}")
            text = safe_markitdown_convert(md, src)
            if not text or not text.strip():
                raise ValueError(f"No extractable text from: {src}")
            out.append((display, text))
        except Exception as e:
            print(f"[warn] Skipping '{src}': {e}", file=sys.stderr)
    return out


def chunk_text(s: str, chunk_chars: int) -> List[str]:
    if chunk_chars <= 0 or len(s) <= chunk_chars:
        return [s]
    chunks = []
    i = 0
    # Try to break on paragraph boundaries when possible
    while i < len(s):
        end = min(i + chunk_chars, len(s))
        # backtrack to last double newline to avoid cutting mid-paragraph
        cut = s.rfind("\n\n", i, end)
        if cut == -1 or cut <= i + int(0.5 * chunk_chars):
            cut = end
        chunks.append(s[i:cut])
        i = cut
    return [c for c in chunks if c.strip()]


SYSTEM_PROMPT = """\
You are a careful analyst. You receive multiple SOURCE sections in Markdown.
Be concise and accurate. If the user did not provide a custom query, provide a
clear, well-structured summary with:
- bullet-point highlights,
- key facts and figures,
- notable quotes (short),
- inconsistencies or gaps,
- and a short conclusion.

When you reference something, cite it inline as [SOURCE: <name>].
Only use information from the provided sources.
"""

DEFAULT_SUMMARY_QUERY = "Summarize the materials clearly as instructed, with inline [SOURCE: name] citations."

REDUCE_QUERY = """\
You will receive several partial answers derived from different chunks of the same corpus.
Merge them into a single, non-redundant, well-structured result for the user’s query.
Preserve important details, remove repetition, and keep inline [SOURCE: name] mentions where appropriate.
"""


def ask_llm(client: OpenAI, model: str, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def build_corpus_block(named_markdowns: List[Tuple[str, str]]) -> str:
    parts = []
    for name, md in named_markdowns:
        parts.append(f"\n\n## SOURCE: {name}\n\n{md.strip()}\n")
    return "".join(parts).strip()


def main():
    parser = argparse.ArgumentParser(
        prog="llm_ingest",
        description="Feed mixed sources (files/URLs) to an LLM. Default action is summarize.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-i", "--input", action="append", required=True,
                        help="Input path or URL. Repeat for multiple (e.g., -i a.pdf -i https://site).")
    parser.add_argument("-q", "--query", default=None,
                        help="Custom question/prompt. If omitted, performs a concise summary.")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
                        help="LLM model name (default: gpt-4o-mini or $LLM_MODEL).")
    parser.add_argument("--max-tokens", type=int, default=1200, help="Max tokens for the final call (default: 1200).")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature (default: 0.2).")
    parser.add_argument("--chunk-chars", type=int, default=18000,
                        help="Approx. max characters per chunk (map-reduce over chunks; 0 disables).")
    parser.add_argument("--out", type=str, default=None, help="Write result to file instead of stdout.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only parse & convert sources; print combined Markdown and exit.")

    args = parser.parse_args()

    # Ensure API key is present unless dry-run
    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: Set OPENAI_API_KEY environment variable.", file=sys.stderr)
        sys.exit(2)

    named_markdowns = read_and_convert_sources(args.input)
    if not named_markdowns:
        print("ERROR: No usable sources.", file=sys.stderr)
        sys.exit(3)

    corpus_markdown = build_corpus_block(named_markdowns)

    if args.dry_run:
        print(corpus_markdown)
        return

    client = OpenAI()

    user_query = args.query.strip() if args.query else DEFAULT_SUMMARY_QUERY

    # Chunk + map-reduce if content is large
    chunks = chunk_text(corpus_markdown, args.chunk_chars) if args.chunk_chars else [corpus_markdown]

    partials: List[str] = []
    for idx, ch in enumerate(chunks, start=1):
        prompt = textwrap.dedent(f"""\
        Below are one or more SOURCE sections. Answer the user's query at the end,
        only using the provided sources.

        {ch}

        ---
        USER QUERY: {user_query}
        """)
        piece = ask_llm(
            client=client,
            model=args.model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        partials.append(f"### PART {idx}\n\n{piece}")

    if len(partials) == 1:
        final = partials[0].split("\n", 1)[-1]  # strip the "### PART 1" header
    else:
        # Reduce step
        reducer_input = "\n\n".join(partials) + f"\n\n---\nUSER QUERY (for context): {user_query}\n"
        final = ask_llm(
            client=client,
            model=args.model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=REDUCE_QUERY + "\n\n" + reducer_input,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(final)
        print(f"Wrote output to: {args.out}")
    else:
        print(final)


if __name__ == "__main__":
    main()
