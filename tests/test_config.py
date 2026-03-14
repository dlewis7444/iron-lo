# tests/test_config.py
from unittest.mock import patch, MagicMock
import pytest
from config import BmcConfig, load_config, _ILO_PROFILE, _IDRAC_PROFILE


def test_load_config_reads_ilo_env_vars():
    """Backward compat: ILO_HOST / ILO_CRED_PATH still work."""
    with patch.dict("os.environ", {"ILO_HOST": "myilo.local", "ILO_CRED_PATH": "internal/myilo/admin"}, clear=True):
        config = load_config()
    assert config.host == "myilo.local"
    assert config.cred_path == "internal/myilo/admin"
    assert config.profile.bmc_type == "ilo"


def test_load_config_raises_on_missing_env_var():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(KeyError):
            load_config()


def test_get_credentials_returns_username_from_path():
    config = BmcConfig(host="test-ilo.local", cred_path="internal/test-ilo/myuser", profile=_ILO_PROFILE)
    mock_result = MagicMock()
    mock_result.stdout = "mypassword\n"
    with patch("subprocess.run", return_value=mock_result):
        username, password = config.get_credentials()
    assert username == "myuser"
    assert password == "mypassword"


def test_get_credentials_strips_whitespace():
    config = BmcConfig(host="test-ilo.local", cred_path="internal/test-ilo/admin", profile=_ILO_PROFILE)
    mock_result = MagicMock()
    mock_result.stdout = "  secret123  \n"
    with patch("subprocess.run", return_value=mock_result):
        _, password = config.get_credentials()
    assert password == "secret123"


def test_get_credentials_calls_pass_show():
    config = BmcConfig(host="test-ilo.local", cred_path="internal/test-ilo/admin", profile=_ILO_PROFILE)
    mock_result = MagicMock()
    mock_result.stdout = "pw\n"
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        config.get_credentials()
    mock_run.assert_called_once_with(
        ["pass", "show", "internal/test-ilo/admin"],
        capture_output=True, text=True, check=True,
    )


def test_load_config_bmc_vars_with_idrac():
    """BMC_HOST / BMC_CRED_PATH / BMC_TYPE=idrac happy path."""
    env = {"BMC_HOST": "idrac.local", "BMC_CRED_PATH": "internal/idrac/root", "BMC_TYPE": "idrac"}
    with patch.dict("os.environ", env, clear=True):
        config = load_config()
    assert config.host == "idrac.local"
    assert config.cred_path == "internal/idrac/root"
    assert config.profile is _IDRAC_PROFILE


def test_load_config_bmc_host_takes_precedence():
    """BMC_HOST overrides ILO_HOST when both are set."""
    env = {"BMC_HOST": "bmc.local", "ILO_HOST": "old.local", "ILO_CRED_PATH": "internal/x/u"}
    with patch.dict("os.environ", env, clear=True):
        config = load_config()
    assert config.host == "bmc.local"


def test_load_config_bmc_type_defaults_to_ilo():
    with patch.dict("os.environ", {"ILO_HOST": "h.local", "ILO_CRED_PATH": "internal/x/u"}, clear=True):
        config = load_config()
    assert config.profile.bmc_type == "ilo"


def test_load_config_bmc_type_idrac_sets_idrac_paths():
    env = {"ILO_HOST": "h.local", "ILO_CRED_PATH": "internal/x/u", "BMC_TYPE": "idrac"}
    with patch.dict("os.environ", env, clear=True):
        config = load_config()
    assert config.profile.system_path == "/Systems/System.Embedded.1"
    assert config.profile.power_action_path == "/Systems/System.Embedded.1/Actions/ComputerSystem.Reset"


def test_load_config_unknown_bmc_type_raises():
    env = {"ILO_HOST": "h.local", "ILO_CRED_PATH": "internal/x/u", "BMC_TYPE": "bmc9000"}
    with patch.dict("os.environ", env, clear=True):
        with pytest.raises(ValueError, match="Unknown BMC_TYPE"):
            load_config()
