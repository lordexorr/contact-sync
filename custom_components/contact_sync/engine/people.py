"""Reading and writing Google contacts."""
from .model import LABEL_NAMES, Contact, Value, address_key, date_key, email_key, fold, label, phone_key, url_key

NAME_KEYS = ("honorificPrefix", "givenName", "middleName", "familyName", "honorificSuffix")
# Google Contacts lists, and counts, only the contacts in this group. Others are found only through a label.
MY_CONTACTS = "contactGroups/myContacts"
# Each list field's name in the People API.
LISTS = {"phones": "phoneNumbers", "emails": "emailAddresses", "addresses": "addresses", "urls": "urls",
         "related": "relations", "dates": "events"}
_KEYS = {"phones": phone_key, "emails": email_key, "urls": url_key, "related": fold}
# Fields the sync doesn't merge field by field. Merging copies of a person in one account carries them over.
CARRIED = ("imClients", "userDefined", "calendarUrls", "externalIds", "locations", "miscKeywords",
           "sipAddresses", "occupations", "interests")
# Google's own types, which it translates when showing them. Any other label is stored as typed.
_TYPES = {t.lower(): t for t in (
    "home", "work", "mobile", "homeFax", "workFax", "otherFax", "pager", "workMobile", "workPager", "main",
    "googleVoice", "other", "blog", "profile", "homePage", "ftp", "reservations", "appInstallPage", "spouse",
    "child", "mother", "father", "parent", "brother", "sister", "friend", "relative", "domesticPartner",
    "manager", "assistant", "referredBy", "partner", "anniversary")}


def read(account: str, person: dict, group_names: dict[str, str]) -> tuple[Contact, str]:
    """The contact, and the address of its photo ("" for none).

    group_names maps each of the account's own labels from resourceName to name.
    """
    c = Contact(account=account, id=person["resourceName"])
    if names := _own(person.get("names")):
        c.prefix, c.given, c.middle, c.family, c.suffix = (names[0].get(k, "") for k in NAME_KEYS)
    if nicknames := _own(person.get("nicknames")):
        c.nickname = nicknames[0].get("value", "")
    if orgs := _own(person.get("organizations")):
        c.company, c.title = orgs[0].get("name", ""), orgs[0].get("title", "")
        c.other_companies = [[o.get("name", ""), o.get("title", "")] for o in orgs[1:]]
    c.locations = [e["value"] for e in _own(person.get("locations")) if e.get("value")]
    c.birthday = next(filter(None, (_date_text(e.get("date") or {}) for e in _own(person.get("birthdays")))), "")
    if notes := _own(person.get("biographies")):
        c.note = notes[0].get("value", "")
    for field, name in LISTS.items():
        getattr(c, field).extend(_value(field, e) for e in _own(person.get(name)))
    member_of = {m.get("contactGroupMembership", {}).get("contactGroupResourceName") for m in person.get("memberships", [])}
    c.groups = sorted({group_names[g] for g in member_of if g in group_names})
    c.listed = MY_CONTACTS in member_of
    for source in person.get("metadata", {}).get("sources", []):
        if source.get("type") == "CONTACT":
            c.updated = source.get("updateTime", "")
    # Details shown from the person's own Google profile help with matching, but aren't the contact's to sync.
    c.match_keys = sorted(
        {f"e:{email_key(e.get('value', ''))}" for e in person.get("emailAddresses", [])}
        | {f"p:{phone_key(e.get('value', ''))}" for e in person.get("phoneNumbers", [])}
    )
    photo = next((p.get("url", "") for p in _own(person.get("photos")) if not p.get("default")), "")
    return c, photo


