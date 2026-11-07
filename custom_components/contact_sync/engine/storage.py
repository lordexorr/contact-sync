"""JSON files on disk, replaced atomically so a crash never leaves half a file."""
import json
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def read_json(path: Path, default):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except ValueError as err:
        # A damaged file mustn't take the page down: set it aside for inspection and start fresh.
        bad = path.with_name(path.name + ".bad")
        try:
            os.replace(path, bad)
        except OSError:
            pass  # another reader already moved it
        log.error("%s was unreadable (%s); moved it to %s", path, err, bad.name)
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Every write gets its own temp file, so two writers to the same path can't collide.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            os.fchmod(f.fileno(), 0o644)  # mkstemp makes the file owner-only; keep the usual permissions
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())  # on disk before the rename, so a power cut can't leave an empty file
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
