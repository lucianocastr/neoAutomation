"""
Tests de integridad API ↔ PostgreSQL (Suite Integrity).

Verifica que los valores enviados via API REST queden almacenados
exactamente como se esperan en la base de datos PostgreSQL.

No requieren portal físico ni ESP32. Solo la balanza encendida y en red.

Ejecutar:
    pytest tests/test_integrity.py -v

Mapeo de campos documentado (API → DB):
  name            → product.name
  saleType=weight → product.uom_id = '1'
  saleType=unit   → product.uom_id = '2'
  originData      → product.extra_field2
  preservationData→ product.preservation_info
  ingredients     → product.ingredients
  extraField1     → product.extra_field1
  eanDescription  → product.upc
  active          → product.isactive (normalizado a Y/N)
  advertising.name → advertising.name
  advertising.text → advertising.advertising
"""

import pytest

PLU_WEIGHT = 99980   # PLU tipo weight para tests de integridad
PLU_UNIT   = 99979   # PLU tipo unit (separado para no pisar saleType)
ADV_INTEG  = "TEST_INTEGRITY_99980"


# ── warmup ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def warmup(api, creds):
    try:
        api.create_plu({**creds, "plu": str(PLU_WEIGHT), "name": "INTEG WARMUP",
                        "saleType": "weight", "priceList1": 1.0})
    except Exception:
        pass


# ── helpers ───────────────────────────────────────────────────────────────────

def _create_weight(api, creds, **kwargs):
    payload = {**creds, "plu": str(PLU_WEIGHT), "saleType": "weight",
               "priceList1": 1.0, **kwargs}
    return api.create_plu(payload)


# ── Phase 1: Mapeo de campos básicos ─────────────────────────────────────────

class TestFieldMapping:
    def test_name_stored(self, api, creds, db):
        """name se almacena en product.name."""
        name = "INTEG NAME TEST"
        _create_weight(api, creds, name=name)
        row = db.product_detail(PLU_WEIGHT)
        assert row is not None
        assert row["name"] == name

    def test_origin_data_maps_to_extra_field2(self, api, creds, db):
        """originData se almacena en product.extra_field2."""
        origin = "Producto de origen argentino"
        _create_weight(api, creds, name="INTEG ORIGIN", originData=origin)
        row = db.product_detail(PLU_WEIGHT)
        assert row is not None
        assert row["extra_field2"] == origin

    def test_preservation_data_maps(self, api, creds, db):
        """preservationData se almacena en product.preservation_info."""
        preservation = "Mantener refrigerado 2-8C"
        _create_weight(api, creds, name="INTEG PRESERV", preservationData=preservation)
        row = db.product_detail(PLU_WEIGHT)
        assert row is not None
        assert row["preservation_info"] == preservation

    def test_ingredients_stored(self, api, creds, db):
        """ingredients se almacena en product.ingredients."""
        ingr = "Harina de trigo, agua, sal"
        _create_weight(api, creds, name="INTEG INGR", ingredients=ingr)
        row = db.product_detail(PLU_WEIGHT)
        assert row is not None
        assert row["ingredients"] == ingr

    def test_extra_field1_stored(self, api, creds, db):
        """extraField1 se almacena en product.extra_field1."""
        extra = "Campo extra de prueba"
        _create_weight(api, creds, name="INTEG EXTRA1", extraField1=extra)
        row = db.product_detail(PLU_WEIGHT)
        assert row is not None
        assert row["extra_field1"] == extra

    def test_ean_description_accepted_by_api(self, api, creds):
        """eanDescription es aceptado por la API sin error.
        Nota: en este firmware product.upc queda vacío — mapeo de columna distinto al NEO2."""
        r = _create_weight(api, creds, name="INTEG EAN", eanDescription="7790001234567")
        assert r.get("ok") is True


# ── Phase 1b: Mapeo de uom_id (tipo de venta) ────────────────────────────────

class TestSaleTypeMapping:
    def test_weight_maps_to_uom_id_1(self, api, creds, db):
        """saleType=weight → product.uom_id = '1'."""
        _create_weight(api, creds, name="INTEG WEIGHT UOM")
        row = db.product_detail(PLU_WEIGHT)
        assert row is not None
        assert row["uom_id"] == "1", f"uom_id esperado '1', recibido '{row['uom_id']}'"

    def test_unit_maps_to_uom_id_2(self, api, creds, db):
        """saleType=unit → product.uom_id = '2'."""
        api.create_plu({**creds, "plu": str(PLU_UNIT), "name": "INTEG UNIT UOM",
                        "saleType": "unit", "priceList1": 500.0})
        row = db.product_detail(PLU_UNIT)
        assert row is not None
        assert row["uom_id"] == "2", f"uom_id esperado '2', recibido '{row['uom_id']}'"


