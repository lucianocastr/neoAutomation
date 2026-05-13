# CUORA NEO — Estado del proyecto
### Suite de automatización de pruebas · Actualizado: 2026-05-13

---

## Estado general

| Etapa | Estado | Detalle |
|---|:---:|---|
| Arquitectura y diseño | ✅ Completo | Plan v2.0, 24 secciones, ~2200 líneas |
| Contratos de código | ✅ Completo | MetrologyProfile, NEOApiClient, WeightActuatorContract |
| Diseño del hardware | ✅ Completo | Puente portal 500mm, pin flotante, lista de materiales |
| **Infra Python** | ✅ Creado + corregido | `tests/errors.py`, `api_client.py`, `metrology.py`, `assertions.py` |
| **Config y env** | ✅ Creado | `config/hardware_params.yaml`, `.env.test.example` (IPs reales) |
| **Firmware HID ESP32-S3** | ✅ Flasheado y validado | `firmware/hid/hid.ino` — TCP :9999, KEY_PRESS verificado |
| **Stack HID end-to-end** | ✅ Validado | KEY_PRESS F4 → balanza ejecutó CERO (0.014→0.000 kg) |
| **SVG puente portal** | ✅ Diseñado | `assets/puente-portal-actuador.svg` — T_BANDEJA=162mm, telescópico 380–560mm |
| **Firmware actuador (pin)** | ✅ Listo para flashear | `firmware/actuator/` — SET_WEIGHT/HOME/ZERO, hardware no construido |
| **Firmware actuador (electroimán)** | ❌ Descartado | `firmware/actuator-electroiman/` — diseño descartado, se usa pin NBR |
| Tests de aplicación | ❌ No iniciado | Cypress (Fases 1-2), pytest (Fases 3-4) |
| **Hardware físico (puente portal)** | ❌ No construido | SVG listo para herrero — sin rack (design B descartado) |
| Sprint 0 — curva de estabilización | 🟡 Pendiente hardware | Construir portal primero |

**Archivos creados y validados:**
```
tests/__init__.py
tests/errors.py                               ← jerarquía de excepciones tipadas (§18)
tests/api_client.py                           ← NEOApiClient (§17) — bugs corregidos 2026-05-12
tests/metrology.py                            ← MetrologyProfile + build_profile() (§23)
tests/assertions.py                           ← assert_weight, assert_overload_triggered... (§24)
config/hardware_params.yaml                   ← parámetros físicos + metrología AR/BR/US (§16 + §22.3)
.env.test.example                             ← plantilla con IPs reales del entorno

firmware/actuator/platformio.ini              ← PlatformIO ESP32-S3 DevKitC-1 N16R8
firmware/actuator/include/config.h            ← pines y constantes de movimiento (APROBADO)
firmware/actuator/src/main.cpp                ← actuador pin NBR: SET_WEIGHT/HOME/ZERO (APROBADO)

firmware/actuator-electroiman/platformio.ini  ← mismo board (DISEÑO PARALELO — no flashear aún)
firmware/actuator-electroiman/include/config.h← config + PIN_MAGNET, slots, HOME_HEIGHT_MM
firmware/actuator-electroiman/src/main.cpp    ← PICK/LIFT/MAGNET_ON/OFF, tray_count

firmware/hid/hid.ino                          ← HID teclado — flasheado y validado ✅

assets/puente-portal-actuador.svg             ← plano del puente portal (T_BANDEJA=162mm)
assets/pesas.jpeg                             ← foto inventario pesas DOLZ disponibles

docs/API-Cuora-NEO.docx
docs/CUORA-NEO-manual.pdf
docs/ESP32-DevKitC.docx
docs/PM-objetivos.xlsx                        ← objetivos DB-4.x del PM
docs/informes/                                ← informes de avance generados
docs/analysis/analisis-impacto-electroiman.md ← riesgos y dependencias del diseño con electroimán
```

---

## Tracking PM — Objetivos DB-4.x

