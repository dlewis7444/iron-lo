# bmc01 iLO MCP Server — Design Spec

**Date:** 2026-03-13
**Status:** Approved

---

## Problem

Claude Code currently manages bmc01's iLO 5 entirely through Playwright browser automation. This is non-deterministic (the LLM navigates the SPA freely), token-expensive (requires screenshots), and brittle to iLO firmware updates. LUKS full-disk encryption means every reboot requires manually entering a passphrase through the graphical KVM console — the most fragile part of the current workflow.

## Goals

1. **Primary:** Make iLO control as deterministic as possible — structured API calls and text streams instead of LLM-driven browser navigation.
2. **Secondary:** Minimize token use — structured JSON responses and plain-text serial output instead of screenshots.

## Non-Goals

- Replacing Playwright entirely: it stays registered as an emergency fallback for pixel-level-only operations.
- Supporting iLO 4 or iLO 6.
- A web dashboard or GUI.

---

## Architecture

```
Claude Code
    │
    ▼
iron-lo MCP Server  (Python, runs on workstation)
    ├── Redfish tools  ──────────────► iLO 5 REST API  (192.0.2.1, HTTPS)
    └── Serial console tool  ─────────► iLO 5 SSH (port 22)
                                             └── VSP (Virtual Serial Port)
                                                  └── bmc01 kernel serial console
                                                       ├── LUKS prompt (dracut)
                                                       └── OS shell / login

Playwright (unchanged, emergency only)
```

**Project layout:**
```
/opt/iron-lo/
├── mcp_server.py          # MCP entry point, tool registration
├── redfish.py             # iLO Redfish HTTP client
├── serial_console.py      # SSH + VSP session manager
├── config.py              # host, port, credential lookup via pass
├── requirements.txt
└── perplexity.md          # existing research doc
```

---

## Component: Redfish Client (`redfish.py`)

Thin HTTP wrapper around iLO 5's Redfish/REST API.

- Base URL: `https://192.0.2.1/redfish/v1`
- Auth: HTTP Basic, credentials fetched at startup via `pass vendor/bmc01/admin`
- TLS: `verify=False` (iLO uses a self-signed cert)
- Library: `httpx` with a single persistent `httpx.AsyncClient` instance reused across all calls
- **Session handling:** per-request Basic Auth headers only — no Redfish session tokens. iLO 5 has a default concurrent session limit of 6; using stateless Basic Auth per-request avoids consuming session table slots and eliminates session expiry as a failure mode.

---

## Error Return Shape

All tools return structured dicts. On failure, every tool returns:
```json
{"error": "<human-readable message>", "code": "<http status or internal error string>"}
```
On success, tools return their documented shape. Claude should check for the presence of the `error` key before interpreting the result.

---

## MCP Tools — Redfish Lifecycle

### `ilo_power`
| Parameter | Type | Values |
|-----------|------|--------|
| `action` | str | `on`, `off`, `reset`, `nmi` |
| `force` | bool | default `false` |

Returns `{state: str, result: str}`.

**Redfish `ResetType` mapping:**

| `action` | `force=false` | `force=true` |
|----------|--------------|-------------|
| `on` | `On` | `On` |
| `off` | `GracefulShutdown` | `ForceOff` |
| `reset` | `GracefulRestart` | `ForceRestart` |
| `nmi` | `Nmi` | `Nmi` |

Behavior: idempotent — `on` when already on returns success. Maps to `POST /redfish/v1/Systems/1/Actions/ComputerSystem.Reset` with body `{"ResetType": "<value>"}`.

### `ilo_get_status`
No parameters.

Returns `{power: str, health: str, uid: str, post_state: str, bios_ver: str, ilo_ver: str}`.

- `power`: `"On"` or `"Off"`
- `health`: `"OK"`, `"Warning"`, or `"Critical"`
- `uid`: UID indicator LED state — `"Lit"`, `"Off"`, or `"Blinking"` (maps to Redfish `IndicatorLED`)
- `post_state`: e.g. `"FinishedPost"`, `"InPostDiscoveryComplete"`, `"PowerOff"` — use this to detect boot progress
- `bios_ver`: BIOS version string
- `ilo_ver`: iLO firmware version string

The cheap "dashboard replacement" — Claude calls this instead of screenshotting the iLO UI to check current state.

### `ilo_boot_source`
| Parameter | Type | Values |
|-----------|------|--------|
| `source` | str | `hdd`, `pxe`, `cd`, `uefi_shell` |
| `persistent` | bool | `true` = change default; `false` = one-time override |

