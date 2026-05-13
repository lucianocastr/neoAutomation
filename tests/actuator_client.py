import json
import socket
from tests.errors import ActuatorError


class ActuatorClient:
    """Cliente TCP para el firmware actuador ESP32-S3 (firmware/actuator/)."""

    def __init__(self, host: str, port: int = 9999, timeout: float = 30.0):
        self._host = host
        self._port = port
        self._timeout = timeout

    def home(self) -> dict:
        return self._send({"cmd": "HOME"})

    def zero(self) -> dict:
        return self._send({"cmd": "ZERO"})

    def set_weight(self, grams: float) -> dict:
        return self._send({"cmd": "SET_WEIGHT", "grams": grams})

    def set_calibration(self, steps_per_gram: float) -> dict:
        return self._send({"cmd": "SET_CALIBRATION", "steps_per_gram": steps_per_gram})

    def status(self) -> dict:
        return self._send({"cmd": "STATUS"})

    def _send(self, payload: dict) -> dict:
        try:
            with socket.create_connection((self._host, self._port), timeout=self._timeout) as s:
                s.sendall((json.dumps(payload) + "\n").encode())
                data = b""
                while True:
                    chunk = s.recv(1024)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
        except OSError as e:
            raise ActuatorError(f"Actuador no alcanzable {self._host}:{self._port} — {e}")

        try:
            resp = json.loads(data.decode().strip())
        except json.JSONDecodeError as e:
            raise ActuatorError(f"Respuesta inválida del actuador: {data!r} — {e}")

        if resp.get("status") != "ok":
            raise ActuatorError(
                f"Actuador reportó error: {resp.get('message', resp)}"
            )
        return resp
