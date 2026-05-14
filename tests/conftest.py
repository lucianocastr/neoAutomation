import os
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

from tests.api_client import NEOApiClient
from tests.actuator_client import ActuatorClient
from tests.hid_client import HIDClient
from tests.db_client import BalanzaDB
from tests.metrology import build_profile


def _load_env():
    env_path = Path(__file__).parent.parent / ".env.test"
    if env_path.exists():
        load_dotenv(env_path, override=True)


def _require(var: str) -> str:
    val = os.getenv(var)
    if not val:
        raise RuntimeError(
            f"Variable de entorno requerida no definida: {var}\n"
            f"Copiar .env.test.example a .env.test y completar los valores."
        )
    return val


@pytest.fixture(scope="session", autouse=True)
def load_env():
    _load_env()


@pytest.fixture(scope="session")
def api(load_env) -> NEOApiClient:
    base_url = f"http://{_require('NEO_IP')}:{_require('NEO_API_PORT')}"
    timeout  = int(os.getenv("API_TIMEOUT_S", "5"))
    return NEOApiClient(base_url, timeout_s=timeout)


@pytest.fixture(scope="session")
def actuator(load_env) -> ActuatorClient:
    host = _require("NEO_ESP32_IP")
    port = int(os.getenv("NEO_ESP32_PORT", "9999"))
    return ActuatorClient(host=host, port=port)


@pytest.fixture(scope="session")
def hid(load_env) -> HIDClient:
    host = _require("NEO_ESP32_IP")
    port = int(os.getenv("NEO_ESP32_PORT", "9999"))
    return HIDClient(host=host, port=port)


@pytest.fixture(scope="session")
def db(load_env) -> BalanzaDB:
    return BalanzaDB()


@pytest.fixture(scope="session")
def vendor_creds(load_env) -> dict:
    """Credenciales de vendedor. Tests que usan este fixture se saltan si no están configuradas."""
    user = os.getenv("NEO_VENDOR_USER", "")
    pw   = os.getenv("NEO_VENDOR_PASS", "")
    if not user or not pw:
        pytest.skip("NEO_VENDOR_USER / NEO_VENDOR_PASS no configuradas — skip vendor tests")
    return {"username": user, "password": pw}


@pytest.fixture(scope="session")
def creds(load_env) -> dict:
    return {
        "username": _require("NEO_WEB_USER"),
        "password": _require("NEO_WEB_PASS"),
    }


@pytest.fixture(scope="session")
def profile(load_env):
    variant = os.getenv("TEST_METROLOGY_PROFILE", "AR")
    cfg_path = Path(__file__).parent.parent / "config" / "hardware_params.yaml"
    with open(cfg_path) as f:
        raw_cfg = yaml.safe_load(f)
    available = list(raw_cfg["metrology"].keys())
    if variant not in available:
        raise RuntimeError(
            f"TEST_METROLOGY_PROFILE='{variant}' no válido. Opciones: {available}"
        )
    return build_profile(variant, raw_cfg["metrology"][variant])