Returns `{boot_source_override_target: str, boot_source_override_enabled: str}` — mirroring the Redfish field names directly. `boot_source_override_enabled` will be `"Once"` when `persistent=False`, `"Continuous"` when `persistent=True`, or `"Disabled"` if no override is active.

Sets `Boot.BootSourceOverrideTarget` and `Boot.BootSourceOverrideEnabled` via `PATCH /redfish/v1/Systems/1`. `persistent=False` is the common case: boot to ISO/PXE once, then revert to HDD.

This tool controls boot order only. It does not mount media. For ISO boot, call `ilo_virtual_media` first to insert the image, then call this tool.

### `ilo_virtual_media`
| Parameter | Type | Values |
|-----------|------|--------|
| `action` | str | `mount`, `unmount` |
| `url` | str (optional) | ISO URL for mount |

Returns `{inserted: bool, connected: bool, image_url: str, slot: int}`.

Targets the DVD slot (slot 2: `GET /redfish/v1/Managers/1/VirtualMedia/2`). The USB floppy slot (slot 1) is not used. On mount, PATCHes `Inserted: true, Image: <url>` to the DVD slot. Does not set boot order — that is `ilo_boot_source`'s responsibility.

### `ilo_get_event_log`
| Parameter | Type | Values |
|-----------|------|--------|
| `log` | str | `ilo`, `system` |
| `limit` | int (optional) | default 20 |

Returns a list of log entry dicts:
```json
[{"id": int, "severity": "OK|Warning|Critical|Informational", "message": str, "created": "ISO8601 str", "entry_type": "Event|SEL|Oem"}, ...]
```

---

## Component: Serial Console (`serial_console.py`)

Manages a persistent SSH connection to iLO's SSH interface, running the `VSP` command to bridge to bmc01's kernel serial console.

- Library: `asyncssh`
- SSH target: `bmc.example.com` port 22
- Credentials: same iLO credentials as Redfish
- Session: one active VSP session at a time; state held in the MCP server process
- Read model: consume-and-advance streaming — each `ilo_console_read` call returns new output since the last call and advances the read position. Empty output means nothing arrived within `timeout_s`. Callers should loop on `read` until the expected prompt appears rather than assuming one call is sufficient.
- VSP exit sequence: sending `ESC (` (escape followed by open-paren) is iLO's built-in VSP exit sequence. `ilo_console_detach` sends this sequence before closing the SSH connection for a clean exit.

---

## MCP Tools — Serial Console

### `ilo_console_attach`
No parameters. Opens SSH connection and runs `VSP`.

If a session is already attached, returns `{status: "already_attached"}` without opening a duplicate. If reconnecting after a drop, opens a fresh session from scratch.

Returns `{status: "attached" | "already_attached"}`.

### `ilo_console_read`
| Parameter | Type | Default |
|-----------|------|---------|
| `timeout_s` | int | 5 |

Drains buffered serial output up to `timeout_s` seconds. Returns new output since last read (consume-and-advance). Returns `{output: str, truncated: bool}`. Empty `output` means nothing arrived — caller should retry if waiting for a prompt.

### `ilo_console_write`
| Parameter | Type | Default |
|-----------|------|---------|
| `text` | str | required |
| `send_enter` | bool | `true` |

Writes text to the serial stream. The caller is responsible for supplying the correct text (e.g. fetching a passphrase from `pass` before calling this tool). Returns `{bytes_written: int}`.

### `ilo_console_send_key`
| Parameter | Type | Values |
|-----------|------|--------|
| `key` | str | `ctrl_c`, `ctrl_d`, `ctrl_l`, `esc` |

Sends a control character. Returns `{sent: str}`.

### `ilo_console_detach`
No parameters. Closes the SSH/VSP session. Returns `{status: "detached"}`.

---

## Typical Workflows

### LUKS unlock after reboot

The LUKS passphrase must be fetched by the caller (via `pass vendor/bmc01/luks-passphrase` or equivalent) before beginning this sequence.

```
ilo_get_status()
  # confirm post_state is not "FinishedPost" — if it is, the machine already booted
  # and no unlock is needed

ilo_console_attach()
ilo_console_read(timeout_s=30)     # loop until "Enter passphrase for luks-..." appears
ilo_console_write(luks_passphrase) # caller supplies passphrase
ilo_console_read(timeout_s=120)    # wait for OS login prompt
ilo_console_detach()
```

