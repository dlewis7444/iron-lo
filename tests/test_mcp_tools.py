# tests/test_mcp_tools.py
import pytest
from unittest.mock import AsyncMock
import mcp_server


@pytest.fixture
def connection_with_mocks():
    cid = "test-connection-id"
    mock_redfish = AsyncMock()
    mock_console = AsyncMock()
    mcp_server._connections[cid] = (mock_redfish, mock_console)
    yield cid, mock_redfish, mock_console
    mcp_server._connections.pop(cid, None)


async def test_bmc_get_status_success(connection_with_mocks):
    cid, mock_redfish, _ = connection_with_mocks
    mock_redfish.get_status = AsyncMock(return_value={
        "power": "On", "health": "OK", "uid": "Off",
        "post_state": "FinishedPost", "bios_ver": "U30", "bmc_ver": "2.55",
    })

    result = await mcp_server.bmc_get_status(cid)

    assert result["power"] == "On"


async def test_bmc_get_status_handles_exception(connection_with_mocks):
    cid, mock_redfish, _ = connection_with_mocks
    mock_redfish.get_status = AsyncMock(side_effect=Exception("connection refused"))

    result = await mcp_server.bmc_get_status(cid)

    assert "error" in result
    assert "connection refused" in result["error"]


async def test_bmc_power_invalid_action(connection_with_mocks):
    cid, mock_redfish, _ = connection_with_mocks

    result = await mcp_server.bmc_power(cid, "explode")

    assert result == {"error": "invalid action: explode", "code": "invalid_action"}
    mock_redfish.power.assert_not_called()


async def test_bmc_power_valid(connection_with_mocks):
    cid, mock_redfish, _ = connection_with_mocks
    mock_redfish.power = AsyncMock(return_value={
        "action": "reset", "reset_type": "GracefulRestart", "result": "accepted"
    })

    result = await mcp_server.bmc_power(cid, "reset")

    assert result["result"] == "accepted"
    mock_redfish.power.assert_awaited_once_with("reset", False)


async def test_bmc_boot_source_invalid(connection_with_mocks):
    cid, mock_redfish, _ = connection_with_mocks

    result = await mcp_server.bmc_boot_source(cid, "floppy")

    assert "error" in result
    mock_redfish.boot_source.assert_not_called()


async def test_bmc_virtual_media_requires_url_for_mount(connection_with_mocks):
    cid, mock_redfish, _ = connection_with_mocks

    result = await mcp_server.bmc_virtual_media(cid, "mount", url="")

    assert result == {"error": "url required for mount", "code": "missing_url"}


async def test_bmc_virtual_media_mount(connection_with_mocks):
    cid, mock_redfish, _ = connection_with_mocks
    mock_redfish.virtual_media = AsyncMock(return_value={
        "inserted": True, "connected": True, "image_url": "http://x/os.iso", "slot": "2"
    })

    result = await mcp_server.bmc_virtual_media(cid, "mount", url="http://x/os.iso")

    assert result["inserted"] is True
    mock_redfish.virtual_media.assert_awaited_once_with("mount", "http://x/os.iso")


async def test_bmc_get_event_log_invalid_log(connection_with_mocks):
    cid, mock_redfish, _ = connection_with_mocks

    result = await mcp_server.bmc_get_event_log(cid, "kernel")

    assert isinstance(result, list)
    assert "error" in result[0]


async def test_bmc_console_attach(connection_with_mocks):
    cid, _, mock_console = connection_with_mocks
    mock_console.attach = AsyncMock(return_value={"status": "attached"})

    result = await mcp_server.bmc_console_attach(cid)

    assert result == {"status": "attached"}


async def test_bmc_console_read(connection_with_mocks):
    cid, _, mock_console = connection_with_mocks
    mock_console.read = AsyncMock(return_value={"output": "login: ", "truncated": False})

    result = await mcp_server.bmc_console_read(cid, timeout_s=10)

    assert result["output"] == "login: "
    mock_console.read.assert_awaited_once_with(10)


async def test_bmc_console_write(connection_with_mocks):
    cid, _, mock_console = connection_with_mocks
    mock_console.write = AsyncMock(return_value={"bytes_written": 12})

    result = await mcp_server.bmc_console_write(cid, "mypassword")

    assert result["bytes_written"] == 12
    mock_console.write.assert_awaited_once_with("mypassword", True)


async def test_bmc_console_send_key(connection_with_mocks):
    cid, _, mock_console = connection_with_mocks
    mock_console.send_key = AsyncMock(return_value={"sent": "ctrl_c"})

    result = await mcp_server.bmc_console_send_key(cid, "ctrl_c")

    assert result == {"sent": "ctrl_c"}


async def test_bmc_console_detach(connection_with_mocks):
    cid, _, mock_console = connection_with_mocks
    mock_console.detach = AsyncMock(return_value={"status": "detached"})

    result = await mcp_server.bmc_console_detach(cid)

    assert result == {"status": "detached"}


# --- New connection-based tests ---


async def test_bmc_connect_returns_connection_id():
    result = await mcp_server.bmc_connect("bmc.local", "ilo", "admin", "pass123")

    assert "connection_id" in result
    cid = result["connection_id"]
    assert cid in mcp_server._connections
    # Cleanup
    mcp_server._connections.pop(cid, None)


async def test_bmc_connect_invalid_bmc_type():
    result = await mcp_server.bmc_connect("bmc.local", "bmc9000", "admin", "pass123")

    assert result["code"] == "invalid_bmc_type"
    assert "bmc9000" in result["error"]


async def test_unknown_connection_id_returns_error():
    result = await mcp_server.bmc_get_status("nonexistent-id")

    assert result["code"] == "unknown_connection"


async def test_multiple_connections_independent():
    r1 = await mcp_server.bmc_connect("bmc1.local", "ilo", "admin", "pass1")
    r2 = await mcp_server.bmc_connect("bmc2.local", "idrac", "root", "pass2")

    assert r1["connection_id"] != r2["connection_id"]
    assert r1["connection_id"] in mcp_server._connections
    assert r2["connection_id"] in mcp_server._connections
    # Cleanup
    mcp_server._connections.pop(r1["connection_id"], None)
    mcp_server._connections.pop(r2["connection_id"], None)
