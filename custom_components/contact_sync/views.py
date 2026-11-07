"""Photo thumbnails for the panel, at the signed addresses its commands hand out."""
from __future__ import annotations

import re

from aiohttp import web

from homeassistant.components.http import KEY_HASS_USER, HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import THUMB_URL
from .engine import photos


class ThumbView(HomeAssistantView):
    url = THUMB_URL + "/{name}"
    name = "api:contact_sync:thumb"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, name: str) -> web.StreamResponse:
        if not request[KEY_HASS_USER].is_admin:
            raise web.HTTPForbidden
        if not re.fullmatch(r"[0-9a-f]+\.jpg", name):
            raise web.HTTPNotFound
        path = photos.THUMB_DIR / name
        if not await self.hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound
        return web.FileResponse(path)
