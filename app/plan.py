"""What a sync would change in each account, worked out from the latest check and your decisions."""
from collections import Counter, defaultdict
from datetime import datetime

from . import match, photos
from .model import Contact, Value, fold, label_text

# Fields with one value per contact, and their names on the review page.
SINGLE = {"name": "Name", "nickname": "Nickname", "company": "Company", "title": "Job title",
          "birthday": "Birthday", "note": "Notes"}
# Fields with any number of values, and what one value is called.
MULTI = {"phones": "phone", "emails": "email", "addresses": "address", "urls": "website", "related": "related name"}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def build(contacts: list[Contact], accounts: list[dict], decisions: dict) -> dict:
    """Possible matches, values to choose between, and every change for each account.

    accounts holds {"key", "name", "groups"} for each account read in the latest check; contacts in
    any other account are ignored, so an account that couldn't be read never looks empty.
    decisions holds the user's "same"/"different" pairs, "picks" and "skips".
    """
    names = {a["key"]: a["name"] for a in accounts}
    contacts = [c for c in contacts if c.account in names]
    by_ref = {c.ref: c for c in contacts}
    picks, skips = decisions.get("picks", {}), set(decisions.get("skips", []))
    clusters, suggestions = match.match(contacts, set(decisions.get("same", [])), set(decisions.get("different", [])))
    spelling = {fold(g): g for a in accounts for g in a["groups"]} | {fold(g): g for c in contacts for g in c.groups}

    review = {"suggestions": [], "conflicts": [], "people": [], "groups": [], "duplicates": []}
    for pair, reason in suggestions:
        review["suggestions"].append({
            "id": pair, "reason": reason, "contacts": [_summary(by_ref[r], names) for r in pair.split("||")],
        })
    to_group = defaultdict(list)  # (account, folded group name) -> contacts to add to it
    for refs in clusters:
        members = [by_ref[r] for r in refs]
        key = refs[0]
        merged, conflicts = _merge(key, members, picks, names)
        review["conflicts"] += [{**c, "person": merged["display"]} for c in conflicts]
        changes = []
        for account in names:
            mine = [c for c in members if c.account == account]
            if len(mine) > 1:
                review["duplicates"].append({"person": merged["display"], "account": names[account], "count": len(mine)})
            if mine:
                changes += _differences(key, account, names[account], mine[0], merged, skips)
                has = {fold(g) for g in mine[0].groups}
            else:
                new = _change(f"{key}|{account}|new", names[account], "Add this contact", _details(merged), skips)
                changes.append(new)
                if new["skipped"]:
                    continue
                has = set()
            for group in merged["groups"]:
                if fold(group) not in has:
                    to_group[(account, fold(group))].append(merged["display"])
        if changes:
            review["people"].append({"name": merged["display"], "changes": changes})
    review["people"].sort(key=lambda p: fold(p["name"]))
    review["groups"] = _group_changes(accounts, names, spelling, to_group, skips)

    waiting = [c for p in review["people"] for c in p["changes"] if not c["skipped"]]
    waiting += [g for g in review["groups"] if not g["skipped"]]
    review["counts"] = {
        "changes": len(waiting),
        "suggestions": len(review["suggestions"]),
        "conflicts": len(review["conflicts"]),
    }
    return review


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


def _merge(key: str, members: list[Contact], picks: dict, names: dict) -> tuple[dict, list[dict]]:
    """The person as all accounts should have them, and the fields whose values disagree."""
    newest = max(members, key=lambda c: c.updated or "")
    merged, conflicts = {}, []
    for field, title in SINGLE.items():
        options = {}
        for c in members:
            value = c.name() if field == "name" else getattr(c, field)
            if value:
                option = options.setdefault(_compare_key(field, value), {"value": value, "contacts": []})
                option["contacts"].append(c)
                if field == "birthday" and value[0].isdigit():
                    option["value"] = value  # the version with the year wins
        chosen = _choose(f"{key}|{field}", options, newest, picks)
        if len(options) > 1:
            conflicts.append(_conflict(f"{key}|{field}", title, options, chosen, names,
                                       lambda o: {"value": show(field, o["value"])}))
        merged[field] = options[chosen]["value"] if chosen else ""
    for field in MULTI:
        merged[field] = _union(members, field)
    merged["groups"] = sorted({fold(g): g for c in members for g in c.groups}.values(), key=fold)
    merged["photo"] = _merge_photo(key, members, newest, picks, names, conflicts)
    merged["display"] = (merged["name"] or merged["company"]
                         or next((v.value for v in merged["emails"] + merged["phones"]), "") or "(no name)")
    return merged, conflicts


def _compare_key(field: str, value: str) -> str:
    # Birthdays compare by day and month, so one with the year and one without count as the same.
    return value[-5:] if field == "birthday" else fold(value)


