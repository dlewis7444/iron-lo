# mcp_server.py
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from config import load_config
from redfish import RedfishClient
from serial_console import SerialConsole


@asynccontextmanager
async def _lifespan(_mcp: FastMCP):
    yield
    await _redfish.close()


mcp = FastMCP("hp-ilo", lifespan=_lifespan)

# Initialise clients — credentials fetched once at startup via pass
_config = load_config()
_username, _password = _config.get_credentials()
_redfish = RedfishClient(_config.host, _username, _password)
_console = SerialConsole(_config.host, _username, _password)


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
    """Control server power. action: on|off|reset|nmi. force=True skips graceful shutdown/restart.
    Returns {action, reset_type, result} — reset_type is the Redfish ResetType sent to iLO."""
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
