# Steam YTD Achievement Leaderboard

Compare how many Steam achievements you and your friends have earned this calendar year.

## Setup

### 1. Install dependencies

```bash
uv sync
uv run python -m pre_commit install
```

### 2. Get your Steam API key

Go to <https://steamcommunity.com/dev/apikey> — it's free and instant.

### 3. Configure credentials

Create a `.env` file in the project root:

```env
STEAM_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# Optional — if omitted, your Steam64 ID is read automatically from the
# session stored by steam-login (see Usage below).
# STEAM_ID=76561198XXXXXXXXX

# Optional — required if your Steam friends list is not set to Public.
# Comma-separated vanity names (steamcommunity.com/id/NAME) or Steam64 IDs.
# STEAM_FRIENDS=somevanityname,anotherplayer,76561198009876543
```

The scripts read `.env` on every run — no shell exports or restarts needed.

## Usage

All commands are available as installed entry points (`uv run <command>`) or directly via `python scripts/<script>.py`. See [scripts/README.md](scripts/README.md) for full flag reference and example output.

| Command | Description |
| --- | --- |
| `uv run steam-achievements` | YTD achievement leaderboard across you and your friends |
| `uv run steam-friends` | Browse your friends list with display name, Steam ID, and visibility |
| `uv run steam-login` | Authenticate and store a session so private game libraries are readable |

### Authentication note

If your own **Game details** privacy setting is not Public, `steam-achievements` returns
empty results for your own account. Run `steam-login` once to store a session in your OS
keychain (Windows Credential Manager / macOS Keychain / Linux Secret Service) — no
profile changes required. The session also lets you omit `STEAM_ID` from `.env` entirely.

> **Note:** This only unlocks *your own* data. Friends with private profiles still
> show 0 — there is no bypass without their session.

## How it works

1. Fetches your friend list via `GetFriendList` (or `STEAM_FRIENDS` from `.env` if set)
2. For each player (you + friends), fetches all owned games with playtime > 0
3. For each played game, calls `GetPlayerAchievements` to get unlock timestamps
4. Filters to achievements where `unlocktime` falls within the target year
5. Sums and ranks everyone

`--filter` applies before step 2 — only matching friends have their achievements
fetched, so filtered runs are faster on large friend lists.

## Caveats

- **Friends list privacy**: Steam's API returns 401 for any setting below Public (including "Friends Only"), regardless of your API key. If you'd rather not change your privacy settings, add `STEAM_FRIENDS` to your `.env` with a comma-separated list of vanity names (the username in `steamcommunity.com/id/USERNAME`) or Steam64 IDs — the script will use those instead. To use the API instead, go to **View my profile → Edit profile → Privacy Settings → Friends List → Public**.
- **Your own privacy**: If *your* Game details are not Public, your own games and achievements return empty from the Web API. Run `steam-login` (see above) to authenticate as yourself and bypass this — no profile changes required.
- **Friends' privacy**: Friends with private "Game details" will still show 0. The only bypass is their own session cookie, which isn't feasible to collect. The cleanest ask: have them set Game details to Public (it only exposes game library and achievement timestamps, not payment info).
- **Speed**: If a friend owns 500+ played games, their fetch takes 20–60 seconds depending on concurrency. The default of 4 parallel requests per player is safe; bump to 8 if you want speed and Steam doesn't throttle you.
- **Rate limits**: Steam's API is lenient for personal keys but will 429 you if you hammer it. The script auto-retries with backoff.
- **App-level privacy**: Some games hide achievements even on public profiles (e.g., adult games). These are silently skipped.
- **Why the API key can't be dropped**: `ISteamUserStats/GetPlayerAchievements` requires a developer API key — it is not in Steam's OAuth-enabled service list (`ICloudService`, `IBroadcastService`, `IGameNotificationsService`, `IPlayerService`, `IPublishedFileService`) and does not honour user access tokens from `IAuthenticationService`. Third-party sites like SteamDB work the same way: they register their own key and can only read public profiles. The `steam-login` session unlocks your *own* private library via `IPlayerService/GetOwnedGames`, but achievement fetching always goes through the developer key. [Reference: partner.steamgames.com/doc/webapi/isteamuserstats]
