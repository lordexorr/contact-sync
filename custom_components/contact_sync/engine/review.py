"""The review page, the Apply pages, and the decisions made on them. Every decision is saved the moment
it's made."""
import threading
import uuid
from collections import Counter, defaultdict

from . import base, check, plan, storage
from .model import Contact, fold
from .settings import PRIVATE_DIR

DECISIONS_FILE = PRIVATE_DIR / "decisions.json"
CUSTOM = "__custom__"  # the label dropdown's Custom… choice, which is never saved as a label
_lock = threading.Lock()


def current_records(options: dict) -> tuple[list[Contact], list[dict]] | None:
    """The contacts and accounts from the latest check, for the accounts still set up; None before the first."""
    records = check.load_records()
    if not records:
        return None
    active = {f"icloud:{a['apple_id']}" for a in check.icloud_accounts()}
    active |= {f"google:{a['email']}" for a in check.google_accounts()}
    accounts = [a for a in records["accounts"] if a["key"] in active]
    return [Contact.from_dict(c) for c in records["contacts"]], accounts


def current_plan(options: dict) -> dict | None:
    """The review from the latest check; None before the first check. review["unread"] names any account the
    check couldn't read, which the review and the Apply page say are left out."""
    loaded = current_records(options)
    if not loaded:
        return None
    review = plan.build(*loaded, decisions(), base.load())
    failed = [a for a in (check.load_status() or {}).get("accounts", []) if a["error"]]
    review["unread"] = [f"{a['service']} {a['name']}" for a in failed]
    review["warnings"] += [f"{a['service']} {a['name']} couldn't be read at the latest check ({a['error']}), so it's "
                           "left out. Applying changes only the other accounts, and it catches up once it can be "
                           "read." for a in failed]
    return review


def decisions() -> dict:
    return storage.read_json(DECISIONS_FILE, {})


def waiting_message(options: dict) -> str:
    """What the daily notification says: what's waiting, and any account that couldn't be read. "" for nothing."""
    lines = []
    review = current_plan(options)
    if review and any(review["counts"].values()):
        lines.append(f"{_counts_line(review['counts'])}. Open Contact Sync in Home Assistant to review and apply.")
    status = check.load_status()
    failed = [f"{a['service']} {a['name']}: {a['error']}" for a in (status or {}).get("accounts", []) if a["error"]]
    if failed:
        lines.append("Couldn't read " + "; ".join(failed))
    return "\n\n".join(lines)


# --- Decisions ---

def decide_match(pair: str, decision: str) -> None:
    def change(d):
        same, different = set(d.get("same", [])), set(d.get("different", []))
        (same if decision == "same" else different).add(pair)
        (different if decision == "same" else same).discard(pair)
        d["same"], d["different"] = sorted(same), sorted(different)
    _update(change)


def decide_duplicate(dup_id: str, decision: str) -> None:
    """Merge a person's copies in one account into one card, or keep them all."""
    if dup_id and decision in ("merge", "keep"):
        _update(lambda d: d.setdefault("duplicates", {}).update({dup_id: decision}))


def decide_extra(extra_id: str, choice: str) -> None:
    """What happens to a detail only Google can hold: the main company, moved to Notes, or deleted. A person has
    one main company, so choosing another leaves the one before it to be decided."""
    if not extra_id or choice not in ("main", "notes", "delete"):
        return

    def change(d):
        extras = d.setdefault("extras", {})
        if choice == "main":
            person = extra_id.rpartition("|extra:")[0]
            for other in [i for i, v in extras.items() if v == "main" and i.rpartition("|extra:")[0] == person]:
                del extras[other]
        extras[extra_id] = choice
    _update(change)


def choose_group(key: str, group: str) -> None:
    """A group for someone in none, in place of any chosen before, waiting to be applied the same as one chosen on
    their form. An empty one leaves them in none, and the review stops asking."""
    group = plan.tidy_text("company", group)[:60]
    if not key or group == CUSTOM:
        return

    def change(d):
        edits = d.setdefault("edits", {})
        edit = {k: v for k, v in edits.get(key, {"set": {}, "lists": {}}).items() if k != "groups"}
        left_out = set(d.get("no_group", [])) - {key}
        if group:
            edit["groups"] = {"from": [], "to": [group]}
            d["skips"] = [i for i in d.get("skips", []) if i != f"group|{fold(group)}"]
        else:
            left_out.add(key)
        if any(edit.values()):
            edits[key] = edit
        else:
            edits.pop(key, None)
        d["no_group"] = sorted(left_out)
    _update(change)


