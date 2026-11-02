"""Contacts as the add-on sees them, whichever account they came from."""
import re
import unicodedata
from dataclasses import asdict, dataclass, field

# Labels left behind by other sync tools. They count as no label, so the review suggests a real one.
ODD_LABELS = {"pref"}

# Standard labels as stored here, and how the review page shows them. Any other label is custom, kept as typed.
LABEL_NAMES = {
    "mobile": "mobile", "iphone": "iPhone", "home": "home", "work": "work", "main": "main", "other": "other",
    "homefax": "home fax", "workfax": "work fax", "otherfax": "other fax", "pager": "pager",
    "workmobile": "work mobile", "workpager": "work pager", "googlevoice": "Google Voice", "school": "school",
    "homepage": "homepage", "blog": "blog", "profile": "profile",
}

_APPLE_LABEL = re.compile(r"^_\$!<(.+)>!\$_$")  # Apple's built-in labels, such as _$!<Mobile>!$_
_STREET_WORDS = {
    "street": "st", "road": "rd", "avenue": "ave", "drive": "dr", "lane": "ln", "court": "ct", "boulevard": "blvd",
    "place": "pl", "terrace": "ter", "highway": "hwy", "route": "rte", "parkway": "pkwy", "circle": "cir",
    "north": "n", "south": "s", "east": "e", "west": "w", "apartment": "apt", "suite": "ste",
}


@dataclass
class Value:
    """One phone number, email address, postal address, website or related name."""

    value: str
    label: str = ""   # a LABEL_NAMES key, or a custom label as typed; "" for none
    key: str = ""     # normalized form that decides whether two values are the same
    parts: list[str] = field(default_factory=list)  # addresses only: street, city, region, postcode, country
    odd: bool = False  # the account had an odd label here (see ODD_LABELS)


@dataclass
class Contact:
    account: str   # "icloud:<Apple ID>" or "google:<email>"
    id: str        # the account's own id: the vCard's address for iCloud, the resourceName for Google
    prefix: str = ""
    given: str = ""
    middle: str = ""
    family: str = ""
    suffix: str = ""
    nickname: str = ""
    company: str = ""
    title: str = ""
    birthday: str = ""   # "YYYY-MM-DD", or "--MM-DD" when the year isn't known
    note: str = ""
    phones: list[Value] = field(default_factory=list)
    emails: list[Value] = field(default_factory=list)
    addresses: list[Value] = field(default_factory=list)
    urls: list[Value] = field(default_factory=list)
    related: list[Value] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    photo: str = ""      # fingerprint of the photo; "" for none, "?" when it couldn't be read
    updated: str = ""    # when the account last changed the contact, if it says
    match_keys: list[str] = field(default_factory=list)  # emails and phones from a Google profile, for matching only
    listed: bool = True  # Google only: in My Contacts, the group Google Contacts lists and counts

    @property
    def ref(self) -> str:
        return f"{self.account}|{self.id}"

    def name(self) -> str:
        return " ".join(p for p in (self.prefix, self.given, self.middle, self.family, self.suffix) if p)

    def display(self) -> str:
        return self.name() or self.company or next((v.value for v in self.emails + self.phones), "") or "(no name)"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Contact":
        lists = {k: [Value(**v) for v in data.get(k, [])] for k in ("phones", "emails", "addresses", "urls", "related")}
        return cls(**{**data, **lists})


def fold(text: str) -> str:
    """Lowercase without accents, punctuation or extra spaces, for comparing (never for display)."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def phone_key(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


def email_key(value: str) -> str:
    return (value or "").strip().lower()


def url_key(value: str) -> str:
    value = re.sub(r"^[a-z][a-z0-9+.-]*://", "", (value or "").strip().lower())
    return re.sub(r"^www\.", "", value).rstrip("/")


def address_key(street: str, city: str, postcode: str) -> str:
    words = [_STREET_WORDS.get(w, w) for w in fold(street).split()]
    zip5 = re.sub(r"\D", "", postcode or "")[:5]
    return f"{' '.join(words)}|{zip5 or fold(city)}"


def label(raw: str) -> tuple[str, bool]:
    """A label as stored here, and whether the account had an odd one."""
    raw = (raw or "").strip()
    if m := _APPLE_LABEL.match(raw):
        raw = m[1]
    if raw.lower() in ODD_LABELS:
        return "", True
    squashed = raw.lower().replace(" ", "")
    return (squashed if squashed in LABEL_NAMES else raw), False


def label_text(value: str) -> str:
    return LABEL_NAMES.get(value, value) if value else "no label"
