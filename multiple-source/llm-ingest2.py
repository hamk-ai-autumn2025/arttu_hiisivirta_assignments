#!/usr/bin/env python3
"""
LLM Ingest CLI + Interactive Wizard (with streaming, timeout, and progress).

- If run with -i/--input flags, behaves like a normal CLI.
- If run without inputs (or with --wizard), launches an interactive prompt:
    * Enter one or more paths/URLs (blank line to finish)
    * Enter a query (blank = default summary)
    * Optional output filename (blank = stdout)

New flags:
  --stream                 Stream tokens live to stdout (quicker feedback)
  --timeout SECONDS        HTTP timeout for API calls (default: 60)
  --reduce-max-tokens N    Max tokens used in the reduce step (default = max-tokens)

Dependencies:
  pip install markitdown openai
"""

import argparse
import os
import sys
import textwrap
from pathlib import Path
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


def resolve_user_path(src: str) -> Path:
    """
    Resolve a user-supplied path:
    - expand ~ and env vars
    - try current working dir
    - if not found, try alongside the script file
    """
    p = Path(os.path.expandvars(os.path.expanduser(src)))
    if p.is_absolute() and p.exists():
        return p

    # try CWD first
    if not p.is_absolute():
        p_cwd = Path.cwd() / p
        if p_cwd.exists():
            return p_cwd

    # then try script directory
    try:
        script_dir = Path(__file__).resolve().parent
        p_script = script_dir / (p.name if not p.exists() else p)
        if p_script.exists():
            return p_script
    except NameError:
        pass  # __file__ may not exist in some environments

    return p


def safe_markitdown_convert(md: MarkItDown, src: str) -> str:
    """
    Convert a file path or URL to Markdown/plain text using MarkItDown.
    """
    result = md.convert(src)
    for attr in ("text_content", "markdown", "content", "text"):
        if hasattr(result, attr):
            value = getattr(result, attr)
            if value:
                return str(value)
    if isinstance(result, dict):
        for key in ("text_content", "markdown", "content", "text"):
            if key in result and result[key]:
                return str(result[key])
    return str(result)


def read_and_convert_sources(inputs: List[str]) -> List[Tuple[str, str]]:
    """
    Returns list of (display_name, markdown_text) for each input.
    """
    md = MarkItDown()
    out: List[Tuple[str, str]] = []
    for src in inputs:
        if is_url(src):
            display = src
            resolved = src
        else:
            resolved_path = resolve_user_path(src)
            if not resolved_path.exists():
                print(f"[warn] Skipping '{src}': Path not found (looked at: '{resolved_path}')", file=sys.stderr)
                continue
            resolved = str(resolved_path)
            display = resolved_path.name

        try:
            text = safe_markitdown_convert(md, resolved)
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


def ask_llm(client: OpenAI, model: str, system_prompt: str, user_prompt: str,
            max_tokens: int, temperature: float, stream: bool = False) -> str:
    if stream:
        # Live token streaming
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        out = []
        try:
            for chunk in resp:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    out.append(delta)
                    print(delta, end="", flush=True)  # live tokens
            print()  # newline after stream
        except KeyboardInterrupt:
            print("\n[Interrupted] Returning what we have so far...", file=sys.stderr)
        return "".join(out).strip()
    else:
        # Normal call
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


def wizard_collect_inputs() -> List[str]:
    print(f"(Working directory: {Path.cwd()})")
    print("\nEnter file paths or URLs. Press Enter on an empty line to finish.")
    print("Examples: report.pdf, notes.docx, data.csv, https://example.com/article\n")
    inputs: List[str] = []
    while True:
        try:
            s = input("Path or URL (blank to finish): ").strip()
        except EOFError:
            break
        if not s:
            break
        inputs.append(s)
    return inputs


def wizard_collect_query(default_query: str) -> str:
    print("\nWhat should I do with these sources?")
    print("Press Enter for a concise summary, or type your own query.")
    q = input("Query: ").strip()
    return q if q else default_query


def wizard_collect_outfile() -> str:
    print("\nWhere should I write the output? Press Enter for stdout.")
    out = input("Output file (optional): ").strip()
    return out


def main():
    parser = argparse.ArgumentParser(
        prog="llm_ingest",
        description="Feed mixed sources (files/URLs) to an LLM. Default action is summarize.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-i", "--input", action="append",
                        help="Input path or URL. Repeat for multiple (e.g., -i a.pdf -i https://site).")
    parser.add_argument("-q", "--query", default=None,
                        help="Custom question/prompt. If omitted, performs a concise summary.")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
                        help="LLM model name (default: gpt-4o-mini or $LLM_MODEL).")
    parser.add_argument("--max-tokens", type=int, default=1200, help="Max tokens for the map/final call (default: 1200).")
    parser.add_argument("--reduce-max-tokens", type=int, default=None,
                        help="Max tokens for the reduce step (default: same as --max-tokens).")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature (default: 0.2).")
    parser.add_argument("--chunk-chars", type=int, default=18000,
                        help="Approx. max characters per chunk (map-reduce over chunks; 0 disables).")
    parser.add_argument("--out", type=str, default=None, help="Write result to file instead of stdout.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only parse & convert sources; print combined Markdown and exit.")
    parser.add_argument("--wizard", action="store_true",
                        help="Force interactive wizard (even if -i provided).")
    parser.add_argument("--stream", action="store_true",
                        help="Stream tokens live to stdout.")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="HTTP request timeout in seconds (default: 60).")

    args = parser.parse_args()

    # Interactive mode
    interactive = args.wizard or not args.input

    if interactive:
        print("=== LLM Ingest Wizard ===")
        print(f"Current model: {args.model}")
        model_override = input("Use a different model? (blank to keep): ").strip()
        if model_override:
            args.model = model_override

        inputs = wizard_collect_inputs()
        if not inputs:
            print("No inputs provided. Exiting.", file=sys.stderr)
            sys.exit(1)
        args.input = inputs

        args.query = wizard_collect_query(DEFAULT_SUMMARY_QUERY)

        out_choice = wizard_collect_outfile()
        if out_choice:
            args.out = out_choice

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

    # OpenAI client with timeout
    client = OpenAI(timeout=args.timeout)

    user_query = args.query.strip() if args.query else DEFAULT_SUMMARY_QUERY
    reduce_max = args.reduce_max_tokens if args.reduce_max_tokens is not None else args.max_tokens

    # Chunk + map-reduce
    chunks = chunk_text(corpus_markdown, args.chunk_chars) if args.chunk_chars else [corpus_markdown]

    partials: List[str] = []
    total = len(chunks)
    try:
        for idx, ch in enumerate(chunks, start=1):
            print(f"[info] Processing chunk {idx}/{total} (approx {len(ch):,} chars)...", file=sys.stderr)
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
                stream=args.stream,
            )
            partials.append(f"### PART {idx}\n\n{piece}")

        if len(partials) == 1:
            final = partials[0].split("\n", 1)[-1]
        else:
            print("[info] Reducing partials...", file=sys.stderr)
            reducer_input = "\n\n".join(partials) + f"\n\n---\nUSER QUERY (for context): {user_query}\n"
            final = ask_llm(
                client=client,
                model=args.model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=REDUCE_QUERY + "\n\n" + reducer_input,
                max_tokens=reduce_max,
                temperature=args.temperature,
                stream=args.stream,
            )
    except KeyboardInterrupt:
        print("\n[Interrupted] Printing partial result so far...", file=sys.stderr)
        final = ("\n\n".join(partials) or "[no output produced]")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(final)
        print(f"Wrote output to: {args.out}")
    else:
        print(final)


if __name__ == "__main__":
    main()
