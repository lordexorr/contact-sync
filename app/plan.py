"""What a sync would change in each account, worked out from the latest check, the last apply and your
decisions: the review's comparison tables, and the edits applying them makes."""
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime

from . import match, photos
from .model import (Contact, Value, address_key, date_key, email_key, fold, label, label_text, phone_key, url_key,
                    us_phone, without_us_country)

# Fields with one value per contact, and their names on the review page.
SINGLE = {"name": "Name", "nickname": "Nickname", "company": "Company", "title": "Job title",
          "birthday": "Birthday", "note": "Notes"}
# The single fields a sync can empty, when an account deleted the value since the last apply. Never the name.
CLEARABLE = ("nickname", "company", "title", "birthday", "note")
# Fields with any number of values, and what one value is called.
MULTI = {"phones": "phone", "emails": "email", "addresses": "address", "urls": "website", "related": "related name",
         "dates": "date"}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
# Labels offered when fixing a label: only ones iCloud and Google both have. Any label already on the value
# is offered too, so a one-sided label such as iPhone stays available.
LABEL_CHOICES = {
    "phones": ["mobile", "home", "work", "main", "homefax", "workfax", "pager", "other"],
    "emails": ["home", "work", "other"],
    "addresses": ["home", "work", "other"],
    "urls": ["homepage", "home", "work", "other"],
    "related": ["spouse", "partner", "child", "mother", "father", "parent", "brother", "sister", "friend", "assistant",
                "manager"],
    "dates": ["anniversary", "other"],
}
_DELETED = {"text": "Deleted since the last sync", "state": "note"}
# More contacts than this gone from one account since the last apply looks like a glitch or a mistake rather
# than tidying up, so deleting them from the other accounts waits until you tick each one.
MASS_DELETION = 10


def build(contacts: list[Contact], accounts: list[dict], decisions: dict, base: dict | None = None) -> dict:
    """Possible matches, values to choose between, a comparison table per person, and what applying does.

    accounts holds {"key", "name", "groups"} for each account read in the latest check; contacts in any
    other account are ignored, so an account that couldn't be read never looks empty. decisions holds the
    user's "same"/"different" pairs, "picks", "skips" and "keeps": a skipped row leaves every account as it
    is, a skipped list value ("<person>|<field>=<value>") is left out of every account, and a kept one stays
    in every account even when an account deleted it. "pick_seen" and "skip_seen" fingerprint what a pick or
    an unticked row was about, so it stops counting once that changes. "extras" says what happens to each
    detail only Google can hold: "main", "notes" or "delete". "edits", "deletes" and "new_people" hold what was
    entered on the Contacts pages, waiting to be applied (see edit_from and new_person). base is what the
    accounts held after the last apply (see base.py).

    review["sync"] holds the edits: for each person, the copies to delete, create and update, and the group
    changes, one per account and group. Skipped rows make none. review["directory"] and review["views"] are
    what the Contacts pages show.
    """
    names = _column_names(accounts)
    contacts = [c for c in contacts if c.account in names]
    by_ref = {c.ref: c for c in contacts}
    picks, skips, keeps = _Picks(decisions), _Skips(decisions), set(decisions.get("keeps", []))
    duplicates = decisions.get("duplicates", {})  # "<person>|dup:<account>" -> "merge" or "keep"
    last = _Last(base or {}, set(by_ref))
    same, different = set(decisions.get("same", [])), set(decisions.get("different", []))
    clusters, suggestions = match.match(contacts, same | last.links(different), different)
    waiting = {r for pair, _ in suggestions for r in pair.split("||")}  # people a possible match holds back
    have = {a["key"]: {fold(g) for g in a["groups"]} for a in accounts}
    # Groups an account has deleted since the last apply, which other accounts still have.
    dropped = {g for a in names for g in last.account_groups(a) - have[a] if any(g in have[b] for b in names)}
    spelling = {fold(g): g for a in accounts for g in a["groups"]} | {fold(g): g for c in contacts for g in c.groups}
    members = Counter((c.account, g) for c in contacts for g in {fold(x) for x in c.groups})

    gone = Counter(a for refs in clusters for a in last.deleted_from(
        refs, [a for a in names if a not in {by_ref[r].account for r in refs}]))
    mass = {a for a, n in gone.items() if n > MASS_DELETION}
    keyed = _decision_keys(decisions)
    edits, deleting = decisions.get("edits", {}), set(decisions.get("deletes", []))

    review = {"columns": list(names.values()), "suggestions": [], "conflicts": [], "people": [], "groups": [],
              "duplicates": [], "extras": [], "clusters": clusters, "sync": {"names": names, "people": {}, "groups": []},
              "directory": [], "views": {}, "pending": {}, "edit_settled": {},
              "warnings": [f"{gone[a]:,} contacts have gone from {names[a]} since the last sync, more than usual. "
                           "Deleting them from the other accounts waits until you tick each one, so check that "
                           "account first. Applying without ticking them leaves every account as it is, and "
                           "they move to Ignored, where ticking one copies it back." for a in sorted(mass)]}
    for pair, reason in suggestions:
        review["suggestions"].append({
            "id": pair, "reason": reason, "contacts": [_summary(by_ref[r], names) for r in pair.split("||")],
        })
    # Possible matches already answered, while both contacts still exist, so an answer can be changed.
    review["decided_matches"] = [
        {"id": pair, "decision": decision, "contacts": [_summary(by_ref[r], names) for r in pair.split("||")]}
        for decision, pairs in (("same", same), ("different", different)) for pair in sorted(pairs)
        if all(r in by_ref for r in pair.split("||"))
    ]
    to_group, from_group = defaultdict(list), defaultdict(list)  # (account, folded group) -> members to add, remove
    unlisted = defaultdict(list)  # Google account -> people whose card there isn't in My Contacts
    totals = Counter()  # folded group name -> people in it after the sync
    for refs in clusters:
        copies = [by_ref[r] for r in refs]
        # Decisions are filed under a person's key: their first ref when the decision was made. A new copy can
        # sort ahead of it, so a person keeps the key their decisions already use.
        key = next((r for r in refs if r in keyed), refs[0])
        merged, conflicts = _merge(key, copies, picks, names, last, decisions.get("extras", {}), edits.get(key))
        review["conflicts"] += [{**c, "person": merged["display"]} for c in conflicts]
        person = _Person(key, copies, merged, names, skips, keeps, last, picks, key in deleting)
        person.compare(duplicates, mass)
        review["conflicts"] += [{**c, "person": merged["display"]} for c in person.conflicts]
        person.ops["held"] = refs[0] in waiting
        if key in edits or key in deleting:
            review["pending"][key] = "delete" if key in deleting else "edit"
        if key in edits:
            review["edit_settled"][key] = person.settled(edits[key])
        review["views"][key] = {**merged["view"], "baseline": merged["baseline"], "groups": merged["groups"],
                                "photo": merged["photo"], "extras": merged["extras"]["entries"],
                                "display": merged["display"], "held": person.ops["held"], "now": person.held_now(),
                                "in": [names[a] for a in person.first], "missing": [names[a] for a in person.missing]}
        review["directory"].append(_directory_entry(key, review["views"][key], review["pending"].get(key, "")))
        if not person.ops["delete"]:
            person.memberships(have, dropped, to_group, from_group, totals)
            for a, c in person.first.items():
                if not c.listed:
                    unlisted[a].append(person._member(a))
            for a, extras in person.extras.items():
                dup_id = f"{key}|dup:{a}"
                review["duplicates"].append({
                    "id": dup_id, "person": merged["display"], "account": names[a],
                    "choice": duplicates.get(dup_id, ""),
                    "copies": [{**_summary(c, names), "kept": c is person.first[a]} for c in [person.first[a]] + extras],
                })
            if merged["extras"]["entries"]:
                review["extras"].append({"id": key, "person": merged["display"], **merged["extras"]})
        review["sync"]["people"][key] = person.ops
        if person.rows:
            review["people"].append({"key": key, "name": merged["display"], "rows": person.rows,
                                     "held": person.ops["held"]})
    for key, entry in decisions.get("new_people", {}).items():
        _new_person_row(review, key, entry, names, skips)
    review["people"].sort(key=lambda p: fold(p["name"]))
    review["directory"].sort(key=lambda d: fold(d["name"]))
    review["groups"], review["sync"]["groups"] = _group_rows(
        names, have, dropped, spelling, members, to_group, from_group, totals, skips, last)
    rows, ops = _listed_rows(names, unlisted, skips)
    review["groups"] += rows
    review["sync"]["groups"] += ops

    rows = [r for p in review["people"] for r in p["rows"]] + review["groups"]
    review["counts"] = {
        "changes": sum(not r["skipped"] for r in rows),
        "suggestions": len(review["suggestions"]),
        "conflicts": sum(not c["decided"] for c in review["conflicts"]),
        "duplicates": sum(not d["choice"] for d in review["duplicates"]),
        "extras": sum(not e["choice"] for d in review["extras"] for e in d["entries"]),
    }
    return review


