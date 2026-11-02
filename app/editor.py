"""The Contacts pages: find a person, see everything on their card, and edit, add or delete. Nothing here writes to
an account. What's entered waits in the decisions until it goes through the review's Apply page, like any change."""
import calendar
import html
import re
from urllib.parse import quote

from . import plan, review
from .model import label_text

esc = html.escape

NAME_FIELDS = ("prefix", "given", "middle", "family", "suffix")
NAME_LABELS = {"prefix": "Prefix", "given": "First name", "middle": "Middle name", "family": "Last name", "suffix": "Suffix"}
PART_FIELDS = ("street", "city", "region", "postcode", "country")
PART_LABELS = {"street": "Street", "city": "City", "region": "State", "postcode": "ZIP", "country": "Country (not for the US)"}
LIST_TITLES = {"phones": "Phone numbers", "emails": "Email addresses", "addresses": "Addresses", "urls": "Websites",
               "related": "Related names", "dates": "Dates"}
DATE_HINT = "8/10/2002, or 8/10 if the year isn't known"
# The label a new row starts on. Related names start with none, since there's no likely one.
NEW_ROW_LABELS = {"phones": "mobile", "emails": "home", "addresses": "home", "urls": "homepage", "dates": "anniversary"}


def _link(key: str) -> str:
    return f"contact?person={esc(quote(key, safe=''))}"


# --- The list ---

def contacts_body(rv: dict | None) -> str:
    if rv is None:
        return "<h1>Contacts</h1><p class='muted'>Nothing to show until the first check has run.</p>"
    rows = "".join(_list_row(d) for d in rv["directory"])
    return (
        f"<h1>Contacts</h1>{_waiting(rv)}<div class='row'><a class='button' href='contact/new'>New contact</a></div>"
        "<p class='muted'>What the accounts hold today. A value only some accounts have says which.</p>"
        "<p><input id='find' type='search' autocomplete='off' placeholder='Search by name, company, phone or email'></p>"
        f"<p class='muted'><span id='shown'>{len(rv['directory']):,}</span> contacts</p>"
        "<div class='scroll'><table class='people'><thead><tr><th>Name</th><th>Company</th><th>Phone</th><th>Email</th>"
        f"<th></th></tr></thead><tbody>{rows}</tbody></table></div><script>{_FIND_SCRIPT}</script>"
    )


def _waiting(rv: dict) -> str:
    """Everything entered here and not applied yet, on top, so nothing's left forgotten."""
    words = {"edit": "Edit", "delete": "Delete", "new": "New contact"}
    items = "".join(
        f"<li class='row'><span><a href='{_link(d['key'])}'>{esc(d['name'])}</a> <span class='muted'>· {words[d['pending']]}"
        f"</span></span><span class='row'><a class='button' href='apply?person={esc(quote(d['key'], safe=''))}'>Apply…</a>"
        f"{review.pending_buttons(rv, d['key'])}</span></li>" for d in rv["directory"] if d["pending"])
    if not items:
        return ""
    return ("<section class='card'><h2>Waiting to be applied</h2><p class='muted'>Entered here, and not written to any "
            f"account yet.</p><ul class='plain'>{items}</ul></section>")


def _lines(items: list[dict]) -> str:
    """Values, one to a line, each with the accounts that have it if that isn't all of them."""
    return "".join(f"<div>{esc(i['text'])}" + (f" <span class='muted where'>{esc(i['where'])}</span>" if i["where"] else "")
                   + "</div>" for i in items)


def _list_row(d: dict) -> str:
    texts = [i["text"] for i in d["phones"]]
    digits = [re.sub(r"\D", "", p) for p in texts]
    search = " ".join([d["name"], d["nickname"], *[i["text"] for i in d["company"]], *texts, *digits, *d["phone_keys"],
                       *[i["text"] for i in d["emails"]]]).lower()
    status = ("Waiting to be applied" if d["pending"] in ("edit", "new") else "Waiting to be deleted" if d["pending"]
              else "Possible match to answer" if d["held"] else "")
    return (f"<tr data-search='{esc(search)}'><td><a href='{_link(d['key'])}'>{esc(d['name'])}</a></td>"
            f"<td>{_lines(d['company'])}</td><td>{_lines(d['phones'])}</td><td>{_lines(d['emails'])}</td>"
            f"<td class='muted'>{status}</td></tr>")


# --- One person ---

