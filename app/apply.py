"""Applying the reviewed changes: check every account again, back them all up, make the changes, then check
again and record what every account holds."""
import io
import logging
import re
import shutil
import uuid
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from PIL import Image

from . import base, check, people, plan, review, storage, vcard
from .google import GoogleContacts, GoogleError, full_size
from .icloud import ICloudAddressBook, ICloudError
from .model import fold
from .settings import PRIVATE_DIR, SHARED_DIR

log = logging.getLogger(__name__)

RESULT_FILE = PRIVATE_DIR / "last_apply.json"
BACKUP_DIR = SHARED_DIR / "backups"
KEEP_BACKUPS = 10
STOPPED = ("Something changed since the Apply page opened, in an account or in the review, so nothing was "
           "written. Open the review to see what's waiting now.")


class Progress:
    """How far a running apply has got, for its page."""

    def __init__(self):
        self.step = "Starting"
        self.done = 0
        self.total = 0


def load_result() -> dict | None:
    return storage.read_json(RESULT_FILE, None)


def summary(result: dict) -> str:
    """The outcome of an apply in a few words."""
    if result["status"] == "stopped":
        return "stopped before writing anything"
    failed = sum(bool(c["error"]) for c in result["changes"])
    made = len(result["changes"]) - failed
    if result["status"] == "failed" and not result["changes"]:
        return "failed before writing anything"
    return f"{made:,} change{'' if made == 1 else 's'} made" + (f", {failed:,} failed" if failed else "")


def run(options: dict, person: str | None, token: str, tz, progress: Progress) -> None:
    """Apply everyone's changes, or one person's, if they're still what the Apply page showed (token)."""
    result = {"started_at": _now(), "finished_at": "", "person": "", "status": "failed", "message": "",
              "backup": "", "changes": []}
    try:
        with check.check_lock:
            _apply(options, person, token, tz, progress, result)
    except Exception as err:
        log.exception("Apply failed")
        result["status"] = "failed"
        result["message"] = (f"Apply stopped with an unexpected error ({type(err).__name__}: {err}). Any changes "
                             "listed below were made before it stopped. Details are in the add-on's log.")
    finally:
        result["finished_at"] = _now()
        storage.write_json(RESULT_FILE, result)


def _apply(options: dict, person: str | None, token: str, tz, progress: Progress, result: dict) -> None:
    progress.step = "Checking every account again"
    raw = check.read_accounts(options).raw
    before = review.current_plan(options)
    if before is None:
        result["status"], result["message"] = "stopped", STOPPED
        return
    if person:
        result["person"] = before["sync"]["people"].get(person, {}).get("name", "")
    work = plan.scope(before, person)
    if plan.digest(work) != token:
        result["status"], result["message"] = "stopped", STOPPED
        return
    if plan.is_empty(work):
        result["status"], result["message"] = "done", "Nothing to apply."
        return
    progress.total = (sum(len(p["delete"]) + len(p["update"]) + len((p["create"] or {}).get("accounts", []))
                          + len(p["drop"]) for p in work["people"].values()) + len(work["groups"]))
    with ExitStack() as stack:
        accounts = _Accounts(options, raw, stack)
        progress.step = "Backing up every account"
        result["backup"] = _backup(raw, work, accounts, tz)
        progress.step = "Making the changes"
        writer = _Writer(accounts, work, progress, result)
        writer.run()

    progress.step = "Checking the result"
    check.read_accounts(options)
    loaded = review.current_records(options)
    if loaded:
        contacts, accounts_now = loaded
        people_before = before["sync"]["people"]
        # A new copy is the person it was made from, even with too little on it to match by, such as a first
        # name and a short number. Recording them together keeps them matched from now on.
        decided = review.decisions()
        decided["same"] = sorted(set(decided.get("same", [])) | {
            "||".join(sorted((people_before[k]["refs"][0], ref))) for (k, _), ref in writer.created.items()})
        after = plan.build(contacts, accounts_now, decided, base.load())
        keys = [person] if person else [k for k, p in people_before.items() if not p["held"]]
        covered = {r for k in keys if k in people_before and k not in writer.failed for r in people_before[k]["refs"]}
        covered |= {ref for (k, _), ref in writer.created.items() if k not in writer.failed}
        base.record(contacts, after["clusters"], covered, accounts_now, person is None, writer.failed_groups)
    failed = sum(bool(c["error"]) for c in result["changes"])
    result["status"] = "done"
    result["message"] = (f"{failed:,} change{' was' if failed == 1 else 's were'} not made. Those people stay in "
                         "the review, so you can try again." if failed else "")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Connections ---