def scope(review: dict, person: str | None = None) -> dict:
    """What applying does: everyone's edits, or one person's with the group changes that go with them.
    People waiting on a possible match are left out until it's answered."""
    sync = review["sync"]
    keys = list(sync["people"]) if person is None else [person] if person in sync["people"] else []
    allowed = {k for k in keys if not sync["people"][k]["held"]}
    people = {k: sync["people"][k] for k in sorted(allowed) if _edits(sync["people"][k])}
    groups = []
    for op in sync["groups"]:
        add = [m for m in op["add"] if m["person"] in allowed]
        remove = [m for m in op["remove"] if m["person"] in allowed]
        # A group is created for the people joining it; one whose only joiners are left out waits for them.
        # It's created empty only when it's empty everywhere. One person never deletes a group.
        create = op["create"] and (bool(add) or (person is None and not op["add"]))
        op = {**op, "create": create, "delete": op["delete"] and person is None}
        if op["create"] or op["delete"] or add or remove:
            groups.append({**op, "add": add, "remove": remove})
    return {"names": sync["names"], "people": people, "groups": groups}


def is_empty(work: dict) -> bool:
    return not work["people"] and not work["groups"]


def digest(work: dict) -> str:
    """A fingerprint of what applying does, to tell whether anything changed between two checks."""
    return hashlib.sha256(json.dumps(work, sort_keys=True).encode()).hexdigest()


def held_back(review: dict) -> int:
    """How many people with changes are waiting on a possible match."""
    return sum(p["held"] and _edits(p) for p in review["sync"]["people"].values())


def tidy_text(field: str, value: str) -> str:
    """A single value as every account should hold it."""
    return _compare_key(field, value)


def list_value(field: str, value: str, typed_label: str, parts: list[str] | None = None) -> dict | None:
    """A list value typed on the Contacts pages, as every account should hold it, or None if it's blank. The same
    rules apply as to what's read from the accounts: phone format, no US country."""
    tag = label(typed_label)[0]
    if field == "addresses":
        parts = without_us_country(["\n".join(p.splitlines()).strip() for p in (list(parts or []) + [""] * 5)[:5]])
        if not any(parts):
            return None
        street, city, region, postcode, _ = parts
        return {"value": _address_text(parts), "label": tag, "key": address_key(street, city, postcode, region), "parts": parts}
    value = (value or "").strip()
    if not value:
        return None
    if field == "phones":
        value = us_phone(value)
    keys = {"phones": phone_key, "emails": email_key, "urls": url_key, "related": fold, "dates": date_key}
    return {"value": value, "label": tag, "key": keys[field](value) or fold(value), "parts": []}


def edit_from(baseline: dict, entered: dict) -> dict:
    """A pending edit: what was entered on a contact's form that differs from what the accounts should hold without
    it. "from" is kept, so that if the accounts move on before it's applied, the review can ask."""
    edit = {"set": {}, "lists": {}}
    name = " ".join(filter(None, entered["name_parts"]))
    if name != baseline["name"]:
        edit["set"]["name"] = {"from": baseline["name"], "to": name, "parts": entered["name_parts"]}
    for field in CLEARABLE:
        if entered[field] != baseline[field]:
            edit["set"][field] = {"from": baseline[field], "to": entered[field]}
    for field in MULTI:
        old = [(_exact(field, r["value"], r["parts"]), r["label"].lower()) for r in baseline["lists"][field]]
        new = [(_exact(field, r["value"], r["parts"]), r["label"].lower()) for r in entered["lists"][field]]
        if old != new:
            edit["lists"][field] = {"from": [text for text, _ in old], "to": entered["lists"][field]}
    return edit


def new_person(entered: dict) -> dict:
    """A contact entered on the Contacts pages, to create in every account: {"name", "contact"}."""
    contact = _blank()
    if any(entered["name_parts"]):
        contact["set"]["name"] = entered["name_parts"]
    contact["set"] |= {f: entered[f] for f in CLEARABLE if entered[f]}
    contact["add"] = [{"field": f, **r} for f in MULTI for r in entered["lists"][f]]
    name = " ".join(filter(None, entered["name_parts"])) or entered["company"]
    return {"name": name, "contact": contact}


def similar(review: dict, entered: dict, skip: str = "") -> list[dict]:
    """People who may be the one just entered, leaving out skip: the same name, phone number or email address. A
    contact entered earlier and not yet applied counts, and "unapplied" says so."""
    name = fold(f"{entered['name_parts'][1]} {entered['name_parts'][3]}") or fold(entered["company"])
    phones = {r["key"] for r in entered["lists"]["phones"]}
    emails = {r["key"] for r in entered["lists"]["emails"]}
    found = []
    for d in review["directory"]:
        why = [word for word, same in (("the same name", d["name_key"] == name),
                                       ("the same phone number", phones & set(d["phone_keys"])),
                                       ("the same email address", emails & set(d["email_keys"]))) if same]
        if why and d["key"] != skip:
            found.append({"key": d["key"], "name": d["name"], "why": " and ".join(why), "unapplied": d["pending"] == "new"})
    return found


def contact_changes(c: Contact) -> dict:
    """An edit that fills an empty contact with everything c holds except its photo."""
    changes = _blank()
    parts = [c.prefix, c.given, c.middle, c.family, c.suffix]
    if any(parts):
        changes["set"]["name"] = parts
    changes["set"] |= {f: getattr(c, f) for f in CLEARABLE if getattr(c, f)}
    changes["add"] = [_value_op(f, v) for f in MULTI for v in getattr(c, f)]
    return changes


def has_edits(edit: dict) -> bool:
    """Whether an edit to one contact changes anything."""
    return bool(edit["set"] or edit["photo"] or edit["add"] or edit["remove"] or edit["relabel"] or edit["respell"]
                or edit["order"] or edit["mark_first"] or edit["company_card"] is not None or edit["drop_extras"]
                or edit.get("carry"))


def show(field: str, value: str) -> str:
    """A field's value as the review page shows it."""
    if not value:
        return ""
    if field in ("birthday", "dates"):
        year, month, day = value.rsplit("-", 2)
        try:
            return f"{MONTHS[int(month) - 1]} {int(day)}" + (f", {year}" if year.isdigit() else "")
        except (ValueError, IndexError):
            return value
    if field == "note":
        value = " ".join(value.split())
        return value if len(value) <= 80 else value[:79] + "…"
    return value


def show_all(field: str, value: str) -> str:
    """A field's value in full: the same as show, except that notes aren't shortened."""
    return value if field == "note" else show(field, value)


def _column_names(accounts: list[dict]) -> dict[str, str]:
    """Each account's name in the review, by account key. The review's columns go by name, so two accounts with
    the same one, such as two iCloud accounts left without a label, each get their login added."""
    counts = Counter(a["name"] for a in accounts)
    return {a["key"]: a["name"] if counts[a["name"]] == 1 else f"{a['name']} ({a['key'].partition(':')[2]})"
            for a in accounts}


def _fingerprint(basis) -> str:
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()[:16]


class _Picks:
    """Values and labels picked in the review. A pick counts only while what it was picked between is what's
    there now, so a value that changes afterwards is asked about instead of being overwritten. A pick from
    before this was kept has no fingerprint yet, and counts until the next check gives it one."""

    def __init__(self, decisions: dict):
        self._picks, self._seen = decisions.get("picks", {}), decisions.get("pick_seen", {})

    def get(self, pick_id: str, values) -> str | None:
        seen = self._seen.get(pick_id)
        return self._picks.get(pick_id) if seen in (None, _fingerprint(sorted(values))) else None


class _Skips(set):
    """Unticked rows and list values. A row stays unticked only while what it compares is unchanged, so a later
    change, such as a new number under the same label, isn't hidden. A row with nothing to go on (seen "") stays
    unticked for as long as it's there, and so does one from before this was kept, until the next check."""

    def __init__(self, decisions: dict):
        super().__init__(decisions.get("skips", []))
        self._seen = decisions.get("skip_seen", {})

    def holds(self, row_id: str, seen: str) -> bool:
        return row_id in self and (not seen or self._seen.get(row_id) in (None, seen))


def _decision_keys(decisions: dict) -> set[str]:
    """The person keys that unticks, picks and duplicate choices are filed under ("<account>|<id>")."""
    ids = [*decisions.get("skips", []), *decisions.get("keeps", []), *decisions.get("picks", {}),
           *decisions.get("duplicates", {}), *decisions.get("extras", {}), *decisions.get("edits", {}),
           *decisions.get("deletes", [])]
    return {"|".join(i.split("|", 2)[:2]) for i in ids if not i.startswith("group|")}


def _edits(person_ops: dict) -> bool:
    return bool(person_ops["update"] or person_ops["create"] or person_ops["delete"] or person_ops["drop"])


