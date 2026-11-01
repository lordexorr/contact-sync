"""Google sign-in, and read access to Google Contacts through the People API."""
import base64
import hashlib
import json
import logging
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlparse

import requests

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
PEOPLE_API = "https://people.googleapis.com/v1"
CONTACTS_SCOPE = "https://www.googleapis.com/auth/contacts"
SCOPES = f"openid email {CONTACTS_SCOPE}"
# Nothing listens at this address. After sign-in the browser lands on an error
# page here, and the user pastes the address, which carries the code, back in.
REDIRECT_URI = "http://127.0.0.1:8765/"
# Refresh errors that only a new sign-in, or a corrected client ID and secret, can fix.
RECONNECT_ERRORS = ("invalid_grant", "invalid_client", "unauthorized_client", "deleted_client")
PERSON_FIELDS = ",".join([
    "addresses", "biographies", "birthdays", "emailAddresses", "events",
    "imClients", "memberships", "metadata", "names", "nicknames",
    "organizations", "phoneNumbers", "photos", "relations", "urls", "userDefined",
])


class GoogleError(Exception):
    pass


def start_sign_in(client_id: str) -> dict:
    """A new sign-in attempt: the URL to open, plus what finish_sign_in needs to complete it."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent select_account",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return {"url": url, "state": state, "verifier": verifier}


def finish_sign_in(pasted_url: str, attempt: dict, client_id: str, client_secret: str) -> dict:
    """Trade the code in the pasted address for a long-lived refresh token."""
    query = parse_qs(urlparse(pasted_url.strip()).query)
    if "error" in query:
        raise GoogleError(f"Google sign-in didn't finish ({query['error'][0]}). Press Cancel, then start again.")
    if query.get("state", [""])[0] != attempt["state"]:
        raise GoogleError("That address is from a different sign-in attempt. Paste the address from this one, "
                          "or press Cancel and start again.")
    code = query.get("code", [""])[0]
    if not code:
        raise GoogleError("No sign-in code in that address. Copy the whole address from the address bar.")
    resp = requests.post(TOKEN_URL, timeout=30, data={
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": attempt["verifier"],
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
    })
    if resp.status_code != 200:
        if "invalid_grant" in resp.text:
            raise GoogleError("That sign-in code has expired or was already used. Press Cancel, then start again.")
        raise GoogleError(f"Google refused the sign-in: {_error_text(resp)}")
    tokens = resp.json()
    # With granular consent the contacts box can be left unticked and Google still issues a token.
    if CONTACTS_SCOPE not in tokens.get("scope", "").split():
        raise GoogleError("Contact Sync wasn't given access to contacts. Press Cancel, start again, "
                          "and tick the box for access to your contacts.")
    if "refresh_token" not in tokens:
        raise GoogleError("Google didn't return a refresh token. Press Cancel, then start again.")
    return {"email": _email_from_id_token(tokens["id_token"]), "refresh_token": tokens["refresh_token"]}


def revoke(refresh_token: str) -> None:
    """Cancel a sign-in at Google. Best effort: the account is forgotten here either way."""
    try:
        resp = requests.post(REVOKE_URL, data={"token": refresh_token}, timeout=30)
    except requests.RequestException as err:
        log.warning("Couldn't reach Google to revoke a sign-in: %s", err)
        return
    if resp.status_code != 200:
        log.warning("Google didn't revoke a sign-in: %s", _error_text(resp))


class GoogleContacts:
    """One Google account's contacts. Use it in a with block so its connection is closed."""

    def __init__(self, refresh_token: str, client_id: str, client_secret: str):
        self.session = requests.Session()
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = ""
        self._expires_at = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.session.close()

    def fetch_contacts(self) -> list[dict]:
        return self._list("people/me/connections", "connections",
                          {"personFields": PERSON_FIELDS, "pageSize": 1000})

    def fetch_groups(self) -> list[dict]:
        return self._list("contactGroups", "contactGroups",
                          {"groupFields": "name,groupType,memberCount", "pageSize": 1000})

    def _list(self, path: str, key: str, params: dict) -> list[dict]:
        items, page_token = [], None
        while True:
            page = self._get(path, {**params, "pageToken": page_token} if page_token else params)
            items += page.get(key, [])
            page_token = page.get("nextPageToken")
            if not page_token:
                return items

    def _get(self, path: str, params: dict) -> dict:
        resp = self.session.get(f"{PEOPLE_API}/{path}", params=params, timeout=60,
                                headers={"Authorization": f"Bearer {self._token()}"})
        if resp.status_code != 200:
            raise GoogleError(f"Google answered {path} with HTTP {resp.status_code}: {_error_text(resp)}")
        return resp.json()

    def _token(self) -> str:
        if time.time() >= self._expires_at - 60:
            resp = self.session.post(TOKEN_URL, timeout=30, data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            })
            if resp.status_code != 200:
                if any(code in resp.text for code in RECONNECT_ERRORS):
                    raise GoogleError(
                        f"Google no longer accepts this sign-in ({_error_text(resp)}). It expired or was revoked, "
                        "or the Google client ID or secret changed. Check those on the Configuration tab, "
                        "then disconnect the account and connect it again."
                    )
                raise GoogleError(f"Google refused to refresh the sign-in: {_error_text(resp)}")
            data = resp.json()
            self._access_token = data["access_token"]
            self._expires_at = time.time() + data.get("expires_in", 3600)
        return self._access_token


def _email_from_id_token(id_token: str) -> str:
    # Comes straight from Google's token endpoint over TLS, so the payload is
    # read without checking the signature.
    payload = id_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["email"]


def _error_text(resp: requests.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}"
    if not isinstance(body, dict):
        return f"HTTP {resp.status_code}"
    error = body.get("error")
    if isinstance(error, dict):  # People API errors
        return error.get("message") or f"HTTP {resp.status_code}"
    return body.get("error_description") or error or f"HTTP {resp.status_code}"  # OAuth errors
