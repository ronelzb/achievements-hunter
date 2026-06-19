from dotenv import dotenv_values

_env = dotenv_values()

# Steam
API_KEY = _env.get("STEAM_API_KEY", "YOUR_API_KEY_HERE") or "YOUR_API_KEY_HERE"
_raw_id = _env.get("STEAM_ID") or ""
MY_ID = "" if _raw_id in ("", "YOUR_STEAM64_ID_HERE") else _raw_id
_raw_friends = _env.get("STEAM_FRIENDS") or ""
FRIENDS_OVERRIDE = [
    friend.strip() for friend in _raw_friends.split(",") if friend.strip()
]

# Database
DATABASE_URL = _env.get("DATABASE_URL") or "sqlite:///data/platinum.db"

# LLM
LLM_PROVIDER = _env.get("LLM_PROVIDER") or ""
LLM_MODEL = _env.get("LLM_MODEL") or ""
LLM_MAX_TOKENS = int(_env.get("LLM_MAX_TOKENS") or 3000)
ANTHROPIC_API_KEY = _env.get("ANTHROPIC_API_KEY") or ""
OPENAI_API_KEY = _env.get("OPENAI_API_KEY") or ""
