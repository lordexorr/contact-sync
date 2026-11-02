"""Reading and writing iCloud's vCards."""
import base64
import re
from collections import defaultdict
from datetime import datetime, timezone

from .model import Contact, Value, address_key, email_key, fold, label, label_text, phone_key, url_key

_LINE = re.compile(r"^(?:(?P<group>[^.:;]+)\.)?(?P<name>[^:;]+)(?P<params>(?:;[^:]*)?):(?P<value>.*)$")
_NOT_LABELS = {"voice", "pref", "internet", "x400"}  # TYPE values that don't say which label a value has
# The vCard property behind each list field, and how its values are compared.
_PROPS = {"phones": "TEL", "emails": "EMAIL", "addresses": "ADR", "urls": "URL", "related": "X-ABRELATEDNAMES"}
_FIELDS = {prop: field for field, prop in _PROPS.items()}
_KEYS = {"TEL": phone_key, "EMAIL": email_key, "URL": url_key, "X-ABRELATEDNAMES": fold}


def read(account: str, items: list[dict]) -> tuple[list[Contact], list[str], dict[str, tuple[str, object]]]:
    """An account's contacts, its group names, and each contact's photo as ("url", address) or ("data", bytes)."""
    parsed = [(item["href"], parse(item["vcard"])) for item in items]
    groups, members = [], {}
    for _, props in parsed:
        if _is_group(props):
            name = _name(props)
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
        contact.groups = sorted(set(members.get(_uid(props), [])))
        contacts.append(contact)
        if photo:
            photos[contact.id] = photo
    return contacts, groups, photos


def groups(items: list[dict]) -> dict[str, dict]:
    """The address book's group items, by folded group name."""
    found = {}
    for item in items:
        props = parse(item["vcard"])
        if _is_group(props) and (name := _name(props)):
            found.setdefault(fold(name), item)
    return found


def is_group(text: str) -> bool:
    """Whether a vCard is a group rather than a contact."""
    return _is_group(parse(text))


def uid(text: str) -> str:
    """A vCard's UID, which is how groups list their members."""
    return _uid(parse(text))


def parse(text: str) -> list[tuple[str, str, dict[str, list[str]], str]]:
    """Every property line as (group, NAME, {PARAM: [values]}, raw value)."""
    props = []
    for line in _unfold(text):
        m = _LINE.match(line)
        if m:
            props.append((m["group"] or "", m["name"].upper(), _params(m["params"]), m["value"]))
    return props


def unescape(value: str) -> str:
    return re.sub(r"\\(.)", lambda m: "\n" if m[1] in "nN" else m[1], value)


def fields(value: str, count: int) -> list[str]:
    """The parts of a structured value such as N or ADR, padded to count."""
    parts = re.split(r"(?<!\\);", value)
    return [unescape(p) for p in parts[:count]] + [""] * (count - len(parts))


def _unfold(text: str) -> list[str]:
    return re.sub(r"\r?\n[ \t]", "", text).splitlines()


def _params(text: str) -> dict[str, list[str]]:
    params: dict[str, list[str]] = {}
    for param in filter(None, text.split(";")):
        key, _, values = param.partition("=")
        if not values:  # a bare type, as in "TEL;CELL:..."
            key, values = "TYPE", key
        params.setdefault(key.upper(), []).extend(v.strip('"') for v in values.split(","))
    return params


def _is_group(props) -> bool:
    return any(n == "X-ADDRESSBOOKSERVER-KIND" and v.lower() == "group" for _, n, _, v in props)


def _name(props) -> str:
    return next((unescape(v) for _, n, _, v in props if n == "FN"), "")


def _uid(props) -> str:
    return next((v for _, n, _, v in props if n == "UID"), "").removeprefix("urn:uuid:")


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
        elif name in _FIELDS:
            if v := _list_value(name, raw, tag, odd):
                getattr(c, _FIELDS[name]).append(v)
        elif name == "PHOTO":
            photo = _photo(raw)
    return c, photo


