# tests/test_config.py
from unittest.mock import patch, MagicMock
import pytest
from config import IloConfig, load_config


def test_load_config_reads_env_vars():
    with patch.dict("os.environ", {"ILO_HOST": "myilo.local", "ILO_CRED_PATH": "internal/myilo/admin"}):
        config = load_config()
    assert config.host == "myilo.local"
    assert config.cred_path == "internal/myilo/admin"


def test_load_config_raises_on_missing_env_var():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(KeyError):
            load_config()


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
