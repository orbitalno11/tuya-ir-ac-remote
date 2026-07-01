"""Unit tests for the tuya_cloud.TuyaCloudClient wrapper.

tinytuya.Cloud is fully mocked -- no real HTTP calls are ever made. These
tests only verify that TuyaCloudClient drives that class correctly and
translates its failures into our own exception types.
"""
from unittest.mock import MagicMock, patch

import pytest

from custom_components.tuya_ir_ac.tuya_cloud import (
    TuyaCloudAuthError,
    TuyaCloudClient,
    TuyaCloudError,
)

PATCH_TARGET = "tinytuya.Cloud"

RAW_DEVICES = [
    {
        "id": "hub123",
        "name": "Living Room IR Hub",
        "key": "hublocalkey==",
        "category": "wnykq",
        "product_name": "Universal Smart IR Remote",
    },
    {
        "id": "sub456",
        "name": "Living Room AC (Panasonic)",
        "key": "sublocalkey==",
        "gateway_id": "hub123",
        "category": "infrared_ac",
        "product_name": "Panasonic AC",
    },
    {
        # malformed entry missing "id" -- must be skipped, not crash
        "name": "Broken entry",
        "key": "x",
    },
]


def _make_client(hass):
    return TuyaCloudClient(
        hass, access_id="myaccessid", access_secret="myaccesssecret", region="us"
    )


async def test_list_devices_success(hass):
    client = _make_client(hass)
    mock_cloud = MagicMock()
    mock_cloud.token = "faketoken"
    mock_cloud.getdevices.return_value = RAW_DEVICES
    with patch(PATCH_TARGET, return_value=mock_cloud) as mock_cls:
        devices = await client.async_list_devices()

    mock_cls.assert_called_once_with(
        apiRegion="us", apiKey="myaccessid", apiSecret="myaccesssecret"
    )
    assert len(devices) == 2  # malformed entry skipped
    hub, sub = devices
    assert hub.device_id == "hub123"
    assert hub.name == "Living Room IR Hub"
    assert hub.local_key == "hublocalkey=="
    assert hub.gateway_id is None
    assert sub.device_id == "sub456"
    assert sub.gateway_id == "hub123"
    assert sub.category == "infrared_ac"


async def test_list_devices_missing_credentials_raises_auth_error(hass):
    client = _make_client(hass)
    with patch(PATCH_TARGET, side_effect=TypeError("Tuya Cloud Key and Secret required")):
        with pytest.raises(TuyaCloudAuthError):
            await client.async_list_devices()


async def test_list_devices_bad_credentials_no_token_raises_auth_error(hass):
    client = _make_client(hass)
    mock_cloud = MagicMock()
    mock_cloud.token = None
    mock_cloud.error = {"Error": "Unable to Get Cloud Token", "Err": "911"}
    with patch(PATCH_TARGET, return_value=mock_cloud):
        with pytest.raises(TuyaCloudAuthError, match="Unable to Get Cloud Token"):
            await client.async_list_devices()


async def test_list_devices_getdevices_error_dict_raises_cloud_error(hass):
    client = _make_client(hass)
    mock_cloud = MagicMock()
    mock_cloud.token = "faketoken"
    mock_cloud.getdevices.return_value = {
        "Error": "Error Response from Tuya Cloud",
        "Err": "913",
    }
    with patch(PATCH_TARGET, return_value=mock_cloud):
        with pytest.raises(TuyaCloudError, match="Error Response from Tuya Cloud"):
            await client.async_list_devices()


async def test_list_devices_empty_list(hass):
    client = _make_client(hass)
    mock_cloud = MagicMock()
    mock_cloud.token = "faketoken"
    mock_cloud.getdevices.return_value = []
    with patch(PATCH_TARGET, return_value=mock_cloud):
        devices = await client.async_list_devices()
    assert devices == []
