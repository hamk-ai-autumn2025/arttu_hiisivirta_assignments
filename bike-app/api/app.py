from fastapi import FastAPI
from pydantic import BaseModel
from db import get_conn
from openai import OpenAI
import os, json
import re
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal
from dotenv import load_dotenv
load_dotenv()


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # dev frontend origin
    allow_credentials=True,
    allow_methods=["*"],   # includes OPTIONS
    allow_headers=["*"],   # includes Content-Type
)

class Query(BaseModel):
    text: str
    max_price: int | None = None
    discipline: str | None = None   # 'road'|'gravel' optional
    height_cm: int | None = None
    inseam_cm: int | None = None

# ---- intent parsing ----

INTENT_PROMPT = """You convert a user's bike request into a strict JSON object.

Return exactly this JSON shape (all fields present):
{
  "discipline": "road" | "gravel" | null,
  "budget_eur_max": number | null,
  "comfort_priority": number | null,          // 0..1 (null if not implied)
  "tire_clearance_min_mm": number | null,
  "prefer_weight_light": number | null        // 0..1 (null if not implied)
}

Rules:
- If user says things like "under 3000", "max 2.5k", "budget 4000€", set budget_eur_max accordingly (in euros).
- If no budget is clearly stated, set budget_eur_max = null.
- If "endurance", "comfort", "long rides" etc. clearly appear, comfort_priority ~0.7..1; otherwise null.
- If "light", "climbing", "weight matters" etc. clearly appear, prefer_weight_light ~0.6..1; otherwise null.
- Discipline mapping examples:
  - "road", "aero", "endurance" -> "road"
  - "gravel", "all-road" -> "gravel"
- Output ONLY the JSON, no text.
"""

def _llm_intent(text: str) -> dict:
    msg = f"{INTENT_PROMPT}\nUser: {text}"
    out = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content": msg}],
        temperature=0
    )

    content = out.choices[0].message.content.strip()
    content = re.sub(r"^```json|```$", "", content).strip()
    try:
        return json.loads(content)
    except Exception:
        # Safety fallback
        return {
            "discipline": None,
            "budget_eur_max": None,
            "comfort_priority": None,
            "tire_clearance_min_mm": None,
            "prefer_weight_light": None,
        }

# Simple rules for things LLM often misses (budget, carbon, Di2, etc.)
_BUDGET_PATTERNS = [
    r"(?:under|below|less than|under\s*€|max|budget|enintään|alle|korkeintaan)\s*([0-9][0-9\.\,kK ]*)\s*(?:€|eur|euro)?",
    r"([0-9][0-9\.\,kK ]*)\s*(?:€|eur|euro)\s*(?:max|budget)?",
]
def _parse_money_to_int(s: str) -> int | None:
    if not s: return None
    s = s.lower().replace(" ", "")
    s = s.replace("€","").replace("eur","").replace("euro","")
    # treat k as * 1000
    if s.endswith("k"):
        s = s[:-1]
        try:
            return int(float(s.replace(",", ".").replace(" ", "")) * 1000)
        except:
            return None
    # normalize separators
    s = s.replace(".", "").replace(",", "")
    if s.isdigit():
        return int(s)
    try:
        return int(float(s))
    except:
        return None

def _regex_intent(text: str) -> dict:
    t = text.lower()

    # budget
    budget = None
    for pat in _BUDGET_PATTERNS:
        m = re.search(pat, t)
        if m:
            budget = _parse_money_to_int(m.group(1))
            if budget: break

    # discipline
    discipline = None
    if any(w in t for w in ["gravel", "all-road", "allroad", "sora"]):
        discipline = "gravel"
    elif any(w in t for w in ["road", "aero", "endurance", "maantie"]):
        discipline = "road"

    # soft prefs (optional)
    comfort = 0.8 if any(w in t for w in ["comfort", "endurance", "long rides", "roubaix", "domane"]) else None
    light = 0.8 if any(w in t for w in ["light", "climb", "climbing", "weight", "kevyt"]) else None
    clearance = None
    m = re.search(r"(?:tire|tyre|clearance)\s*(\d{2,3})\s*mm", t)
    if m:
        clearance = int(m.group(1))

    return {
        "discipline": discipline,
        "budget_eur_max": budget,
        "comfort_priority": comfort,
        "tire_clearance_min_mm": clearance,
        "prefer_weight_light": light,
    }