| ID | Deliverable | Fecha límite | Estado real | Notas |
|---|---|---|---|---|
| DB-4.1 | Diseño de arquitectura HW/SW con I+D | 28/06/26 | ✅ Completo | Finalizado antes de fecha |
| DB-4.2 | Módulo funcional teclado | 22/06/26 | ✅ Completo | ESP32 HID validado end-to-end 12/05/26 — adelantado |
| DB-4.3 | Módulo funcional pesaje | 06/08/26 | 🔄 En progreso | Firmware actuador listo, construcción mecánica pendiente |
| DB-4.4 | Módulo funcional pantalla | 27/08/26 | ⏳ Pendiente | VNC + OpenCV template matching (§21 del plan) |
| DB-4.5 | Módulo funcional conectividades (ETH/WiFi/USB) | 17/09/26 | ⏳ Pendiente | Cypress: ping ETH, ping WiFi, HID USB (ya validado) |
| DB-4.6 | Módulo funcional impresión tickets | 17/10/26 | ⏳ Pendiente | pytest: verificar ticket en BD + captura VNC |
| DB-4.7 | Módulo funcional impresión etiquetas | 16/11/26 | ⏳ Pendiente | pytest: verificar etiqueta en BD + captura VNC |
| DB-4.8 | Módulo funcional Systel Cloud One | 16/12/26 | ⏳ Fase futura | Plataforma multitenant de importación remota — fuera del alcance actual |
| DB-4.9 | Ensayo completo sobre Cuora Neo | 23/12/26 | ⏳ Pendiente | Integración total: ESP32 + VNC + reconocimiento de imagen |

**Notas de alineación:**
- Los IDs HTML de DB-4.7 son recomendaciones de nomenclatura para el equipo de UI — Cypress usará los selectores reales que tenga la interfaz cuando se implemente.
- Systel Cloud One (DB-4.8) es una plataforma multitenant separada. Se validará en una fase posterior fuera del alcance actual.

---

## IPs del entorno de pruebas (confirmadas 2026-05-12)

| Dispositivo | IP | MAC | Puerto |
|---|---|---|---|
| Balanza CUORA NEO-2 (Ethernet) | `192.168.100.123` | `0a:f3:55:12:40:4d` | API :7376, Web :80 |
| Balanza CUORA NEO-2 (WiFi) | `192.168.100.213` | `90:de:80:aa:6b:7f` | mismo dispositivo |
| ESP32-S3 DevKitC-1 N16R8 | `192.168.100.202` | `ac:a7:04:15:00:dc` | TCP :9999 |

**Firmware balanza:** versión `0809`, full scale `30.0 kg`, unidad `kg`

---

## Hallazgos de integración (2026-05-12)

### API REST — quirks confirmados

| Endpoint | Respuesta real | Nota |
|---|---|---|
| `GET /api/ping` | `"pong"` (string JSON) | No es `{"status":"pong"}` — `api_client.py` corregido |
| `GET /api/weight` | `{"weight":"0,000"}` | **Coma** como separador decimal, no punto — `api_client.py` corregido |
| `GET /api/signature` | dict completo | Ok, sin quirks |

### Firmware HID — fix crítico aplicado

**Problema:** Al conectar el ESP32 al USB de la balanza, el kernel Linux de la balanza
se colgaba (freeze total: sin touch, sin teclado, sin SSH). Causa: el stack USB del
kernel recibía el HID device durante su propia inicialización.

**Fix:** invertir el orden de init en `firmwareesp32.ino`:
1. WiFi + TCP server **primero** (control remoto disponible antes de tocar el USB)
2. `delay(8000)` — esperar que el kernel de la balanza esté estable
3. `USB.begin()` + `Keyboard.begin()` al final

**Comportamiento sin USB host:** el ESP32 crashea y reinicia en loop. Es esperado
y normal — solo funciona correctamente cuando está conectado a la balanza.

### Stack end-to-end validado

```
PC → TCP 192.168.100.202:9999 → ESP32 → USB HID → Balanza 192.168.100.123
     KEY_PRESS F4 (CERO)       ok        ok          peso: 0,014 → 0,000 kg ✅
```

---

## Lo próximo a hacer (en orden)

### 1. Decidir diseño del actuador y actualizar SVG del portal

Antes de ir al herrero hay que decidir qué firmware se usará:

**Opción A — Pin fijo (aprobado):** pesa física en la bandeja, motor aplica fuerza.
Firmware: `firmware/actuator/` (listo para flashear).

**Opción B — Electroimán (paralelo):** PICK/LIFT automático de pesas DOLZ.
Firmware: `firmware/actuator-electroiman/` (listo para flashear).
Análisis completo: `docs/analysis/analisis-impacto-electroiman.md`.

