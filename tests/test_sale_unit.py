"""
Tests de venta automatizada — producto tipo unit (Suite G).

No requieren portal físico. Requieren:
  - Balanza en modo TICKET (no etiqueta)
  - ESP32 conectado (para ENTER vía HID)

El producto tipo unit tiene precio fijo — no necesita peso físico en la bandeja.
Flujo automatizado completo:
    api.load_plu(plu)  →  ENTER×3  →  invoice en BD

IMPORTANTE: en modo etiqueta los tests fallan (ENTER imprime etiqueta, no crea invoice).
Cambiar a modo ticket desde Menú → Configuración → Modo de venta antes de ejecutar.

Ejecutar:
    pytest tests/test_sale_unit.py -v -m esp32
"""

import time
import pytest

PLU_UNIT_SALE = 99960   # PLU reservado para tests de venta unit automatizada
PRICE_UNIT    = 150.0   # precio base Lista 1


# ── warmup ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def require_ticket_mode(db):
    """Falla con mensaje claro si la balanza está en modo etiqueta."""
    mode = db.get_print_mode()
    if mode != "ticket":
        pytest.skip(
            f"Balanza en modo '{mode}' — tests de venta requieren modo 'ticket'.\n"
            f"Cambiar desde Menú → Configuración → Tipo de papel → ticket."
        )


@pytest.fixture(scope="module", autouse=True)
def setup_plu(api, creds, require_ticket_mode):
    """Crea el PLU unit con precio fijo antes de cualquier test del módulo."""
    api.create_plu({
        **creds,
        "plu":       str(PLU_UNIT_SALE),
        "name":      "TEST VENTA AUTO",
        "saleType":  "unit",
        "priceList1": PRICE_UNIT,
    })


# ── helpers ───────────────────────────────────────────────────────────────────

def _select_plu(api, plu: int) -> None:
    """Carga el PLU en el display de la balanza vía API REST.
    Equivale a tipear el número en la balanza y confirmar con F3.
    Confirmado: api.get_product() retorna el nombre del PLU tras esta llamada."""
    api.load_plu(plu)


def _close_ticket(hid) -> None:
    """ENTER×3: agrega ítem al ticket → abre resumen → imprime y cierra."""
    hid.enter()
    hid.enter()
    hid.enter()


def _poll_new_invoice(db, count_before: int, timeout_s: int = 8):
    """Espera hasta que aparezca un invoice nuevo en BD o agota timeout.
    Devuelve latest_sale() si lo encontró, None si expiró."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if db.invoice_count() > count_before:
            return db.latest_sale()
        time.sleep(0.5)
    return None


# ── G1: Ciclo de venta completo ───────────────────────────────────────────────

@pytest.mark.esp32
class TestUnitSaleCycle:
    def test_sale_creates_new_invoice(self, api, hid, db):
        """Venta de producto unit genera exactamente un invoice nuevo en BD."""
        count_before = db.invoice_count()
        _select_plu(api, PLU_UNIT_SALE)
        _close_ticket(hid)
        sale = _poll_new_invoice(db, count_before)
        assert sale is not None, (
            f"No apareció invoice nuevo en 8 s (count_before={count_before})"
        )

    def test_sale_invoice_references_correct_plu(self, api, hid, db):
        """El invoice creado referencia el PLU vendido."""
        count_before = db.invoice_count()
        _select_plu(api, PLU_UNIT_SALE)
        _close_ticket(hid)
        sale = _poll_new_invoice(db, count_before)
        assert sale is not None, "No se creó invoice"
        assert sale["product_id"] == PLU_UNIT_SALE, (
            f"product_id={sale['product_id']}, esperado {PLU_UNIT_SALE}"
        )

    def test_sale_line_total_matches_price(self, api, hid, db):
        """El total del invoice coincide con el precio configurado en Lista 1."""
        count_before = db.invoice_count()
        _select_plu(api, PLU_UNIT_SALE)
        _close_ticket(hid)
        sale = _poll_new_invoice(db, count_before)
        assert sale is not None, "No se creó invoice"
        assert abs(sale["line_total"] - PRICE_UNIT) < 0.01, (
            f"line_total={sale['line_total']}, esperado {PRICE_UNIT}"
        )

    def test_sale_qty_is_one_unit(self, api, hid, db):
        """Producto unit registra qty=1 en la línea del invoice."""
        count_before = db.invoice_count()
        _select_plu(api, PLU_UNIT_SALE)
        _close_ticket(hid)
        sale = _poll_new_invoice(db, count_before)
        assert sale is not None, "No se creó invoice"
        assert abs(sale["qty_kg"] - 1.0) < 0.001, (
            f"qty_kg={sale['qty_kg']}, esperado 1.0 para producto unit"
        )

    def test_two_consecutive_sales_each_create_one_invoice(self, api, hid, db):
        """Dos ciclos ENTER×3 consecutivos crean exactamente dos invoices."""
        count_before = db.invoice_count()

        _select_plu(api, PLU_UNIT_SALE)
        _close_ticket(hid)
        _poll_new_invoice(db, count_before)          # espera el primero

        _select_plu(api, PLU_UNIT_SALE)
        _close_ticket(hid)
        _poll_new_invoice(db, count_before + 1)      # espera el segundo

        assert db.invoice_count() == count_before + 2, (
            f"Se esperaban {count_before + 2} invoices, "
            f"hay {db.invoice_count()}"
        )


# ── G2: Precio actualizado refleja en venta siguiente ────────────────────────

@pytest.mark.esp32
class TestPriceUpdateReflectedInSale:
    def test_updated_price_used_in_next_sale(self, api, hid, db, creds):
        """set_price actualiza el precio que aparece en el invoice siguiente."""
        new_price = 275.0
        api.set_price(PLU_UNIT_SALE, "Lista 1", new_price, **creds)

        count_before = db.invoice_count()
        _select_plu(api, PLU_UNIT_SALE)
        _close_ticket(hid)
        sale = _poll_new_invoice(db, count_before)

        # restaurar precio para no afectar otros tests del módulo
        api.set_price(PLU_UNIT_SALE, "Lista 1", PRICE_UNIT, **creds)

        assert sale is not None, "No se creó invoice"
        assert abs(sale["line_total"] - new_price) < 0.01, (
            f"line_total={sale['line_total']}, esperado {new_price} (precio actualizado)"
        )