class _Accounts:
    """A connection to each account read in the check, opened when first needed, and the photos read through
    them."""

    def __init__(self, options: dict, raw: dict, stack: ExitStack):
        self.options, self.raw, self.stack = options, raw, stack
        self._open: dict[str, object] = {}
        self._photos: dict[str, tuple[bytes, str]] = {}

    def get(self, key: str):
        if key not in self._open:
            service, _, login = key.partition(":")
            if service == "icloud":
                a = next(a for a in self.options["icloud_accounts"] if a["apple_id"] == login)
                conn = ICloudAddressBook(a["apple_id"], a["app_password"], self.raw[key]["book"])
            else:
                a = next(a for a in check.google_accounts() if a["email"] == login)
                conn = GoogleContacts(a["refresh_token"], self.options["google_client_id"],
                                      self.options["google_client_secret"])
            self._open[key] = self.stack.enter_context(conn)
        return self._open[key]

    def has_photo(self, ref: str) -> bool:
        key, _, cid = ref.partition("|")
        return cid in self.raw.get(key, {}).get("photos", {})

    def photo(self, ref: str) -> tuple[bytes, str]:
        """A contact's photo at full size, as (data, "JPEG" or "PNG")."""
        if ref not in self._photos:
            key, _, cid = ref.partition("|")
            source = self.raw[key]["photos"][cid]
            if key.startswith("icloud:"):
                kind, value = source
                data = value if kind == "data" else self.get(key).fetch_photo(value)
            else:
                data = self.get(key).fetch_photo(full_size(source))
            self._photos[ref] = _image(data)
        return self._photos[ref]


def _image(data: bytes) -> tuple[bytes, str]:
    """A photo as JPEG or PNG, which both iCloud and Google take; anything else is converted to JPEG."""
    with Image.open(io.BytesIO(data)) as img:
        if img.format in ("JPEG", "PNG"):
            return data, img.format
        out = io.BytesIO()
        img.convert("RGB").save(out, "JPEG", quality=92)
    return out.getvalue(), "JPEG"


# --- Backup ---

def _backup(raw: dict, work: dict, accounts: _Accounts, tz) -> str:
    """Save every account as the check read it, as .json and as a .vcf file that Contacts apps can import,
    plus the full-size photo of every contact about to be changed or deleted. Keeps the latest backups."""
    folder = BACKUP_DIR / datetime.now(tz).strftime("%Y-%m-%d_%H-%M-%S")
    for key, data in raw.items():
        name = _file_name(key)
        if key.startswith("icloud:"):
            storage.write_json(folder / f"{name}.json", data["items"])
            cards = [item["vcard"] for item in data["items"]]
        else:
            storage.write_json(folder / f"{name}.json", {"people": data["people"], "groups": data["groups"]})
            group_names = {g["resourceName"]: g["name"] for g in data["groups"]}
            cards = [vcard.new(str(uuid.uuid4()).upper(), plan.contact_changes(people.read(key, p, group_names)[0]))
                     for p in data["people"]]
        (folder / f"{name}.vcf").write_bytes("".join(c.rstrip("\r\n") + "\r\n" for c in cards).encode())
    touched = {e["ref"] for p in work["people"].values() for e in p["update"].values()}
    touched |= {ref for p in work["people"].values() for ref in p["delete"] + p["drop"]}
    for ref in sorted(touched):
        if accounts.has_photo(ref):
            try:
                data, kind = accounts.photo(ref)
            except Exception as err:  # a missing photo copy mustn't stop the backup
                log.warning("Couldn't back up a contact photo: %s", err)
                continue
            key, _, cid = ref.partition("|")
            path = folder / "photos" / _file_name(key) / f"{_file_name(cid.rsplit('/', 1)[-1])}.{kind.lower()}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    backups = sorted(p for p in BACKUP_DIR.iterdir() if p.is_dir())
    for old in backups[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)
    return folder.name


def _file_name(name: str) -> str:
    return re.sub(r"[^\w@.-]", "_", name.replace(":", "-"))


# --- Writing ---

class _NotMade(Exception):
    pass


