"""
Diagnostico: venta por digitos HID.

Hipotesis: api.load_plu() pre-carga datos pero NO pone la UI en estado
"ingresando PLU por teclado". El ENTER subsiguiente es ignorado.

Flujo A: digits + ENTER        (modo etiqueta directo)
Flujo B: digits + F3 + ENTER   (F3 = carga PLU, ENTER = confirma venta)

Prerequisitos:
  - Balanza en pantalla principal de venta
  - tipopapel=label, saveinvoice=1 (configurado desde UI)
  - ESP32 conectado y accesible
  - .env.test cargado

Ejecutar:
    python scripts/diag_sale_hid_digits.py [A|B]   (default: A)
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env.test")

from tests.hid_client import HIDClient
from tests.db_client import BalanzaDB

PLU = 99960

def poll_invoice(db, count_pre, timeout_s=15):
    deadline = time.monotonic() + timeout_s
    t0 = time.monotonic()
    while time.monotonic() < deadline:
        elapsed = round(time.monotonic() - t0)
        count = db.invoice_count()
        print(f"  t={elapsed}s count={count}", end="\r")
        if count > count_pre:
            return db.latest_sale()
        time.sleep(0.5)
    return None


def main():
    flujo = sys.argv[1].upper() if len(sys.argv) > 1 else "A"
    assert flujo in ("A", "B"), "Flujo debe ser A o B"

    hid = HIDClient(host=os.environ["NEO_ESP32_IP"], port=int(os.getenv("NEO_ESP32_PORT", "9999")))
    db  = BalanzaDB()

    mode      = db.get_print_mode()
    saves     = db.saves_invoices()
    count_pre = db.invoice_count()

    print(f"[config] flujo={flujo}, modo={mode}, saves_invoices={saves}")
    print(f"[antes]  invoice_count={count_pre}")

    if not saves:
        print("[SKIP] saves_invoices=False -- habilitar saveinvoice desde UI y reintentar")
        return

    # Paso 1: ESC para limpiar entrada parcial
    print("[1] ESC (limpiar entrada parcial)...")
    hid.send_key("ESC")
    time.sleep(0.4)

    # Paso 2: tipear PLU digito por digito
    plu_str = str(PLU)
    print(f"[2] tipeando PLU {plu_str} ({len(plu_str)} digitos, 200ms entre cada uno)...")
    for digit in plu_str:
        hid.send_key(digit)
        time.sleep(0.2)

    # Paso 3: flujo A o B
    if flujo == "A":
        print("[3A] ENTER directo...")
        hid.send_key("ENTER")
    else:
        print("[3B] F3 (cargar PLU)...")
        hid.send_key("F3")
        time.sleep(0.5)
        print("[3B] ENTER (confirmar venta)...")
        hid.send_key("ENTER")

    print("[OK] teclas enviadas, esperando invoice...")

    # Paso 4: polling
    sale = poll_invoice(db, count_pre, timeout_s=15)
    if sale:
        print("\n[OK] invoice creado!")
        print(f"     invoice_id  = {sale['invoice_id']}")
        print(f"     documentno  = {sale['documentno']}")
        print(f"     product     = {sale['product_name']} (id={sale['product_id']})")
        print(f"     qty_kg      = {sale['qty_kg']}")
        print(f"     line_total  = {sale['line_total']}")
    else:
        count_post = db.invoice_count()
        print(f"\n[TIMEOUT] count_pre={count_pre} count_post={count_post}")
        print("Observar fisicamente: la impresora imprimio etiqueta?")
        if count_pre == count_post:
            print("  NO -> la balanza no proceso el flujo HID")
        else:
            print("  SI pero count cambio? Revisar logica de polling")


if __name__ == "__main__":
    main()
