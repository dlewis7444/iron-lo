# iron-lo

A Python [MCP](https://modelcontextprotocol.io/) server that gives Claude Code deterministic, structured access to BMC controllers — HPE iLO 5 and Dell iDRAC 9. Replaces brittle Playwright browser automation with two clean transports:

- **Redfish/REST** — lifecycle operations (power, boot, virtual media, event logs, status)
- **SSH + serial console** — text console access, including LUKS passphrase entry at boot

## Prerequisites

- Python 3.11+
- The target BMC reachable over the network

## Configuration

iron-lo requires no configuration. Claude provides BMC credentials at runtime via `bmc_connect`.

## Installation

```bash
git clone https://github.com/dlewis7444/iron-lo.git
cd iron-lo
./install.sh
```

The script creates a virtualenv, installs dependencies, and registers iron-lo as a user-scoped MCP server. Restart Claude Code when it completes.

**To reinstall** (e.g. after pulling updates):

```bash
claude mcp remove iron-lo
./install.sh
```

### Contributors

Install dev extras for the test suite instead:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

(`-e` installs in editable mode so source changes take effect without reinstalling. Register with `./install.sh` as normal.)

## Available Tools

| Tool | Description |
|---|---|
| `bmc_connect` | Register BMC credentials; returns a `connection_id` for all other tools |
| `bmc_get_status` | Power state, health, UID LED, POST state, BIOS and BMC versions |
| `bmc_power` | Power on/off/reset/NMI, with optional force flag |
| `bmc_boot_source` | Set one-time or persistent boot source (hdd/pxe/cd/uefi_shell) |
| `bmc_virtual_media` | Mount or unmount an ISO via virtual DVD |
| `bmc_get_event_log` | Retrieve BMC or system event log entries |
| `bmc_console_attach` | Open an SSH serial console session |
| `bmc_console_read` | Read buffered console output (consume-and-advance) |
| `bmc_console_write` | Send text to the console |
| `bmc_console_send_key` | Send a control key (ctrl_c / ctrl_d / ctrl_l / esc) |
| `bmc_console_detach` | Close the console session cleanly |

All tools except `bmc_connect` require a `connection_id` returned by `bmc_connect`.

## Virtual Media + Boot Workflow

```python
# 1. Connect to a BMC
result = bmc_connect(host="bmc.example.com", bmc_type="ilo", username="admin", password="secret")
cid = result["connection_id"]
# 2. Mount ISO
bmc_virtual_media(connection_id=cid, action="mount", url="http://files.example.com/os.iso")
# 3. One-time boot to CD
bmc_boot_source(connection_id=cid, source="cd", persistent=False)
# 4. Reboot
bmc_power(connection_id=cid, action="reset")
```

## Running Tests

Requires the dev extras (`pip install -e ".[dev]"`):

```bash
source .venv/bin/activate
pytest
```

## Architecture

```
mcp_server.py      # FastMCP entry point; registers 11 tools, manages connection cache
config.py          # BmcProfile dataclass and profile lookup
redfish.py         # RedfishClient: async httpx wrapper for Redfish endpoints
serial_console.py  # SerialConsole: asyncssh serial console session manager
tests/             # Unit tests (respx for HTTP mocks, AsyncMock for SSH)
```

## Design Notes

- **Zero-configuration** — credentials provided at runtime via `bmc_connect`, no env vars needed
- **Connection cache** — in-memory, session-scoped, no disk persistence
- **Auth:** Stateless Basic Auth per Redfish request — avoids consuming iLO's limited session slots
- **TLS:** `verify=False` — BMCs use self-signed certs by default
- **Error shape:** All tools return `{"error": str, "code": str}` on failure
- **Console reads:** Loop on `bmc_console_read` until the expected prompt appears — a single call may not capture full output

## License

MIT
