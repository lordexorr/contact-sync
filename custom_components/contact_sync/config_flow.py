"""Setting up Contact Sync: the entry itself, its options, the Google app, and one sub-entry per account."""
from __future__ import annotations

from typing import Any

import requests
import voluptuous as vol

from homeassistant.config_entries import (SOURCE_RECONFIGURE, ConfigEntry, ConfigFlow, ConfigFlowResult, ConfigSubentry,
                                          ConfigSubentryFlow, OptionsFlow, SubentryFlowResult)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (CONF_CHECK_TIME, CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_NOTIFY, DEFAULT_CHECK_TIME, DOMAIN,
                    SUBENTRY_GOOGLE, SUBENTRY_ICLOUD)
from .engine import check, google
from .engine.icloud import ICloudError

PASSWORD = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
APP_SCHEMA = vol.Schema({vol.Required(CONF_CLIENT_ID): str, vol.Required(CONF_CLIENT_SECRET): PASSWORD})


class ContactSyncConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Contact Sync", data={},
                                           options={CONF_CHECK_TIME: DEFAULT_CHECK_TIME, CONF_NOTIFY: ""})
        return self.async_show_form(step_id="user")

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The Google app: the client ID and secret every Google account signs in through."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            # The entry's update listener reloads it with the new app.
            return self.async_update_and_abort(entry, data_updates={
                CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip(),
                CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET].strip()})
        return self.async_show_form(step_id="reconfigure", data_schema=self.add_suggested_values_to_schema(
            APP_SCHEMA, {CONF_CLIENT_ID: entry.data.get(CONF_CLIENT_ID, "")}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ContactSyncOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_ICLOUD: ICloudAccountFlow, SUBENTRY_GOOGLE: GoogleAccountFlow}


class ContactSyncOptionsFlow(OptionsFlow):
    """When the daily check runs, and who's told afterwards when changes are waiting."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            target = user_input.get(CONF_NOTIFY, "").strip()
            domain, _, name = target.partition(".")
            if target and (domain != "notify" or not (self.hass.states.get(target)
                                                     or self.hass.services.has_service("notify", name))):
                errors[CONF_NOTIFY] = "notify_unknown"
            else:
                return self.async_create_entry(data={CONF_CHECK_TIME: user_input[CONF_CHECK_TIME], CONF_NOTIFY: target})
        schema = vol.Schema({vol.Required(CONF_CHECK_TIME): selector.TimeSelector(),
                             vol.Optional(CONF_NOTIFY, default=""): str})
        return self.async_show_form(step_id="init", errors=errors, data_schema=self.add_suggested_values_to_schema(
            schema, user_input or self.config_entry.options))


def _taken(entry: ConfigEntry, unique_id: str) -> bool:
    return any(s.unique_id == unique_id for s in entry.subentries.values())


class ICloudAccountFlow(ConfigSubentryFlow):
    """An iCloud account, signed in with an app-specific password. Reconfiguring it changes the label or password;
    the Apple ID stays, since everything saved from it is filed under it."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._async_account("user", user_input, None)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._async_account("reconfigure", user_input, self._get_reconfigure_subentry())

    async def _async_account(self, step_id: str, user_input: dict[str, Any] | None,
                             subentry: ConfigSubentry | None) -> SubentryFlowResult:
        errors, placeholders = {}, {"error": ""}
        if user_input is not None:
            apple_id = subentry.data["apple_id"] if subentry else user_input["apple_id"].strip()
            account = {"label": user_input.get("label", "").strip(), "apple_id": apple_id,
                       "app_password": user_input["app_password"].strip()}
            unique_id = f"icloud:{apple_id.lower()}"
            if subentry is None and _taken(self._get_entry(), unique_id):
                return self.async_abort(reason="already_configured")
            try:
                await self.hass.async_add_executor_job(check.test_icloud_account, account)
            except ICloudError as err:
                errors["base"], placeholders["error"] = "refused", str(err)
            except requests.RequestException as err:
                errors["base"], placeholders["error"] = "cannot_connect", str(err)
            else:
                title = account["label"] or apple_id
                if subentry:
                    return self.async_update_and_abort(self._get_entry(), subentry, data=account, title=title)
                return self.async_create_entry(title=title, data=account, unique_id=unique_id)
        fields = {vol.Optional("label", default=""): str}
        if subentry is None:
            fields[vol.Required("apple_id")] = str
        fields[vol.Required("app_password")] = PASSWORD
        suggested = {"label": subentry.data["label"]} if subentry else {}
        if user_input:
            suggested = {k: v for k, v in user_input.items() if k != "app_password"}
        return self.async_show_form(step_id=step_id, errors=errors, description_placeholders=placeholders,
                                    data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), suggested))


