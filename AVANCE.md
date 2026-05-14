# CUORA NEO — Estado del proyecto
### Suite de automatización de pruebas · Actualizado: 2026-05-14 (sesión 4)

---

## Estado general

| Etapa | Estado | Detalle |
|---|:---:|---|
| Arquitectura y diseño | ✅ Completo | Plan v2.0, 24 secciones, ~2200 líneas |
| Contratos de código | ✅ Completo | MetrologyProfile, NEOApiClient, WeightActuatorContract |
| Diseño del hardware | ✅ Completo | Puente portal 500mm, pin flotante, lista de materiales |
| **Infra Python** | ✅ Creado + corregido | `tests/errors.py`, `api_client.py`, `metrology.py`, `assertions.py` |
| **Config y env** | ✅ Creado | `config/hardware_params.yaml`, `.env.test.example` (IPs reales) |
| **Firmware HID ESP32-S3** | 📦 Referencia | `firmware/hid/hid.ino` — supersedido por firmware/esp32/ |
| **Stack HID end-to-end** | ✅ Validado | KEY_PRESS F4 → balanza ejecutó CERO (0.014→0.000 kg) |
| **SVG puente portal** | ✅ Diseñado | `assets/puente-portal-actuador.svg` — T_BANDEJA=162mm, telescópico 380–560mm |
| **Firmware actuador (pin)** | 📦 Referencia | `firmware/actuator/` — supersedido por firmware/esp32/ |
| **Firmware ESP32 unificado** | ✅ Flasheado y validado | `firmware/esp32/` — HID + Actuador en un solo ESP32-S3 — end-to-end OK 2026-05-13 |
| **Firmware actuador (electroimán)** | ❌ Descartado | `firmware/actuator-electroiman/` — diseño descartado 2026-05-13 |
| **Clientes Python + test prototipo** | ✅ Validado con hardware | `test_tare_product.py` corregido — F2 cancela tara, no F4 |
| **Prueba manual guiada** | ✅ Validado 2026-05-13 | `scripts/prueba_manual.py` — tara+producto con pesas físicas, 4/4 fases OK |
| **Prueba manual venta** | ✅ Validado 2026-05-13 | `scripts/prueba_manual_venta.py` — PLU+peso+ticket, invoice en BD verificada |
| Tests de aplicación | ❌ No iniciado | Cypress (Fases 1-2), pytest SSH/VNC (Fases 3-4) |
| **Hardware físico (puente portal)** | ❌ No construido | SVG listo — solo bloquea tests de pesaje automatizado |
| Sprint 0 — curva de estabilización | 🟡 Pendiente hardware | Ejecutar tras construir portal |

**Archivos creados y validados:**
```
tests/__init__.py
tests/errors.py                               ← jerarquía de excepciones tipadas (§18)
tests/api_client.py                           ← NEOApiClient (§17) — bugs corregidos 2026-05-12
tests/metrology.py                            ← MetrologyProfile + build_profile() (§23)
tests/assertions.py                           ← assert_weight, assert_overload_triggered... (§24)
tests/actuator_client.py                      ← TCP client para ESP32 actuador ← NUEVO
tests/hid_client.py                           ← TCP client para ESP32 HID ← NUEVO
tests/poll_utils.py                           ← poll_until_stable() (§6.5) ← NUEVO
tests/conftest.py                             ← fixtures pytest: api/actuator/hid/profile ← NUEVO
tests/test_tare_product.py                    ← prototipo: tara + peso producto — F2 cancela tara (corregido)
scripts/prueba_manual.py                      ← guía interactiva: misma lógica, pesas a mano ← NUEVO
scripts/prueba_manual_venta.py                ← guía venta: PLU + peso + ENTER×3 + verifica BD ← NUEVO
tests/db_client.py                            ← BalanzaDB: queries SSH→psql a PostgreSQL ← NUEVO
tests/hid_client.py                           ← agregado hid.enter() para confirmar venta
requirements.txt                              ← dependencias Python del proyecto ← NUEVO
config/hardware_params.yaml                   ← parámetros físicos + metrología AR/BR/US (§16 + §22.3)
.env.test.example                             ← plantilla — NEO_ESP32_IP único (un solo ESP32)

firmware/esp32/platformio.ini                 ← FIRMWARE ACTIVO — PlatformIO ESP32-S3 ← NUEVO
firmware/esp32/include/config.h               ← pines y constantes (igual que actuator/)
firmware/esp32/src/main.cpp                   ← HID + Actuador fusionados ← NUEVO
                                                 Comandos: SET_WEIGHT/HOME/ZERO/STATUS/SET_CALIBRATION/KEY_PRESS

firmware/actuator/                            ← REFERENCIA HISTÓRICA — no flashear
firmware/actuator-electroiman/                ← DESCARTADO — no flashear
firmware/hid/hid.ino                          ← REFERENCIA HISTÓRICA — no flashear

assets/puente-portal-actuador.svg             ← plano del puente portal (T_BANDEJA=162mm)
assets/pesas.jpeg                             ← foto inventario pesas DOLZ disponibles

docs/API-Cuora-NEO.docx
docs/CUORA-NEO-manual.pdf
docs/ESP32-DevKitC.docx
docs/PM-objetivos.xlsx                        ← objetivos DB-4.x del PM
docs/informes/                                ← informes de avance generados
docs/analysis/analisis-impacto-electroiman.md ← análisis descartado (referencia)
```