def _blank() -> dict:
    """An edit to one contact: fields to set ("" empties one), the photo ({"from": ref} or "clear"), list values
    to add, remove, relabel and respell (write as given, once, wherever the card has that value), the order to
    put lists in ({field: keys}), the lists whose first value iCloud marks as preferred, whether an iCloud card
    shows as a company (None leaves it), and whether to drop what only Google can hold."""
    return {"set": {}, "photo": None, "add": [], "remove": [], "relabel": [], "respell": [], "order": {},
            "mark_first": [], "company_card": None, "drop_extras": False}


def _value_op(field: str, v: Value) -> dict:
    return {"field": field, "key": v.key or fold(v.value), "value": v.value, "label": v.label, "parts": list(v.parts)}


# --- What every account held after the last apply ---

class _Last:
    """What each account held after the last apply. A value an account has deleted since then is removed
    from the other accounts; a value that was never synced is copied to them."""

    def __init__(self, base: dict, refs_now: set[str]):
        self._contacts = base.get("contacts", {})
        self._groups = {a: set(g) for a, g in base.get("groups", {}).items()}
        self._clusters = base.get("clusters", [])
        self._cluster_of = {r: cluster for cluster in self._clusters for r in cluster}
        self._now = refs_now

    def links(self, different: set[str]) -> set[str]:
        """Pairs of contacts that were one person at the last apply, so changing a name or number in one
        account doesn't split them up. A person holding a pair since answered "different" isn't linked."""
        apart = [set(pair.split("||")) for pair in different]
        pairs = set()
        for cluster in self._clusters:
            if any(pair <= set(cluster) for pair in apart):
                continue
            present = sorted(r for r in cluster if r in self._now)
            pairs |= {f"{a}||{b}" for a, b in zip(present, present[1:])}
        return pairs

    def deleted_from(self, refs: list[str], missing: list[str]) -> list[str]:
        """The accounts in missing that had this person at the last apply and have since deleted them."""
        before = {r for ref in refs for r in self._cluster_of.get(ref, ())}
        gone = {r.split("|", 1)[0] for r in before if r not in self._now}
        return [a for a in missing if a in gone]

    def changed(self, c: Contact, field: str, key: str) -> bool:
        """Whether c's value, compared as key, differs from what c held at the last apply."""
        entry = self._contacts.get(c.ref)
        return entry is not None and not _matches(field, entry["fields"].get(field, ""), key)

    def had(self, c: Contact, field: str, key: str) -> bool:
        """Whether c held this value at the last apply."""
        old = self._contacts.get(c.ref, {}).get("fields", {}).get(field, "")
        return bool(old) and _matches(field, old, key)

    def company_card(self, c: Contact) -> bool | None:
        """Whether c showed as a company at the last apply; None if that isn't recorded."""
        return self._contacts.get(c.ref, {}).get("company_card")

    def photo_changed(self, c: Contact, fp: str) -> bool:
        entry = self._contacts.get(c.ref)
        if entry is None or entry["photo"] == "?":
            return False
        return not entry["photo"] or not photos.same(entry["photo"], fp)

    def had_photo(self, c: Contact, fp: str) -> bool:
        old = self._contacts.get(c.ref, {}).get("photo", "")
        return old not in ("", "?") and photos.same(old, fp)

    def lists(self, c: Contact, field: str) -> dict[str, str]:
        """c's values in field at the last apply, as {key: label}."""
        return self._contacts.get(c.ref, {}).get("lists", {}).get(field, {})

    def groups(self, c: Contact) -> set[str]:
        return set(self._contacts.get(c.ref, {}).get("groups", []))

    def account_groups(self, account: str) -> set[str]:
        return self._groups.get(account, set())


# --- Working out the person every account should have ---

def _merge(key: str, members: list[Contact], picks: _Picks, names: dict, last: _Last, extras: dict,
           edit: dict | None = None) -> tuple[dict, list[dict]]:
    """The person as all accounts should have them, and the fields whose values disagree.

    merged["cleared"] maps each field (and "photo") that an account deleted since the last apply, while the
    others kept it unchanged, to the accounts that deleted it. Those fields are emptied everywhere.
    merged["baseline"] is the person without any pending edit, and merged["view"] the person with it.
    """
    merged, conflicts, cleared = {}, [], {}
    for field, title in SINGLE.items():
        options = {}
        for c in members:
            value = _compare_key(field, c.name() if field == "name" else getattr(c, field))
            if value:
                options.setdefault(value, {"value": value, "contacts": []})["contacts"].append(c)
        if field == "birthday":
            _settle_years(options)
        changed = {k for k, o in options.items() if any(last.changed(c, field, k) for c in o["contacts"])}
        chosen = _choose(f"{key}|{field}", options, picks, changed)
        if len(options) > 1:
            conflicts.append(_conflict(f"{key}|{field}", title, options, chosen, names, picks,
                                       lambda o: {"value": show(field, o["value"])}))
        merged[field] = options[chosen]["value"] if chosen else ""
        if field == "name":
            source = _newest(options[chosen]["contacts"]) if chosen else None
            merged["name_parts"] = ([_compare_key(field, p) for p in
                                     (source.prefix, source.given, source.middle, source.family, source.suffix)]
                                    if source else [""] * 5)
        elif chosen and len(options) == 1 and chosen not in changed:
            emptied = [c.account for c in members if not getattr(c, field) and last.had(c, field, chosen)]
            if emptied:
                cleared[field], merged[field] = emptied, ""
    merged["labels_held"] = {}  # "<field>~<value>" -> every label the accounts give it, which a pick is made between
    for field in MULTI:
        merged[field] = _union(members, field, last)
        for v in merged[field]:  # a label picked on the review page wins
            held = sorted({x.label.lower() for c in members for x in getattr(c, field) if (x.key or fold(x.value)) == v.key})
            merged["labels_held"][f"{field}~{v.key}"] = held
            v.label = picks.get(f"{key}|{field}~{v.key}", held) or v.label
            # The accounts may hold the same value written differently. Every account ends up with one wording.
            spellings = _spellings(field, v.key, members)
            written = _choose(f"{key}|{field}#{v.key}", spellings, picks, set())
            if len(spellings) > 1:
                conflicts.append(_conflict(f"{key}|{field}#{v.key}", f"How this {MULTI[field]} is written", spellings,
                                           written, names, picks, lambda o: {"value": _text(field, o["value"])}))
            v.value, v.parts = spellings[written]["value"], spellings[written]["parts"]
        # In the order the accounts list them, when they agree.
        listed = [list(dict.fromkeys(k for x in getattr(c, field) if (k := x.key or fold(x.value)))) for c in members]
        order = _agreed_order([v.key for v in merged[field]], listed)
        if order:
            merged[field].sort(key=lambda v: order.index(v.key))
    merged["edit"] = {"removed": {}, "kept": {}, "order": {}, "dropped": {"set": [], "lists": []}}
    merged["baseline"] = _view(merged)
    _apply_edit(key, merged, conflicts, cleared, picks, edit or {})
    merged["view"] = _view(merged)
    merged["extras"] = _extra_details(key, members, merged, extras, cleared, names)
    merged["groups"] = sorted({fold(g): g for c in members for g in c.groups}.values(), key=fold)
    merged["photo"], merged["photo_from"] = _merge_photo(key, members, picks, names, conflicts, last, cleared)
    merged["cleared"] = cleared
    merged["display"] = (merged["name"] or merged["company"]
                         or next((v.value for v in merged["emails"] + merged["phones"]), "") or "(no name)")
    return merged, conflicts


def _view(merged: dict) -> dict:
    """The person as the Contacts pages show them."""
    removed = merged["edit"]["removed"]
    return {"name_parts": list(merged["name_parts"]), **{f: merged[f] for f in SINGLE},
            "lists": {f: [{"value": v.value, "label": v.label, "key": v.key, "parts": list(v.parts)}
                          for v in merged[f] if v.key not in removed.get(f, ())] for f in MULTI}}


def _directory_entry(key: str, view: dict, pending: str) -> dict:
    """One line of the Contacts list, showing what the accounts hold today, and what's needed to search it and spot a
    duplicate. A value only some accounts hold says which."""
    lists, now, total = view["lists"], view["now"], len(view["in"])

    def lines(items: list[dict]) -> list[dict]:
        accounts = {}
        for item in items:
            accounts.setdefault(item["text"], set()).update(item["accounts"])
        return [{"text": text, "where": "" if len(held) == total else ", ".join(sorted(held))} for text, held in accounts.items()]

    return {"key": key, "name": view["display"], "company": lines(now["single"]["company"]), "nickname": view["nickname"],
            "phones": lines(now["lists"]["phones"]), "emails": lines(now["lists"]["emails"]),
            "phone_keys": [r["key"] for r in lists["phones"]], "email_keys": [r["key"] for r in lists["emails"]],
            "name_key": fold(f"{view['name_parts'][1]} {view['name_parts'][3]}") or fold(view["company"]),
            "held": view["held"], "pending": pending}


