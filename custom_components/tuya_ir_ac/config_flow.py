"""Config flow for the Tuya IR AC Remote integration.

Each config entry represents one AC unit reachable through a Tuya local IR
hub (host/device_id/local_key are stored per-entry; if you have multiple AC
units on the same physical hub, add the integration again with the same
hub fields and a different name/brand/variant).

Two ways to supply the hub's host/device_id/local_key:
  - "manual": type them in directly (from the tinytuya wizard CLI, etc).
  - "cloud": authenticate once with a Tuya Cloud API Access ID/Secret and
    pick the hub (and optionally a paired sub-device, for a friendly name/
    brand hint) from a fetched device list instead of copy-pasting. Cloud
    credentials are used only during this flow -- runtime IR control stays
    100% local either way. See tuya_cloud.py.

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
    API_REGIONS,
    BRAND_GENERIC,
    BRANDS,
    CONF_ACCESS_ID,
    CONF_ACCESS_SECRET,
    CONF_API_REGION,
    CONF_BRAND,
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_PROTOCOL_VERSION,
    CONF_VARIANT,
    DEFAULT_API_REGION,
    DEFAULT_PROTOCOL_VERSION,
    DOMAIN,
    LEARN_PUNCH_LIST,
    LEARN_TIMEOUT,
    PROTOCOL_VERSIONS,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
)
from .tuya_cloud import (
    TuyaCloudAuthError,
    TuyaCloudClient,
    TuyaCloudDevice,
    TuyaCloudError,
)
from .tuya_ir import (
    TuyaIrAuthError,
    TuyaIrConnectionError,
    TuyaIrError,
    TuyaIrHub,
    TuyaIrTimeoutError,
)

_LOGGER = logging.getLogger(__name__)

# Sentinel used in the sub-device picker when the user wants to skip it.
_SKIP_SUBDEVICE = "__skip__"


def _find_saved_cloud_credentials(hass: Any) -> dict[str, str]:
    """Return cloud credentials saved on an existing entry, if any."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if CONF_ACCESS_ID in entry.data:
            return {
                CONF_ACCESS_ID: entry.data[CONF_ACCESS_ID],
                CONF_ACCESS_SECRET: entry.data[CONF_ACCESS_SECRET],
                CONF_API_REGION: entry.data.get(CONF_API_REGION, DEFAULT_API_REGION),
            }
    return {}


def _marker(key: str, defaults: dict[str, str], fallback: str | None = None):
    """vol.Required with a default pulled from `defaults` (or `fallback`)."""
    if key in defaults:
        return vol.Required(key, default=defaults[key])
    if fallback is not None:
        return vol.Required(key, default=fallback)
    return vol.Required(key)


class TuyaIrAcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for one Tuya IR AC unit."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._cloud_devices: list[TuyaCloudDevice] = []
        self._cloud_subdevices: list[TuyaCloudDevice] = []
        self._suggested_name: str | None = None
        self._suggested_brand: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Entry point: choose manual entry or Tuya Cloud-assisted discovery."""
        return self.async_show_menu(step_id="user", menu_options=["manual", "cloud"])

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manual path: hub connection fields, validated by connecting."""
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
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Cloud path: authenticate and fetch the account's device list."""
        errors: dict[str, str] = {}
        defaults = _find_saved_cloud_credentials(self.hass)

        if user_input is not None:
            client = TuyaCloudClient(
                self.hass,
                access_id=user_input[CONF_ACCESS_ID],
                access_secret=user_input[CONF_ACCESS_SECRET],
                region=user_input[CONF_API_REGION],
            )
            devices: list[TuyaCloudDevice] = []
            try:
                devices = await client.async_list_devices()
            except TuyaCloudAuthError:
                errors["base"] = "invalid_auth"
            except TuyaCloudError:
                errors["base"] = "cannot_connect"
            else:
                if not devices:
                    errors["base"] = "no_devices_found"

            if not errors:
                self._cloud_devices = devices
                self._data[CONF_ACCESS_ID] = user_input[CONF_ACCESS_ID]
                self._data[CONF_ACCESS_SECRET] = user_input[CONF_ACCESS_SECRET]
                self._data[CONF_API_REGION] = user_input[CONF_API_REGION]
                return await self.async_step_cloud_hub()

            # Re-show with what the user just typed, not the stale saved creds.
            defaults = user_input

        schema = vol.Schema(
            {
                _marker(CONF_ACCESS_ID, defaults): str,
                _marker(CONF_ACCESS_SECRET, defaults): str,
                _marker(
                    CONF_API_REGION, defaults, fallback=DEFAULT_API_REGION
                ): vol.In(API_REGIONS),
            }
        )
        return self.async_show_form(step_id="cloud", data_schema=schema, errors=errors)

    async def async_step_cloud_hub(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Pick which cloud device is the physical IR hub."""
        # Heuristic: a hub/gateway device has no gateway_id of its own. If
        # nothing matches that (unexpected account shape), fall back to
        # showing every device so the user can still pick manually.
        hub_candidates = [d for d in self._cloud_devices if not d.gateway_id]
        if not hub_candidates:
            hub_candidates = list(self._cloud_devices)

        options = {
            device.device_id: f"{device.name} ({device.device_id})"
            for device in hub_candidates
        }

        if user_input is not None:
            selected_id = user_input[CONF_DEVICE_ID]
            hub = next(d for d in hub_candidates if d.device_id == selected_id)
            self._data[CONF_DEVICE_ID] = hub.device_id
            self._data[CONF_LOCAL_KEY] = hub.local_key
            self._suggested_name = hub.name

            self._cloud_subdevices = [
                d for d in self._cloud_devices if d.gateway_id == hub.device_id
            ]
            if self._cloud_subdevices:
                return await self.async_step_cloud_subdevice()
            return await self.async_step_cloud_host()

        schema = vol.Schema({vol.Required(CONF_DEVICE_ID): vol.In(options)})
        return self.async_show_form(step_id="cloud_hub", data_schema=schema)

    async def async_step_cloud_subdevice(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Optionally pick a paired sub-device for a friendly name/brand hint.

        This never changes device_id/local_key -- local IR send/learn always
        targets the physical hub selected in the previous step. A sub-device
        selection here only prefills the display name and a best-effort
        brand guess for later steps.
        """
        options = {device.device_id: device.name for device in self._cloud_subdevices}
        options[_SKIP_SUBDEVICE] = "None of these / use hub directly"

        if user_input is not None:
            selected_id = user_input["subdevice"]
            if selected_id != _SKIP_SUBDEVICE:
                sub = next(
                    d for d in self._cloud_subdevices if d.device_id == selected_id
                )
                self._suggested_name = sub.name
                product_text = (sub.product_name or "").lower()
                for brand in BRANDS:
                    if brand != BRAND_GENERIC and brand in product_text:
                        self._suggested_brand = brand
                        break
            return await self.async_step_cloud_host()

        schema = vol.Schema(
            {vol.Required("subdevice", default=_SKIP_SUBDEVICE): vol.In(options)}
        )
        return self.async_show_form(step_id="cloud_subdevice", data_schema=schema)

    async def async_step_cloud_host(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Cloud can't see LAN topology -- ask for the hub's local IP."""
        errors: dict[str, str] = {}
        if user_input is not None:
            hub = TuyaIrHub(
                self.hass,
                host=user_input[CONF_HOST],
                device_id=self._data[CONF_DEVICE_ID],
                local_key=self._data[CONF_LOCAL_KEY],
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
                self._data[CONF_NAME] = user_input[CONF_NAME]
                self._data[CONF_HOST] = user_input[CONF_HOST]
                self._data[CONF_PROTOCOL_VERSION] = user_input[CONF_PROTOCOL_VERSION]
                await self.async_set_unique_id(
                    f"{self._data[CONF_DEVICE_ID]}_{self._data[CONF_NAME]}"
                )
                self._abort_if_unique_id_configured()
                return await self.async_step_brand()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=self._suggested_name): str,
                vol.Required(CONF_HOST): str,
                vol.Required(
                    CONF_PROTOCOL_VERSION, default=DEFAULT_PROTOCOL_VERSION
                ): vol.In(PROTOCOL_VERSIONS),
            }
        )
        return self.async_show_form(
            step_id="cloud_host", data_schema=schema, errors=errors
        )

    async def async_step_brand(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Which brand is this AC unit (pre-selected if cloud gave a hint)."""
        if user_input is not None:
            self._data[CONF_BRAND] = user_input[CONF_BRAND]
            return await self.async_step_variant()

        default_brand = self._suggested_brand or BRANDS[0]
        schema = vol.Schema(
            {vol.Required(CONF_BRAND, default=default_brand): vol.In(BRANDS)}
        )
        return self.async_show_form(step_id="brand", data_schema=schema)

    async def async_step_variant(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Which built-in protocol variant to start from."""
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
