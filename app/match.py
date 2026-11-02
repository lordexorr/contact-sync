"""Deciding which contacts, in any of the accounts, are the same person."""
from collections import Counter, defaultdict
from itertools import combinations

from .model import Contact, fold

# A phone or email shared by more contacts than this, such as a company switchboard, says nothing about who's who.
MAX_SHARED = 12


def match(contacts: list[Contact], same: set[str], different: set[str]) -> tuple[list[list[str]], list[tuple[str, str]]]:
    """Groups of contact refs that are one person, and (pair, reason) for pairs the user should decide.

    Contacts are one person when they share a phone number or email address and their names agree; when
    they have the same name in different accounts and nothing contradicts it; or when the user said
    so. A shared phone or email under different names, or the same name where something does contradict
    it, is a suggestion. Pairs are two refs joined by "||"; a suggestion names the first ref of each
    group, which is also how the user's same/different decisions are stored.
    """
    by_ref = {c.ref: c for c in contacts}
    details, names = defaultdict(set), defaultdict(set)
    for c in contacts:
        for key in _detail_keys(c):
            details[key].add(c.ref)
        if name := _name_key(c):
            names[name].add(c.ref)

    linked, suggested = set(), {}
    for refs in details.values():
        if len(refs) <= MAX_SHARED:
            for pair in _pairs(refs):
                a, b = (by_ref[r] for r in pair.split("||"))
                if _names_agree(a, b):
                    linked.add(pair)
                else:
                    suggested.setdefault(pair, "The same phone number or email address, under different names")
    for refs in names.values():
        if len(refs) > MAX_SHARED:
            continue
        # With the name twice in one account it's unclear which copy goes with which, so every pair is asked about.
        crowded = max(Counter(by_ref[r].account for r in refs).values()) > 1
        for pair in _pairs(refs):
            if pair in linked:
                continue
            a, b = (by_ref[r] for r in pair.split("||"))
            if a.account == b.account:
                suggested.setdefault(pair, "The same name twice in the same account")
            elif crowded or _contradict(a, b):
                suggested.setdefault(pair, "The same name, but different phone numbers, email addresses or birthdays")
            else:
                linked.add(pair)

    parent = {r: r for r in by_ref}

    def root(r: str) -> str:
        while parent[r] != r:
            parent[r] = parent[parent[r]]
            r = parent[r]
        return r

    for pair in linked | same:
        a, b = pair.split("||")
        if a in parent and b in parent:
            parent[root(a)] = root(b)
    groups = defaultdict(list)
    for r in by_ref:
        groups[root(r)].append(r)
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