def parse_intent(text: str) -> dict:
    llm = _llm_intent(text)
    rx  = _regex_intent(text)

    # Merge: prefer LLM, but fill any None with regex values
    merged = {
        "discipline": llm.get("discipline") or rx["discipline"],
        "budget_eur_max": llm.get("budget_eur_max") if llm.get("budget_eur_max") is not None else rx["budget_eur_max"],
        "comfort_priority": llm.get("comfort_priority") if llm.get("comfort_priority") is not None else rx["comfort_priority"],
        "tire_clearance_min_mm": llm.get("tire_clearance_min_mm") if llm.get("tire_clearance_min_mm") is not None else rx["tire_clearance_min_mm"],
        "prefer_weight_light": llm.get("prefer_weight_light") if llm.get("prefer_weight_light") is not None else rx["prefer_weight_light"],
    }
    return merged


def reduce_to_8(vec):
    # simple bucketing: average into 8 chunks
    n = len(vec)
    buckets = 8
    out = [0.0]*buckets
    counts = [0]*buckets
    for i, v in enumerate(vec):
        b = i * buckets // n
        out[b] += float(v)
        counts[b] += 1
    return [out[i]/counts[i] if counts[i] else 0.0 for i in range(buckets)]


def embed_query(text: str):
    e = client.embeddings.create(model="text-embedding-3-small", input=text)
    full = e.data[0].embedding
    v8 = reduce_to_8(full)               # match vector(8)
    # pgvector accepts `[a,b,c,...]` as text; we'll pass it as a param and cast ::vector
    vec_str = "[" + ",".join(str(x) for x in v8) + "]"
    return vec_str

def extract_hard_filters(user_text: str):
    t = user_text.lower()
    return {
        "frame_carbon": any(w in t for w in ["carbon", "hiilikuitu"]),
        "shimano": "shimano" in t,
        "di2": "di2" in t or "electronic" in t or "sähkövaihde" in t,
        "sram": "sram" in t or "axs" in t,  # include AXS synonym
    }

def build_recommend_sql(vec, budget: int | None, discipline: str | None, user_text: str):
    hf = extract_hard_filters(user_text)

    base = """
    SELECT id, brand, model, discipline, price_eur, frame_material, tire_clearance_mm,
           groupset, weight_kg, url, image_url, description,
           1 - (embedding <=> %s::vector) AS sim
    FROM bikes
    """
    where = []
    params = [vec]

    if budget is not None:
        where.append("price_eur <= %s")
        params.append(budget)

    if discipline:
        where.append("discipline = %s")
        params.append(discipline)

    # --- more resilient DI2/AXS/carbon matching ---
    di2_or = """(
        groupset ILIKE '%%di2%%'
        OR description ILIKE '%%di2%%'
        OR groupset ~* '(r9(250|170)|r8(150|170)|r7(170))'  -- Dura-Ace/Ultegra/105 Di2 codes
        OR description ~* '(r9(250|170)|r8(150|170)|r7(170))'
    )"""
    axs_or = """(
        groupset ILIKE '%%axs%%'
        OR description ILIKE '%%axs%%'
        OR groupset ~* '(red|force|rival).*axs'
        OR description ~* '(red|force|rival).*axs'
    )"""

    if hf["frame_carbon"]:
        where.append("(frame_material ILIKE '%%carbon%%')")

    if hf["di2"]:
        where.append(di2_or)

    if hf["shimano"]:
        where.append("(groupset ILIKE '%%shimano%%' OR description ILIKE '%%shimano%%')")

    if hf["sram"]:
        where.append(axs_or)

    if where:
        base += "WHERE " + " AND ".join(where) + "\n"

    base += "ORDER BY embedding <=> %s::vector\nLIMIT 12;"
    params.append(vec)

    return base, params