def pick(choice_id: str, choice: str, seen: str = "", row: str = "") -> None:
    """A value picked for a field that differs between accounts, or a label picked for one value. seen
    fingerprints what it was picked between (see plan._Picks). row is the value's row when Leave as they are
    unticked it: picking a value ticks it again."""
    if not (choice_id and choice):
        return

    def change(d):
        d.setdefault("picks", {})[choice_id] = choice
        _note_seen(d.setdefault("pick_seen", {}), choice_id, seen)
        if row:
            _tick(d, row, True, "")
    _update(change)


def set_skip(change_id: str, keep: bool, seen: str = "") -> None:
    """Tick or untick a row or a list value. seen fingerprints what an unticked row compares (see plan._Skips)."""
    if change_id:
        _update(lambda d: _tick(d, change_id, keep, seen))


def _tick(d: dict, change_id: str, keep: bool, seen: str) -> None:
    # "keeps" holds what was ticked again, so a value an account deleted can be kept everywhere instead.
    skips, keeps = set(d.get("skips", [])), set(d.get("keeps", []))
    (skips.discard if keep else skips.add)(change_id)
    (keeps.add if keep else keeps.discard)(change_id)
    d["skips"], d["keeps"] = sorted(skips), sorted(keeps)
    _note_seen(d.setdefault("skip_seen", {}), change_id, "" if keep else seen)


def keep_unticked(row_ids: list[str]) -> None:
    """Leave these rows unticked from now on."""
    if row_ids:
        _update(lambda d: d.update(skips=sorted(set(d.get("skips", [])) | set(row_ids))))


def reset() -> None:
    _update(lambda d: d.clear())


def save_edit(key: str, edit: dict) -> None:
    """Keep what was entered on a contact's form until it's applied. Rows unticked for those fields are ticked
    again, since entering a value is asking for it. An edit that changes nothing cancels any waiting."""
    def change(d):
        edits = d.setdefault("edits", {})
        if edit["set"] or edit["lists"] or edit.get("groups"):
            edits[key] = edit
        else:
            edits.pop(key, None)
        prefixes = tuple(f"{key}|field:{f}" for f in edit["set"]) + tuple(
            f"{key}|{f}{mark}" for f in edit["lists"] for mark in (":", "=", "~", "#", "@"))
        groups = edit.get("groups") or {"from": [], "to": []}
        changed = {f"group|{g}" for g in set(groups["from"]) ^ {fold(name) for name in groups["to"]}}
        d["skips"] = [i for i in d.get("skips", []) if not i.startswith(prefixes) and i not in changed]
    _update(change)


def add_new_person(person: dict) -> str:
    """Keep a contact entered on the Contacts page until it's applied. Its key while no account has it."""
    key = f"new|{uuid.uuid4().hex}"
    _update(lambda d: d.setdefault("new_people", {}).update({key: person}))
    return key


def update_new_person(key: str, person: dict) -> None:
    """Replace an entered contact that hasn't been applied."""
    _update(lambda d: d.setdefault("new_people", {}).update({key: person}))


def finish_new_people(keys) -> None:
    """Forget entered contacts that have been created."""
    if keys:
        _update(lambda d: d.update(new_people={k: v for k, v in d.get("new_people", {}).items() if k not in keys}))


def request_delete(key: str) -> None:
    """Ask for a person to be deleted from every account when changes are next applied."""
    def change(d):
        d["deletes"] = sorted(set(d.get("deletes", [])) | {key})
        d["skips"] = [i for i in d.get("skips", []) if i != f"{key}|new"]
    _update(change)


def discard_pending(key: str) -> None:
    """Forget an edit, delete or new contact that hasn't been applied."""
    def change(d):
        d.get("edits", {}).pop(key, None)
        d.get("new_people", {}).pop(key, None)
        d["deletes"] = [k for k in d.get("deletes", []) if k != key]
    _update(change)


def tidy_decisions(options: dict) -> None:
    """After a check or an apply, forget choices about anything the accounts no longer differ on, so an answer
    given once can't undo a later edit. Nothing is forgotten while an account can't be read, because what it
    holds may be the only difference."""
    review = current_plan(options)
    if review and not review["unread"]:
        _update(lambda d: tidy(d, review))


