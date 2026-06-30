"""Local-network wrapper around tinytuya's Tuya IR hub support.

Isolates the rest of the integration from tinytuya specifics: all tinytuya
calls are blocking/synchronous, so every public method here runs the actual
work in the executor. Each call opens a short-lived connection (connect,
do one thing, close) rather than keeping a persistent shared socket --
simpler and avoids cross-entity locking, at the cost of a small per-command
connection overhead.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONNECT_RETRIES

_LOGGER = logging.getLogger(__name__)


class TuyaIrError(Exception):
    """Base error for Tuya IR hub communication."""


class TuyaIrConnectionError(TuyaIrError):
    """Could not reach, or could not detect the control type of, the hub."""


class TuyaIrAuthError(TuyaIrError):
    """The local_key appears to be wrong (payload decode failure)."""


class TuyaIrTimeoutError(TuyaIrError):
    """No button press was received on a real remote within the timeout."""


class TuyaIrHub:
    """Async-friendly handle to a single Tuya local-network IR hub."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        device_id: str,
        local_key: str,
        version: str = "3.3",
    ) -> None:
        self._hass = hass
        self._host = host
        self._device_id = device_id
        self._local_key = local_key
        self._version = float(version)

    def _build_device(self) -> Any:
        # Imported lazily so unit tests can run without tinytuya installed
        # by mocking this method instead.
        from tinytuya.core.exceptions import DecodeError  # noqa: PLC0415
        from tinytuya.Contrib.IRRemoteControlDevice import (  # noqa: PLC0415
            IRRemoteControlDevice,
        )

        try:
            device = IRRemoteControlDevice(
                self._device_id,
                self._host,
                self._local_key,
                version=self._version,
                persist=False,
            )
        except DecodeError as err:
            raise TuyaIrAuthError(
                f"Could not decode a response from the hub at {self._host} -- "
                "the local_key is likely incorrect"
            ) from err
        except OSError as err:
            raise TuyaIrConnectionError(
                f"Could not connect to the Tuya IR hub at {self._host}: {err}"
            ) from err

        if not device.control_type:
            device.close()
            raise TuyaIrConnectionError(
                f"Could not detect the control type of the Tuya IR hub at "
                f"{self._host} -- device unreachable or local_key is incorrect"
            )

        return device

    def _check_connection_sync(self) -> None:
        device = self._build_device()
        device.close()

    def _send_code_sync(self, base64_code: str) -> None:
        last_err: Exception | None = None
        for attempt in range(CONNECT_RETRIES + 1):
            device = None
            try:
                device = self._build_device()
                device.send_button(base64_code)
                return
            except (TuyaIrConnectionError, OSError) as err:
                last_err = err
                _LOGGER.debug(
                    "send_code attempt %d/%d failed: %s",
                    attempt + 1,
                    CONNECT_RETRIES + 1,
                    err,
                )
            finally:
                if device is not None:
                    device.close()
        raise TuyaIrConnectionError(
            f"Failed to send IR code to {self._host} after "
            f"{CONNECT_RETRIES + 1} attempts: {last_err}"
        ) from last_err

    def _learn_code_sync(self, timeout: int) -> str:
        device = self._build_device()
        try:
            code = device.receive_button(timeout=timeout)
        except OSError as err:
            raise TuyaIrConnectionError(
                f"Lost connection to the hub at {self._host} while learning: {err}"
            ) from err
        finally:
            device.close()

        if not code or not isinstance(code, str):
            raise TuyaIrTimeoutError(
                f"No button press was received within {timeout} seconds"
            )
        return code

    async def async_check_connection(self) -> None:
        """Verify the hub is reachable and the local_key is valid.

        Raises TuyaIrConnectionError or TuyaIrAuthError on failure.
        """
        await self._hass.async_add_executor_job(self._check_connection_sync)

    async def async_send_code(self, base64_code: str) -> None:
        """Transmit a previously learned/known Tuya base64 IR code."""
        await self._hass.async_add_executor_job(self._send_code_sync, base64_code)

    async def async_learn_code(self, timeout: int) -> str:
        """Enter learning mode and wait for a button press on a real remote.

        Returns the captured Tuya base64 code. Raises TuyaIrTimeoutError if
        no button was pressed in time, or TuyaIrConnectionError on a
        connection problem.
        """
        return await self._hass.async_add_executor_job(
            self._learn_code_sync, timeout
        )
