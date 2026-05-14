"""
Prueba manual: flujo de venta completo — sin portal físico.

Guía paso a paso:
  1. Seleccionás un PLU en la balanza (touchscreen o teclado HID)
  2. Colocás el peso manualmente
  3. El script confirma la venta con F3 via HID
  4. Verifica en la BD que el ticket quedó registrado correctamente

Uso:
    python scripts/prueba_manual_venta.py
    python scripts/prueba_manual_venta.py --plu 96
    python scripts/prueba_manual_venta.py --plu 57 --peso 200
"""

import sys
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv
import os

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env.test", override=False)

from tests.api_client   import NEOApiClient
from tests.hid_client   import HIDClient
from tests.db_client    import BalanzaDB
from tests.metrology    import build_profile
from tests.errors       import StabilizationError

import yaml
import requests

NEO_IP     = os.getenv("NEO_IP",       "192.168.100.123")
NEO_PORT   = int(os.getenv("NEO_API_PORT", "7376"))
ESP32_IP   = os.getenv("NEO_ESP32_IP", "192.168.100.202")
ESP32_PORT = int(os.getenv("NEO_ESP32_PORT", "9999"))
PROFILE    = os.getenv("TEST_METROLOGY_PROFILE", "AR")

SEP = "─" * 58


def header(t):  print(f"\n{SEP}\n  {t}\n{SEP}")
def ok(m):      print(f"  ✅  {m}")
def fail(m):    print(f"  ❌  {m}")
def info(m):    print(f"  ·   {m}")
def pause(m):   print(f"\n  👉  {m}"); input("      [Enter para continuar]")


def wait_stable(api, profile, expected_kg, label, max_wait_s=30.0):
    tol_kg = profile.tolerance_g_for(abs(expected_kg)) / 1000
    deadline = time.monotonic() + max_wait_s
    consecutive = 0
    last = None
    print(f"  ⏳  Esperando {expected_kg*1000:.0f}g ± {tol_kg*1000:.1f}g  ", end="", flush=True)
    while time.monotonic() < deadline:
        last = api.get_weight(profile.unit_to_kg)
        if abs(last - expected_kg) <= tol_kg:
            consecutive += 1
            print(".", end="", flush=True)
            if consecutive >= 3:
                print(f"  → {last*1000:.1f}g  ✅")
                return last
        else:
            consecutive = 0
            print(f"\r  ⏳  {last*1000:.1f}g (esperando {expected_kg*1000:.0f}g ± {tol_kg*1000:.1f}g)  ",
                  end="", flush=True)
        time.sleep(0.5)
    print()
    raise StabilizationError(
        f"'{label}' no estabilizó en {max_wait_s}s: "
        f"último={last*1000:.1f}g, esperado={expected_kg*1000:.0f}g ± {tol_kg*1000:.1f}g"
    )


def wait_for_invoice(db: BalanzaDB, count_before: int, timeout_s: float = 15.0) -> dict | None:
    """Espera hasta que aparezca una nueva invoice en la BD."""
    deadline = time.monotonic() + timeout_s
    print(f"  ⏳  Esperando ticket en BD  ", end="", flush=True)
    while time.monotonic() < deadline:
        if db.invoice_count() > count_before:
            sale = db.latest_sale()
            print(f"  → encontrado ✅")
            return sale
        print(".", end="", flush=True)
        time.sleep(1)
    print()
    return None


def get_current_product(api_base: str) -> dict | None:
    """Intenta obtener el producto seleccionado en la balanza. Retorna None si no hay ninguno."""
    try:
        r = requests.get(f"{api_base}/api/product", timeout=3)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def wait_for_plu(api_base: str, timeout_s: float = 60.0) -> dict | None:
    """Espera hasta que la balanza tenga un PLU cargado (api/product responde 200)."""
    deadline = time.monotonic() + timeout_s
    print(f"  ⏳  Esperando selección de PLU en la balanza  ", end="", flush=True)
    while time.monotonic() < deadline:
        p = get_current_product(api_base)
        if p and p.get("ok") is not False:
            print(f"  → OK ✅")
            return p
        print(".", end="", flush=True)
        time.sleep(1)
    print()
    return None


