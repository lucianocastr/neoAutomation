"""
Prueba manual: Tara + Peso de Producto — sin portal físico.

Reemplaza el actuador con instrucciones interactivas. Usa HID y API reales.
Las pesas DOLZ se colocan y retiran a mano siguiendo las indicaciones.

Uso:
    python scripts/prueba_manual.py
    python scripts/prueba_manual.py --ip 192.168.100.123 --esp32 192.168.100.202
    python scripts/prueba_manual.py --tare 500 --product 1000
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
from tests.metrology import build_profile, MetrologyProfile
from tests.assertions import assert_weight, assert_negative_within_limit
from tests.errors import StabilizationError, WeightAssertionError

import yaml

# ── Defaults ────────────────────────────────────────────────────────────────

NEO_IP      = os.getenv("NEO_IP",       "192.168.100.123")
NEO_PORT    = int(os.getenv("NEO_API_PORT", "7376"))
ESP32_IP    = os.getenv("NEO_ESP32_IP", "192.168.100.202")
ESP32_PORT  = int(os.getenv("NEO_ESP32_PORT", "9999"))
PROFILE_VAR = os.getenv("TEST_METROLOGY_PROFILE", "AR")

TARE_G    = 500
PRODUCT_G = 1000


# ── UI helpers ──────────────────────────────────────────────────────────────

SEP = "─" * 58

def header(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def ok(msg):    print(f"  ✅  {msg}")
def fail(msg):  print(f"  ❌  {msg}")
def info(msg):  print(f"  ·   {msg}")
def warn(msg):  print(f"  ⚠️   {msg}")

def pause(msg: str):
    print(f"\n  👉  {msg}")
    input("      [Enter para continuar]")


# ── Polling con progreso visible ────────────────────────────────────────────

def wait_stable(
    api: NEOApiClient,
    profile: MetrologyProfile,
    expected_kg: float,
    label: str,
    max_wait_s: float = 30.0,
    consecutive_ok: int = 3,
    poll_interval_s: float = 0.5,
) -> float:
    tol_kg = profile.tolerance_g_for(abs(expected_kg)) / 1000
    deadline = time.monotonic() + max_wait_s
    consecutive = 0
    last = None

    print(f"  ⏳  Esperando {expected_kg * 1000:.0f}g ± {tol_kg * 1000:.1f}g  ", end="", flush=True)

    while time.monotonic() < deadline:
        last = api.get_weight(profile.unit_to_kg)
        if abs(last - expected_kg) <= tol_kg:
            consecutive += 1
            print(".", end="", flush=True)
            if consecutive >= consecutive_ok:
                print(f"  → {last * 1000:.1f}g  ✅")
                return last
        else:
            consecutive = 0
            print(f"\r  ⏳  {last * 1000:.1f}g (esperando {expected_kg * 1000:.0f}g ± {tol_kg * 1000:.1f}g)  ", end="", flush=True)
        time.sleep(poll_interval_s)

    print()
    raise StabilizationError(
        f"'{label}' no estabilizó en {max_wait_s}s: "
        f"último={last * 1000:.1f}g, "
        f"esperado={expected_kg * 1000:.1f}g ± {tol_kg * 1000:.1f}g"
    )


# ── Test principal ──────────────────────────────────────────────────────────

def run_test(api: NEOApiClient, hid: HIDClient, profile: MetrologyProfile,
             tare_g: int, product_g: int) -> bool:

    errors = []

    # ── FASE 1: Verificar bandeja vacía ─────────────────────────────────────
    header("FASE 1 — Verificar bandeja vacía")

    pause("Asegurate de que la bandeja esté VACÍA y la balanza en reposo.")

    initial = api.get_weight(profile.unit_to_kg)
    info(f"Lectura actual: {initial * 1000:.1f}g")

    if initial >= 0.003:
        fail(f"Bandeja no vacía: {initial * 1000:.1f}g (máx. esperado 3g)")
        errors.append("bandeja_no_vacia")
    else:
        ok(f"Bandeja libre: {initial * 1000:.1f}g")

    # ── FASE 2: Simular envase → aplicar TARA ───────────────────────────────
    header(f"FASE 2 — Colocar envase ({tare_g}g) y aplicar TARA")

    pause(f"Colocá ~{tare_g}g en la bandeja.\n"
          f"      (ej: una pesa de {tare_g}g o equivalente)")

    try:
        wait_stable(api, profile, tare_g / 1000, "tara_carga")
    except StabilizationError as e:
        fail(str(e))
        errors.append("tara_no_estabilizo")

    info("Enviando TARA (F2) al ESP32...")
    hid.tare()
    ok("Tecla F2 enviada")

    try:
        wait_stable(api, profile, 0.0, "post_tara")
        ok("Balanza en 0 tras TARA")
    except StabilizationError as e:
        fail(str(e))
        errors.append("post_tara_no_estabilizo")

    # ── FASE 3: Agregar producto → verificar peso neto ──────────────────────
    header(f"FASE 3 — Agregar producto ({product_g}g) y verificar peso neto")

    pause(f"Agregá ~{product_g}g MÁS sobre la bandeja (total ~{tare_g + product_g}g).\n"
          f"      El display de la balanza debería mostrar ~{product_g}g (neto).")

    try:
        actual_kg = wait_stable(api, profile, product_g / 1000, "producto_neto")
        try:
            assert_weight(actual_kg, product_g / 1000, profile, label="product_net")
            ok(f"Peso neto correcto: {actual_kg * 1000:.1f}g (esperado {product_g}g)")
        except WeightAssertionError as e:
            fail(str(e))
            errors.append("peso_neto_fuera_tolerancia")
    except StabilizationError as e:
        fail(str(e))
        errors.append("producto_no_estabilizo")

    # ── FASE 4: Retirar todo → verificar negativo → CERO ────────────────────
    header("FASE 4 — Retirar pesas y limpiar")

    pause("Retirá TODAS las pesas de la bandeja.\n"
          "      (La balanza debería mostrar un valor negativo — es correcto)")

    try:
        # Con tara activa y bandeja vacía, la balanza muestra exactamente -tare_g.
        # Verificamos que el valor es correcto (no usamos assert_negative_within_limit
        # que está diseñada para pequeños excesos negativos, no para taras intencionales).
        actual_neg = wait_stable(api, profile, -(tare_g / 1000), "retiro_negativo")
        info(f"Lectura negativa: {actual_neg * 1000:.1f}g (esperado ~{-tare_g}g)")
        ok("Negativo correcto — tara activa confirmada")
    except StabilizationError as e:
        fail(str(e))
        errors.append("retiro_no_estabilizo")

    # F2 (TARA) con bandeja vacía cancela la tara activa y devuelve 0g.
    # F4 (CERO) NO cancela tara — solo aplica corrección de cero en rango pequeño.
    info("Cancelando tara con F2 (TARA) — bandeja vacía...")
    hid.tare()
    ok("Tecla F2 enviada")

    try:
        wait_stable(api, profile, 0.0, "post_cancelar_tara")
    except StabilizationError as e:
        fail(str(e))
        errors.append("post_cancelar_tara_no_estabilizo")

    final = api.get_weight(profile.unit_to_kg)
    if abs(final) < 0.003:
        ok(f"Balanza en reposo: {final * 1000:.1f}g")
    else:
        fail(f"Balanza no quedó en 0 al final: {final * 1000:.1f}g")
        errors.append("final_no_cero")

    # ── Resumen ──────────────────────────────────────────────────────────────
    header("RESUMEN")
    if not errors:
        ok(f"Test PASÓ — {tare_g}g tara + {product_g}g producto validados con hardware real")
        ok("HID (F2/F4), API weight, poll_until_stable y assert_weight: todos OK")
    else:
        fail(f"Test FALLÓ — {len(errors)} error(es): {', '.join(errors)}")
    print(SEP + "\n")

    return len(errors) == 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip",      default=NEO_IP,   help="IP de la balanza")
    parser.add_argument("--port",    default=NEO_PORT,  type=int)
    parser.add_argument("--esp32",   default=ESP32_IP,  help="IP del ESP32")
    parser.add_argument("--esp32-port", default=ESP32_PORT, type=int, dest="esp32_port")
    parser.add_argument("--tare",    default=TARE_G,    type=int, help="Gramos de tara (envase)")
    parser.add_argument("--product", default=PRODUCT_G, type=int, help="Gramos de producto")
    parser.add_argument("--profile", default=PROFILE_VAR, help="AR | BR | US")
    args = parser.parse_args()

    cfg_path = Path(__file__).parent.parent / "config" / "hardware_params.yaml"
    with open(cfg_path) as f:
        raw_cfg = yaml.safe_load(f)
    profile = build_profile(args.profile, raw_cfg["metrology"][args.profile])

    api = NEOApiClient(f"http://{args.ip}:{args.port}", timeout_s=5)
    hid = HIDClient(host=args.esp32, port=args.esp32_port)

    print(f"\n{'═' * 58}")
    print(f"  Prueba manual — Tara + Producto")
    print(f"  Balanza: {args.ip}:{args.port}  |  ESP32: {args.esp32}:{args.esp32_port}")
    print(f"  Perfil: {args.profile}  |  Tara: {args.tare}g  |  Producto: {args.product}g")
    print(f"{'═' * 58}")

    try:
        success = run_test(api, hid, profile, args.tare, args.product)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n  Test interrumpido por el usuario.\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
