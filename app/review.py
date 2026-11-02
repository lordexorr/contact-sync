"""The review page, the Apply pages, and the decisions made on them. Every decision is saved the moment
it's made."""
import html
import threading
from collections import Counter, defaultdict
from urllib.parse import quote

from . import base, check, plan, storage
from .model import Contact
from .settings import PRIVATE_DIR

DECISIONS_FILE = PRIVATE_DIR / "decisions.json"
CUSTOM = "__custom__"  # the label dropdown's Custom… choice, which is never saved as a label
esc = html.escape
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


def pick(choice_id: str, choice: str, seen: str = "") -> None:
    """A value picked for a field that differs between accounts, or a label picked for one value. seen
    fingerprints what it was picked between (see plan._Picks)."""
    if not (choice_id and choice):
        return

    def change(d):
        d.setdefault("picks", {})[choice_id] = choice
        _note_seen(d.setdefault("pick_seen", {}), choice_id, seen)
    _update(change)


def set_skip(change_id: str, keep: bool, seen: str = "") -> None:
    """Tick or untick a row or a list value. seen fingerprints what an unticked row compares (see plan._Skips)."""
    if not change_id:
        return

    def change(d):
        # "keeps" holds what was ticked again, so a value an account deleted can be kept everywhere instead.
        skips, keeps = set(d.get("skips", [])), set(d.get("keeps", []))
        (skips.discard if keep else skips.add)(change_id)
        (keeps.add if keep else keeps.discard)(change_id)
        d["skips"], d["keeps"] = sorted(skips), sorted(keeps)
        _note_seen(d.setdefault("skip_seen", {}), change_id, "" if keep else seen)
    _update(change)


def keep_unticked(row_ids: list[str]) -> None:
    """Leave these rows unticked from now on."""
    if row_ids:
        _update(lambda d: d.update(skips=sorted(set(d.get("skips", [])) | set(row_ids))))


def reset() -> None:
    _update(lambda d: d.clear())


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


# --- HTML ---

def summary_card(review: dict | None, last_apply: str = "") -> str:
    head = "<section class='card'><h2>Review</h2>"
    if review is None:
        return head + "<p class='muted'>Nothing to review until the first check has run.</p>" + last_apply + "</section>"
    if any(review["counts"].values()):
        body = f"<p>{_counts_line(review['counts'])}</p>"
    else:
        # The review stays open even with nothing waiting, so ignored rows and past answers can be changed.
        ignored = (sum(r["skipped"] for p in review["people"] for r in p["rows"])
                   + sum(r["skipped"] for r in review["groups"]))
        decided = (sum(c["decided"] for c in review["conflicts"]) + len(review["decided_matches"])
                   + sum(bool(d["choice"]) for d in review["duplicates"])
                   + sum(d["complete"] for d in review.get("extras", [])))
        kept = " and ".join(filter(None, (f"{ignored:,} ignored" if ignored else "",
                                          f"{decided:,} decided" if decided else "")))
        matches = "Every account that could be read matches." if review.get("unread") else "Every account matches."
        body = (f"<p class='ok'>{matches} There's nothing to sync.</p>"
                + (f"<p class='muted'>{kept}, under Open the review.</p>" if kept else ""))
    return (head + body + "<div class='row'><a class='button' href='review'>Open the review</a></div>"
            + last_apply + "</section>")


def page_body(review: dict | None) -> str:
    if review is None:
        return "<h1>Review</h1><p class='muted'>Nothing to review until the first check has run.</p>"
    parts = [
        "<h1>Review</h1>",
        "<p class='muted'>Nothing is written to any account until you apply. Everything you choose is saved as "
        "you click it, and kept for later checks.</p>",
        f"<p>{_counts_line(review['counts'])}</p>",
    ]
    parts += [f"<div class='flash error'>{esc(w)}</div>" for w in review["warnings"]]
    if review["suggestions"] or review["decided_matches"]:
        parts.append(_suggestions(review["suggestions"], review["decided_matches"]))
    if review["duplicates"]:
        parts.append(_duplicates(review["duplicates"]))
    if review["extras"]:
        parts.append(_extras(review["extras"]))
    if review["conflicts"]:
        parts.append(_conflicts(review["conflicts"]))
    if review["people"] or review["groups"]:
        parts.append(_changes(review))
    if not plan.is_empty(plan.scope(review)):  # at the end, where the review finishes
        parts.append("<div class='row'><a class='button' href='apply'>Apply changes…</a></div>")
    parts.append(
        "<section class='card'><h2>Start over</h2><p class='muted'>Forget every match, choice and skip "
        "made on this page.</p><details class='fold'><summary>Forget my decisions…</summary>"
        "<p>Every row you unticked comes back ticked, every possible match is asked again, and every value "
        "you picked goes back to the one marked. Nothing is written to any account until you apply.</p>"
        "<form method='post' action='review/reset'><button class='secondary'>Yes, forget my decisions</button>"
        "</form></details></section>"
    )
    parts.append(f"<div id='toast' class='toast' hidden></div><script>{_SCRIPT}</script>")
    return "".join(parts)


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
    return " · ".join(parts)