def _choose(conflict_id: str, options: dict, newest: Contact, picks: dict) -> str | None:
    """The user's pick if they made one, otherwise the value from the most recently changed contact."""
    if not options:
        return None
    if picks.get(conflict_id) in options:
        return picks[conflict_id]
    return next((k for k, o in options.items() if any(c is newest for c in o["contacts"])), next(iter(options)))


def _conflict(conflict_id: str, title: str, options: dict, chosen: str, names: dict, describe) -> dict:
    return {"id": conflict_id, "field": title, "chosen": chosen, "options": [
        {"key": k, **describe(o), "accounts": sorted({names[c.account] for c in o["contacts"]})}
        for k, o in options.items()
    ]}


def _union(members: list[Contact], field: str) -> list[Value]:
    """Every value any account has. Each takes the label most accounts give it; an odd label becomes "other"."""
    merged, labels = {}, defaultdict(list)
    for c in members:
        for v in getattr(c, field):
            key = v.key or fold(v.value)
            if not key:
                continue
            m = merged.setdefault(key, Value(v.value, "", key, list(v.parts)))
            m.odd = m.odd or v.odd
            if v.label:
                labels[key].append(v.label)
    for key, m in merged.items():
        if labels[key]:
            top = Counter(l.lower() for l in labels[key]).most_common(1)[0][0]
            m.label = next(l for l in labels[key] if l.lower() == top)
        elif m.odd:
            m.label = "other"
    return list(merged.values())


def _merge_photo(key, members, newest, picks, names, conflicts) -> str:
    options = {}
    for c in members:
        if c.photo in ("", "?"):
            continue
        fp = next((k for k in options if photos.same(k, c.photo)), c.photo)
        options.setdefault(fp, {"value": fp, "contacts": []})["contacts"].append(c)
    chosen = _choose(f"{key}|photo", options, newest, picks)
    if len(options) > 1:
        conflicts.append(_conflict(f"{key}|photo", "Photo", options, chosen, names, lambda o: {"thumb": o["value"]}))
    return chosen or ""


def _differences(key: str, account: str, account_name: str, c: Contact, merged: dict, skips: set) -> list[dict]:
    """The changes that would bring this account's copy of the person in line with everyone else's."""
    changes = []
    for field, title in SINGLE.items():
        old, new = (c.name() if field == "name" else getattr(c, field)), merged[field]
        if new and (old != new if field == "birthday" else fold(old) != fold(new)):
            text = f"{title}: {show(field, old) or 'none'} → {show(field, new)}"
            changes.append(_change(f"{key}|{account}|{field}", account_name, text, "", skips))
    for field, noun in MULTI.items():
        have = {v.key or fold(v.value): v for v in getattr(c, field)}
        for v in merged[field]:
            mine = have.get(v.key)
            if mine is None:
                text = f"Add {noun}: {v.value} ({label_text(v.label)})"
                changes.append(_change(f"{key}|{account}|{field}+{v.key}", account_name, text, "", skips))
            elif v.label and mine.label.lower() != v.label.lower():
                old = "PREF" if mine.odd else label_text(mine.label)
                text = f"Change the label of {v.value}: {old} → {label_text(v.label)}"
                changes.append(_change(f"{key}|{account}|{field}~{v.key}", account_name, text, "", skips))
    photo = merged["photo"]
    if photo and c.photo != "?" and not (c.photo and photos.same(c.photo, photo)):
        text = "Replace the photo" if c.photo else "Add a photo"
        changes.append(_change(f"{key}|{account}|photo", account_name, text, "", skips, thumb=photo))
    return changes


def _change(change_id: str, account_name: str, text: str, details: str, skips: set, thumb: str = "") -> dict:
    return {"id": change_id, "account": account_name, "text": text, "details": details, "thumb": thumb,
            "skipped": change_id in skips}


def _group_changes(accounts: list[dict], names: dict, spelling: dict, to_group: dict, skips: set) -> list[dict]:
    """Groups each account lacks, and contacts each account's groups lack. Google labels count as groups."""
    have = {a["key"]: {fold(g) for g in a["groups"]} for a in accounts}
    every = {fold(g) for a in accounts for g in a["groups"]} | {g for _, g in to_group}
    changes = []
    for account in names:
        for group in sorted(every):
            people = sorted(to_group.get((account, group), []), key=fold)
            create = group not in have[account]
            if not people and not create:
                continue
            name = spelling.get(group, group)
            if create:
                text = f"Create the group “{name}”" + (f" with {_count(len(people), 'contact')}" if people else "")
            else:
                text = f"Add {_count(len(people), 'contact')} to the group “{name}”"
            changes.append(_change(f"group|{account}|{group}", names[account], text, ", ".join(people), skips))
    return changes


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


def _count(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"
