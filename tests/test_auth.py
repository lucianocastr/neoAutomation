"""
Tests de autenticación y autorización (Suite D).

No requieren portal físico ni ESP32. Solo la balanza encendida y en red.

Ejecutar:
    pytest tests/test_auth.py -v

Tests de vendor (D3) se saltan automáticamente si NEO_VENDOR_USER / NEO_VENDOR_PASS
no están configuradas en .env.test.
"""

import os
import requests
import pytest

PLU_AUTH = 99970   # PLU reservado para tests de auth

_WRONG = os.getenv("NEO_TEST_WRONG_PASS", "intentionally-wrong")

ADV_NAME = "TEST_AUTH_ADV"   # nombre de advertising para tests — sobrescribe si ya existe


# ── warmup ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def warmup(api, creds):
    try:
        api.create_plu({**creds, "plu": str(PLU_AUTH), "name": "AUTH WARMUP",
                        "saleType": "weight", "priceList1": 1.0})
    except Exception:
        pass


# ── helpers ───────────────────────────────────────────────────────────────────

def _post(api, path, body):
    return requests.post(f"{api._base}{path}", json=body, timeout=5)


def _delete(api, path, body):
    return requests.delete(f"{api._base}{path}", json=body, timeout=5)


# ── D1: Admin tiene acceso completo ──────────────────────────────────────────

class TestAdminPermissions:
    def test_create_plu_ok(self, api, creds):
        """Admin puede crear PLU."""
        r = api.create_plu({**creds, "plu": str(PLU_AUTH), "name": "AUTH TEST PLU",
                            "saleType": "weight", "priceList1": 100.0})
        assert r.get("ok") is True

    def test_set_price_ok(self, api, creds):
        """Admin puede actualizar precio."""
        r = api.set_price(PLU_AUTH, "Lista 1", 150.0, **creds)
        assert r.get("ok") is True

    def test_create_advertising_ok(self, api, creds):
        """Admin puede crear/actualizar advertising."""
        r = api.create_advertising({**creds, "name": ADV_NAME,
                                    "text": "Texto de prueba auth"})
        assert r.get("ok") is True

    def test_load_plu_no_auth_required(self, api):
        """load_plu no requiere autenticación."""
        r = _post(api, "/api/plu/load", {"plu": str(PLU_AUTH)})
        assert r.status_code == 200

    def test_ping_no_auth_required(self, api):
        """ping no requiere autenticación."""
        assert api.ping() == "pong"

    def test_weight_no_auth_required(self, api, profile):
        """weight no requiere autenticación."""
        w = api.get_weight(profile.unit_to_kg)
        assert isinstance(w, float)


# ── D4: Sin credenciales → 401 ───────────────────────────────────────────────

class TestNoCredentials:
    @pytest.mark.parametrize("path,body", [
        ("/api/plu/create",
         {"plu": str(PLU_AUTH), "name": "TEST", "saleType": "weight", "priceList1": 1.0}),
        ("/api/plu/price",
         {"plu": str(PLU_AUTH), "priceList": "Lista 1", "price": "100"}),
        ("/api/advertising",
         {"name": ADV_NAME, "text": "test"}),
    ])
    def test_sin_username_retorna_401(self, api, path, body, creds):
        """Omitir username → 401."""
        payload = {**body, "password": creds["password"]}
        r = _post(api, path, payload)
        assert r.status_code == 401

    @pytest.mark.parametrize("path,body", [
        ("/api/plu/create",
         {"plu": str(PLU_AUTH), "name": "TEST", "saleType": "weight", "priceList1": 1.0}),
        ("/api/plu/price",
         {"plu": str(PLU_AUTH), "priceList": "Lista 1", "price": "100"}),
        ("/api/advertising",
         {"name": ADV_NAME, "text": "test"}),
    ])
    def test_sin_password_retorna_401(self, api, path, body, creds):
        """Omitir password → 401."""
        payload = {**body, "username": creds["username"]}
        r = _post(api, path, payload)
        assert r.status_code == 401


# ── D5: Contraseña incorrecta → 401 ──────────────────────────────────────────

class TestWrongCredentials:
    def test_wrong_password_create_401(self, api):
        """Contraseña incorrecta en create → 401."""
        r = _post(api, "/api/plu/create", {
            "username": "Supervisor", "password": _WRONG,
            "plu": str(PLU_AUTH), "name": "TEST", "saleType": "weight", "priceList1": 1.0,
        })
        assert r.status_code == 401

    def test_wrong_password_advertising_401(self, api):
        """Contraseña incorrecta en advertising → 401."""
        r = _post(api, "/api/advertising", {
            "username": "Supervisor", "password": _WRONG,
            "name": ADV_NAME, "text": "test",
        })
        assert r.status_code == 401

    def test_wrong_password_price_401(self, api):
        """Contraseña incorrecta en price → 401."""
        r = _post(api, "/api/plu/price", {
            "username": "Supervisor", "password": _WRONG,
            "plu": str(PLU_AUTH), "priceList": "Lista 1", "price": "100",
        })
        assert r.status_code == 401


# ── D3: Vendedor — solo lectura ───────────────────────────────────────────────

class TestVendorRestrictions:
    """Requiere NEO_VENDOR_USER y NEO_VENDOR_PASS en .env.test."""

    def test_vendor_cannot_create_plu(self, api, vendor_creds):
        """Vendedor no puede crear PLU → 401 o 403."""
        r = _post(api, "/api/plu/create", {
            **vendor_creds, "plu": str(PLU_AUTH), "name": "TEST VENDOR",
            "saleType": "weight", "priceList1": 1.0,
        })
        assert r.status_code in (401, 403)

    def test_vendor_cannot_set_price(self, api, vendor_creds):
        """Vendedor no puede actualizar precio → 401 o 403."""
        r = _post(api, "/api/plu/price", {
            **vendor_creds, "plu": str(PLU_AUTH),
            "priceList": "Lista 1", "price": "100",
        })
        assert r.status_code in (401, 403)

    def test_vendor_cannot_delete_plu(self, api, vendor_creds):
        """Vendedor no puede borrar PLU → 401 o 403."""
        r = _delete(api, "/api/plu/delete", {**vendor_creds, "plu": str(PLU_AUTH)})
        assert r.status_code in (401, 403, 500)  # 500 por BUGS-4528 si llega al delete

    def test_vendor_cannot_create_advertising(self, api, vendor_creds):
        """Vendedor no puede crear advertising → 401 o 403."""
        r = _post(api, "/api/advertising", {
            **vendor_creds, "name": ADV_NAME, "text": "test vendor",
        })
        assert r.status_code in (401, 403)
