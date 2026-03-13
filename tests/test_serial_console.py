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
