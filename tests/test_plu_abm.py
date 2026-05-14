"""
Tests de ABM (Alta/Baja/Modificación) de PLUs via API REST.

No requieren portal físico ni ESP32. Solo la balanza encendida y en red.

Ejecutar:
    pytest tests/test_plu_abm.py -v

Quirks de este firmware (documentados como comportamiento real):
  - DELETE /api/plu/delete → 500 siempre cuando el PLU existe (BUGS-4528)
    pero valida correctamente existencia (404) y creds (401) antes del bug de transacción.
  - DELETE → 500 causa lag ~1-2s en la API: nunca llamar _try_delete antes de create.
  - POST /api/plu/delete → 405 — workaround NEO2 no aplica a este firmware.
  - load_plu con PLU inexistente → 200 (no valida existencia).
  - set_price con PLU inexistente → 404 (sí valida existencia).
  - No se puede cambiar saleType via upsert (weight→unit retorna 500).
  - priceList1 obligatorio y positivo (BUGS-4547 resuelto).
  - Nombres de listas case-sensitive: "Lista 1", "Lista 2".
"""

import os
import requests
import pytest

PLU_TEST      = 99999   # PLU peso — se crea y persiste (delete roto)
PLU_TEST_UNIT = 99998   # PLU unitario separado — no conflicto de saleType con PLU_TEST
PLU_GHOST     = 999997  # PLU que nunca se crea — usado para tests de "no existe"

# Credencial inválida para tests de 401 — no es una cred real
_WRONG = os.getenv("NEO_TEST_WRONG_PASS", "intentionally-wrong")


# ── helpers ───────────────────────────────────────────────────────────────────

def _minimal_payload(creds: dict, plu: int = PLU_TEST,
                     name: str = "TEST AUTOMATIZACION") -> dict:
    return {**creds, "plu": str(plu), "name": name,
            "saleType": "weight", "priceList1": 100.00}


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def warmup_api(api, creds):
    """El primer write tras cold start puede fallar con 500 (connection pool JPA).
    Hacer un create previo (swallowing el posible 500) calienta el path de escritura."""
    try:
        api.create_plu(_minimal_payload(creds))
    except Exception:
        pass


@pytest.fixture
def existing_plu(api, creds):
    """Garantiza que PLU_TEST exista antes del test (upsert, sin delete previo).

    No llama _try_delete: DELETE→500 causa lag en la API que rompe el create siguiente.
    PLU_TEST persiste en la BD tras el test (delete roto — BUGS-4528).
    """
    api.create_plu(_minimal_payload(creds))
    yield PLU_TEST


# ── create ────────────────────────────────────────────────────────────────────

class TestPluCreate:
    def test_create_ok(self, api, creds):
        """Crear/upsertear PLU retorna ok=True."""
        r = api.create_plu(_minimal_payload(creds))
        assert r.get("ok") is True
        assert r.get("action") in ("created", "updated")

    def test_upsert_retorna_updated(self, api, creds, existing_plu):
        """Segunda creación del mismo PLU retorna action=updated."""
        r = api.create_plu(_minimal_payload(creds, name="TEST UPSERT"))
        assert r.get("ok") is True
        assert r.get("action") == "updated"

    def test_create_con_sale_type_unit(self, api, creds):
        """Crear PLU unitario (PLU_TEST_UNIT) retorna ok."""
        payload = {**creds, "plu": str(PLU_TEST_UNIT), "name": "TEST UNITARIO",
                   "saleType": "unit", "priceList1": 500.00}
        r = api.create_plu(payload)
        assert r.get("ok") is True

    def test_create_sin_name_retorna_400(self, api, creds):
        """Omitir name debe retornar HTTP 400."""
        payload = {**creds, "plu": str(PLU_TEST), "saleType": "weight", "priceList1": 100.0}
        r = requests.post(f"{api._base}/api/plu/create", json=payload, timeout=5)
        assert r.status_code == 400

    def test_create_sin_plu_retorna_400(self, api, creds):
        """Omitir plu debe retornar HTTP 400."""
        payload = {**creds, "name": "TEST", "saleType": "weight", "priceList1": 100.0}
        r = requests.post(f"{api._base}/api/plu/create", json=payload, timeout=5)
        assert r.status_code == 400

    def test_create_creds_incorrectas_retorna_401(self, api):
        """Credenciales incorrectas deben retornar HTTP 401."""
        payload = {"username": "Supervisor", "password": _WRONG,
                   "plu": str(PLU_TEST), "name": "TEST", "saleType": "weight", "priceList1": 100.0}
        r = requests.post(f"{api._base}/api/plu/create", json=payload, timeout=5)
        assert r.status_code == 401


