import csv
import json
from decimal import Decimal
from typing import List, Any
from db import get_conn


def make_embedding(description: str) -> List[float]:
    """
    Temporary / fallback embedding.
    Right now we don't call an API model to embed the text, so we just return
    a deterministic 8-dim vector.

    You can later replace this with a real embedding model and bump the
    DB column type to vector(1536) etc.
    """
    # Very dumb hash -> 8 floats trick just so every row isn't identical.
    vals = [0.0] * 8
    for i, ch in enumerate(description.encode("utf-8")):
        vals[i % 8] += (ch % 13) / 10.0  # spread bytes into 0.0..1.2 ranges
    return vals


def to_decimal_safe(val: str) -> Any:
    """
    Convert numeric-looking CSV fields to Decimal, otherwise None or string.
    If field is empty or '-', return None.
    """
    if val is None:
        return None
    txt = val.strip()
    if txt == "" or txt == "-":
        return None
    try:
        # store as Decimal so psycopg can insert into NUMERIC
        return Decimal(txt)
    except Exception:
        return None


def ingest(csv_path: str) -> None:
    """
    Read bikes_seed.csv and insert rows into the bikes table.
    If a row with same (brand, model, url) already exists, skip it.
    """
    with get_conn() as conn, conn.cursor() as cur, open(csv_path, newline='', encoding='utf-8') as f:

        reader = csv.DictReader(f)

        for row in reader:
            # --- clean / map columns from CSV ---
            brand = row.get("brand", "").strip()
            model = row.get("model", "").strip()
            discipline = row.get("discipline", "").strip()
            price_eur = to_decimal_safe(row.get("price_eur"))
            frame_material = row.get("frame_material", "").strip()
            tire_clearance_mm = row.get("tire_clearance_mm", "").strip()
            groupset = row.get("groupset", "").strip()
            weight_kg = to_decimal_safe(row.get("weight_kg"))
            url = row.get("url", "").strip()
            image_url = row.get("image_url", "").strip()
            description = row.get("description", "").strip()

            # make sure we have *some* description text for embedding source
            full_text = (
                f"{brand} {model}. "
                f"{discipline} bike. "
                f"Frame: {frame_material}. "
                f"Groupset: {groupset}. "
                f"Weight: {weight_kg} kg. "
                f"Details: {description}"
            ).strip()

            embedding_vec = make_embedding(full_text)

            # --- check for duplicate before inserting ---
            cur.execute(
                """
                SELECT id FROM bikes
                WHERE brand = %s AND model = %s AND url = %s
                """,
                (brand, model, url),
            )
            already = cur.fetchone()
            if already:
                print(f"SKIP (already exists): {brand} {model}")
                continue

            # --- insert row ---
            cur.execute(
                """
                INSERT INTO bikes (
                    brand,
                    model,
                    discipline,
                    price_eur,
                    frame_material,
                    tire_clearance_mm,
                    groupset,
                    weight_kg,
                    url,
                    image_url,
                    description,
                    embedding
                )
                VALUES (
                    %(brand)s,
                    %(model)s,
                    %(discipline)s,
                    %(price_eur)s,
                    %(frame_material)s,
                    %(tire_clearance_mm)s,
                    %(groupset)s,
                    %(weight_kg)s,
                    %(url)s,
                    %(image_url)s,
                    %(description)s,
                    %(embedding)s
                )
                """,
                {
                    "brand": brand,
                    "model": model,
                    "discipline": discipline,
                    "price_eur": price_eur,
                    "frame_material": frame_material,
                    "tire_clearance_mm": tire_clearance_mm,
                    "groupset": groupset,
                    "weight_kg": weight_kg,
                    "url": url,
                    "image_url": image_url,
                    "description": description,
                    # psycopg understands Python list[float] for vector(n)
                    "embedding": embedding_vec,
                },
            )

        print("Done ingesting bikes.")


if __name__ == "__main__":
    # relative path like ../bikes_seed.csv
    csv_path = "../bikes_seed.csv"
    ingest(csv_path)
