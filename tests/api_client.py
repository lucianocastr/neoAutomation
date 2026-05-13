import time
import requests
from typing import List
from tests.errors import ConnectivityError, ActuatorError
from tests.errors import TimeoutError as NEOTimeout


class NEOApiClient:
    def __init__(self, base_url: str, timeout_s: int = 5):
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s
        self._timeline: List[dict] = []

    # ── Endpoints tipados ──────────────────────────────────────

    def ping(self) -> str:
        resp = self._get("/api/ping")
        # /api/ping retorna el string JSON "pong", no un dict
        return resp if isinstance(resp, str) else resp["status"]

    def signature(self) -> dict:
        return self._get("/api/signature")

    def get_weight(self, unit_to_kg: float = 1.0) -> float:
        """
        Retorna el peso en kg.
        unit_to_kg: factor de conversión del perfil metrológico activo.
          - kg (AR/BR): 1.0
          - lb (US):    0.453592
        Proveer vía metrology.unit_to_kg desde el fixture de sesión.
        """
        raw = self._get("/api/weight")
        # La API retorna coma como separador decimal: "0,000" → "0.000"
        w = float(str(raw["weight"]).replace(",", "."))
        return w * unit_to_kg

    def get_product(self) -> dict:
        return self._get("/api/product")

    def load_plu(self, plu: int) -> dict:
        return self._post("/api/plu/load", {"plu": plu})

    def create_plu(self, data: dict) -> dict:
        return self._post("/api/plu/create", data)

    # ── Evidencia ──────────────────────────────────────────────

    def dump_timeline(self) -> List[dict]:
        return list(self._timeline)

    def clear_timeline(self):
        self._timeline.clear()

    # ── Infraestructura ────────────────────────────────────────

    def _get(self, path: str) -> dict:
        return self._request("GET", path)

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, json=body)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        t0 = time.monotonic()
        try:
            r = requests.request(method, f"{self._base}{path}",
                                 timeout=self._timeout, **kwargs)
            r.raise_for_status()
            body = r.json()
            self._timeline.append({
                "t_ms": round((time.monotonic() - t0) * 1000),
                "method": method,
                "path": path,
                "status": r.status_code,
            })
            return body
        except requests.Timeout:
            raise NEOTimeout(f"{method} {path} timeout después de {self._timeout}s")
        except requests.ConnectionError:
            raise ConnectivityError(f"Device no alcanzable: {self._base}")
        except requests.HTTPError as e:
            raise NEOTimeout(f"{method} {path} → HTTP {e.response.status_code}")
