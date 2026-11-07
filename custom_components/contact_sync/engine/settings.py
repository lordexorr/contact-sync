"""Where things are stored. Home Assistant hands over its folders at setup, through configure()."""
from pathlib import Path

# Private: check results, review decisions, the last apply, photo thumbnails.
PRIVATE_DIR = Path("/data")
# Reachable over the Samba share, so the raw contact snapshots and the backups can be opened from a PC.
SHARED_DIR = Path("/config")


def configure(private_dir: Path, shared_dir: Path) -> None:
    """Keep everything under these two folders instead. Called once at setup, before anything is read or
    written: every module names its files under PRIVATE_DIR or SHARED_DIR, so each one is moved across."""
    global PRIVATE_DIR, SHARED_DIR
    from . import apply, base, check, photos, review  # here, since each of them imports this module

    for module in (apply, base, check, photos, review):
        for name, path in list(vars(module).items()):
            if not isinstance(path, Path):
                continue
            for old, new in ((PRIVATE_DIR, private_dir), (SHARED_DIR, shared_dir)):
                if path.is_relative_to(old):
                    setattr(module, name, new / path.relative_to(old))
                    break
    PRIVATE_DIR, SHARED_DIR = private_dir, shared_dir
