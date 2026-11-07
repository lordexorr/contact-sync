"""The Contacts pages: find a person, see everything on their card, and edit, add or delete. Nothing here writes to
an account. What's entered waits in the decisions until it goes through the review's Apply page, like any change."""
import calendar
import re

from . import plan, review
from .model import label_text

NAME_FIELDS = ("prefix", "given", "middle", "family", "suffix")
NAME_LABELS = {"prefix": "Prefix", "given": "First name", "middle": "Middle name", "family": "Last name", "suffix": "Suffix"}
PART_FIELDS = ("street", "city", "region", "postcode", "country")
PART_LABELS = {"street": "Street", "city": "City", "region": "State", "postcode": "ZIP", "country": "Country (not for the US)"}
LIST_TITLES = {"phones": "Phone numbers", "emails": "Email addresses", "addresses": "Addresses", "urls": "Websites",
               "related": "Related names", "dates": "Dates"}
DATE_HINT = "8/10/2002, or 8/10 if the year isn't known"
# The label a new row starts on. Related names start with none, since there's no likely one.
NEW_ROW_LABELS = {"phones": "mobile", "emails": "home", "addresses": "home", "urls": "homepage", "dates": "anniversary"}


# --- The list ---

def contacts_data(rv: dict | None) -> dict | None:
    """The Contacts list, with everything entered here and not applied yet on top, so nothing's left forgotten.
    None before the first check."""
    if rv is None:
        return None
    return {"waiting": [{"key": d["key"], "name": d["name"], "pending": d["pending"]} for d in rv["directory"] if d["pending"]],
            "people": [_list_row(d) for d in rv["directory"]]}


def _list_row(d: dict) -> dict:
    """One line of the list. Each value says which accounts have it if that isn't all of them; search finds phone
    numbers by their digits too."""
    texts = [i["text"] for i in d["phones"]]
    digits = [re.sub(r"\D", "", p) for p in texts]
    search = " ".join([d["name"], d["nickname"], *[i["text"] for i in d["company"]], *texts, *digits, *d["phone_keys"],
                       *[i["text"] for i in d["emails"]]]).lower()
    status = ("Waiting to be applied" if d["pending"] in ("edit", "new") else "Waiting to be deleted" if d["pending"]
              else "Possible match to answer" if d["held"] else "")
    return {"key": d["key"], "name": d["name"], "company": d["company"], "phones": d["phones"], "emails": d["emails"],
            "status": status, "search": search}


# --- One person ---

def contact_data(rv: dict | None, key: str) -> dict | None:
    """Everything on a person's card, as the accounts hold it today; None if they're no longer here."""
    view = (rv or {}).get("views", {}).get(key)
    if view is None:
        return None
    total = len(view["in"])

    def value_row(title: str, item: dict, note: bool = False) -> dict:
        where = ", ".join(item["accounts"]) if len(item["accounts"]) != total else ""
        return {"title": title, "text": item["text"], "where": where, "note": note}

    single, lists = view["now"]["single"], view["now"]["lists"]
    names = single["name"] if len(single["name"]) > 1 else []  # a name every account agrees on is the heading
    rows = [value_row(title, item) for title, items in (
        ("Name", names), ("Nickname", single["nickname"]), ("Company", single["company"]), ("Job title", single["title"]),
        ("Birthday", single["birthday"])) for item in items]
    for field, title in LIST_TITLES.items():
        rows += [value_row(f"{label_text(i['label'])} · {title}", i) for i in lists[field]]
    rows += [value_row("Notes", i, note=True) for i in single["note"]]
    rows += [value_row("Group", i) for i in view["now"]["groups"]]
    new = bool(view.get("new"))
    if new:
        intro, where = "Not in any account yet. This is what you entered.", ""
    else:
        intro = "What the accounts hold today."
        where = f"In {', '.join(view['in'])}." + (f" Not in {', '.join(view['missing'])}." if view["missing"] else "")
    return {"key": key, "name": view["display"], "thumb": view["photo"], "intro": intro, "where": where, "rows": rows,
            "google_only": "; ".join(e["text"] for e in view["extras"] if not e["current"]),
            "columns": rv["columns"], "changes": [] if new else review.person_changes(rv, key),
            "held": view["held"], "new": new, "pending": rv["pending"].get(key, ""),
            "delete": f"{view['display']} would be deleted from {', '.join(view['in'])}. The next page shows the change "
                      "before anything is deleted, and a backup is saved first."}


# --- The form ---

