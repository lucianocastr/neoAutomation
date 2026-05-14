"""
Prototipo: Test de Tara + Peso de Producto

El actuador (pin NBR) simula el peso del envase vacío en la Fase 1 y el peso
total (envase + producto) en la Fase 2. La balanza aplica TARA entre fases,
por lo que la lectura neta en Fase 2 corresponde solo al producto.

Requiere:
  - Portal físico construido y firmware/actuator/ flasheado en el ESP32-S3
  - Sprint 0 completado (STEPS_PER_GRAM calibrado)
  - .env.test con NEO_ESP32_ACTUATOR_IP, NEO_ESP32_HID_IP, NEO_IP, NEO_API_PORT
"""

import pytest

from tests.actuator_client import ActuatorClient
from tests.hid_client import HIDClient
from tests.api_client import NEOApiClient
from tests.metrology import MetrologyProfile
from tests.assertions import assert_weight, assert_negative_within_limit
from tests.poll_utils import poll_until_stable

TARE_G    = 500    # fuerza que simula el envase vacío (gramos)
PRODUCT_G = 1000   # fuerza que simula el producto (gramos)


def test_tare_and_product_weight(
    actuator: ActuatorClient,
    api: NEOApiClient,
    hid: HIDClient,
    profile: MetrologyProfile,
):
    # ── FASE 1: Simular envase vacío y aplicar tara ─────────────

    actuator.home()
    initial = api.get_weight(profile.unit_to_kg)
    assert initial < 0.003, (
        f"Bandeja no libre antes del test: {initial * 1000:.1f}g "
        f"(máximo esperado 3g)"
    )

    actuator.set_weight(TARE_G)
    poll_until_stable(api, profile, expected_weight_kg=TARE_G / 1000)

    hid.tare()
    poll_until_stable(api, profile, expected_weight_kg=0.0)

    # ── FASE 2: Simular envase + producto, verificar peso neto ──

    actuator.set_weight(TARE_G + PRODUCT_G)
    poll_until_stable(api, profile, expected_weight_kg=PRODUCT_G / 1000)

    measured = api.get_weight(profile.unit_to_kg)
    assert_weight(measured, PRODUCT_G / 1000, profile, label="product_net")

    # ── FASE 3: Retirar y dejar limpio ──────────────────────────

    actuator.zero()
    # Con tara activa y pin retraído la balanza muestra exactamente -TARE_G.
    poll_until_stable(api, profile, expected_weight_kg=-(TARE_G / 1000))

    # F2 con bandeja vacía cancela la tara (F4/CERO no cancela tara).
    hid.tare()
    poll_until_stable(api, profile, expected_weight_kg=0.0)

    final = api.get_weight(profile.unit_to_kg)
    assert final < 0.003, (
        f"Bandeja no quedó libre al final del test: {final * 1000:.1f}g"
    )