def _copy(c: dict, heading: str) -> str:
    """One copy of a contact, with everything it holds, for the side-by-side cards."""
    return (f"<div><div class='muted'>{esc(heading)}</div><b>{esc(c['name'])}</b>"
            + (f"<img class='thumb' src='thumb/{esc(c['thumb'])}.jpg' alt=''>" if c["thumb"] else "")
            + "".join(f"<div>{esc(line)}</div>" for line in c["lines"])
            + (f"<div class='muted'>{esc(c['updated'])}</div>" if c["updated"] else "")
            + "</div>")


def _suggestions(items: list[dict], decided: list[dict]) -> str:
    """Pairs still to answer on top; answered ones in a collapsed section, where the answer can be changed."""
    labels = {"same": "Same person", "different": "Different people"}
    rows = []
    for s in items:
        sides = "".join(_copy(c, c["account"]) for c in s["contacts"])
        pair = esc(s["id"])
        rows.append(
            f"<div class='item'><p class='muted'>{esc(s['reason'])}</p><div class='pair'>{sides}</div><div class='row'>"
            f"<button type='button' class='match' data-pair='{pair}' data-decision='same'>Same person</button>"
            f"<button type='button' class='match secondary' data-pair='{pair}' data-decision='different'>"
            "Different people</button></div></div>"
        )
    answered = []
    for s in decided:
        sides = "".join(_copy(c, c["account"]) for c in s["contacts"])
        other = "different" if s["decision"] == "same" else "same"
        answered.append(
            f"<div class='item'><div class='pair'>{sides}</div><div class='row'><span class='muted'>You said: "
            f"{labels[s['decision']]}.</span><button type='button' class='match secondary' data-pair='{esc(s['id'])}' "
            f"data-decision='{other}'>Change to {labels[other]}</button></div></div>"
        )
    folded = (f"<details class='fold'><summary>Decided ({len(answered)})</summary>{''.join(answered)}</details>"
              if answered else "")
    body = "".join(rows) or "<p class='muted'>Nothing left to decide.</p>"
    return f"<section class='card'><h2>Possible matches ({len(items)} to decide)</h2>{body}{folded}</section>"


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
                f"<label class='option'><input type='radio' class='pick' autocomplete='off' name='choice-{i}' "
                f"data-conflict='{esc(c['id'])}' data-seen='{esc(c['seen'])}' value='{esc(o['key'])}'"
                f"{' checked' if picked else ''}>"
                f"{shown}<span class='muted'>{esc(', '.join(o['accounts']))}</span>{default}</label>"
            )
        waits = ("<p class='muted'>Until you choose, every account keeps its own order.</p>"
                 if c.get("required") and not c["decided"] else "")
        return f"<div class='item'><b>{esc(c['person'])}</b> · {esc(c['field'])}{''.join(options)}{waits}</div>"

    waiting = [row(i, c) for i, c in enumerate(items) if not c["decided"]]
    decided = [row(i, c) for i, c in enumerate(items) if c["decided"]]
    folded = (f"<details class='fold'><summary>Decided ({len(decided)})</summary>{''.join(decided)}</details>"
              if decided else "")
    body = "".join(waiting) or "<p class='muted'>Nothing left to decide.</p>"
    return (f"<section class='card'><h2>Different values ({len(waiting)} to decide)</h2><p class='muted'>Pick "
            "the value every account should have.</p>" f"{body}{folded}</section>")