def form_data(rv: dict | None, key: str = "", entered: dict | None = None, errors: tuple = (),
              similar: tuple = ()) -> dict | None:
    """A contact's form: filled in with what the accounts hold, with what was entered, or empty for a new contact.
    None before the first check; {"missing"} or {"held"} when the contact can't be edited."""
    if rv is None:
        return None
    view = rv["views"].get(key) if key else None
    if key and view is None:
        return {"missing": True}
    if view and view["held"]:
        return {"held": True, "name": view["display"]}
    return {
        "key": key, "title": "New contact" if not view or view.get("new") else f"Edit {view['display']}",
        "errors": list(errors),
        # A contact entered earlier and not applied gets a way to change or discard it, since it isn't in any account.
        "similar": [{**s, "pending": rv["pending"].get(s["key"], "")} for s in similar],
        "values": _values(entered or view or _empty()),
        "group_names": rv["group_names"],
        # The labels iCloud and Google both have; a value's own label, if it's another, is added to its dropdown.
        "labels": {f: [label_text(o) for o in plan.LABEL_CHOICES[f]] for f in LIST_TITLES},
        "new_row_labels": {f: label_text(NEW_ROW_LABELS[f]) if f in NEW_ROW_LABELS else "" for f in LIST_TITLES},
        "layout": {"names": [[f, NAME_LABELS[f]] for f in NAME_FIELDS], "parts": [[f, PART_LABELS[f]] for f in PART_FIELDS],
                   "lists": [[f, title, plan.MULTI[f]] for f, title in LIST_TITLES.items()], "date_hint": DATE_HINT},
    }


def _empty() -> dict:
    return {"name_parts": [""] * 5, "nickname": "", "company": "", "title": "", "birthday": "", "note": "", "groups": [],
            "lists": {f: [] for f in LIST_TITLES}}


def _values(values: dict) -> dict:
    """What a form's boxes hold, the shape read_form takes back: labels as shown, dates as typed, and five boxes
    for each address."""
    return {"name_parts": list(values["name_parts"]), "nickname": values["nickname"], "company": values["company"],
            "title": values["title"], "birthday": _date_for_form(values["birthday"]), "note": values["note"],
            "groups": list(values["groups"]),
            "lists": {f: [{"label": label_text(r["label"]) if r["label"] else "",
                           "value": "" if f == "addresses" else _date_for_form(r["value"]) if f == "dates" else r["value"],
                           "parts": (list(r["parts"]) + [""] * 5)[:5] if f == "addresses" else []}
                          for r in values["lists"][f]] for f in LIST_TITLES}}


# --- Reading the form ---

def read_form(raw: dict) -> tuple[dict, list[str]]:
    """What was entered, as every account should hold it, and anything wrong with it. raw is shaped like
    form_data's "values", with each label as chosen or typed."""
    errors = []
    entered = {"name_parts": [plan.tidy_text("name", str(p)) for p in (list(raw.get("name_parts") or []) + [""] * 5)[:5]]}
    for field in ("nickname", "company", "title", "note"):
        entered[field] = plan.tidy_text(field, str(raw.get(field, "")))
    entered["birthday"] = _read_date(str(raw.get("birthday", "")), "birthday", errors)
    entered["lists"] = {}
    for field in LIST_TITLES:
        rows, seen = [], set()
        for typed in (raw.get("lists") or {}).get(field, []):
            tag = str(typed.get("label", "")).strip()[:40]
            if field == "addresses":
                value, parts = "", [str(p) for p in (list(typed.get("parts") or []) + [""] * 5)[:5]]
            else:
                value, parts = str(typed.get("value", "")), None
            if field == "dates" and value.strip():
                value = _read_date(value, "date", errors)
            if field == "emails" and value.strip() and not re.fullmatch(r"[^@\s]+@[^@\s]+", value.strip()):
                errors.append(f"“{value.strip()}” doesn't look like an email address.")
            row = plan.list_value(field, value, tag, parts)
            if row and row["key"] not in seen:
                seen.add(row["key"])
                rows.append(row)
        entered["lists"][field] = rows
    groups = {}
    for name in raw.get("groups") or []:
        if chosen := plan.tidy_text("company", str(name)):
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


def save(options: dict, key: str, raw: dict) -> dict:
    """Keep what was entered, ready for its Apply page. {"key"} when it's saved, "unchanged" if nothing differs, or
    {"entered", "errors", "similar"} to show the form again."""
    rv = review.current_plan(options)
    entered, errors = read_form(raw)
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
    if found and not raw.get("confirmed"):
        return {"entered": entered, "errors": [], "similar": found}
    if is_new:
        review.update_new_person(key, plan.new_person(entered))
        return {"key": key, "unchanged": False}
    return {"key": review.add_new_person(plan.new_person(entered)), "unchanged": False}