class GoogleAccountFlow(ConfigSubentryFlow):
    """A Google account, signed in on Google's own page through the Google app. Google then sends the browser to an
    address nothing answers, which is pasted back here: it carries the sign-in code. Reconfiguring it signs the same
    account in again, for when Google stops accepting its sign-in, and keeps everything saved from it."""

    _attempt: dict | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        entry = self._get_entry()
        if not (entry.data.get(CONF_CLIENT_ID) and entry.data.get(CONF_CLIENT_SECRET)):
            return await self.async_step_app()
        return await self.async_step_sign_in()

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self.async_step_sign_in()

    async def async_step_app(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """The Google app, once, before the first Google account."""
        if user_input is not None:
            entry = self._get_entry()
            self.hass.config_entries.async_update_entry(entry, data={
                **entry.data, CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip(),
                CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET].strip()})
            return await self.async_step_sign_in()
        return self.async_show_form(step_id="app", data_schema=APP_SCHEMA)

    async def async_step_sign_in(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        entry = self._get_entry()
        client_id, client_secret = entry.data[CONF_CLIENT_ID], entry.data[CONF_CLIENT_SECRET]
        if self._attempt is None:
            self._attempt = google.start_sign_in(client_id)
        errors, placeholders = {}, {"url": self._attempt["url"], "error": ""}
        if user_input is not None:
            try:
                account = await self.hass.async_add_executor_job(
                    google.finish_sign_in, user_input["url"], self._attempt, client_id, client_secret)
            except google.GoogleError as err:
                errors["base"], placeholders["error"] = "refused", str(err)
            except requests.RequestException as err:
                errors["base"], placeholders["error"] = "cannot_connect", str(err)
            else:
                unique_id = f"google:{account['email'].lower()}"
                if self.source == SOURCE_RECONFIGURE:
                    subentry = self._get_reconfigure_subentry()
                    if subentry.unique_id == unique_id:
                        # Its saved data stays filed under the email as first added; the old sign-in is cancelled.
                        await self.hass.async_add_executor_job(google.revoke, subentry.data["refresh_token"])
                        return self.async_update_and_abort(entry, subentry, data={**subentry.data,
                                                                                  "refresh_token": account["refresh_token"]})
                    await self.hass.async_add_executor_job(google.revoke, account["refresh_token"])
                    errors["base"], placeholders["error"] = "refused", (
                        f"That signed in as {account['email']}. Sign in as {subentry.data['email']}, or add "
                        f"{account['email']} as another account.")
                    self._attempt = google.start_sign_in(client_id)  # a code works once, so this sign-in starts over
                    placeholders["url"] = self._attempt["url"]
                elif _taken(entry, unique_id):
                    await self.hass.async_add_executor_job(google.revoke, account["refresh_token"])
                    return self.async_abort(reason="already_configured")
                else:
                    return self.async_create_entry(title=account["email"], data=account, unique_id=unique_id)
        return self.async_show_form(step_id="sign_in", errors=errors, description_placeholders=placeholders,
                                    data_schema=vol.Schema({vol.Required("url"): str}))
