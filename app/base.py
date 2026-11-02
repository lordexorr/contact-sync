"""What every account held after the last apply. Comparing a later check with it tells a detail an account
has since deleted, which the sync then deletes from the other accounts, from one that was never synced,
which it copies to them."""
from . import plan, storage
from .model import Contact, fold
from .settings import PRIVATE_DIR

BASE_FILE = PRIVATE_DIR / "base.json"


def load() -> dict:
    """{"clusters": [refs of one person], "contacts": {ref: entry}, "groups": {account: [folded names]}}"""
    return storage.read_json(BASE_FILE, {})


def record(contacts: list[Contact], clusters: list[list[str]], covered: set[str], accounts: list[dict],
           full: bool, keep_groups: set[str]) -> None:
    """Record the people an apply covered, as the accounts hold them now.

    covered holds the refs of the contacts the apply covered, from before and after it. Every person touching
    them is recorded afresh. Everyone else keeps what was recorded before, so a deletion in a person the apply
    left out is still noticed later. After applying everyone (full), each account's groups are recorded too,
    except in keep_groups: accounts where a group change failed.

    An account that couldn't be read (one not in accounts) keeps what was recorded about it, so it isn't
    mistaken for new when it comes back. A person gone from every account that could be read stays recorded
    whole, so they can be deleted from it too.
    """
    data = load()
    by_ref = {c.ref: c for c in contacts}
    read = {a["key"] for a in accounts}
    fresh = [list(cluster) for cluster in clusters if covered & set(cluster)]
    fresh_refs = {r for cluster in fresh for r in cluster}
    home = {r: cluster for cluster in fresh for r in cluster}
    old, away = [], set()
    for cluster in data.get("clusters", []):
        unread = [r for r in cluster if r.partition("|")[0] not in read]
        if not (covered | fresh_refs) & set(cluster):
            old.append(cluster)
        elif unread:
            mine = next((home[r] for r in cluster if r in home), None)
            if mine is None:
                old.append(cluster)
            else:
                mine += [r for r in unread if r not in mine]
                away.update(unread)
    kept_refs = {r for cluster in old for r in cluster} | away
    entries = {r: e for r, e in data.get("contacts", {}).items() if r in kept_refs}
    entries |= {r: _entry(by_ref[r]) for r in fresh_refs}
    groups = dict(data.get("groups", {}))
    if full:
        groups |= {a["key"]: sorted({fold(g) for g in a["groups"]}) for a in accounts if a["key"] not in keep_groups}
    storage.write_json(BASE_FILE, {"clusters": old + [sorted(cluster) for cluster in fresh], "contacts": entries,
                                   "groups": groups})


def forget(account: str) -> None:
    """Drop everything recorded about an account that's been removed."""
    data = load()
    if not data:
        return
    mine = account + "|"
    clusters = [[r for r in cluster if not r.startswith(mine)] for cluster in data.get("clusters", [])]
    storage.write_json(BASE_FILE, {
        "clusters": [cluster for cluster in clusters if cluster],
        "contacts": {r: e for r, e in data.get("contacts", {}).items() if not r.startswith(mine)},
        "groups": {a: g for a, g in data.get("groups", {}).items() if a != account},
    })


def _entry(c: Contact) -> dict:
    return {
        "fields": {f: c.name() if f == "name" else getattr(c, f) for f in plan.SINGLE},
        "photo": c.photo,
        "company_card": c.company_card,
        "lists": {f: {k: v.label for v in getattr(c, f) if (k := v.key or fold(v.value))} for f in plan.MULTI},
        "groups": sorted({fold(g) for g in c.groups}),
    }