def _changes(review: dict) -> str:
    """A comparison table per person, and one for groups. Rows still waiting first; unticked rows in a
    collapsed Ignored section, where ticking one brings it back."""
    columns = review["columns"]

    def tables(skipped: bool) -> list[str]:
        out = [_table(p["name"], columns, [r for r in p["rows"] if r["skipped"] == skipped],
                      "" if skipped else _person_footer(review, p)) for p in review["people"]]
        out.append(_table("Groups", columns, [r for r in review["groups"] if r["skipped"] == skipped]))
        return [t for t in out if t]

    waiting, ignored = tables(False), tables(True)
    count = sum(r["skipped"] for p in review["people"] for r in p["rows"]) + sum(r["skipped"] for r in review["groups"])
    legend = (
        "<p class='muted'>Each table shows what every account has now, and in the green last column what all of "
        "them will have after the sync. Struck-through values would be replaced or removed, and values marked + "
        "would be added. Untick a row to leave every account as it is. In a list, untick a value to leave it out "
        "of every account.</p><p class='muted'>Something deleted from one account since the last sync is "
        "deleted from the others too. In a list such a value starts unticked: tick it to keep it everywhere "
        "instead.</p>"
    )
    folded = (f"<details class='fold'><summary>Ignored ({count:,})</summary><p class='muted'>Tick a row "
              f"to bring it back.</p>{''.join(ignored)}</details>" if ignored else "")
    body = "".join(waiting) or "<p class='muted'>Nothing waiting.</p>"
    return f"<section class='card'><h2>Changes</h2>{legend}{body}{folded}</section>"


def _person_footer(review: dict, person: dict) -> str:
    if person["held"]:
        return "<p class='muted'>Waiting on a possible match above. Answer it to apply this person's changes.</p>"
    if plan.is_empty(plan.scope(review, person["key"])):
        return ""
    return (f"<div class='row'><a class='button secondary' href='apply?person={esc(quote(person['key'], safe=''))}'>"
            f"Apply just {esc(person['name'])}…</a></div>")


def _table(title: str, columns: list[str], rows: list[dict], footer: str = "") -> str:
    if not rows:
        return ""
    head = "".join(f"<th>{esc(c)}</th>" for c in columns)
    body = "".join(_row(r, columns) for r in rows)
    return (f"<div class='item'><b>{esc(title)}</b><div class='scroll'><table class='compare'><thead><tr><th></th>"
            f"{head}<th>After sync</th></tr></thead><tbody>{body}</tbody></table></div>{footer}</div>")


def _row(row: dict, columns: list[str]) -> str:
    # autocomplete=off on every control: otherwise Firefox restores ticks by position after the reload, and a
    # row that moved to Ignored hands its unticked look to the row that took its place.
    box = (f"<label><input type='checkbox' class='skip' autocomplete='off' data-id='{esc(row['id'])}' "
           f"data-seen='{esc(row['seen'])}'{'' if row['skipped'] else ' checked'}> {esc(row['title'])}</label>")
    cells = "".join(f"<td>{_cell(row['cells'].get(c, []))}</td>" for c in columns)
    return f"<tr><th>{box}</th>{cells}<td class='after'>{_after(row['after'])}</td></tr>"


def _cell(items: list[dict]) -> str:
    """An account's current values: struck through when the sync replaces or removes them ("old"), "+" for
    values it would gain ("new"), "−" for members a group would lose ("gone"), a note on an empty cell the
    sync would fill ("add"), and plain notes ("note")."""
    out = []
    for i in items:
        state = i.get("state", "")
        if "thumb" in i:
            out.append(_thumb(i["thumb"], state))
        elif state == "old":
            out.append(f"<div class='old'>{esc(i['text'])}</div>")
        elif state == "new":
            out.append(f"<div class='new'>+ {esc(i['text'])}</div>")
        elif state == "gone":
            out.append(f"<div class='gone'>− {esc(i['text'])}</div>")
        elif state == "note":
            out.append(f"<div class='muted'>{esc(i['text'])}</div>")
        elif state == "add":
            out.append(f"<div>{esc(i['text'])} <span class='new'>· will be added</span></div>")
        else:
            out.append(f"<div>{esc(i['text'])}</div>")
    return "".join(out)


