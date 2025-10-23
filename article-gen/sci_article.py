#!/usr/bin/env python3
"""
SCI Article CLI (Markdown → PDF via xhtml2pdf, with LLM-generated content)

- Inputs a topic string
- Generates a structured scientific article in Markdown:
  Abstract → Conclusions, chapters with subchapters, APA-style in-text citations + reference list, plus a table
- Converts Markdown to a styled PDF using xhtml2pdf (pure-Python, no native deps)
- If OPENAI_API_KEY is set (or --llm flag given), uses an LLM to draft each section with real content.

Install:
  pip install xhtml2pdf markdown jinja2 openai
"""

import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# Markdown/templating
from markdown import markdown as md_to_html
from jinja2 import Template

# PDF (pure-Python)
from xhtml2pdf import pisa

# Optional LLM (OpenAI)
OPENAI_AVAILABLE = False
try:
    from openai import OpenAI  # openai>=1.0
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False


# ---------- Utilities ----------

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def today() -> str:
    return dt.date.today().isoformat()


# ---------- Citation / Reference Helper ----------

@dataclass
class Reference:
    authors: str      # e.g., "Smith, J., & Doe, A."
    year: str         # "2021"
    title: str
    source: str       # journal/publisher + details
    doi: Optional[str] = None
    url: Optional[str] = None

    def apa_citation(self) -> str:
        parts = [f"{self.authors} ({self.year}). {self.title}. {self.source}."]
        if self.doi:
            parts.append(f"https://doi.org/{self.doi}")
        elif self.url:
            parts.append(self.url)
        return " ".join(parts)


@dataclass
class Citations:
    items: Dict[str, Reference] = field(default_factory=dict)

    def add(self, key: str, ref: Reference):
        self.items[key] = ref

    def cite(self, *keys: str) -> str:
        """In-text citation like (Smith, 2021; Lee, 2022)."""
        entries = []
        for k in keys:
            ref = self.items.get(k)
            if not ref:
                continue
            first_author = ref.authors.split(",")[0]
            entries.append(f"{first_author}, {ref.year}")
        return f"({'; '.join(entries)})" if entries else ""

    def reference_list(self) -> str:
        ordered = sorted(self.items.values(), key=lambda r: r.authors)
        return "\n".join(f"- {r.apa_citation()}" for r in ordered)


def default_references_for_topic(topic: str) -> Citations:
    """Provide plausible generic references. Replace with real ones as needed."""
    c = Citations()
    c.add("foundations",
          Reference("Smith, J., & Doe, A.", "2021",
                    f"Foundations of {topic.lower()}",
                    "Journal of Emerging Technologies, 12(3), 123–145",
                    doi="10.1000/jemtech.2021.12345"))
    c.add("methods",
          Reference("Lee, K.", "2022",
                    f"Methodological advances in {topic.lower()}",
                    "Methods & Measures, 8(2), 55–73",
                    doi="10.1000/mnm.2022.5678"))
    c.add("applications",
          Reference("Rao, P., Nguyen, T., & Müller, F.", "2023",
                    f"Applications of {topic.lower()} across domains",
                    "International Review of Applied Science, 19(1), 1–26",
                    url="https://example.org/applications-review"))
    c.add("ethics",
          Reference("Garcia, L.", "2020",
                    f"Ethical considerations in {topic.lower()}",
                    "Ethics in Technology, 5(4), 201–220",
                    doi="10.1000/ethtech.2020.202"))
    c.add("limits",
          Reference("O'Neil, C.", "2016",
                    "Weapons of Math Destruction: How Big Data Increases Inequality and Threatens Democracy",
                    "Crown"))
    return c


# ---------- LLM content generation ----------

LLM_SYSTEM_PROMPT = (
    "You are a precise science-writing assistant. "
    "Write structured, neutral, evidence-informed prose with clear topic sentences, "
    "2–4 paragraphs per section unless otherwise specified. "
    "Avoid fabricating statistics or specific numeric claims. "
    "Use only the provided citation keys/authors and include APA-style in-text citations inline."
)

def llm_client() -> Optional["OpenAI"]:
    if not OPENAI_AVAILABLE:
        return None
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        return OpenAI()
    except Exception:
        return None


