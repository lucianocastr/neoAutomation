# CUORA NEO Automation Suite — Core Architecture

## Objetivo del proyecto

Construir una suite HIL (Hardware-In-The-Loop) confiable y reproducible para validar:
- conectividad
- pesaje
- ventas
- ABM
- persistencia
- comportamiento metrológico

sobre balanzas CUORA NEO.

La prioridad NO es escalar infraestructura.
La prioridad es:
- estabilidad
- repetibilidad
- aislamiento
- reducción de falsos positivos
- confiabilidad del laboratorio

---

# Principios arquitectónicos

## API REST = fuente numérica de verdad

Los valores numéricos se leen SIEMPRE desde:
- GET /api/weight
- GET /api/product
- endpoints REST equivalentes

NO leer:
- peso por OCR
- precio por OCR
- PLU desde VNC

VNC solo valida:
- estado cualitativo
- pantalla correcta
- diálogos visibles
- navegación visual

---

## VNC es observación, NO control

- VNC siempre view-only
- pynput USB HID es el único canal de input físico
- Cypress nunca interactúa con la Java app táctil

---

## Cypress-first

Cypress cubre:
- API REST
- panel web
- ABM
- reportes
- configuración

Python/pytest cubre:
- SSH
- PostgreSQL
- hardware
- VNC
- OCR/OpenCV
- actuador

---

## No sleeps fijos para estabilización

Está prohibido usar:

```python
time.sleep(5)
```

para esperar estabilización de peso.

Siempre usar:
- poll_until_stable()
- verificaciones de estado
- convergencia dinámica

---

## SSH es readonly para el SO

Prohibido:
- apt update
- apt upgrade
- apt install
- modificar paquetes del device

Los tests SSH:
- verifican
- leen
- inspeccionan

No alteran el sistema operativo.

---

## Ownership por capa

| Dominio | Ownership |
|---|---|
| API schema | Cypress API |
| Panel web | Cypress Web |
| Persistencia | pytest + PostgreSQL |
| Hardware | pytest hardware |
| Estado visual | pytest VNC |

No duplicar validaciones entre capas.

---

## El laboratorio es parte del sistema

La suite depende de:
- estabilidad física
- calibración
- repetibilidad
- estado limpio

No asumir laboratorio perfecto.

---

## NO sobreingeniería

No introducir:
- Kubernetes
- microservicios
- dashboards enterprise
- distributed runners
- plugin architectures complejas

hasta lograr:
- estabilidad física
- flakiness baja
- reproducibilidad consistente

---

# Objetivo final

La suite debe producir resultados:
- repetibles
- confiables
- diagnosticables
- consistentes entre corridas