⚠️ **Si se elige Opción B**, actualizar el SVG antes de enviarlo al herrero:
- Reemplazar punta NBR por electroimán Ø35mm
- Agregar rack de 4 pegs en pata izquierda (alturas: 430/390/350/310mm desde mesa)
- Agregar conducto cable 12V por columna

**Inventario de pesas disponibles (DOLZ):**
- 2 kg × 1 (hierro fundido, ferromagnético)
- 1 kg × 1 (hierro fundido, ferromagnético)
- 500 g × 2–3 (latón — si Opción B: pegar arandela M6 encima, pesar tras mod)

Falta construir la parte mecánica:
- Puente portal telescópico (SVG en `assets/puente-portal-actuador.svg`)
- Motor NEMA17 + driver DRV8825
- Fin de carrera home + seguridad
- Ver lista de materiales en **§5** y **§11** del plan

### 2. Sprint 0 — curva de estabilización (1–2 días con hardware)

Ejecutar `scripts/sprint0_estabilizacion.py` para medir cuánto tarda el sensor
en estabilizarse. **Sin este dato, `max_wait_s` en `poll_until_stable()` es una adivinanza.**

```bash
python scripts/sprint0_estabilizacion.py
# → genera estabilizacion.csv
# → medir: ¿en cuántos segundos la variación cae < ±1g?
# → ese valor define max_wait_s y stable_reads en config/hardware_params.yaml
```

Checklist completo: ver **§4 Fase 0** del plan.

### 3. Completar `.env.test`

```bash
cp .env.test.example .env.test
# IPs ya conocidas. Completar solo:
#   NEO_SSH_USER, NEO_SSH_PASS o KEY_PATH
#   NEO_DB_NAME, NEO_DB_USER, NEO_DB_PASS
```

Verificaciones pendientes (requieren credenciales):
```bash
ssh systel@192.168.100.123 uptime    # confirmar usuario SSH
# VNC: vncviewer 192.168.100.123:5900
```

### 4. Fase 1 — Cypress API (1 semana)

Prerequisito: Sprint 0 ejecutado + `.env.test` completo.

Primer test: `cypress/e2e/api/connectivity.cy.js`
- `GET /api/ping` → respuesta `"pong"` (string, no dict) en < 200ms
- `GET /api/weight` → valor numérico con coma decimal, parseable

---

## Mapa del plan (qué sección buscar para qué)

| Necesito saber sobre... | Sección | Línea aprox. |
|---|---|---|
| Fases y cronograma | **§4** | 152 |
| Primer test ejecutable (Sprint 0) | §4 Fase 0 | 154 |
| Checklist antes de cada fase | **§14** | 1235 |
| Estructura de carpetas | **§9** | 851 |
| Variables de entorno completas | **§10** | 921 |
| `poll_until_stable()` — firma actual | **§6.5** | 731 |
| `clean_state` fixture | **§8** | 807 |
| Hardware: planos y materiales | **§5** + §11 | 539, 1142 |
| `MetrologyProfile` (AR/BR/US) | **§23** | 1975 |
| `assertions.py` | **§24** | 2108 |
| Datos metrológicos por país | **§22** | 1804 |
| `NEOApiClient` | **§17** | 1458 |
| `errors.py` — excepciones tipadas | **§18** | 1544 |
| `hardware_params.yaml` | **§16** | 1389 |
| Riesgos críticos | **§12** | 1195 |
| Comandos SSH permitidos / prohibidos | §4 Fase 3 | 340 |
| Calibración del actuador (15 pesas) | §6.3 | 668 |
| Anti-backlash firmware ESP32 | §6.4 | 700 |
| Pin flotante — cómo funciona | **§7** | 781 |
| Orchestration (`PhaseResult`, hooks) | **§10b** | 949 |
| Firmware compatibility preflight | **§10c** | ~1100 |
| Flakiness measurement | **§21** | 1717 |

---

## Módulos de código (estado)

