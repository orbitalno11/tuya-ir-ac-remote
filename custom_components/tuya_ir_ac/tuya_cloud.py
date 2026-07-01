"""Tuya Cloud API wrapper used only during config-flow device discovery.

Setup-time convenience only -- once a config entry is created, the
integration never talks to the Tuya Cloud again; all runtime IR send/learn
stays local via tuya_ir.TuyaIrHub. This module exists purely to let the
config flow list the user's Tuya devices (so they can pick the physical IR
hub, and optionally a paired sub-device for a friendly name/brand hint)
instead of manually running the tinytuya wizard CLI and copy-pasting
device_id/local_key.

tinytuya.Cloud is blocking/synchronous (does real HTTP calls), so every
public method here runs the actual work in the executor, mirroring the
pattern used in tuya_ir.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_AUTH_HINT = (
    "Could not authenticate with the Tuya Cloud API -- check your Access ID/"
    "Secret and region, and confirm your Tuya IoT Platform project's Cloud "
    "Development subscription hasn't expired (see https://iot.tuya.com)."
)


class TuyaCloudError(Exception):
    """Base error for Tuya Cloud API communication."""


class TuyaCloudAuthError(TuyaCloudError):
    """The Access ID/Secret are missing, invalid, or unauthorized."""


@dataclass
class TuyaCloudDevice:
    """A single device returned by the Tuya Cloud device list."""

    device_id: str
    name: str
    local_key: str
    gateway_id: str | None
    category: str
    product_name: str


class TuyaCloudClient:
    """Async-friendly handle to the Tuya Cloud API, for discovery only."""

    def __init__(
        self,
        hass: HomeAssistant,
        access_id: str,
        access_secret: str,
        region: str,
    ) -> None:
        self._hass = hass
        self._access_id = access_id
        self._access_secret = access_secret
        self._region = region

    def _list_devices_sync(self) -> list[TuyaCloudDevice]:
        from tinytuya import Cloud  # noqa: PLC0415

        try:
            cloud = Cloud(
                apiRegion=self._region,
                apiKey=self._access_id,
                apiSecret=self._access_secret,
            )
        except TypeError as err:
            # tinytuya raises TypeError synchronously if apiKey/apiSecret
            # are missing/empty.
            raise TuyaCloudAuthError(str(err)) from err

        if not cloud.token:
            # Cloud() does not raise on a bad key/secret pair -- it stores
            # the failure in cloud.error and leaves cloud.token as None.
            detail = None
            if isinstance(cloud.error, dict):
                detail = cloud.error.get("Error")
            raise TuyaCloudAuthError(detail or _AUTH_HINT)

        result = cloud.getdevices()
        if isinstance(result, dict):
            # getdevices() returns an error_json dict (has an "Error" key)
            # on failure, or a list of device dicts on success.
            raise TuyaCloudError(result.get("Error", "Unknown error listing devices"))

        devices: list[TuyaCloudDevice] = []
        for raw in result:
            device_id = raw.get("id")
            if not device_id:
                continue
            devices.append(
                TuyaCloudDevice(
                    device_id=device_id,
                    name=raw.get("name") or device_id,
                    local_key=raw.get("key", ""),
                    gateway_id=raw.get("gateway_id") or None,
                    category=raw.get("category", ""),
                    product_name=raw.get("product_name", ""),
                )
            )
        return devices

    async def async_list_devices(self) -> list[TuyaCloudDevice]:
        """Authenticate and return the account's device list."""
        return await self._hass.async_add_executor_job(self._list_devices_sync)
