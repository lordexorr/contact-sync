"""Reading Google contacts."""
from .model import Contact, Value, address_key, email_key, fold, label, phone_key, url_key


def read(account: str, person: dict, group_names: dict[str, str]) -> tuple[Contact, str]:
    """The contact, and the address of its photo ("" for none).

    group_names maps each of the account's own labels from resourceName to name.
    """
    c = Contact(account=account, id=person["resourceName"])
    if names := _own(person.get("names")):
        n = names[0]
        c.prefix, c.given, c.middle, c.family, c.suffix = (
            n.get(k, "") for k in ("honorificPrefix", "givenName", "middleName", "familyName", "honorificSuffix")
        )
    if nicknames := _own(person.get("nicknames")):
        c.nickname = nicknames[0].get("value", "")
    if orgs := _own(person.get("organizations")):
        c.company, c.title = orgs[0].get("name", ""), orgs[0].get("title", "")
    for entry in _own(person.get("birthdays")):
        d = entry.get("date") or {}
        if d.get("month") and d.get("day"):
            c.birthday = (f"{d['year']:04d}" if d.get("year") else "-") + f"-{d['month']:02d}-{d['day']:02d}"
            break
    if notes := _own(person.get("biographies")):
        c.note = notes[0].get("value", "")
    for e in _own(person.get("phoneNumbers")):
        c.phones.append(_value(e, e.get("value", ""), phone_key))
    for e in _own(person.get("emailAddresses")):
        c.emails.append(_value(e, e.get("value", ""), email_key))
    for e in _own(person.get("urls")):
        c.urls.append(_value(e, e.get("value", ""), url_key))
    for e in _own(person.get("relations")):
        c.related.append(_value(e, e.get("person", ""), fold))
    for e in _own(person.get("addresses")):
        street = "\n".join(filter(None, (e.get("streetAddress", ""), e.get("extendedAddress", ""))))
        parts = [street, e.get("city", ""), e.get("region", ""), e.get("postalCode", ""), e.get("country", "")]
        text = e.get("formattedValue", "").replace("\n", ", ") or ", ".join(filter(None, parts))
        tag, odd = label(e.get("type", ""))
        c.addresses.append(Value(text, tag, address_key(street, parts[1], parts[3]), parts, odd))
    c.groups = sorted({
        group_names[g] for m in person.get("memberships", [])
        if (g := m.get("contactGroupMembership", {}).get("contactGroupResourceName")) in group_names
    })
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


def _own(entries) -> list[dict]:
    """Entries the contact itself holds, leaving out ones shown from the person's own Google profile."""
    return [e for e in entries or [] if e.get("metadata", {}).get("source", {}).get("type") == "CONTACT"]


def _value(entry: dict, value: str, key) -> Value:
    tag, odd = label(entry.get("type", ""))
    return Value(value, tag, key(value), odd=odd)
