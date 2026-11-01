"""Reading iCloud's vCards."""
import base64
import re

from .model import Contact, Value, address_key, email_key, fold, label, phone_key, url_key

_LINE = re.compile(r"^(?:(?P<group>[^.:;]+)\.)?(?P<name>[^:;]+)(?P<params>(?:;[^:]*)?):(?P<value>.*)$")
_NOT_LABELS = {"voice", "pref", "internet", "x400"}  # TYPE values that don't say which label a value has


def read(account: str, items: list[dict]) -> tuple[list[Contact], list[str], dict[str, tuple[str, object]]]:
    """An account's contacts, its group names, and each contact's photo as ("url", address) or ("data", bytes)."""
    parsed = [(item["href"], parse(item["vcard"])) for item in items]
    groups, members = [], {}
    for _, props in parsed:
        if _is_group(props):
            name = next((unescape(v) for _, n, _, v in props if n == "FN"), "")
            if name:
                groups.append(name)
                for _, n, _, v in props:
                    if n == "X-ADDRESSBOOKSERVER-MEMBER":
                        members.setdefault(v.removeprefix("urn:uuid:"), []).append(name)
    contacts, photos = [], {}
    for href, props in parsed:
        if _is_group(props):
            continue
        contact, photo = _contact(account, href, props)
        uid = next((v for _, n, _, v in props if n == "UID"), "")
        contact.groups = sorted(set(members.get(uid, [])))
        contacts.append(contact)
        if photo:
            photos[contact.id] = photo
    return contacts, groups, photos


def parse(text: str) -> list[tuple[str, str, dict[str, list[str]], str]]:
    """Every property line as (group, NAME, {PARAM: [values]}, raw value)."""
    props = []
    for line in re.sub(r"\r?\n[ \t]", "", text).splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        params: dict[str, list[str]] = {}
        for param in filter(None, m["params"].split(";")):
            key, _, values = param.partition("=")
            if not values:  # a bare type, as in "TEL;CELL:..."
                key, values = "TYPE", key
            params.setdefault(key.upper(), []).extend(v.strip('"') for v in values.split(","))
        props.append((m["group"] or "", m["name"].upper(), params, m["value"]))
    return props


def unescape(value: str) -> str:
    return re.sub(r"\\(.)", lambda m: "\n" if m[1] in "nN" else m[1], value)


def fields(value: str, count: int) -> list[str]:
    """The parts of a structured value such as N or ADR, padded to count."""
    parts = re.split(r"(?<!\\);", value)
    return [unescape(p) for p in parts[:count]] + [""] * (count - len(parts))


def _is_group(props) -> bool:
    return any(n == "X-ADDRESSBOOKSERVER-KIND" and v.lower() == "group" for _, n, _, v in props)


def _contact(account: str, href: str, props) -> tuple[Contact, tuple[str, object] | None]:
    # Custom and Apple labels sit on a separate X-ABLabel line in the same itemN group as the value.
    item_labels = {g: v for g, n, _, v in props if g and n == "X-ABLABEL"}
    c = Contact(account=account, id=href)
    photo = None
    for group, name, params, raw in props:
        tag, odd = label(unescape(item_labels[group]) if group in item_labels else _type_label(params.get("TYPE", [])))
        if name == "N":
            c.family, c.given, c.middle, c.prefix, c.suffix = fields(raw, 5)
        elif name == "NICKNAME":
            c.nickname = unescape(raw)
        elif name == "ORG":
            c.company = fields(raw, 1)[0]
        elif name == "TITLE":
            c.title = unescape(raw)
        elif name == "BDAY":
            c.birthday = _birthday(raw, params)
        elif name == "NOTE":
            c.note = unescape(raw)
        elif name == "REV":
            c.updated = raw
        elif name == "TEL":
            value = unescape(raw)
            c.phones.append(Value(value, tag, phone_key(value), odd=odd))
        elif name == "EMAIL":
            value = unescape(raw)
            c.emails.append(Value(value, tag, email_key(value), odd=odd))
        elif name == "ADR":
            _, _, street, city, region, postcode, country = fields(raw, 7)
            line = " ".join(filter(None, (region, postcode)))
            text = ", ".join(filter(None, (street.replace("\n", ", "), city, line, country)))
            if text:
                parts = [street, city, region, postcode, country]
                c.addresses.append(Value(text, tag, address_key(street, city, postcode), parts, odd))
        elif name == "URL":
            value = unescape(raw)
            c.urls.append(Value(value, tag, url_key(value), odd=odd))
        elif name == "X-ABRELATEDNAMES":
            value = unescape(raw)
            c.related.append(Value(value, tag, fold(value), odd=odd))
        elif name == "PHOTO":
            photo = _photo(raw)
    return c, photo


def _type_label(types: list[str]) -> str:
    kinds = {t.lower() for t in types} - _NOT_LABELS
    if "fax" in kinds:
        return "workfax" if "work" in kinds else "homefax" if "home" in kinds else "otherfax"
    for kind in ("iphone", "main", "pager", "cell", "home", "work", "other"):
        if kind in kinds:
            return "mobile" if kind == "cell" else kind
    return ""


def _birthday(value: str, params: dict[str, list[str]]) -> str:
    if value.startswith("--"):
        digits = re.sub(r"\D", "", value)
        return f"--{digits[-4:-2]}-{digits[-2:]}" if len(digits) >= 4 else ""
    digits = re.sub(r"\D", "", value.split("T")[0])
    if len(digits) < 8:
        return ""
    year, month, day = digits[:4], digits[4:6], digits[6:8]
    # Apple stores a birthday without a year under a placeholder year, named in X-APPLE-OMIT-YEAR.
    if params.get("X-APPLE-OMIT-YEAR", [""])[0] == year:
        return f"--{month}-{day}"
    return f"{year}-{month}-{day}"


def _photo(raw: str) -> tuple[str, object] | None:
    if raw.startswith("http"):
        return ("url", raw)
    if raw.startswith("data:"):
        raw = raw.partition(",")[2]
    try:
        return ("data", base64.b64decode(raw))
    except ValueError:
        return None