```
✅ Creados (2026-05-08 al 2026-05-13):
  tests/__init__.py
  tests/errors.py
  tests/api_client.py                              ← fix: coma decimal en weight, ping string
  tests/metrology.py
  tests/assertions.py
  config/hardware_params.yaml
  .env.test.example                               ← IPs reales del entorno
  assets/puente-portal-actuador.svg               ← plano portal T_BANDEJA=162mm ← NUEVO
  firmware/actuator/platformio.ini
  firmware/actuator/include/config.h              ← APROBADO (pin NBR)
  firmware/actuator/src/main.cpp                  ← APROBADO (sin flashear — HW no construido)
  firmware/actuator-electroiman/platformio.ini    ← PARALELO ← NUEVO
  firmware/actuator-electroiman/include/config.h  ← PARALELO ← NUEVO
  firmware/actuator-electroiman/src/main.cpp      ← PARALELO ← NUEVO
  firmware/hid/hid.ino                            ← flasheado y validado ✅
  docs/analysis/analisis-impacto-electroiman.md   ← riesgos/dependencias ← NUEVO

❌ Pendientes — crear en este orden:
  scripts/sprint0_estabilizacion.py    ← §4 Fase 0
  scripts/calibracion_bandeja.py       ← §6.2

  Fase 1 (Cypress API):
    cypress/package.json
    cypress/cypress.config.js
    cypress/support/commands.js
    cypress/support/e2e.js
    cypress/e2e/api/connectivity.cy.js
    cypress/e2e/api/abm.cy.js
    cypress/e2e/api/pesaje.cy.js
    cypress/e2e/api/ventas.cy.js

  Fase 2 (Cypress Web):
    cypress/e2e/web/login.cy.js
    cypress/e2e/web/abm_plu.cy.js
    cypress/e2e/web/price_lists.cy.js
    cypress/e2e/web/reports.cy.js
    cypress/e2e/web/config.cy.js

  Fase 3 (pytest SSH):
    tests/conftest.py
    tests/ssh/conftest.py
    tests/ssh/test_system_health.py
    tests/ssh/test_db_state.py

  Fase 4 (pytest VNC/Hardware):
    tests/vnc/pages/vnc_base.py
    tests/vnc/pages/device_state.py
    tests/vnc/pesaje/test_tara_directa.py
    tests/vnc/pesaje/test_ajuste_cero.py
    tests/vnc/pesaje/test_sobrecarga.py
    tests/vnc/ventas/test_venta_pesable.py
    scripts/flakiness_report.py
```

---

## Decisiones de arquitectura que no cambiar

| Decisión | Por qué |
|---|---|
| `tolerance_g` nunca hardcodeado | Deriva de `MetrologyProfile.tolerance_g_for()` según el rango activo |
| VNC solo lectura (view-only) | pynput es el único canal de teclado; VNC+HID duplican teclas |
| Valores numéricos (peso, precio) solo desde la API | VNC OCR es frágil; la API es la fuente de verdad |
| SSH: solo lectura del SO | El SO tiene customizaciones Systel — `apt update/upgrade` está prohibido |
| `poll_until_stable()` siempre recibe `profile` | La tolerancia depende del rango del instrumento, no es constante |
| Tests usan `cal["700"]`, nunca `700` directamente | El peso nominal difiere del medido — siempre usar calibración de sesión |
| PLUs de test en rango 90000–99999 | Evita colisión con datos reales del comercio |
| WiFi + TCP server init antes que USB HID | El kernel de la balanza se congela si recibe HID durante su init |
| `firmware/actuator/` es el diseño aprobado | Pin NBR + fuerza por motor. No modificar sin decisión explícita |
| `firmware/actuator-electroiman/` es paralelo | Electroimán PICK/LIFT — no reemplaza al aprobado hasta validar hardware |
| SVG del portal debe actualizarse antes del herrero | Si se elige electroimán, el rack de 4 pegs debe quedar en el plano de fabricación |

---

## Comandos de verificación rápida

```bash
# ¿Está la balanza en la red?
curl http://192.168.100.123:7376/api/ping
# Responde: "pong"  (string, no dict)

# ¿Qué firmware tiene?
curl http://192.168.100.123:7376/api/signature
# → version: "0809", scaleFS: 30.0 kg

# ¿Cuánto pesa ahora?
curl http://192.168.100.123:7376/api/weight
# Responde: {"weight":"0,000"}  ← coma decimal, no punto

# ¿ESP32 responde?
echo '{"cmd":"STATUS"}' | nc 192.168.100.202 9999

# ¿Tecla llega a la balanza?
echo '{"cmd":"KEY_PRESS","key":"F4"}' | nc 192.168.100.202 9999

# Correr primer test (Fase 1, cuando exista):
npx cypress run --spec "cypress/e2e/api/connectivity.cy.js"

# Correr tests SSH (Fase 3, cuando existan):
pytest tests/ssh/ -v

# Correr todo con hardware (Fase 4):
pytest tests/vnc/ -s -m hardware
```
