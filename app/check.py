"""Reading the accounts: every contact in one pass, or a few contacts for applying one person's changes.
Read-only: it never writes to any account."""
import logging
import re
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import base, people, photos, storage, vcard
from .google import GoogleContacts, GoogleError, revoke
from .icloud import ICloudAddressBook, ICloudError
from .settings import PRIVATE_DIR, SHARED_DIR

log = logging.getLogger(__name__)

STATUS_FILE = PRIVATE_DIR / "status.json"
RECORDS_FILE = PRIVATE_DIR / "records.json"
GOOGLE_ACCOUNTS_FILE = PRIVATE_DIR / "google_accounts.json"
ICLOUD_ACCOUNTS_FILE = PRIVATE_DIR / "icloud_accounts.json"
GOOGLE_APP_FILE = PRIVATE_DIR / "google_app.json"
SNAPSHOT_DIR = SHARED_DIR / "snapshots"

check_lock = threading.Lock()  # one check, or one apply, at a time
# Guards the account lists, the snapshots, status.json and records.json. It's only held for quick file work,
# so adding or removing an account never waits for a check, and a check can still tell that an account was
# removed while it was being read.
_state_lock = threading.Lock()


def load_status() -> dict | None:
    return storage.read_json(STATUS_FILE, None)


def load_records() -> dict | None:
    """Every contact from the latest check, in the add-on's own form, plus each account's groups."""
    return storage.read_json(RECORDS_FILE, None)


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
        _forget("google", email)
    for account in accounts:
        if account["email"] == email:
            revoke(account["refresh_token"])


def google_app() -> dict:
    """The app registered in Google Cloud that every Google account signs in through:
    {"client_id", "client_secret"}, both "" until it's set up."""
    return {"client_id": "", "client_secret": "", **storage.read_json(GOOGLE_APP_FILE, {})}


def save_google_app(client_id: str, client_secret: str) -> None:
    with _state_lock:
        storage.write_json(GOOGLE_APP_FILE, {"client_id": client_id, "client_secret": client_secret})


def _google(refresh_token: str) -> GoogleContacts:
    app = google_app()
    return GoogleContacts(refresh_token, app["client_id"], app["client_secret"])


def icloud_accounts() -> list[dict]:
    """Each iCloud account as {"label", "apple_id", "app_password"}."""
    return storage.read_json(ICLOUD_ACCOUNTS_FILE, [])


def test_icloud_account(account: dict) -> None:
    """Sign in and find the address book; raises ICloudError (or a connection error) if that fails."""
    with ICloudAddressBook(account["apple_id"], account["app_password"]) as book:
        book.fetch([])


def save_icloud_account(account: dict) -> None:
    """Add the account, or update the label and password of the one with the same Apple ID. That one keeps
    its Apple ID as first typed, which is what everything saved from it is filed under."""
    with _state_lock:
        accounts = icloud_accounts()
        at = next((i for i, a in enumerate(accounts) if a["apple_id"].lower() == account["apple_id"].lower()), None)
        if at is None:
            accounts.append(account)
        else:
            accounts[at] = {**account, "apple_id": accounts[at]["apple_id"]}
        storage.write_json(ICLOUD_ACCOUNTS_FILE, accounts)


def remove_icloud_account(apple_id: str) -> None:
    """Forget the account and delete what was saved from it."""
    with _state_lock:
        storage.write_json(ICLOUD_ACCOUNTS_FILE, [a for a in icloud_accounts() if a["apple_id"] != apple_id])
        _forget("icloud", apple_id)


def _forget(service: str, login: str) -> None:
    """Delete everything saved from an account that's been removed. The caller holds _state_lock."""
    key = f"{service}:{login}"
    _snapshot_path(f"{service}-{login}").unlink(missing_ok=True)
    status = load_status()
    if status:
        status["accounts"] = [r for r in status["accounts"] if f"{r['service'].lower()}:{r['login']}" != key]
        storage.write_json(STATUS_FILE, status)
    records = load_records()
    if records:
        records["accounts"] = [a for a in records["accounts"] if a["key"] != key]
        records["contacts"] = [c for c in records["contacts"] if c["account"] != key]
        storage.write_json(RECORDS_FILE, records)
    base.forget(key)


def _connected() -> set[str]:
    return ({f"icloud:{a['apple_id']}" for a in icloud_accounts()}
            | {f"google:{a['email']}" for a in google_accounts()})


