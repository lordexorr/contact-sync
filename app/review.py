"""The review page, and the decisions made on it."""
import html
import threading

from . import check, plan, storage
from .model import Contact
from .settings import PRIVATE_DIR

DECISIONS_FILE = PRIVATE_DIR / "decisions.json"
esc = html.escape
_lock = threading.Lock()


def current_plan(options: dict) -> dict | None:
    """The review from the latest check, for the accounts still set up; None before the first check."""
    records = check.load_records()
    if not records:
        return None
    active = {f"icloud:{a['apple_id']}" for a in options["icloud_accounts"] if a["apple_id"] and a["app_password"]}
    active |= {f"google:{a['email']}" for a in check.google_accounts()}
    accounts = [a for a in records["accounts"] if a["key"] in active]
    contacts = [Contact.from_dict(c) for c in records["contacts"]]
    return plan.build(contacts, accounts, storage.read_json(DECISIONS_FILE, {}))


# --- Decisions ---

def decide_match(pair: str, decision: str) -> None:
    def change(d):
        same, different = set(d.get("same", [])), set(d.get("different", []))
        (same if decision == "same" else different).add(pair)
        (different if decision == "same" else same).discard(pair)
        d["same"], d["different"] = sorted(same), sorted(different)
    _update(change)


def pick(conflict: str, choice: str) -> None:
    if conflict and choice:
        _update(lambda d: d.setdefault("picks", {}).update({conflict: choice}))


def save_changes(shown: list[str], kept: set[str]) -> None:
    """Every change shown on the page that wasn't left ticked is skipped from now on."""
    def change(d):
        d["skips"] = sorted((set(d.get("skips", [])) - set(shown)) | (set(shown) - kept))
    _update(change)


def reset() -> None:
    _update(lambda d: d.clear())


def _update(change) -> None:
    with _lock:
        decisions = storage.read_json(DECISIONS_FILE, {})
        change(decisions)
        storage.write_json(DECISIONS_FILE, decisions)


# --- HTML ---

def summary_card(review: dict | None) -> str:
    head = "<section class='card'><h2>Review</h2>"
    if review is None:
        return head + "<p class='muted'>Nothing to review until the first check has run.</p></section>"
    if not any(review["counts"].values()):
        return head + "<p class='ok'>Every account matches. There's nothing to sync.</p></section>"
    return (head + f"<p>{_counts_line(review['counts'])}</p>"
            "<div class='row'><a class='button' href='review'>Open the review</a></div></section>")


def page_body(review: dict | None) -> str:
    if review is None:
        return "<h1>Review</h1><p class='muted'>Nothing to review until the first check has run.</p>"
    parts = [
        "<h1>Review</h1>",
        "<p class='muted'>Nothing here has been written to any account. Untick a change to skip it; "
        "your choices are kept for later checks.</p>",
        f"<p>{_counts_line(review['counts'])}</p>",
    ]
    if review["suggestions"]:
        parts.append(_suggestions(review["suggestions"]))
    if review["conflicts"]:
        parts.append(_conflicts(review["conflicts"]))
    if review["people"] or review["groups"]:
        parts.append(_changes(review["people"], review["groups"]))
    if review["duplicates"]:
        parts.append(_duplicates(review["duplicates"]))
    parts.append(
        "<section class='card'><h2>Start over</h2><p class='muted'>Forget every match, choice and skip "
        "made on this page.</p><form method='post' action='review/reset'>"
        "<button class='secondary'>Forget my decisions</button></form></section>"
    )
    return "".join(parts)


def _counts_line(counts: dict) -> str:
    parts = [f"{_n(counts['changes'], 'change')} waiting"]
    if counts["suggestions"]:
        parts.append(f"{_n(counts['suggestions'], 'possible match', 'possible matches')} to confirm")
    if counts["conflicts"]:
        parts.append(f"{_n(counts['conflicts'], 'value')} to choose between accounts")
    return " · ".join(parts)


