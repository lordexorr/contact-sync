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


def _link(key: str) -> str:
    return f"contact?person={esc(quote(key, safe=''))}"


# --- The list ---

def contacts_body(rv: dict | None) -> str:
    if rv is None:
        return "<h1>Contacts</h1><p class='muted'>Nothing to show until the first check has run.</p>"
    rows = "".join(_list_row(d) for d in rv["directory"])
    return (
        "<h1>Contacts</h1><div class='row'><a class='button' href='contact/new'>New contact</a></div>"
        "<p><input id='find' type='search' autocomplete='off' placeholder='Search by name, company, phone or email'></p>"
        f"<p class='muted'><span id='shown'>{len(rv['directory']):,}</span> contacts</p>"
        "<div class='scroll'><table class='people'><thead><tr><th>Name</th><th>Company</th><th>Phone</th><th>Email</th>"
        f"<th></th></tr></thead><tbody>{rows}</tbody></table></div><script>{_FIND_SCRIPT}</script>"
    )


def _list_row(d: dict) -> str:
    digits = [re.sub(r"\D", "", p) for p in d["phones"]]
    search = " ".join([d["name"], d["company"], d["nickname"], *d["phones"], *digits, *d["emails"]]).lower()
    status = ("Waiting to be applied" if d["pending"] in ("edit", "new") else "Waiting to be deleted" if d["pending"]
              else "Possible match to answer" if d["held"] else "")
    name = (f"<a href='{_link(d['key'])}'>{esc(d['name'])}</a>" if d["pending"] != "new"
            else f"<a href='apply?person={esc(quote(d['key'], safe=''))}'>{esc(d['name'])}</a>")
    return (f"<tr data-search='{esc(search)}'><td>{name}</td><td>{esc(d['company'])}</td>"
            f"<td>{esc(d['phones'][0]) if d['phones'] else ''}</td><td>{esc(d['emails'][0]) if d['emails'] else ''}</td>"
            f"<td class='muted'>{status}</td></tr>")


# --- One person ---

def contact_body(rv: dict | None, key: str) -> str:
    view = (rv or {}).get("views", {}).get(key)
    if view is None:
        return "<h1>Contact</h1><p class='muted'>This contact is no longer here.</p>"
    photo = f"<img class='thumb' src='thumb/{esc(view['photo'])}.jpg' alt=''>" if view["photo"] else ""
    facts = [("Nickname", view["nickname"]), ("Company", view["company"]), ("Job title", view["title"]),
             ("Birthday", plan.show("birthday", view["birthday"]))]
    rows = "".join(f"<tr><th>{title}</th><td>{esc(value)}</td></tr>" for title, value in facts if value)
    for field, title in LIST_TITLES.items():
        for r in view["lists"][field]:
            shown = plan.show("dates", r["value"]) if field == "dates" else r["value"]
            rows += f"<tr><th>{esc(label_text(r['label']))} · {title}</th><td>{esc(shown)}</td></tr>"
    if view["note"]:
        rows += f"<tr><th>Notes</th><td class='note-text'>{esc(view['note'])}</td></tr>"
    if view["groups"]:
        rows += f"<tr><th>Groups</th><td>{esc(', '.join(view['groups']))}</td></tr>"
    others = [e["text"] for e in view["extras"] if not e["current"]]
    if others:
        rows += ("<tr><th>Only in Google</th><td>" + esc("; ".join(others))
                 + " <a href='review'>Decide in the review</a></td></tr>")
    where = f"In {', '.join(view['in'])}." + (f" Not in {', '.join(view['missing'])}." if view["missing"] else "")
    return (f"<p><a href='contacts'>← Contacts</a></p><h1>{esc(view['display'])}{photo}</h1>"
            "<p class='muted'>What every account will have after the next apply, including anything waiting.</p>"
            f"<div class='scroll'><table class='facts'><tbody>{rows}</tbody></table></div>"
            f"<p class='muted'>{esc(where)}</p>{_actions(rv, key, view)}")


