class NEOTestError(Exception):
    """Excepción base de la suite. Subclasificar siempre, no lanzar directamente."""
    category: str = "unknown"


class ConnectivityError(NEOTestError):
    category = "connectivity_failure"
    # Cuándo lanzar: device no responde, timeout de red, SSH no conecta


class StabilizationError(NEOTestError):
    category = "stabilization_failure"
    # Cuándo lanzar: poll_until_stable() excede max_wait sin convergencia


class ActuatorError(NEOTestError):
    category = "actuator_failure"
    # Cuándo lanzar: ESP32 no responde, motor atascado, peso estabilizó en cero tras set()


class FirmwareMismatchError(NEOTestError):
    category = "firmware_mismatch"
    # Cuándo lanzar: versión detectada no está en SUPPORTED_FIRMWARE


class StateCorruptionError(NEOTestError):
    category = "state_corruption"
    # Cuándo lanzar: clean_state no pudo llevar la balanza a READY en N intentos


class WeightAssertionError(NEOTestError):
    category = "assertion_failure"
    # Cuándo lanzar: peso medido fuera del rango aceptable


class TimeoutError(NEOTestError):
    category = "timeout_failure"
    # Cuándo lanzar: timeout genérico no clasificable en las categorías anteriores
