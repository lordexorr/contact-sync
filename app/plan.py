"""What a sync would change in each account, worked out from the latest check, the last apply and your
decisions: the review's comparison tables, and the edits applying them makes."""
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime

from . import match, photos
from .model import Contact, Value, fold, label_text

# Fields with one value per contact, and their names on the review page.
SINGLE = {"name": "Name", "nickname": "Nickname", "company": "Company", "title": "Job title",
          "birthday": "Birthday", "note": "Notes"}
# The single fields a sync can empty, when an account deleted the value since the last apply. Never the name.
CLEARABLE = ("nickname", "company", "title", "birthday", "note")
# Fields with any number of values, and what one value is called.
MULTI = {"phones": "phone", "emails": "email", "addresses": "address", "urls": "website", "related": "related name"}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
# Labels offered when fixing a label: only ones iCloud and Google both have. Any label already on the value
# is offered too, so a one-sided label such as iPhone stays available.
LABEL_CHOICES = {
    "phones": ["mobile", "home", "work", "main", "homefax", "workfax", "pager", "other"],
    "emails": ["home", "work", "other"],
    "addresses": ["home", "work", "other"],
    "urls": ["homepage", "home", "work", "other"],
    "related": [],
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
    in every account even when an account deleted it. base is what the accounts held after the last apply
    (see base.py).

    review["sync"] holds the edits: for each person, the copies to delete, create and update, and the group
    changes, one per account and group. Skipped rows make none.
    """
    names = {a["key"]: a["name"] for a in accounts}
    contacts = [c for c in contacts if c.account in names]
    by_ref = {c.ref: c for c in contacts}
    picks, skips, keeps = decisions.get("picks", {}), set(decisions.get("skips", [])), set(decisions.get("keeps", []))
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

    review = {"columns": list(names.values()), "suggestions": [], "conflicts": [], "people": [], "groups": [],
              "duplicates": [], "clusters": clusters, "sync": {"names": names, "people": {}, "groups": []},
              "warnings": [f"{gone[a]:,} contacts have gone from {names[a]} since the last sync, more than usual. "
                           "Deleting them from the other accounts waits until you tick each one, so check that "
                           "account first." for a in sorted(mass)]}
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
        merged, conflicts = _merge(key, copies, picks, names, last)
        review["conflicts"] += [{**c, "person": merged["display"], "decided": c["id"] in picks} for c in conflicts]
        person = _Person(key, copies, merged, names, skips, keeps, last)
        person.compare(duplicates, mass)
        person.ops["held"] = refs[0] in waiting
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
        review["sync"]["people"][key] = person.ops
        if person.rows:
            review["people"].append({"key": key, "name": merged["display"], "rows": person.rows,
                                     "held": person.ops["held"]})
    review["people"].sort(key=lambda p: fold(p["name"]))
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


def contact_changes(c: Contact) -> dict:
    """An edit that fills an empty contact with everything c holds except its photo."""
    changes = _blank()
    parts = [c.prefix, c.given, c.middle, c.family, c.suffix]
    if any(parts):
        changes["set"]["name"] = parts
    changes["set"] |= {f: getattr(c, f) for f in CLEARABLE if getattr(c, f)}
    changes["add"] = [_value_op(f, v) for f in MULTI for v in getattr(c, f)]
    return changes


def show(field: str, value: str) -> str:
    """A field's value as the review page shows it."""
    if not value:
        return ""
    if field == "birthday":
        year, month, day = value.rsplit("-", 2)
        try:
            return f"{MONTHS[int(month) - 1]} {int(day)}" + (f", {year}" if year.isdigit() else "")
        except (ValueError, IndexError):
            return value
    if field == "note":
        value = " ".join(value.split())
        return value if len(value) <= 80 else value[:79] + "…"
    return value


def _decision_keys(decisions: dict) -> set[str]:
    """The person keys that unticks, picks and duplicate choices are filed under ("<account>|<id>")."""
    ids = [*decisions.get("skips", []), *decisions.get("keeps", []), *decisions.get("picks", {}),
           *decisions.get("duplicates", {})]
    return {"|".join(i.split("|", 2)[:2]) for i in ids if not i.startswith("group|")}


def _edits(person_ops: dict) -> bool:
    return bool(person_ops["update"] or person_ops["create"] or person_ops["delete"] or person_ops["drop"])


def _blank() -> dict:
    """An edit to one contact: fields to set ("" empties one), the photo ({"from": ref} or "clear"), and list
    values to add, remove and relabel."""
    return {"set": {}, "photo": None, "add": [], "remove": [], "relabel": []}


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
        return entry is not None and _compare_key(field, entry["fields"].get(field, "")) != key

    def had(self, c: Contact, field: str, key: str) -> bool:
        """Whether c held this value at the last apply."""
        old = self._contacts.get(c.ref, {}).get("fields", {}).get(field, "")
        return bool(old) and _compare_key(field, old) == key

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

def _merge(key: str, members: list[Contact], picks: dict, names: dict, last: _Last) -> tuple[dict, list[dict]]:
    """The person as all accounts should have them, and the fields whose values disagree.

    merged["cleared"] maps each field (and "photo") that an account deleted since the last apply, while the
    others kept it unchanged, to the accounts that deleted it. Those fields are emptied everywhere.
    """
    merged, conflicts, cleared = {}, [], {}
    for field, title in SINGLE.items():
        options = {}
        for c in members:
            value = c.name() if field == "name" else getattr(c, field)
            if value:
                option = options.setdefault(_compare_key(field, value), {"value": value, "contacts": []})
                option["contacts"].append(c)
                if field == "birthday" and value[0].isdigit():
                    option["value"] = value  # the version with the year wins
        changed = {k for k, o in options.items() if any(last.changed(c, field, k) for c in o["contacts"])}
        chosen = _choose(f"{key}|{field}", options, picks, changed)
        if len(options) > 1:
            conflicts.append(_conflict(f"{key}|{field}", title, options, chosen, names,
                                       lambda o: {"value": show(field, o["value"])}))
        merged[field] = options[chosen]["value"] if chosen else ""
        if field == "name":
            source = _newest(options[chosen]["contacts"]) if chosen else None
            merged["name_parts"] = ([source.prefix, source.given, source.middle, source.family, source.suffix]
                                    if source else [""] * 5)
        elif chosen and len(options) == 1 and chosen not in changed:
            emptied = [c.account for c in members if not getattr(c, field) and last.had(c, field, chosen)]
            if emptied:
                cleared[field], merged[field] = emptied, ""
    for field in MULTI:
        merged[field] = _union(members, field, last)
        for v in merged[field]:  # a label picked on the review page wins
            v.label = picks.get(f"{key}|{field}~{v.key}", v.label)
    merged["groups"] = sorted({fold(g): g for c in members for g in c.groups}.values(), key=fold)
    merged["photo"], merged["photo_from"] = _merge_photo(key, members, picks, names, conflicts, last, cleared)
    merged["cleared"] = cleared
    merged["display"] = (merged["name"] or merged["company"]
                         or next((v.value for v in merged["emails"] + merged["phones"]), "") or "(no name)")
    return merged, conflicts


def _compare_key(field: str, value: str) -> str:
    # Birthdays compare by day and month, so one with the year and one without count as the same.
    return value[-5:] if field == "birthday" else fold(value)


def _newest(contacts: list[Contact]) -> Contact:
    return max(contacts, key=lambda c: c.updated or "")


def _choose(conflict_id: str, options: dict, picks: dict, changed: set) -> str | None:
    """The user's pick if they made one. Otherwise, of the values changed since the last apply (or of all of
    them when none was), the one from the most recently changed contact."""
    if not options:
        return None
    if picks.get(conflict_id) in options:
        return picks[conflict_id]
    pool = [k for k in options if k in changed] or list(options)
    return max(pool, key=lambda k: _newest(options[k]["contacts"]).updated or "")


def _conflict(conflict_id: str, title: str, options: dict, chosen: str, names: dict, describe) -> dict:
    return {"id": conflict_id, "field": title, "chosen": chosen, "options": [
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
        conflicts.append(_conflict(f"{key}|photo", "Photo", options, chosen, names, lambda o: {"thumb": o["value"]}))
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

def _row(row_id: str, title: str, cells: dict, changing: list[str], names: dict, after: dict, skips: set) -> dict:
    return {"id": row_id, "title": title, "cells": cells, "changing": [names[a] for a in changing], "after": after,
            "skipped": row_id in skips}


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

    def __init__(self, key: str, copies: list[Contact], merged: dict, names: dict, skips: set, keeps: set,
                 last: _Last):
        self.key, self.merged, self.names = key, merged, names
        self.skips, self.keeps, self.last = skips, keeps, last
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
        self.ops = {"name": merged["display"], "refs": [c.ref for c in copies], "held": False,
                    "update": {}, "create": None, "delete": [], "drop": []}

    def compare(self, duplicates: dict, mass: set[str]) -> None:
        """Fill in the rows, and the edits for the rows left ticked. duplicates holds the user's merge or keep
        choices for copies in the same account; mass, the accounts where unusually many contacts have gone."""
        gone = self.last.deleted_from(self.ops["refs"], self.missing)
        if gone:
            if not self._delete_row(gone, bool(set(gone) & mass))["skipped"]:
                self.ops["delete"] = list(self.ops["refs"])
                return  # nothing else about a person matters once they're being deleted
        elif self.missing and not self._contact_row()["skipped"]:
            self.ops["create"] = {"accounts": self.missing, "contact": self._new_contact()}
        for a in self.extras:
            if duplicates.get(f"{self.key}|dup:{a}") == "merge":
                self._merge_row(a)
        self._single_rows()
        self._photo_row()
        for field, noun in MULTI.items():
            self._list_rows(field, noun)
        self.ops["update"] = {a: {"ref": self.first[a].ref, **e} for a, e in self.edits.items()
                              if e["set"] or e["photo"] or e["add"] or e["remove"] or e["relabel"] or e.get("carry")}

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
             unticked: bool = False) -> dict:
        """A row, ticked unless skipped. One that starts unticked stays so until it's ticked."""
        row = _row(row_id, title, cells, changing, self.names, after, self.skips)
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
        return changes

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
                changing = [a for a, old in have.items()
                            if (old != new if field == "birthday" else fold(old) != fold(new))]
                cells = {self.names[a]: _now(show(field, old), show(field, new), a in changing)
                         for a, old in have.items()}
                after = {"kind": "text", "value": show(field, new)}
                value = self.merged["name_parts"] if field == "name" else new
            else:
                continue
            if changing and not self._row(f"{self.key}|field:{field}", title, cells, changing, after)["skipped"]:
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
        if changing and not self._row(f"{self.key}|field:photo", "Photo", cells, changing, after)["skipped"]:
            for a in changing:
                self.edits[a]["photo"] = edit

    def _list_rows(self, field: str, noun: str) -> None:
        """For one kind of list (phones, emails…): a row for each value whose label differs between accounts,
        then one row per label listing every value under it, wherever some account's list would change."""
        held = {a: v[field] for a, v in self.values.items()}
        for v in self.merged[field]:
            holders = {a: h[v.key] for a, h in held.items() if v.key in h}
            changing = [a for a, m in holders.items() if v.label and m.label.lower() != v.label.lower()]
            if changing:
                row_id = f"{self.key}|{field}~{v.key}"  # also the id of the label picked in the dropdown
                seen = {m.label for m in holders.values() if m.label}
                options = list(dict.fromkeys(LABEL_CHOICES[field] + sorted(seen, key=str.lower) + [v.label]))
                cells = {self.names[a]: _now("PREF" if m.odd else label_text(m.label), label_text(v.label), a in changing)
                         for a, m in holders.items()}
                after = {"kind": "label", "id": row_id, "options": [(o, label_text(o)) for o in options],
                         "chosen": v.label}
                row = self._row(row_id, f"Label of {v.value}", cells, changing, after)
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
                now = [{"text": h[v.key].value, "state": "" if v.key in kept else "old"} for v in values if v.key in h]
                now += [{"text": v.value, "state": "new"} for v in values if v.key in kept and v.key not in h]
                cells[self.names[a]] = now or [{"text": "—"}]
            items = [{"id": f"{self.key}|{field}={v.key}", "text": v.value, "kept": v.key in kept,
                      "note": self._deleted_note(field, v.key)} for v in values]
            row = self._row(f"{self.key}|{field}:{label.lower()}", title[0].upper() + title[1:], cells, changing,
                            {"kind": "values", "items": items})
            if row["skipped"]:
                continue
            for a in changing:
                for v in values:
                    if v.key in kept and v.key not in held[a]:
                        self.edits[a]["add"].append(_value_op(field, v))
                    elif v.key not in kept and v.key in held[a]:
                        self.edits[a]["remove"].append({"field": field, "key": v.key, "value": held[a][v.key].value})

    def _kept(self, field: str, v: Value) -> bool:
        """Whether every account ends up with this value: unless it's unticked, or an account deleted it since
        the last apply and it wasn't ticked again."""
        value_id = f"{self.key}|{field}={v.key}"
        return value_id in self.keeps or (value_id not in self.skips and not self._deleted_by(field, v.key))

    def _deleted_by(self, field: str, key: str) -> list[str]:
        return [a for a, c in self.first.items() if key not in self.values[a][field] and key in self.last.lists(c, field)]

    def _deleted_note(self, field: str, key: str) -> str:
        by = self._deleted_by(field, key)
        return f"Deleted from {', '.join(self.names[a] for a in by)} since the last sync" if by else ""


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
        row = _row(f"group|{g}", title, cells, changing, names, after, skips)
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
        row = _row(f"listed|{a}", "My Contacts (Google)", cells, [a], names, after, skips)
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