def _new_person_row(review: dict, key: str, entry: dict, names: dict, skips: _Skips) -> None:
    """A contact entered on the Contacts pages, which no account has yet."""
    cells = {name: [{"text": "Not in this account", "state": "add"}] for name in names.values()}
    row = _row(f"{key}|new", "Contact", cells, list(names), names,
               {"kind": "text", "value": "New contact in every account", "details": _new_details(entry["contact"])}, skips)
    review["sync"]["people"][key] = {
        "name": entry["name"], "refs": [], "held": False, "undeleted": False, "update": {}, "delete": [], "drop": [],
        "create": None if row["skipped"] else {"accounts": list(names), "contact": entry["contact"]}}
    review["people"].append({"key": key, "name": entry["name"], "rows": [row], "held": False})
    review["pending"][key] = "new"
    s = entry["contact"]["set"]
    parts = s.get("name", [""] * 5)
    entered = {"name_parts": parts, "name": " ".join(filter(None, parts)), **{f: s.get(f, "") for f in CLEARABLE},
               "lists": {f: [{k: r[k] for k in ("value", "label", "key", "parts")} for r in entry["contact"]["add"]
                             if r["field"] == f] for f in MULTI}}
    # It's held nowhere yet, so what it'd hold stands in for what the accounts hold today.
    now = {"single": {f: [{"text": show_all(f, entered[f]), "accounts": []}] if entered[f] else [] for f in SINGLE},
           "lists": {f: [{"text": _text(f, r["value"]), "label": r["label"], "key": r["key"], "accounts": []}
                         for r in entered["lists"][f]] for f in MULTI}}
    view = {**entered, "display": entry["name"], "held": False, "new": True, "now": now, "baseline": None, "groups": [],
            "photo": "", "extras": [], "in": [], "missing": list(names.values())}
    review["views"][key] = view
    review["directory"].append(_directory_entry(key, view, "new"))


def _new_details(contact: dict) -> str:
    s = contact["set"]
    lines = [s.get("company", "")] + [f"{a['value']} ({label_text(a['label'])})" for a in contact["add"]
                                      if a["field"] in ("phones", "emails")]
    return " · ".join(line for line in lines if line)


def _apply_edit(key: str, merged: dict, conflicts: list[dict], cleared: dict, picks: _Picks, edit: dict) -> None:
    """Bring a pending edit into the person, in place of what the accounts would otherwise end up with. Every row
    that follows then compares the accounts with it, the same as with any other value."""
    state = merged["edit"]
    for field, change in edit.get("set", {}).items():
        shown = lambda value, f=field: show(f, value) or "(empty)"
        if not _edit_stands(key, "set", field, SINGLE[field], merged[field], change["from"], change["to"], state, picks,
                            conflicts, shown):
            continue
        merged[field] = change["to"]
        if field == "name":
            merged["name_parts"] = change["parts"]
        elif change["to"]:
            cleared.pop(field, None)
        else:
            cleared[field] = []
        conflicts[:] = [c for c in conflicts if c["id"] != f"{key}|{field}"]
    for field, change in edit.get("lists", {}).items():
        now = [_exact(field, v.value, v.parts) for v in merged[field]]
        wanted = [_exact(field, r["value"], r["parts"]) for r in change["to"]]
        by_exact = {_exact(field, v.value, v.parts): _text(field, v.value) for v in merged[field]}
        by_exact |= {_exact(field, r["value"], r["parts"]): _text(field, r["value"]) for r in change["to"]}
        shown = lambda texts, lookup=by_exact: " · ".join(lookup[t] for t in texts) or "(none)"
        if not _edit_stands(key, "lists", field, f"{MULTI[field].capitalize()} list", now, change["from"], wanted, state,
                            picks, conflicts, shown):
            continue
        written = [Value(r["value"], r["label"], r["key"], list(r["parts"])) for r in change["to"]]
        keys = {v.key for v in written}
        state["removed"][field] = {v.key for v in merged[field]} - keys
        state["kept"][field] = keys
        state["order"][field] = [v.key for v in written]
        merged[field] = written + [v for v in merged[field] if v.key not in keys]
        conflicts[:] = [c for c in conflicts if not c["id"].startswith(f"{key}|{field}#")]


def _edit_stands(key: str, kind: str, field: str, title: str, now, before, wanted, state: dict, picks: _Picks,
                 conflicts: list[dict], shown) -> bool:
    """Whether a pending edit to one field counts. If the accounts have moved on since it was made, the review
    asks which to keep, with nothing chosen for you, and until it's answered the edit waits."""
    if now in (before, wanted):
        return True
    edit_id = f"{key}|edit:{field}"
    values = [shown(wanted), shown(now)]
    picked = picks.get(edit_id, values) if picks.get(edit_id, values) in ("edit", "now") else None
    conflicts.append({"id": edit_id, "field": f"{title}: your edit, or what changed since", "chosen": picked,
                      "seen": _fingerprint(sorted(values)), "decided": picked is not None, "required": True,
                      "waiting": "Until you choose, your edit waits and the accounts stay as they are.",
                      "options": [{"key": "edit", "value": values[0], "accounts": ["Your edit"]},
                                  {"key": "now", "value": values[1], "accounts": ["In the accounts now"]}]})
    if picked == "now":
        state["dropped"][kind].append(field)
    return picked == "edit"


def _compare_key(field: str, value: str) -> str:
    """A value as every account should hold it, exactly as written apart from stray spaces. Two values differ
    if these do, even by capitals or punctuation, so every account ends up literally the same."""
    if field == "birthday":
        return value
    return "\n".join((value or "").splitlines()).strip() if field == "note" else " ".join((value or "").split())


def _matches(field: str, value: str, key: str) -> bool:
    """Whether a value is the one an option's key stands for."""
    return _same_birthday(value, key) if field == "birthday" else _compare_key(field, value) == key


def _shown(field: str, value: str) -> str:
    """A value as an account holds it now, saying so if stray spaces are all that's wrong with it."""
    tidy = _compare_key(field, value)
    return f"{show(field, tidy)} (extra space)" if value != tidy else show(field, value)


def _spellings(field: str, key: str, members: list[Contact]) -> dict:
    """The ways the accounts write the list value with this key: {exact text: {"value", "parts", "contacts"}}."""
    options = {}
    for c in members:
        for x in getattr(c, field):
            if (x.key or fold(x.value)) == key:
                parts = without_us_country([p.strip() for p in x.parts]) if field == "addresses" else []
                value = (_address_text(parts) if field == "addresses"
                         else us_phone(x.value.strip()) if field == "phones" else x.value.strip())
                option = options.setdefault(_exact(field, value, parts), {"value": value, "parts": parts, "contacts": []})
                option["contacts"].append(c)
    if field == "dates":
        _settle_years(options)
    return options


def _text(field: str, value: str) -> str:
    """A list value as the review page shows it."""
    return show(field, value) if field == "dates" else value


def _extra_details(key: str, members: list[Contact], merged: dict, decided: dict, cleared: dict, names: dict) -> dict:
    """What to do with details only Google can hold: companies after the first, and locations. iCloud has room
    for one company and job title and no location, so every account keeps one company and the rest go.

    Each has to be decided (see "extras" in build): nothing has a default except that the company every account
    already shows stays the main one. An exact repeat of the main company goes without asking. Once everything
    about a person is decided, the main company replaces the merged one and moved details join the note, which
    the usual rows then bring to every account."""
    current = (merged["company"], merged["title"])
    found = {}
    for c in members:
        for name, title in c.other_companies:
            detail = ("company", _compare_key("company", name), _compare_key("title", title))
            if detail[1:] != current and (detail[1] or detail[2]):
                found.setdefault(detail, set()).add(c.account)
        for place in c.locations:
            found.setdefault(("location", _compare_key("company", place), ""), set()).add(c.account)
    if not found:
        return {"entries": [], "complete": True, "summary": "Repeat removed"}

    def entry(detail: tuple, accounts: list[str], is_current: bool) -> dict:
        entry_id = f"{key}|extra:{_fingerprint(list(detail))}"
        return {"id": entry_id, "kind": detail[0], "name": detail[1], "title": detail[2], "current": is_current,
                "text": ", ".join(filter(None, detail[1:])), "accounts": accounts, "choice": decided.get(entry_id, "")}

    details = sorted(found)
    entries = [entry(d, sorted(names[a] for a in found[d]), False) for d in details]
    if any(d[0] == "company" for d in details) and any(current):
        entries.insert(0, entry(("company", *current), [], True))
        if not any(e["choice"] == "main" for e in entries) and not entries[0]["choice"]:
            entries[0]["choice"] = "main"
    complete = all(e["choice"] for e in entries)
    summary = ""
    if complete:
        main = next((e for e in entries if e["choice"] == "main"), None)
        if main and not main["current"]:
            for field, value in (("company", main["name"]), ("title", main["title"])):
                merged[field] = value
                if value:
                    cleared.pop(field, None)
                else:
                    cleared[field] = []
        moved = [e for e in entries if e["choice"] == "notes"]
        lines = [f"Location: {e['text']}" if e["kind"] == "location" else f"Also: {e['text']}" for e in moved]
        note = merged["note"]
        lines = [line for line in lines if line not in note.splitlines()]  # already there after a failed apply
        if lines:
            merged["note"] = "\n".join(filter(None, [note, *lines]))
            cleared.pop("note", None)
        gone = [e["text"] for e in entries if e["choice"] == "delete"]
        summary = " ".join(filter(None, (
            f"Main company: {main['text']}." if main and not main["current"] else "",
            f"Moved to Notes: {'; '.join(e['text'] for e in moved)}." if moved else "",
            f"Deleted: {'; '.join(gone)}." if gone else ""))) or "Removed"
    return {"entries": entries, "complete": complete, "summary": summary}