def _after(after: dict) -> str:
    kind = after["kind"]
    if kind == "photo":
        return _thumb(after["thumb"])
    if kind == "values":
        # One box per value: unticked means every account ends up without it.
        return "".join(
            f"<label class='value'><input type='checkbox' class='skip' autocomplete='off' data-id='{esc(i['id'])}'"
            f"{' checked' if i['kept'] else ''}> {esc(i['text'])}</label>"
            + (f"<div class='muted note'>{esc(i['note'])}</div>" if i.get("note") else "")
            for i in after["items"]
        )
    if kind == "label":
        # Custom… opens a box for typing any label; iCloud and Google both keep custom labels as typed.
        options = "".join(f"<option value='{esc(v)}'{' selected' if v == after['chosen'] else ''}>{esc(text)}</option>"
                          for v, text in after["options"]) + f"<option value='{CUSTOM}'>Custom…</option>"
        seen = esc(after["seen"])
        return (f"<select class='label' autocomplete='off' data-id='{esc(after['id'])}' data-seen='{seen}'>{options}</select>"
                "<span class='custom' hidden><input type='text' autocomplete='off' maxlength='40' placeholder='Label'>"
                f"<button type='button' class='custom-save' data-id='{esc(after['id'])}' data-seen='{seen}'>Save</button></span>")
    details = (f"<details><summary class='muted'>Details</summary>{esc(after['details'])}</details>"
               if after.get("details") else "")
    return f"<div>{esc(after['value'])}</div>{details}"


def _thumb(fingerprint: str, extra_class: str = "") -> str:
    return f"<img class='thumb {extra_class}' src='thumb/{esc(fingerprint)}.jpg' alt=''>"


def _duplicates(items: list[dict]) -> str:
    """People with more than one card in the same account. Undecided ones on top; decided ones in a collapsed
    section, where the other choice is still a click away."""
    def card(d: dict) -> str:
        sides = "".join(_copy(c, "Kept if merged" if c["kept"] else "Another card") for c in d["copies"])
        buttons = "".join(
            f"<button type='button' class='dup{'' if value == 'merge' else ' secondary'}' data-id='{esc(d['id'])}' "
            f"data-decision='{value}'>{text}</button>"
            for value, text in (("merge", "Merge into one"), ("keep", "Keep both")) if value != d["choice"])
        chosen = {"merge": "Merging into one card.", "keep": "Keeping every card."}.get(d["choice"], "")
        return (f"<div class='item'><b>{esc(d['person'])}</b> · {len(d['copies'])} cards in {esc(d['account'])}"
                f"<div class='pair'>{sides}</div><div class='row'>"
                + (f"<span class='muted'>{chosen}</span>" if chosen else "") + f"{buttons}</div></div>")

    waiting = [card(d) for d in items if not d["choice"]]
    decided = [card(d) for d in items if d["choice"]]
    folded = (f"<details class='fold'><summary>Decided ({len(decided)})</summary>{''.join(decided)}</details>"
              if decided else "")
    body = "".join(waiting) or "<p class='muted'>Nothing left to decide.</p>"
    return ("<section class='card'><h2>Duplicates within one account " f"({len(waiting)} to decide)</h2>"
            "<p class='muted'>The same person more than once in one account. <b>Merge into one</b> moves "
            "everything from the other cards onto the one with the most details, including details Contact "
            "Sync doesn't otherwise use, then deletes the others when you apply. <b>Keep both</b> leaves them "
            f"as they are. Until you choose, applying leaves the extra cards alone.</p>{body}{folded}</section>")


def _extras(items: list[dict]) -> str:
    """Details only Google can hold. Each has to be decided, with nothing chosen for you except that the company
    every account already shows stays the main one. People still to decide on top; decided ones collapsed below."""
    def card(d: dict) -> str:
        rows = []
        for e in d["entries"]:
            options = [("main", "Main company")] if e["kind"] == "company" else []
            options += [("notes", "Move to Notes"), ("delete", "Delete")]
            boxes = "".join(
                f"<label class='option'><input type='radio' class='extra' autocomplete='off' name='{esc(e['id'])}' "
                f"data-id='{esc(e['id'])}' value='{value}'{' checked' if e['choice'] == value else ''}> {text}</label>"
                for value, text in options)
            where = "Every account" if e["current"] else f"Only in {', '.join(e['accounts'])}"
            rows.append(f"<tr><td>{esc(e['text'])}<div class='muted'>{esc(where)}</div></td><td>{boxes}</td></tr>")
        return (f"<div class='item'><b>{esc(d['person'])}</b><div class='scroll'><table><tbody>{''.join(rows)}"
                "</tbody></table></div></div>")

    waiting = [card(d) for d in items if not d["complete"]]
    decided = [card(d) for d in items if d["complete"]]
    folded = (f"<details class='fold'><summary>Decided ({len(decided)})</summary>{''.join(decided)}</details>"
              if decided else "")
    body = "".join(waiting) or "<p class='muted'>Nothing left to decide.</p>"
    return (f"<section class='card'><h2>Details only Google can hold ({len(waiting)} to decide)</h2><p class='muted'>"
            "iCloud has room for one company and job title and no location. For each person, choose the main "
            "company, which every account will show, and move each other detail to Notes or delete it. Until "
            f"everything about a person is chosen, these details stay as they are.</p>{body}{folded}</section>")


