# Steam YTD Achievement Leaderboard

Compare how many Steam achievements you and your friends have earned this calendar year.

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Get your Steam credentials

| Thing | Where to get it |
| --- | --- |
| **API Key** | <https://steamcommunity.com/dev/apikey> (free, instant) |
| **Your Steam64 ID** | Open `https://steamcommunity.com/id/YOUR_USERNAME?xml=1` in a browser — the `<steamID64>` tag at the top is your ID |

### 3. Configure credentials

Create a `.env` file in the project root:

```env
STEAM_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
STEAM_ID=76561198XXXXXXXXX

# Optional — required if your Steam friends list is not set to Public.
# Comma-separated vanity names (steamcommunity.com/id/NAME) or Steam64 IDs.
# STEAM_FRIENDS=somevanityname,anotherplayer,76561198009876543
```

The script loads it automatically via `python-dotenv`. No shell exports needed.

## Usage

```bash
# Current year, all friends
python scripts/steam_ytd_achievements.py

# Show only top 5
python scripts/steam_ytd_achievements.py --top 5

# Check a specific year
python scripts/steam_ytd_achievements.py --year 2025

# Increase parallelism (faster but more aggressive on rate limits)
python scripts/steam_ytd_achievements.py --concurrency 8
```

## How it works

1. Fetches your friend list via `GetFriendList`
2. For each player (you + friends), fetches all owned games with playtime > 0
3. For each played game, calls `GetPlayerAchievements` to get unlock timestamps
4. Filters to achievements where `unlocktime` falls within the target year
5. Sums and ranks everyone

## Caveats

- **Friends list privacy**: Steam's API returns 401 for any setting below Public (including "Friends Only"), regardless of your API key. If you'd rather not change your privacy settings, add `STEAM_FRIENDS` to your `.env` with a comma-separated list of vanity names (the username in `steamcommunity.com/id/USERNAME`) or Steam64 IDs — the script will use those instead. To use the API instead, go to **View my profile → Edit profile → Privacy Settings → Friends List → Public**.
- **Private profiles**: Friends with private profiles will show 0 (the API returns nothing). Steam has no way around this.
- **Speed**: If a friend owns 500+ played games, their fetch takes 20–60 seconds depending on concurrency. The default of 4 parallel requests per player is safe; bump to 8 if you want speed and Steam doesn't throttle you.
- **Rate limits**: Steam's API is lenient for personal keys but will 429 you if you hammer it. The script auto-retries with backoff.
- **App-level privacy**: Some games hide achievements even on public profiles (e.g., adult games). These are silently skipped.

## Example output

```text
🎮  Steam YTD Achievement Leaderboard — 2026
====================================================
  Friends found: 12
  ⏳ Fetching: Cambur (YOU)
  ⏳ Fetching: SteamFriend1
  ⏳ Fetching: SteamFriend2
  ...

Rank  Player                       Achievements
────────────────────────────────────────────────
🥇    Cambur                          127 ◀ YOU
🥈    SteamFriend1                           94
🥉    SteamFriend2                           61
  4.  SteamFriend3                           42

🏆  You're #1 with 127 achievements in 2026. Nice.
```
