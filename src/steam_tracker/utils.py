import base64
import json


def decode_token(cookie: str) -> dict | None:
    """Decodes the JWT embedded in a steamLoginSecure cookie value."""
    try:
        jwt = cookie.split("||", 1)[-1]
        payload_b64 = jwt.split(".")[1]
        padding = "=" * ((-len(payload_b64)) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except Exception:
        return None
