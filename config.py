# config.py
import os
import subprocess
from dataclasses import dataclass


@dataclass
class IloConfig:
    host: str
    cred_path: str

    def get_credentials(self) -> tuple[str, str]:
        """Fetch credentials from pass store. Returns (username, password)."""
        result = subprocess.run(
            ["pass", "show", self.cred_path],
            capture_output=True, text=True, check=True,
        )
        password = result.stdout.splitlines()[0].strip()
        username = self.cred_path.rsplit("/", 1)[-1]
        return username, password


def load_config() -> IloConfig:
    """Load iLO config from environment variables ILO_HOST and ILO_CRED_PATH."""
    host = os.environ["ILO_HOST"]
    cred_path = os.environ["ILO_CRED_PATH"]
    return IloConfig(host=host, cred_path=cred_path)