def _list_value(name: str, raw: str, tag: str = "", odd: bool = False) -> Value | None:
    """The value on a phone, email, address, website or related-name line; None for an empty address."""
    if name != "ADR":
        value = unescape(raw)
        return Value(value, tag, _KEYS[name](value), odd=odd)
    _, _, street, city, region, postcode, country = fields(raw, 7)
    line = " ".join(filter(None, (region, postcode)))
    text = ", ".join(filter(None, (street.replace("\n", ", "), city, line, country)))
    if not text:
        return None
    return Value(text, tag, address_key(street, city, postcode, region), [street, city, region, postcode, country], odd)


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


# --- Writing ---
# Only the lines a change touches are rewritten. Every other line, including ones this add-on doesn't read,
# goes back to iCloud as it came.

PRODID = "PRODID:-//Contact Sync//EN"
# How each label is written: as TYPE values where vCard has them, otherwise on an X-ABLabel line.
_TYPES = {
    "TEL": {"mobile": ["CELL", "VOICE"], "iphone": ["IPHONE", "CELL", "VOICE"], "home": ["HOME", "VOICE"],
            "work": ["WORK", "VOICE"], "main": ["MAIN"], "homefax": ["HOME", "FAX"], "workfax": ["WORK", "FAX"],
            "otherfax": ["OTHER", "FAX"], "pager": ["PAGER"]},
    "EMAIL": {"home": ["INTERNET", "HOME"], "work": ["INTERNET", "WORK"]},
    "ADR": {"home": ["HOME"], "work": ["WORK"]},
    "URL": {"home": ["HOME"], "work": ["WORK"]},
}
_ALWAYS = {"EMAIL": ["INTERNET"]}  # TYPE values a line keeps whatever its label
# Apple's built-in labels, which it writes as _$!<Name>!$_ on the X-ABLabel line.
_APPLE = {name.lower(): name for name in (
    "Other", "HomePage", "Father", "Mother", "Parent", "Brother", "Sister", "Child", "Friend", "Spouse", "Partner",
    "Assistant", "Manager")}
_LABEL_TYPES = {"home", "work", "cell", "iphone", "main", "pager", "fax", "other", "voice"}  # TYPE values that make a label
# Lines that describe the card's photo, which go when the photo is replaced and never move to another card.
_PHOTO_LINES = {"PHOTO", "X-IMAGEHASH", "X-IMAGETYPE"}
# Lines a merge never copies from another card: the card's own identity, and everything the sync already
# merges field by field.
_NOT_CARRIED = {"BEGIN", "END", "VERSION", "PRODID", "UID", "REV", "N", "FN", "NICKNAME", "ORG", "TITLE", "BDAY",
                "NOTE", "X-ABSHOWAS", "X-ADDRESSBOOKSERVER-KIND", "X-ADDRESSBOOKSERVER-MEMBER", "X-ABLABEL",
                "X-ABADR"} | _PHOTO_LINES | set(_PROPS.values())
# Details a card can hold several of, so a merge adds any the kept card lacks. Of any other detail, such as
# a gender, the kept card's own stays when it has one.
_MANY = {"X-ABDATE", "X-SOCIALPROFILE", "IMPP", "X-AIM", "X-JABBER", "X-MSN", "X-YAHOO", "X-ICQ", "X-SKYPE",
         "X-QQ", "X-GADUGADU", "CATEGORIES"}


def edit(text: str, changes: dict, photo: tuple[bytes, str] | None = None,
         current_photo: tuple[bytes, str] | None = None, carry: list[str] = ()) -> str:
    """The vCard with changes made: an edit from the plan ("set", "photo", "add", "remove", "relabel").

    photo is the new picture, as (data, "JPEG" or "PNG"), when changes["photo"] replaces it. current_photo is
    the picture the contact has now. iCloud gives it as a link, which is swapped for the picture itself so
    rewriting the contact can't lose it. carry holds the vCards of copies being merged into this one.
    """
    card = _Card(text)
    for field, value in changes["set"].items():
        _set(card, field, value)
    if changes["photo"] == "clear" or photo:
        card.drop(p[0] for p in card.props() if p[2] in _PHOTO_LINES)
        if photo:
            card.insert(_photo_line(photo))
    elif current_photo:
        for i, group, _, params, raw in card.find("PHOTO"):
            if raw.lower().startswith("http"):
                kept = {k: v for k, v in params.items() if k not in ("VALUE", "ENCODING", "TYPE")}
                card.lines[i] = _photo_line(current_photo, group, kept)
    _edit_lists(card, changes)
    for value in changes["add"]:
        _add(card, value)
    for other in carry:
        _carry(card, other)
    card.put("REV", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))  # when the card last changed
    return card.text()