def llm_section_text(client, model: str, topic: str, section_title: str, allowed_citations: Dict[str, Reference], target_words: int = 180) -> Optional[str]:
    """
    Ask the LLM to write a section. We provide the list of allowed in-text citations (author, year) and
    require the model to reference them in prose (e.g., (Smith, 2021)).
    """
    if client is None:
        return None

    # Prepare a compact bibliography list for the prompt
    biblio_lines = []
    for k, r in allowed_citations.items():
        biblio_lines.append(f"- {k}: {r.authors} ({r.year}). {r.title}. {r.source}.")
    biblio = "\n".join(biblio_lines)

    user_prompt = (
        f"Topic: {topic}\n"
        f"Section: {section_title}\n"
        f"Target length: ~{target_words} words.\n\n"
        f"Allowed citations (use 1–3 of these exactly as APA in-text, like (Smith, 2021)):\n"
        f"{biblio}\n\n"
        f"Guidelines:\n"
        f"- Write 2–4 paragraphs of clear, academic prose.\n"
        f"- DO NOT invent statistics, datasets, or fake URLs/DOIs.\n"
        f"- If you make general claims, attribute them to the allowed citations.\n"
        f"- No bullet lists unless specifically asked; here, use paragraphs only.\n"
        f"- Do not include a section heading in the output; just the prose.\n"
    )

    try:
        # Do NOT pass temperature to avoid model-specific constraints
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = resp.choices[0].message.content.strip()
        return text
    except Exception as e:
        # Fail soft; fallback will handle
        return None


# ---------- Deterministic fallback paragraph ----------

def fallback_para(topic: str, section: str) -> str:
    return (
        f"This section addresses {section.lower()} within the context of {topic.lower()}. "
        f"It clarifies key terminology, summarizes prevailing approaches, and outlines "
        f"implications for research and practice. Assumptions and boundary conditions are "
        f"made explicit to support reproducibility."
    )


def make_table_markdown(topic: str) -> str:
    return (
        f"| Approach | Typical Benefit | Typical Limitation |\n"
        f"|---|---|---|\n"
        f"| Heuristic methods | Fast to implement; domain-intuitive | May lack theoretical guarantees |\n"
        f"| Data-driven models | Capture complex patterns | Require sizable, high-quality datasets |\n"
        f"| Hybrid {topic.lower()} pipelines | Balance interpretability and performance | Integration complexity |\n"
    )


# ---------- Article assembly ----------

def generate_markdown_article(topic: str, author: str, affiliation: str, keywords: List[str], use_llm: bool, model: str) -> (str, str):
    """
    Returns (markdown_text, suggested_filename_stub).
    """
    citations = default_references_for_topic(topic)

    client = llm_client() if use_llm else None

    def sec(name: str, words=180):
        # Try LLM; fallback to deterministic paragraph
        text = llm_section_text(client, model, topic, name, citations.items if citations else {}, target_words=words) if client else None
        return text if text else fallback_para(topic, name)

    md_template = Template(r"""---
title: "{{ title }}"
author:
  - "{{ author }}"
affiliation:
  - "{{ affiliation }}"
date: "{{ date }}"
---

# {{ title }}
**Author:** {{ author }}  
**Affiliation:** {{ affiliation }}  
**Date:** {{ date }}

---

## Abstract
{{ abstract }}

**Keywords:** {{ keyword_line }}

---

## 1. Introduction
{{ intro }} {{ citations.cite("foundations") }}

### 1.1 Problem Statement
{{ problem }}

### 1.2 Objectives
- Provide a structured overview of {{ title.lower() }}.
- Summarize key methods and their trade-offs.
- Present preliminary results and discuss implications.

### 1.3 Scope and Assumptions
{{ scope }}

---

## 2. Background
{{ background }} {{ citations.cite("applications","ethics") }}

### 2.1 Core Concepts
{{ core }}

### 2.2 Related Work
{{ related }} {{ citations.cite("foundations","methods","applications") }}

---

## 3. Methods
{{ methods }} {{ citations.cite("methods") }}

### 3.1 Data / Materials
{{ materials }}

### 3.2 Procedure
{{ procedure }}

### 3.3 Evaluation Metrics
{{ metrics }}

---

## 4. Results
{{ results }}

### 4.1 Summary Table
Below is a comparative table relevant to {{ title.lower() }}.

{{ table_md }}

### 4.2 Observations
{{ observations }}

---

## 5. Discussion
{{ discussion }} {{ citations.cite("ethics","limits") }}

### 5.1 Practical Implications
{{ practical }}

### 5.2 Theoretical Implications
{{ theoretical }}

---

## 6. Limitations
{{ limitations }} {{ citations.cite("limits") }}

---

## 7. Future Work
{{ future }}

---

## 8. Conclusions
{{ conclusions }}

---

## Acknowledgments
The author thanks colleagues and reviewers for constructive feedback.

---

## References
{{ citations.reference_list() }}
""")

    # Compose sections
    abstract = sec("Abstract", 120)
    intro = sec("Introduction")
    problem = sec("Problem Statement", 150)
    scope = sec("Scope and Assumptions", 140)
    background = sec("Background")
    core = sec("Core Concepts", 160)
    related = sec("Related Work", 180)
    methods = sec("Methods")
    materials = sec("Data / Materials", 140)
    procedure = sec("Procedure", 160)
    metrics = sec("Evaluation Metrics", 140)
    results = sec("Results")
    observations = sec("Observations", 140)
    discussion = sec("Discussion")
    practical = sec("Practical Implications", 140)
    theoretical = sec("Theoretical Implications", 140)
    limitations = sec("Limitations", 120)
    future = sec("Future Work", 120)
    conclusions = sec("Conclusions", 140)

    md = md_template.render(
        title=topic.strip(),
        author=author.strip() if author else "Anonymous",
        affiliation=affiliation.strip() if affiliation else "Independent Researcher",
        date=today(),
        abstract=abstract,
        keyword_line=", ".join([k.strip() for k in keywords]) if keywords else topic.lower(),
        intro=intro,
        problem=problem,
        scope=scope,
        background=background,
        core=core,
        related=related,
        methods=methods,
        materials=materials,
        procedure=procedure,
        metrics=metrics,
        results=results,
        table_md=make_table_markdown(topic),
        observations=observations,
        discussion=discussion,
        practical=practical,
        theoretical=theoretical,
        limitations=limitations,
        future=future,
        conclusions=conclusions,
        citations=citations
    )

    stub = f"{today()}_scientific-article_{slugify(topic)}"
    return md, stub