# ── load ─────────────────────────────────────────────────────────────────────

class TestPluLoad:
    def test_load_plu_conocido(self, api):
        """Cargar PLU existente (57) retorna ok."""
        r = api.load_plu(57)
        assert r.get("ok") is True

    def test_load_plu_test(self, api, existing_plu):
        """Cargar PLU recién creado retorna ok."""
        r = api.load_plu(PLU_TEST)
        assert r.get("ok") is True

    def test_load_plu_inexistente_retorna_200(self, api):
        """load_plu no valida existencia — retorna 200 para cualquier número (comportamiento real)."""
        r = requests.post(f"{api._base}/api/plu/load", json={"plu": str(PLU_GHOST)}, timeout=5)
        assert r.status_code == 200


# ── price ─────────────────────────────────────────────────────────────────────

class TestPluPrice:
    def test_set_price_lista1(self, api, creds, existing_plu):
        """Actualizar precio Lista 1 retorna ok."""
        r = api.set_price(PLU_TEST, "Lista 1", 250.00, **creds)
        assert r.get("ok") is True

    def test_set_price_lista2(self, api, creds, existing_plu):
        """Actualizar precio Lista 2 retorna ok."""
        r = api.set_price(PLU_TEST, "Lista 2", 220.00, **creds)
        assert r.get("ok") is True

    def test_set_price_con_coma_decimal(self, api, creds, existing_plu):
        """Precio con coma decimal ('199,90') debe ser aceptado."""
        r = api.set_price(PLU_TEST, "Lista 1", "199,90", **creds)
        assert r.get("ok") is True

    def test_set_price_lista_inexistente_retorna_404(self, api, creds, existing_plu):
        """Lista con nombre incorrecto (minúsculas) debe retornar HTTP 404."""
        r = requests.post(f"{api._base}/api/plu/price", timeout=5, json={
            **creds, "plu": str(PLU_TEST),
            "priceList": "lista 1",  # case-sensitive — "Lista 1" es el nombre correcto
            "price": "100",
        })
        assert r.status_code == 404

    def test_set_price_plu_inexistente_retorna_404(self, api, creds):
        """set_price valida existencia del PLU — retorna 404 si no existe."""
        r = requests.post(f"{api._base}/api/plu/price", timeout=5, json={
            **creds, "plu": str(PLU_GHOST), "priceList": "Lista 1", "price": "100",
        })
        assert r.status_code == 404

    def test_set_price_creds_incorrectas_retorna_401(self, api, existing_plu):
        """Credenciales incorrectas en price deben retornar HTTP 401."""
        r = requests.post(f"{api._base}/api/plu/price", timeout=5, json={
            "username": "Supervisor", "password": _WRONG,
            "plu": str(PLU_TEST), "priceList": "Lista 1", "price": "100",
        })
        assert r.status_code == 401


# ── delete ────────────────────────────────────────────────────────────────────

class TestPluDelete:
    """
    BUGS-4528: DELETE /api/plu/delete → 500 cuando el PLU existe (transacción rota).
    El endpoint sí valida existencia (404) y creds (401) antes del bug.
    POST /api/plu/delete → 405 en este firmware (workaround NEO2 no aplica).
    """

    @pytest.mark.xfail(reason="BUGS-4528: DELETE → 500 cuando PLU existe", strict=False)
    def test_delete_retorna_ok(self, api, creds, existing_plu):
        """Borrar PLU existente debería retornar ok (falla por BUGS-4528)."""
        r = api.delete_plu(PLU_TEST, **creds)
        assert r.get("ok") is True

    def test_delete_plu_inexistente_retorna_404(self, api, creds):
        """Borrar PLU que no existe retorna 404 (validación de existencia funciona)."""
        r = requests.delete(f"{api._base}/api/plu/delete", timeout=5,
                            json={**creds, "plu": str(PLU_GHOST)})
        assert r.status_code == 404

    def test_delete_creds_incorrectas_retorna_401(self, api):
        """Credenciales incorrectas en delete retornan 401 (validación de creds funciona)."""
        r = requests.delete(f"{api._base}/api/plu/delete", timeout=5,
                            json={"username": "Supervisor", "password": _WRONG,
                                  "plu": str(PLU_TEST)})
        assert r.status_code == 401


# ── setup ─────────────────────────────────────────────────────────────────────

class TestSetup:
    def test_setup_responde(self, api):
        """/api/setup debe responder sin excepción."""
        r = api.get_setup()
        assert isinstance(r, dict)

    def test_setup_tiene_campos_esperados(self, api):
        """/api/setup retorna al menos name y number."""
        r = api.get_setup()
        assert "name" in r or "number" in r
