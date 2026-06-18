from dotenv import dotenv_values

_env = dotenv_values()

API_KEY = _env.get("STEAM_API_KEY", "YOUR_API_KEY_HERE") or "YOUR_API_KEY_HERE"
_raw_id = _env.get("STEAM_ID") or ""
MY_ID = "" if _raw_id in ("", "YOUR_STEAM64_ID_HERE") else _raw_id
_raw_friends = _env.get("STEAM_FRIENDS") or ""
FRIENDS_OVERRIDE = [
    friend.strip() for friend in _raw_friends.split(",") if friend.strip()
]
