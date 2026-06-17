import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("STEAM_API_KEY", "YOUR_API_KEY_HERE")
MY_ID = os.getenv("STEAM_ID", "YOUR_STEAM64_ID_HERE")
_raw_friends = os.getenv("STEAM_FRIENDS", "")
FRIENDS_OVERRIDE = [
    friend.strip() for friend in _raw_friends.split(",") if friend.strip()
]