def apply_body(review: dict | None, person: str | None, checking: bool) -> str:
    """The page before applying: what changes in each account, and the Apply now button."""
    if review is None:
        return "<h1>Apply changes</h1><p class='muted'>Nothing to apply until the first check has run.</p>"
    people = review["sync"]["people"]
    heading = f"<h1>Apply {esc(people[person]['name'])}</h1>" if person in people else "<h1>Apply changes</h1>"
    work = plan.scope(review, person)
    notes = list(review["warnings"])
    if person is None and (held := plan.held_back(review)):
        notes.append(f"{_n(held, 'person', 'people')} waiting on a possible match {'is' if held == 1 else 'are'} "
                     "left out until you answer it in the review.")
    elif person in people and people[person]["held"]:
        notes.append("This person is waiting on a possible match. Answer it in the review first.")
    undecided = sum(not c["decided"] and not c.get("required") and (person is None or c["id"].startswith(person + "|"))
                    for c in review["conflicts"])
    if undecided and not plan.is_empty(work):
        notes.append(f"{_n(undecided, 'value')} between accounts {'hasn' if undecided == 1 else 'haven'}'t been "
                     "picked. The value marked in the review is used.")
    orders = sum(not c["decided"] and bool(c.get("required")) and (person is None or c["id"].startswith(person + "|"))
                 for c in review["conflicts"])
    if orders and not plan.is_empty(work):
        notes.append(f"{_n(orders, 'list')} {'hasn' if orders == 1 else 'haven'}'t had an order chosen. Every account "
                     "keeps its own order until you choose.")
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
    notes_html = "".join(f"<p class='muted'>{esc(n)}</p>" for n in notes)
    back = "<a href='review'>Back to the review</a>"
    if plan.is_empty(work):
        return f"{heading}{notes_html}<p>Nothing to apply.</p><p>{back}</p>"
    if checking:
        return f"{heading}<p class='muted'>A check is running. This page is ready once it finishes.</p>"
    return (
        f"{heading}{_totals(work, person in people)}{notes_html}{_steps(person in people)}"
        "<form method='post' action='apply' onsubmit=\"this.querySelector('button').disabled=true\">"
        f"<input type='hidden' name='person' value='{esc(person or '')}'>"
        f"<input type='hidden' name='token' value='{plan.digest(work)}'>"
        f"<div class='row'><button>Apply now</button>{back}</div></form>"
    )


def result_body(result: dict | None, progress, when) -> str:
    """While applying, how far it has got; afterwards, every change made and every one that failed."""
    if progress is not None:
        count = f" · {progress.done:,} of {progress.total:,}" if progress.total else ""
        return (f"<h1>Applying changes…</h1><p>{esc(progress.step)}{count}</p>"
                "<p class='muted'>This page updates itself. Leaving it doesn't stop anything.</p>")
    if not result:
        return "<h1>Apply</h1><p class='muted'>Nothing has been applied yet.</p>"
    title = {"done": "Applied", "stopped": "Stopped", "failed": "Apply failed"}[result["status"]]
    who = f" {esc(result['person'])}" if result["person"] else ""
    parts = [f"<h1>{title}{who}</h1>", f"<p class='muted'>{esc(when(result['finished_at']))}</p>"]
    if result["message"]:
        parts.append(f"<p class='{'muted' if result['status'] == 'done' else 'bad'}'>{esc(result['message'])}</p>")
    if result["backup"]:
        parts.append("<p class='muted'>Backed up first to <code>addon_configs/local_contact_sync/backups/"
                     f"{esc(result['backup'])}</code>.</p>")
    failed = [c for c in result["changes"] if c["error"]]
    made = [c for c in result["changes"] if not c["error"]]
    if failed:
        parts.append(f"<section class='card'><h2>Not made ({len(failed):,})</h2>{_change_table(failed)}</section>")
    if made:
        check = sum(bool(c.get("warning")) for c in made)
        note = f" · {check:,} to check" if check else ""
        parts.append(f"<section class='card'><h2>Made ({len(made):,}{note})</h2>{_change_table(made)}</section>")
    parts.append("<div class='row'><a class='button' href='review'>Open the review</a></div>")
    return "".join(parts)


