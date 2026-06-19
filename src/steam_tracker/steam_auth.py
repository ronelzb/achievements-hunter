import argparse
import base64
import contextlib
import getpass
import time

import keyring
import rsa

from .settings import MY_ID
from .steam_api import (
    begin_auth,
    finalize_session,
    poll_auth_session,
    submit_guard_code,
)
from .steam_http import community_get, community_post
from .utils import decode_token

_KEYRING_SERVICE = "achievements-hunter"
_KEYRING_USERNAME = "steamLoginSecure"
_KEYRING_REFRESH = "steamRefreshToken"


def load_session() -> str | None:
    return keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)


def save_session(cookie: str) -> None:
    keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, cookie)


def load_refresh_token() -> str | None:
    return keyring.get_password(_KEYRING_SERVICE, _KEYRING_REFRESH)


def save_refresh_token(token: str) -> None:
    keyring.set_password(_KEYRING_SERVICE, _KEYRING_REFRESH, token)


def logout() -> None:
    """Removes the stored session cookie and refresh token from the keyring."""
    for username in (_KEYRING_USERNAME, _KEYRING_REFRESH):
        with contextlib.suppress(Exception):
            keyring.delete_password(_KEYRING_SERVICE, username)


def steam_id_from_session(*, debug: bool = False) -> str | None:
    """Extracts the Steam64 ID from the stored session cookie.

    Tries the steamid||jwt prefix format first, then falls back to the JWT
    sub claim (Steam embeds the Steam64 ID there in the current token format).
    """
    cookie = load_session()
    if not cookie:
        if debug:
            print("[debug] no session cookie in keyring — run steam-login first")
        return None
    if debug:
        _payload = decode_token(cookie)
        if _payload:
            _mask = {"sub", "steamid", "jti", "iss", "ip_subject", "ip_confirmer"}
            _masked = {
                k: (
                    str(v)[:4] + "…" + str(v)[-3:]
                    if k in _mask and len(str(v)) > 6
                    else v
                )
                for k, v in _payload.items()
            }
            print(f"[debug] session token claims: {_masked}")
        else:
            print("[debug] session cookie found but JWT could not be decoded")
    parts = cookie.split("||", 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[0]
    payload = decode_token(cookie)
    if payload:
        sub = str(payload.get("sub", ""))
        if sub.isdigit():
            return sub
    if debug:
        print(
            "[debug] session cookie found but Steam ID could not be extracted — unexpected format"
        )
    return None


def get_my_id(*, debug: bool = False) -> str | None:
    """Returns the user's Steam64 ID from STEAM_ID env var or the stored session cookie."""
    return MY_ID or steam_id_from_session(debug=debug)


def _token_expiry(cookie: str) -> int | None:
    """Returns the exp claim from the JWT embedded in a steamLoginSecure cookie, or None."""
    payload = decode_token(cookie)
    exp = payload.get("exp") if payload is not None else None
    return int(exp) if exp is not None else None


def validate_session(cookie: str, *, debug: bool = False) -> bool:
    """Returns True if the session cookie still grants access to steamcommunity.com."""
    exp = _token_expiry(cookie)
    if exp is not None and time.time() > exp:
        if debug:
            print(f"[debug] session validation: token expired (exp={exp})")
        return False
    response = community_get("my/", cookies={"steamLoginSecure": cookie})
    if response is None:
        if debug:
            print("[debug] session validation: no response (network error or timeout)")
        return False
    if "login" in response.url:
        if debug:
            print(f"[debug] session validation: redirected to {response.url}")
        return False
    return True


def get_rsa_key(username: str) -> dict:
    """Fetches Steam's RSA public key for the given username."""
    response = community_post("login/getrsakey/", data={"username": username})
    response.raise_for_status()
    return response.json()


def encrypt_password(password: str, mod: str, exp: str) -> str:
    """RSA-encrypts the password with Steam's public key; returns base64-encoded ciphertext."""
    public_key = rsa.PublicKey(int(mod, 16), int(exp, 16))
    encrypted = rsa.encrypt(password.encode("utf-8"), public_key)
    return base64.b64encode(encrypted).decode("utf-8")


def _select_and_submit_guard(
    conf_types: set[int], client_id: str, steam_id: str
) -> None:
    """Presents available Steam Guard options and submits the user's chosen method."""
    options: list[tuple[int, str]] = []
    if 4 in conf_types:
        options.append((4, "Tap Approve in your Steam mobile app"))
    if 3 in conf_types:
        options.append((3, "Enter authenticator code"))
    if 2 in conf_types:
        options.append((2, "Enter email code"))
    if not options:
        return

    if len(options) == 1:
        chosen = options[0][0]
    else:
        print("Steam Guard verification — choose a method:")
        for i, (_, label) in enumerate(options, start=1):
            print(f"  [{i}] {label}")
        while True:
            raw = input("Choice [1]: ").strip() or "1"
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                chosen = options[int(raw) - 1][0]
                break
            print(f"  Please enter a number between 1 and {len(options)}.")

    if chosen == 4:
        print("Check your Steam mobile app and tap Approve.")
    elif chosen == 3:
        code = input("Steam Guard code (authenticator app): ").strip()
        submit_guard_code(client_id, steam_id, code, code_type=3)
    elif chosen == 2:
        code = input("Steam Guard code (sent to your email): ").strip()
        submit_guard_code(client_id, steam_id, code, code_type=2)


def login(username: str, password: str, *, debug: bool = False) -> str:
    """Full login flow using Steam's current auth API. Returns the steamLoginSecure cookie value."""
    rsa_data = get_rsa_key(username)
    encrypted = encrypt_password(
        password, rsa_data["publickey_mod"], rsa_data["publickey_exp"]
    )
    data = begin_auth(username, encrypted, rsa_data["timestamp"])

    client_id = data["client_id"]
    request_id = data["request_id"]
    steam_id = data.get("steamid", "")
    interval = float(data.get("interval", 5.0))

    conf_types = {
        c.get("confirmation_type") for c in data.get("allowed_confirmations", [])
    }
    if debug:
        print(f"[debug] confirmation types offered: {sorted(conf_types)}")

    _select_and_submit_guard(conf_types, client_id, steam_id)

    refresh_token = poll_auth_session(client_id, request_id, interval)
    save_refresh_token(refresh_token)
    return finalize_session(refresh_token, steam_id, debug=debug)


def main() -> None:
    parser = argparse.ArgumentParser(description="Steam authentication manager")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--login", action="store_true", help="Authenticate and store session"
    )
    group.add_argument(
        "--logout", action="store_true", help="Clear stored session and tokens"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print detailed auth diagnostics"
    )
    args = parser.parse_args()

    if args.logout:
        logout()
        print("Logged out — session and tokens cleared.")
        return

    existing = load_session()
    if existing and validate_session(existing, debug=args.debug):
        print("Already logged in — session is valid.")
        return

    print("Steam Login")
    print("-" * 40)
    username = input("Steam username: ").strip()
    password = getpass.getpass("Password: ")

    try:
        cookie = login(username, password, debug=args.debug)
        save_session(cookie)
        print("Login successful — session saved to keychain.")
    except RuntimeError as error:
        print(f"Error: {error}")
        raise SystemExit(1) from error
