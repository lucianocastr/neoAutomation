from tests.metrology import MetrologyProfile
from tests.errors import WeightAssertionError


def assert_weight(
    measured_kg: float,
    expected_kg: float,
    profile: MetrologyProfile,
    tolerance_g: float = None,
    label: str = "",
) -> None:
    """
    Verifica que measured_kg esté dentro de la tolerancia metrológica del rango activo.
    Si tolerance_g no se especifica, usa profile.tolerance_g_for(expected_kg).
    """
    tol = (tolerance_g or profile.tolerance_g_for(expected_kg)) / 1000
    delta = abs(measured_kg - expected_kg)
    if delta > tol:
        raise WeightAssertionError(
            f"{'['+label+'] ' if label else ''}"
            f"Peso medido {measured_kg*1000:.1f}g, esperado {expected_kg*1000:.1f}g, "
            f"delta {delta*1000:.1f}g > tolerancia {tol*1000:.1f}g "
            f"(variante {profile.variant}, e={profile.range_for(expected_kg).division_kg*1000:.0f}g)"
        )


def assert_overload_triggered(
    measured_kg: float,
    capacity_kg: float,
    profile: MetrologyProfile,
) -> None:
    """Verifica que la balanza reportó sobrecarga para la capacidad activa."""
    threshold = profile.overload_threshold_kg(capacity_kg)
    if measured_kg < threshold:
        raise WeightAssertionError(
            f"Sobrecarga NO detectada: {measured_kg*1000:.0f}g < umbral {threshold*1000:.0f}g "
            f"(variante {profile.variant}, above_max={profile.above_max_divisions}e)"
        )


def assert_below_minimum_weighable(
    measured_kg: float,
    profile: MetrologyProfile,
) -> None:
    """Verifica que el peso está bajo el mínimo pesable (zona de 'peso insuficiente')."""
    min_w = profile.min_weighable_kg()
    if measured_kg >= min_w:
        raise WeightAssertionError(
            f"Peso {measured_kg*1000:.0f}g está sobre el mínimo pesable "
            f"{min_w*1000:.0f}g ({profile.variant})"
        )


def assert_tare_within_limit(tare_kg: float, profile: MetrologyProfile) -> None:
    """Verifica que la tara solicitada no excede el límite de la variante."""
    if tare_kg > profile.tare_limit_kg:
        raise WeightAssertionError(
            f"Tara {tare_kg*1000:.0f}g excede límite {profile.tare_limit_kg*1000:.0f}g "
            f"({profile.variant})"
        )


def assert_negative_within_limit(measured_kg: float, profile: MetrologyProfile) -> None:
    """Verifica que un peso negativo (diferencia de tara) está dentro del rango permitido."""
    min_negative = -profile.min_weighable_kg()
    if measured_kg < min_negative:
        raise WeightAssertionError(
            f"Peso negativo {measured_kg*1000:.0f}g por debajo del límite "
            f"{min_negative*1000:.0f}g ({profile.variant})"
        )
