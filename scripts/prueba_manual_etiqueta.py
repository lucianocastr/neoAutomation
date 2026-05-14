"""
Prueba manual: impresión de etiqueta en modo etiqueta.

En modo etiqueta la balanza imprime directamente al pesar un producto
con PLU cargado. El flujo es:
  1. Seleccionar PLU (touchscreen o teclado → F3)
  2. Colocar producto en bandeja → esperar ESTABLE
  3. ENTER ×1 → imprime etiqueta inmediatamente

No genera invoice en BD (modo etiqueta no crea ticket).

Uso:
    python scripts/prueba_manual_etiqueta.py
    python scripts/prueba_manual_etiqueta.py --plu 57
    python scripts/prueba_manual_etiqueta.py --plu 57 --peso 200
"""

import sys
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv
import os

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env.test", override=False)

from tests.api_client import NEOApiClient
from tests.hid_client import HIDClient
from tests.db_client  import BalanzaDB
from tests.metrology  import build_profile
from tests.errors     import StabilizationError

import yaml

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


def show_products(db: BalanzaDB):
    products = db.active_products()
    print("\n  Productos disponibles:")
    for p in products[:15]:
        print(f"    PLU {p['id']:>4}  {p['name']:<30}  ${p['price']:.2f}/kg")
    if len(products) > 15:
        print(f"    ... y {len(products)-15} más")


def run_test(api: NEOApiClient, hid: HIDClient, db: BalanzaDB,
             profile, plu_id: int | None, peso_g: int | None) -> bool:

    errors = []

    # ── FASE 1: Estado inicial ───────────────────────────────────
    header("FASE 1 — Estado inicial")

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
    else:
        print("\n  ℹ️   Seleccioná cualquier PLU en la pantalla de la balanza.")
        price = None

    pause("Seleccioná el PLU en la balanza y luego presioná Enter aquí")

    # ── FASE 3: Colocar producto ─────────────────────────────────
    header(f"FASE 3 — Colocar producto{'  (~' + str(peso_g) + 'g)' if peso_g else ''}")

    peso_esperado = peso_g / 1000 if peso_g else None

    if peso_esperado:
        pause(f"Colocá ~{peso_g}g en la bandeja y presioná Enter")
        try:
            medido_kg = wait_stable(api, profile, peso_esperado, "peso_etiqueta")
        except StabilizationError as e:
            fail(str(e))
            medido_kg = api.get_weight(profile.unit_to_kg)
            info(f"Continuando con peso actual: {medido_kg*1000:.1f}g")
    else:
        pause("Colocá el producto en la bandeja y presioná Enter cuando la balanza diga ESTABLE")
        time.sleep(1)
        medido_kg = api.get_weight(profile.unit_to_kg)
        ok(f"Peso registrado: {medido_kg*1000:.1f}g")

    if medido_kg < profile.min_weighable_kg():
        fail(f"Peso {medido_kg*1000:.1f}g por debajo del mínimo pesable "
             f"({profile.min_weighable_kg()*1000:.0f}g) — la etiqueta podría no imprimirse")
        errors.append("peso_bajo_minimo")

    # ── FASE 4: Imprimir etiqueta ─────────────────────────────────
    header("FASE 4 — Imprimir etiqueta")

    info("ENTER — confirmando etiqueta...")
    hid.enter()
    time.sleep(2.0)
    ok("ENTER enviado")

    # Confirmación visual del operador
    print()
    print("  ¿Se imprimió la etiqueta?")
    print("    1) Sí — etiqueta impresa correctamente")
    print("    2) No — no salió etiqueta")
    print("    3) Parcial — salió pero con error (texto cortado, precio incorrecto, etc.)")
    while True:
        resp = input("      Respuesta [1/2/3]: ").strip()
        if resp in ("1", "2", "3"):
            break
        print("      Ingresá 1, 2 o 3")

    if resp == "1":
        ok("Etiqueta impresa")
    elif resp == "2":
        fail("No se imprimió etiqueta")
        errors.append("etiqueta_no_impresa")

        # Intentar con un segundo ENTER — algunos modos requieren confirmación extra
        print()
        print("  ℹ️   Probando con un segundo ENTER...")
        hid.enter()
        time.sleep(2.0)
        print("  ¿Ahora se imprimió?")
        print("    1) Sí   2) No")
        r2 = input("      [1/2]: ").strip()
        if r2 == "1":
            errors.remove("etiqueta_no_impresa")
            ok("Etiqueta impresa con segundo ENTER")
            info("NOTA: este PLU/modo requiere 2 ENTERs — actualizar flujo")
            errors.append("requiere_doble_enter")
        else:
            info("No respondió — posible problema con modo de impresión o PLU sin precio")
    else:
        fail("Etiqueta impresa con error")
        errors.append("etiqueta_con_error")

    # ── FASE 5: Verificar precio en etiqueta ─────────────────────
    if resp == "1" and price and medido_kg > 0:
        header("FASE 5 — Verificar precio")
        precio_esperado = price * medido_kg
        info(f"Precio esperado: ${price:.2f}/kg × {medido_kg*1000:.1f}g = ${precio_esperado:.2f}")
        print()
        print("  ¿El precio en la etiqueta coincide con el esperado?")
        print("    1) Sí   2) No")
        r3 = input("      [1/2]: ").strip()
        if r3 == "1":
            ok(f"Precio correcto: ${precio_esperado:.2f}")
        else:
            fail("Precio incorrecto en etiqueta")
            errors.append("precio_incorrecto")
    else:
        header("FASE 5 — omitida (sin PLU/precio o etiqueta no impresa)")

    # ── FASE 6: Limpiar bandeja ──────────────────────────────────
    header("FASE 6 — Limpiar")
    pause("Retirá el producto de la bandeja y presioná Enter")
    ok("Test completado")

    # ── Resumen ──────────────────────────────────────────────────
    header("RESUMEN")
    expected_warns = {"requiere_doble_enter"}
    hard_errors = [e for e in errors if e not in expected_warns]
    warns = [e for e in errors if e in expected_warns]

    if not hard_errors:
        ok("Test PASÓ — etiqueta impresa correctamente")
        if warns:
            info(f"Advertencias: {', '.join(warns)}")
    else:
        fail(f"Test FALLÓ — {len(hard_errors)} error(es): {', '.join(hard_errors)}")
    print(SEP + "\n")
    return len(hard_errors) == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plu",   type=int, default=None, help="PLU a imprimir (ej: 57)")
    parser.add_argument("--peso",  type=int, default=None, help="Gramos a colocar (referencia)")
    parser.add_argument("--ip",    default=NEO_IP,   help="IP balanza")
    parser.add_argument("--esp32", default=ESP32_IP, help="IP ESP32")
    args = parser.parse_args()

    cfg_path = Path(__file__).parent.parent / "config" / "hardware_params.yaml"
    with open(cfg_path) as f:
        raw_cfg = yaml.safe_load(f)
    profile = build_profile(PROFILE, raw_cfg["metrology"][PROFILE])

    api = NEOApiClient(f"http://{args.ip}:{NEO_PORT}", timeout_s=5)
    hid = HIDClient(host=args.esp32, port=ESP32_PORT)
    db  = BalanzaDB()

    print(f"\n{'═'*58}")
    print(f"  Prueba manual — Impresión de etiqueta")
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
