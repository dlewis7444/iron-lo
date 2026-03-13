# bmc01 iLO MCP Server Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server that gives Claude Code deterministic, structured access to bmc01's iLO 5 via Redfish API (lifecycle) and SSH VSP (serial console), replacing Playwright browser automation.

**Architecture:** FastMCP server with two backend modules: `redfish.py` wraps iLO 5 Redfish REST for all lifecycle ops; `serial_console.py` manages a persistent SSH+VSP connection for text console access. `config.py` loads host and credentials from `pass`. All tools return structured JSON; errors use a consistent `{error, code}` shape.

**Tech Stack:** Python 3.11+, `mcp` (FastMCP), `httpx`, `asyncssh`, `pytest`, `pytest-asyncio`, `respx`

**Spec:** `docs/superpowers/specs/2026-03-13-iron-lo-mcp-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `config.py` | IloConfig dataclass; credential fetch via `pass`; singleton `FHRDM01_ILO` |
| `redfish.py` | RedfishClient: async httpx wrapper for iLO 5 Redfish endpoints |
| `serial_console.py` | SerialConsole: asyncssh + VSP session manager |
| `mcp_server.py` | FastMCP entry point; registers all 10 tools; error handling |
| `requirements.txt` | All dependencies (prod + test) |
| `pytest.ini` | asyncio_mode=auto, testpaths=tests |
| `tests/test_config.py` | Unit tests for config and credential loading |
| `tests/test_redfish.py` | Unit tests for all RedfishClient methods (respx mocks) |
| `tests/test_serial_console.py` | Unit tests for SerialConsole (asyncssh mocked) |
| `tests/test_mcp_tools.py` | Tests for MCP tool validation logic and error paths |

---

## Chunk 1: Scaffold + Config + Redfish Client

### Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
mcp>=1.0.0
httpx>=0.27.0
asyncssh>=2.14.0
respx>=0.21.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: Create pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 3: Create virtualenv and install dependencies**

```bash
cd /opt/iron-lo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 4: Create tests directory**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt pytest.ini tests/__init__.py
git commit -m "chore: project scaffold — deps, pytest config, venv"
```

---

### Task 2: config.py

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import subprocess
from unittest.mock import patch, MagicMock
from config import IloConfig, FHRDM01_ILO


def test_bmc01_ilo_singleton():
    assert FHRDM01_ILO.host == "bmc.example.com"
    assert FHRDM01_ILO.cred_path == "vendor/bmc01/admin"


def test_get_credentials_returns_username_from_path():
    config = IloConfig(host="test-ilo.local", cred_path="internal/test-ilo/myuser")
    mock_result = MagicMock()
    mock_result.stdout = "mypassword\n"
    with patch("subprocess.run", return_value=mock_result):
        username, password = config.get_credentials()
    assert username == "myuser"
    assert password == "mypassword"


def test_get_credentials_strips_whitespace():
    config = IloConfig(host="test-ilo.local", cred_path="internal/test-ilo/admin")
    mock_result = MagicMock()
    mock_result.stdout = "  secret123  \n"
    with patch("subprocess.run", return_value=mock_result):
        _, password = config.get_credentials()
    assert password == "secret123"


def test_get_credentials_calls_pass_show():
    config = IloConfig(host="test-ilo.local", cred_path="internal/test-ilo/admin")
    mock_result = MagicMock()
    mock_result.stdout = "pw\n"
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        config.get_credentials()
    mock_run.assert_called_once_with(
        ["pass", "show", "internal/test-ilo/admin"],
        capture_output=True, text=True, check=True,
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: Implement config.py**

```python
# config.py
import subprocess
from dataclasses import dataclass


@dataclass
class IloConfig:
    host: str
    cred_path: str

    def get_credentials(self) -> tuple[str, str]:
        """Fetch credentials from pass store. Returns (username, password)."""
        result = subprocess.run(
            ["pass", "show", self.cred_path],
            capture_output=True, text=True, check=True,
        )
        password = result.stdout.splitlines()[0].strip()
        username = self.cred_path.rsplit("/", 1)[-1]
        return username, password


