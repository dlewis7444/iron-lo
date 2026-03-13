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
    console, _ = attached_console

    result = await console.send_key("f12")

    assert result == {"error": "unknown key: f12", "code": "invalid_key"}


async def test_send_key_when_not_attached(console):
    result = await console.send_key("ctrl_c")
    assert result == {"error": "not attached", "code": "not_attached"}