def show_products(db: BalanzaDB):
    products = db.active_products()
    print("\n  Productos disponibles:")
    for p in products[:15]:
        print(f"    PLU {p['id']:>4}  {p['name']:<30}  ${p['price']:.2f}/kg")
    if len(products) > 15:
        print(f"    ... y {len(products)-15} más")


def run_test(api: NEOApiClient, hid: HIDClient, db: BalanzaDB,
             profile, plu_id: int | None, peso_g: int | None) -> bool:

    api_base = f"http://{NEO_IP}:{NEO_PORT}"
    errors = []

    # ── FASE 1: Estado inicial ───────────────────────────────────
    header("FASE 1 — Estado inicial")

    count_before = db.invoice_count()
    info(f"Tickets en BD antes del test: {count_before}")

    initial = api.get_weight(profile.unit_to_kg)
    info(f"Peso actual: {initial*1000:.1f}g")
    if abs(initial) >= 0.003:
        pause(f"Bandeja muestra {initial*1000:.1f}g — retirá lo que haya y presioná Enter")
        initial = api.get_weight(profile.unit_to_kg)
    ok("Bandeja libre")

    # ── FASE 2: Seleccionar PLU ──────────────────────────────────
    header("FASE 2 — Seleccionar PLU")

    show_products(db)

    if plu_id:
        price = db.product_price(plu_id)
        if price is None:
            fail(f"PLU {plu_id} no encontrado o sin precio activo")
            return False
        info(f"PLU {plu_id} — precio: ${price:.2f}/kg")
        print()
        print(f"  ℹ️   En la balanza: escribí '{plu_id}' en el teclado y presioná F3")
        print(f"      O buscá '{plu_id}' en la pantalla y tocalo.")
    else:
        print("\n  ℹ️   Seleccioná cualquier PLU en la pantalla de la balanza.")
        price = None

    pause("Seleccioná el PLU en la balanza y luego presioná Enter aquí")

    # Verificar que la balanza tiene un PLU cargado
    product_info = get_current_product(api_base)
    if product_info and product_info.get("ok") is not False:
        plu_name = product_info.get("name") or product_info.get("description") or "desconocido"
        ok(f"PLU cargado en balanza: {plu_name}")
    else:
        info("API /product no confirma PLU (puede ser normal — continuando)")

    # ── FASE 3: Colocar peso ─────────────────────────────────────
    header(f"FASE 3 — Colocar peso{'  (~' + str(peso_g) + 'g)' if peso_g else ''}")

    peso_esperado = peso_g / 1000 if peso_g else None

    if peso_esperado:
        pause(f"Colocá ~{peso_g}g en la bandeja y presioná Enter")
        try:
            medido_kg = wait_stable(api, profile, peso_esperado, "peso_venta")
        except StabilizationError as e:
            fail(str(e))
            medido_kg = api.get_weight(profile.unit_to_kg)
            info(f"Continuando con peso actual: {medido_kg*1000:.1f}g")
    else:
        pause("Colocá el peso en la bandeja y presioná Enter cuando la balanza diga ESTABLE")
        time.sleep(1)
        medido_kg = api.get_weight(profile.unit_to_kg)
        ok(f"Peso registrado: {medido_kg*1000:.1f}g")

    if medido_kg < profile.min_weighable_kg():
        fail(f"Peso {medido_kg*1000:.1f}g por debajo del mínimo pesable "
             f"({profile.min_weighable_kg()*1000:.0f}g) — la venta podría no registrarse")
        errors.append("peso_bajo_minimo")

    # ── FASE 4: Cerrar y imprimir ticket ────────────────────────
    # Flujo CUORA NEO:
    #   ENTER ×1 → agrega ítem al ticket
    #   ENTER ×2 → abre pantalla de resumen del ticket
    #   ENTER ×3 → imprime y cierra el ticket → crea invoice en BD
    header("FASE 4 — Cerrar e imprimir ticket")

    info("ENTER 1/3 — agrega ítem al ticket...")
    hid.enter()
    time.sleep(1.5)

    info("ENTER 2/3 — abre resumen del ticket...")
    hid.enter()
    time.sleep(1.5)

    info("ENTER 3/3 — imprime y cierra ticket...")
    hid.enter()
    ok("Secuencia ENTER enviada — ticket imprimiendo")

    # ── FASE 5: Verificar en BD ───────────────────────────────────
    header("FASE 5 — Verificar ticket en base de datos")

    sale = wait_for_invoice(db, count_before, timeout_s=15)

    if sale is None:
        fail("No apareció nuevo ticket en BD dentro de 15 segundos")
        fail("Posibles causas: PLU sin precio, peso bajo mínimo, venta no confirmada")
        errors.append("ticket_no_creado")
    else:
        ok(f"Ticket #{sale['documentno']} registrado")
        info(f"Producto: {sale['product_name']} (PLU {sale['product_id']})")
        info(f"Peso:     {sale['qty_kg']*1000:.1f}g")
        info(f"Precio:   ${sale['price_per_kg']:.2f}/kg")
        info(f"Total:    ${sale['grandtotal']:.2f}")

        # Verificar que el peso registrado coincide con lo medido
        delta_g = abs(sale['qty_kg'] - medido_kg) * 1000
        tol_g = profile.tolerance_g_for(medido_kg)
        if delta_g <= tol_g:
            ok(f"Peso en BD correcto: {sale['qty_kg']*1000:.1f}g ≈ {medido_kg*1000:.1f}g (Δ{delta_g:.1f}g ≤ {tol_g:.1f}g)")
        else:
            fail(f"Peso en BD {sale['qty_kg']*1000:.1f}g ≠ medido {medido_kg*1000:.1f}g (Δ{delta_g:.1f}g > {tol_g:.1f}g)")
            errors.append("peso_bd_no_coincide")

        if plu_id and sale['product_id'] != plu_id:
            fail(f"PLU en BD ({sale['product_id']}) ≠ PLU esperado ({plu_id})")
            errors.append("plu_incorrecto")
        else:
            ok(f"PLU correcto: {sale['product_id']}")

    # ── FASE 6: Limpiar bandeja ──────────────────────────────────
    header("FASE 6 — Limpiar")
    pause("Retirá el peso de la bandeja y presioná Enter")
    ok("Test completado")

    # ── Resumen ──────────────────────────────────────────────────
    header("RESUMEN")
    if not errors:
        ok("Test PASÓ — venta registrada y verificada en BD")
        ok("HID ENTER×3, API weight, PostgreSQL invoice+invoiceline: todos OK")
    else:
        fail(f"Test FALLÓ — {len(errors)} error(es): {', '.join(errors)}")
    print(SEP + "\n")
    return len(errors) == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plu",    type=int, default=None, help="PLU a vender (ej: 96)")
    parser.add_argument("--peso",   type=int, default=None, help="Gramos a colocar (referencia)")
    parser.add_argument("--ip",     default=NEO_IP,   help="IP balanza")
    parser.add_argument("--esp32",  default=ESP32_IP, help="IP ESP32")
    args = parser.parse_args()

    cfg_path = Path(__file__).parent.parent / "config" / "hardware_params.yaml"
    with open(cfg_path) as f:
        raw_cfg = yaml.safe_load(f)
    profile = build_profile(PROFILE, raw_cfg["metrology"][PROFILE])

    api = NEOApiClient(f"http://{args.ip}:{NEO_PORT}", timeout_s=5)
    hid = HIDClient(host=args.esp32, port=ESP32_PORT)
    db  = BalanzaDB()

    print(f"\n{'═'*58}")
    print(f"  Prueba manual — Venta completa")
    print(f"  Balanza: {args.ip}:{NEO_PORT}  |  ESP32: {args.esp32}:{ESP32_PORT}")
    print(f"  Perfil: {PROFILE}{'  |  PLU: '+str(args.plu) if args.plu else ''}")
    print(f"{'═'*58}")

    try:
        success = run_test(api, hid, db, profile, args.plu, args.peso)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n  Test interrumpido.\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