---

## Tracking PM — Objetivos DB-4.x

| ID | Deliverable | Fecha límite | Estado real | Notas |
|---|---|---|---|---|
| DB-4.1 | Diseño de arquitectura HW/SW con I+D | 28/06/26 | ✅ Completo | Finalizado antes de fecha |
| DB-4.2 | Módulo funcional teclado | 22/06/26 | ✅ Completo | ESP32 HID validado end-to-end 13/05/26 — firmware unificado flasheado y probado |
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

### SSH a la balanza — confirmado 2026-05-13

- **Usuario:** `root` (no `systel`)
- **Key:** `~/.ssh/cuora_neo` (ya instalada en la balanza)
- **Comando:** `ssh -i ~/.ssh/cuora_neo root@192.168.100.123`

### Flujo de venta CUORA NEO — confirmado 2026-05-13

```
1. Seleccionar PLU (touchscreen o teclado → número → F3)
2. Colocar peso en bandeja (esperar ESTABLE)
3. ENTER → agrega ítem al ticket (pueden agregarse varios productos)
4. ENTER → abre pantalla de resumen del ticket
5. ENTER → imprime ticket y cierra → crea invoice en BD
```

**BD:** `public.invoice` + `public.invoiceline` — confirmado con PLU 57, 0.200 kg, $6.98.
**Credenciales BD:** `systel / Systel#4316` vía SSH root@192.168.100.123 → psql.
**DB client:** `tests/db_client.py` → `BalanzaDB.latest_sale()`, `invoice_count()`.

### Comportamiento de TARA/CERO — confirmado 2026-05-13

| Tecla | Función real en CUORA NEO |
|---|---|
| F2 (TARA) con peso en bandeja | Aplica tara — display pasa a 0g |
| F2 (TARA) con bandeja vacía + tara activa | **Cancela la tara** — display vuelve a 0g |
| F4 (CERO) | Corrección de cero dentro del rango permitido — **NO cancela tara** |

Para limpiar el estado al final del test: retirar pesas → F2 (no F4).
`test_tare_product.py` y `prueba_manual.py` ya correguidos con este comportamiento.

### Firmware ESP32 unificado — validación completa 2026-05-13

1. Flash: `pio run --target upload` desde `firmware/esp32/` → OK
2. Serial Monitor confirma: `WiFi OK → TCP :9999 → USB HID keyboard ready`
3. `lsusb` desde la balanza: `Bus 001 Device 003: ID 303a:1001` — ESP32 detectado
4. `dmesg`: `hid-generic: USB HID v1.11 Keyboard` — kernel registró como teclado (event9)
5. `python scripts/validar_esp32.py` → 4/4 tests pasaron
6. Evento `EV_KEY KEY_F4` confirmado en `/dev/input/event9` → balanza corrigió peso a 0

**Nota importante sobre el primer boot:** El primer `KEY_PRESS` después del flash puede fallar con
`SendReport(): report 1 wait failed` — condición de carrera única en el arranque inicial.
En el segundo intento (o tras ~30s de conexión estable) funciona correctamente. No requiere fix.

---

## Lo próximo a hacer (en orden)

### SIN PORTAL — disponible ahora

| Tarea | Script / herramienta | Prerequisito |
|---|---|---|
| ~~Tests de API pura (ping, weight, signature)~~ | `test_api_connectivity.py` | ✅ 11/11 tests 2026-05-14 |
| ~~ABM de PLUs via API~~ | `test_plu_abm.py` | ✅ 19 passed + 1 xpassed 2026-05-14 |
| ~~Tests de autenticación / roles~~ | `test_auth.py` | ✅ 11 passed + 4 skip vendor 2026-05-14 |
| ~~Tests de encoding UTF-8~~ | `test_encoding.py` | ✅ 13/13 tests 2026-05-14 |
| ~~Tests de integridad API↔DB~~ | `test_integrity.py` | ✅ 20/20 tests 2026-05-14 |
| ~~Prueba tara + producto~~ | `prueba_manual.py` | ✅ hecho |
| ~~Prueba venta + ticket en BD~~ | `prueba_manual_venta.py` | ✅ hecho |
| ~~Flashear firmware ESP32~~ | — | ✅ hecho |
| ~~Prueba impresión de etiquetas~~ | `prueba_manual_etiqueta.py` | ✅ hecho |

