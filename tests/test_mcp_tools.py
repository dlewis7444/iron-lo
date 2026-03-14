# tests/test_mcp_tools.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def mock_pass_credentials():
    """Prevent real `pass` calls and provide env vars when importing mcp_server."""
    mock_result = MagicMock()
    mock_result.stdout = "testpassword\n"
    env = {"BMC_HOST": "test-bmc.local", "BMC_CRED_PATH": "internal/test-bmc/admin", "BMC_TYPE": "ilo"}
    with patch("subprocess.run", return_value=mock_result), \
         patch.dict("os.environ", env):
        yield


@pytest.fixture
def mock_redfish():
    with patch("mcp_server._redfish") as m:
        yield m


@pytest.fixture
def mock_console():
    with patch("mcp_server._console") as m:
        yield m


async def test_bmc_get_status_success(mock_redfish):
    import mcp_server
    mock_redfish.get_status = AsyncMock(return_value={
        "power": "On", "health": "OK", "uid": "Off",
        "post_state": "FinishedPost", "bios_ver": "U30", "bmc_ver": "2.55",
    })

    result = await mcp_server.bmc_get_status()

    assert result["power"] == "On"


async def test_bmc_get_status_handles_exception(mock_redfish):
    import mcp_server
    mock_redfish.get_status = AsyncMock(side_effect=Exception("connection refused"))

    result = await mcp_server.bmc_get_status()

    assert "error" in result
    assert "connection refused" in result["error"]


async def test_bmc_power_invalid_action(mock_redfish):
    import mcp_server

    result = await mcp_server.bmc_power("explode")

    assert result == {"error": "invalid action: explode", "code": "invalid_action"}
    mock_redfish.power.assert_not_called()


async def test_bmc_power_valid(mock_redfish):
    import mcp_server
    mock_redfish.power = AsyncMock(return_value={
        "action": "reset", "reset_type": "GracefulRestart", "result": "accepted"
    })

    result = await mcp_server.bmc_power("reset")

    assert result["result"] == "accepted"
    mock_redfish.power.assert_awaited_once_with("reset", False)


async def test_bmc_boot_source_invalid(mock_redfish):
    import mcp_server

    result = await mcp_server.bmc_boot_source("floppy")

    assert "error" in result
    mock_redfish.boot_source.assert_not_called()


async def test_bmc_virtual_media_requires_url_for_mount(mock_redfish):
    import mcp_server

    result = await mcp_server.bmc_virtual_media("mount", url="")

    assert result == {"error": "url required for mount", "code": "missing_url"}


async def test_bmc_virtual_media_mount(mock_redfish):
    import mcp_server
    mock_redfish.virtual_media = AsyncMock(return_value={
        "inserted": True, "connected": True, "image_url": "http://x/os.iso", "slot": "2"
    })

    result = await mcp_server.bmc_virtual_media("mount", url="http://x/os.iso")

    assert result["inserted"] is True
    mock_redfish.virtual_media.assert_awaited_once_with("mount", "http://x/os.iso")


async def test_bmc_get_event_log_invalid_log(mock_redfish):
    import mcp_server

    result = await mcp_server.bmc_get_event_log("kernel")

    assert isinstance(result, list)
    assert "error" in result[0]


async def test_bmc_console_attach(mock_console):
    import mcp_server
    mock_console.attach = AsyncMock(return_value={"status": "attached"})

    result = await mcp_server.bmc_console_attach()

    assert result == {"status": "attached"}


async def test_bmc_console_read(mock_console):
    import mcp_server
    mock_console.read = AsyncMock(return_value={"output": "login: ", "truncated": False})

    result = await mcp_server.bmc_console_read(timeout_s=10)

    assert result["output"] == "login: "
    mock_console.read.assert_awaited_once_with(10)


async def test_bmc_console_write(mock_console):
    import mcp_server
    mock_console.write = AsyncMock(return_value={"bytes_written": 12})

    result = await mcp_server.bmc_console_write("mypassword")

    assert result["bytes_written"] == 12
    mock_console.write.assert_awaited_once_with("mypassword", True)


async def test_bmc_console_send_key(mock_console):
    import mcp_server
    mock_console.send_key = AsyncMock(return_value={"sent": "ctrl_c"})

    result = await mcp_server.bmc_console_send_key("ctrl_c")

    assert result == {"sent": "ctrl_c"}


async def test_bmc_console_detach(mock_console):
    import mcp_server
    mock_console.detach = AsyncMock(return_value={"status": "detached"})

    result = await mcp_server.bmc_console_detach()

    assert result == {"status": "detached"}
