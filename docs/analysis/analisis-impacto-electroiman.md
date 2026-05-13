# ANÁLISIS DE IMPACTO — Automatización con electroimán

> Análisis de riesgos, dependencias y problemas no evidentes del plan de implementación aprobado.
> No es un plan de ejecución — es una lista de cosas que hay que resolver antes o durante.

---

## 1. Estado de archivos (al interrumpir la implementación — 2026-05-13)

| Archivo | Estado |
|---|---|
| `firmware/actuator/include/config.h` | ✅ **Modificado** — PIN_MAGNET, tiempos, SLOT_HEIGHT_MM_x, HOME_HEIGHT_MM, T_BANDEJA_MM, PEG_CLEAR/ENGAGE_MM |
| `firmware/actuator/src/main.cpp` | ✅ **Modificado** — PICK/LIFT/MAGNET_ON/OFF/RESET_MAGAZINE + mm_to_steps + tray_count |
| `config/hardware_params.yaml` | ✅ **Modificado** — sección weight_magazine completa |

---

## 2. Problemas técnicos críticos no contemplados en el plan

### 2.1 Tensión lógica del ESP32 vs MOSFET

El ESP32-S3 opera a **3.3V** en sus GPIO. El IRFZ44N recomendado en el BOM original
requiere **≥4V en la compuerta (Vgs)** para saturarse completamente. A 3.3V, el MOSFET
opera en zona lineal → calor excesivo, control impreciso.

**Decisión tomada:** usar **IRLZ44N** (logic-level, satura a 2.5V). ✅

### 2.2 Fuente de 12V para el electroimán

El ESP32 se alimenta por USB (5V). El electroimán necesita **12V @ ~400mA**.

**Decisión tomada:** fuente DC 12V/1A **separada por enchufe**. ✅
- Circuito: `Fuente 12V → IRLZ44N drain` + `GPIO12 → IRLZ44N gate` + `1N4007 flyback`

### 2.3 Aceleración del stepper — sin rampa aún

El firmware arranca directamente a FAST_SPEED sin rampa trapezoidal.
Con 2kg colgado del imán, la inercia del arranque podría desprender la pesa.

**Decisión tomada:** testear primero antes de implementar la rampa. Si la pesa se cae
durante el movimiento rápido → reducir FAST_SPEED en config.h o implementar rampa.

### 2.4 Pérdida de estado tras reboot del ESP32

`tray_count` vive en RAM. Si el ESP32 se reinicia, el contador queda en 0 aunque haya
pesas en la bandeja.

**Fix implementado:** comando `RESET_MAGAZINE` que el operador ejecuta manualmente
después de despejar la bandeja. El script Python debe llamarlo al inicio de cada sesión.

### 2.5 Geometría del slot de almacenamiento — requiere validación física

El diseño asume que el peg del rack entra por el C-slot de la pesa DOLZ de forma que:
1. La pesa cuelga del peg (peg horizontal a través del C-slot)
2. El carro baja, el electroimán toca la cara superior de la pesa
3. El carro sube, la pesa sale del peg lateralmente (C-slot abierto)

**Esto debe validarse físicamente antes de confiar en PICK/LIFT.** Si la orientación
del C-slot no coincide con el peg, el sistema falla mecánicamente sin error visible en el firmware.

---

## 3. Dependencias entre tareas (orden obligatorio)

```
[A] Resolver fuente 12V / selección MOSFET  ✅ DECIDIDO (12V separada + IRLZ44N)
         │
[B] Construir portal (herrero)               ← BLOQUEANTE para todo
         │
[C] Actualizar SVG del portal                ← herrero lo necesita antes de construir
         │
[D] Soldar rack de almacenamiento            ← BLOQUEANTE para calibrar alturas
         │
[E] Medir alturas reales de los slots        ← actualizar SLOT_HEIGHT_MM_x y home_height_mm
         │
[F] Validar geometría peg + C-slot DOLZ     ← BLOQUEANTE para confiar en PICK/LIFT
         │
[G] Pegar arandelas en pesas de latón        ← pesar tras mod, actualizar nominal_g
         │
[H] Armar circuito electroimán               ← MOSFET + diodo + fuente 12V
         │
[I] Flashear firmware                        ← ya compilable, pendiente hardware
         │
[J] Sprint 0 — calibración                  ← BLOQUEANTE para todos los tests
```

**Nada del firmware es útil hasta tener B+D+H completados.**

---

## 4. Impacto en el SVG del portal

El SVG actual (`assets/puente-portal-actuador.svg`) muestra:

| Elemento | Estado en SVG actual |
|---|---|
| Pin NBR en punta del carro | ✗ — cambiar a electroimán Ø35mm |
| Rack de almacenamiento (4 pegs) | ✗ — agregar en pata izquierda |
| Cableado eléctrico 12V | ✗ — agregar conducto por columna |
| Medidas de los slots | ✗ — agregar cotas de altura |

**El herrero necesita el SVG actualizado antes de fabricar.** El portal actual
no incluye el rack → hay que rediseñar el SVG antes de enviarlo.

---

## 5. Impacto en las pesas físicas (modificación permanente)

Las pesas de 500g de latón requieren pegar una arandela de hierro M6 (Ø18mm, ~3g).
Esto **altera su masa nominal**:

| Uso | Impacto |
|---|---|
| Tests funcionales (precio × peso) | Sin impacto — tolerancia amplia |
| Tests metrológicos certificados | ⚠️ la pesa pasa a ser ~503g — usar valor real medido |

**Acción post-modificación:** pesar la pesa en la propia balanza y actualizar
`nominal_g` en `config/hardware_params.yaml` slot 2 y 3 con el valor medido.

---

## 6. Scope real de main.cpp

| Cambio | Estado |
|---|---|
| `magnet_on()` / `magnet_off()` | ✅ Implementado |
| `mm_to_steps()` / `slot_to_steps()` | ✅ Implementado |
| `handle_pick(slot)` | ✅ Implementado |
| `handle_lift(slot)` | ✅ Implementado |
| `handle_reset_magazine()` | ✅ Implementado |
| Nuevos estados PICKING/LIFTING en enum | ✅ Implementado |
| `tray_count` global en STATUS | ✅ Implementado |
| `PIN_MAGNET` en setup() | ✅ Implementado |
| Nuevos casos en switch loop() | ✅ Implementado |
| Rampa trapezoidal de aceleración | ⏳ Diferida — testear primero |

---

## 7. Decisiones pendientes post-construcción

| # | Qué decidir | Cuándo |
|---|---|---|
| 1 | Alturas reales de cada slot | Tras soldar el rack |
| 2 | HOME_HEIGHT_MM real | Tras construir el portal |
| 3 | Fuerza real del imán (¿aguanta 2kg en movimiento?) | Sprint 0 — primer test PICK |
| 4 | ¿Es necesaria la rampa de aceleración? | Sprint 0 — si la pesa se cae |
| 5 | Masa real de 500g tras pegar arandela | Tras modificar las pesas |
