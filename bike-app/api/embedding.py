# embedding.py
# Responsible for turning bike spec text into a numeric embedding vector.

import os
from decimal import Decimal

# In the prototype we originally used a real embedding model.
# For local/offline/dev use on Windows, we can fall back to a dummy vector
# so the ingest script still works and the DB can be populated.

def embed_text(text: str):
    """
    Return an embedding list[float] for `text`.
    In production this should call the actual embedding model.
    For now we just make a deterministic fake vector so we can test search.
    """
    # Simple stable hash -> 8 floats
    h = abs(hash(text))
    vec = []
    for i in range(8):
        part = (h >> (i * 8)) & 0xFF  # take 1 byte at a time
        vec.append(float(part) / 255.0)
    return vec
