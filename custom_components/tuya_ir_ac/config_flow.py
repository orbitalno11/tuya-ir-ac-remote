"""Config flow for the Tuya IR AC Remote integration.

Each config entry represents one AC unit reachable through a Tuya local IR
hub (host/device_id/local_key are stored per-entry; if you have multiple AC
units on the same physical hub, add the integration again with the same
hub fields and a different name/brand/variant).

The options flow implements "Learn Command": capturing real IR codes from
the user's physical remote to override/extend the bundled best-effort
built-in code tables.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .codes.loader import list_variants
from .const import (
    BRANDS,
    CONF_BRAND,
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_PROTOCOL_VERSION,
    CONF_VARIANT,
    DEFAULT_PROTOCOL_VERSION,
    DOMAIN,
    LEARN_PUNCH_LIST,
    LEARN_TIMEOUT,
    PROTOCOL_VERSIONS,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
)
from .tuya_ir import (
    TuyaIrAuthError,
    TuyaIrConnectionError,
    TuyaIrError,
    TuyaIrHub,
    TuyaIrTimeoutError,
)

_LOGGER = logging.getLogger(__name__)


class TuyaIrAcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for one Tuya IR AC unit."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """First step: hub connection fields, validated by connecting."""
        errors: dict[str, str] = {}
        if user_input is not None:
            hub = TuyaIrHub(
                self.hass,
                host=user_input[CONF_HOST],
                device_id=user_input[CONF_DEVICE_ID],
                local_key=user_input[CONF_LOCAL_KEY],
                version=user_input[CONF_PROTOCOL_VERSION],
            )
            try:
                await hub.async_check_connection()
            except TuyaIrAuthError:
                errors["base"] = "invalid_auth"
            except TuyaIrConnectionError:
                errors["base"] = "cannot_connect"
            except TuyaIrError:
                errors["base"] = "unknown"

            if not errors:
                self._data = dict(user_input)
                await self.async_set_unique_id(
                    f"{self._data[CONF_DEVICE_ID]}_{self._data[CONF_NAME]}"
                )
                self._abort_if_unique_id_configured()
                return await self.async_step_brand()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_DEVICE_ID): str,
                vol.Required(CONF_LOCAL_KEY): str,
                vol.Required(
                    CONF_PROTOCOL_VERSION, default=DEFAULT_PROTOCOL_VERSION
                ): vol.In(PROTOCOL_VERSIONS),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_brand(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Second step: which brand is this AC unit."""
        if user_input is not None:
            self._data[CONF_BRAND] = user_input[CONF_BRAND]
            return await self.async_step_variant()

        schema = vol.Schema(
            {vol.Required(CONF_BRAND, default=BRANDS[0]): vol.In(BRANDS)}
        )
        return self.async_show_form(step_id="brand", data_schema=schema)

    async def async_step_variant(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Third step: which built-in protocol variant to start from."""
        brand = self._data[CONF_BRAND]
        variants = list_variants(brand) or ["generic"]

        if user_input is not None:
            self._data[CONF_VARIANT] = user_input[CONF_VARIANT]
            return self.async_create_entry(
                title=self._data[CONF_NAME], data=self._data
            )

        schema = vol.Schema(
            {vol.Required(CONF_VARIANT, default=variants[0]): vol.In(variants)}
        )
        return self.async_show_form(
            step_id="variant",
            data_schema=schema,
            description_placeholders={"brand": brand},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TuyaIrAcOptionsFlow:
        """Get the Learn Command options flow for an existing entry."""
        return TuyaIrAcOptionsFlow()


class TuyaIrAcOptionsFlow(config_entries.OptionsFlow):
    """Learn Command flow: capture real IR codes from the user's remote.

    Uses self.handler (the config entry_id, set by the flow manager for
    every options flow) instead of self.config_entry: older Home Assistant
    versions require config_entry to be stored manually in __init__, while
    current versions expose it as a read-only property populated by the
    flow manager -- assigning to it directly raises AttributeError on those
    versions. self.handler is stable and available on both.
    """

    def __init__(self) -> None:
        self._pending_keys: list[str] = []
        self._current_key: str | None = None
        self._captured: dict[str, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Let the user pick which state(s) to (re)learn."""
        if user_input is not None:
            selected = user_input.get("keys", [])
            if not selected:
                return self.async_abort(reason="no_keys_selected")
            self._pending_keys = list(selected)
            self._captured = {}
            return await self._async_advance_capture()

        schema = vol.Schema(
            {
                vol.Required("keys", default=[]): cv.multi_select(
                    {key: key for key in LEARN_PUNCH_LIST}
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def _async_advance_capture(self) -> config_entries.ConfigFlowResult:
        """Move to the next pending key, or finish and persist captured codes."""
        if not self._pending_keys:
            entry_id = self.handler
            entry_data = self.hass.data[DOMAIN][entry_id]
            entry_data["learned_codes"].update(self._captured)
            store: Store = entry_data["store"]
            await store.async_save(entry_data["learned_codes"])
            await self.hass.config_entries.async_reload(entry_id)
            return self.async_create_entry(title="", data={})

        self._current_key = self._pending_keys[0]
        return await self.async_step_capture()

    async def async_step_capture(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Prompt the user to press a button, then capture the IR code."""
        key = self._current_key
        errors: dict[str, str] = {}

        if user_input is not None:
            hub: TuyaIrHub = self.hass.data[DOMAIN][self.handler]["hub"]
            try:
                code = await hub.async_learn_code(timeout=LEARN_TIMEOUT)
            except TuyaIrTimeoutError:
                errors["base"] = "learn_timeout"
            except TuyaIrError:
                errors["base"] = "cannot_connect"

            if not errors:
                self._captured[key] = code
                self._pending_keys.pop(0)
                return await self._async_advance_capture()

        return self.async_show_form(
            step_id="capture",
            data_schema=vol.Schema({}),
            description_placeholders={"state_key": key, "timeout": str(LEARN_TIMEOUT)},
            errors=errors,
        )