def tidy(d: dict, review: dict) -> None:
    """decided (d) without the choices review no longer has a place for. A choice from before fingerprints were
    kept gets the fingerprint of what's there now."""
    rows = [r for p in review["people"] for r in p["rows"]] + review["groups"]
    row_seen = {r["id"]: r["seen"] for r in rows}
    values = {i["id"] for r in rows if r["after"]["kind"] == "values" for i in r["after"]["items"]}
    pick_seen = ({c["id"]: c["seen"] for c in review["conflicts"]}
                 | {r["id"]: r["after"]["seen"] for r in rows if r["after"]["kind"] == "label"})
    duplicates = {x["id"] for x in review["duplicates"]}
    extras = {e["id"] for x in review.get("extras", []) for e in x["entries"]}
    d["extras"] = {i: v for i, v in d.get("extras", {}).items() if i in extras}
    d["skips"] = [i for i in d.get("skips", []) if i in row_seen or i in values]
    d["keeps"] = [i for i in d.get("keeps", []) if i in row_seen or i in values]
    skip_seen = d.get("skip_seen", {})
    d["skip_seen"] = {i: skip_seen.get(i, row_seen[i]) for i in d["skips"] if row_seen.get(i)}
    d["picks"] = {i: v for i, v in d.get("picks", {}).items() if i in pick_seen}
    old_seen = d.get("pick_seen", {})
    d["pick_seen"] = {i: old_seen.get(i, pick_seen[i]) for i in d["picks"]}
    d["duplicates"] = {i: v for i, v in d.get("duplicates", {}).items() if i in duplicates}
    # A pending edit lasts until every account holds it, and a delete until the person is gone.
    people, settled = review["sync"]["people"], review.get("edit_settled", {})
    d["deletes"] = [k for k in d.get("deletes", []) if k in people]
    # Someone waiting on a possible match isn't asked about for now, which doesn't change the answer.
    ungrouped = {u["id"] for u in review.get("ungrouped", [])}
    d["no_group"] = [k for k in d.get("no_group", []) if k in ungrouped or people.get(k, {}).get("held")]
    edits = {}
    for key, edit in d.get("edits", {}).items():
        done = settled.get(key, {})
        left = {kind: {f: c for f, c in edit.get(kind, {}).items() if f not in done.get(kind, [])}
                for kind in ("set", "lists")}
        if edit.get("groups") and not done.get("groups"):
            left["groups"] = edit["groups"]
        if key in people and any(left.values()):
            edits[key] = left
    d["edits"] = edits


def _note_seen(seen_by_id: dict, choice_id: str, seen: str) -> None:
    if seen:
        seen_by_id[choice_id] = seen
    else:
        seen_by_id.pop(choice_id, None)


def _update(change) -> None:
    with _lock:
        decisions = storage.read_json(DECISIONS_FILE, {})
        change(decisions)
        storage.write_json(DECISIONS_FILE, decisions)


# --- What the pages show ---
# The panel in Home Assistant's sidebar lays these out. Every word on the pages comes from here, so the test
# scripts check it with everything else.

def summary(review: dict | None) -> dict:
    """The Review card on the Contact Sync page: what's waiting, or that nothing is and what was kept."""
    if review is None:
        return {"ready": False, "waiting": "", "matches": "", "kept": ""}
    if any(review["counts"].values()):
        return {"ready": True, "waiting": _counts_line(review["counts"]), "matches": "", "kept": ""}
    # The review stays open even with nothing waiting, so ignored rows and past answers can be changed.
    ignored = _ignored(review)
    decided = (sum(c["decided"] or c.get("left", False) for c in review["conflicts"]) + len(review["decided_matches"])
               + sum(bool(d["choice"]) for d in review["duplicates"])
               + sum(d["complete"] for d in review.get("extras", []))
               + sum(u["decided"] for u in review.get("ungrouped", [])))
    kept = " and ".join(filter(None, (f"{ignored:,} ignored" if ignored else "",
                                      f"{decided:,} decided" if decided else "")))
    matches = "Every account that could be read matches." if review.get("unread") else "Every account matches."
    return {"ready": True, "waiting": "", "matches": f"{matches} There's nothing to sync.",
            "kept": f"{kept}, under Open the review." if kept else ""}


def page_data(review: dict | None) -> dict | None:
    """The review page; None before the first check. In each section the panel shows what's still to decide on
    top and folds away what's decided, and folds unticked rows away under Ignored."""
    if review is None:
        return None
    # A new group typed for one person is offered for the rest, before any account has it.
    typed = {fold(g): g for u in review["ungrouped"] for g in u["groups"]}
    choices = sorted((typed | {fold(g): g for g in review["group_names"]}).values(), key=fold)
    return {
        "counts": _counts_line(review["counts"]),
        "warnings": review["warnings"],
        "suggestions": review["suggestions"],
        "decided_matches": review["decided_matches"],
        "duplicates": review["duplicates"],
        "extras": review["extras"],
        "conflicts": review["conflicts"],
        "ungrouped": [{**u, "chosen": _chosen_group(u, choices)} for u in review["ungrouped"]],
        "group_choices": choices,
        "columns": review["columns"],
        "people": [{"key": p["key"], "name": p["name"], "rows": p["rows"], **_person_footer(review, p)}
                   for p in review["people"]],
        "groups": review["groups"],
        "ignored": _ignored(review),
        "can_apply": not plan.is_empty(plan.scope(review)),
    }