def contact_body(rv: dict | None, key: str) -> str:
    view = (rv or {}).get("views", {}).get(key)
    if view is None:
        return "<h1>Contact</h1><p class='muted'>This contact is no longer here.</p>"
    photo = f"<img class='thumb' src='thumb/{esc(view['photo'])}.jpg' alt=''>" if view["photo"] else ""
    total = len(view["in"])

    def value_row(title: str, item: dict, css: str = "") -> str:
        where = (f" <span class='muted where'>{esc(', '.join(item['accounts']))}</span>"
                 if len(item["accounts"]) != total else "")
        return f"<tr><th>{title}</th><td{css}>{esc(item['text'])}{where}</td></tr>"

    single, lists = view["now"]["single"], view["now"]["lists"]
    names = single["name"] if len(single["name"]) > 1 else []  # a name every account agrees on is the heading
    rows = "".join(value_row(title, item) for title, items in (
        ("Name", names), ("Nickname", single["nickname"]), ("Company", single["company"]), ("Job title", single["title"]),
        ("Birthday", single["birthday"])) for item in items)
    for field, title in LIST_TITLES.items():
        rows += "".join(value_row(f"{esc(label_text(i['label']))} · {title}", i) for i in lists[field])
    rows += "".join(value_row("Notes", i, " class='note-text'") for i in single["note"])
    rows += "".join(value_row("Group", i) for i in view["now"]["groups"])
    others =[e["text"] for e in view["extras"] if not e["current"]]
    if others:
        rows += ("<tr><th>Only in Google</th><td>" + esc("; ".join(others))
                 + " <a href='review'>Decide in the review</a></td></tr>")
    if view.get("new"):
        intro, where = "Not in any account yet. This is what you entered.", ""
    else:
        intro = "What the accounts hold today."
        where = f"In {', '.join(view['in'])}." + (f" Not in {', '.join(view['missing'])}." if view["missing"] else "")
    changes = "" if view.get("new") else review.person_changes(rv, key)
    return (f"<p><a href='contacts'>← Contacts</a></p><h1>{esc(view['display'])}{photo}</h1><p class='muted'>{intro}</p>"
            f"<div class='scroll'><table class='facts'><tbody>{rows}</tbody></table></div>"
            + (f"<p class='muted'>{esc(where)}</p>" if where else "") + changes + _actions(rv, key, view))


def _actions(rv: dict, key: str, view: dict) -> str:
    if view["held"]:
        return ("<p>This contact is waiting on a possible match. <a href='review'>Answer it in the review</a> first, "
                "so a change can't land on the wrong person.</p>")
    pending = rv["pending"].get(key)
    apply_link = f"<a class='button' href='apply?person={esc(quote(key, safe=''))}'>Apply…</a>"
    buttons = f"<div class='row'>{apply_link}{review.pending_buttons(rv, key)}</div>"
    if pending == "delete":
        return f"<p>Waiting to be deleted from every account.</p>{buttons}"
    if pending == "new":
        return f"<p>This new contact is waiting to be applied.</p>{buttons}"
    if pending:
        waiting = f"<p>Your edit is waiting to be applied.</p>{buttons}"
    else:
        waiting = (f"<div class='row'><a class='button' href='contact/edit?person={esc(quote(key, safe=''))}'>Edit</a></div>")
    return (f"{waiting}<details class='fold'><summary>Delete everywhere…</summary>"
            f"<p>{esc(view['display'])} would be deleted from {esc(', '.join(view['in']))}. The next page shows the change "
            "before anything is deleted, and a backup is saved first.</p><form method='post' action='contact/delete'>"
            f"<input type='hidden' name='person' value='{esc(key)}'><button class='secondary'>Delete everywhere…</button>"
            "</form></details>")


# --- The form ---