class _Run:
    """What one check collects from the accounts it reads successfully."""

    def __init__(self):
        self.saved: set[Path] = set()
        self.accounts: list[dict] = []
        self.contacts: list[dict] = []
        self.fingerprints = photos.Fingerprints()
        # Each account's data as read, for applying changes. iCloud: {"book", "items", "photos": {href: ref}};
        # Google: {"people", "groups", "photos": {resourceName: url}}.
        self.raw: dict[str, dict] = {}


def run_check(options: dict) -> None:
    with check_lock:
        read_accounts(options)


def read_accounts(options: dict) -> _Run:
    """Read every account, save a snapshot and the contacts of each, and record counts and errors.
    The caller holds check_lock."""
    run = _Run()
    results = [_check_icloud(a, run) for a in icloud_accounts()]
    results += [_check_google(a, options, run) for a in google_accounts()]
    with _state_lock:
        connected = _connected()

        def kept(key: str) -> bool:  # an account removed while it was being read stays out
            return key in connected

        checked_at = datetime.now(timezone.utc).isoformat()
        results = [r for r in results if kept(f"{r['service'].lower()}:{r['login']}")]
        storage.write_json(STATUS_FILE, {"checked_at": checked_at, "accounts": results})
        storage.write_json(RECORDS_FILE, {
            "checked_at": checked_at,
            "accounts": [a for a in run.accounts if kept(a["key"])],
            "contacts": [c for c in run.contacts if kept(c["account"])],
        })
        _remove_other_snapshots(run.saved)
        run.raw = {key: data for key, data in run.raw.items() if kept(key)}
    run.fingerprints.save()
    return run


class ReadError(Exception):
    """An account that couldn't be read for an apply. The message names it and says why."""


def read_some(options: dict, refs: list[str], new_groups: dict[str, list[str]] | None = None) -> _Run:
    """Fresh copies of a few contacts, plus every account's groups, without reading every contact. raw holds
    just those contacts and the groups (iCloud group cards are found in the latest snapshot, plus any in
    new_groups). Contacts that no longer exist are left out. Raises ReadError if an account can't be read.
    The caller holds check_lock."""
    wanted = defaultdict(list)
    for ref in refs:
        account, _, cid = ref.partition("|")
        wanted[account].append(cid)
    run = _Run()
    for a in icloud_accounts():
        try:
            _read_some_icloud(a, wanted[f"icloud:{a['apple_id']}"], new_groups or {}, run)
        except Exception as err:
            raise ReadError(f"Couldn't read iCloud {a['label'] or a['apple_id']}: {_describe(err, 'iCloud')}") from err
    for a in google_accounts():
        try:
            _read_some_google(a, wanted[f"google:{a['email']}"], options, run)
        except Exception as err:
            raise ReadError(f"Couldn't read Google {a['email']}: {_describe(err, 'Google')}") from err
    return run


def _read_some_icloud(account: dict, hrefs: list[str], new_groups: dict, run: _Run) -> None:
    key = f"icloud:{account['apple_id']}"
    snapshot = storage.read_json(_snapshot_path(f"icloud-{account['apple_id']}"), [])
    hrefs = list(dict.fromkeys(hrefs + [i["href"] for i in vcard.groups(snapshot).values()] + new_groups.get(key, [])))
    with ICloudAddressBook(account["apple_id"], account["app_password"]) as book:
        items = book.fetch(hrefs)
        contacts, groups, photo_refs = vcard.read(key, items)
        for c in contacts:
            if c.id in photo_refs:
                c.photo = run.fingerprints.get(photo_refs[c.id], book.fetch_photo)
    run.accounts.append({"key": key, "name": account["label"] or "iCloud", "groups": groups})
    run.contacts += [c.to_dict() for c in contacts]
    run.raw[key] = {"book": book.book, "items": items, "photos": photo_refs}


def _read_some_google(account: dict, resources: list[str], options: dict, run: _Run) -> None:
    key = f"google:{account['email']}"
    with _google(account["refresh_token"]) as api:
        persons = [p for p in (api.fetch_contact(rn) for rn in resources) if p]
        groups = [g for g in api.fetch_groups() if g.get("groupType") == "USER_CONTACT_GROUP"]
        group_names = {g["resourceName"]: g["name"] for g in groups}
        photo_urls = {}
        for person in persons:
            c, photo_url = people.read(key, person, group_names)
            if photo_url:
                c.photo = run.fingerprints.get(("url", photo_url), api.fetch_photo)
                photo_urls[c.id] = photo_url
            run.contacts.append(c.to_dict())
    run.accounts.append({"key": key, "name": account["email"], "groups": list(group_names.values())})
    run.raw[key] = {"people": persons, "groups": groups, "photos": photo_urls}