def _exact(field: str, value: str, parts: list[str]) -> str:
    """A list value's exact text. An address goes by its parts: Google words its own version of the same parts
    differently from iCloud, and that isn't something either account holds."""
    if field != "addresses":
        return value
    return "\n".join(p.replace("\n", ", ") for p in (list(parts) + [""] * 5)[:5])


def _address_text(parts: list[str]) -> str:
    street, city, region, postcode, country = (list(parts) + [""] * 5)[:5]
    line = " ".join(filter(None, (region, postcode)))
    return ", ".join(filter(None, (street.replace("\n", ", "), city, line, country)))


def _same_birthday(a: str, b: str) -> bool:
    """Whether two birthdays agree: the same day, and the same year unless one has none."""
    if not a or not b:
        return a == b
    return a[-5:] == b[-5:] and (a[:4] == b[:4] or not a[0].isdigit() or not b[0].isdigit())


def _settle_years(options: dict) -> None:
    """A birthday without a year counts as the same as one with it, so the version with the year wins. With two
    years for that day there's a choice to make between those, and the one without a year has no say in it."""
    for key in [k for k in options if not k[0].isdigit()]:
        dated = [k for k in options if k[0].isdigit() and k[-5:] == key[-5:]]
        if dated:
            yearless = options.pop(key)
            if len(dated) == 1:
                options[dated[0]]["contacts"] += yearless["contacts"]


def _newest(contacts: list[Contact]) -> Contact:
    return max(contacts, key=lambda c: c.updated or "")


def _choose(conflict_id: str, options: dict, picks: _Picks, changed: set) -> str | None:
    """The user's pick if they made one. Otherwise, of the values changed since the last apply (or of all of
    them when none was), the one from the most recently changed contact."""
    if not options:
        return None
    picked = picks.get(conflict_id, options)
    if picked in options:
        return picked
    pool = [k for k in options if k in changed] or list(options)
    return max(pool, key=lambda k: _newest(options[k]["contacts"]).updated or "")


def _conflict(conflict_id: str, title: str, options: dict, chosen: str, names: dict, picks: _Picks, describe) -> dict:
    return {"id": conflict_id, "field": title, "chosen": chosen, "seen": _fingerprint(sorted(options)),
            "decided": picks.get(conflict_id, options) in options, "options": [
                {"key": k, **describe(o), "accounts": sorted({names[c.account] for c in o["contacts"]})}
                for k, o in options.items()
            ]}


def _union(members: list[Contact], field: str, last: _Last) -> list[Value]:
    """Every value any account has. Each takes the label most accounts give it, preferring labels changed
    since the last apply; an odd label becomes "other"."""
    merged, labels, changed = {}, defaultdict(list), defaultdict(list)
    for c in members:
        now = {}  # like the record of the last apply: one label per value, the last one when a value repeats
        for v in getattr(c, field):
            key = v.key or fold(v.value)
            if not key:
                continue
            m = merged.setdefault(key, Value(v.value, "", key, list(v.parts)))
            m.odd = m.odd or v.odd
            if v.label:
                labels[key].append(v.label)
                now[key] = v.label
        before = last.lists(c, field)
        changed_here = {k: l for k, l in now.items() if k in before and before[k].lower() != l.lower()}
        for key, value_label in changed_here.items():
            changed[key].append(value_label)
    for key, m in merged.items():
        pool = changed[key] or labels[key]
        if pool:
            top = Counter(l.lower() for l in pool).most_common(1)[0][0]
            m.label = next(l for l in pool if l.lower() == top)
        elif m.odd:
            m.label = "other"
    return list(merged.values())


def _merge_photo(key, members, picks, names, conflicts, last, cleared) -> tuple[str, str]:
    """The photo every account should have, as its fingerprint and the ref of a contact that has it."""
    options = {}
    for c in members:
        if c.photo in ("", "?"):
            continue
        fp = next((k for k in options if photos.same(k, c.photo)), c.photo)
        options.setdefault(fp, {"value": fp, "contacts": []})["contacts"].append(c)
    changed = {k for k, o in options.items() if any(last.photo_changed(c, k) for c in o["contacts"])}
    chosen = _choose(f"{key}|photo", options, picks, changed)
    if len(options) > 1:
        conflicts.append(_conflict(f"{key}|photo", "Photo", options, chosen, names, picks, lambda o: {"thumb": o["value"]}))
    if not chosen:
        return "", ""
    if len(options) == 1 and chosen not in changed:
        emptied = [c.account for c in members if c.photo == "" and last.had_photo(c, chosen)]
        if emptied:
            cleared["photo"] = emptied
            return "", ""
    return chosen, _newest(options[chosen]["contacts"]).ref


# --- Comparison rows ---
# Each row compares what every account has now ("cells") with what all of them will have after the sync
# ("after"). "changing" names the accounts the row would change.

def _row(row_id: str, title: str, cells: dict, changing: list[str], names: dict, after: dict, skips: _Skips,
         basis=None) -> dict:
    """A row. basis is what the row compares, so unticking it lasts only until that changes."""
    seen = "" if basis is None else _fingerprint(basis)
    return {"id": row_id, "title": title, "cells": cells, "changing": [names[a] for a in changing], "after": after,
            "seen": seen, "skipped": skips.holds(row_id, seen)}


def _now(old: str, new: str, changing: bool) -> list[dict]:
    """An account's current value and, when the sync would change it, the new value below it: the old one
    struck through ("old") and the new one marked + ("new"), the same way lists show it."""
    if not changing:
        return [{"text": old or "—"}]
    return ([{"text": old, "state": "old"}] if old else []) + ([{"text": new, "state": "new"}] if new else [])


