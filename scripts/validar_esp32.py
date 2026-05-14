"""
Validación rápida del firmware ESP32 unificado (firmware/esp32/).

Ejecutar DESPUÉS de flashear firmware/esp32/ al ESP32-S3.
No requiere motor ni portal — solo ESP32 conectado a la balanza por USB.

Uso:
    python scripts/validar_esp32.py
    python scripts/validar_esp32.py --ip 192.168.100.202
"""

import sys
import argparse
import time
sys.path.insert(0, __file__.replace("\\scripts\\validar_esp32.py", "")
                             .replace("/scripts/validar_esp32.py", ""))

from tests.actuator_client import ActuatorClient
from tests.hid_client import HIDClient
from tests.errors import ActuatorError

ESP32_IP   = "192.168.100.202"
ESP32_PORT = 9999


def ok(msg):  print(f"  ✅  {msg}")
def fail(msg): print(f"  ❌  {msg}"); return False


def test_status(actuator: ActuatorClient) -> bool:
    print("\n[1] STATUS — conectividad TCP + estado del firmware")
    try:
        resp = actuator.status()
        ok(f"Respuesta: {resp}")
        if resp.get("hid") == "ready":
            ok("Campo 'hid':'ready' presente — firmware unificado confirmado")
        else:
            return fail("Campo 'hid' ausente — puede ser el firmware HID viejo")
        if resp.get("state") == "IDLE":
            ok("Estado: IDLE")
        return True
    except ActuatorError as e:
        return fail(f"No conecta: {e}")


def test_hid_status(hid: HIDClient) -> bool:
    print("\n[2] HID STATUS — verifica que el servidor HID responde")
    try:
        resp = hid.status()
        ok(f"Respuesta: {resp}")
        return True
    except ActuatorError as e:
        return fail(f"Error HID: {e}")


def test_key_press(hid: HIDClient) -> bool:
    print("\n[3] KEY_PRESS F4 (CERO) — verifica HID hacia la balanza")
    print("     ⚠️  Observar la pantalla de la balanza — debe ejecutar CERO")
    try:
        hid.zero()   # F4
        ok("Comando enviado sin error")
        print("     ¿La balanza ejecutó CERO? (revisar pantalla)")
        return True
    except ActuatorError as e:
        return fail(f"Error KEY_PRESS: {e}")


def test_key_press_tare(hid: HIDClient) -> bool:
    print("\n[4] KEY_PRESS F2 (TARA) — segunda tecla de validación")
    print("     ⚠️  Observar la pantalla de la balanza — debe aplicar TARA")
    try:
        time.sleep(1)
        hid.tare()   # F2
        ok("Comando enviado sin error")
        return True
    except ActuatorError as e:
        return fail(f"Error KEY_PRESS: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip",   default=ESP32_IP,   help="IP del ESP32")
    parser.add_argument("--port", default=ESP32_PORT, type=int)
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"  Validación firmware/esp32/ — {args.ip}:{args.port}")
    print(f"{'='*55}")

    actuator = ActuatorClient(args.ip, args.port)
    hid      = HIDClient(args.ip, args.port)

    results = [
        test_status(actuator),
        test_hid_status(hid),
        test_key_press(hid),
        test_key_press_tare(hid),
    ]

    print(f"\n{'='*55}")
    passed = sum(results)
    total  = len(results)
    if passed == total:
        print(f"  ✅  {passed}/{total} tests pasaron — firmware unificado OK")
    else:
        print(f"  ❌  {passed}/{total} tests pasaron")
    print(f"{'='*55}\n")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