def _suggestions(items: list[dict]) -> str:
    rows = []
    for s in items:
        sides = "".join(
            f"<div><div class='muted'>{esc(c['account'])}</div><b>{esc(c['name'])}</b>"
            + (f"<img class='thumb' src='thumb/{esc(c['thumb'])}.jpg' alt=''>" if c["thumb"] else "")
            + "".join(f"<div>{esc(line)}</div>" for line in c["lines"])
            + (f"<div class='muted'>{esc(c['updated'])}</div>" if c["updated"] else "")
            + "</div>"
            for c in s["contacts"]
        )
        rows.append(
            f"<div class='item'><p class='muted'>{esc(s['reason'])}</p><div class='pair'>{sides}</div>"
            f"<form method='post' action='review/match' class='row'><input type='hidden' name='pair' value='{esc(s['id'])}'>"
            "<button name='decision' value='same'>Same person</button>"
            "<button class='secondary' name='decision' value='different'>Different people</button></form></div>"
        )
    return f"<section class='card'><h2>Possible matches ({len(items)})</h2>{''.join(rows)}</section>"


def _conflicts(items: list[dict]) -> str:
    rows = []
    for c in items:
        options = "".join(
            f"<label class='option'><input type='radio' name='choice' value='{esc(o['key'])}'"
            f"{' checked' if o['key'] == c['chosen'] else ''}>"
            + (f"<img class='thumb' src='thumb/{esc(o['thumb'])}.jpg' alt=''>" if o.get("thumb") else f"<span>{esc(o['value'])}</span>")
            + f"<span class='muted'>{esc(', '.join(o['accounts']))}</span></label>"
            for o in c["options"]
        )
        rows.append(
            f"<form method='post' action='review/pick' class='item'><b>{esc(c['person'])}</b> · {esc(c['field'])}"
            f"<input type='hidden' name='conflict' value='{esc(c['id'])}'>{options}"
            "<button class='secondary'>Use the selected value</button></form>"
        )
    return (f"<section class='card'><h2>Different values ({len(items)})</h2><p class='muted'>The selected value "
            "is the one from the most recently changed contact, unless you pick another.</p>"
            f"{''.join(rows)}</section>")


def _changes(people: list[dict], groups: list[dict]) -> str:
    """Changes waiting first; unticked ones in a collapsed Ignored section at the bottom, in the same form
    so ticking one there and saving brings it back."""
    def blocks(skipped: bool) -> list[str]:
        out = []
        for name, changes in [(p["name"], p["changes"]) for p in people] + [("Groups", groups)]:
            chosen = [c for c in changes if c["skipped"] == skipped]
            if chosen:
                out.append(f"<div class='item'><b>{esc(name)}</b><ul class='changes'>"
                           f"{''.join(_checkbox(c) for c in chosen)}</ul></div>")
        return out

    waiting, ignored = blocks(False), blocks(True)
    count = sum(c["skipped"] for p in people for c in p["changes"]) + sum(g["skipped"] for g in groups)
    hidden = (f"<details class='ignored'><summary>Ignored ({count:,})</summary><p class='muted'>Tick a change "
              f"and press Save choices to bring it back.</p>{''.join(ignored)}</details>" if ignored else "")
    body = "".join(waiting) or "<p class='muted'>Nothing waiting.</p>"
    save = "<div class='row'><button>Save choices</button></div>"
    return (f"<section class='card'><h2>Changes</h2><form method='post' action='review/changes'>{save}"
            f"{body}{hidden}{save}</form></section>")


def _checkbox(change: dict) -> str:
    thumb = f"<img class='thumb' src='thumb/{esc(change['thumb'])}.jpg' alt=''>" if change["thumb"] else ""
    details = (f"<details><summary class='muted'>Details</summary>{esc(change['details'])}</details>"
               if change["details"] else "")
    return (
        f"<li><input type='hidden' name='shown' value='{esc(change['id'])}'><label>"
        f"<input type='checkbox' name='keep' value='{esc(change['id'])}'{'' if change['skipped'] else ' checked'}> "
        f"<span class='muted'>{esc(change['account'])}:</span> {esc(change['text'])}</label>{thumb}{details}</li>"
    )


def _duplicates(items: list[dict]) -> str:
    rows = "".join(f"<li>{esc(d['person'])}: {d['count']} copies in {esc(d['account'])}</li>" for d in items)
    return ("<section class='card'><h2>Duplicates within one account</h2><p class='muted'>Listed for now. "
            f"Applying changes, in a later version, will offer to merge them.</p><ul>{rows}</ul></section>")


def _n(count: int, one: str, many: str = "") -> str:
    return f"{count:,} {one if count == 1 else (many or one + 's')}"