class _Person:
    """One person's comparison rows, and the edits applying them makes to each account's copy. Where an
    account has the person more than once, the copy with the most details is the one compared and updated,
    and the one kept if the copies are merged."""

    def __init__(self, key: str, copies: list[Contact], merged: dict, names: dict, skips: _Skips, keeps: set,
                 last: _Last, picks: _Picks, deleting: bool = False):
        self.key, self.merged, self.names = key, merged, names
        self.skips, self.keeps, self.last, self.picks, self.deleting = skips, keeps, last, picks, deleting
        self.conflicts: list[dict] = []  # choices that depend on what's kept, such as the order of a list
        by_account = defaultdict(list)
        for c in copies:
            by_account[c.account].append(c)
        self.first = {a: max(cs, key=_detail_count) for a, cs in by_account.items()}
        self.extras = {a: [c for c in cs if c is not self.first[a]] for a, cs in by_account.items() if len(cs) > 1}
        self.missing = [a for a in names if a not in self.first]
        # Each account's list values by key, field by field.
        self.values = {a: {f: {(v.key or fold(v.value)): v for v in getattr(c, f)} for f in MULTI}
                       for a, c in self.first.items()}
        self.rows: list[dict] = []
        self.edits: dict[str, dict] = defaultdict(_blank)
        # "drop" holds extra copies that merging deletes, once everything on them is on the copy kept.
        # "undeleted": an account deleted the person, and the row deleting them from the others is unticked.
        self.ops = {"name": merged["display"], "refs": [c.ref for c in copies], "held": False, "undeleted": False,
                    "update": {}, "create": None, "delete": [], "drop": []}

    def compare(self, duplicates: dict, mass: set[str]) -> None:
        """Fill in the rows, and the edits for the rows left ticked. duplicates holds the user's merge or keep
        choices for copies in the same account; mass, the accounts where unusually many contacts have gone."""
        gone = self.last.deleted_from(self.ops["refs"], self.missing)
        if gone or self.deleting:
            # Deleting on the Contacts page is your own request, so it never starts unticked.
            if not self._delete_row(gone, bool(set(gone) & mass) and not self.deleting)["skipped"]:
                self.ops["delete"] = list(self.ops["refs"])
                return  # nothing else about a person matters once they're being deleted
            self.ops["undeleted"] = bool(gone)
        elif self.missing and not self._contact_row()["skipped"]:
            self.ops["create"] = {"accounts": self.missing, "contact": self._new_contact()}
        for a in self.extras:
            if duplicates.get(f"{self.key}|dup:{a}") == "merge":
                self._merge_row(a)
        self._single_rows()
        self._company_card_row()
        self._extras_row()
        self._photo_row()
        for field, noun in MULTI.items():
            self._list_rows(field, noun)
            self._written_rows(field, noun)
            self._order_rows(field, noun)
        self.ops["update"] = {a: {"ref": self.first[a].ref, **e} for a, e in self.edits.items() if has_edits(e)}

    def held_now(self) -> dict:
        """What the accounts hold today, exactly as written, for the Contacts pages. Each different version of a
        value is listed with the accounts that hold it, the same value in one label or another counting as two."""
        single, lists = {}, {}
        for field in SINGLE:
            found = {}
            for a, c in self.first.items():
                if value := (c.name() if field == "name" else getattr(c, field)):
                    found.setdefault(value, []).append(self.names[a])
            single[field] = [{"text": show_all(field, value), "accounts": sorted(held)} for value, held in found.items()]
        for field in MULTI:
            rank = {r["key"]: i for i, r in enumerate(self.merged["baseline"]["lists"][field])}
            found = {}
            for a, c in self.first.items():
                for v in getattr(c, field):
                    key = v.key or fold(v.value)
                    if key:
                        text = _address_text(v.parts) if field == "addresses" else _text(field, v.value)
                        item = found.setdefault((key, text, v.label.lower()), {
                            "text": text, "label": v.label, "key": key, "accounts": []})
                        if self.names[a] not in item["accounts"]:
                            item["accounts"].append(self.names[a])
            lists[field] = sorted(found.values(), key=lambda item: rank.get(item["key"], len(rank)))
        return {"single": single, "lists": lists}

    def settled(self, edit: dict) -> dict:
        """The fields of a pending edit that need nothing more: every account holds them, or you chose to keep
        what the accounts hold instead."""
        dropped = self.merged["edit"]["dropped"]
        done = {"set": list(dropped["set"]), "lists": list(dropped["lists"])}
        if self.missing:
            return done
        for field, change in edit.get("set", {}).items():
            if all((c.name() if field == "name" else getattr(c, field)) == change["to"] for c in self.first.values()):
                done["set"].append(field)
        for field, change in edit.get("lists", {}).items():
            wanted = [(_exact(field, r["value"], r["parts"]), r["label"].lower()) for r in change["to"]]
            if all([(_exact(field, x.value, x.parts), x.label.lower()) for x in getattr(c, field)] == wanted
                   for c in self.first.values()):
                done["lists"].append(field)
        return done

    def memberships(self, have: dict, dropped: set, to_group, from_group, totals) -> None:
        """Note the groups the person joins in each account, and the ones they leave everywhere because an
        account took them out since the last apply."""
        mine = {a: {fold(g) for g in c.groups} for a, c in self.first.items()}
        left = {g for a, c in self.first.items() for g in self.last.groups(c) - mine[a] if g in have[a]}
        for g in {fold(g) for g in self.merged["groups"]} - dropped:
            if g in left:
                for a in self.first:
                    if g in mine[a]:
                        from_group[(a, g)].append(self._member(a))
                continue
            totals[g] += 1
            for a in self.names:
                if (a in self.first and g not in mine[a]) or (a not in self.first and self.ops["create"]):
                    to_group[(a, g)].append(self._member(a))

    def _member(self, account: str) -> dict:
        """The person's copy in account; ref "" stands for the copy applying creates there."""
        c = self.first.get(account)
        return {"person": self.key, "ref": c.ref if c else "", "name": self.merged["display"]}

    def _row(self, row_id: str, title: str, cells: dict, changing: list[str], after: dict,
             unticked: bool = False, basis=None) -> dict:
        """A row, ticked unless skipped. One that starts unticked stays so until it's ticked."""
        row = _row(row_id, title, cells, changing, self.names, after, self.skips, basis)
        row["skipped"] = row["skipped"] or (unticked and row_id not in self.keeps)
        self.rows.append(row)
        return row

    def _contact_row(self) -> dict:
        cells = ({self.names[a]: [{"text": "Has this contact"}] for a in self.first}
                 | {self.names[a]: [{"text": "Not in this account", "state": "add"}] for a in self.missing})
        after = {"kind": "text", "value": "In every account", "details": _details(self.merged)}
        return self._row(f"{self.key}|new", "Contact", cells, self.missing, after)

    def _delete_row(self, gone: list[str], unticked: bool) -> dict:
        # The same id as the row that copies the person, so a skip carries over either way.
        cells = {}
        for a, name in self.names.items():
            if a in self.first:
                cells[name] = [{"text": "Has this contact", "state": "old"}]
            else:
                cells[name] = [_DELETED] if a in gone else [{"text": "Not in this account"}]
        return self._row(f"{self.key}|new", "Contact", cells, list(self.first),
                         {"kind": "text", "value": "Deleted from every account"}, unticked)

    def _merge_row(self, account: str) -> None:
        """One card in place of several in account: everything on the others moves onto the one kept, which
        the other rows then bring up to date, and the others are deleted."""
        cells = {name: [{"text": "—"}] for a, name in self.names.items() if a != account}
        cells[self.names[account]] = ([{"text": f"{self.first[account].display()} (kept)"}]
                                      + [{"text": c.display(), "state": "old"} for c in self.extras[account]])
        after = {"kind": "text", "value": "One card", "details": "Everything on the other cards, including details "
                 "Contact Sync doesn't otherwise use, moves onto the card kept. The others are then deleted."}
        if not self._row(f"{self.key}|dup:{account}", "Duplicate cards", cells, [account], after)["skipped"]:
            self.edits[account]["carry"] = [c.ref for c in self.extras[account]]
            self.ops["drop"] += [c.ref for c in self.extras[account]]

    def _new_contact(self) -> dict:
        """The edit that fills a new, empty contact with the person."""
        m = self.merged
        changes = _blank()
        if any(m["name_parts"]):
            changes["set"]["name"] = m["name_parts"]
        changes["set"] |= {f: m[f] for f in CLEARABLE if m[f]}
        changes["add"] = [_value_op(f, v) for f in MULTI for v in m[f] if self._kept(f, v)]
        if m["photo"]:
            changes["photo"] = {"from": m["photo_from"]}
        changes["company_card"] = self._company_card()
        return changes

    def _company_card(self) -> bool | None:
        """Whether this person's iCloud cards should show as a company; None with no iCloud card to go by. A card
        changed since the last apply decides; otherwise any card showing as a company does."""
        cards = [c for a, c in self.first.items() if a.startswith("icloud:")]
        if not cards:
            return None
        changed = [c for c in cards if self.last.company_card(c) not in (None, c.company_card)]
        return any(c.company_card for c in (changed or cards))

    def _company_card_row(self) -> None:
        """A row when iCloud accounts disagree on showing the person as a company. Google has no such setting."""
        want = self._company_card()
        cards = {a: c for a, c in self.first.items() if a.startswith("icloud:")}
        changing = [a for a, c in cards.items() if c.company_card != want]
        if not changing:
            return
        word = {True: "Company", False: "Person"}
        cells = {self.names[a]: [{"text": "—"}] for a in self.first}
        cells |= {self.names[a]: _now(word[c.company_card], word[want], a in changing) for a, c in cards.items()}
        after = {"kind": "text", "value": f"{word[want]} card in every iCloud account"}
        row = self._row(f"{self.key}|companycard", "Shown as", cells, changing, after,
                        basis=sorted([a, c.company_card] for a, c in cards.items()))
        if not row["skipped"]:
            for a in changing:
                self.edits[a]["company_card"] = want

    def _extras_row(self) -> None:
        """A row taking what only Google can hold off its cards, once everything about the person is decided."""
        extras = self.merged["extras"]
        holding = {a: c for a, c in self.first.items() if c.other_companies or c.locations}
        if not holding or not extras["complete"]:
            return
        cells = {self.names[a]: [{"text": "—"}] for a in self.first}
        for a, c in holding.items():
            held = [", ".join(filter(None, company)) for company in c.other_companies] + list(c.locations)
            cells[self.names[a]] = [{"text": text, "state": "old"} for text in held]
        row = self._row(f"{self.key}|extras", "Other companies and locations", cells, list(holding),
                        {"kind": "text", "value": extras["summary"]},
                        basis=sorted([a, c.other_companies, c.locations] for a, c in holding.items()))
        if not row["skipped"]:
            for a in holding:
                self.edits[a]["drop_extras"] = True

    def _single_rows(self) -> None:
        cleared = self.merged["cleared"]
        for field, title in SINGLE.items():
            new = self.merged[field]
            have = {a: c.name() if field == "name" else getattr(c, field) for a, c in self.first.items()}
            if field in cleared:
                changing = [a for a, old in have.items() if old]
                cells = {self.names[a]: _now(show(field, old), "", True) if old
                         else [_DELETED] if a in cleared[field] else [{"text": "—"}] for a, old in have.items()}
                after, value = {"kind": "text", "value": "Removed from every account"}, ""
            elif new:
                changing = [a for a, old in have.items() if old != new]
                cells = {self.names[a]: _now(_shown(field, old), show(field, new), a in changing)
                         for a, old in have.items()}
                after = {"kind": "text", "value": show(field, new)}
                value = self.merged["name_parts"] if field == "name" else new
            else:
                continue
            basis = sorted([a, old] for a, old in have.items())
            if changing and not self._row(f"{self.key}|field:{field}", title, cells, changing, after, basis=basis)["skipped"]:
                for a in changing:
                    self.edits[a]["set"][field] = value

    def _photo_row(self) -> None:
        photo = self.merged["photo"]
        cells = {}
        if "photo" in self.merged["cleared"]:
            changing = [a for a, c in self.first.items() if c.photo not in ("", "?")]
            for a, c in self.first.items():
                if a in changing:
                    cells[self.names[a]] = [{"thumb": c.photo, "state": "old"}]
                else:
                    cells[self.names[a]] = [_DELETED] if a in self.merged["cleared"]["photo"] else [{"text": "—"}]
            after, edit = {"kind": "text", "value": "Removed from every account"}, "clear"
        elif photo:
            changing = [a for a, c in self.first.items() if c.photo != "?" and not (c.photo and photos.same(c.photo, photo))]
            for a, c in self.first.items():
                had = c.photo not in ("", "?")
                if a in changing:
                    cells[self.names[a]] = ([{"thumb": c.photo, "state": "old"}] if had else []) + [{"thumb": photo, "state": "new"}]
                else:
                    cells[self.names[a]] = [{"thumb": c.photo}] if had else [{"text": "—"}]
            after, edit = {"kind": "photo", "thumb": photo}, {"from": self.merged["photo_from"]}
        else:
            return
        basis = sorted([a, c.photo] for a, c in self.first.items())
        if changing and not self._row(f"{self.key}|field:photo", "Photo", cells, changing, after, basis=basis)["skipped"]:
            for a in changing:
                self.edits[a]["photo"] = edit

    def _list_rows(self, field: str, noun: str) -> None:
        """For one kind of list (phones, emails…): a row for each value whose label differs between accounts,
        then one row per label listing every value under it, wherever some account's list would change."""
        held = {a: v[field] for a, v in self.values.items()}
        for v in self.merged[field]:
            holders = {a: h[v.key] for a, h in held.items() if v.key in h}
            changing = [a for a, m in holders.items() if v.label and (m.odd or m.label.lower() != v.label.lower())]
            if changing:
                row_id = f"{self.key}|{field}~{v.key}"  # also the id of the label picked in the dropdown
                seen = {m.label for m in holders.values() if m.label}
                options = list(dict.fromkeys(LABEL_CHOICES[field] + sorted(seen, key=str.lower) + [v.label]))
                cells = {self.names[a]: _now(_label_held(m), label_text(v.label), a in changing)
                         for a, m in holders.items()}
                labels_held = self.merged["labels_held"][f"{field}~{v.key}"]
                after = {"kind": "label", "id": row_id, "options": [(o, label_text(o)) for o in options],
                         "chosen": v.label, "seen": _fingerprint(labels_held)}
                row = self._row(row_id, f"Label of {_text(field, v.value)}", cells, changing, after, basis=labels_held)
                if not row["skipped"] and self._kept(field, v):
                    for a in changing:
                        self.edits[a]["relabel"].append({"field": field, "key": v.key, "label": v.label})
        by_label = defaultdict(list)
        for v in self.merged[field]:
            by_label[v.label.lower()].append(v)
        for values in by_label.values():
            keys = {v.key for v in values}
            kept = {v.key for v in values if self._kept(field, v)}
            changing = [a for a, h in held.items() if set(h) & keys != kept]
            if not changing:
                continue
            label = values[0].label
            title = f"{label_text(label)} {noun}" if label else f"{noun} (no label)"
            cells = {}
            for a, h in held.items():
                # What the account has, with values being left out marked "old", then values it would gain as "new".
                now = [{"text": _text(field, h[v.key].value), "state": "" if v.key in kept else "old"}
                       for v in values if v.key in h]
                now += [{"text": _text(field, v.value), "state": "new"} for v in values if v.key in kept and v.key not in h]
                cells[self.names[a]] = now or [{"text": "—"}]
            items = [{"id": f"{self.key}|{field}={v.key}", "text": _text(field, v.value), "kept": v.key in kept,
                      "note": self._deleted_note(field, v.key)} for v in values]
            row = self._row(f"{self.key}|{field}:{label.lower()}", title[0].upper() + title[1:], cells, changing,
                            {"kind": "values", "items": items},
                            basis=[sorted(keys), sorted([a, sorted(set(h) & keys)] for a, h in held.items())])
            if row["skipped"]:
                continue
            for a in changing:
                for v in values:
                    if v.key in kept and v.key not in held[a]:
                        self.edits[a]["add"].append(_value_op(field, v))
                    elif v.key not in kept and v.key in held[a]:
                        self.edits[a]["remove"].append({"field": field, "key": v.key, "value": held[a][v.key].value})

    def _written_rows(self, field: str, noun: str) -> None:
        """A row for each value an account holds written differently from how every account will, or more than
        once, so every account ends up with the same text once."""
        for v in self.merged[field]:
            if not self._kept(field, v):
                continue
            target = _exact(field, v.value, v.parts)
            lines = {a: [x for x in getattr(c, field) if (x.key or fold(x.value)) == v.key] for a, c in self.first.items()}
            exact = {a: [_exact(field, x.value, x.parts) for x in xs] for a, xs in lines.items()}
            changing = [a for a, texts in exact.items() if texts and texts != [target]]
            if not changing:
                continue
            shown = _text(field, v.value)
            cells = {}
            for a, xs in lines.items():
                if a in changing:
                    cells[self.names[a]] = _now(_as_written(field, xs), shown, True)
                else:
                    cells[self.names[a]] = [{"text": shown if xs else "—"}]
            row = self._row(f"{self.key}|{field}#{v.key}", f"How this {noun} is written", cells, changing,
                            {"kind": "text", "value": shown}, basis=sorted([a, texts] for a, texts in exact.items()))
            if not row["skipped"]:
                for a in changing:
                    self.edits[a]["respell"].append({"field": field, "key": v.key, "value": v.value, "parts": list(v.parts)})

    def _order_rows(self, field: str, noun: str) -> None:
        """Every account lists a person's values in the same order. When accounts disagree, the review asks which
        to use, with nothing chosen for you, and until it's answered each account's order stays as it is. Once the
        order is settled, an account gaining a value or losing a repeat is written in it too, and iCloud's
        preferred marker goes on the first value wherever either iCloud account has one."""
        kept = [v for v in self.merged[field] if self._kept(field, v)]
        if len(kept) < 2:
            return
        keys = [v.key for v in kept]
        now = {a: list(dict.fromkeys(x.key or fold(x.value) for x in getattr(c, field))) for a, c in self.first.items()}
        now = {a: [k for k in held if k in keys] for a, held in now.items()}
        text = {v.key: _text(field, v.value) for v in kept}
        plural = noun + ("es" if noun.endswith("s") else "s")
        edited = self.merged["edit"]["order"].get(field)  # the order typed on the Contacts page, which isn't asked about
        order = [k for k in edited if k in keys] if edited else _agreed_order(keys, list(now.values()))
        row_id = f"{self.key}|{field}@order"
        if order is None:
            options = {}
            for a, held in now.items():
                if len(held) >= 2:  # an account holding fewer than two of the values has no order to go by
                    listed = held + [k for k in keys if k not in held]
                    option = options.setdefault(_fingerprint(listed), {"order": listed, "contacts": []})
                    option["contacts"].append(self.first[a])
            chosen = self.picks.get(row_id, options)
            chosen = chosen if chosen in options else None
            self.conflicts.append({**_conflict(row_id, f"Order of {plural}", options, chosen, self.names, self.picks,
                                               lambda o: {"value": " · ".join(text[k] for k in o["order"])}),
                                   "required": True})
            if chosen is None:
                return
            order = options[chosen]["order"]
            edited = order
        changing = [a for a, held in now.items() if held != [k for k in order if k in held]]
        if edited and changing:
            cells = {self.names[a]: [{"text": " · ".join(text[k] for k in held) or "—",
                                      "state": "old" if a in changing else ""}]
                     + ([{"text": " · ".join(text[k] for k in order), "state": "new"}] if a in changing else [])
                     for a, held in now.items()}
            row = self._row(row_id, f"Order of {plural}", cells, changing,
                            {"kind": "text", "value": " · ".join(text[k] for k in order)},
                            basis=sorted([a, held] for a, held in now.items()))
            if row["skipped"]:
                return
        icloud ={a: getattr(c, field) for a, c in self.first.items() if a.startswith("icloud:")}
        marked = any(x.pref for values in icloud.values() for x in values)
        for a, c in self.first.items():
            repeats = len(getattr(c, field)) != len(now[a])
            if now[a] != order or repeats:
                self.edits[a]["order"][field] = order
                if marked and a in icloud:
                    self.edits[a]["mark_first"].append(field)
        if self.ops["create"]:
            self.ops["create"]["contact"]["order"][field] = order
            if marked:
                self.ops["create"]["contact"]["mark_first"].append(field)
        if not marked:
            return
        unmarked = [a for a, values in icloud.items() if field not in self.edits[a]["mark_first"]
                    and not (values and values[0].pref and not any(x.pref for x in values[1:]))]
        if unmarked:
            word = {True: f"First {noun} marked", False: "None marked"}
            cells = {self.names[a]: [{"text": "—"}] for a in self.first}
            cells |= {self.names[a]: _now(word[any(x.pref for x in values)], word[True], a in unmarked)
                      for a, values in icloud.items()}
            row = self._row(f"{self.key}|{field}@preferred", f"Preferred {noun}", cells, unmarked,
                            {"kind": "text", "value": f"First {noun} marked in every iCloud account"},
                            basis=sorted([a, [x.pref for x in values]] for a, values in icloud.items()))
            if not row["skipped"]:
                for a in unmarked:
                    self.edits[a]["mark_first"].append(field)

    def _kept(self, field: str, v: Value) -> bool:
        """Whether every account ends up with this value: unless it's unticked, or an account deleted it since
        the last apply and it wasn't ticked again."""
        value_id = f"{self.key}|{field}={v.key}"
        edit = self.merged["edit"]
        if v.key in edit["removed"].get(field, ()):
            return value_id in self.keeps
        if v.key in edit["kept"].get(field, ()):
            return value_id not in self.skips
        return value_id in self.keeps or (value_id not in self.skips and not self._deleted_by(field, v.key))

    def _deleted_by(self, field: str, key: str) -> list[str]:
        return [a for a, c in self.first.items() if key not in self.values[a][field] and key in self.last.lists(c, field)]

    def _deleted_note(self, field: str, key: str) -> str:
        if key in self.merged["edit"]["removed"].get(field, ()):
            return "Removed in your edit"
        by = self._deleted_by(field, key)
        return f"Deleted from {', '.join(self.names[a] for a in by)} since the last sync" if by else ""