def form_body(rv: dict | None, key: str = "", entered: dict | None = None, errors: tuple = (), similar: tuple = ()) -> str:
    if rv is None:
        return "<h1>Contact</h1><p class='muted'>Nothing to edit until the first check has run.</p>"
    view = rv["views"].get(key) if key else None
    if key and view is None:
        return "<h1>Contact</h1><p class='muted'>This contact is no longer here.</p>"
    if view and view["held"]:
        return f"<h1>{esc(view['display'])}</h1>{_actions(rv, key, view)}"
    values = entered or view or _empty()
    back = _link(key) if key else "contacts"
    title = "New contact" if not view or view.get("new") else f"Edit {esc(view['display'])}"
    faults = "".join(f"<div class='flash error'>{esc(e)}</div>" for e in errors) + _similar_warning(rv, similar)
    warned = "<input type='hidden' name='confirmed' value='1'>" if similar else ""
    names ="".join(_field(NAME_LABELS[f], f, values["name_parts"][i]) for i, f in enumerate(NAME_FIELDS))
    singles = (_field("Nickname", "nickname", values["nickname"]) + _field("Company", "company", values["company"])
               + _field("Job title", "title", values["title"])
               + _field("Birthday", "birthday", _date_for_form(values["birthday"]), DATE_HINT))
    lists = "".join(_list_section(field, title_, values["lists"][field]) for field, title_ in LIST_TITLES.items())
    save = "Add anyway" if similar else "Save…"
    return (
        f"<p><a href='{back}'>← Back</a></p><h1>{title}</h1>{faults}"
        "<p class='muted'>Saving writes nothing to any account. The next page shows what changes in each account, "
        "and <b>Apply now</b> makes the changes.</p>"
        f"<form method='post' action='contact/save' class='edit'>{warned}<input type='hidden' name='person' value='{esc(key)}'>"
        f"<section class='card'><h2>Name</h2><div class='edit-grid'>{names}</div></section>"
        f"<section class='card'><h2>Details</h2><div class='edit-grid'>{singles}</div></section>"
        f"<section class='card'><h2>Phone numbers, addresses and more</h2><p class='muted'>The first in each list is "
        f"the main one. Use the arrows to change the order.</p>{lists}</section>"
        f"{_groups_section(rv, values['groups'])}"
        "<section class='card'><h2>Notes</h2><textarea name='note' rows='5'>"
        f"{esc(values['note'])}</textarea></section>"
        f"<div class='row'><button>{save}</button><a href='{back}'>Cancel</a></div></form><script>{_FORM_SCRIPT}</script>"
    )


def _similar_warning(rv: dict, similar: tuple) -> str:
    """Who this may duplicate. A contact you entered earlier and haven't applied gets a way to change or discard it,
    since it isn't in any account yet."""
    if not similar:
        return ""
    items = ""
    for s in similar:
        if s["unapplied"]:
            items += (f"<li class='row'><span>{esc(s['name'])}: you entered this contact earlier and haven't applied it, "
                      f"with {esc(s['why'])}.</span>{review.pending_buttons(rv, s['key'])}</li>")
        else:
            items += f"<li><a href='{_link(s['key'])}' target='_blank' rel='noopener'>{esc(s['name'])}</a>: {esc(s['why'])}</li>"
    return ("<div class='flash error'>This may already be here:<ul class='plain'>" f"{items}</ul>"
            "To add this one as well, press <b>Add anyway</b>.</div>")


def _empty() -> dict:
    return {"name_parts": [""] * 5, "nickname": "", "company": "", "title": "", "birthday": "", "note": "", "groups": [],
            "lists": {f: [] for f in LIST_TITLES}}


def _groups_section(rv: dict, current: list[str]) -> str:
    """A dropdown per group the person is in, each listing every group, with a last choice for a new one."""
    body = "".join(_group_row(rv, g) for g in current)
    return ("<section class='card'><h2>Groups</h2><p class='muted'>Removing someone from a group never deletes the "
            f"group.</p><div class='edit-list' data-field='groups'>{body}</div><template id='row-groups'>{_group_row(rv, '')}"
            "</template><div class='row'><button type='button' class='secondary add-row' data-field='groups'>Add a group"
            "</button></div></section>")


def _group_row(rv: dict, current: str) -> str:
    choices = list(rv["group_names"])
    if current and current.lower() not in {g.lower() for g in choices}:
        choices.append(current)
    options = "<option value=''>Choose a group</option>" + "".join(
        f"<option value='{esc(g)}'{' selected' if g.lower() == current.lower() else ''}>{esc(g)}</option>" for g in choices)
    return (f"<div class='edit-row'><span class='group-choice'><select class='label-pick' name='groups_name' autocomplete='off'>"
            f"{options}<option value='{review.CUSTOM}'>New group…</option></select><input type='text' class='label-custom' "
            "name='groups_new' autocomplete='off' maxlength='60' placeholder='Name of the new group' hidden></span>"
            "<span class='row-buttons'><button type='button' class='secondary row-remove' title='Remove'>✕</button></span></div>")


def _field(title: str, name: str, value: str, hint: str = "") -> str:
    placeholder = f" placeholder='{esc(hint)}'" if hint else ""
    return f"<label>{esc(title)}<input type='text' name='{name}' autocomplete='off' value='{esc(value)}'{placeholder}></label>"


def _list_section(field: str, title: str, rows: list[dict]) -> str:
    noun = plan.MULTI[field]
    blank = {"value": "", "label": NEW_ROW_LABELS.get(field, ""), "parts": []}
    body ="".join(_list_row_input(field, r) for r in rows)
    return (f"<h3>{title}</h3><div class='edit-list' data-field='{field}'>{body}</div>"
            f"<template id='row-{field}'>{_list_row_input(field, blank)}</template>"
            f"<div class='row'><button type='button' class='secondary add-row' data-field='{field}'>Add {'an' if noun[0] in 'aeiou' else 'a'} {noun}</button></div>")


