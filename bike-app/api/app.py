from fastapi import FastAPI
from pydantic import BaseModel
from db import get_conn
from openai import OpenAI
import os, json
import re
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal


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

INTENT_PROMPT = """You turn a user's free-text into JSON constraints for a bike search.
Fields: discipline ('road'|'gravel'), budget_eur_max (int), comfort_priority (0-1),
tire_clearance_min_mm (int or null), prefer_weight_light (0-1).
Only output JSON, no commentary.
User: {q}
"""

def parse_intent(text: str) -> dict:
    msg = INTENT_PROMPT.format(q=text)
    out = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content": msg}],
        temperature=0
    )
    # Best-effort JSON parse
    content = out.choices[0].message.content.strip()
    content = re.sub(r"^```json|```$", "", content).strip()
    return json.loads(content)

def embed_query(text: str):
    e = client.embeddings.create(model="text-embedding-3-small", input=text)
    return e.data[0].embedding

def build_recommend_sql(vec, budget: int | None, discipline: str | None):
    base = """
    SELECT id, brand, model, discipline, price_eur, frame_material, tire_clearance_mm,
           groupset, weight_kg, stack_mm, reach_mm, size_label, url, image_url, spec_text,
           1 - (embedding <=> %s::vector) AS sim
    FROM bikes
    """
    where = []
    params = [vec]  # First %s is used in the SELECT similarity calculation

    if budget is not None:
        where.append("price_eur <= %s")
        params.append(budget)

    if discipline:
        where.append("discipline = %s")
        params.append(discipline)

    if where:
        base += "WHERE " + " AND ".join(where) + "\n"

    base += "ORDER BY embedding <=> %s::vector\nLIMIT 6;"
    params.append(vec)  # Last %s is for the ORDER BY clause

    return base, params


@app.post("/recommend")
def recommend(q: Query):
    # 1) intent
    intent = parse_intent(q.text)
    budget = q.max_price or intent.get("budget_eur_max")

    # 2) DB filter + vector search
    vec = embed_query(q.text)
    sql, params = build_recommend_sql(vec, budget, q.discipline)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = [dict(zip([c.name for c in cur.description], r)) for r in cur.fetchall()]


    # 3) LLM explanation grounded ONLY on provided rows
    facts = [
      {k: r[k] for k in ["brand","model","discipline","price_eur","frame_material",
                         "tire_clearance_mm","groupset","weight_kg","stack_mm","reach_mm",
                         "size_label","url","image_url","sim"]}
      for r in rows
    ]
    explain_prompt = f"""Given these bike candidates (JSON below), choose TOP 3 and explain WHY they match the user's request.
Use ONLY these fields; do not invent specs. Keep each explanation ≤80 words.
Return JSON: [{{brand, model, reason, url, image_url}}]
User request: {q.text}
Candidates: {json.dumps(facts, default=lambda o: float(o) if isinstance(o, Decimal) else o, ensure_ascii=False)}

"""
    out = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content": explain_prompt}],
        temperature=0.2
    )
    content = out.choices[0].message.content.strip()
    content = re.sub(r"^```json|```$", "", content).strip()
    top3 = json.loads(content)
    return {"intent": intent, "results": top3}