@app.post("/recommend")
def recommend(q: Query):
    # 1) intent
    intent = parse_intent(q.text)
    budget = q.max_price or intent.get("budget_eur_max")

    # 2) DB filter + vector search
    vec = embed_query(q.text)
    sql, params = build_recommend_sql(vec, budget, q.discipline or intent.get("discipline"), q.text)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = [dict(zip([c.name for c in cur.description], r)) for r in cur.fetchall()]

        if not rows:
            # retry without DI2/AXS/carbon constraints, but keep budget/discipline
            base = """
            SELECT id, brand, model, discipline, price_eur, frame_material, tire_clearance_mm,
                groupset, weight_kg, url, image_url, description,
                1 - (embedding <=> %s::vector) AS sim
            FROM bikes
            """
            where = []
            params2 = [vec]
            if budget is not None:
                where.append("price_eur <= %s"); params2.append(budget)
            if q.discipline or intent.get("discipline"):
                where.append("discipline = %s"); params2.append(q.discipline or intent.get("discipline"))
            if where:
                base += "WHERE " + " AND ".join(where) + "\n"
            base += "ORDER BY embedding <=> %s::vector LIMIT 12;"
            params2.append(vec)

            cur.execute(base, params2)
            rows = [dict(zip([c.name for c in cur.description], r)) for r in cur.fetchall()]

# 3) LLM explanation grounded ONLY on provided rows
    facts = [
        {k: r[k] for k in [
            "brand","model","discipline","price_eur","frame_material",
            "tire_clearance_mm","groupset","weight_kg","url","image_url","description","sim"
        ]}
        for r in rows
    ]

    explain_prompt = f"""Given these bike candidates (JSON below), choose TOP 6 and explain WHY they match the user's request.
    Use ONLY these fields; do not invent specs. Keep each explanation ≤80 words.
    Return JSON array (max 6 items): [{{"brand": string, "model": string, "reason": string, "url": string, "image_url": string}}]
    User request: {q.text}
    Candidates: {json.dumps(facts, default=lambda o: float(o) if isinstance(o, Decimal) else o, ensure_ascii=False)}
    """

    top6 = None
    try:
        out = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": explain_prompt}],
            temperature=0.1,
            # If your model supports it, you can force JSON:
            # response_format={"type": "json_object"}  # or {"type": "json"}
        )
        content = (out.choices[0].message.content or "").strip()
        # Strip common code fences if present
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE).strip()

        parsed = json.loads(content)
        if isinstance(parsed, dict) and "results" in parsed and isinstance(parsed["results"], list):
            items = parsed["results"]
        elif isinstance(parsed, list):
            items = parsed
        else:
            items = []

        top6 = items[:6]
    except Exception as e:
        # Optional: log to server console for debugging
        print("LLM explain parse failed:", e)

    # Fallback: if LLM parsing failed, return the top 6 by similarity with a simple reason
    if not top6:
        def _fmt_price(v):
            try:
                from decimal import Decimal as _D
                if isinstance(v, _D):
                    v = float(v)
                return f"€{int(v):,}".replace(",", " ")
            except Exception:
                return "price N/A"

        rows_sorted = sorted(rows, key=lambda r: float(r.get("sim", 0) or 0), reverse=True)[:6]
        top6 = [
            {
                "brand": r.get("brand"),
                "model": r.get("model"),
                "reason": f"{(r.get('discipline') or '').title()} bike, {r.get('frame_material') or 'material N/A'} frame, "
                        f"{r.get('groupset') or 'groupset N/A'}, {_fmt_price(r.get('price_eur'))}.",
                "url": r.get("url"),
                "image_url": r.get("image_url"),
            }
            for r in rows_sorted
        ]

    return {"intent": intent, "results": top6}