### CON PORTAL (bloqueante para pesaje automatizado)

1. **Construir portal físico** — enviar `assets/puente-portal-actuador.svg` al herrero
   - Puente telescópico 380–560mm, carro Ø8mm, husillo M8, NEMA17 + DRV8825
   - Ver lista de materiales en §5 y §11 del plan

2. **Sprint 0 — curva de estabilización** (1–2 días con hardware)
   ```bash
   python scripts/sprint0_estabilizacion.py
   # → calibra max_wait_s y stable_reads en config/hardware_params.yaml
   ```

3. **pytest completo con hardware**
   ```bash
   pytest tests/test_tare_product.py -v
   ```

### Completar `.env.test` (copiar de `.env.test.example`)

Todo confirmado — copiar y usar directamente:
```bash
cp .env.test.example .env.test
# SSH: root@192.168.100.123, key ~/.ssh/cuora_neo
# DB: systel / Systel#4316
# ESP32: 192.168.100.202:9999
```

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
✅ Creados (2026-05-08 al 2026-05-14):
  tests/__init__.py
  tests/errors.py
  tests/api_client.py                              ← fix: coma decimal en weight, ping string
  tests/metrology.py
  tests/assertions.py
  tests/actuator_client.py                         ← TCP client para ESP32 actuador
  tests/hid_client.py                              ← TCP client para ESP32 HID
  tests/poll_utils.py                              ← poll_until_stable() (§6.5)
  tests/db_client.py                              ← BalanzaDB: queries SSH→psql a PostgreSQL
  tests/conftest.py                                ← fixtures: api/actuator/hid/profile/db/creds
  tests/test_tare_product.py                       ← prototipo tara+producto (requiere portal)
  tests/test_api_connectivity.py                  ← 11 tests API pura: ping/weight/signature
  tests/test_plu_abm.py                           ← 20 tests create/load/price/delete PLU
  tests/test_auth.py                              ← 15 tests auth D1-D5 (roles, 401, 403)
  tests/test_encoding.py                          ← 13 tests UTF-8: ñ tildes ° ASCII límite
  tests/test_integrity.py                         ← 20 tests integridad API↔DB (campos, precios, advertising)
  pytest.ini                                      ← markers: portal, esp32
  scripts/prueba_manual_etiqueta.py               ← guía etiqueta: PLU+peso+ENTER directo
  config/hardware_params.yaml
  .env.test.example                               ← NEO_ESP32_IP único (un solo ESP32)
  assets/puente-portal-actuador.svg               ← plano portal T_BANDEJA=162mm
  firmware/esp32/platformio.ini                   ← FIRMWARE ACTIVO (HID + Actuador)
  firmware/esp32/include/config.h                 ← pines y constantes
  firmware/esp32/src/main.cpp                     ← listo para flashear ✅
  firmware/actuator/                              ← REFERENCIA HISTÓRICA (no flashear)
  firmware/actuator-electroiman/                  ← DESCARTADO (no flashear)
  firmware/hid/hid.ino                            ← REFERENCIA HISTÓRICA (no flashear)
  docs/analysis/analisis-impacto-electroiman.md   ← análisis descartado (referencia)

❌ Pendientes — crear en este orden:
  scripts/sprint0_estabilizacion.py    ← §4 Fase 0 (requiere hardware)
  scripts/calibracion_bandeja.py       ← §6.2 (requiere hardware)

  Fase 1 (Cypress API) — NO requiere portal:
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
| `firmware/esp32/` es el firmware activo | HID + Actuador fusionados en un solo ESP32-S3. No modificar `firmware/actuator/` ni `firmware/hid/` |
| `firmware/actuator-electroiman/` está descartado | Diseño de electroimán descartado 2026-05-13. Mantener solo como documentación |
| SVG del portal listo para el herrero tal como está | Diseño B (electroimán) descartado — sin rack de pesas, sin cambios al SVG |
| `poll_until_stable()` usa `abs(expected_kg)` para tolerancia | Permite manejar lecturas negativas (ej. tara activa sin peso) — no cambiar |

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
