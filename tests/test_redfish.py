# tests/test_redfish.py
import pytest
import httpx
import respx
from redfish import RedfishClient

BASE = "https://192.0.2.1/redfish/v1"


@pytest.fixture
def client():
    return RedfishClient("192.0.2.1", "admin", "testpass")


@respx.mock
async def test_get_status(client):
    respx.get(f"{BASE}/Systems/1").mock(return_value=httpx.Response(200, json={
        "PowerState": "On",
        "Status": {"HealthRollup": "OK"},
        "IndicatorLED": "Off",
        "Oem": {"Hpe": {"PostState": "FinishedPost"}},
        "BiosVersion": "U30 v2.76",
    }))
    respx.get(f"{BASE}/Managers/1").mock(return_value=httpx.Response(200, json={
        "FirmwareVersion": "iLO 5 v2.55",
    }))

    result = await client.get_status()

    assert result == {
        "power": "On",
        "health": "OK",
        "uid": "Off",
        "post_state": "FinishedPost",
        "bios_ver": "U30 v2.76",
        "ilo_ver": "iLO 5 v2.55",
    }


@respx.mock
async def test_get_status_missing_oem_fields(client):
    """get_status handles iLO responses with missing optional fields."""
    respx.get(f"{BASE}/Systems/1").mock(return_value=httpx.Response(200, json={
        "PowerState": "Off",
        "Status": {"HealthRollup": "OK"},
    }))
    respx.get(f"{BASE}/Managers/1").mock(return_value=httpx.Response(200, json={}))

    result = await client.get_status()

    assert result["power"] == "Off"
    assert result["uid"] == "Off"
    assert result["post_state"] == "Unknown"
    assert result["ilo_ver"] == "Unknown"
