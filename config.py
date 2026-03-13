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


FHRDM01_ILO = IloConfig(
    host="bmc.example.com",
    cred_path="vendor/bmc01/admin",
)
