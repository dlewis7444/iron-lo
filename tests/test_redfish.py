# tests/test_redfish.py
import pytest
import httpx
import respx
from redfish import RedfishClient
from config import _ILO_PROFILE, _IDRAC_PROFILE

BASE = "https://192.0.2.1/redfish/v1"


@pytest.fixture
def ilo_client():
    return RedfishClient("192.0.2.1", "admin", "testpass", _ILO_PROFILE)


@pytest.fixture
def idrac_client():
    return RedfishClient("192.0.2.1", "admin", "testpass", _IDRAC_PROFILE)


@respx.mock
async def test_get_status(ilo_client):
    respx.get(f"{BASE}/Systems/1/").mock(return_value=httpx.Response(200, json={
        "PowerState": "On",
        "Status": {"HealthRollup": "OK"},
        "IndicatorLED": "Off",
        "Oem": {"Hpe": {"PostState": "FinishedPost"}},
        "BiosVersion": "U30 v2.76",
    }))
    respx.get(f"{BASE}/Managers/1/").mock(return_value=httpx.Response(200, json={
        "FirmwareVersion": "iLO 5 v2.55",
    }))

    result = await ilo_client.get_status()

    assert result == {
        "power": "On",
        "health": "OK",
        "uid": "Off",
        "post_state": "FinishedPost",
        "bios_ver": "U30 v2.76",
        "bmc_ver": "iLO 5 v2.55",
    }


@respx.mock
async def test_get_status_missing_oem_fields(ilo_client):
    """get_status handles iLO responses with missing optional fields."""
    respx.get(f"{BASE}/Systems/1/").mock(return_value=httpx.Response(200, json={
        "PowerState": "Off",
        "Status": {"HealthRollup": "OK"},
    }))
    respx.get(f"{BASE}/Managers/1/").mock(return_value=httpx.Response(200, json={}))

    result = await ilo_client.get_status()

    assert result["power"] == "Off"
    assert result["uid"] == "Off"
    assert result["post_state"] == "Unknown"
    assert result["bmc_ver"] == "Unknown"


@respx.mock
async def test_power_reset(ilo_client):
    respx.post(f"{BASE}/Systems/1/Actions/ComputerSystem.Reset/").mock(
        return_value=httpx.Response(200, json={})
    )

    result = await ilo_client.power("reset", force=False)

    assert result == {"action": "reset", "reset_type": "GracefulRestart", "result": "accepted"}
    assert respx.calls.last.request.content == b'{"ResetType":"GracefulRestart"}'


@respx.mock
async def test_power_force_off(ilo_client):
    respx.post(f"{BASE}/Systems/1/Actions/ComputerSystem.Reset/").mock(
        return_value=httpx.Response(200, json={})
    )

    result = await ilo_client.power("off", force=True)

    assert result["reset_type"] == "ForceOff"


@respx.mock
async def test_power_nmi_ignores_force(ilo_client):
    respx.post(f"{BASE}/Systems/1/Actions/ComputerSystem.Reset/").mock(
        return_value=httpx.Response(200, json={})
    )

    result_normal = await ilo_client.power("nmi", force=False)
    result_forced = await ilo_client.power("nmi", force=True)

    assert result_normal["reset_type"] == "Nmi"
    assert result_forced["reset_type"] == "Nmi"


@respx.mock
async def test_boot_source_once(ilo_client):
    respx.patch(f"{BASE}/Systems/1/").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{BASE}/Systems/1/").mock(return_value=httpx.Response(200, json={
        "Boot": {
            "BootSourceOverrideTarget": "Pxe",
            "BootSourceOverrideEnabled": "Once",
        }
    }))

    result = await ilo_client.boot_source("pxe", persistent=False)

    assert result == {
        "boot_source_override_target": "Pxe",
        "boot_source_override_enabled": "Once",
    }
    import json
    patch_call = next(c for c in respx.calls if c.request.method == "PATCH")
    assert json.loads(patch_call.request.content) == {
        "Boot": {"BootSourceOverrideTarget": "Pxe", "BootSourceOverrideEnabled": "Once"}
    }


