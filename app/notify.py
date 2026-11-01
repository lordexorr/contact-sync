"""Telling you through Home Assistant that changes are waiting."""
import logging
import os

import requests

log = logging.getLogger(__name__)

CORE_API = "http://supervisor/core/api"


def send(target: str, title: str, message: str) -> None:
    """Send through a notify entity (with notify.send_message) or a notify service, whichever target names."""
    domain, _, name = target.partition(".")
    if domain != "notify" or not name:
        log.warning("The daily notification target %r isn't a notify entity or service, such as notify.my_phone",
                    target)
        return
    headers = {"Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN', '')}"}
    try:
        if requests.get(f"{CORE_API}/states/{target}", headers=headers, timeout=15).status_code == 200:
            resp = requests.post(f"{CORE_API}/services/notify/send_message", headers=headers, timeout=30,
                                 json={"entity_id": target, "title": title, "message": message})
        else:
            resp = requests.post(f"{CORE_API}/services/notify/{name}", headers=headers, timeout=30,
                                 json={"title": title, "message": message})
    except requests.RequestException as err:
        log.warning("Couldn't reach Home Assistant to send the daily notification: %s", err)
        return
    if resp.status_code >= 400:
        log.warning("Home Assistant didn't send the daily notification (HTTP %s): %s", resp.status_code, resp.text[:200])
