"""Contacts as Contact Sync sees them, whichever account they came from."""
import re
import unicodedata
from dataclasses import asdict, dataclass, field

# Labels left behind by other sync tools. They count as no label, so the review suggests a real one.
ODD_LABELS = {"pref", "x-personal", "email"}
# Labels typed in place of a standard one. They count as that one, and the review fixes what's stored.
NEAR_LABELS = {"fax": "otherfax"}

# Standard labels as stored here, and how the review page shows them. Any other label is custom, kept as typed.
LABEL_NAMES = {
    "mobile": "mobile", "iphone": "iPhone", "home": "home", "work": "work", "main": "main", "other": "other",
    "homefax": "home fax", "workfax": "work fax", "otherfax": "other fax", "pager": "pager",
    "workmobile": "work mobile", "workpager": "work pager", "googlevoice": "Google Voice", "school": "school",
    "homepage": "homepage", "blog": "blog", "profile": "profile", "anniversary": "anniversary",
}

_APPLE_LABEL = re.compile(r"^_\$!<(.+)>!\$_$")  # Apple's built-in labels, such as _$!<Mobile>!$_
_EXTENSION = re.compile(r"\s*(?:[,;#]|ext\.?|x)\s*(\d+)\s*$", re.I)  # the end of a phone number, such as " x123"
_STREET_WORDS = {
    "street": "st", "road": "rd", "avenue": "ave", "drive": "dr", "lane": "ln", "court": "ct", "boulevard": "blvd",
    "place": "pl", "terrace": "ter", "highway": "hwy", "route": "rte", "parkway": "pkwy", "circle": "cir",
    "north": "n", "south": "s", "east": "e", "west": "w", "apartment": "apt", "suite": "ste",
}
_US_COUNTRY = {"us", "u s", "usa", "u s a", "united states", "united states of america"}  # as fold leaves them
_US_STATES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california", "co": "colorado",
    "ct": "connecticut", "de": "delaware", "dc": "district of columbia", "fl": "florida", "ga": "georgia",
    "hi": "hawaii", "id": "idaho", "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas", "ky": "kentucky",
    "la": "louisiana", "me": "maine", "md": "maryland", "ma": "massachusetts", "mi": "michigan", "mn": "minnesota",
    "ms": "mississippi", "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada", "nh": "new hampshire",
    "nj": "new jersey", "nm": "new mexico", "ny": "new york", "nc": "north carolina", "nd": "north dakota",
    "oh": "ohio", "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania", "ri": "rhode island",
    "sc": "south carolina", "sd": "south dakota", "tn": "tennessee", "tx": "texas", "ut": "utah", "vt": "vermont",
    "va": "virginia", "wa": "washington", "wv": "west virginia", "wi": "wisconsin", "wy": "wyoming",
}


@dataclass
class Value:
    """One phone number, email address, postal address, website, related name or date."""

    value: str
    label: str = ""   # a LABEL_NAMES key, or a custom label as typed; "" for none
    key: str = ""     # normalized form that decides whether two values are the same
    parts: list[str] = field(default_factory=list)  # addresses only: street, city, region, postcode, country
    odd: str = ""     # the odd label the account had here, if any (see ODD_LABELS and NEAR_LABELS)
    pref: bool = False  # iCloud only: marked as the preferred value in its list


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
    dates: list[Value] = field(default_factory=list)  # "YYYY-MM-DD", or "--MM-DD" when the year isn't known
    other_companies: list[list[str]] = field(default_factory=list)  # Google only: [name, title] after the first
    locations: list[str] = field(default_factory=list)  # Google only
    company_card: bool = False  # iCloud only: shown as a company rather than a person
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
        lists = {k: [Value(**v) for v in data.get(k, [])] for k in ("phones", "emails", "addresses", "urls", "related", "dates")}
        return cls(**{**data, **lists})


def fold(text: str) -> str:
    """Lowercase without accents, punctuation or extra spaces, for comparing (never for display). Text that's
    nothing but symbols, such as an emoji, stays as it is, so it still counts as a value."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split()) or " ".join(text.split())


def phone_key(value: str) -> str:
    """The number without formatting, and without the 1 on a US number. A number with another country code
    keeps it, so it can't pass for a US number ending in the same digits. An extension stays part of the key."""
    value = value or ""
    extension = _EXTENSION.search(value)
    digits = re.sub(r"\D", "", value[:extension.start()] if extension else value)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    return f"{digits}x{extension[1]}" if extension else digits


def us_phone(value: str) -> str:
    """A US number written as (555) 555-0123, however it came, with any extension after it as " x12". Anything
    else stays as it is: another country's code, a short number, or a number with letters in it."""
    extension = _EXTENSION.search(value)
    main = value[:extension.start()] if extension else value
    digits = re.sub(r"\D", "", main)
    international = main.lstrip().startswith("+") and not digits.startswith("1")
    ten = digits[1:] if len(digits) == 11 and digits[0] == "1" else digits
    # In a US number, neither the area code nor the three digits after it can start with 0 or 1.
    if international or re.search(r"[A-Za-z]", main) or not re.fullmatch(r"[2-9]\d{2}[2-9]\d{6}", ten):
        return value
    return f"({ten[:3]}) {ten[3:6]}-{ten[6:]}" + (f" x{extension[1]}" if extension else "")


def email_key(value: str) -> str:
    return (value or "").strip().lower()


def url_key(value: str) -> str:
    value = re.sub(r"^[a-z][a-z0-9+.-]*://", "", (value or "").strip().lower())
    return re.sub(r"^www\.", "", value).rstrip("/")


def address_key(street: str, city: str, postcode: str, region: str = "") -> str:
    """How addresses compare, to tell which is which. One with only a state or region goes by that, a US state's
    abbreviation counting as its name, so "NY" and "New York" are one address written two ways."""
    words = [_STREET_WORDS.get(w, w) for w in fold(street).split()]
    place = re.sub(r"\D", "", postcode or "")[:5] or fold(city)
    if not words and not place:
        return f"{_US_STATES.get(fold(region), fold(region))}|"
    return f"{' '.join(words)}|{place}"


def date_key(value: str) -> str:
    """Dates compare by day and month, so one with the year and one without count as the same date."""
    return (value or "")[-5:]


def without_us_country(parts: list[str]) -> list[str]:
    """An address's parts without a US country, which adds nothing for a household in the US. An address with
    nothing else on it keeps it, so it isn't left empty. Other countries stay."""
    street, city, region, postcode, country = (list(parts) + [""] * 5)[:5]
    if fold(country) in _US_COUNTRY and (street or city or region or postcode):
        return [street, city, region, postcode, ""]
    return list(parts)


def label(raw: str) -> tuple[str, str]:
    """A label as stored here, and the account's own text if it was an odd one."""
    raw = (raw or "").strip()
    if m := _APPLE_LABEL.match(raw):
        raw = m[1]
    if raw.lower() in ODD_LABELS:
        return "", raw
    squashed = raw.lower().replace(" ", "")
    if squashed in NEAR_LABELS:
        return NEAR_LABELS[squashed], raw
    return (squashed if squashed in LABEL_NAMES else raw), ""


def label_text(value: str) -> str:
    return LABEL_NAMES.get(value, value) if value else "no label"