class _Writer:
    """Makes the changes in work, one person at a time and then the group changes, noting how each went."""

    def __init__(self, accounts: _Accounts, work: dict, progress: Progress, result: dict):
        self.accounts, self.work, self.progress, self.result = accounts, work, progress, result
        self.names = work["names"]
        self.created: dict[tuple[str, str], str] = {}  # (person, account) -> ref of the copy made there
        self.deleted: set[str] = set()
        self.failed: set[str] = set()  # people with a change that wasn't made
        self.failed_groups: set[str] = set()  # accounts where creating or deleting a group failed
        self.uids: dict[str, str] = {}  # ref -> UID of each iCloud contact made here
        raw = accounts.raw
        self._items = {k: {i["href"]: i for i in d["items"]} for k, d in raw.items() if k.startswith("icloud:")}
        self._groups = {k: vcard.groups(d["items"]) for k, d in raw.items() if k.startswith("icloud:")}
        self._people = {k: {p["resourceName"]: p for p in d["people"]} for k, d in raw.items() if k.startswith("google:")}

    def run(self) -> None:
        for key, p in sorted(self.work["people"].items(), key=lambda item: fold(item[1]["name"])):
            for ref in p["delete"]:
                self._do(key, ref.partition("|")[0], p["name"], "Deleted", self._delete, ref)
            updated = {account: self._do(key, account, p["name"], describe(edit), self._update, account, edit)
                       for account, edit in p["update"].items()}
            for account in (p["create"] or {}).get("accounts", []):
                self._do(key, account, p["name"], "Added", self._create, key, account, p["create"]["contact"])
            for ref in p["drop"]:  # an extra copy goes only once everything on it is on the copy kept
                account = ref.partition("|")[0]
                self._do(key, account, p["name"], "Duplicate card deleted", self._drop, ref, updated.get(account))
        for op in self.work["groups"]:
            self._group(op)

    def _do(self, person: str | None, account: str, subject: str, what: str, action, *args) -> bool:
        """Make one change and note it. action may return a note on part of the change that wasn't made."""
        error = ""
        try:
            error = action(*args) or ""
        except (ICloudError, GoogleError, _NotMade) as err:
            error = str(err)
        except requests.RequestException as err:
            error = f"Couldn't reach {'iCloud' if account.startswith('icloud:') else 'Google'}: {err}"
        except Exception as err:  # one change failing mustn't stop the rest
            log.exception("Couldn't make a change")
            error = f"Unexpected error ({type(err).__name__}: {err}). Details are in the add-on's log."
        if error and person:
            self.failed.add(person)
        self.result["changes"].append({"account": self.names[account], "subject": subject, "what": what,
                                       "error": error})
        self.progress.done += 1
        return not error

    def _delete(self, ref: str) -> None:
        account, _, cid = ref.partition("|")
        if account.startswith("icloud:"):
            item = self._items[account][cid]
            self.accounts.get(account).delete(item["href"], item["etag"])
        else:
            self.accounts.get(account).delete_contact(cid)
        self.deleted.add(ref)

    def _drop(self, ref: str, kept_updated: bool | None) -> None:
        if not kept_updated:
            raise _NotMade("Left as it is, because moving its details onto the card kept didn't work.")
        self._delete(ref)

    def _update(self, account: str, edit: dict) -> str:
        edit, photo, note = self._photo_for(edit)
        if note and not (edit["set"] or edit["photo"] or edit["add"] or edit["remove"] or edit["relabel"]
                         or edit.get("carry")):
            raise _NotMade(note)
        cid = edit["ref"].partition("|")[2]
        carry = [r.partition("|")[2] for r in edit.get("carry", [])]
        conn = self.accounts.get(account)
        if account.startswith("icloud:"):
            item = self._items[account][cid]
            source = self.accounts.raw[account]["photos"].get(cid)
            # A photo iCloud gives as a link goes back as the picture itself, so the rewrite keeps it.
            current = self.accounts.photo(edit["ref"]) if edit["photo"] is None and source and source[0] == "url" else None
            text = vcard.edit(item["vcard"], edit, photo, current, [self._items[account][c]["vcard"] for c in carry])
            conn.put(item["href"], text, item["etag"])
        else:
            body, fields = people.edit(self._people[account][cid], edit, [self._people[account][c] for c in carry])
            if fields:
                conn.update_contact(cid, body, fields)
            if edit["photo"] == "clear":
                conn.delete_photo(cid)
            elif photo:
                conn.update_photo(cid, photo[0])
        return note

    def _create(self, person: str, account: str, contact: dict) -> str:
        contact, photo, note = self._photo_for(contact)
        conn = self.accounts.get(account)
        if account.startswith("icloud:"):
            uid = str(uuid.uuid4()).upper()
            href = urlparse(self.accounts.raw[account]["book"]).path + uid + ".vcf"
            conn.put(href, vcard.new(uid, contact, photo))
            ref = f"{account}|{href}"
            self.uids[ref] = uid
        else:
            cid = conn.create_contact(people.new(contact))
            ref = f"{account}|{cid}"
            if photo:
                try:
                    conn.update_photo(cid, photo[0])
                except (GoogleError, requests.RequestException) as err:
                    note = f"The photo wasn't copied: {err}"
        self.created[(person, account)] = ref
        return note

    def _photo_for(self, edit: dict) -> tuple[dict, tuple[bytes, str] | None, str]:
        """The photo an edit copies, read from the account that has it. If that fails, the edit goes ahead
        without the photo, and a note says so."""
        if not isinstance(edit["photo"], dict):
            return edit, None, ""
        try:
            return edit, self.accounts.photo(edit["photo"]["from"]), ""
        except Exception as err:
            log.warning("Couldn't read a photo to copy: %s", err)
            return {**edit, "photo": None}, None, f"The photo wasn't copied: {err}"

    def _group(self, op: dict) -> None:
        account = op["account"]
        add = [i for i in (self._member_id(account, m) for m in op["add"]) if i]
        remove = [i for i in (self._member_id(account, m) for m in op["remove"]) if i]
        if op["delete"]:
            what = "Group deleted"
        else:
            parts = ((["Group created"] if op["create"] else []) + ([f"{_people(len(add))} added"] if add else [])
                     + ([f"{_people(len(remove))} taken out"] if remove else []))
            if not parts:  # everyone it was for failed to be added already
                self.progress.done += 1
                return
            what = ", ".join(parts)
        if not self._do(None, account, op["group"], what, self._write_group, op, add, remove):
            self.failed |= {m["person"] for m in op["add"] + op["remove"]}
            if op["create"] or op["delete"]:
                self.failed_groups.add(account)

    def _member_id(self, account: str, member: dict) -> str:
        """How a group names a member: by UID in iCloud, by resourceName in Google. "" when their copy in the
        account wasn't made, or was just deleted."""
        ref = member["ref"] or self.created.get((member["person"], account), "")
        if not ref or ref in self.deleted:
            return ""
        cid = ref.partition("|")[2]
        if account.startswith("google:"):
            return cid
        return self.uids.get(ref) or vcard.uid(self._items[account][cid]["vcard"])

    def _write_group(self, op: dict, add: list[str], remove: list[str]) -> None:
        account = op["account"]
        conn = self.accounts.get(account)
        if account.startswith("icloud:"):
            item = self._groups[account].get(op["fold"])
            if op["delete"]:
                if item:
                    conn.delete(item["href"], item["etag"])
            elif item is None:
                uid = str(uuid.uuid4()).upper()
                conn.put(urlparse(self.accounts.raw[account]["book"]).path + uid + ".vcf",
                         vcard.group_card(uid, op["group"], add))
            else:
                conn.put(item["href"], vcard.edit_members(item["vcard"], add, remove), item["etag"])
            return
        group = next((g["resourceName"] for g in self.accounts.raw[account]["groups"]
                      if fold(g.get("name", "")) == op["fold"]), "")
        if op["delete"]:
            if group:
                conn.delete_group(group)
            return
        if not group:
            group = conn.create_group(op["group"])
        if add or remove:
            conn.modify_members(group, add, remove)


