"""One pass over every account. Read-only: it never writes to any account."""
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import storage
from .google import GoogleContacts, GoogleError, revoke
from .icloud import ICloudAddressBook, ICloudError, is_group
from .settings import PRIVATE_DIR, SHARED_DIR

log = logging.getLogger(__name__)

STATUS_FILE = PRIVATE_DIR / "status.json"
GOOGLE_ACCOUNTS_FILE = PRIVATE_DIR / "google_accounts.json"
SNAPSHOT_DIR = SHARED_DIR / "snapshots"

_check_lock = threading.Lock()  # one check at a time
# Guards the Google account list, the snapshots and status.json. It's only held for quick file
# work, so connecting or disconnecting never waits for a check, and a check can still tell that
# an account was disconnected while it was being read.
_state_lock = threading.Lock()


def load_status() -> dict | None:
    return storage.read_json(STATUS_FILE, None)


def google_accounts() -> list[dict]:
    return storage.read_json(GOOGLE_ACCOUNTS_FILE, [])


def save_google_account(account: dict) -> None:
    with _state_lock:
        others = [a for a in google_accounts() if a["email"] != account["email"]]
        storage.write_json(GOOGLE_ACCOUNTS_FILE, others + [account])


def remove_google_account(email: str) -> None:
    """Forget the account, delete what was saved from it, and cancel its sign-in at Google."""
    with _state_lock:
        accounts = google_accounts()
        storage.write_json(GOOGLE_ACCOUNTS_FILE, [a for a in accounts if a["email"] != email])
        _snapshot_path(f"google-{email}").unlink(missing_ok=True)
        status = load_status()
        if status:
            status["accounts"] = [r for r in status["accounts"] if not _is_google(r, email)]
            storage.write_json(STATUS_FILE, status)
    for account in accounts:
        if account["email"] == email:
            revoke(account["refresh_token"])


def run_check(options: dict) -> None:
    """Read every account, save a snapshot of each, and record counts and errors."""
    with _check_lock:
        saved: set[Path] = set()
        results = [_check_icloud(a, saved) for a in options["icloud_accounts"]]
        results += [_check_google(a, options, saved) for a in google_accounts()]
        with _state_lock:
            connected = {a["email"] for a in google_accounts()}
            results = [r for r in results if r["service"] != "Google" or r["login"] in connected]
            storage.write_json(STATUS_FILE, {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "accounts": results,
            })
            _remove_other_snapshots(saved)


def _result(service: str, name: str, login: str) -> dict:
    return {"service": service, "name": name, "login": login, "contacts": None, "groups": None, "error": None}


def _check_icloud(account: dict, saved: set[Path]) -> dict:
    row = _result("iCloud", account["label"] or "iCloud", account["apple_id"])
    if not account["apple_id"] or not account["app_password"]:
        row["error"] = "Apple ID or app-specific password missing. Add them on the add-on's Configuration tab."
    else:
        try:
            with ICloudAddressBook(account["apple_id"], account["app_password"]) as book:
                items = book.fetch_all()
            row["groups"] = sum(1 for item in items if is_group(item["vcard"]))
            row["contacts"] = len(items) - row["groups"]
            saved.add(_save_snapshot(f"icloud-{account['apple_id']}", items))
        except Exception as err:  # one account failing must not cost the others their results
            row["error"] = _describe(err, "iCloud")
    _log(row)
    return row


def _check_google(account: dict, options: dict, saved: set[Path]) -> dict:
    row = _result("Google", account["email"], account["email"])
    try:
        with GoogleContacts(
            account["refresh_token"], options["google_client_id"], options["google_client_secret"]
        ) as api:
            people = api.fetch_contacts()
            groups = [g for g in api.fetch_groups() if g.get("groupType") == "USER_CONTACT_GROUP"]
        row["contacts"], row["groups"] = len(people), len(groups)
        with _state_lock:  # an account disconnected while it was being read isn't saved again
            if any(a["email"] == account["email"] for a in google_accounts()):
                saved.add(_save_snapshot(f"google-{account['email']}", {"people": people, "groups": groups}))
    except Exception as err:  # one account failing must not cost the others their results
        row["error"] = _describe(err, "Google")
    _log(row)
    return row


def _describe(err: Exception, service: str) -> str:
    if isinstance(err, (ICloudError, GoogleError)):
        return str(err)
    if isinstance(err, requests.RequestException):
        return f"Couldn't reach {service}: {err}"
    log.exception("Unexpected error while reading %s", service)
    return f"Unexpected error ({type(err).__name__}: {err}). Details are in the add-on's log."


def _is_google(row: dict, email: str) -> bool:
    return row["service"] == "Google" and row["login"] == email


def _snapshot_path(name: str) -> Path:
    return SNAPSHOT_DIR / (re.sub(r"[^\w@.-]", "_", name) + ".json")


def _save_snapshot(name: str, data) -> Path:
    path = _snapshot_path(name)
    storage.write_json(path, data)
    return path


def _remove_other_snapshots(keep: set[Path]) -> None:
    # Only this check's snapshots stay. One left from a removed account, or from an account
    # whose check just failed, would look current when it isn't.
    if SNAPSHOT_DIR.is_dir():
        for path in SNAPSHOT_DIR.iterdir():
            if path.is_file() and path not in keep:
                path.unlink(missing_ok=True)


def _log(row: dict) -> None:
    if row["error"]:
        log.warning("%s %s: %s", row["service"], row["name"], row["error"])
    else:
        log.info("%s %s: %d contacts, %d groups", row["service"], row["name"], row["contacts"], row["groups"])
