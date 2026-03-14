# serial_console.py
import asyncio
import asyncssh
from typing import Optional


_KEY_MAP = {
    "ctrl_c": "\x03",
    "ctrl_d": "\x04",
    "ctrl_l": "\x0c",
    "esc":    "\x1b",
}


class SerialConsole:
    def __init__(self, host: str, username: str, password: str):
        self._host = host
        self._username = username
        self._password = password
        self._conn: Optional[asyncssh.SSHClientConnection] = None
        self._process: Optional[asyncssh.SSHClientProcess] = None

    @property
    def is_attached(self) -> bool:
        return self._conn is not None and self._process is not None

    async def attach(self) -> dict:
        if self.is_attached:
            return {"status": "already_attached"}
        self._conn = await asyncssh.connect(
            self._host,
            username=self._username,
            password=self._password,
            known_hosts=None,
            server_host_key_algs=["ssh-rsa"],
            kex_algs=["diffie-hellman-group14-sha256", "diffie-hellman-group14-sha1"],
        )
        self._process = await self._conn.create_process("VSP")
        return {"status": "attached"}

    async def detach(self) -> dict:
        if not self.is_attached:
            return {"status": "detached"}
        try:
            self._process.stdin.write("\x1b(")
            await asyncio.sleep(0.2)
        except Exception:
            pass
        try:
            self._process.close()
        except Exception:
            pass
        try:
            self._conn.close()
        except Exception:
            pass
        self._process = None
        self._conn = None
        return {"status": "detached"}

    async def read(self, timeout_s: int = 5) -> dict:
        if not self.is_attached:
            return {"error": "not attached", "code": "not_attached"}
        try:
            data = await asyncio.wait_for(
                self._process.stdout.read(4096),
                timeout=timeout_s,
            )
            return {"output": data, "truncated": len(data) == 4096}
        except asyncio.TimeoutError:
            return {"output": "", "truncated": False}

    async def write(self, text: str, send_enter: bool = True) -> dict:
        if not self.is_attached:
            return {"error": "not attached", "code": "not_attached"}
        payload = text + ("\n" if send_enter else "")
        self._process.stdin.write(payload)
        return {"bytes_written": len(payload.encode())}

    async def send_key(self, key: str) -> dict:
        if not self.is_attached:
            return {"error": "not attached", "code": "not_attached"}
        char = _KEY_MAP.get(key)
        if not char:
            return {"error": f"unknown key: {key}", "code": "invalid_key"}
        self._process.stdin.write(char)
        return {"sent": key}
