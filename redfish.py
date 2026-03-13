# redfish.py
import httpx


_SOURCE_MAP = {
    "hdd": "Hdd",
    "pxe": "Pxe",
    "cd": "Cd",
    "uefi_shell": "UefiShell",
}

_RESET_MAP = {
    ("on",    False): "On",
    ("on",    True):  "On",
    ("off",   False): "GracefulShutdown",
    ("off",   True):  "ForceOff",
    ("reset", False): "GracefulRestart",
    ("reset", True):  "ForceRestart",
    ("nmi",   False): "Nmi",
    ("nmi",   True):  "Nmi",
}

_LOG_PATHS = {
    "ilo":    "/Managers/1/LogServices/IEL/Entries",
    "system": "/Systems/1/LogServices/IML/Entries",
}


class RedfishClient:
    def __init__(self, host: str, username: str, password: str):
        self._base = f"https://{host}/redfish/v1"
        self._client = httpx.AsyncClient(
            verify=False,
            auth=(username, password),
        )

    async def _get(self, path: str) -> dict:
        resp = await self._client.get(f"{self._base}{path}")
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, data: dict) -> dict:
        resp = await self._client.post(f"{self._base}{path}", json=data)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def _patch(self, path: str, data: dict) -> dict:
        resp = await self._client.patch(f"{self._base}{path}", json=data)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def get_status(self) -> dict:
        system = await self._get("/Systems/1")
        manager = await self._get("/Managers/1")
        return {
            "power":      system.get("PowerState", "Unknown"),
            "health":     system.get("Status", {}).get("HealthRollup", "Unknown"),
            "uid":        system.get("IndicatorLED", "Off"),
            "post_state": system.get("Oem", {}).get("Hpe", {}).get("PostState", "Unknown"),
            "bios_ver":   system.get("BiosVersion", "Unknown"),
            "ilo_ver":    manager.get("FirmwareVersion", "Unknown"),
        }

    async def power(self, action: str, force: bool = False) -> dict:
        reset_type = _RESET_MAP[(action, force)]
        await self._post(
            "/Systems/1/Actions/ComputerSystem.Reset",
            {"ResetType": reset_type},
        )
        return {"action": action, "reset_type": reset_type, "result": "accepted"}

    async def boot_source(self, source: str, persistent: bool = False) -> dict:
        redfish_source = _SOURCE_MAP[source]
        enabled = "Continuous" if persistent else "Once"
        await self._patch("/Systems/1", {
            "Boot": {
                "BootSourceOverrideTarget": redfish_source,
                "BootSourceOverrideEnabled": enabled,
            }
        })
        system = await self._get("/Systems/1")
        boot = system.get("Boot", {})
        return {
            "boot_source_override_target": boot.get("BootSourceOverrideTarget", "None"),
            "boot_source_override_enabled": boot.get("BootSourceOverrideEnabled", "Disabled"),
        }

    async def virtual_media(self, action: str, url: str | None = None) -> dict:
        if action == "mount":
            await self._patch("/Managers/1/VirtualMedia/2", {
                "Inserted": True,
                "Image": url,
            })
        else:
            await self._patch("/Managers/1/VirtualMedia/2", {
                "Inserted": False,
                "Image": "",
            })
        media = await self._get("/Managers/1/VirtualMedia/2")
        return {
            "inserted": media.get("Inserted", False),
            "connected": media.get("ConnectedVia", "NotConnected") != "NotConnected",
            "image_url": media.get("Image", ""),
            "slot": 2,
        }

    async def close(self):
        await self._client.aclose()
