# redfish.py
import httpx
from config import BmcProfile


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


class RedfishClient:
    def __init__(self, host: str, username: str, password: str, profile: BmcProfile):
        self._base = f"https://{host}/redfish/v1"
        self._profile = profile
        self._client = httpx.AsyncClient(
            verify=False,
            auth=(username, password),
            limits=httpx.Limits(max_keepalive_connections=0),
            follow_redirects=True,
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
        system = await self._get(self._profile.system_path)
        manager = await self._get(self._profile.manager_path)
        post_state = (
            system.get("Oem", {}).get("Hpe", {}).get("PostState", "Unknown")
            if self._profile.bmc_type == "ilo"
            else "Unknown"
        )
        return {
            "power":      system.get("PowerState", "Unknown"),
            "health":     system.get("Status", {}).get("HealthRollup", "Unknown"),
            "uid":        system.get("IndicatorLED", "Off"),
            "post_state": post_state,
            "bios_ver":   system.get("BiosVersion", "Unknown"),
            "bmc_ver":    manager.get("FirmwareVersion", "Unknown"),
        }

    async def power(self, action: str, force: bool = False) -> dict:
        reset_type = _RESET_MAP[(action, force)]
        await self._post(
            self._profile.power_action_path,
            {"ResetType": reset_type},
        )
        return {"action": action, "reset_type": reset_type, "result": "accepted"}

    async def boot_source(self, source: str, persistent: bool = False) -> dict:
        redfish_source = _SOURCE_MAP[source]
        enabled = "Continuous" if persistent else "Once"
        await self._patch(self._profile.system_path, {
            "Boot": {
                "BootSourceOverrideTarget": redfish_source,
                "BootSourceOverrideEnabled": enabled,
            }
        })
        system = await self._get(self._profile.system_path)
        boot = system.get("Boot", {})
        return {
            "boot_source_override_target": boot.get("BootSourceOverrideTarget", "None"),
            "boot_source_override_enabled": boot.get("BootSourceOverrideEnabled", "Disabled"),
        }

    async def virtual_media(self, action: str, url: str | None = None) -> dict:
        path = self._profile.virtual_media_path
        if action == "mount":
            await self._patch(path, {
                "Inserted": True,
                "Image": url,
            })
        else:
            await self._patch(path, {
                "Inserted": False,
                "Image": "",
            })
        media = await self._get(path)
        slot = path.rsplit("/", 1)[-1]
        return {
            "inserted": media.get("Inserted", False),
            "connected": media.get("ConnectedVia", "NotConnected") != "NotConnected",
            "image_url": media.get("Image", ""),
            "slot": slot,
        }

    async def get_event_log(self, log: str, limit: int = 20) -> list:
        data = await self._get(self._profile.log_paths[log])
        entries = []
        for member in data.get("Members", [])[:limit]:
            entries.append({
                "id":         int(member.get("Id", 0)),
                "severity":   member.get("Severity", "Informational"),
                "message":    member.get("Message", ""),
                "created":    member.get("Created", ""),
                "entry_type": member.get("EntryType", "Event"),
            })
        return entries

    async def close(self):
        await self._client.aclose()