def _chosen_group(u: dict, choices: list[str]) -> str:
    # The one group already chosen for someone shows in their dropdown. More than one is changed on their form.
    only = fold(u["groups"][0]) if len(u["groups"]) == 1 else ""
    return next((g for g in choices if fold(g) == only), "")


def _ignored(review: dict) -> int:
    return sum(r["skipped"] for p in review["people"] for r in p["rows"]) + sum(r["skipped"] for r in review["groups"])


def _person_footer(review: dict, person: dict) -> dict:
    """Under a person's table: waiting on a possible match, or Apply just them, and what's waiting from their form."""
    if person["held"]:
        return {"held": True, "can_apply": False, "pending": ""}
    return {"held": False, "can_apply": not plan.is_empty(plan.scope(review, person["key"])),
            "pending": review.get("pending", {}).get(person["key"], "")}


def _counts_line(counts: dict) -> str:
    parts = [f"{_n(counts['changes'], 'change')} waiting"]
    if counts["suggestions"]:
        parts.append(f"{_n(counts['suggestions'], 'possible match', 'possible matches')} to confirm")
    if counts["conflicts"]:
        parts.append(f"{_n(counts['conflicts'], 'value')} to choose between accounts")
    if counts["duplicates"]:
        parts.append(f"{_n(counts['duplicates'], 'duplicate')} to decide")
    if counts.get("extras"):
        parts.append(f"{_n(counts['extras'], 'extra detail')} to decide")
    if counts.get("ungrouped"):
        parts.append(f"{_n(counts['ungrouped'], 'contact')} to put in a group")
    return " · ".join(parts)


def apply_data(review: dict | None, person: str | None, checking: bool) -> dict | None:
    """The page before applying: what changes in each account, and what Apply now does. None before the first
    check. token fingerprints the work shown, so applying stops if anything changed since."""
    if review is None:
        return None
    people = review["sync"]["people"]
    work = plan.scope(review, person)
    notes = list(review["warnings"])
    if person is None and (held := plan.held_back(review)):
        notes.append(f"{_n(held, 'person', 'people')} waiting on a possible match {'is' if held == 1 else 'are'} "
                     "left out until you answer it in the review.")
    elif person in people and people[person]["held"]:
        notes.append("This person is waiting on a possible match. Answer it in the review first.")
    undecided = sum(not c["decided"] and not c.get("required") and not c.get("left")
                    and (person is None or c["id"].startswith(person + "|")) for c in review["conflicts"])
    if undecided and not plan.is_empty(work):
        notes.append(f"{_n(undecided, 'value')} between accounts {'hasn' if undecided == 1 else 'haven'}'t been "
                     "picked. The value marked in the review is used.")
    asked = [c for c in review["conflicts"] if not c["decided"] and c.get("required")
             and (person is None or c["id"].startswith(person + "|"))]
    orders = sum("waiting" not in c for c in asked)
    if orders and not plan.is_empty(work):
        notes.append(f"{_n(orders, 'list')} {'hasn' if orders == 1 else 'haven'}'t had an order chosen. Every account "
                     "keeps its own order until you choose.")
    if len(asked) > orders:
        notes.append("The accounts changed after you edited this contact, so that part of your edit is waiting. "
                     "Choose which to keep under Different values in the review.")
    open_dups = sum(not d["choice"] and (person is None or d["id"].startswith(person + "|"))
                    for d in review["duplicates"])
    if open_dups and not plan.is_empty(work):
        notes.append(f"{_n(open_dups, 'duplicate')} {'hasn' if open_dups == 1 else 'haven'}'t been decided. "
                     "Their extra cards are left as they are.")
    open_extras = sum(not e["choice"] for d in review["extras"] for e in d["entries"]
                      if person is None or d["id"] == person)
    if open_extras and not plan.is_empty(work):
        notes.append(f"{_n(open_extras, 'extra detail')} {'hasn' if open_extras == 1 else 'haven'}'t been decided. "
                     "They're left as they are.")
    open_groups = sum(not u["decided"] and (person is None or u["id"] == person) for u in review["ungrouped"])
    if open_groups and not plan.is_empty(work):
        notes.append(f"{_n(open_groups, 'contact')} {'isn' if open_groups == 1 else 'aren'}'t in a group yet, and "
                     f"{'stays' if open_groups == 1 else 'stay'} that way until you choose in the review.")
    one = person in people
    return {"title": f"Apply {people[person]['name']}" if one else "Apply changes", "person": person or "",
            "notes": notes, "empty": plan.is_empty(work), "checking": checking,
            "pending": review.get("pending", {}).get(person, "") if one else "",
            "columns": review["columns"], "changes": person_changes(review, person),
            "totals": _totals(work, one), "steps": _steps(one), "token": plan.digest(work)}


