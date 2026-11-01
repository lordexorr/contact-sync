"""Read access to an iCloud address book over CardDAV."""
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import requests

ICLOUD_URL = "https://contacts.icloud.com/"
DAV = "DAV:"
CARDDAV = "urn:ietf:params:xml:ns:carddav"
NS = {"d": DAV, "c": CARDDAV}
MULTIGET_BATCH = 100

ET.register_namespace("d", DAV)
ET.register_namespace("c", CARDDAV)


class ICloudError(Exception):
    pass


class ICloudAddressBook:
    """One iCloud account's address book. Use it in a with block so its connection is closed."""

    def __init__(self, apple_id: str, app_password: str):
        self.session = requests.Session()
        self.session.auth = (apple_id, app_password)
        self.session.headers["User-Agent"] = "ContactSync/0.1"

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.session.close()

    def fetch_photo(self, url: str) -> bytes:
        """A contact photo, which iCloud keeps as a separate file at the address in the vCard."""
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content

    def fetch_all(self) -> list[dict]:
        """Every item in the address book, contacts and groups alike, as {href, etag, vcard}."""
        book = self._find_address_book()
        listing = self._dav("PROPFIND", book, _propfind(f"{{{DAV}}}getetag"), depth=1)
        hrefs = [r.findtext("d:href", "", NS).strip() for r in listing.findall("d:response", NS)]
        hrefs = [h for h in hrefs if not _same_path(urljoin(book, h), book)]  # skip the collection itself
        items = []
        for start in range(0, len(hrefs), MULTIGET_BATCH):
            items += self._multiget(book, hrefs[start:start + MULTIGET_BATCH])
        return items

    def _find_address_book(self) -> str:
        # Discovery: account root -> principal -> address book home -> the address book in it.
        principal = self._href_prop(ICLOUD_URL, f"{{{DAV}}}current-user-principal")
        home = self._href_prop(principal, f"{{{CARDDAV}}}addressbook-home-set")
        tree = self._dav("PROPFIND", home, _propfind(f"{{{DAV}}}resourcetype"), depth=1)
        for resp in tree.findall("d:response", NS):
            if resp.find(".//d:resourcetype/c:addressbook", NS) is not None:
                return urljoin(home, resp.findtext("d:href", "", NS).strip())
        raise ICloudError("No address book found in this iCloud account.")

    def _href_prop(self, url: str, prop: str) -> str:
        tree = self._dav("PROPFIND", url, _propfind(prop), depth=0)
        href = tree.findtext(f".//{prop}/{{{DAV}}}href", "").strip()
        if not href:
            raise ICloudError(f"iCloud didn't report {prop.split('}')[1]}.")
        return urljoin(url, href)

    def _multiget(self, book: str, hrefs: list[str]) -> list[dict]:
        root = ET.Element(f"{{{CARDDAV}}}addressbook-multiget")
        prop = ET.SubElement(root, f"{{{DAV}}}prop")
        ET.SubElement(prop, f"{{{DAV}}}getetag")
        ET.SubElement(prop, f"{{{CARDDAV}}}address-data")
        for href in hrefs:
            ET.SubElement(root, f"{{{DAV}}}href").text = href
        tree = self._dav("REPORT", book, _xml(root), depth=1)
        items = []
        for resp in tree.findall("d:response", NS):
            vcard = resp.findtext(".//c:address-data", None, NS)
            if vcard is not None:  # None when the item was deleted mid-check
                items.append({
                    "href": resp.findtext("d:href", "", NS).strip(),
                    "etag": resp.findtext(".//d:getetag", "", NS),
                    "vcard": vcard,
                })
        return items

    def _dav(self, method: str, url: str, body: bytes, depth: int) -> ET.Element:
        resp = self.session.request(
            method, url, data=body, timeout=60,
            headers={"Depth": str(depth), "Content-Type": "application/xml; charset=utf-8"},
        )
        if resp.status_code == 401:
            raise ICloudError("Apple rejected the Apple ID or app-specific password.")
        if resp.status_code != 207:
            raise ICloudError(f"iCloud answered {method} {urlparse(url).path} with HTTP {resp.status_code}.")
        return ET.fromstring(resp.content)


def _xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _propfind(prop: str) -> bytes:
    root = ET.Element(f"{{{DAV}}}propfind")
    ET.SubElement(ET.SubElement(root, f"{{{DAV}}}prop"), prop)
    return _xml(root)


def _same_path(a: str, b: str) -> bool:
    return urlparse(a).path.rstrip("/") == urlparse(b).path.rstrip("/")