FHRDM01_ILO = IloConfig(
    host="bmc.example.com",
    cred_path="vendor/bmc01/admin",
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: config — IloConfig dataclass with pass-store credential fetch"
```

---

### Task 3: RedfishClient base + get_status()

**Files:**
- Create: `redfish.py`
- Create: `tests/test_redfish.py`

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_redfish.py::test_get_status -v
```

Expected: `ModuleNotFoundError: No module named 'redfish'`

- [ ] **Step 3: Implement RedfishClient with get_status**

```python
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

    async def close(self):
        await self._client.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_redfish.py::test_get_status tests/test_redfish.py::test_get_status_missing_oem_fields -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add redfish.py tests/test_redfish.py
git commit -m "feat: RedfishClient base class and get_status()"
```

---

### Task 4: RedfishClient — power()

**Files:**
- Modify: `redfish.py` (add `power` method)
- Modify: `tests/test_redfish.py` (add tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_redfish.py`:

```python
@respx.mock
async def test_power_reset(client):
    respx.post(f"{BASE}/Systems/1/Actions/ComputerSystem.Reset").mock(
        return_value=httpx.Response(200, json={})
    )

    result = await client.power("reset", force=False)

    assert result == {"action": "reset", "reset_type": "GracefulRestart", "result": "accepted"}
    assert respx.calls.last.request.content == b'{"ResetType": "GracefulRestart"}'


@respx.mock
async def test_power_force_off(client):
    respx.post(f"{BASE}/Systems/1/Actions/ComputerSystem.Reset").mock(
        return_value=httpx.Response(200, json={})
    )

    result = await client.power("off", force=True)

    assert result["reset_type"] == "ForceOff"


@respx.mock
async def test_power_nmi_ignores_force(client):
    respx.post(f"{BASE}/Systems/1/Actions/ComputerSystem.Reset").mock(
        return_value=httpx.Response(200, json={})
    )

    result_normal = await client.power("nmi", force=False)
    result_forced = await client.power("nmi", force=True)

    assert result_normal["reset_type"] == "Nmi"
    assert result_forced["reset_type"] == "Nmi"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_redfish.py::test_power_reset -v
```

Expected: `AttributeError: 'RedfishClient' object has no attribute 'power'`

- [ ] **Step 3: Add power() to redfish.py**

Add after `get_status()`:

```python
    async def power(self, action: str, force: bool = False) -> dict:
        reset_type = _RESET_MAP[(action, force)]
        await self._post(
            "/Systems/1/Actions/ComputerSystem.Reset",
            {"ResetType": reset_type},
        )
        return {"action": action, "reset_type": reset_type, "result": "accepted"}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_redfish.py::test_power_reset tests/test_redfish.py::test_power_force_off tests/test_redfish.py::test_power_nmi_ignores_force -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add redfish.py tests/test_redfish.py
git commit -m "feat: RedfishClient.power() with graceful/force variants"
```

---

### Task 5: RedfishClient — boot_source() + virtual_media()

**Files:**
- Modify: `redfish.py` (add `boot_source`, `virtual_media`)
- Modify: `tests/test_redfish.py` (add tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_redfish.py`:

```python
@respx.mock
async def test_boot_source_once(client):
    respx.patch(f"{BASE}/Systems/1").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{BASE}/Systems/1").mock(return_value=httpx.Response(200, json={
        "Boot": {
            "BootSourceOverrideTarget": "Pxe",
            "BootSourceOverrideEnabled": "Once",
        }
    }))

    result = await client.boot_source("pxe", persistent=False)

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
async def test_boot_source_persistent(client):
    respx.patch(f"{BASE}/Systems/1").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{BASE}/Systems/1").mock(return_value=httpx.Response(200, json={
        "Boot": {
            "BootSourceOverrideTarget": "Hdd",
            "BootSourceOverrideEnabled": "Continuous",
        }
    }))

    result = await client.boot_source("hdd", persistent=True)

    assert result["boot_source_override_enabled"] == "Continuous"


@respx.mock
async def test_virtual_media_mount(client):
    respx.patch(f"{BASE}/Managers/1/VirtualMedia/2").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get(f"{BASE}/Managers/1/VirtualMedia/2").mock(
        return_value=httpx.Response(200, json={
            "Inserted": True,
            "ConnectedVia": "URI",
            "Image": "http://fileserver/os.iso",
        })
    )

    result = await client.virtual_media("mount", "http://fileserver/os.iso")

    assert result == {
        "inserted": True,
        "connected": True,
        "image_url": "http://fileserver/os.iso",
        "slot": 2,
    }


@respx.mock
async def test_virtual_media_unmount(client):
    respx.patch(f"{BASE}/Managers/1/VirtualMedia/2").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get(f"{BASE}/Managers/1/VirtualMedia/2").mock(
        return_value=httpx.Response(200, json={
            "Inserted": False,
            "ConnectedVia": "NotConnected",
            "Image": "",
        })
    )

    result = await client.virtual_media("unmount")

    assert result["inserted"] is False
    assert result["connected"] is False
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_redfish.py::test_boot_source_once -v
```

Expected: `AttributeError: 'RedfishClient' object has no attribute 'boot_source'`

- [ ] **Step 3: Add boot_source() and virtual_media() to redfish.py**

Add after `power()`:

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_redfish.py::test_boot_source_once tests/test_redfish.py::test_boot_source_persistent tests/test_redfish.py::test_virtual_media_mount tests/test_redfish.py::test_virtual_media_unmount -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add redfish.py tests/test_redfish.py
git commit -m "feat: RedfishClient boot_source() and virtual_media()"
```

---

### Task 6: RedfishClient — get_event_log() + run full suite

**Files:**
- Modify: `redfish.py` (add `get_event_log`)
- Modify: `tests/test_redfish.py` (add tests)

- [ ] **Step 1: Write failing test**

Append to `tests/test_redfish.py`:

```python
@respx.mock
async def test_get_event_log_ilo(client):
    respx.get(f"{BASE}/Managers/1/LogServices/IEL/Entries").mock(
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

    result = await client.get_event_log("ilo", limit=20)

    assert len(result) == 2
    assert result[0] == {
        "id": 1,
        "severity": "OK",
        "message": "iLO reset to factory defaults",
        "created": "2026-01-01T00:00:00Z",
        "entry_type": "Event",
    }


@respx.mock
async def test_get_event_log_respects_limit(client):
    respx.get(f"{BASE}/Systems/1/LogServices/IML/Entries").mock(
        return_value=httpx.Response(200, json={
            "Members": [{"Id": str(i), "Severity": "OK", "Message": f"msg{i}",
                         "Created": "2026-01-01T00:00:00Z", "EntryType": "SEL"}
                        for i in range(10)]
        })
    )

    result = await client.get_event_log("system", limit=3)

    assert len(result) == 3
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_redfish.py::test_get_event_log_ilo -v
```

Expected: `AttributeError: 'RedfishClient' object has no attribute 'get_event_log'`

- [ ] **Step 3: Add get_event_log() to redfish.py**

Add after `virtual_media()`:

```python
    async def get_event_log(self, log: str, limit: int = 20) -> list:
        data = await self._get(_LOG_PATHS[log])
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
```

- [ ] **Step 4: Run full redfish test suite**

```bash
pytest tests/test_redfish.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add redfish.py tests/test_redfish.py
git commit -m "feat: RedfishClient.get_event_log() — completes Redfish client"
```

---

## Chunk 2: Serial Console + MCP Server

### Task 7: SerialConsole — attach/detach

**Files:**
- Create: `serial_console.py`
- Create: `tests/test_serial_console.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_serial_console.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from serial_console import SerialConsole


@pytest.fixture
def console():
    return SerialConsole("bmc.example.com", "admin", "testpass")


async def test_initial_state_is_detached(console):
    assert not console.is_attached


async def test_attach_opens_ssh_and_runs_vsp(console):
    mock_conn = AsyncMock()
    mock_process = AsyncMock()
    mock_conn.create_process = AsyncMock(return_value=mock_process)

    with patch("asyncssh.connect", AsyncMock(return_value=mock_conn)) as mock_connect:
        result = await console.attach()

    assert result == {"status": "attached"}
    assert console.is_attached
    mock_connect.assert_awaited_once_with(
        "bmc.example.com",
        username="admin",
        password="testpass",
        known_hosts=None,
    )
    mock_conn.create_process.assert_awaited_once_with("VSP")


async def test_attach_when_already_attached_is_idempotent(console):
    mock_conn = AsyncMock()
    mock_process = AsyncMock()
    mock_conn.create_process = AsyncMock(return_value=mock_process)

    with patch("asyncssh.connect", AsyncMock(return_value=mock_conn)):
        await console.attach()
        result = await console.attach()

    assert result == {"status": "already_attached"}


async def test_detach_sends_vsp_exit_sequence(console):
    mock_conn = AsyncMock()
    mock_process = AsyncMock()
    mock_process.stdin = MagicMock()
    mock_conn.create_process = AsyncMock(return_value=mock_process)

    with patch("asyncssh.connect", AsyncMock(return_value=mock_conn)):
        await console.attach()
        result = await console.detach()

    assert result == {"status": "detached"}
    assert not console.is_attached
    mock_process.stdin.write.assert_called_with("\x1b(")


async def test_detach_when_not_attached(console):
    result = await console.detach()
    assert result == {"status": "detached"}
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_serial_console.py -v
```

Expected: `ModuleNotFoundError: No module named 'serial_console'`

- [ ] **Step 3: Implement serial_console.py with attach/detach**

```python
# serial_console.py
import asyncio
import asyncssh
from typing import Optional


_KEY_MAP = {
    "ctrl_c": "\x03",
    "ctrl_d": "\x04",
    "ctrl_l": "\x0c",
    "esc":    "\x1b",
}


class SerialConsole:
    def __init__(self, host: str, username: str, password: str):
        self._host = host
        self._username = username
        self._password = password
        self._conn: Optional[asyncssh.SSHClientConnection] = None
        self._process: Optional[asyncssh.SSHClientProcess] = None

    @property
    def is_attached(self) -> bool:
        return self._conn is not None and self._process is not None

    async def attach(self) -> dict:
        if self.is_attached:
            return {"status": "already_attached"}
        self._conn = await asyncssh.connect(
            self._host,
            username=self._username,
            password=self._password,
            known_hosts=None,
        )
        self._process = await self._conn.create_process("VSP")
        return {"status": "attached"}

    async def detach(self) -> dict:
        if not self.is_attached:
            return {"status": "detached"}
        try:
            self._process.stdin.write("\x1b(")
            await asyncio.sleep(0.2)
        except Exception:
            pass
        try:
            self._process.close()
        except Exception:
            pass
        try:
            self._conn.close()
        except Exception:
            pass
        self._process = None
        self._conn = None
        return {"status": "detached"}

    async def read(self, timeout_s: int = 5) -> dict:
        if not self.is_attached:
            return {"error": "not attached", "code": "not_attached"}
        try:
            data = await asyncio.wait_for(
                self._process.stdout.read(4096),
                timeout=timeout_s,
            )
            return {"output": data, "truncated": len(data) == 4096}
        except asyncio.TimeoutError:
            return {"output": "", "truncated": False}

    async def write(self, text: str, send_enter: bool = True) -> dict:
        if not self.is_attached:
            return {"error": "not attached", "code": "not_attached"}
        payload = text + ("\n" if send_enter else "")
        self._process.stdin.write(payload)
        return {"bytes_written": len(payload.encode())}

    async def send_key(self, key: str) -> dict:
        if not self.is_attached:
            return {"error": "not attached", "code": "not_attached"}
        char = _KEY_MAP.get(key)
        if not char:
            return {"error": f"unknown key: {key}", "code": "invalid_key"}
        self._process.stdin.write(char)
        return {"sent": key}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_serial_console.py::test_initial_state_is_detached tests/test_serial_console.py::test_attach_opens_ssh_and_runs_vsp tests/test_serial_console.py::test_attach_when_already_attached_is_idempotent tests/test_serial_console.py::test_detach_sends_vsp_exit_sequence tests/test_serial_console.py::test_detach_when_not_attached -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add serial_console.py tests/test_serial_console.py
git commit -m "feat: SerialConsole attach/detach with VSP exit sequence"
```

---

### Task 8: SerialConsole — read/write/send_key

**Files:**
- Modify: `tests/test_serial_console.py` (add tests; implementation already in place from Task 7)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_serial_console.py`:

```python
@pytest.fixture
async def attached_console():
    """A console that is already attached with a mock SSH session."""
    console = SerialConsole("bmc.example.com", "admin", "testpass")
    mock_conn = AsyncMock()
    mock_process = AsyncMock()
    mock_process.stdin = MagicMock()
    mock_process.stdout = AsyncMock()
    mock_conn.create_process = AsyncMock(return_value=mock_process)

    with patch("asyncssh.connect", AsyncMock(return_value=mock_conn)):
        await console.attach()

    return console, mock_process


async def test_read_returns_output(attached_console):
    console, mock_process = attached_console
    mock_process.stdout.read = AsyncMock(return_value="Enter passphrase for luks-abc:")

    result = await console.read(timeout_s=5)

    assert result == {"output": "Enter passphrase for luks-abc:", "truncated": False}


async def test_read_returns_empty_on_timeout(attached_console):
    console, mock_process = attached_console

    async def slow_read(_):
        await asyncio.sleep(10)
        return ""

    mock_process.stdout.read = slow_read

    result = await console.read(timeout_s=1)

    assert result == {"output": "", "truncated": False}


async def test_read_when_not_attached(console):
    result = await console.read()
    assert result == {"error": "not attached", "code": "not_attached"}


async def test_write_sends_text_with_newline(attached_console):
    console, mock_process = attached_console

    result = await console.write("mypassword")

    mock_process.stdin.write.assert_called_with("mypassword\n")
    assert result["bytes_written"] == len("mypassword\n".encode())


async def test_write_without_enter(attached_console):
    console, mock_process = attached_console

    await console.write("partial", send_enter=False)

    mock_process.stdin.write.assert_called_with("partial")


async def test_write_when_not_attached(console):
    result = await console.write("text")
    assert result == {"error": "not attached", "code": "not_attached"}


async def test_send_key_ctrl_c(attached_console):
    console, mock_process = attached_console

    result = await console.send_key("ctrl_c")

    mock_process.stdin.write.assert_called_with("\x03")
    assert result == {"sent": "ctrl_c"}


async def test_send_key_invalid(attached_console):
    console, mock_process = attached_console

    result = await console.send_key("f12")

    assert result == {"error": "unknown key: f12", "code": "invalid_key"}


async def test_send_key_when_not_attached(console):
    result = await console.send_key("ctrl_c")
    assert result == {"error": "not attached", "code": "not_attached"}
```

- [ ] **Step 2: Run to verify tests fail (before fixture is usable)**

```bash
pytest tests/test_serial_console.py::test_read_returns_output -v
```

Expected: FAIL — `asyncio.TimeoutError` or fixture issue (implementation exists but tests are new)

- [ ] **Step 3: Verify implementation is already in place from Task 7**

`read()`, `write()`, and `send_key()` were written in Task 7. No new code needed.

- [ ] **Step 4: Run full serial console suite**

```bash
pytest tests/test_serial_console.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_serial_console.py
git commit -m "test: complete serial console test coverage for read/write/send_key"
```

---

### Task 9: MCP server — all tools

**Files:**
- Create: `mcp_server.py`
- Create: `tests/test_mcp_tools.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_mcp_tools.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def mock_pass_credentials():
    """Prevent real `pass` calls when importing mcp_server."""
    mock_result = MagicMock()
    mock_result.stdout = "testpassword\n"
    with patch("subprocess.run", return_value=mock_result):
        yield


@pytest.fixture
def mock_redfish():
    with patch("mcp_server._redfish") as m:
        yield m


@pytest.fixture
def mock_console():
    with patch("mcp_server._console") as m:
        yield m


async def test_ilo_get_status_success(mock_redfish):
    import mcp_server
    mock_redfish.get_status = AsyncMock(return_value={
        "power": "On", "health": "OK", "uid": "Off",
        "post_state": "FinishedPost", "bios_ver": "U30", "ilo_ver": "2.55",
    })

    result = await mcp_server.ilo_get_status()

    assert result["power"] == "On"


async def test_ilo_get_status_handles_exception(mock_redfish):
    import mcp_server
    mock_redfish.get_status = AsyncMock(side_effect=Exception("connection refused"))

    result = await mcp_server.ilo_get_status()

    assert "error" in result
    assert "connection refused" in result["error"]


async def test_ilo_power_invalid_action(mock_redfish):
    import mcp_server

    result = await mcp_server.ilo_power("explode")

    assert result == {"error": "invalid action: explode", "code": "invalid_action"}
    mock_redfish.power.assert_not_called()


async def test_ilo_power_valid(mock_redfish):
    import mcp_server
    mock_redfish.power = AsyncMock(return_value={
        "action": "reset", "reset_type": "GracefulRestart", "result": "accepted"
    })

    result = await mcp_server.ilo_power("reset")

    assert result["result"] == "accepted"
    mock_redfish.power.assert_awaited_once_with("reset", False)


async def test_ilo_boot_source_invalid(mock_redfish):
    import mcp_server

    result = await mcp_server.ilo_boot_source("floppy")

    assert "error" in result
    mock_redfish.boot_source.assert_not_called()


async def test_ilo_virtual_media_requires_url_for_mount(mock_redfish):
    import mcp_server

    result = await mcp_server.ilo_virtual_media("mount", url="")

    assert result == {"error": "url required for mount", "code": "missing_url"}


async def test_ilo_virtual_media_mount(mock_redfish):
    import mcp_server
    mock_redfish.virtual_media = AsyncMock(return_value={
        "inserted": True, "connected": True, "image_url": "http://x/os.iso", "slot": 2
    })

    result = await mcp_server.ilo_virtual_media("mount", url="http://x/os.iso")

    assert result["inserted"] is True
    mock_redfish.virtual_media.assert_awaited_once_with("mount", "http://x/os.iso")


async def test_ilo_get_event_log_invalid_log(mock_redfish):
    import mcp_server

    result = await mcp_server.ilo_get_event_log("kernel")

    assert isinstance(result, list)
    assert "error" in result[0]


async def test_ilo_console_attach(mock_console):
    import mcp_server
    mock_console.attach = AsyncMock(return_value={"status": "attached"})

    result = await mcp_server.ilo_console_attach()

    assert result == {"status": "attached"}


async def test_ilo_console_read(mock_console):
    import mcp_server
    mock_console.read = AsyncMock(return_value={"output": "login: ", "truncated": False})

    result = await mcp_server.ilo_console_read(timeout_s=10)

    assert result["output"] == "login: "
    mock_console.read.assert_awaited_once_with(10)


async def test_ilo_console_write(mock_console):
    import mcp_server
    mock_console.write = AsyncMock(return_value={"bytes_written": 12})

    result = await mcp_server.ilo_console_write("mypassword")

    assert result["bytes_written"] == 12
    mock_console.write.assert_awaited_once_with("mypassword", True)


async def test_ilo_console_send_key(mock_console):
    import mcp_server
    mock_console.send_key = AsyncMock(return_value={"sent": "ctrl_c"})

    result = await mcp_server.ilo_console_send_key("ctrl_c")

    assert result == {"sent": "ctrl_c"}


async def test_ilo_console_detach(mock_console):
    import mcp_server
    mock_console.detach = AsyncMock(return_value={"status": "detached"})

    result = await mcp_server.ilo_console_detach()

    assert result == {"status": "detached"}
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_mcp_tools.py::test_ilo_get_status_success -v
```

Expected: `ModuleNotFoundError: No module named 'mcp_server'`

- [ ] **Step 3: Implement mcp_server.py**

```python
# mcp_server.py
from mcp.server.fastmcp import FastMCP
from config import FHRDM01_ILO
from redfish import RedfishClient
from serial_console import SerialConsole


mcp = FastMCP("iron-lo")

# Initialise clients — credentials fetched once at startup via pass
_username, _password = FHRDM01_ILO.get_credentials()
_redfish = RedfishClient(FHRDM01_ILO.host, _username, _password)
_console = SerialConsole(FHRDM01_ILO.host, _username, _password)


def _error(msg: str, code: str) -> dict:
    return {"error": msg, "code": code}


@mcp.tool()
async def ilo_get_status() -> dict:
    """Get current iLO status: power state, health, UID LED, POST state, BIOS and iLO versions."""
    try:
        return await _redfish.get_status()
    except Exception as e:
        return _error(str(e), "redfish_error")


@mcp.tool()
async def ilo_power(action: str, force: bool = False) -> dict:
    """Control server power. action: on|off|reset|nmi. force=True skips graceful shutdown/restart."""
    if action not in ("on", "off", "reset", "nmi"):
        return _error(f"invalid action: {action}", "invalid_action")
    try:
        return await _redfish.power(action, force)
    except Exception as e:
        return _error(str(e), "redfish_error")


@mcp.tool()
async def ilo_boot_source(source: str, persistent: bool = False) -> dict:
    """Set boot source. source: hdd|pxe|cd|uefi_shell. persistent=False for one-time override."""
    if source not in ("hdd", "pxe", "cd", "uefi_shell"):
        return _error(f"invalid source: {source}", "invalid_source")
    try:
        return await _redfish.boot_source(source, persistent)
    except Exception as e:
        return _error(str(e), "redfish_error")


@mcp.tool()
async def ilo_virtual_media(action: str, url: str = "") -> dict:
    """Mount or unmount virtual media (DVD slot 2). action: mount|unmount. url required for mount."""
    if action not in ("mount", "unmount"):
        return _error(f"invalid action: {action}", "invalid_action")
    if action == "mount" and not url:
        return _error("url required for mount", "missing_url")
    try:
        return await _redfish.virtual_media(action, url or None)
    except Exception as e:
        return _error(str(e), "redfish_error")


@mcp.tool()
async def ilo_get_event_log(log: str, limit: int = 20) -> list:
    """Get iLO or system event log entries. log: ilo|system."""
    if log not in ("ilo", "system"):
        return [_error(f"invalid log: {log}", "invalid_log")]
    try:
        return await _redfish.get_event_log(log, limit)
    except Exception as e:
        return [_error(str(e), "redfish_error")]


@mcp.tool()
async def ilo_console_attach() -> dict:
    """Attach to iLO Virtual Serial Port (VSP) over SSH. Idempotent."""
    try:
        return await _console.attach()
    except Exception as e:
        return _error(str(e), "ssh_error")


@mcp.tool()
async def ilo_console_read(timeout_s: int = 5) -> dict:
    """
    Read pending serial console output since last read (consume-and-advance).
    Empty output means nothing arrived within timeout_s — retry if waiting for a prompt.
    """
    return await _console.read(timeout_s)


@mcp.tool()
async def ilo_console_write(text: str, send_enter: bool = True) -> dict:
    """Write text to the serial console. Caller is responsible for supplying the correct text."""
    return await _console.write(text, send_enter)


@mcp.tool()
async def ilo_console_send_key(key: str) -> dict:
    """Send a control key to the serial console. key: ctrl_c|ctrl_d|ctrl_l|esc."""
    return await _console.send_key(key)


@mcp.tool()
async def ilo_console_detach() -> dict:
    """Detach from the serial console. Sends VSP exit sequence (ESC open-paren) before closing."""
    return await _console.detach()


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```

Expected: all tests PASS (config + redfish + serial_console + mcp_tools).

- [ ] **Step 5: Commit**

```bash
git add mcp_server.py tests/test_mcp_tools.py
git commit -m "feat: MCP server — all 10 iLO tools registered via FastMCP"
```

---

## Chunk 3: OS Serial Console Setup + Claude Code Integration

### Task 10: bmc01 serial console OS setup

These steps are executed manually over SSH on bmc01. Execute each step and verify before proceeding to the next. A failed reboot will require the existing Playwright/graphical console to recover.

**Pre-flight: verify UEFI COM1 is enabled**

- [ ] **Step 1: Check UEFI serial port setting via iLO Redfish**

```bash
# From workstation — check if COM1 is mentioned in system BIOS settings
curl -sk -u dlewis:$(pass show vendor/bmc01/admin) \
  https://bmc.example.com/redfish/v1/Systems/1/Bios | \
  python3 -m json.tool | grep -i serial
```

If the BIOS serial port is disabled, enable it via UEFI before continuing. This may require a reboot into BIOS setup (use existing Playwright path to access iLO console for that).

- [ ] **Step 2: Add console=ttyS0 to GRUB_CMDLINE_LINUX on bmc01**

```bash
ssh bmc01 "sudo sed -i 's/^GRUB_CMDLINE_LINUX=\"/GRUB_CMDLINE_LINUX=\"console=tty0 console=ttyS0,115200n8 /' /etc/default/grub"
ssh bmc01 "grep GRUB_CMDLINE_LINUX /etc/default/grub"
```

Expected: line now contains `console=tty0 console=ttyS0,115200n8`.

- [ ] **Step 3: Back up current initramfs**

```bash
ssh bmc01 "sudo cp /boot/initramfs-\$(uname -r).img /boot/initramfs-\$(uname -r).img.bak && ls -lh /boot/initramfs-\$(uname -r).img.bak"
```

Expected: backup file listed.

- [ ] **Step 4: Rebuild UEFI grub config**

```bash
ssh bmc01 "sudo grub2-mkconfig -o /boot/efi/EFI/redhat/grub.cfg 2>&1 | tail -5"
```

Expected: output ends with `done`.

- [ ] **Step 5: Rebuild initramfs**

```bash
ssh bmc01 "sudo dracut --force 2>&1 | tail -3"
```

Expected: exits without error.

- [ ] **Step 6: Reboot bmc01 — use existing Playwright console for LUKS unlock**

Trigger reboot:
```bash
ssh bmc01 "sudo reboot"
```

Open the iLO graphical console via Playwright (existing path) and enter the LUKS passphrase when prompted. This is the last time the graphical console is needed for LUKS unlock.

Wait for bmc01 to come back up:
```bash
# Poll until SSH responds
until ssh -o ConnectTimeout=5 bmc01 "echo ok" 2>/dev/null; do sleep 10; done
echo "bmc01 is back"
```

- [ ] **Step 7: Verify VSP shows output**

```bash
ssh -o StrictHostKeyChecking=no dlewis@bmc.example.com "VSP" &
VSP_PID=$!
sleep 5  # increase to 10 if SSH handshake is slow and no output appears
kill $VSP_PID 2>/dev/null
```

A login or systemd prompt should appear over VSP. If no output, check Step 1 (COM1 UEFI setting).

- [ ] **Step 8: Commit setup notes**

```bash
# On workstation
cat >> /opt/iron-lo/SETUP_LOG.md << 'EOF'
## 2026-03-13: Serial console setup

- Added `console=tty0 console=ttyS0,115200n8` to bmc01 GRUB_CMDLINE_LINUX
- Rebuilt grub config (UEFI path) and initramfs
- Rebooted with LUKS unlock via Playwright (final graphical console use)
- VSP verified working over iLO SSH
EOF
git add SETUP_LOG.md
git commit -m "docs: log bmc01 serial console setup"
```

---

### Task 11: Claude Code MCP registration + smoke test

**Files:**
- Modify: `~/.claude/claude_desktop_config.json` (add iron-lo MCP entry)

- [ ] **Step 1: Check current MCP config location**

```bash
# Find where Claude Code MCP servers are configured
ls ~/.claude/claude_desktop_config.json 2>/dev/null || \
ls ~/.config/claude/claude_desktop_config.json 2>/dev/null || \
echo "config not found — check Claude Code docs for MCP config path"
```

If neither exists, check `~/.claude/settings.json` for an `mcpServers` key or consult Claude Code's `/mcp` command.

- [ ] **Step 2: Add iron-lo entry to MCP config**

Add under `mcpServers`:
```json
"iron-lo": {
  "command": "/opt/iron-lo/.venv/bin/python3",
  "args": ["/opt/iron-lo/mcp_server.py"]
}
```

- [ ] **Step 3: Restart Claude Code to load the new MCP server**

Close and reopen Claude Code, or reload MCP servers if that option exists.

- [ ] **Step 4: Smoke test — ilo_get_status**

In a Claude Code session with the iron-lo project:

```
Call ilo_get_status and show me the result.
```

Expected: structured JSON with `power`, `health`, `uid`, `post_state`, `bios_ver`, `ilo_ver` — no Playwright browser opens.

- [ ] **Step 5: Smoke test — ilo_console_attach + read**

```
Attach the iLO serial console and read 3 seconds of output.
```

Expected: text output from bmc01's serial console (likely a login prompt or systemd messages) — no screenshot, no browser.

- [ ] **Step 6: Commit registration note**

```bash
cat >> /opt/iron-lo/SETUP_LOG.md << 'EOF'

## 2026-03-13: Claude Code MCP registration

- Added iron-lo MCP server to claude_desktop_config.json
- Verified ilo_get_status and ilo_console_attach work without Playwright
EOF
git add SETUP_LOG.md
git commit -m "docs: log Claude Code MCP registration and smoke test"
```