def with_backup_details(text: str, dates: list[tuple[str, str]], companies: list[tuple[str, str]]) -> str:
    """A vCard with details only a backup carries: dates as (YYYY-MM-DD, type), and further companies as
    (name, title)."""
    card = _Card(text)
    for date, kind in dates:
        group = f"item{card.next_item()}"
        omit = ";X-APPLE-OMIT-YEAR=1604" if date.startswith("1604-") else ""
        shown = "_$!<Anniversary>!$_" if kind.lower() == "anniversary" else _esc(kind or "other")
        card.insert(f"{group}.X-ABDATE{omit}:{date}", f"{group}.X-ABLabel:{shown}")
    for name, title in companies:
        card.insert(*([f"ORG:{_esc(name)}"] if name else []), *([f"TITLE:{_esc(title)}"] if title else []))
    return card.text()


def new(uid: str, changes: dict, photo: tuple[bytes, str] | None = None) -> str:
    """A vCard for a new contact, filled by changes."""
    s = changes["set"]
    name = " ".join(p for p in s.get("name", []) if p)
    shown = name or s.get("company") or next((a["value"] for a in changes["add"]), "")
    lines = ["BEGIN:VCARD", "VERSION:3.0", PRODID, "N:;;;;", f"FN:{_esc(shown)}"]
    if not name and s.get("company"):
        lines.append("X-ABShowAs:COMPANY")
    lines += [f"UID:{uid}", "END:VCARD"]
    return edit("\r\n".join(lines), changes, photo)


def group_card(uid: str, name: str, members: list[str]) -> str:
    """A new group, with members given by their UIDs."""
    lines = ["BEGIN:VCARD", "VERSION:3.0", PRODID, f"N:{_esc(name)}", f"FN:{_esc(name)}",
             "X-ADDRESSBOOKSERVER-KIND:group"]
    lines += [f"X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:{m}" for m in members]
    lines += [f"UID:{uid}", "END:VCARD"]
    return "".join(_fold(line) + "\r\n" for line in lines)


def edit_members(text: str, add: list[str], remove: list[str]) -> str:
    """A group with members added and removed, by their UIDs."""
    card, gone, have, drop = _Card(text), set(remove), set(), []
    for i, _, name, _, raw in card.props():
        if name == "X-ADDRESSBOOKSERVER-MEMBER":
            member = raw.removeprefix("urn:uuid:")
            if member in gone:
                drop.append(i)
            else:
                have.add(member)
    card.drop(drop)
    card.insert(*[f"X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:{m}" for m in dict.fromkeys(add) if m not in have])
    return card.text()


class _Card:
    """A vCard's unfolded lines, for editing."""

    def __init__(self, text: str):
        self.lines = [line for line in _unfold(text) if line.strip()]

    def props(self):
        """(index, group, NAME, params, raw value) for each property line."""
        for i, line in enumerate(self.lines):
            if m := _LINE.match(line):
                yield i, m["group"] or "", m["name"].upper(), _params(m["params"]), m["value"]

    def find(self, name: str) -> list[tuple]:
        return [p for p in self.props() if p[2] == name]

    def drop(self, indexes) -> None:
        gone = set(indexes)
        self.lines = [line for i, line in enumerate(self.lines) if i not in gone]

    def insert(self, *lines: str) -> None:
        """Add lines just before END:VCARD."""
        end = next((i for i in range(len(self.lines) - 1, -1, -1) if self.lines[i].upper() == "END:VCARD"),
                   len(self.lines))
        self.lines[end:end] = lines

    def put(self, name: str, raw: str) -> None:
        """Set a property that has one value, keeping the first line's group and parameters; "" removes it."""
        found = self.find(name)
        if raw and found:
            i = found[0][0]
            m = _LINE.match(self.lines[i])
            self.lines[i] = self.lines[i][:m.start("value")] + raw
            self.drop(p[0] for p in found[1:])
        elif raw:
            self.insert(f"{name}:{raw}")
        else:
            self.drop(p[0] for p in found)

    def next_item(self) -> int:
        numbers = [int(m[1]) for _, group, *_ in self.props() if (m := re.fullmatch(r"item(\d+)", group, re.I))]
        return max(numbers, default=0) + 1

    def text(self) -> str:
        return "".join(_fold(line) + "\r\n" for line in self.lines)


