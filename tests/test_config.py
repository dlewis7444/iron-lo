import subprocess
from unittest.mock import patch, MagicMock
from config import IloConfig, FHRDM01_ILO


def test_bmc01_ilo_singleton():
    assert FHRDM01_ILO.host == "bmc.example.com"
    assert FHRDM01_ILO.cred_path == "vendor/bmc01/admin"


def test_get_credentials_returns_username_from_path():
    config = IloConfig(host="test-ilo.local", cred_path="internal/test-ilo/myuser")
    mock_result = MagicMock()
    mock_result.stdout = "mypassword\n"
    with patch("subprocess.run", return_value=mock_result):
        username, password = config.get_credentials()
    assert username == "myuser"
    assert password == "mypassword"


def test_get_credentials_strips_whitespace():
    config = IloConfig(host="test-ilo.local", cred_path="internal/test-ilo/admin")
    mock_result = MagicMock()
    mock_result.stdout = "  secret123  \n"
    with patch("subprocess.run", return_value=mock_result):
        _, password = config.get_credentials()
    assert password == "secret123"


def test_get_credentials_calls_pass_show():
    config = IloConfig(host="test-ilo.local", cred_path="internal/test-ilo/admin")
    mock_result = MagicMock()
    mock_result.stdout = "pw\n"
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        config.get_credentials()
    mock_run.assert_called_once_with(
        ["pass", "show", "internal/test-ilo/admin"],
        capture_output=True, text=True, check=True,
    )
