import base64
import getpass
import time

import keyring
import rsa

from .steam_http import community_get, community_post

_KEYRING_SERVICE = "achievements-hunter"
_KEYRING_USERNAME = "steamLoginSecure"


def load_session() -> str | None:
    return keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)


def save_session(cookie: str) -> None:
    keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, cookie)


def validate_session(cookie: str) -> bool:
    """Returns True if the session cookie still grants access to steamcommunity.com."""
    response = community_get("my/", cookies={"steamLoginSecure": cookie})
    return response is not None and "login" not in response.url


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


def do_login(
    username: str,
    encrypted_password: str,
    rsa_timestamp: str,
    guard_code: str = "",
    email_code: str = "",
) -> dict:
    """POSTs credentials to Steam's login endpoint and returns the parsed response."""
    response = community_post(
        "login/dologin/",
        data={
            "username": username,
            "password": encrypted_password,
            "rsatimestamp": rsa_timestamp,
            "donotcache": str(int(time.time() * 1000)),
            "twofactorcode": guard_code,
            "emailauth": email_code,
            "remember_login": "true",
        },
    )
    response.raise_for_status()
    return response.json()


def login(username: str, password: str) -> str:
    """Full login flow. Returns the steamLoginSecure cookie value ({steamid}||{token})."""
    rsa_data = get_rsa_key(username)
    encrypted = encrypt_password(
        password, rsa_data["publickey_mod"], rsa_data["publickey_exp"]
    )
    result = do_login(username, encrypted, rsa_data["timestamp"])

    if result.get("requires_twofactor"):
        guard_code = input("Steam Guard code (authenticator app): ").strip()
        result = do_login(
            username, encrypted, rsa_data["timestamp"], guard_code=guard_code
        )
    elif result.get("emailauth_needed"):
        domain = result.get("emaildomain", "your email")
        email_code = input(f"Steam Guard code (sent to {domain}): ").strip()
        result = do_login(
            username, encrypted, rsa_data["timestamp"], email_code=email_code
        )

    if not result.get("login_complete"):
        raise RuntimeError(result.get("message", "Login failed."))

    params = result.get("transfer_parameters", {})
    steam_id = params.get("steamid", "")
    token = params.get("token_secure", "")
    return f"{steam_id}||{token}"


def main() -> None:
    existing = load_session()
    if existing and validate_session(existing):
        print("Already logged in — session is valid.")
        return

    print("Steam Login")
    print("-" * 40)
    username = input("Steam username: ").strip()
    password = getpass.getpass("Password: ")

    try:
        cookie = login(username, password)
        save_session(cookie)
        print("Login successful — session saved to keychain.")
    except RuntimeError as error:
        print(f"Error: {error}")
        raise SystemExit(1) from error
