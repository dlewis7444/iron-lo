# config.py
from dataclasses import dataclass


@dataclass
class BmcProfile:
    bmc_type: str
    system_path: str
    manager_path: str
    virtual_media_path: str
    power_action_path: str
    log_paths: dict          # keys: "bmc", "system"
    console_command: str     # "VSP" or "console com2"
    console_exit_seq: str    # "\x1b(" or "\r~."
    ssh_host_key_algs: list[str]
    ssh_kex_algs: list[str]


_ILO_PROFILE = BmcProfile(
    bmc_type="ilo",
    system_path="/Systems/1/",
    manager_path="/Managers/1/",
    virtual_media_path="/Managers/1/VirtualMedia/2/",
    power_action_path="/Systems/1/Actions/ComputerSystem.Reset/",
    log_paths={
        "bmc":    "/Managers/1/LogServices/IEL/Entries/",
        "system": "/Systems/1/LogServices/IML/Entries/",
    },
    console_command="VSP",
    console_exit_seq="\x1b(",
    ssh_host_key_algs=["ssh-rsa"],
    ssh_kex_algs=["diffie-hellman-group14-sha256", "diffie-hellman-group14-sha1"],
)

_IDRAC_PROFILE = BmcProfile(
    bmc_type="idrac",
    system_path="/Systems/System.Embedded.1/",
    manager_path="/Managers/iDRAC.Embedded.1/",
    virtual_media_path="/Managers/iDRAC.Embedded.1/VirtualMedia/CD/",
    power_action_path="/Systems/System.Embedded.1/Actions/ComputerSystem.Reset/",
    log_paths={
        "bmc":    "/Managers/iDRAC.Embedded.1/Logs/Sel/",
        "system": "/Managers/iDRAC.Embedded.1/Logs/Lclog/",
    },
    console_command="console com2",
    console_exit_seq="\r~.",
    ssh_host_key_algs=["ssh-rsa"],
    ssh_kex_algs=["diffie-hellman-group14-sha256", "diffie-hellman-group14-sha1"],
)

_PROFILES = {"ilo": _ILO_PROFILE, "idrac": _IDRAC_PROFILE}


def get_profile(bmc_type: str) -> BmcProfile:
    key = bmc_type.lower()
    if key not in _PROFILES:
        raise ValueError(f"Unknown bmc_type: {bmc_type!r}. Must be one of: {list(_PROFILES)}")
    return _PROFILES[key]