def _steps(one_person: bool) -> str:
    if one_person:
        read = ("Reads this person's cards again, and stops without writing anything if anything about them "
                "changed since this page opened.")
        backup = "Backs up their cards to a folder named after them"
        record = "Reads their cards again and records what each account holds"
    else:
        read = "Checks every account again, and stops without writing anything if something changed since this page opened."
        backup = "Backs up every account"
        record = "Checks again and records what every account holds"
    return (
        f"<p>When you press <b>Apply now</b>, Contact Sync:</p><ol><li>{read}</li>"
        f"<li>{backup} in <code>addon_configs/local_contact_sync/backups</code>, with a <code>What changed.txt</code> "
        "file listing every change. The last 10 backups of this kind are kept.</li>"
        "<li>Makes these changes. Only the details shown in the review are touched; everything else on each contact "
        "stays as it is.</li>"
        f"<li>{record}, so later reviews can tell a deletion from a detail that was never synced.</li></ol>"
    )


def _totals(work: dict, one_person: bool) -> str:
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
        rows.append(f"<tr><td>{esc(name)}</td>" + "".join(f"<td class='num'>{c[k]:,}</td>" for k in
                                                          ("added", "updated", "deleted"))
                    + f"<td>{esc(groups) or '–'}</td><td>{esc(members) or '–'}</td></tr>")
    return ("<div class='scroll'><table><thead><tr><th>Account</th><th class='num'>Contacts added</th>"
            "<th class='num'>Updated</th><th class='num'>Deleted</th><th>Groups</th><th>Group members</th></tr>"
            f"</thead><tbody>{''.join(rows)}</tbody></table></div>")


def _change_table(changes: list[dict]) -> str:
    """Changes in a table, with a last column for why one wasn't made, or for something to check about one
    that was."""
    notes = any(c["error"] or c.get("warning") for c in changes)
    head = ("<th>Account</th><th>Contact or group</th><th>Change</th>"
            + (f"<th>{'Why not' if any(c['error'] for c in changes) else 'Check'}</th>" if notes else ""))
    rows = "".join(
        f"<tr><td>{esc(c['account'])}</td><td>{esc(c['subject'])}</td><td>{esc(c['what'])}</td>"
        + (f"<td class='bad'>{esc(c['error'] or c.get('warning', ''))}</td>" if notes else "") + "</tr>"
        for c in changes
    )
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>"


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
  if (t.matches('input.skip')) save('review/skip', {id: t.dataset.id, keep: t.checked ? '1' : '', seen: t.dataset.seen || ''});
  else if (t.matches('select.label')) {
    const box = t.nextElementSibling;
    if (t.value === '__custom__') { box.hidden = false; box.querySelector('input').focus(); }
    else { box.hidden = true; save('review/label', {id: t.dataset.id, label: t.value, seen: t.dataset.seen}); }
  }
  else if (t.matches('input.pick')) save('review/pick', {conflict: t.dataset.conflict, choice: t.value, seen: t.dataset.seen});
  else if (t.matches('input.extra')) save('review/extra', {id: t.dataset.id, choice: t.value});
});
document.addEventListener('click', e => {
  const b = e.target.closest('button.match');
  if (b) { b.disabled = true; save('review/match', {pair: b.dataset.pair, decision: b.dataset.decision}); }
  const d = e.target.closest('button.dup');
  if (d) { d.disabled = true; save('review/duplicate', {id: d.dataset.id, decision: d.dataset.decision}); }
  const c = e.target.closest('button.custom-save');
  if (c) {
    const label = c.previousElementSibling.value.trim();
    if (label) { c.disabled = true; save('review/label', {id: c.dataset.id, label: label, seen: c.dataset.seen}); }
  }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.matches('.custom input')) { e.preventDefault(); e.target.nextElementSibling.click(); }
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