def person_changes(review: dict, person: str | None) -> list[dict]:
    """One person's rows that change, to see on their card or Apply page; none with nothing to change. To see, not
    to change: ticks and labels are changed in the review, which saves them as they're clicked."""
    found = next((p for p in review["people"] if p["key"] == person), None)
    return [r for r in found["rows"] if not r["skipped"]] if found else []


def result_data(result: dict | None, progress, when) -> dict:
    """While applying, how far it has got; afterwards, every change made and every one that failed."""
    if progress is not None:
        count = f"{progress.done:,} of {progress.total:,}" if progress.total else ""
        return {"running": True, "step": progress.step, "count": count}
    if not result:
        return {"running": False, "done": False}
    title = {"done": "Applied", "stopped": "Stopped", "failed": "Apply failed"}[result["status"]]
    who = f" {result['person']}" if result["person"] else ""
    made = [c for c in result["changes"] if not c["error"]]
    return {"running": False, "done": True, "title": title + who, "when": when(result["finished_at"]),
            "message": result["message"], "bad": result["status"] != "done",
            "backup": f"contact_sync/backups/{result['backup']}" if result["backup"] else "",
            "failed": [c for c in result["changes"] if c["error"]], "made": made,
            "to_check": sum(bool(c.get("warning")) for c in made)}


def _steps(one_person: bool) -> list[str]:
    """What Apply now does, in order."""
    if one_person:
        read = ("Reads this person's cards again, and stops without writing anything if anything about them "
                "changed since this page opened.")
        backup = "Backs up their cards to a folder named after them"
        record = "Reads their cards again and records what each account holds"
    else:
        read = "Checks every account again, and stops without writing anything if something changed since this page opened."
        backup = "Backs up every account"
        record = "Checks again and records what every account holds"
    return [read,
            f"{backup} in contact_sync/backups, in Home Assistant's config folder, with a What changed.txt file "
            "listing every change. The last 10 backups of this kind are kept.",
            "Makes these changes. Only the details shown in the review are touched; everything else on each contact "
            "stays as it is.",
            f"{record}, so later reviews can tell a deletion from a detail that was never synced."]


def _totals(work: dict, one_person: bool) -> list[dict]:
    """Per account: contacts added, updated and deleted, and each group created, deleted, joined or left."""
    counts = {a: Counter() for a in work["names"]}
    for p in work["people"].values():
        for ref in p["delete"]:
            counts[ref.partition("|")[0]]["deleted"] += 1
        for a in p["update"]:
            counts[a]["updated"] += 1
        for a in (p["create"] or {}).get("accounts", []):
            counts[a]["added"] += 1
    created, deleted, joins, leaves = (defaultdict(list) for _ in range(4))  # account -> group names
    for op in sorted(work["groups"], key=lambda op: op["fold"]):
        a = op["account"]
        if op["delete"]:
            deleted[a].append(op["group"])
        elif op["create"]:
            created[a].append(op["group"])
        if op["add"]:
            joins[a].append(op["group"] if one_person else f"{op['group']} +{len(op['add']):,}")
        if op["remove"]:
            leaves[a].append(op["group"] if one_person else f"{op['group']} −{len(op['remove']):,}")
    rows = []
    for a, name in work["names"].items():
        c = counts[a]
        groups = "; ".join(f"{verb} {', '.join(g)}" for verb, g in (("Created", created[a]), ("Deleted", deleted[a])) if g)
        if one_person:
            members = "; ".join(f"{verb} {', '.join(g)}" for verb, g in (("Added to", joins[a]), ("Taken out of", leaves[a])) if g)
        else:
            members = ", ".join(joins[a] + leaves[a])
        if not (+c or groups or members):
            continue
        rows.append({"account": name, "added": c["added"], "updated": c["updated"], "deleted": c["deleted"],
                     "groups": groups or "–", "members": members or "–"})
    return rows


def _n(count: int, one: str, many: str = "") -> str:
    return f"{count:,} {one if count == 1 else (many or one + 's')}"
