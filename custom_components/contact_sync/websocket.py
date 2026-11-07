"""The panel's commands. Every one is for admins only: the pages show everyone's contacts, and change them."""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, THUMB_URL
from .engine import editor, review
from .runtime import ContactSync

_FINGERPRINT = re.compile(r"[0-9a-f]+")


def _label(a: dict) -> None:
    label = str(a.get("label", "")).strip()[:40]
    if label != review.CUSTOM:
        review.pick(str(a.get("id", "")), label, str(a.get("seen", "")))


# What the review page saves as each choice is clicked.
DECISIONS = {
    "match": lambda a: review.decide_match(str(a.get("pair", "")), str(a.get("decision", ""))),
    "duplicate": lambda a: review.decide_duplicate(str(a.get("id", "")), str(a.get("decision", ""))),
    "extra": lambda a: review.decide_extra(str(a.get("id", "")), str(a.get("choice", ""))),
    "group": lambda a: review.choose_group(str(a.get("id", "")), str(a.get("group", ""))),
    "pick": lambda a: review.pick(str(a.get("conflict", "")), str(a.get("choice", "")), str(a.get("seen", "")),
                                  str(a.get("row", ""))),
    "label": _label,
    "skip": lambda a: review.set_skip(str(a.get("id", "")), bool(a.get("keep")), str(a.get("seen", ""))),
    "reset": lambda a: review.reset(),
}


@callback
def async_register(hass: HomeAssistant) -> None:
    for command in (ws_home, ws_check, ws_review, ws_decide, ws_contacts, ws_contact, ws_form, ws_save, ws_delete,
                    ws_discard, ws_apply_page, ws_apply, ws_result):
        websocket_api.async_register_command(hass, command)


def _sync(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> ContactSync | None:
    if entries := hass.config_entries.async_loaded_entries(DOMAIN):
        return entries[0].runtime_data
    connection.send_error(msg["id"], "not_loaded", "Contact Sync isn't set up.")
    return None


@callback
def _send(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict, data: Any) -> None:
    """data with each photo's fingerprint swapped for a signed address of its thumbnail. An <img> can't send the
    login token, so the address carries a signature for this login that runs out after a while."""
    def signed(value):
        if isinstance(value, dict):
            return {k: (async_sign_path(hass, f"{THUMB_URL}/{v}.jpg", timedelta(hours=2),
                                        refresh_token_id=connection.refresh_token_id)
                        if k == "thumb" and isinstance(v, str) and _FINGERPRINT.fullmatch(v) else signed(v))
                    for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [signed(v) for v in value]
        return value

    connection.send_result(msg["id"], signed(data))


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/home"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_home(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        _send(hass, connection, msg, await sync.async_page(sync.home))


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/check"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_check(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        if not sync.applying:  # applying checks every account itself
            sync.start_check()
        connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/review"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_review(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        _send(hass, connection, msg, await sync.async_page(review.page_data))


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/decide", vol.Required("kind"): vol.In(DECISIONS),
                                  vol.Optional("args", default={}): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_decide(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        await sync.async_run(DECISIONS[msg["kind"]], msg["args"])
        connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/contacts"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_contacts(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        _send(hass, connection, msg, await sync.async_page(editor.contacts_data))


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/contact", vol.Required("person"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_contact(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        _send(hass, connection, msg, await sync.async_page(editor.contact_data, msg["person"]))


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/form", vol.Optional("person", default=""): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_form(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        _send(hass, connection, msg, await sync.async_page(editor.form_data, msg["person"]))


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/save", vol.Optional("person", default=""): str,
                                  vol.Required("entered"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_save(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        _send(hass, connection, msg, await sync.async_run(sync.save, msg["person"], msg["entered"]))


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/delete", vol.Required("person"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_delete(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        await sync.async_run(review.request_delete, msg["person"])
        connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/discard", vol.Required("person"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_discard(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        await sync.async_run(review.discard_pending, msg["person"])
        connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/apply_page",
                                  vol.Optional("person", default=""): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_apply_page(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        _send(hass, connection, msg, await sync.async_page(sync.apply_page, msg["person"] or None))


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/apply", vol.Optional("person", default=""): str,
                                  vol.Required("token"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_apply(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        connection.send_result(msg["id"], {"started": sync.start_apply(msg["person"] or None, msg["token"])})


@websocket_api.websocket_command({vol.Required("type"): "contact_sync/result"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_result(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    if sync := _sync(hass, connection, msg):
        _send(hass, connection, msg, await sync.async_page(sync.result_page))
