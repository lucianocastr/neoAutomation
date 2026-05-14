"""
Tests de venta automatizada — producto tipo unit (Suite G).

No requieren portal físico. Requieren ESP32 conectado.

Compatibles con ambos modos de la balanza:
  - tipopapel=ticket:              ENTER×3 → invoice en BD (siempre)
  - tipopapel=label/clabel:        ENTER×1 → invoice en BD (solo si saveinvoice=1)

El número de ENTERs se determina automáticamente en runtime según el modo activo.
Si saveinvoice=0 en modo etiqueta, los tests se saltan automáticamente.

Ejecutar:
    pytest tests/test_sale_unit.py -v -m esp32
"""

import time
import pytest

PLU_UNIT_SALE = 99960   # PLU reservado para tests de venta unit automatizada
PRICE_UNIT    = 150.0   # precio base Lista 1


# ── warmup ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def require_invoice_saving(db):
    """Skip si la configuración no persiste ventas en BD.
    Pasa cuando: tipopapel=ticket  (siempre)
              o: tipopapel=label/clabel + saveinvoice=1 (desde UI balanza)."""
    if not db.saves_invoices():
        pytest.skip(
            f"Modo '{db.get_print_mode()}' con saveinvoice=0 — ventas no se guardan en BD.\n"
            f"Opciones: cambiar a tipopapel=ticket, o activar Guardar Ventas desde la UI."
        )


@pytest.fixture(scope="module")
def enter_count(db) -> int:
    """ENTERs necesarios DESPUÉS de tipear los dígitos del PLU.
    label/clabel → 2  (ENTER 1: carga el PLU; ENTER 2: imprime etiqueta)
    ticket → 3        (ENTER 1: agrega al ticket; ENTER 2: resumen; ENTER 3: imprime)"""
    return 2 if db.get_print_mode() in ("label", "clabel") else 3


@pytest.fixture(autouse=True)
def inter_test_recovery():
    """15s antes de cada test:
    - La balanza vuelve a pantalla principal después de imprimir (~5s)
    - Los invoices tardíos del test anterior aparecen en BD (hasta ~12s post-ENTER)
    Garantiza que count_before no captura invoices del test anterior."""
    time.sleep(15)
    yield


@pytest.fixture(scope="module", autouse=True)
def setup_plu(api, creds, require_invoice_saving):
    """Crea el PLU unit con precio fijo antes de cualquier test del módulo."""
    api.create_plu({
        **creds,
        "plu":       str(PLU_UNIT_SALE),
        "name":      "TEST VENTA AUTO",
        "saleType":  "unit",
        "priceList1": PRICE_UNIT,
    })


# ── helpers ───────────────────────────────────────────────────────────────────

def _select_plu(hid, plu: int) -> None:
    """Tipea el PLU dígito a dígito vía HID como lo haría un usuario real.
    Delay 400ms entre dígitos: necesario para que la UI Java de la balanza
    procese cada keypress antes del siguiente.
    No usar api.load_plu(): precarga datos pero no pone la UI en estado
    de entrada de PLU, por lo que el ENTER subsiguiente es ignorado."""
    for digit in str(plu):
        hid.send_key(digit)
        time.sleep(0.4)


def _complete_sale(hid, n_enters: int) -> None:
    """Envía los ENTERs necesarios para cerrar la venta.
    1s entre ENTERs: la UI necesita procesar cada paso antes del siguiente."""
    for i in range(n_enters):
        hid.enter()
        if i < n_enters - 1:
            time.sleep(1.0)


