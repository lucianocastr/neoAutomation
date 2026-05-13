# Hardware HIL — CUORA NEO

## Principio general

El sistema físico es parte central de la arquitectura.
Los tests dependen de:
- estabilidad mecánica
- repetibilidad
- timing real
- gravedad
- vibraciones
- backlash

No asumir comportamiento ideal.

---

# Actuador

El actuador utiliza:
- ESP32-S3 DevKitC-1 N16R8 (16MB Flash, 8MB PSRAM)
- NEMA17
- DRV8825
- lead screw M8
- puente portal
- pin flotante

## Board: ESP32-S3 DevKitC-1 N16R8

| Parámetro | Valor |
|---|---|
| Chip | ESP32-S3, Xtensa LX7 dual-core 240MHz |
| Flash / PSRAM | 16MB / 8MB |
| GPIO útiles | 45 |
| USB-UART | Puerto USB-A izquierdo — CP2102 (GPIO43/44) — para programar y debug |
| USB OTG nativo | Puerto USB-A derecho — GPIO19/20 — para USB HID hacia la balanza |
| PlatformIO board ID | `esp32-s3-devkitc-1` |

Los dos puertos USB son independientes: se puede programar por UART y tener el OTG conectado a la balanza simultáneamente.

## Pines reservados

- GPIO19, GPIO20 → USB OTG D−/D+. No usar para otra función si HID está activo.
- GPIO0 → boot mode. Evitar pull-down en circuito.
- GPIO43, GPIO44 → UART0 (TX/RX del CP2102). No conectar a periféricos.

---

# Pin flotante

El pin NO transmite carga estructural al carro.

Objetivo:
- garantizar que el peso recaiga completamente sobre la bandeja
- evitar fuerzas parásitas
- reducir vibraciones
- mejorar repetibilidad

La holgura axial del pin implica:
- el carro puede subir
- mientras el pin sigue apoyado

Por eso:
- zero() NO implica bandeja libre inmediata

---

# Lifecycle del actuador

Flujo obligatorio:

set(weight)
↓
contact detection
↓
mechanical settle
↓
poll_until_stable()
↓
ready_for_assertion

Los tests NO deben:
- asumir estabilización inmediata
- usar sleeps arbitrarios
- verificar peso antes de convergencia

---

# Anti-backlash

La compensación de backlash es responsabilidad:
- EXCLUSIVA del firmware ESP32-S3

Los tests:
- NO conocen backlash
- NO compensan backlash
- NO ajustan posiciones manualmente

Toda posición final debe alcanzarse:
- desde arriba
- mediante aproximación descendente final

---

# Ownership del timing

| Capa | Responsabilidad |
|---|---|
| firmware ESP32-S3 | movimiento |
| actuador | posición |
| poll_until_stable | convergencia |
| tests | lógica funcional |

No duplicar waits entre capas.

---

# Estabilización

Toda lectura de peso debe pasar por:
- poll_until_stable()

Nunca:
- requests.get("/weight") directo para assertions finales

---

# Estado READY

La balanza se considera READY únicamente si:
- peso < threshold
- sin tara
- sin PLU
- pantalla principal
- sin diálogos activos

Todos los tests deben iniciar desde READY.

---

# Riesgos físicos reales

Considerar siempre:
- backlash
- vibraciones
- deriva
- desgaste
- pin atascado
- homing incorrecto
- desplazamiento de bandeja
- variaciones mecánicas

La suite debe detectar:
- inconsistencia
- no ocultarla con retries excesivos

---

# Filosofía

La prioridad es:
- confiabilidad del laboratorio
- repetibilidad física
- estabilidad operacional

No sofisticación mecánica prematura.