# Steam YTD Achievement Leaderboard

Compare how many Steam achievements you and your friends have earned this calendar year.

## Setup

### 1. Install dependencies

```bash
uv sync
uv run python -m pre_commit install
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

### (Optional) Authenticate with Steam

If your own **Game details** privacy setting is not Public, the Steam Web API returns
empty results for your account even though the API key is yours. Running `steam-login`
stores a session cookie in your OS keychain (Windows Credential Manager / macOS Keychain /
Linux Secret Service) so the leaderboard can fetch your own data without changing any
privacy settings:

```bash
python scripts/steam_login.py
# Steam Login
# ----------------------------------------
# Steam username: your_username
# Password:
# (Steam Guard code prompt appears here only if you have Steam Guard enabled)
# Login successful — session saved to keychain.
```

The session persists across runs. Re-run `steam-login` if it ever expires (typically
after several weeks). A saved session is silently validated each run; a prompt only
appears when the session is missing or stale.

> **Note:** This only unlocks *your own* data. Friends with private profiles still
> show 0 — there is no bypass without their session.
>
> **Future:** Steam also supports QR-code login (scan with the mobile app — no password
> typed). This would require migrating to Steam's newer `IAuthenticationService` API,
> which is a separate implementation from the current credential flow. Not supported yet.

## Caveats

- **Friends list privacy**: Steam's API returns 401 for any setting below Public (including "Friends Only"), regardless of your API key. If you'd rather not change your privacy settings, add `STEAM_FRIENDS` to your `.env` with a comma-separated list of vanity names (the username in `steamcommunity.com/id/USERNAME`) or Steam64 IDs — the script will use those instead. To use the API instead, go to **View my profile → Edit profile → Privacy Settings → Friends List → Public**.
- **Your own privacy**: If *your* Game details are not Public, your own games and achievements return empty from the Web API. Run `steam-login` (see Setup step 4) to authenticate as yourself and bypass this — no profile changes required.
- **Friends' privacy**: Friends with private "Game details" will still show 0. The only bypass is their own session cookie, which isn't feasible to collect. The cleanest ask: have them set Game details to Public (it only exposes game library and achievement timestamps, not payment info).
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
