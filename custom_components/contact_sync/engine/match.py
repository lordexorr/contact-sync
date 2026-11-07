"""Deciding which contacts, in any of the accounts, are the same person."""
from collections import Counter, defaultdict
from itertools import combinations

from .model import Contact, fold

# A phone or email shared by more contacts than this, such as a company switchboard, says nothing about who's who.
MAX_SHARED = 12


def match(contacts: list[Contact], same: set[str], different: set[str]) -> tuple[list[list[str]], list[tuple[str, str]]]:
    """Groups of contact refs that are one person, and (pair, reason) for pairs the user should decide.

    Contacts are one person when the user said so or they were at the last apply (same); when they share a
    phone number or email address, their names agree and their birthdays don't differ; or when they have the
    same name in different accounts and nothing contradicts it. Nothing joins two people the user said are
    different, even through a third contact. Anything else that looks alike is a suggestion. Pairs are two
    refs joined by "||"; a suggestion names the first ref of each group, which is also how the user's
    same/different decisions are stored.
    """
    by_ref = {c.ref: c for c in contacts}
    details, names = defaultdict(set), defaultdict(set)
    for c in contacts:
        for key in _detail_keys(c):
            details[key].add(c.ref)
        if name := _name_key(c):
            names[name].add(c.ref)

    people = _People(by_ref, different)
    suggested = {}
    for pair in sorted(same):
        a, b = pair.split("||")
        if a in by_ref and b in by_ref:
            people.join(a, b)
    for key in sorted(details):
        if len(details[key]) <= MAX_SHARED:
            for pair in _pairs(details[key]):
                a, b = pair.split("||")
                if not _names_agree(by_ref[a], by_ref[b]):
                    suggested.setdefault(pair, "The same phone number or email address, under different names")
                elif not people.join(a, b, check_birthdays=True):
                    suggested.setdefault(pair, "The same phone number or email address, but different birthdays")
    for name in sorted(names):
        if len(names[name]) <= MAX_SHARED:
            _match_name(names[name], by_ref, people, suggested)

    groups = defaultdict(list)
    for r in by_ref:
        groups[people.root(r)].append(r)
    clusters = sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])

    first = {r: g[0] for g in clusters for r in g}
    # An answer holds for the two people it was about, even after either gains a copy that sorts first.
    answered = {frozenset(first[r] for r in pair.split("||")) for pair in same | different
                if all(r in first for r in pair.split("||"))}
    open_pairs = {}
    for pair, reason in sorted(suggested.items()):
        a, b = (first[r] for r in pair.split("||"))
        if a != b and frozenset((a, b)) not in answered:
            open_pairs.setdefault("||".join(sorted((a, b))), reason)
    return clusters, sorted(open_pairs.items())


def _match_name(refs: set[str], by_ref: dict[str, Contact], people: "_People", suggested: dict) -> None:
    """Join contacts sharing a name, unless it's unclear who goes with whom. With the name twice in one account,
    or on two contacts that look like different people, a copy with nothing else on it could be either, so
    every pair is asked about."""
    pairs = [pair for pair in _pairs(refs) if people.root(pair.split("||")[0]) != people.root(pair.split("||")[1])]
    crowded = max(Counter(by_ref[r].account for r in refs).values()) > 1

    def looks_different(a: str, b: str) -> bool:
        return (by_ref[a].account != by_ref[b].account and _contradict(by_ref[a], by_ref[b])) or people.kept_apart(a, b)

    unclear = any(looks_different(*pair.split("||")) for pair in pairs)
    for pair in pairs:
        a, b = pair.split("||")
        if by_ref[a].account == by_ref[b].account:
            suggested.setdefault(pair, "The same name twice in the same account")
        elif crowded or _contradict(by_ref[a], by_ref[b]):
            suggested.setdefault(pair, "The same name, but different phone numbers, email addresses or birthdays")
        elif unclear or not people.join(a, b):
            suggested.setdefault(pair, "The same name, but another contact with this name looks like a different "
                                       "person, so this could be either")


class _People:
    """Groups of contact refs, each one person so far."""

    def __init__(self, by_ref: dict[str, Contact], different: set[str]):
        self._by_ref = by_ref
        self._parent = {r: r for r in by_ref}
        self._groups = {r: {r} for r in by_ref}
        self._apart = defaultdict(set)
        for pair in different:
            a, b = pair.split("||")
            self._apart[a].add(b)
            self._apart[b].add(a)

    def root(self, r: str) -> str:
        while self._parent[r] != r:
            self._parent[r] = self._parent[self._parent[r]]
            r = self._parent[r]
        return r

    def kept_apart(self, a: str, b: str) -> bool:
        """Whether the user said someone in a's group and someone in b's are different people."""
        others = self._groups[self.root(b)]
        return any(self._apart[r] & others for r in self._groups[self.root(a)])

    def join(self, a: str, b: str, check_birthdays: bool = False) -> bool:
        """Make a's and b's groups one person, unless that's ruled out. Whether they're one person now."""
        ra, rb = self.root(a), self.root(b)
        if ra == rb:
            return True
        if self.kept_apart(a, b) or (check_birthdays and self._birthdays_differ(ra, rb)):
            return False
        if len(self._groups[ra]) < len(self._groups[rb]):
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._groups[ra] |= self._groups.pop(rb)
        return True

    def _birthdays_differ(self, ra: str, rb: str) -> bool:
        days_a, days_b = (
            {self._by_ref[r].birthday[-5:] for r in self._groups[root] if self._by_ref[r].birthday} for root in (ra, rb))
        return bool(days_a and days_b and not days_a & days_b)


def _detail_keys(c: Contact) -> set[str]:
    keys = {f"e:{v.key}" for v in c.emails if v.key} | {f"p:{v.key}" for v in c.phones if len(v.key) >= 7}
    return keys | {k for k in c.match_keys if (k.startswith("e:") and len(k) > 2) or len(k) >= 9}


def _name_key(c: Contact) -> str:
    # A first or last name alone counts too, and a card with no name goes by its company. A business can be
    # typed in either way, as a first name on one card and as the company on another.
    return "n:" + fold(f"{c.given} {c.family}" if c.given or c.family else c.company) if c.given or c.family or c.company else ""


def _contradict(a: Contact, b: Contact) -> bool:
    """Whether two same-named contacts look like different people: each has phones or emails, but none
    in common, or each has a birthday, but on different days. A detail only one of them has doesn't count."""
    ka, kb = _detail_keys(a), _detail_keys(b)
    if ka and kb and not ka & kb:
        return True
    return bool(a.birthday and b.birthday and a.birthday[-5:] != b.birthday[-5:])


def _names_agree(a: Contact, b: Contact) -> bool:
    ga, fa, gb, fb = fold(a.given), fold(a.family), fold(b.given), fold(b.family)
    if not (ga or fa) or not (gb or fb):
        return True  # one has no name, as with many business entries
    if fa and fb and fa != fb:
        return False
    if not ga or not gb:
        return True
    return ga == gb or ga.startswith(gb) or gb.startswith(ga)


def _pairs(refs: set[str]):
    return ("||".join(pair) for pair in combinations(sorted(refs), 2))
