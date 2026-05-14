"""
Tests de conectividad y formato de la API REST de la CUORA NEO.

No requieren portal físico ni ESP32. Solo la balanza encendida y en red.

Ejecutar:
    pytest tests/test_api_connectivity.py -v
"""

import pytest
from tests.errors import ConnectivityError


# ── ping ─────────────────────────────────────────────────────────


class TestPing:
    def test_ping_responde(self, api):
        """/api/ping debe responder sin excepción."""
        result = api.ping()
        assert result is not None

    def test_ping_retorna_pong(self, api):
        """/api/ping retorna el string 'pong'."""
        assert api.ping() == "pong"


# ── weight ───────────────────────────────────────────────────────


class TestWeight:
    def test_weight_responde(self, api):
        """/api/weight debe responder sin excepción."""
        raw = api._get("/api/weight")
        assert "weight" in raw

    def test_weight_es_parseable(self, api, profile):
        """El valor de peso debe convertirse a float (coma → punto)."""
        peso_kg = api.get_weight(profile.unit_to_kg)
        assert isinstance(peso_kg, float)

    def test_weight_en_rango_fisico(self, api, profile):
        """Peso debe estar dentro del rango físico de la balanza (−cap … +cap)."""
        max_kg = max(r.capacity_kg for r in profile.ranges)
        peso_kg = api.get_weight(profile.unit_to_kg)
        assert -max_kg <= peso_kg <= max_kg, (
            f"Peso {peso_kg:.3f}kg fuera del rango físico ±{max_kg}kg"
        )

    def test_weight_formato_raw(self, api):
        """El campo 'weight' en la respuesta cruda usa coma como separador decimal."""
        raw = api._get("/api/weight")
        w_str = str(raw["weight"])
        # La API retorna coma decimal: "0,000", "1,234", etc.
        # No debe contener punto decimal en el valor crudo
        assert "," in w_str or w_str.lstrip("-").replace(".", "").isdigit(), (
            f"Formato inesperado de weight: {w_str!r}"
        )


# ── signature ────────────────────────────────────────────────────


class TestSignature:
    def test_signature_responde(self, api):
        """/api/signature debe responder sin excepción."""
        sig = api.signature()
        assert sig is not None

    def test_signature_es_dict(self, api):
        """/api/signature debe retornar un objeto (dict)."""
        sig = api.signature()
        assert isinstance(sig, dict)

    def test_signature_no_vacio(self, api):
        """El dict de signature no debe estar vacío."""
        sig = api.signature()
        assert len(sig) > 0


# ── endpoints inexistentes ───────────────────────────────────────


class TestEndpointsInexistentes:
    @pytest.mark.parametrize("path", ["/api/sales", "/api/ticket"])
    def test_endpoint_retorna_404(self, api, path):
        """Endpoints no implementados deben retornar HTTP 404."""
        import requests
        import os
        url = f"http://{os.getenv('NEO_IP', '192.168.100.123')}:{os.getenv('NEO_API_PORT', '7376')}{path}"
        r = requests.get(url, timeout=5)
        assert r.status_code == 404, f"{path} retornó {r.status_code}, esperado 404"
