"""What Contact Sync does while Home Assistant runs: the daily check, checking and applying when asked, and what
each page of the panel shows. The engine does the work, always in the executor, since it reads files and talks to
iCloud and Google."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util, slugify

from .const import (CONF_CHECK_TIME, CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_NOTIFY, DEFAULT_CHECK_TIME, DOMAIN,
                    SIGNAL_UPDATED, SUBENTRY_GOOGLE, SUBENTRY_ICLOUD)
from .engine import apply, check, editor, google, review

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__package__)


def fmt_time(dt: datetime) -> str:
    return f"{dt:%a %b} {dt.day}, {dt.hour % 12 or 12}:{dt:%M} {'AM' if dt.hour < 12 else 'PM'}"


class ContactSync:
    """Contact Sync with the accounts and options its config entry has."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, version: str) -> None:
        self.hass = hass
        self.entry = entry
        self.version = version
        self.tz = dt_util.get_time_zone(hass.config.time_zone) or dt_util.UTC
        hour, minute, *_ = entry.options.get(CONF_CHECK_TIME, DEFAULT_CHECK_TIME).split(":")
        self.check_time = time(int(hour), int(minute))
        self.checking = False
        self.applying = False
        self.check_error = ""
        self.progress: apply.Progress | None = None
        # What the entities show, from the latest look at the review.
        self.counts: dict | None = None
        self.checked_at: datetime | None = None
        self.unread: list[str] = []
        self._issues: set[str] = set()  # the Repairs issues raised, one for each account that couldn't be read
        self._unsub_daily: Callable[[], None] | None = None

    @property
    def options(self) -> dict:
        return {CONF_CHECK_TIME: self.entry.options.get(CONF_CHECK_TIME, DEFAULT_CHECK_TIME),
                CONF_NOTIFY: self.entry.options.get(CONF_NOTIFY, "")}

    async def async_start(self) -> None:
        icloud = [dict(s.data) for s in self.entry.subentries.values() if s.subentry_type == SUBENTRY_ICLOUD]
        google_ = [dict(s.data) for s in self.entry.subentries.values() if s.subentry_type == SUBENTRY_GOOGLE]
        check.set_accounts(icloud, google_, {"client_id": self.entry.data.get(CONF_CLIENT_ID, ""),
                                             "client_secret": self.entry.data.get(CONF_CLIENT_SECRET, "")})
        keys = {f"icloud:{a['apple_id']}" for a in icloud} | {f"google:{a['email']}" for a in google_}
        # Google sign-ins from before this reload, so one whose account was just removed can be cancelled at Google.
        # Since a restart they aren't known, and what was saved from a removed account is still deleted.
        kept = self.hass.data.setdefault(DOMAIN, {})
        before = kept.get("google_tokens", {})
        kept["google_tokens"] = {a["email"]: a["refresh_token"] for a in google_}
        revoked = [token for email, token in before.items() if f"google:{email}" not in keys]
        await self.hass.async_add_executor_job(_forget_removed, keys, revoked)
        self._unsub_daily = async_track_time_change(self.hass, self._daily, hour=self.check_time.hour,
                                                    minute=self.check_time.minute, second=0)
        # The review takes a moment to put together, so setup doesn't wait for it; the entities follow once it's ready.
        self.entry.async_create_background_task(self.hass, self.async_refresh(), "contact_sync_refresh")

    @callback
    def async_stop(self) -> None:
        if self._unsub_daily:
            self._unsub_daily()

    # --- Checking and applying ---

    @callback
    def _daily(self, now: datetime) -> None:
        self.start_check(daily=True)

    @callback
    def start_check(self, daily: bool = False) -> None:
        """Check every account in the background. A check already running carries on instead; one started during
        an apply waits for it to finish."""
        if self.checking:
            return
        self.checking, self.check_error = True, ""
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
        self.entry.async_create_background_task(self.hass, self._async_check(daily), "contact_sync_check")

    async def _async_check(self, daily: bool) -> None:
        try:
            message = await self.hass.async_add_executor_job(_check, self.options, daily)
        except Exception as err:  # the page says what happened, and the next check tries again
            _LOGGER.exception("Check failed")
            self.check_error = (f"The check at {fmt_time(datetime.now(self.tz))} failed ({type(err).__name__}: {err}). "
                                "Details are in Home Assistant's log.")
        else:
            if message:
                await self._async_notify(message)
        finally:
            self.checking = False
            await self.async_refresh()

    async def _async_notify(self, message: str) -> None:
        """Through a notify entity (with notify.send_message) or a notify action, whichever the option names."""
        target = self.options[CONF_NOTIFY]
        data = {"title": "Contact Sync", "message": message}
        try:
            if self.hass.states.get(target):
                await self.hass.services.async_call("notify", "send_message", {"entity_id": target, **data}, blocking=True)
            else:
                await self.hass.services.async_call("notify", target.partition(".")[2], data, blocking=True)
        except HomeAssistantError as err:
            _LOGGER.warning("Couldn't send the daily notification through %s: %s", target, err)

    @callback
    def start_apply(self, person: str | None, token: str) -> bool:
        """Apply in the background what the Apply page showed (token); False while a check is running."""
        if self.checking:
            return False
        if not self.applying:
            self.applying, self.progress = True, apply.Progress()
            async_dispatcher_send(self.hass, SIGNAL_UPDATED)
            self.entry.async_create_background_task(self.hass, self._async_apply(person, token, self.progress),
                                                    "contact_sync_apply")
        return True

    async def _async_apply(self, person: str | None, token: str, progress: apply.Progress) -> None:
        try:
            await self.hass.async_add_executor_job(apply.run, self.options, person, token, self.tz, progress)
        finally:
            self.applying = False
            await self.async_refresh()

    # --- What the pages and entities show ---

    async def async_page(self, build: Callable[..., Any], *args: Any) -> Any:
        """build(review, *args) in the executor, with the review from the latest check and every decision so far.
        What the entities show is brought up to date on the way."""
        def run():
            rv = review.current_plan(self.options)
            return build(rv, *args), (rv or {}).get("counts"), check.load_status() or {}

        data, counts, status = await self.hass.async_add_executor_job(run)
        self.counts = counts
        self.checked_at = dt_util.parse_datetime(status["checked_at"]) if status.get("checked_at") else None
        self.unread = [f"{a['service']} {a['name']}" for a in status.get("accounts", []) if a["error"]]
        self._report_unread(status)
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)
        return data

    @callback
    def _report_unread(self, status: dict) -> None:
        """A Repairs issue for each account the latest check couldn't read, gone once a check reads it. They aren't
        kept over a restart: the first look at the review afterwards raises them again."""
        failing = {f"account_unread_{slugify(a['service'] + ' ' + a['login'])}": a
                   for a in status.get("accounts", []) if a["error"]}
        for issue_id in self._issues - failing.keys():
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        for issue_id, a in failing.items():
            ir.async_create_issue(self.hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                                  translation_key="account_unread",
                                  translation_placeholders={"account": f"{a['service']} {a['name']}", "error": a["error"]})
        self._issues = set(failing)

    async def async_refresh(self) -> None:
        await self.async_page(lambda rv: None)

    async def async_run(self, job: Callable[..., Any], *args: Any) -> Any:
        """job(*args) in the executor: a decision, or something entered on the Contacts pages."""
        return await self.hass.async_add_executor_job(job, *args)

    def next_check_at(self) -> datetime:
        now = datetime.now(self.tz)
        day = now.date() if now.time() < self.check_time else now.date() + timedelta(days=1)
        return datetime.combine(day, self.check_time, tzinfo=self.tz)

    def when(self, stamp: str) -> str:
        return fmt_time(datetime.fromisoformat(stamp).astimezone(self.tz))

    def home(self, rv: dict | None) -> dict:
        """The Contact Sync page: every account at the latest check, the review in brief, and the last apply."""
        status = check.load_status()
        result = apply.load_result()
        return {
            "accounts": status["accounts"] if status else None,
            "checked": self.when(status["checked_at"]) if status and status["checked_at"] else "",
            "next_check": fmt_time(self.next_check_at()),
            "checking": self.checking, "applying": self.applying, "check_error": self.check_error,
            "set_up": bool(check.icloud_accounts() or check.google_accounts()),
            "review": review.summary(rv),
            "last_apply": {"when": self.when(result["finished_at"]), "summary": apply.summary(result)} if result else None,
        }

    def apply_page(self, rv: dict | None, person: str | None) -> dict | None:
        data = review.apply_data(rv, person, self.checking)
        return data and {**data, "applying": self.applying}

    def result_page(self) -> dict:
        """How far an apply has got, or what the last one did. It doesn't need the review, which isn't rebuilt each
        time the page follows along."""
        return review.result_data(apply.load_result(), self.progress if self.applying else None, self.when)

    def save(self, key: str, raw: dict) -> dict:
        """What was entered on a contact's form: {"saved", "unchanged"}, or {"form"} to show it again."""
        saved = editor.save(self.options, key, raw)
        if "key" in saved:
            return {"saved": saved["key"], "unchanged": saved["unchanged"]}
        return {"form": editor.form_data(review.current_plan(self.options), key, saved["entered"],
                                         tuple(saved["errors"]), tuple(saved["similar"]))}


def _check(options: dict, daily: bool) -> str:
    """A check, then what the daily notification says if this is the daily one."""
    check.run_check(options)
    review.tidy_decisions(options)
    apply.record_start(options)
    return review.waiting_message(options) if daily and options[CONF_NOTIFY] else ""


def _forget_removed(keys: set[str], revoked: list[str]) -> None:
    """Delete what was saved from accounts that have been removed, and cancel their sign-ins at Google."""
    for key in check.saved_accounts() - keys:
        check.forget(key)
    for token in revoked:
        google.revoke(token)