def _poll_new_invoice(db, count_before: int, timeout_s: int = 25):
    """Espera hasta que aparezca un invoice nuevo en BD o agota timeout.
    Devuelve latest_sale() si lo encontró, None si expiró.
    25s: necesario porque la app Java puede tardar 10-15s en persistir
    el invoice después de recibir el ENTER final."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if db.invoice_count() > count_before:
            return db.latest_sale()
        time.sleep(0.5)
    return None


# ── G1: Ciclo de venta completo ───────────────────────────────────────────────

@pytest.mark.esp32
class TestUnitSaleCycle:
    def test_sale_creates_new_invoice(self, api, hid, db, enter_count):
        """Venta de producto unit genera exactamente un invoice nuevo en BD."""
        count_before = db.invoice_count()
        _select_plu(hid, PLU_UNIT_SALE)
        _complete_sale(hid, enter_count)
        sale = _poll_new_invoice(db, count_before)
        assert sale is not None, (
            f"No apareció invoice nuevo en 8 s (count_before={count_before}, "
            f"modo={db.get_print_mode()}, enters={enter_count})"
        )

    def test_sale_invoice_references_correct_plu(self, api, hid, db, enter_count):
        """El invoice creado referencia el PLU vendido."""
        count_before = db.invoice_count()
        _select_plu(hid, PLU_UNIT_SALE)
        _complete_sale(hid, enter_count)
        sale = _poll_new_invoice(db, count_before)
        assert sale is not None, "No se creó invoice"
        assert sale["product_id"] == PLU_UNIT_SALE, (
            f"product_id={sale['product_id']}, esperado {PLU_UNIT_SALE}"
        )

    def test_sale_line_total_matches_price(self, api, hid, db, enter_count):
        """El total del invoice coincide con el precio configurado en Lista 1."""
        count_before = db.invoice_count()
        _select_plu(hid, PLU_UNIT_SALE)
        _complete_sale(hid, enter_count)
        sale = _poll_new_invoice(db, count_before)
        assert sale is not None, "No se creó invoice"
        assert abs(sale["line_total"] - PRICE_UNIT) < 0.01, (
            f"line_total={sale['line_total']}, esperado {PRICE_UNIT}"
        )

    def test_sale_qty_is_one_unit(self, api, hid, db, enter_count):
        """Producto unit registra qty=1 en la línea del invoice."""
        count_before = db.invoice_count()
        _select_plu(hid, PLU_UNIT_SALE)
        _complete_sale(hid, enter_count)
        sale = _poll_new_invoice(db, count_before)
        assert sale is not None, "No se creó invoice"
        assert abs(sale["qty_kg"] - 1.0) < 0.001, (
            f"qty_kg={sale['qty_kg']}, esperado 1.0 para producto unit"
        )

    def test_two_consecutive_sales_each_create_one_invoice(self, api, hid, db, enter_count):
        """Dos ventas consecutivas crean exactamente dos invoices."""
        count_before = db.invoice_count()

        _select_plu(hid, PLU_UNIT_SALE)
        _complete_sale(hid, enter_count)
        _poll_new_invoice(db, count_before)

        _select_plu(hid, PLU_UNIT_SALE)
        _complete_sale(hid, enter_count)
        _poll_new_invoice(db, count_before + 1)

        assert db.invoice_count() == count_before + 2, (
            f"Se esperaban {count_before + 2} invoices, "
            f"hay {db.invoice_count()}"
        )


# ── G2: Precio actualizado refleja en venta siguiente ────────────────────────

@pytest.mark.esp32
class TestPriceUpdateReflectedInSale:
    def test_updated_price_used_in_next_sale(self, api, hid, db, creds, enter_count):
        """set_price actualiza el precio que aparece en el invoice siguiente."""
        new_price = 275.0
        api.set_price(PLU_UNIT_SALE, "Lista 1", new_price, **creds)

        count_before = db.invoice_count()
        _select_plu(hid, PLU_UNIT_SALE)
        _complete_sale(hid, enter_count)
        sale = _poll_new_invoice(db, count_before)

        # restaurar precio para no afectar otros tests del módulo
        api.set_price(PLU_UNIT_SALE, "Lista 1", PRICE_UNIT, **creds)

        assert sale is not None, "No se creó invoice"
        assert abs(sale["line_total"] - new_price) < 0.01, (
            f"line_total={sale['line_total']}, esperado {new_price} (precio actualizado)"
        )