def _set(card: _Card, field: str, value) -> None:
    if field == "name":
        prefix, given, middle, family, suffix = value
        card.put("N", ";".join(_esc(p) for p in (family, given, middle, prefix, suffix)))
        if full := " ".join(p for p in value if p):
            card.put("FN", _esc(full))
    elif field == "company":
        found = card.find("ORG")
        parts = re.split(r"(?<!\\);", found[0][4]) if found else [""]
        parts[0] = _esc(value)  # the department and anything after it stay
        card.put("ORG", ";".join(parts) if any(parts) else "")
    elif field == "birthday":
        card.put("BDAY", "")
        if value:
            year, month, day = value.rsplit("-", 2)
            if year.isdigit():
                card.insert(f"BDAY;VALUE=date:{year}-{month}-{day}")
            else:  # Apple's way of storing a birthday without a year
                card.insert(f"BDAY;X-APPLE-OMIT-YEAR=1604;VALUE=date:1604-{month}-{day}")
    else:
        card.put({"nickname": "NICKNAME", "title": "TITLE", "note": "NOTE"}[field], _esc(value))


def _edit_lists(card: _Card, changes: dict) -> None:
    """Remove, relabel and respell list values. Each is found against the card as it is, then the card is rebuilt
    once. A respelled value that's on the card more than once keeps only its last line."""
    removing = {(r["field"], r["key"]) for r in changes["remove"]}
    relabel = {(r["field"], r["key"]): r["label"] for r in changes["relabel"]}
    respell = {(r["field"], r["key"]): r for r in changes["respell"]}
    if not removing and not relabel and not respell:
        return
    next_item = card.next_item()
    last = {}
    for i, _, name, _, raw in card.props():
        if name in _FIELDS and (v := _list_value(name, raw)):
            last[(_FIELDS[name], v.key or fold(v.value))] = i
    gone_lines, gone_groups, rewritten, relabelled = set(), set(), {}, set()
    for i, group, name, params, raw in card.props():
        if name not in _FIELDS or not (v := _list_value(name, raw)):
            continue
        key = (_FIELDS[name], v.key or fold(v.value))
        if key in removing or (key in respell and i != last[key]):
            # Apple keeps each labelled value in its own itemN group, with its label lines; they go together.
            if group:
                gone_groups.add(group.lower())
            else:
                gone_lines.add(i)
            continue
        written = _raw_value(name, respell[key], raw) if key in respell else raw
        if key in relabel:
            types, ablabel = _label(name, relabel[key])
            kept = [t for t in params.get("TYPE", []) if t.lower() not in _LABEL_TYPES]
            if ablabel and not group:
                group, next_item = f"item{next_item}", next_item + 1
            rewritten[i] = (_head(group, name, {**params, "TYPE": _unique(kept + types)}) + ":" + written, group, ablabel)
            if group:
                relabelled.add(group.lower())
        elif written != raw:
            rewritten[i] = (card.lines[i][:_LINE.match(card.lines[i]).start("value")] + written, group, "")
    lines = []
    for i, line in enumerate(card.lines):
        m = _LINE.match(line)
        group = (m["group"] or "").lower() if m else ""
        if i in gone_lines or (group and group in gone_groups):
            continue
        if m and m["name"].upper() == "X-ABLABEL" and group in relabelled:
            continue  # replaced just below the value it labels
        if i in rewritten:
            new_line, new_group, ablabel = rewritten[i]
            lines.append(new_line)
            if ablabel:
                lines.append(f"{new_group}.X-ABLabel:{_esc(ablabel)}")
        else:
            lines.append(line)
    card.lines = lines