def _actions(rv: dict, key: str, view: dict) -> str:
    if view["held"]:
        return ("<p>This contact is waiting on a possible match. <a href='review'>Answer it in the review</a> first, "
                "so a change can't land on the wrong person.</p>")
    pending = rv["pending"].get(key)
    apply_link = f"<a class='button' href='apply?person={esc(quote(key, safe=''))}'>Apply…</a>"
    if pending == "delete":
        return f"<p>Waiting to be deleted from every account.</p><div class='row'>{apply_link}{review.discard_button(rv, key)}</div>"
    waiting = f"<p>Your edit is waiting to be applied.</p><div class='row'>{apply_link}{review.discard_button(rv, key)}</div>" if pending else ""
    return (f"{waiting}<div class='row'><a class='button{' secondary' if pending else ''}' href='contact/edit?person="
            f"{esc(quote(key, safe=''))}'>Edit</a></div><details class='fold'><summary>Delete everywhere…</summary>"
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
    title = f"Edit {esc(view['display'])}" if view else "New contact"
    faults = "".join(f"<div class='flash error'>{esc(e)}</div>" for e in errors)
    warned = ""
    if similar:
        items = "".join(f"<li><a href='{_link(s['key'])}' target='_blank' rel='noopener'>{esc(s['name'])}</a>: {esc(s['why'])}</li>"
                        for s in similar)
        warned = (f"<div class='flash error'>This may already be in your contacts:<ul>{items}</ul>"
                  "To add it anyway, press <b>Add anyway</b>.</div><input type='hidden' name='confirmed' value='1'>")
    names = "".join(_field(NAME_LABELS[f], f, values["name_parts"][i]) for i, f in enumerate(NAME_FIELDS))
    singles = (_field("Nickname", "nickname", values["nickname"]) + _field("Company", "company", values["company"])
               + _field("Job title", "title", values["title"])
               + _field("Birthday", "birthday", _date_for_form(values["birthday"]), DATE_HINT))
    lists = "".join(_list_section(field, title_, values["lists"][field]) for field, title_ in LIST_TITLES.items())
    choices = "".join(f"<datalist id='labels-{field}'>" + "".join(
        f"<option value='{esc(label_text(o))}'>" for o in plan.LABEL_CHOICES[field]) + "</datalist>" for field in LIST_TITLES)
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
        "<section class='card'><h2>Notes</h2><textarea name='note' rows='5'>"
        f"{esc(values['note'])}</textarea></section>{choices}"
        f"<div class='row'><button>{save}</button><a href='{back}'>Cancel</a></div></form><script>{_FORM_SCRIPT}</script>"
    )


def _empty() -> dict:
    return {"name_parts": [""] * 5, "nickname": "", "company": "", "title": "", "birthday": "", "note": "",
            "lists": {f: [] for f in LIST_TITLES}}


def _field(title: str, name: str, value: str, hint: str = "") -> str:
    placeholder = f" placeholder='{esc(hint)}'" if hint else ""
    return f"<label>{esc(title)}<input type='text' name='{name}' autocomplete='off' value='{esc(value)}'{placeholder}></label>"


def _list_section(field: str, title: str, rows: list[dict]) -> str:
    noun = plan.MULTI[field]
    blank = {"value": "", "label": "", "parts": []}
    body = "".join(_list_row_input(field, r) for r in rows)
    return (f"<h3>{title}</h3><div class='edit-list' data-field='{field}'>{body}</div>"
            f"<template id='row-{field}'>{_list_row_input(field, blank)}</template>"
            f"<div class='row'><button type='button' class='secondary add-row' data-field='{field}'>Add {'an' if noun[0] in 'aeiou' else 'a'} {noun}</button></div>")


def _list_row_input(field: str, r: dict) -> str:
    tag = label_text(r["label"]) if r["label"] else ""
    label_box = (f"<input type='text' class='label-box' name='{field}_label' list='labels-{field}' autocomplete='off' "
                 f"placeholder='Label' value='{esc(tag)}'>")
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
        labels = form.getall(f"{field}_label", [])
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
    if view and view["baseline"]["name"] and not any(entered["name_parts"]):
        errors.append("A name can be changed, but not removed.")
    if errors:
        return {"entered": entered, "errors": errors, "similar": []}
    if view:
        edit = plan.edit_from(view["baseline"], entered)
        review.save_edit(key, edit)
        return {"key": key, "unchanged": not (edit["set"] or edit["lists"])}
    found = plan.similar(rv, entered)
    if found and not form.get("confirmed"):
        return {"entered": entered, "errors": [], "similar": found}
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
document.addEventListener('click', e => {
  const add = e.target.closest('.add-row');
  if (add) {
    const field = add.dataset.field;
    const list = document.querySelector(`.edit-list[data-field="${field}"]`);
    list.appendChild(document.getElementById(`row-${field}`).content.cloneNode(true));
    list.lastElementChild.querySelector('.value-box, textarea').focus();
    return;
  }
  const row = e.target.closest('.edit-row');
  if (!row) return;
  if (e.target.closest('.row-remove')) row.remove();
  else if (e.target.closest('.row-up') && row.previousElementSibling) row.parentNode.insertBefore(row, row.previousElementSibling);
  else if (e.target.closest('.row-down') && row.nextElementSibling) row.parentNode.insertBefore(row.nextElementSibling, row);
});
"""