def edit(person: dict, changes: dict, carry: list[dict] = ()) -> tuple[dict, list[str]]:
    """An updateContact body making changes (an edit from the plan, apart from its photo), and the fields it
    replaces. It carries only the contact's own entries, each with every part Google sent; entries shown
    from the person's Google profile aren't the contact's, and stay as they are. carry holds other copies of
    the person being merged into this one: their entries in the fields the sync doesn't merge are added."""
    body = _changed(person, changes)
    for field in CARRIED:
        mine = [dict(e) for e in _own(person.get(field))]
        seen = [_bare(e) for e in mine]
        extra = [_bare(e) for other in carry for e in _own(other.get(field))]
        extra = [e for i, e in enumerate(extra) if e not in seen and e not in extra[:i]]
        if extra:
            body[field] = mine + extra
    if changes["drop_extras"]:  # the first company stays, already brought up to date
        body["organizations"] = body.get("organizations", [dict(e) for e in _own(person.get("organizations"))])[:1]
        if _own(person.get("locations")):
            body["locations"] = []
    elif carried := [_bare(e) for other in carry for e in _own(other.get("organizations"))]:
        # Other companies on a card being merged stay on the card kept, for the review to ask about.
        mine = body.get("organizations", [dict(e) for e in _own(person.get("organizations"))])
        have = [(e.get("name", ""), e.get("title", "")) for e in mine]
        body["organizations"] = mine + [e for e in carried if (e.get("name", ""), e.get("title", "")) not in have]
    sources =[s for s in person.get("metadata", {}).get("sources", []) if s.get("type") == "CONTACT"]
    return {**body, "etag": person.get("etag", ""), "metadata": {"sources": sources}}, sorted(body)


def new(changes: dict) -> dict:
    """A createContact body for a new contact, filled by changes."""
    return {k: v for k, v in _changed({}, changes).items() if v}


def backup_companies(person: dict) -> list[tuple[str, str]]:
    """What a backup's .vcf holds beyond the details the sync compares: companies after the first, as (name, title)."""
    return [(o.get("name", ""), o.get("title", "")) for o in _own(person.get("organizations"))[1:]]


def google_type(value_label: str) -> str:
    """A label as Google stores it: one of its own types, or the label as shown here."""
    return _TYPES.get(value_label.lower().replace(" ", ""), LABEL_NAMES.get(value_label, value_label))


def _changed(person: dict, changes: dict) -> dict:
    def own(name: str) -> list[dict]:
        return [dict(e) for e in _own(person.get(name))]

    body, s = {}, changes["set"]
    if "name" in s:
        names = own("names")
        entry = names[0] if names else {}
        for derived in ("displayName", "displayNameLastFirst", "unstructuredName"):
            entry.pop(derived, None)
        body["names"] = [_put(entry, dict(zip(NAME_KEYS, s["name"])))]
    if "nickname" in s:
        body["nicknames"] = _first(own("nicknames"), {"value": s["nickname"]})
    if "company" in s or "title" in s:
        values = {key: s[field] for field, key in (("company", "name"), ("title", "title")) if field in s}
        body["organizations"] = _first(own("organizations"), values, ("name", "title"))
    if "birthday" in s:
        entries = own("birthdays")
        if s["birthday"]:
            entry = entries[0] if entries else {}
            entry.pop("text", None)
            body["birthdays"] = [{**entry, "date": _date(s["birthday"])}]
        else:
            body["birthdays"] = []
    if "note" in s:
        body["biographies"] = _first(own("biographies"), {"value": s["note"]})
        for entry in body["biographies"][:1]:
            entry.setdefault("contentType", "TEXT_PLAIN")
    for field, name in LISTS.items():
        removing = {r["key"] for r in changes["remove"] if r["field"] == field}
        relabel = {r["key"]: r["label"] for r in changes["relabel"] if r["field"] == field}
        respell = {r["key"]: r for r in changes["respell"] if r["field"] == field}
        adding = [a for a in changes["add"] if a["field"] == field]
        order = changes["order"].get(field)
        if not (removing or relabel or respell or adding or order):
            continue
        current = own(name)
        last = {_key(field, e): i for i, e in enumerate(current)}  # the one a repeated value keeps
        entries = []
        for i, e in enumerate(current):
            key = _key(field, e)
            if key in removing or (key in respell and i != last[key]):
                continue
            if key in respell:
                e = _rewritten(field, e, respell[key])
            if key in relabel:
                e.pop("formattedType", None)
                e["type"] = google_type(relabel[key])
            entries.append(e)
        body[name] = entries + [_entry(field, a) for a in adding]
        if order:
            body[name] = _in_order(field, body[name], order)
    return body


