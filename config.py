# config.py
import os
import subprocess
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
    system_path="/Systems/1",
    manager_path="/Managers/1",
    virtual_media_path="/Managers/1/VirtualMedia/2",
    power_action_path="/Systems/1/Actions/ComputerSystem.Reset",
    log_paths={
        "bmc":    "/Managers/1/LogServices/IEL/Entries",
        "system": "/Systems/1/LogServices/IML/Entries",
    },
    console_command="VSP",
    console_exit_seq="\x1b(",
    ssh_host_key_algs=["ssh-rsa"],
    ssh_kex_algs=["diffie-hellman-group14-sha256", "diffie-hellman-group14-sha1"],
)

_IDRAC_PROFILE = BmcProfile(
    bmc_type="idrac",
    system_path="/Systems/System.Embedded.1",
    manager_path="/Managers/iDRAC.Embedded.1",
    virtual_media_path="/Managers/iDRAC.Embedded.1/VirtualMedia/CD",
    power_action_path="/Systems/System.Embedded.1/Actions/ComputerSystem.Reset",
    log_paths={
        "bmc":    "/Managers/iDRAC.Embedded.1/Logs/Sel",
        "system": "/Managers/iDRAC.Embedded.1/Logs/Lclog",
    },
    console_command="console com2",
    console_exit_seq="\r~.",
    ssh_host_key_algs=["ssh-rsa"],
    ssh_kex_algs=["diffie-hellman-group14-sha256", "diffie-hellman-group14-sha1"],
)

_PROFILES = {"ilo": _ILO_PROFILE, "idrac": _IDRAC_PROFILE}


@dataclass
class BmcConfig:
    host: str
    cred_path: str
    profile: BmcProfile

    def get_credentials(self) -> tuple[str, str]:
        """Fetch credentials from pass store. Returns (username, password)."""
        result = subprocess.run(
            ["pass", "show", self.cred_path],
            capture_output=True, text=True, check=True,
        )
        password = result.stdout.splitlines()[0].strip()
        username = self.cred_path.rsplit("/", 1)[-1]
        return username, password


def load_config() -> BmcConfig:
    """Load BMC config from environment variables. BMC_* vars take precedence over ILO_* for backward compat."""
    host = os.environ.get("BMC_HOST") or os.environ["ILO_HOST"]
    cred_path = os.environ.get("BMC_CRED_PATH") or os.environ["ILO_CRED_PATH"]
    bmc_type = os.environ.get("BMC_TYPE", "ilo").lower()
    if bmc_type not in _PROFILES:
        raise ValueError(f"Unknown BMC_TYPE: {bmc_type!r}. Must be one of: {list(_PROFILES)}")
    return BmcConfig(host=host, cred_path=cred_path, profile=_PROFILES[bmc_type])
