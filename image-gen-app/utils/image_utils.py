import base64

def decode_base64_to_bytes(b64_str: str) -> bytes:
    return base64.b64decode(b64_str)