def _in_order(field: str, entries: list[dict], order: list[str]) -> list[dict]:
    """Entries in the given order, with Google's primary marker on the first."""
    rank = {key: i for i, key in enumerate(order)}
    ordered = sorted(entries, key=lambda e: rank.get(_key(field, e), len(rank)))
    for i, entry in enumerate(ordered):
        metadata = {k: v for k, v in entry.get("metadata", {}).items() if k not in ("primary", "sourcePrimary")}
        entry["metadata"] = {**metadata, **({"sourcePrimary": True} if i == 0 else {})}
    return ordered


def _key(field: str, entry: dict) -> str:
    v = _value(field, entry)
    return v.key or fold(v.value)


def _date_text(d: dict) -> str:
    """A Google date as "YYYY-MM-DD", or "--MM-DD" with no year; "" if it has no month and day."""
    if not (d.get("month") and d.get("day")):
        return ""
    return (f"{d['year']:04d}" if d.get("year") else "-") + f"-{d['month']:02d}-{d['day']:02d}"


def _date(text: str) -> dict:
    """A date as Google takes it."""
    year, month, day = text.rsplit("-", 2)
    return {"month": int(month), "day": int(day)} | ({"year": int(year)} if year.isdigit() else {})


def _rewritten(field: str, entry: dict, written: dict) -> dict:
    """An entry holding a value as written, keeping its label and anything else on it. Google works out an
    address's formatted text again from the parts, and its country code from a changed country."""
    if field == "dates":
        return {**entry, "date": _date(written["value"])}
    if field != "addresses":
        name = "person" if field == "related" else "value"
        return {**{k: v for k, v in entry.items() if k != "canonicalForm"}, name: written["value"]}
    new = _entry(field, {**written, "label": ""})
    gone = {"formattedValue", "streetAddress", "extendedAddress", "city", "region", "postalCode", "country"}
    if new.get("country") != entry.get("country"):
        gone.add("countryCode")
    return {**{k: v for k, v in entry.items() if k not in gone}, **new}


def _bare(entry: dict) -> dict:
    """An entry without what Google adds on reading it, ready to add to another contact."""
    return {k: v for k, v in entry.items() if k not in ("metadata", "formattedType", "formattedProtocol")}


def _put(entry: dict, values: dict) -> dict:
    for key, value in values.items():
        if value:
            entry[key] = value
        else:
            entry.pop(key, None)
    return entry


def _first(entries: list[dict], values: dict, keep: tuple = ()) -> list[dict]:
    """entries with the first one holding values (made if there's none), dropped if left without any of keep."""
    entry = _put(entries[0] if entries else {}, values)
    return ([entry] if any(entry.get(k) for k in keep or values) else []) + entries[1:]


def _entry(field: str, value: dict) -> dict:
    if field == "addresses":
        street, city, region, postcode, country = (list(value["parts"]) + [""] * 5)[:5]
        first, _, rest = street.partition("\n")
        entry = {k: v for k, v in (("streetAddress", first), ("extendedAddress", rest.replace("\n", ", ")),
                                   ("city", city), ("region", region), ("postalCode", postcode),
                                   ("country", country)) if v}
    elif field == "dates":
        entry = {"date": _date(value["value"])}
    else:
        entry = {"person" if field == "related" else "value": value["value"]}
    if value["label"]:
        entry["type"] = google_type(value["label"])
    return entry


def _own(entries) -> list[dict]:
    """Entries the contact itself holds, leaving out ones shown from the person's own Google profile."""
    return [e for e in entries or [] if e.get("metadata", {}).get("source", {}).get("type") == "CONTACT"]


def _value(field: str, entry: dict) -> Value:
    tag, odd = label(entry.get("type", ""))
    if field == "addresses":
        street = "\n".join(filter(None, (entry.get("streetAddress", ""), entry.get("extendedAddress", ""))))
        parts = [street, entry.get("city", ""), entry.get("region", ""), entry.get("postalCode", ""),
                 entry.get("country", "")]
        text = entry.get("formattedValue", "").replace("\n", ", ") or ", ".join(filter(None, parts))
        if not any(parts):  # typed as free text, which counts as the street, where it goes in another account
            street = parts[0] = text
        return Value(text, tag, address_key(street, parts[1], parts[3], parts[2]) if text else "", parts, odd)
    if field == "dates":
        value = _date_text(entry.get("date") or {})
        return Value(value, tag, date_key(value), odd=odd)
    value = entry.get("person" if field == "related" else "value", "")
    return Value(value, tag, _KEYS[field](value), odd=odd)
