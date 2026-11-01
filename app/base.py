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
    """
    data = load()
    by_ref = {c.ref: c for c in contacts}
    fresh = [cluster for cluster in clusters if covered & set(cluster)]
    fresh_refs = {r for cluster in fresh for r in cluster}
    old = [cluster for cluster in data.get("clusters", []) if not (covered | fresh_refs) & set(cluster)]
    old_refs = {r for cluster in old for r in cluster}
    entries = {r: e for r, e in data.get("contacts", {}).items() if r in old_refs}
    entries |= {r: _entry(by_ref[r]) for r in fresh_refs}
    groups = dict(data.get("groups", {}))
    if full:
        groups |= {a["key"]: sorted({fold(g) for g in a["groups"]}) for a in accounts if a["key"] not in keep_groups}
    storage.write_json(BASE_FILE, {"clusters": old + fresh, "contacts": entries, "groups": groups})


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
        "lists": {f: {k: v.label for v in getattr(c, f) if (k := v.key or fold(v.value))} for f in plan.MULTI},
        "groups": sorted({fold(g) for g in c.groups}),
    }