def _label_box(field: str, tag: str) -> str:
    """The label dropdown: the labels iCloud and Google both have, this value's own if it's another, and Custom…"""
    current = label_text(tag) if tag else ""
    choices = [label_text(o) for o in plan.LABEL_CHOICES[field]]
    if current and current.lower() not in {c.lower() for c in choices}:
        choices.append(current)
    options = "<option value=''>no label</option>" + "".join(
        f"<option value='{esc(c)}'{' selected' if c.lower() == current.lower() else ''}>{esc(c)}</option>" for c in choices)
    return (f"<span class='label-choice'><select class='label-pick' name='{field}_label' autocomplete='off'>{options}"
            f"<option value='{review.CUSTOM}'>Custom…</option></select><input type='text' class='label-custom' "
            f"name='{field}_label_custom' autocomplete='off' maxlength='40' placeholder='Label' hidden></span>")


def _list_row_input(field: str, r: dict) -> str:
    label_box = _label_box(field, r["label"])
    if field == "addresses":
        parts = (list(r["parts"]) + [""] * 5)[:5]
        boxes = (f"<textarea name='addresses_street' rows='2' placeholder='{PART_LABELS['street']}'>{esc(parts[0])}</textarea>"
                 + "".join(f"<input type='text' name='addresses_{f}' autocomplete='off' placeholder='{esc(PART_LABELS[f])}' "
                           f"value='{esc(parts[i + 1])}'>" for i, f in enumerate(PART_FIELDS[1:])))
        value = f"<div class='address-boxes'>{boxes}</div>"
    else:
        shown = _date_for_form(r["value"]) if field == "dates" else r["value"]
        hint = f" placeholder='{esc(DATE_HINT)}'" if field == "dates" else ""
        value = f"<input type='text' class='value-box' name='{field}_value' autocomplete='off' value='{esc(shown)}'{hint}>"
    return (f"<div class='edit-row'>{label_box}{value}<span class='row-buttons'>"
            "<button type='button' class='secondary row-up' title='Move up'>↑</button>"
            "<button type='button' class='secondary row-down' title='Move down'>↓</button>"
            "<button type='button' class='secondary row-remove' title='Remove'>✕</button></span></div>")


# --- Reading the form ---

def read_form(form) -> tuple[dict, list[str]]:
    """What was entered, as every account should hold it, and anything wrong with it."""
    errors = []
    entered = {"name_parts": [plan.tidy_text("name", str(form.get(f, ""))) for f in NAME_FIELDS]}
    for field in ("nickname", "company", "title", "note"):
        entered[field] = plan.tidy_text(field, str(form.get(field, "")))
    entered["birthday"] = _read_date(str(form.get("birthday", "")), "birthday", errors)
    entered["lists"] = {}
    for field in LIST_TITLES:
        rows, seen = [], set()
        custom = form.getall(f"{field}_label_custom", [])
        labels = [str(custom[i]) if tag == review.CUSTOM and i < len(custom) else "" if tag == review.CUSTOM else tag
                  for i, tag in enumerate(form.getall(f"{field}_label", []))]
        if field == "addresses":
            columns = [form.getall(f"addresses_{f}", []) for f in PART_FIELDS]
            typed = [("", str(labels[i]) if i < len(labels) else "", [str(c[i]) if i < len(c) else "" for c in columns])
                     for i in range(len(columns[0]))]
        else:
            values = form.getall(f"{field}_value", [])
            typed = [(str(v), str(labels[i]) if i < len(labels) else "", None) for i, v in enumerate(values)]
        for value, tag, parts in typed:
            if field == "dates" and value.strip():
                value = _read_date(value, "date", errors)
            if field == "emails" and value.strip() and not re.fullmatch(r"[^@\s]+@[^@\s]+", value.strip()):
                errors.append(f"“{value.strip()}” doesn't look like an email address.")
            row = plan.list_value(field, value, tag, parts)
            if row and row["key"] not in seen:
                seen.add(row["key"])
                rows.append(row)
        entered["lists"][field] = rows
    typed = form.getall("groups_new", [])
    groups = {}
    for i, name in enumerate(form.getall("groups_name", [])):
        chosen = (str(typed[i]) if i < len(typed) else "") if name == review.CUSTOM else str(name)
        if chosen := plan.tidy_text("company", chosen):
            groups.setdefault(chosen.lower(), chosen)
    entered["groups"] = list(groups.values())
    if not any(entered["name_parts"]) and not entered["company"]:
        errors.append("Enter a name or a company.")
    return entered, errors