# ---------- Markdown → PDF (xhtml2pdf) ----------

HTML_TEMPLATE = Template("""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{{ title }}</title>
  <style>{{ css }}</style>
</head>
<body>
{{ body }}
</body>
</html>
""")

# Keep CSS simple for xhtml2pdf (subset CSS support)
BASE_CSS = """
@page {
  size: A4;
  margin: 2.2cm;
}
body {
  font-family: DejaVu Sans, Arial, Helvetica, sans-serif;
  line-height: 1.45;
  font-size: 11.5pt;
}
h1 { font-size: 22pt; margin: 0.2em 0 0.3em; }
h2 { font-size: 16pt; margin-top: 1.2em; }
h3 { font-size: 13pt; margin-top: 1.0em; }
p  { margin: 0.4em 0; }
hr { border: 0; border-top: 1px solid #888; margin: 1em 0; }
table { border-collapse: collapse; width: 100%; margin: 0.6em 0 1em; }
th, td { border: 1px solid #999; padding: 6px 8px; text-align: left; }
ul { margin: 0.4em 0 0.8em 1.1em; }
code, pre { font-family: Courier, monospace; font-size: 10.5pt; }
"""

def markdown_to_pdf(md_text: str, pdf_path: str, title: str):
    """Convert Markdown → HTML → PDF with xhtml2pdf."""
    html_body = md_to_html(md_text, extensions=["tables", "fenced_code"])
    html = HTML_TEMPLATE.render(title=title, css=BASE_CSS, body=html_body)
    os.makedirs(os.path.dirname(os.path.abspath(pdf_path)) or ".", exist_ok=True)
    with open(pdf_path, "wb") as f:
        result = pisa.CreatePDF(src=html, dest=f)
        if result.err:
            raise RuntimeError("xhtml2pdf failed to render PDF; try simplifying CSS/HTML.")


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        description="Generate a Markdown+PDF scientific article from a topic (LLM-powered sections; xhtml2pdf backend)."
    )
    parser.add_argument("topic", help="Topic for the scientific article, e.g., 'Quantum Computing in Healthcare'")
    parser.add_argument("--author", default="Anonymous", help="Author name (default: Anonymous)")
    parser.add_argument("--affiliation", default="Independent Researcher", help="Affiliation for title block")
    parser.add_argument("--keywords", default="", help="Comma-separated keywords")
    parser.add_argument("--outdir", default=".", help="Output directory (default: current directory)")
    parser.add_argument("--no-pdf", action="store_true", help="Only write Markdown; skip PDF generation")
    parser.add_argument("--llm", action="store_true", help="Require LLM (fail if no OPENAI_API_KEY)")
    parser.add_argument("--model", default="gpt-4o-mini", help="LLM model name (default: gpt-4o-mini)")
    args = parser.parse_args()

    # Figure out LLM use
    api_key_present = bool(os.environ.get("OPENAI_API_KEY"))
    use_llm = args.llm or api_key_present

    if args.llm and not (OPENAI_AVAILABLE and api_key_present):
        print("ERROR: --llm was set but OPENAI_API_KEY not found or openai not installed.", file=sys.stderr)
        sys.exit(2)

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    md_text, stub = generate_markdown_article(args.topic, args.author, args.affiliation, keywords, use_llm, args.model)

    os.makedirs(args.outdir, exist_ok=True)
    md_path = os.path.join(args.outdir, f"{stub}.md")
    pdf_path = os.path.join(args.outdir, f"{stub}.pdf")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    if not args.no_pdf:
        try:
            markdown_to_pdf(md_text, pdf_path, title=args.topic)
        except Exception as e:
            print(f"PDF generation failed: {e}", file=sys.stderr)
            print("Markdown was still written. You can open the .md or try another PDF backend.", file=sys.stderr)
            sys.exit(2)

    print(md_path)
    if not args.no_pdf:
        print(pdf_path)


if __name__ == "__main__":
    main()