def merge_records(run: _Run, replaced: set[str]) -> None:
    """Put a partial read into the saved records and snapshots: each contact in replaced is swapped for its
    fresh copy, or dropped if it's gone, and each account's groups are brought up to date."""
    with _state_lock:
        records = load_records()
        if not records:
            return
        records["contacts"] = [c for c in records["contacts"] if f"{c['account']}|{c['id']}" not in replaced]
        records["contacts"] += run.contacts
        groups = {a["key"]: a["groups"] for a in run.accounts}
        for account in records["accounts"]:
            account["groups"] = groups.get(account["key"], account["groups"])
        storage.write_json(RECORDS_FILE, records)
        # The counts on the Contact Sync page follow along.
        status = load_status()
        if status:
            counts = Counter(c["account"] for c in records["contacts"])
            for row in status["accounts"]:
                key = f"{row['service'].lower()}:{row['login']}"
                if key in groups and not row["error"]:
                    row["contacts"], row["groups"] = counts[key], len(groups[key])
            storage.write_json(STATUS_FILE, status)
        for key, data in run.raw.items():
            service, _, login = key.partition(":")
            path = _snapshot_path(f"{service}-{login}")
            gone = {ref.partition("|")[2] for ref in replaced if ref.startswith(key + "|")}
            if service == "icloud":
                _merge_items(path, data["items"], gone, "href", None)
            else:
                _merge_items(path, data["people"], gone, "resourceName", data["groups"])


def _merge_items(path: Path, fresh: list[dict], gone: set[str], id_key: str, groups: list | None) -> None:
    snapshot = storage.read_json(path, None)
    if snapshot is None:
        return
    items = snapshot if groups is None else snapshot["people"]
    by_id = {i[id_key]: i for i in fresh}
    items = [by_id.pop(i[id_key], i) for i in items if i[id_key] not in gone or i[id_key] in by_id]
    items += list(by_id.values())
    storage.write_json(path, items if groups is None else {"people": items, "groups": groups})


def _result(service: str, name: str, login: str) -> dict:
    return {"service": service, "name": name, "login": login, "contacts": None, "groups": None, "error": None}


def _check_icloud(account: dict, run: _Run) -> dict:
    row = _result("iCloud", account["label"] or "iCloud", account["apple_id"])
    key = f"icloud:{account['apple_id']}"
    if not account["apple_id"] or not account["app_password"]:
        row["error"] = "Apple ID or app-specific password missing. Add them on the add-on's Configuration tab."
    else:
        try:
            with ICloudAddressBook(account["apple_id"], account["app_password"]) as book:
                items = book.fetch_all()
                contacts, groups, photo_refs = vcard.read(key, items)
                for c in contacts:
                    if c.id in photo_refs:
                        c.photo = run.fingerprints.get(photo_refs[c.id], book.fetch_photo)
            row["contacts"], row["groups"] = len(contacts), len(groups)
            with _state_lock:  # an account removed while it was being read isn't saved again
                if key in _connected():
                    run.saved.add(_save_snapshot(f"icloud-{account['apple_id']}", items))
            run.accounts.append({"key": key, "name": row["name"], "groups": groups})
            run.contacts += [c.to_dict() for c in contacts]
            run.raw[key] = {"book": book.book, "items": items, "photos": photo_refs}
        except Exception as err:  # one account failing must not cost the others their results
            row["error"] = _describe(err, "iCloud")
    _log(row)
    return row


def _check_google(account: dict, options: dict, run: _Run) -> dict:
    row = _result("Google", account["email"], account["email"])
    key = f"google:{account['email']}"
    try:
        with _google(account["refresh_token"]) as api:
            persons = api.fetch_contacts()
            groups = [g for g in api.fetch_groups() if g.get("groupType") == "USER_CONTACT_GROUP"]
            group_names = {g["resourceName"]: g["name"] for g in groups}
            contacts, photo_urls = [], {}
            for person in persons:
                c, photo_url = people.read(key, person, group_names)
                if photo_url:
                    c.photo = run.fingerprints.get(("url", photo_url), api.fetch_photo)
                    photo_urls[c.id] = photo_url
                contacts.append(c)
        row["contacts"], row["groups"] = len(contacts), len(groups)
        with _state_lock:  # an account disconnected while it was being read isn't saved again
            if any(a["email"] == account["email"] for a in google_accounts()):
                run.saved.add(_save_snapshot(f"google-{account['email']}", {"people": persons, "groups": groups}))
        run.accounts.append({"key": key, "name": account["email"], "groups": list(group_names.values())})
        run.contacts += [c.to_dict() for c in contacts]
        run.raw[key] = {"people": persons, "groups": groups, "photos": photo_urls}
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
