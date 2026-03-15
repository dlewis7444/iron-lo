# iron-lo

A Python [MCP](https://modelcontextprotocol.io/) server that gives Claude Code deterministic, structured access to BMC controllers — HPE iLO 5 and Dell iDRAC 9. Replaces brittle Playwright browser automation with two clean transports:

- **Redfish/REST** — lifecycle operations (power, boot, virtual media, event logs, status)
- **SSH + serial console** — text console access, including LUKS passphrase entry at boot

## Prerequisites

- Python 3.11+
- [`pass`](https://www.passwordstore.org/) for credential management
- The target BMC reachable over the network

## Configuration

iron-lo is configured entirely through environment variables:

| Variable | Required | Description |
|---|---|---|
| `BMC_HOST` | yes | Hostname or IP of the BMC (e.g. `bmc.example.com`) |
| `BMC_CRED_PATH` | yes | `pass` store path to the BMC credentials (e.g. `vendor/bmc01/admin`) |
| `BMC_TYPE` | no | `ilo` (default) or `idrac` |

The credential entry in `pass` must have the password on the first line. The username is derived from the last path segment of `BMC_CRED_PATH`.

Legacy `ILO_HOST` / `ILO_CRED_PATH` env vars are also accepted for backward compatibility.

## Installation

```bash
git clone https://github.com/yourusername/iron-lo.git
cd iron-lo
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

For contributors who want to run the test suite, install the dev extras instead:

```bash
pip install -e ".[dev]"
```

(`-e` installs in editable mode so source changes take effect without reinstalling.)

## MCP Registration

Add to your Claude Code MCP settings (e.g. `~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "iron-lo": {
      "command": "python3",
      "args": ["/path/to/iron-lo/mcp_server.py"],
      "env": {
        "BMC_HOST": "bmc.example.com",
        "BMC_CRED_PATH": "vendor/bmc01/admin",
        "BMC_TYPE": "ilo"
      }
    }
  }
}
```

To manage multiple BMCs, register separate entries with different env vars.

## Available Tools

| Tool | Description |
|---|---|
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

## Virtual Media + Boot Workflow

```python
# 1. Mount ISO
bmc_virtual_media(action="mount", url="http://files.example.com/os.iso")
# 2. One-time boot to CD
bmc_boot_source(source="cd", persistent=False)
# 3. Reboot
bmc_power(action="reset")
```

## Running Tests

Requires the dev extras (`pip install -e ".[dev]"`):

```bash
source .venv/bin/activate
pytest
```

## Architecture

```
mcp_server.py      # FastMCP entry point; registers 10 tools
config.py          # BmcConfig dataclass; reads env vars; fetches pass credentials
redfish.py         # RedfishClient: async httpx wrapper for Redfish endpoints
serial_console.py  # SerialConsole: asyncssh serial console session manager
tests/             # Unit tests (respx for HTTP mocks, AsyncMock for SSH)
```

## Design Notes

- **Auth:** Stateless Basic Auth per Redfish request — avoids consuming iLO's limited session slots
- **TLS:** `verify=False` — BMCs use self-signed certs by default
- **Error shape:** All tools return `{"error": str, "code": str}` on failure
- **Console reads:** Loop on `bmc_console_read` until the expected prompt appears — a single call may not capture full output

## License

MIT
