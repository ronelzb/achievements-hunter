import base64
import hashlib
import json
import re


def decode_token(cookie: str) -> dict | None:
    """Decodes the JWT embedded in a steamLoginSecure cookie value."""
    try:
        jwt = cookie.split("||", 1)[-1]
        payload_b64 = jwt.split(".")[1]
        padding = "=" * ((-len(payload_b64)) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except Exception:
        return None


def truncate(text: str, width: int) -> str:
    if len(text) > width:
        return text[: width - 1] + "…"
    return text


def game_slug(game_name: str) -> str:
    """Return a URL-safe slug for a game name (e.g. 'The Evil Within' → 'the-evil-within')."""
    return re.sub(r"[^a-z0-9]+", "-", game_name.lower()).strip("-")


def content_hash(text: str) -> str:
    """Return a SHA-256 hex digest of *text* for content-based deduplication."""
    return hashlib.sha256(text.encode()).hexdigest()