def _carry(card: _Card, other: str) -> None:
    """Copy onto card every detail of another copy of the person that the sync doesn't merge field by field,
    such as dates, social profiles and messaging handles, so deleting that copy loses nothing."""
    have_names = {name for _, _, name, _, _ in card.props()}
    have_lines = {(name, raw.lower()) for _, _, name, _, raw in card.props()}
    grouped, single = defaultdict(list), []
    for line in _unfold(other):
        if not (m := _LINE.match(line)):
            continue
        name = m["name"].upper()
        if m["group"]:
            grouped[m["group"].lower()].append(m)
        elif name not in _NOT_CARRIED and (name, m["value"].lower()) not in have_lines:
            if name in _MANY or name not in have_names:
                single.append(line)
    card.insert(*single)
    for members in grouped.values():
        main = {m["name"].upper() for m in members} - {"X-ABLABEL", "X-ABADR"}
        if not main or main & _NOT_CARRIED:
            continue
        if all((m["name"].upper(), m["value"].lower()) in have_lines for m in members if m["name"].upper() in main):
            continue
        # A labelled detail comes over whole, under a group name of its own on this card.
        group = f"item{card.next_item()}"
        card.insert(*[f"{group}.{m.string[m.start('name'):]}" for m in members])


def _add(card: _Card, value: dict) -> None:
    name = _PROPS[value["field"]]
    types, ablabel = _label(name, value["label"])
    group = f"item{card.next_item()}" if ablabel else ""
    lines = [_head(group, name, {"TYPE": types}) + ":" + _raw_value(name, value)]
    if ablabel:
        lines.append(f"{group}.X-ABLabel:{_esc(ablabel)}")
    card.insert(*lines)


def _raw_value(name: str, value: dict, raw: str = "") -> str:
    """A list value as its vCard line writes it. An address replacing raw keeps what comes before the street."""
    if name == "ADR":
        parts = (list(value["parts"]) + [""] * 5)[:5]  # street, city, region, postcode, country
        before = (re.split(r"(?<!\\);", raw)[:2] + ["", ""])[:2] if raw else ["", ""]
        return ";".join(before + [_esc(p) for p in parts])
    if name == "X-ABRELATEDNAMES":
        return _esc(value["value"])
    return " ".join(value["value"].splitlines())


def _label(name: str, value_label: str) -> tuple[list[str], str]:
    """The TYPE values, and the X-ABLabel ("" for none), that give a value of this property its label."""
    always = list(_ALWAYS.get(name, []))
    if not value_label:
        return always, ""
    lower = value_label.lower()
    if lower in _TYPES.get(name, {}):
        return _unique(always + _TYPES[name][lower]), ""
    if lower in _APPLE:
        return always, f"_$!<{_APPLE[lower]}>!$_"
    return always, label_text(value_label)


def _head(group: str, name: str, params: dict[str, list[str]]) -> str:
    head = f"{group}.{name}" if group else name
    for key, values in params.items():
        if not values:
            continue
        if key == "TYPE":
            head += "".join(f";type={v}" for v in values)
        else:
            head += f";{key}=" + ",".join(f'"{v}"' if re.search(r"[:;,]", v) else v for v in values)
    return head


def _photo_line(photo: tuple[bytes, str], group: str = "", params: dict | None = None) -> str:
    data, kind = photo
    return _head(group, "PHOTO", {**(params or {}), "ENCODING": ["b"], "TYPE": [kind]}) + ":" + base64.b64encode(data).decode()


def _unique(values: list[str]) -> list[str]:
    seen, out = set(), []
    for v in values:
        if v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def _esc(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _fold(line: str) -> str:
    """A line split into pieces of at most 75 bytes, as vCard asks, without splitting a character."""
    if line.isascii():
        return "\r\n ".join([line[:75]] + [line[i:i + 74] for i in range(75, len(line), 74)])
    pieces, piece, size = [], "", 0
    for ch in line:
        n = len(ch.encode())
        if size + n > 75:
            pieces.append(piece)
            piece, size = " ", 1
        piece += ch
        size += n
    pieces.append(piece)
    return "\r\n".join(pieces)
