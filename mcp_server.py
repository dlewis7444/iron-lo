# mcp_server.py
import uuid
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from config import get_profile
from redfish import RedfishClient
from serial_console import SerialConsole


_connections: dict[str, tuple[RedfishClient, SerialConsole]] = {}


def _resolve(connection_id: str) -> tuple[RedfishClient, SerialConsole]:
    try:
        return _connections[connection_id]
    except KeyError:
        raise KeyError(f"Unknown connection_id: {connection_id!r}. "
                       "Call bmc_connect first to register a BMC.")


@asynccontextmanager
async def _lifespan(_mcp: FastMCP):
    yield
    for redfish, console in _connections.values():
        try:
            await console.detach()
        except Exception:
            pass
        await redfish.close()
    _connections.clear()


mcp = FastMCP("iron-lo", lifespan=_lifespan)


def _error(msg: str, code: str) -> dict:
    return {"error": msg, "code": code}


def _exc_msg(e: Exception) -> str:
    s = str(e)
    return s if s else f"{type(e).__name__}"


@mcp.tool()
async def bmc_connect(host: str, bmc_type: str, username: str, password: str) -> dict:
    """Register BMC credentials for this session. No network call is made.
    Returns a connection_id to pass to all other bmc_* tools."""
    try:
        profile = get_profile(bmc_type)
    except ValueError as e:
        return _error(str(e), "invalid_bmc_type")
    cid = str(uuid.uuid4())
    _connections[cid] = (
        RedfishClient(host, username, password, profile),
        SerialConsole(host, username, password, profile),
    )
    return {"connection_id": cid}


@mcp.tool()
async def bmc_get_status(connection_id: str) -> dict:
    """Get current BMC status: power state, health, UID LED, POST state, BIOS and BMC versions."""
    try:
        redfish, console = _resolve(connection_id)
        return await redfish.get_status()
    except KeyError as e:
        return _error(str(e), "unknown_connection")
    except Exception as e:
        return _error(_exc_msg(e), "redfish_error")


@mcp.tool()
async def bmc_power(connection_id: str, action: str, force: bool = False) -> dict:
    """Control server power. action: on|off|reset|nmi. force=True skips graceful shutdown/restart.
    Returns {action, reset_type, result} — reset_type is the Redfish ResetType sent to the BMC."""
    if action not in ("on", "off", "reset", "nmi"):
        return _error(f"invalid action: {action}", "invalid_action")
    try:
        redfish, console = _resolve(connection_id)
        return await redfish.power(action, force)
    except KeyError as e:
        return _error(str(e), "unknown_connection")
    except Exception as e:
        return _error(_exc_msg(e), "redfish_error")


@mcp.tool()
async def bmc_boot_source(connection_id: str, source: str, persistent: bool = False) -> dict:
    """Set boot source. source: hdd|pxe|cd|uefi_shell. persistent=False for one-time override."""
    if source not in ("hdd", "pxe", "cd", "uefi_shell"):
        return _error(f"invalid source: {source}", "invalid_source")
    try:
        redfish, console = _resolve(connection_id)
        return await redfish.boot_source(source, persistent)
    except KeyError as e:
        return _error(str(e), "unknown_connection")
    except Exception as e:
        return _error(_exc_msg(e), "redfish_error")


@mcp.tool()
async def bmc_virtual_media(connection_id: str, action: str, url: str = "") -> dict:
    """Mount or unmount virtual media. action: mount|unmount. url required for mount."""
    if action not in ("mount", "unmount"):
        return _error(f"invalid action: {action}", "invalid_action")
    if action == "mount" and not url:
        return _error("url required for mount", "missing_url")
    try:
        redfish, console = _resolve(connection_id)
        return await redfish.virtual_media(action, url or None)
    except KeyError as e:
        return _error(str(e), "unknown_connection")
    except Exception as e:
        return _error(_exc_msg(e), "redfish_error")


@mcp.tool()
async def bmc_get_event_log(connection_id: str, log: str, limit: int = 20) -> list:
    """Get BMC or system event log entries. log: bmc|system."""
    if log not in ("bmc", "system"):
        return [_error(f"invalid log: {log}", "invalid_log")]
    try:
        redfish, console = _resolve(connection_id)
        return await redfish.get_event_log(log, limit)
    except KeyError as e:
        return [_error(str(e), "unknown_connection")]
    except Exception as e:
        return [_error(_exc_msg(e), "redfish_error")]


@mcp.tool()
async def bmc_console_attach(connection_id: str) -> dict:
    """Attach to the BMC serial console over SSH. Idempotent."""
    try:
        redfish, console = _resolve(connection_id)
        return await console.attach()
    except KeyError as e:
        return _error(str(e), "unknown_connection")
    except Exception as e:
        return _error(_exc_msg(e), "ssh_error")


@mcp.tool()
async def bmc_console_read(connection_id: str, timeout_s: int = 5) -> dict:
    """
    Read pending serial console output since last read (consume-and-advance).
    Empty output means nothing arrived within timeout_s — retry if waiting for a prompt.
    """
    try:
        redfish, console = _resolve(connection_id)
        return await console.read(timeout_s)
    except KeyError as e:
        return _error(str(e), "unknown_connection")
    except Exception as e:
        return _error(_exc_msg(e), "console_error")


@mcp.tool()
async def bmc_console_write(connection_id: str, text: str, send_enter: bool = True) -> dict:
    """Write text to the serial console. Caller is responsible for supplying the correct text."""
    try:
        redfish, console = _resolve(connection_id)
        return await console.write(text, send_enter)
    except KeyError as e:
        return _error(str(e), "unknown_connection")
    except Exception as e:
        return _error(_exc_msg(e), "console_error")


@mcp.tool()
async def bmc_console_send_key(connection_id: str, key: str) -> dict:
    """Send a control key to the serial console. key: ctrl_c|ctrl_d|ctrl_l|esc."""
    try:
        redfish, console = _resolve(connection_id)
        return await console.send_key(key)
    except KeyError as e:
        return _error(str(e), "unknown_connection")
    except Exception as e:
        return _error(_exc_msg(e), "console_error")


@mcp.tool()
async def bmc_console_detach(connection_id: str) -> dict:
    """Detach from the serial console. Sends the BMC-specific exit sequence before closing."""
    try:
        redfish, console = _resolve(connection_id)
        return await console.detach()
    except KeyError as e:
        return _error(str(e), "unknown_connection")
    except Exception as e:
        return _error(_exc_msg(e), "console_error")


if __name__ == "__main__":
    mcp.run()