**Recovery if VSP session drops mid-sequence:**
1. Call `ilo_get_status()` and check `post_state`. If `"FinishedPost"`, the machine booted successfully — no action needed.
2. If `post_state` indicates still booting, call `ilo_console_attach()` (reconnects) and `ilo_console_read()` to determine current state before retrying `write`.
3. Never re-send the passphrase without first confirming the prompt is present — a double send will be treated as a wrong passphrase followed by garbage input.

### Boot from ISO once
```
ilo_virtual_media(action="mount", url="http://...")  # insert ISO into DVD slot
ilo_boot_source(source="cd", persistent=False)        # set one-time boot override
ilo_power(action="reset")
# then attach console to watch progress
```

### Quick health check
```
ilo_get_status()
# → {power: "On", health: "OK", post_state: "FinishedPost", ...}
```

---

## Prerequisite: bmc01 Serial Console Setup

One-time configuration required before `ilo_console_attach` is useful.

### Step 0: Verify UEFI serial port is enabled

On the DL380 Gen10, the iLO VSP bridges to the COM1 serial port. If COM1 is disabled in UEFI, `ttyS0` will exist in the OS but VSP will show no output. Before making any grub/dracut changes, confirm COM1 is enabled:

> UEFI > System Configuration > BIOS/Platform Configuration (RBSU) > System Options > Serial Port Options > Embedded Serial Port

It should be set to `COM1 IRQ4 I/O: 3F8h`. If disabled, enable it and reboot into the OS before proceeding.

### Step 1: Edit `/etc/default/grub`

Append to `GRUB_CMDLINE_LINUX`:
```
console=tty0 console=ttyS0,115200n8
```
`tty0` listed first keeps VGA as primary display; `ttyS0` mirrors to serial. dracut will present the LUKS passphrase prompt on both consoles.

### Step 2: Back up the current initramfs
```bash
cp /boot/initramfs-$(uname -r).img /boot/initramfs-$(uname -r).img.bak
```
If the dracut rebuild produces a malformed initramfs, restore this backup before rebooting.

### Step 3: Rebuild grub config

bmc01 is Gen10 hardware and boots UEFI. Use the UEFI grub config path:
```bash
grub2-mkconfig -o /boot/efi/EFI/redhat/grub.cfg
```
(Not `/boot/grub2/grub.cfg` — that is the BIOS path and changes written there will be silently ignored on a UEFI system.)

### Step 4: Rebuild initramfs
```bash
dracut --force
```
This bakes the serial console parameters into the initramfs so the LUKS passphrase prompt appears on `ttyS0`. Risk: if the rebuild produces a bad initramfs, the machine will drop to a dracut emergency shell on next boot. The backup from Step 2 is recovery.

### Step 5: Reboot — transitional LUKS unlock

Use the existing Playwright/graphical console path one final time to enter the LUKS passphrase after this reboot. After this reboot succeeds, VSP handles all future unlocks.

### Step 6: Verify

```bash
# From workstation — SSH to iLO, run VSP, confirm OS login prompt appears on serial
ssh admin@bmc.example.com
VSP
```

---

## Claude Code Integration

Register in MCP settings:
```json
{
  "iron-lo": {
    "command": "python3",
    "args": ["/opt/iron-lo/mcp_server.py"]
  }
}
```

**Dependencies (`requirements.txt`):**
```
mcp
httpx
asyncssh
```

---

## Before / After

| Scenario | Today (Playwright) | After |
|---|---|---|
| Check server health | Screenshot iLO dashboard | `ilo_get_status()` → JSON |
| Power cycle | Navigate to Power menu, click Reset | `ilo_power(action="reset")` |
| Graceful shutdown | Navigate to Power menu | `ilo_power(action="off")` |
| Hard power cut | Navigate to Power menu | `ilo_power(action="off", force=True)` |
| LUKS unlock | Watch KVM screenshot for passphrase prompt, send keys | `ilo_console_attach` → `read` → `write` → `read` |
| Mount ISO | Navigate virtual media wizard | `ilo_virtual_media(action="mount", url=...)` |
| One-time PXE boot | Navigate Boot Order UI | `ilo_boot_source(source="pxe", persistent=False)` |
| Emergency pixel access | Playwright (current) | Playwright (unchanged) |

---

## Generalization

`config.py` accepts `ilo_host` and `cred_path` parameters. Once proven on bmc01, the same MCP server can be reused for other iLOs in the lab by registering additional MCP entries pointing to the same `mcp_server.py` with different config.