@respx.mock
async def test_boot_source_persistent(ilo_client):
    respx.patch(f"{BASE}/Systems/1/").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{BASE}/Systems/1/").mock(return_value=httpx.Response(200, json={
        "Boot": {
            "BootSourceOverrideTarget": "Hdd",
            "BootSourceOverrideEnabled": "Continuous",
        }
    }))

    result = await ilo_client.boot_source("hdd", persistent=True)

    assert result["boot_source_override_enabled"] == "Continuous"


@respx.mock
async def test_virtual_media_mount(ilo_client):
    respx.get(f"{BASE}/Managers/1/VirtualMedia/2/").mock(
        return_value=httpx.Response(200, json={
            "Inserted": True,
            "ConnectedVia": "URI",
            "Image": "http://fileserver/os.iso",
            "Oem": {"Hpe": {"Actions": {
                "#HpeVirtualMedia.InsertVirtualMedia": {
                    "target": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/Oem/Hpe/HpeVirtualMedia.InsertVirtualMedia/",
                },
                "#HpeVirtualMedia.EjectVirtualMedia": {
                    "target": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/Oem/Hpe/HpeVirtualMedia.EjectVirtualMedia/",
                },
            }}},
        })
    )
    respx.post(f"{BASE}/Managers/1/VirtualMedia/2/Actions/Oem/Hpe/HpeVirtualMedia.InsertVirtualMedia/").mock(
        return_value=httpx.Response(200)
    )

    result = await ilo_client.virtual_media("mount", "http://fileserver/os.iso")

    assert result == {
        "inserted": True,
        "connected": True,
        "image_url": "http://fileserver/os.iso",
        "slot": "2",
    }


@respx.mock
async def test_virtual_media_unmount(ilo_client):
    respx.get(f"{BASE}/Managers/1/VirtualMedia/2/").mock(
        return_value=httpx.Response(200, json={
            "Inserted": False,
            "ConnectedVia": "NotConnected",
            "Image": "",
            "Oem": {"Hpe": {"Actions": {
                "#HpeVirtualMedia.InsertVirtualMedia": {
                    "target": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/Oem/Hpe/HpeVirtualMedia.InsertVirtualMedia/",
                },
                "#HpeVirtualMedia.EjectVirtualMedia": {
                    "target": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/Oem/Hpe/HpeVirtualMedia.EjectVirtualMedia/",
                },
            }}},
        })
    )
    respx.post(f"{BASE}/Managers/1/VirtualMedia/2/Actions/Oem/Hpe/HpeVirtualMedia.EjectVirtualMedia/").mock(
        return_value=httpx.Response(200)
    )

    result = await ilo_client.virtual_media("unmount")

    assert result["inserted"] is False
    assert result["connected"] is False


@respx.mock
async def test_get_event_log_bmc_ilo(ilo_client):
    respx.get(f"{BASE}/Managers/1/LogServices/IEL/Entries/").mock(
        return_value=httpx.Response(200, json={
            "Members": [
                {
                    "Id": "1",
                    "Severity": "OK",
                    "Message": "iLO reset to factory defaults",
                    "Created": "2026-01-01T00:00:00Z",
                    "EntryType": "Event",
                },
                {
                    "Id": "2",
                    "Severity": "Warning",
                    "Message": "Server powered off",
                    "Created": "2026-01-02T00:00:00Z",
                    "EntryType": "Event",
                },
            ]
        })
    )

    result = await ilo_client.get_event_log("bmc", limit=20)

    assert len(result) == 2
    assert result[0] == {
        "id": 1,
        "severity": "OK",
        "message": "iLO reset to factory defaults",
        "created": "2026-01-01T00:00:00Z",
        "entry_type": "Event",
    }


