# Command Reference

All commands are available as `uv run <command>` (entry points) or `python scripts/<script>.py`.

## `steam-achievements` — YTD leaderboard

```bash
# Current year, all friends
uv run steam-achievements

# Show only top 5
uv run steam-achievements --top 5

# Check a specific year
uv run steam-achievements --year 2025

# Compare with specific friends (case-insensitive partial match)
uv run steam-achievements --filter cambur alpha

# Increase parallelism (faster but more aggressive on rate limits)
uv run steam-achievements --concurrency 8

# Print raw API errors for troubleshooting
uv run steam-achievements --debug
```

| Flag | Default | Description |
| --- | --- | --- |
| `--year` | current year | Calendar year to rank achievements in |
| `--top N` | all | Show only top N players (you are always appended if outside top N) |
| `--filter NAME …` | all friends | Compare only with friends whose display name contains any NAME (case-insensitive partial match) |
| `--concurrency N` | 4 | Parallel API requests per player |
| `--debug` | off | Print raw API errors and session diagnostics |

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

## `steam-game` — list achievements for a game

```bash
# Search by name (pick from results if multiple matches)
uv run steam-game "Elden Ring"

# Skip search with a known App ID
uv run steam-game --app-id 1245620

# Show only achievements you've won
uv run steam-game "Elden Ring" --filter won

# Show only achievements you haven't won yet
uv run steam-game "Elden Ring" --filter not-won

# Use Steam's schema order instead of won-first
uv run steam-game "Elden Ring" --sort steam

# Print raw API errors for troubleshooting
uv run steam-game "Elden Ring" --debug
```

| Flag | Default | Description |
| --- | --- | --- |
| `query` | — | Game name to search on the Steam store |
| `--app-id ID` | — | Steam App ID; skips the search step |
| `--filter won\|not-won\|all` / `-f` | all | Show only won, not-won, or all achievements |
| `--sort won-first\|steam` / `-s` | won-first | Sort: won (newest first) then not-won, or Steam schema order |
| `--debug` / `-d` | off | Print raw API errors |

```text
Game: Elden Ring (App ID: 1245620)
Achievements: 34 / 42 won (81.0%)

  #    Achievement                   Description                              Unlocked
 ────────────────────────────────────────────────────────────────────────────────────
   1 ✓ Elden Ring                    Obtained the Elden Ring. The            2024-03-10
                                     impossible was made possible.
   2 ✓ Legendary Armaments           Acquired all legendary armaments.       2024-02-28
  ...
  41 ✗ Legendary Sorceries and       Acquired all legendary sorceries and    —
       Incantations                  incantations.
```

## `steam-friends` — browse your friends list

```bash
# List all friends with display name, real name, Steam64 ID, and profile visibility
uv run steam-friends

# Filter to friends whose display name contains a term (case-insensitive, partial)
uv run steam-friends --filter cambur
uv run steam-friends -f cambur alpha

# Print raw API errors for troubleshooting
uv run steam-friends --debug
```

| Flag | Default | Description |
| --- | --- | --- |
| `--filter NAME …` / `-f` | all friends | Show only friends whose display name contains any NAME |
| `--debug` / `-d` | off | Print raw API errors and session diagnostics |

```text
Display Name                 Real Name              Steam64 ID          Visibility
─────────────────────────────────────────────────────────────────────────────────
AlphaGamer                   —                      76561198000000002   Private
Zephyr                       John Doe               76561198000000001   Public

  2 friend(s) listed.
```

## `steam-login` — authenticate as yourself

Stores a session cookie in your OS keychain (Windows Credential Manager / macOS
Keychain / Linux Secret Service). Required if your **Game details** privacy setting
is not Public. Also lets you omit `STEAM_ID` from `.env` — the Steam64 ID is
derived automatically from the stored session.

```bash
uv run steam-login
# Steam Login
# ----------------------------------------
# Steam username: your_username
# Password:
# (Steam Guard prompt appears here if Steam Guard is enabled)
# Login successful — session saved to keychain.

# Log out and clear the stored session
uv run steam-login --logout

# Check session status without prompting for credentials
uv run steam-login --login --debug
```

| Flag | Description |
| --- | --- |
| `--login` | Validate existing session or prompt for credentials (default action) |
| `--logout` | Clear the stored session and refresh token from the keychain |
| `--debug` | Print session token claims and validation details |

The session persists across runs. Re-run `steam-login` if it ever expires (typically
after several weeks). A saved session is silently validated each run; a prompt only
appears when the session is missing or stale.

> **Note:** This only unlocks *your own* data. Friends with private profiles still
> show 0 — there is no bypass without their session.
>
> **Future:** Steam also supports QR-code login (scan with the mobile app — no password
> typed). This would require migrating to Steam's newer `IAuthenticationService` API,
> which is a separate implementation from the current credential flow. Not supported yet.
