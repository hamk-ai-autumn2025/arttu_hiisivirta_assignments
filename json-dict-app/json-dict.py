#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from typing import Any, Dict, Iterable

def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def clean_terms(items: Iterable[str], limit: int) -> list[str]:
    # lowercase, strip, drop empties, dedupe, sort alpha, cap
    terms = [str(x).strip().lower() for x in (items or [])]
    terms = [t for t in terms if t]
    terms = dedupe_preserve_order(terms)
    terms.sort()
    return terms[:max(0, limit)]

def clean_definitions(items: Iterable[str], limit: int, max_len: int) -> list[str]:
    # strip, collapse spaces, drop empties, dedupe (preserve order), cap and hard-limit length
    defs = []
    for x in (items or []):
        s = re.sub(r"\s+", " ", str(x).strip())
        if s:
            defs.append(s[:max_len].rstrip())
    defs = dedupe_preserve_order(defs)
    return defs[:max(0, limit)]

def clean_example(text: Any, max_len: int) -> str:
    s = re.sub(r"\s+", " ", str(text or "").strip())
    return s[:max_len].rstrip()

def build_messages(word: str, language: str) -> list[dict]:
    system = (
        "You are a precise lexicographer. "
        "Return ONLY valid JSON (no preface, no markdown). "
        f"Target language for definitions and example: {language}. "
        "Schema:\n"
        "{\n"
        '  "word": string,\n'
        '  "definitions": array of strings (1-3 concise meanings),\n'
        '  "synonyms": array of strings,\n'
        '  "antonyms": array of strings,\n'
        '  "example": string (one natural sentence using the word)\n'
        "}\n"
        "Constraints:\n"
        "- Arrays must contain unique entries where sensible.\n"
        "- If an item is unknown, return an empty array (not null).\n"
        "- Ensure the JSON is syntactically valid and matches the schema."
    )
    user = f'Produce an entry for the word "{word}". Prefer the most common modern usage.'
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

def print_json(obj: Dict[str, Any], pretty: bool) -> None:
    if pretty:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False))
    else:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False))
    sys.stdout.flush()

def main() -> None:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("word", help="The word to look up.")
    parser.add_argument("--model", default="gpt-5", help="LLM model to use.")
    parser.add_argument("--language", default="en", help="Language code for definitions/example.")
    parser.add_argument("--temperature", type=float, default=None,
                        help="Sampling temperature. If omitted, not sent.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    parser.add_argument("--max-defs", type=int, default=3, help="Max definitions to keep (default 3).")
    parser.add_argument("--max-terms", type=int, default=12, help="Max synonyms/antonyms each (default 12).")
    parser.add_argument("--max-def-len", type=int, default=240, help="Max characters per definition (default 240).")
    parser.add_argument("--max-example-len", type=int, default=240, help="Max characters for example (default 240).")
    args = parser.parse_args()

    # Stable, ordered schema build
    result = {
        "word": args.word,
        "definitions": [],
        "synonyms": [],
        "antonyms": [],
        "example": ""
    }

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        result["definitions"] = ["error: OPENAI_API_KEY is not set."]
        print_json(result, args.pretty)
        return

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        messages = build_messages(args.word, args.language)

        req = {
            "model": args.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if args.temperature is not None:
            req["temperature"] = args.temperature

        def do_request(kwargs):
            return client.chat.completions.create(**kwargs)

        try:
            resp = do_request(req)
        except Exception as e:
            msg = str(e)
            if "param': 'temperature'" in msg or "Unsupported value" in msg or "does not support" in msg:
                req.pop("temperature", None)
                resp = do_request(req)
            else:
                raise

        content = resp.choices[0].message.content if resp and resp.choices else ""
        data = {}
        try:
            data = json.loads(content) if content else {}
        except json.JSONDecodeError:
            pass  # fall back to empty dict; we’ll output a minimal clean object

        # Fill & clean
        result["word"] = str(data.get("word", args.word)) or args.word
        result["definitions"] = clean_definitions(data.get("definitions"), args.max_defs, args.max_def_len)
        result["synonyms"] = clean_terms(data.get("synonyms"), args.max_terms)
        result["antonyms"] = clean_terms(data.get("antonyms"), args.max_terms)
        result["example"] = clean_example(data.get("example"), args.max_example_len)

        print_json(result, args.pretty)

    except Exception as e:
        result["definitions"] = [f"error: {type(e).__name__}: {e}"]
        print_json(result, args.pretty)

if __name__ == "__main__":
    main()
