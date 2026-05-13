from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class MetrologyRange:
    """Un rango de capacidad de la balanza con su resolución (e)."""
    capacity_kg: float
    division_kg: float

    @property
    def tolerance_g_floor(self) -> float:
        """Tolerancia mínima segura para poll_until_stable(): 1.25 × e en gramos."""
        return self.division_kg * 1000 * 1.25


@dataclass(frozen=True)
class MetrologyProfile:
    """
    Perfil metrológico completo de una variante NEO-2.
    Todos los valores están en kg, independientemente de la unidad nativa.
    """
    variant: str
    unit: str                         # "kg" | "lb"
    unit_to_kg: float                 # factor de conversión (1.0 para kg, 0.453592 para lb)
    ranges: List[MetrologyRange]

    zero_limit_kg: float              # 3% de la capacidad máxima
    tare_limit_kg: float              # tara máxima admitida
    plu_tare_limit_kg: float          # tara en PLUs (5% capacidad máxima)
    above_max_divisions: int          # divisiones de gracia sobre el máximo (0 para AR)
    initial_zero_kg: float            # límite de auto-cero al arranque
    frozen_mode: bool                 # si la variante soporta productos congelados
    drained_mode: bool                # si la variante soporta productos escurridos

    # ── Consultas derivadas ──────────────────────────────────────────────────

    def range_for(self, weight_kg: float) -> MetrologyRange:
        """Retorna el rango activo para un peso dado (el menor rango que lo contiene)."""
        for r in sorted(self.ranges, key=lambda x: x.capacity_kg):
            if weight_kg <= r.capacity_kg:
                return r
        return self.ranges[-1]  # fuera de escala → rango mayor (overload)

    def tolerance_g_for(self, weight_kg: float) -> float:
        """
        Tolerancia mínima segura para poll_until_stable() al medir ese peso.
        Usa 1.25 × e del rango activo. Siempre ≥ 2.5g.
        """
        return max(2.5, self.range_for(weight_kg).tolerance_g_floor)

    def overload_threshold_kg(self, capacity_kg: float) -> float:
        """Peso mínimo que ya debe mostrar overload para una capacidad dada."""
        r = next((x for x in self.ranges if x.capacity_kg == capacity_kg), self.ranges[0])
        grace_kg = self.above_max_divisions * r.division_kg
        return capacity_kg + grace_kg + r.division_kg  # un paso más allá de la gracia

    def min_weighable_kg(self) -> float:
        """Mínimo pesable (20e del rango menor)."""
        return self.ranges[0].division_kg * 20

    def normalize_to_kg(self, value: float) -> float:
        """Convierte un valor en unidades nativas a kg."""
        return value * self.unit_to_kg


def build_profile(variant: str, raw: dict) -> MetrologyProfile:
    """Construye un MetrologyProfile desde el dict leído del YAML."""
    f = raw["unit_to_kg"]
    ranges = [
        MetrologyRange(
            capacity_kg=r["capacity_native"] * f,
            division_kg=r["division_native"] * f,
        )
        for r in raw["ranges"]
    ]
    return MetrologyProfile(
        variant=variant,
        unit=raw["unit"],
        unit_to_kg=f,
        ranges=ranges,
        zero_limit_kg=raw["zero_limit_native"] * f,
        tare_limit_kg=raw["tare_limit_native"] * f,
        plu_tare_limit_kg=raw["plu_tare_limit_native"] * f,
        above_max_divisions=raw["above_max_divisions"],
        initial_zero_kg=raw["initial_zero_native"] * f,
        frozen_mode=raw["frozen_mode"],
        drained_mode=raw["drained_mode"],
    )
