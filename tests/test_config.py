# tests/test_config.py
import pytest
from config import get_profile, BmcProfile, _ILO_PROFILE, _IDRAC_PROFILE, _PROFILES


def test_get_profile_ilo():
    profile = get_profile("ilo")
    assert profile.bmc_type == "ilo"
    assert profile.system_path == "/Systems/1"


def test_get_profile_idrac():
    profile = get_profile("idrac")
    assert profile.bmc_type == "idrac"
    assert "/iDRAC.Embedded.1" in profile.manager_path


def test_get_profile_case_insensitive():
    assert get_profile("ILO").bmc_type == "ilo"
    assert get_profile("IDRAC").bmc_type == "idrac"


def test_get_profile_unknown_raises():
    with pytest.raises(ValueError, match="Unknown bmc_type"):
        get_profile("bmc9000")


def test_profiles_have_required_fields():
    for profile in _PROFILES.values():
        assert profile.bmc_type
        assert profile.system_path
        assert profile.manager_path
        assert profile.virtual_media_path
        assert profile.power_action_path
        assert profile.log_paths
        assert profile.console_command
        assert profile.console_exit_seq
        assert profile.ssh_host_key_algs
        assert profile.ssh_kex_algs