def _read_date(text: str, what: str, errors: list[str]) -> str:
    """A date as stored here: "YYYY-MM-DD", or "--MM-DD" with no year. Takes 8/10/2002, 8/10, 2002-08-10, or --08-10."""
    text = text.strip()
    if not text:
        return ""
    us = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?", text)
    iso = re.fullmatch(r"(\d{4}|-)-(\d{1,2})-(\d{1,2})", text)
    if us:
        month, day, year = int(us[1]), int(us[2]), us[3]
    elif iso:
        month, day, year = int(iso[2]), int(iso[3]), iso[1] if iso[1] != "-" else None
    else:
        errors.append(f"“{text}” isn't a {what} this can read. Use {DATE_HINT}.")
        return ""
    # With no year, February 29 still counts, since it's a real birthday in some years.
    if not 1 <= month <= 12 or not 1 <= day <= calendar.monthrange(int(year) if year else 2000, month)[1]:
        errors.append(f"“{text}” isn't a real date.")
        return ""
    return f"{year or '-'}-{month:02d}-{day:02d}"


def _date_for_form(value: str) -> str:
    if not value:
        return ""
    year, month, day = value.rsplit("-", 2)
    return f"{int(month)}/{int(day)}" + (f"/{year}" if year.isdigit() else "")


def save(options: dict, key: str, form) -> dict:
    """Keep what was entered, ready for its Apply page. {"key"} when it's saved, "unchanged" if nothing differs, or
    {"entered", "errors", "similar"} to show the form again."""
    rv = review.current_plan(options)
    entered, errors = read_form(form)
    view = (rv or {}).get("views", {}).get(key) if key else None
    if rv is None or (key and view is None):
        return {"entered": entered, "errors": ["This contact is no longer here."], "similar": []}
    if view and view["held"]:
        return {"entered": entered, "errors": ["Answer this contact's possible match in the review first."], "similar": []}
    is_new = bool(view and view.get("new"))
    if view and not is_new and view["baseline"]["name"] and not any(entered["name_parts"]):
        errors.append("A name can be changed, but not removed.")
    if errors:
        return {"entered": entered, "errors": errors, "similar": []}
    if view and not is_new:
        edit = plan.edit_from(view["baseline"], entered)
        review.save_edit(key, edit)
        return {"key": key, "unchanged": not (edit["set"] or edit["lists"] or edit.get("groups"))}
    found = plan.similar(rv, entered, key)
    if found and not form.get("confirmed"):
        return {"entered": entered, "errors": [], "similar": found}
    if is_new:
        review.update_new_person(key, plan.new_person(entered))
        return {"key": key, "unchanged": False}
    return {"key": review.add_new_person(plan.new_person(entered)), "unchanged": False}


_FIND_SCRIPT = """
const box = document.getElementById('find');
box.addEventListener('input', () => {
  const words = box.value.toLowerCase().split(/\\s+/).filter(Boolean);
  let shown = 0;
  document.querySelectorAll('tr[data-search]').forEach(row => {
    const text = row.dataset.search;
    const match = words.every(word => {
      const digits = word.replace(/\\D/g, '');
      return text.includes(word) || (digits.length >= 3 && text.includes(digits));
    });
    row.hidden = !match;
    if (match) shown++;
  });
  document.getElementById('shown').textContent = shown.toLocaleString();
});
box.focus();
"""

_FORM_SCRIPT = """
document.addEventListener('change', e => {
  if (!e.target.matches('select.label-pick')) return;
  const box = e.target.nextElementSibling;
  box.hidden = e.target.value !== '__custom__';
  if (!box.hidden) box.focus();
});
document.addEventListener('click', e => {
  const add = e.target.closest('.add-row');
  if (add) {
    const field = add.dataset.field;
    const list = document.querySelector(`.edit-list[data-field="${field}"]`);
    list.appendChild(document.getElementById(`row-${field}`).content.cloneNode(true));
    const row = list.lastElementChild;
    (row.querySelector('.value-box, textarea') || row.querySelector('select')).focus();
    return;
  }
  const row = e.target.closest('.edit-row');
  if (!row) return;
  if (e.target.closest('.row-remove')) row.remove();
  else if (e.target.closest('.row-up') && row.previousElementSibling) row.parentNode.insertBefore(row, row.previousElementSibling);
  else if (e.target.closest('.row-down') && row.nextElementSibling) row.parentNode.insertBefore(row.nextElementSibling, row);
});
"""