def _agreed_order(keys: list[str], orders: list[list[str]]) -> list[str] | None:
    """The one order that keeps every account's own order, or None if they disagree. Accounts holding different
    values can still agree: x, y in one and x, z in another fits x, y, z. Values it leaves open keep keys' order."""
    before = {k: set() for k in keys}
    for order in orders:
        for earlier, later in zip(order, order[1:]):
            before[later].add(earlier)
    remaining, result = list(keys), []
    while remaining:
        free = next((k for k in remaining if not before[k] & set(remaining)), None)
        if free is None:
            return None
        result.append(free)
        remaining.remove(free)
    return result


def _label_held(v: Value) -> str:
    """The label an account has on a value now, as it's written if it's an odd one."""
    if v.odd:
        return v.odd if isinstance(v.odd, str) else "PREF"  # records from an older version say only that it was odd
    return label_text(v.label)


def _as_written(field: str, values: list[Value]) -> str:
    """How an account writes a value now, saying so if it's there more than once or has stray spaces."""
    texts = [_address_text(v.parts) if field == "addresses" else v.value for v in values]
    tidy = list(dict.fromkeys(_text(field, " ".join(t.split())) for t in texts))
    notes = [f"listed {len(values)} times"] if len(values) > 1 else []
    if any(t != " ".join(t.split()) for t in texts) or any(p != p.strip() for v in values for p in v.parts):
        notes.append("extra space")
    return "; ".join(tidy) + (f" ({', '.join(notes)})" if notes else "")