@respx.mock
async def test_get_event_log_respects_limit(ilo_client):
    respx.get(f"{BASE}/Systems/1/LogServices/IML/Entries/").mock(
        return_value=httpx.Response(200, json={
            "Members": [{"Id": str(i), "Severity": "OK", "Message": f"msg{i}",
                         "Created": "2026-01-01T00:00:00Z", "EntryType": "SEL"}
                        for i in range(10)]
        })
    )

    result = await ilo_client.get_event_log("system", limit=3)

    assert len(result) == 3


# --- iDRAC tests ---

@respx.mock
async def test_get_status_idrac(idrac_client):
    respx.get(f"{BASE}/Systems/System.Embedded.1/").mock(return_value=httpx.Response(200, json={
        "PowerState": "On",
        "Status": {"HealthRollup": "OK"},
        "IndicatorLED": "Off",
        "BiosVersion": "2.18.0",
    }))
    respx.get(f"{BASE}/Managers/iDRAC.Embedded.1/").mock(return_value=httpx.Response(200, json={
        "FirmwareVersion": "6.10.30.00",
    }))

    result = await idrac_client.get_status()

    assert result["power"] == "On"
    assert result["post_state"] == "Unknown"
    assert result["bmc_ver"] == "6.10.30.00"
    assert result["bios_ver"] == "2.18.0"


@respx.mock
async def test_power_reset_idrac(idrac_client):
    respx.post(f"{BASE}/Systems/System.Embedded.1/Actions/ComputerSystem.Reset/").mock(
        return_value=httpx.Response(200, json={})
    )

    result = await idrac_client.power("reset", force=False)

    assert result == {"action": "reset", "reset_type": "GracefulRestart", "result": "accepted"}


@respx.mock
async def test_boot_source_once_idrac(idrac_client):
    respx.patch(f"{BASE}/Systems/System.Embedded.1/").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{BASE}/Systems/System.Embedded.1/").mock(return_value=httpx.Response(200, json={
        "Boot": {
            "BootSourceOverrideTarget": "Pxe",
            "BootSourceOverrideEnabled": "Once",
        }
    }))

    result = await idrac_client.boot_source("pxe", persistent=False)

    assert result["boot_source_override_target"] == "Pxe"
    assert result["boot_source_override_enabled"] == "Once"


@respx.mock
async def test_virtual_media_mount_idrac(idrac_client):
    respx.patch(f"{BASE}/Managers/iDRAC.Embedded.1/VirtualMedia/CD/").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get(f"{BASE}/Managers/iDRAC.Embedded.1/VirtualMedia/CD/").mock(
        return_value=httpx.Response(200, json={
            "Inserted": True,
            "ConnectedVia": "URI",
            "Image": "http://fileserver/os.iso",
        })
    )

    result = await idrac_client.virtual_media("mount", "http://fileserver/os.iso")

    assert result["inserted"] is True
    assert result["slot"] == "CD"


@respx.mock
async def test_get_event_log_bmc_idrac(idrac_client):
    respx.get(f"{BASE}/Managers/iDRAC.Embedded.1/Logs/Sel/").mock(
        return_value=httpx.Response(200, json={
            "Members": [
                {
                    "Id": "1",
                    "Severity": "OK",
                    "Message": "System Board SEL Full",
                    "Created": "2026-01-01T00:00:00Z",
                    "EntryType": "SEL",
                }
            ]
        })
    )

    result = await idrac_client.get_event_log("bmc", limit=20)

    assert len(result) == 1
    assert result[0]["message"] == "System Board SEL Full"


@respx.mock
async def test_get_event_log_system_idrac(idrac_client):
    respx.get(f"{BASE}/Managers/iDRAC.Embedded.1/Logs/Lclog/").mock(
        return_value=httpx.Response(200, json={
            "Members": [
                {
                    "Id": "1",
                    "Severity": "Informational",
                    "Message": "BIOS updated",
                    "Created": "2026-01-01T00:00:00Z",
                    "EntryType": "Event",
                }
            ]
        })
    )

    result = await idrac_client.get_event_log("system", limit=20)

    assert len(result) == 1
    assert result[0]["message"] == "BIOS updated"