# ── Phase 3: Normalización de campo active ───────────────────────────────────

class TestActiveNormalization:
    @pytest.mark.parametrize("active_val,expected", [
        ("Y",     "Y"),
        ("true",  "Y"),
        ("1",     "Y"),
        ("N",     "N"),
        ("false", "N"),
    ])
    def test_active_normalized(self, api, creds, db, active_val, expected):
        """active={active_val} se normaliza a isactive={expected} en DB."""
        _create_weight(api, creds, name=f"INTEG ACTIVE {active_val}", active=active_val)
        row = db.product_detail(PLU_WEIGHT)
        assert row is not None
        assert row["isactive"] == expected, (
            f"active='{active_val}' → isactive='{row['isactive']}', esperado '{expected}'"
        )


# ── Phase 2: Precios en productprice ─────────────────────────────────────────
# Columna real: productprice.pricelist (no pricestd); pricelist_version_id='lst1' para Lista 1.

class TestPriceMapping:
    def test_price_list1_stored_in_db(self, api, creds, db):
        """priceList1 enviado en create queda registrado en productprice."""
        price = 1234.56
        _create_weight(api, creds, name="INTEG PRICE1", priceList1=price)
        stored = db.product_price(PLU_WEIGHT)
        assert stored is not None
        assert abs(stored - price) < 0.01, (
            f"Precio guardado {stored} ≠ enviado {price}"
        )

    def test_price_via_set_price_stored(self, api, creds, db):
        """set_price actualiza el valor en productprice."""
        price = 999.99
        _create_weight(api, creds, name="INTEG PRICE SET", priceList1=1.0)
        api.set_price(PLU_WEIGHT, "Lista 1", price, **creds)
        stored = db.product_price(PLU_WEIGHT)
        assert stored is not None
        assert abs(stored - price) < 0.01, (
            f"Precio guardado {stored} ≠ enviado {price}"
        )

    def test_price_comma_decimal_stored_correctly(self, api, creds, db):
        """Precio con coma decimal ('750,50') se almacena como 750.50."""
        _create_weight(api, creds, name="INTEG PRICE COMMA", priceList1=1.0)
        api.set_price(PLU_WEIGHT, "Lista 1", "750,50", **creds)
        stored = db.product_price(PLU_WEIGHT)
        assert stored is not None
        assert abs(stored - 750.50) < 0.01, (
            f"Precio guardado {stored} ≠ 750.50"
        )


# ── Phase 5: Advertising ─────────────────────────────────────────────────────

class TestAdvertisingMapping:
    def test_advertising_name_stored(self, api, creds, db):
        """advertising.name se almacena en advertising.name en DB."""
        api.create_advertising({**creds, "name": ADV_INTEG,
                                "text": "Texto de prueba integridad"})
        row = db.advertising_detail(ADV_INTEG)
        assert row is not None
        assert row["name"] == ADV_INTEG

    def test_advertising_text_stored(self, api, creds, db):
        """advertising.text se almacena en advertising.advertising en DB."""
        text = "Oferta especial valida hasta el fin de semana"
        api.create_advertising({**creds, "name": ADV_INTEG, "text": text})
        row = db.advertising_detail(ADV_INTEG)
        assert row is not None
        assert row["text"] == text

    def test_advertising_active_y_stored(self, api, creds, db):
        """advertising con active=Y se almacena con isactive=Y."""
        api.create_advertising({**creds, "name": ADV_INTEG,
                                "text": "test activo", "active": "Y"})
        row = db.advertising_detail(ADV_INTEG)
        assert row is not None
        assert row["isactive"] == "Y"

    def test_advertising_upsert_updates_text(self, api, creds, db):
        """Segunda llamada con mismo name actualiza el texto (upsert)."""
        api.create_advertising({**creds, "name": ADV_INTEG, "text": "primer texto"})
        api.create_advertising({**creds, "name": ADV_INTEG, "text": "segundo texto"})
        row = db.advertising_detail(ADV_INTEG)
        assert row is not None
        assert row["text"] == "segundo texto"
