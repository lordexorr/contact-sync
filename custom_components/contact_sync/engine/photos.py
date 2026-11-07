"""Photo fingerprints, so the same picture counts as the same in every account even after re-compression."""
import hashlib
import io
import logging

from PIL import Image

from . import storage
from .settings import PRIVATE_DIR

log = logging.getLogger(__name__)

THUMB_DIR = PRIVATE_DIR / "thumbs"
CACHE_FILE = PRIVATE_DIR / "photo_cache.json"
SAME_BITS = 10  # fingerprints differing in at most this many of their 64 bits are the same picture


class Fingerprints:
    """Fingerprints from earlier checks, by photo address or data hash, so each photo is downloaded once."""

    def __init__(self):
        self._known = storage.read_json(CACHE_FILE, {})
        self._used: dict[str, str] = {}

    def get(self, ref: tuple[str, object], fetch) -> str:
        """The fingerprint for ("url", address) or ("data", bytes); "?" if the photo can't be read."""
        kind, value = ref
        key = value if kind == "url" else hashlib.sha256(value).hexdigest()
        fp = self._known.get(key)
        if not fp or not (THUMB_DIR / f"{fp}.jpg").exists():
            try:
                fp = fingerprint(fetch(value) if kind == "url" else value)
            except Exception as err:  # a photo that can't be read just isn't compared
                log.warning("Couldn't read a contact photo: %s", err)
                return "?"
        self._used[key] = fp
        return fp

    def save(self) -> None:
        """Keep only this check's fingerprints and thumbnails."""
        storage.write_json(CACHE_FILE, self._used)
        keep = {f"{fp}.jpg" for fp in self._used.values()}
        if THUMB_DIR.is_dir():
            for path in THUMB_DIR.iterdir():
                if path.name not in keep:
                    path.unlink(missing_ok=True)


def fingerprint(data: bytes) -> str:
    """A 64-bit difference hash, as 16 hex digits. Also saves a small thumbnail for the review page."""
    with Image.open(io.BytesIO(data)) as original:
        img = original.convert("RGB")
    pixels = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS).get_flattened_data()
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = bits << 1 | (pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    fp = f"{bits:016x}"
    thumb = THUMB_DIR / f"{fp}.jpg"
    if not thumb.exists():
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        img.thumbnail((96, 96))
        img.save(thumb, "JPEG", quality=85)
    return fp


def same(a: str, b: str) -> bool:
    return bin(int(a, 16) ^ int(b, 16)).count("1") <= SAME_BITS
