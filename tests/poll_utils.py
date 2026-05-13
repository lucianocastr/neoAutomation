import time
from pathlib import Path
from functools import lru_cache

import yaml

from tests.api_client import NEOApiClient
from tests.metrology import MetrologyProfile
from tests.errors import StabilizationError


@lru_cache(maxsize=1)
def _stabilization_cfg() -> dict:
    cfg_path = Path(__file__).parent.parent / "config" / "hardware_params.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)["stabilization"]


def poll_until_stable(
    api: NEOApiClient,
    profile: MetrologyProfile,
    expected_weight_kg: float,
    max_wait_s: float = None,
    consecutive_ok: int = None,
) -> float:
    """
    Espera hasta que la API devuelva expected_weight_kg ± tolerancia durante
    N lecturas consecutivas. Lanza StabilizationError si se agota max_wait_s.
    Retorna el valor final estabilizado en kg.

    La tolerancia usa abs(expected_weight_kg) para manejar correctamente
    lecturas negativas (ej. cuando el pin se retrae con tara activa).
    """
    cfg = _stabilization_cfg()
    max_wait   = max_wait_s    if max_wait_s    is not None else cfg["max_wait_s"]
    n_required = consecutive_ok if consecutive_ok is not None else cfg["stable_reads"]
    interval   = cfg["poll_interval_s"]

    tol_kg = profile.tolerance_g_for(abs(expected_weight_kg)) / 1000

    deadline    = time.monotonic() + max_wait
    consecutive = 0
    last        = None

    while time.monotonic() < deadline:
        last = api.get_weight(profile.unit_to_kg)
        if abs(last - expected_weight_kg) <= tol_kg:
            consecutive += 1
            if consecutive >= n_required:
                return last
        else:
            consecutive = 0
        time.sleep(interval)

    raise StabilizationError(
        f"Peso no estabilizó en {max_wait}s: "
        f"último={last * 1000:.1f}g, "
        f"esperado={expected_weight_kg * 1000:.1f}g ± {tol_kg * 1000:.1f}g"
    )
