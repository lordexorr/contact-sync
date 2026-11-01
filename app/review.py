"""The review page, and the decisions made on it. Every decision is saved the moment it's made."""
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


def pick(choice_id: str, choice: str) -> None:
    """A value picked for a field that differs between accounts, or a label picked for one value."""
    if choice_id and choice:
        _update(lambda d: d.setdefault("picks", {}).update({choice_id: choice}))


def set_skip(change_id: str, keep: bool) -> None:
    if not change_id:
        return

    def change(d):
        skips = set(d.get("skips", []))
        (skips.discard if keep else skips.add)(change_id)
        d["skips"] = sorted(skips)
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
        "<p class='muted'>Nothing here has been written to any account. Everything you choose is saved as "
        "you click it, and kept for later checks.</p>",
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
    parts.append(f"<div id='toast' class='toast' hidden></div><script>{_SCRIPT}</script>")
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
        pair = esc(s["id"])
        rows.append(
            f"<div class='item'><p class='muted'>{esc(s['reason'])}</p><div class='pair'>{sides}</div><div class='row'>"
            f"<button type='button' class='match' data-pair='{pair}' data-decision='same'>Same person</button>"
            f"<button type='button' class='match secondary' data-pair='{pair}' data-decision='different'>"
            "Different people</button></div></div>"
        )
    return f"<section class='card'><h2>Possible matches ({len(items)})</h2>{''.join(rows)}</section>"


def _conflicts(items: list[dict]) -> str:
    """Values still to decide on top. Until one is picked, nothing is selected and the value that will be used
    is marked, so any click counts as a decision; decided ones sit in a collapsed section below."""
    def row(i: int, c: dict) -> str:
        options = []
        for o in c["options"]:
            picked = c["decided"] and o["key"] == c["chosen"]
            default = "" if c["decided"] or o["key"] != c["chosen"] else (
                "<span class='muted'>· used unless you pick another</span>")
            shown = (f"<img class='thumb' src='thumb/{esc(o['thumb'])}.jpg' alt=''>" if o.get("thumb")
                     else f"<span>{esc(o['value'])}</span>")
            options.append(
                f"<label class='option'><input type='radio' class='pick' name='choice-{i}' "
                f"data-conflict='{esc(c['id'])}' value='{esc(o['key'])}'{' checked' if picked else ''}>"
                f"{shown}<span class='muted'>{esc(', '.join(o['accounts']))}</span>{default}</label>"
            )
        return f"<div class='item'><b>{esc(c['person'])}</b> · {esc(c['field'])}{''.join(options)}</div>"

    waiting = [row(i, c) for i, c in enumerate(items) if not c["decided"]]
    decided = [row(i, c) for i, c in enumerate(items) if c["decided"]]
    folded = (f"<details class='fold'><summary>Decided ({len(decided)})</summary>{''.join(decided)}</details>"
              if decided else "")
    body = "".join(waiting) or "<p class='muted'>Nothing left to decide.</p>"
    return (f"<section class='card'><h2>Different values ({len(waiting)} to decide)</h2><p class='muted'>Pick "
            "the value every account should have.</p>" f"{body}{folded}</section>")


def _changes(people: list[dict], groups: list[dict]) -> str:
    """Changes waiting first; unticked ones in a collapsed Ignored section, where ticking one brings it back."""
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
    folded = (f"<details class='fold'><summary>Ignored ({count:,})</summary><p class='muted'>Tick a change "
              f"to bring it back.</p>{''.join(ignored)}</details>" if ignored else "")
    body = "".join(waiting) or "<p class='muted'>Nothing waiting.</p>"
    return f"<section class='card'><h2>Changes</h2>{body}{folded}</section>"


def _checkbox(change: dict) -> str:
    thumb = f"<img class='thumb' src='thumb/{esc(change['thumb'])}.jpg' alt=''>" if change["thumb"] else ""
    details = (f"<details><summary class='muted'>Details</summary>{esc(change['details'])}</details>"
               if change["details"] else "")
    box = (f"<label><input type='checkbox' class='skip' data-id='{esc(change['id'])}'"
           f"{'' if change['skipped'] else ' checked'}> ")
    if label := change.get("label"):
        # One line for every account that needs the label; the dropdown sits outside the <label> so
        # using it doesn't tick or untick the box.
        options = "".join(f"<option value='{esc(v)}'{' selected' if v == label['chosen'] else ''}>{esc(text)}</option>"
                          for v, text in label["options"])
        return (f"<li>{box}{esc(change['text'])}:</label> <select class='label' data-id='{esc(change['id'])}'>"
                f"{options}</select> <span class='muted'>now {esc(label['now'])}</span></li>")
    return (f"<li>{box}<span class='muted'>{esc(change['account'])}:</span> {esc(change['text'])}</label>"
            f"{thumb}{details}</li>")


def _duplicates(items: list[dict]) -> str:
    rows = "".join(f"<li>{esc(d['person'])}: {d['count']} copies in {esc(d['account'])}</li>" for d in items)
    return ("<section class='card'><h2>Duplicates within one account</h2><p class='muted'>Listed for now. "
            f"Applying changes, in a later version, will offer to merge them.</p><ul>{rows}</ul></section>")


def _n(count: int, one: str, many: str = "") -> str:
    return f"{count:,} {one if count == 1 else (many or one + 's')}"


# Saves each click straight away, then reloads at the same scroll position so handled items move out of the way.
_SCRIPT = """
async function save(url, data) {
  sessionStorage.setItem('reviewScroll', String(window.scrollY));
  let ok = false;
  try { ok = (await fetch(url, {method: 'POST', body: new URLSearchParams(data)})).ok; } catch (err) {}
  sessionStorage.setItem('reviewSaved', ok ? 'ok' : 'error');
  location.reload();
}
document.addEventListener('change', e => {
  const t = e.target;
  if (t.matches('input.skip')) save('review/skip', {id: t.dataset.id, keep: t.checked ? '1' : ''});
  else if (t.matches('select.label')) save('review/label', {id: t.dataset.id, label: t.value});
  else if (t.matches('input.pick')) save('review/pick', {conflict: t.dataset.conflict, choice: t.value});
});
document.addEventListener('click', e => {
  const b = e.target.closest('button.match');
  if (b) { b.disabled = true; save('review/match', {pair: b.dataset.pair, decision: b.dataset.decision}); }
});
window.addEventListener('load', () => {
  const y = sessionStorage.getItem('reviewScroll');
  if (y !== null) { sessionStorage.removeItem('reviewScroll'); window.scrollTo(0, Number(y)); }
  const saved = sessionStorage.getItem('reviewSaved');
  if (saved) {
    sessionStorage.removeItem('reviewSaved');
    const toast = document.getElementById('toast');
    toast.textContent = saved === 'ok' ? 'Saved' : "Couldn't save that. Try again.";
    toast.classList.toggle('error', saved !== 'ok');
    toast.hidden = false;
    setTimeout(() => { toast.hidden = true; }, 2000);
  }
});
"""
