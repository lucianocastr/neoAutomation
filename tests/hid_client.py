import json
import socket
from tests.errors import ActuatorError


class HIDClient:
    """
    Cliente TCP para el firmware HID ESP32-S3 (firmware/hid/hid.ino).
    El ESP32 actúa como teclado USB conectado a la balanza; este cliente
    le envía comandos por WiFi y él los reenvía como pulsaciones HID.

    Protocolo: {"cmd": "KEY_PRESS", "key": "<nombre>"} → {"status": "ok"}
    """

    def __init__(self, host: str, port: int = 9999, timeout: float = 5.0):
        self._host = host
        self._port = port
        self._timeout = timeout

    def tare(self) -> None:
        """F2 — aplica TARA en la balanza."""
        self._send({"cmd": "KEY_PRESS", "key": "F2"})

    def zero(self) -> None:
        """F4 — cancela tara / vuelve a cero."""
        self._send({"cmd": "KEY_PRESS", "key": "F4"})

    def ok(self) -> None:
        """F3 — carga PLU / tecla OK."""
        self._send({"cmd": "KEY_PRESS", "key": "F3"})

    def enter(self) -> None:
        """ENTER — confirma venta."""
        self._send({"cmd": "KEY_PRESS", "key": "ENTER"})

    def menu(self) -> None:
        """F10 — abre menú."""
        self._send({"cmd": "KEY_PRESS", "key": "F10"})

    def send_key(self, key: str) -> None:
        """Envía cualquier tecla soportada por el firmware HID."""
        self._send({"cmd": "KEY_PRESS", "key": key})

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
            raise ActuatorError(f"HID ESP32 no alcanzable {self._host}:{self._port} — {e}")

        try:
            resp = json.loads(data.decode().strip())
        except json.JSONDecodeError as e:
            raise ActuatorError(f"Respuesta inválida del HID: {data!r} — {e}")

        if resp.get("status") != "ok":
            raise ActuatorError(f"HID reportó error: {resp.get('msg', resp)}")
        return resp