def describe(edit: dict) -> str:
    """A short account of an update, such as "Birthday and photo updated, 2 phones added"."""
    updated = [plan.SINGLE[f].lower() for f, v in edit["set"].items() if v]
    removed = [plan.SINGLE[f].lower() for f, v in edit["set"].items() if not v]
    if edit["photo"] == "clear":
        removed.append("photo")
    elif edit["photo"]:
        updated.append("photo")
    parts = ([f"{_join(updated)} updated"] if updated else []) + ([f"{_join(removed)} removed"] if removed else [])
    for kind, verb in (("add", "added"), ("remove", "removed")):
        parts += [f"{_count(n, plan.MULTI[f])} {verb}" for f, n in Counter(v["field"] for v in edit[kind]).items()]
    if edit["relabel"]:
        parts.append(f"{_count(len(edit['relabel']), 'label')} changed")
    if edit.get("carry"):
        parts.append(f"details of {_count(len(edit['carry']), 'duplicate card')} moved here")
    text = ", ".join(parts) or "updated"
    return text[0].upper() + text[1:]


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _count(n: int, noun: str) -> str:
    return f"{n:,} {noun}" if n == 1 else f"{n:,} {noun}{'es' if noun.endswith('s') else 's'}"


def _people(n: int) -> str:
    return "1 person" if n == 1 else f"{n:,} people"