def _detail_count(c: Contact) -> int:
    singles = sum(bool(getattr(c, f)) for f in CLEARABLE) + bool(c.name()) + (c.photo not in ("", "?"))
    return singles + sum(len(getattr(c, f)) for f in MULTI) + len(c.groups)


def _group_rows(names, have, dropped, spelling, members, to_group, from_group, totals, skips, last):
    """One row per group that some account lacks, has deleted, or would gain or lose people in, and the
    changes each makes, one per account. Google labels count as groups."""
    rows, ops = [], []
    for g in sorted(set().union(*have.values()) | set(totals)):
        title = spelling.get(g, g)
        cells = {}
        if g in dropped:
            changing = [a for a in names if g in have[a]]
            for a, name in names.items():
                if g in have[a]:
                    cells[name] = [{"text": _count(members[(a, g)], "member"), "state": "old"}]
                else:
                    cells[name] = [_DELETED] if g in last.account_groups(a) else [{"text": "Not in this account"}]
            after = {"kind": "text", "value": "Deleted from every account"}
        else:
            changing = [a for a in names if g not in have[a] or to_group.get((a, g)) or from_group.get((a, g))]
            if not changing:
                continue
            for a, name in names.items():
                adds, removes = len(to_group.get((a, g), [])), len(from_group.get((a, g), []))
                if g not in have[a]:
                    cells[name] = [{"text": "Not in this account", "state": "add"}]
                else:
                    cells[name] = ([{"text": _count(members[(a, g)], "member")}]
                                   + ([{"text": f"{adds:,} more", "state": "new"}] if adds else [])
                                   + ([{"text": f"{removes:,} fewer", "state": "gone"}] if removes else []))
            details = "; ".join(
                [f"Adds to {names[a]}: {_names(to_group[(a, g)])}" for a in names if to_group.get((a, g))]
                + [f"Removes from {names[a]}: {_names(from_group[(a, g)])}" for a in names if from_group.get((a, g))])
            after = {"kind": "text", "value": f"In every account, {_count(totals[g], 'member')}", "details": details}
        # Unticked for an account that lacks the group, new members don't bring it back; for a group every
        # account has, the people joining or leaving do.
        lacking = sorted(a for a in names if g not in have[a])
        moving = sorted({m["person"] for a in names for m in to_group.get((a, g), []) + from_group.get((a, g), [])})
        row = _row(f"group|{g}", title, cells, changing, names, after, skips,
                   basis=[g in dropped, lacking, [] if lacking else moving])
        rows.append(row)
        if not row["skipped"]:
            ops += [{"account": a, "group": title, "fold": g, "create": g not in have[a], "delete": g in dropped,
                     "add": to_group.get((a, g), []), "remove": from_group.get((a, g), [])} for a in changing]
    return rows, ops


def _listed_rows(names, unlisted, skips):
    """A row for each Google account with cards outside My Contacts. Google Contacts lists and counts only the
    contacts in that group; a card that's only in a label is there, but missing from its list and count."""
    rows, ops = [], []
    for a, people in unlisted.items():
        cells = {name: [{"text": "—"}] for name in names.values()}
        cells[names[a]] = [{"text": f"{_count(len(people), 'contact')} only in labels, not in My Contacts"}]
        after = {"kind": "text", "value": "In My Contacts, so Google Contacts lists them",
                 "details": f"Adds to My Contacts in {names[a]}: {_names(people)}"}
        row = _row(f"listed|{a}", "My Contacts (Google)", cells, [a], names, after, skips,
                   basis=sorted(m["person"] for m in people))
        rows.append(row)
        if not row["skipped"]:
            ops.append({"account": a, "group": "My Contacts", "fold": "", "create": False, "delete": False,
                        "add": people, "remove": [], "system": True})
    return rows, ops


# --- Descriptions ---

def _details(merged: dict) -> str:
    lines = [merged["company"]] + [f"{v.value} ({label_text(v.label)})" for v in merged["phones"] + merged["emails"]]
    if merged["birthday"]:
        lines.append("Birthday " + show("birthday", merged["birthday"]))
    return " · ".join(line for line in lines if line)


def _summary(c: Contact, names: dict) -> dict:
    """Everything one copy of a contact holds, for the possible-match cards."""
    lines = [" — ".join(filter(None, (c.company, c.title)))]
    lines += [f"{v.value} ({label_text(v.label)})" for v in c.phones + c.emails + c.addresses]
    lines += [v.value for v in c.urls]
    lines += [f"{v.value} ({label_text(v.label)})" for v in c.related]
    if c.birthday:
        lines.append("Birthday " + show("birthday", c.birthday))
    lines += [f"{show('dates', v.value)} ({label_text(v.label)})" for v in c.dates]
    if c.groups:
        lines.append("Groups: " + ", ".join(c.groups))
    if c.note.strip():
        lines.append("Note: " + show("note", c.note.strip().splitlines()[0]))
    lines = [line for line in lines if line]
    thumb = c.photo if c.photo not in ("", "?") else ""
    return {"account": names[c.account], "name": c.display(), "lines": lines or ([] if thumb else ["Name only"]),
            "thumb": thumb, "updated": _when(c.updated)}


def _when(stamp: str) -> str:
    try:
        changed = datetime.fromisoformat(stamp)
    except ValueError:
        return ""
    return f"Last changed {MONTHS[changed.month - 1]} {changed.day}, {changed.year}"


def _names(members: list[dict]) -> str:
    return ", ".join(sorted({m["name"] for m in members}, key=fold))


def _count(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"
