"""Unit tests for the tuya_ir.TuyaIrHub wrapper.

tinytuya.Contrib.IRRemoteControlDevice is fully mocked -- no real sockets
are ever touched. These tests only verify that TuyaIrHub drives that class
correctly and translates its failures into our own exception types.
"""
from unittest.mock import MagicMock, patch

import pytest
from tinytuya.core.exceptions import DecodeError

from custom_components.tuya_ir_ac.tuya_ir import (
    TuyaIrAuthError,
    TuyaIrConnectionError,
    TuyaIrHub,
    TuyaIrTimeoutError,
)

PATCH_TARGET = "tinytuya.Contrib.IRRemoteControlDevice.IRRemoteControlDevice"


def _make_hub(hass):
    return TuyaIrHub(
        hass,
        host="192.168.1.50",
        device_id="abc123",
        local_key="secretkey",
        version="3.3",
    )


async def test_check_connection_success(hass):
    hub = _make_hub(hass)
    mock_device = MagicMock()
    mock_device.control_type = 1
    with patch(PATCH_TARGET, return_value=mock_device) as mock_cls:
        await hub.async_check_connection()
    mock_cls.assert_called_once_with(
        "abc123", "192.168.1.50", "secretkey", version=3.3, persist=False
    )
    mock_device.close.assert_called_once()


async def test_check_connection_no_control_type_raises_connection_error(hass):
    hub = _make_hub(hass)
    mock_device = MagicMock()
    mock_device.control_type = 0
    with patch(PATCH_TARGET, return_value=mock_device):
        with pytest.raises(TuyaIrConnectionError):
            await hub.async_check_connection()
    mock_device.close.assert_called_once()


async def test_check_connection_decode_error_raises_auth_error(hass):
    hub = _make_hub(hass)
    with patch(PATCH_TARGET, side_effect=DecodeError("bad key")):
        with pytest.raises(TuyaIrAuthError):
            await hub.async_check_connection()


async def test_check_connection_os_error_raises_connection_error(hass):
    hub = _make_hub(hass)
    with patch(PATCH_TARGET, side_effect=OSError("unreachable")):
        with pytest.raises(TuyaIrConnectionError):
            await hub.async_check_connection()


async def test_send_code_success(hass):
    hub = _make_hub(hass)
    mock_device = MagicMock()
    mock_device.control_type = 1
    with patch(PATCH_TARGET, return_value=mock_device):
        await hub.async_send_code("BASE64CODE==")
    mock_device.send_button.assert_called_once_with("BASE64CODE==")
    mock_device.close.assert_called_once()


async def test_send_code_retries_then_raises(hass):
    hub = _make_hub(hass)
    with patch(PATCH_TARGET, side_effect=OSError("dropped")) as mock_cls:
        with pytest.raises(TuyaIrConnectionError):
            await hub.async_send_code("BASE64CODE==")
    # initial attempt + CONNECT_RETRIES retries
    assert mock_cls.call_count == 3


async def test_send_code_succeeds_after_one_retry(hass):
    hub = _make_hub(hass)
    mock_device = MagicMock()
    mock_device.control_type = 1
    with patch(
        PATCH_TARGET, side_effect=[OSError("dropped"), mock_device]
    ) as mock_cls:
        await hub.async_send_code("BASE64CODE==")
    assert mock_cls.call_count == 2
    mock_device.send_button.assert_called_once_with("BASE64CODE==")


async def test_learn_code_success(hass):
    hub = _make_hub(hass)
    mock_device = MagicMock()
    mock_device.control_type = 1
    mock_device.receive_button.return_value = "LEARNEDCODE=="
    with patch(PATCH_TARGET, return_value=mock_device):
        code = await hub.async_learn_code(timeout=15)
    assert code == "LEARNEDCODE=="
    mock_device.receive_button.assert_called_once_with(timeout=15)
    mock_device.close.assert_called_once()


async def test_learn_code_timeout_raises(hass):
    hub = _make_hub(hass)
    mock_device = MagicMock()
    mock_device.control_type = 1
    mock_device.receive_button.return_value = None
    with patch(PATCH_TARGET, return_value=mock_device):
        with pytest.raises(TuyaIrTimeoutError):
            await hub.async_learn_code(timeout=15)
