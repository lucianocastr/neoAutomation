"""
Tests de encoding UTF-8 y límites de campos (Suite F).

Verifica que la API almacene correctamente caracteres especiales del español
(ñ, tildes, °) y respete el límite de 56 caracteres del campo name.

No requieren portal físico ni ESP32. Solo la balanza encendida y en red.

Ejecutar:
    pytest tests/test_encoding.py -v
"""

import requests
import pytest

PLU_ENC = 99990   # PLU reservado para tests de encoding


# ── warmup ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def warmup(api, creds):
    try:
        api.create_plu({**creds, "plu": str(PLU_ENC), "name": "ENC WARMUP",
                        "saleType": "weight", "priceList1": 1.0})
    except Exception:
        pass


# ── helpers ───────────────────────────────────────────────────────────────────

def _create(api, creds, **kwargs):
    payload = {**creds, "plu": str(PLU_ENC), "saleType": "weight",
               "priceList1": 1.0, **kwargs}
    return api.create_plu(payload)


# ── F1: Caracteres argentinos ─────────────────────────────────────────────────

class TestArgentineChars:
    NAME_ENYE = "Jamón Crudo Ñ 25%"

    def test_enie_in_name_create_ok(self, api, creds):
        """Crear PLU con ñ/Ñ en name retorna ok."""
        r = _create(api, creds, name=self.NAME_ENYE)
        assert r.get("ok") is True

    def test_enie_in_name_stored_in_db(self, api, creds, db):
        """ñ en name se almacena correctamente en PostgreSQL."""
        _create(api, creds, name=self.NAME_ENYE)
        row = db.product_detail(PLU_ENC)
        assert row is not None
        assert row["name"] == self.NAME_ENYE

    def test_tildes_in_ingredients_stored(self, api, creds, db):
        """Tildes (á é í ó ú ü) en ingredients se almacenan correctamente."""
        ingredients = "Azúcar, harina, mantequilla, vainillín, canéla"
        _create(api, creds, name="TEST TILDES", ingredients=ingredients)
        row = db.product_detail(PLU_ENC)
        assert row is not None
        assert row["ingredients"] == ingredients

    def test_grado_celsius_in_preservation(self, api, creds, db):
        """Símbolo ° en preservationData se almacena correctamente."""
        preservation = "Conservar entre 2°C y 8°C"
        _create(api, creds, name="TEST GRADO", preservationData=preservation)
        row = db.product_detail(PLU_ENC)
        assert row is not None
        assert row["preservation_info"] == preservation

    def test_inverted_punctuation_in_name(self, api, creds):
        """¿ y ¡ en name son aceptados por la API."""
        r = _create(api, creds, name="¡Oferta! ¿Sabías?")
        assert r.get("ok") is True


# ── F3: Símbolos ASCII ────────────────────────────────────────────────────────

class TestAsciiSymbols:
    def test_symbols_in_name_ok(self, api, creds):
        """Símbolos & % / ( ) + - en name son aceptados."""
        r = _create(api, creds, name="Pan & Queso (100g) +IVA")
        assert r.get("ok") is True

    def test_symbols_in_name_stored(self, api, creds, db):
        """Símbolos en name se almacenan sin alteración."""
        name = "Prod & Co (v2)"
        _create(api, creds, name=name)
        row = db.product_detail(PLU_ENC)
        assert row is not None
        assert row["name"] == name

    def test_symbols_in_ingredients(self, api, creds, db):
        """Símbolos especiales en ingredients se almacenan correctamente."""
        ingr = "Leche 50%, agua, sal (NaCl), E-300"
        _create(api, creds, name="TEST SYM INGR", ingredients=ingr)
        row = db.product_detail(PLU_ENC)
        assert row is not None
        assert row["ingredients"] == ingr


# ── F4: Límite de 56 caracteres en name ──────────────────────────────────────

class TestNameFieldLimit:
    def test_name_56_chars_accepted(self, api, creds):
        """Name de exactamente 56 caracteres es aceptado."""
        name_56 = "A" * 56
        r = _create(api, creds, name=name_56)
        assert r.get("ok") is True

    def test_name_56_chars_stored_complete(self, api, creds, db):
        """Name de 56 caracteres se almacena completo en DB."""
        name_56 = "B" * 56
        _create(api, creds, name=name_56)
        row = db.product_detail(PLU_ENC)
        assert row is not None
        assert len(row["name"]) == 56

    def test_name_57_chars_rejected_or_truncated(self, api, creds, db):
        """Name de 57 caracteres es rechazado (400) o truncado a 56."""
        name_57 = "C" * 57
        r = requests.post(f"{api._base}/api/plu/create",
                          json={**creds, "plu": str(PLU_ENC), "name": name_57,
                                "saleType": "weight", "priceList1": 1.0},
                          timeout=5)
        if r.status_code == 400:
            return  # rechazado correctamente
        assert r.status_code in (200, 201), f"Status inesperado: {r.status_code}"
        row = db.product_detail(PLU_ENC)
        assert row is not None
        assert len(row["name"]) <= 56, "name no fue truncado a 56 caracteres"


# ── F6: Encoding de respuesta ─────────────────────────────────────────────────

class TestResponseEncoding:
    def test_response_content_type_is_json(self, api, creds):
        """Respuesta de create tiene Content-Type application/json."""
        r = requests.post(f"{api._base}/api/plu/create",
                          json={**creds, "plu": str(PLU_ENC), "name": "RESP ENC TEST",
                                "saleType": "weight", "priceList1": 1.0},
                          timeout=5)
        ct = r.headers.get("Content-Type", "")
        assert "application/json" in ct.lower()

    def test_response_uses_utf8_not_escapes(self, api, creds):
        """Respuesta JSON no usa secuencias \\uXXXX — retorna UTF-8 directo."""
        name_with_enye = "Ñoquis con salsa"
        r = requests.post(f"{api._base}/api/plu/create",
                          json={**creds, "plu": str(PLU_ENC), "name": name_with_enye,
                                "saleType": "weight", "priceList1": 1.0},
                          timeout=5)
        assert r.status_code in (200, 201)
        # Si la respuesta tiene ñ (ñ escapado), el API usa Unicode escapes
        raw_text = r.content.decode("utf-8")
        assert "\\u00f1" not in raw_text.lower(), (
            "API usó Unicode escape \\u00f1 en lugar de UTF-8 directo"
        )
