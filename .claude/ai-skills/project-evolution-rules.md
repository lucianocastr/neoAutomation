# Project Evolution Rules — CUORA NEO

## Filosofía

El proyecto debe evolucionar:
- incrementalmente
- acumulativamente
- sin reescrituras masivas
- sin sobreingeniería

---

# Prioridades reales

La prioridad actual es:
- estabilidad física
- repetibilidad
- reducción de falsos positivos
- confiabilidad del laboratorio

NO:
- escalabilidad enterprise
- cloud orchestration
- dashboards

---

# NO agregar todavía

Hasta consolidar estabilidad real, NO introducir:

- Kubernetes
- microservicios
- distributed runners
- dashboards enterprise
- telemetry platform
- plugin architecture compleja
- visual AI
- multi-device real
- cloud orchestration
- event buses
- observabilidad enterprise

---

# Agregar robustez incremental

Toda mejora debe:
- integrarse sobre la arquitectura actual
- respetar contratos existentes
- evitar refactors masivos

---

# Configuración vs arquitectura

Separar:
- reglas arquitectónicas
- parámetros calibrables
- estado runtime
- secrets

No mezclar:
- timing experimental
- contratos de diseño

---

# Evitar complejidad prematura

No abstraer:
- lo que todavía no tiene variaciones reales
- lo que aún no duele mantener
- lo que todavía no tiene múltiples implementaciones

---

# Reglas de implementación

Antes de agregar una nueva capa preguntar:

1. ¿Reduce falsos positivos?
2. ¿Mejora repetibilidad?
3. ¿Reduce debugging?
4. ¿Evita deuda técnica real?
5. ¿Ya existe necesidad concreta?

Si la respuesta es NO:
postergar.

---

# Flakiness

El enemigo principal del proyecto es:
- intermitencia
- inconsistencia
- comportamiento no reproducible

Toda decisión debe priorizar:
- confiabilidad
sobre
- sofisticación

---

# Objetivo final

Construir un entorno:
- confiable
- reproducible
- mantenible
- extensible

sin perder pragmatismo.