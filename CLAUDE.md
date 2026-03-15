# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`iron-lo` is a Python MCP server that gives Claude Code deterministic, structured access to BMC controllers — HPE iLO 5 and Dell iDRAC 9. It replaces brittle Playwright browser automation with two clean transports:

- **Redfish/REST** for all lifecycle operations (power, boot, virtual media, logs, status)
- **SSH + serial console** for text console access, including LUKS passphrase entry at boot

## Running and Testing

```bash
# Activate venv
source .venv/bin/activate

# Run all tests
pytest

# Run a single test file
pytest tests/test_redfish.py

# Run a single test by name
pytest tests/test_redfish.py::test_power_reset

# Run the MCP server (requires env vars)
BMC_HOST=bmc.example.com BMC_CRED_PATH=vendor/bmc01/admin BMC_TYPE=ilo python mcp_server.py
```

## Architecture

```
mcp_server.py          # FastMCP entry point; registers 10 tools; top-level error handling
config.py              # BmcConfig dataclass; reads BMC_HOST / BMC_CRED_PATH / BMC_TYPE env vars;
                       # fetches credentials from `pass` at startup
redfish.py             # RedfishClient: async httpx wrapper for Redfish endpoints
serial_console.py      # SerialConsole: asyncssh + serial console session manager (one session at a time)
tests/test_redfish.py  # Unit tests using respx to mock httpx calls
```

## Key Design Decisions

**Credentials:** Loaded once at startup via `pass show <BMC_CRED_PATH>`. The username is the last path segment of `BMC_CRED_PATH`. Never hardcode credentials.

**Redfish auth:** Stateless Basic Auth per request (no Redfish session tokens). iLO 5 limits concurrent sessions to 6; Basic Auth avoids consuming session slots.

**TLS:** `verify=False` — BMCs use self-signed certs; this is intentional and expected.

**Error shape:** All tools return `{"error": str, "code": str}` on failure. Check for the `error` key before interpreting a result.

**Console read model:** Consume-and-advance streaming. Each `bmc_console_read` call returns output since the last call and advances the buffer position. Loop on `read` until the expected prompt appears — a single call is not guaranteed to capture the full output.

**iLO VSP exit:** `bmc_console_detach` sends `ESC (` (escape + open-paren) before closing SSH — this is iLO's built-in VSP exit sequence. iDRAC uses `~.`.

**SSH key negotiation:** iLO 5 requires legacy algorithms. `asyncssh.connect` explicitly sets `server_host_key_algs=["ssh-rsa"]` and `kex_algs=["diffie-hellman-group14-sha256", "diffie-hellman-group14-sha1"]`.

**BmcProfile:** BMC-specific paths and behaviors are isolated in `BmcProfile` dataclasses in `config.py`. Adding a new BMC type means adding a new profile — no conditional logic in the client layer.

## Virtual Media + Boot Order Workflow

`bmc_virtual_media` and `bmc_boot_source` are intentionally separate tools:

1. `bmc_virtual_media(action="mount", url=...)` — insert ISO into virtual DVD
2. `bmc_boot_source(source="cd", persistent=False)` — set one-time boot override
3. `bmc_power(action="reset")` — reboot

## MCP Registration (Claude Code settings)

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

## Generalization

`config.py` is config-driven via env vars. The same `mcp_server.py` can serve multiple BMCs by registering additional MCP entries with different `BMC_HOST` / `BMC_CRED_PATH` / `BMC_TYPE` values.
