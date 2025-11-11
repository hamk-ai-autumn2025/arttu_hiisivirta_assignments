import csv, os
from openai import OpenAI
from db import get_conn
from dotenv import load_dotenv
load_dotenv()

EMBED_MODEL = "text-embedding-3-small"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def make_spec_text(row):
    # Short, consistent canonical text for semantic search:
    return (
        f"{row['brand']} {row['model']} is a {row['discipline']} bike. "
        f"Price {row['price_eur']} EUR. Frame {row['frame_material']}. "
        f"Tire clearance {row['tire_clearance_mm']} mm. Groupset {row['groupset']}. "
        f"Weight {row['weight_kg']} kg. Geometry stack {row['stack_mm']} mm, reach {row['reach_mm']} mm."
    )

def embed(text):
    out = client.embeddings.create(model=EMBED_MODEL, input=text)
    return out.data[0].embedding

def ingest(csv_path: str):
    with get_conn() as conn, conn.cursor() as cur, open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            spec_text = make_spec_text(row)
            vec = embed(spec_text)
            cur.execute("""
                INSERT INTO bikes (brand, model, discipline, price_eur, frame_material,
                    tire_clearance_mm, groupset, weight_kg, stack_mm, reach_mm, size_label,
                    url, image_url, spec_text, embedding)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, %s)
            """, (
                row["brand"], row["model"], row["discipline"], int(row["price_eur"]),
                row["frame_material"], int(row["tire_clearance_mm"]), row["groupset"],
                float(row["weight_kg"]), int(row["stack_mm"]), int(row["reach_mm"]),
                row["size_label"], row["url"], row["image_url"], spec_text, vec
            ))

if __name__ == "__main__":
    import sys
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "../bikes_seed.csv"
    ingest(csv_path)

