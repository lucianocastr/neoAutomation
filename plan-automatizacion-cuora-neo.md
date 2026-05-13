# Plan de Automatización — Suite de Pruebas CUORA NEO
### Systel · I+D · Revisión 2.0 · 2026-05-07

---

## Resumen ejecutivo

Este documento define la arquitectura, fases de implementación y procedimientos de calibración para la suite de pruebas automatizadas de la balanza electrónica **CUORA NEO de Systel**.

El objetivo es cubrir los cuatro dominios de validación obligatorios — **Conectividad, Pesaje, Ventas y ABM** — mediante una arquitectura de dos suites complementarias, aprovechando la experiencia del equipo en Cypress y la API REST nativa del equipo.

El proyecto se estructura en **5 fases**. La Fase 0 valida el flujo completo de automatización usando el POC existente (ESP32 + servo), permitiendo presentar un **MVP funcional antes de invertir en hardware de producción**.

---

## 1. Objetivo y alcance

### Dominios mínimos a cubrir

| Dominio | Qué se prueba |
|---------|---------------|
| **Conectividad** | Ethernet/WiFi, SSH, API REST, panel web, VNC, FTP |
| **Pesaje** | Tara directa/acumulativa, ajuste de cero, lectura estable, sobrecarga |
| **Ventas** | Venta pesable, unitaria, escurrida, ticket, etiqueta, pre-empaque |
| **ABM** | Alta/baja/modificación de PLUs, listas de precios, usuarios, departamentos |

### Capas de validación obligatorias

| Capa | Herramienta | Qué verifica |
|------|-------------|--------------|
| **UI Web** | Cypress E2E | Panel web: login, ABM, reportes, configuración |
| **API REST** | Cypress + cy.request | Endpoints: ping, weight, plu/create, plu/load |
| **UI Táctil** | pytest + VNC (view-only) | Pantalla física de la balanza vía VNC |
| **Datos** | pytest + PostgreSQL vía SSH | Persistencia después de cada operación crítica |
| **Conectividad** | Cypress + pytest | Disponibilidad de cada interfaz |

---

## 2. Interfaces disponibles en el dispositivo

| Interfaz | Puerto | Uso en la suite |
|----------|--------|-----------------|
| API REST | **7376** | Control programático, peso en tiempo real, ABM vía código |
| Panel web | 80 | E2E de configuración, reportes y ABM |
| SSH | 22 | Salud del sistema, acceso a PostgreSQL, lectura de logs |
| VNC | 5900 | Vista (solo lectura) de la pantalla táctil |
| FTP | 21 | Importación masiva de datos (formato Systel/MGV) |
| USB Host | — | Teclado físico vía pynput (HID directo, sin foco de ventana) |

---

## 3. Arquitectura técnica

### 3.1 Decisión arquitectural: Cypress-first + Python para SSH/VNC

Cypress cubre **API REST y Web E2E** en un solo runner con la sintaxis que el equipo ya conoce. Python + pytest se reserva exclusivamente para lo que Cypress no maneja: SSH, PostgreSQL y pantalla VNC.

```
┌─────────────────────────────────────────────────────────┐
│  SUITE 1 — Cypress (JavaScript)                         │
│  cypress/e2e/api/                                       │
│    connectivity.cy.js  ← GET /api/ping, /api/signature  │
│    pesaje.cy.js        ← GET /api/weight (sensor real)  │
│    abm.cy.js           ← POST /api/plu/create           │
│    ventas.cy.js        ← plu/load → weight → product    │
│  cypress/e2e/web/                                       │
│    login.cy.js · abm_plu.cy.js · reports.cy.js          │
│    price_lists.cy.js · config.cy.js                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  SUITE 2 — pytest + Python                              │
│  tests/ssh/                                             │
│    test_system_health.py · test_db_state.py             │
│    test_backup_restore.py · test_ftp_import.py          │
│  tests/vnc/pesaje/                                      │
│    test_tara_directa.py · test_tara_acumulativa.py      │
│    test_ajuste_cero.py                                  │
│  tests/vnc/ventas/                                      │
│    test_venta_pesable.py · test_venta_escurrida.py      │
│    test_preempaque.py                                   │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Por qué la API REST es el diferencial clave

La API (puerto 7376) permite automatizar escenarios que sin ella requerirían VNC frágil:

| Endpoint | Cobertura |
|----------|-----------|
| `GET /api/ping` | Health check sin latencia |
| `GET /api/signature` | Versión, MACs, señal WiFi dBm |
| `GET /api/weight` | Peso del sensor **en tiempo real** |
| `GET /api/product` | PLU cargado en pantalla |
| `POST /api/plu/load` | Cargar PLU sin tocar la pantalla |
| `POST /api/plu/create` | Crear/actualizar PLU con todos sus atributos |

El flujo `POST /api/plu/load` → colocar peso → `GET /api/weight` valida pesaje usando el **sensor físico real**, sin depender de VNC para leer el valor en pantalla.

### 3.3 Stack tecnológico

| Herramienta | Suite | Rol |
|-------------|-------|-----|
| Cypress 13 | JS | API + Web E2E; cy.request nativo |
| paramiko | Python | SSH + SCP + túnel TCP a PostgreSQL |
| psycopg2 | Python | Cliente PostgreSQL vía túnel SSH |
| vncdotool | Python | Protocolo RFB: screenshot en view-only |
| OpenCV + Pillow | Python | Detección de estado de pantalla (ORB matching) |
| pytesseract | Python | OCR de valores numéricos en VNC (fallback) |
| pynput | Python | USB HID directo → teclado físico de la balanza |
| pytest | Python | Runner + markers por capa (ssh/vnc/hardware) |
| python-dotenv | ambas | Variables de entorno por ambiente |

### 3.4 Cobertura por herramienta

| Dominio | API Cypress | Web Cypress | SSH pytest | VNC pytest |
|---------|:-----------:|:-----------:|:-----------:|:----------:|
| Conectividad | ✓ ping, sig. | ✓ login | ✓ health | — |
| Pesaje | ✓ /weight | — | — | ✓ tara, cero |
| Ventas | ✓ plu/load | ✓ reportes | ✓ DB | ✓ ticket |
| ABM | ✓ plu/create | ✓ CRUD | ✓ verificar | — |

### 3.5 Source of truth por dominio (regla arquitectónica)

| Dominio | Fuente primaria | Fuente de verificación |
|---------|----------------|------------------------|
| Peso actual | `GET /api/weight` | VNC display (solo fallback cualitativo) |
| PLU en pantalla | `GET /api/product` | VNC (estado cualitativo: ¿hay un PLU mostrado?) |
| Persistencia de datos | PostgreSQL vía SSH | No duplicar con API |
| Estado de pantalla | VNC — OpenCV | API (¿PLU=0?, ¿weight=0?) como verificación cruzada |
| Conectividad | Respuesta HTTP < umbral | SSH uptime |

> **Regla no negociable:** Los valores numéricos (peso, precio, código PLU) se leen **siempre** de la API. VNC solo verifica estado cualitativo: ¿estoy en la pantalla correcta?, ¿hay un diálogo de error abierto?
>
> Esta regla previene que se lea el peso "del display VNC porque es más fácil de debuguear" — esa práctica introduce fragilidad por compresión JPEG y cambios de layout en futuras versiones de firmware.

### 3.6 Interfaces y herramientas por responsabilidad

La balanza expone tres interfaces completamente independientes:

| Interfaz | Herramienta | Rol en la suite |
|----------|-------------|-----------------|
| Java app (pantalla táctil) | VNC view-only + pynput USB HID | Observar estado + inyectar teclas físicas |
| Panel web `:80` | Cypress E2E (browser) | CRUD completo, reportes, configuración |
| REST API `:7376` | Cypress `cy.request` | Peso en tiempo real, ABM vía código, ping |
| PostgreSQL vía SSH | pytest + psycopg2 | Verificación de persistencia post-operación |

> Cypress nunca toca la Java app. pynput nunca toca el panel web. Estas capas son ortogonales — no hay solapamiento ni conflicto.

---

## 4. Fases del proyecto

### Fase 0 — MVP: Validación del flujo con POC existente

> **Objetivo:** Demostrar que el flujo completo de automatización funciona de punta a punta usando el ESP32 + servo del POC, antes de construir hardware de producción.

**Duración estimada:** 3–5 días  
**Prerequisito de hardware:** Solo el ESP32 + servo + cualquier objeto para poner en la bandeja

#### ¿Qué valida el POC?

| Componente del flujo | ¿Valida? | Nota |
|----------------------|:--------:|------|
| Cypress: GET /api/ping, /api/weight | ✓ | Sin actuador |
| Cypress: POST /api/plu/load | ✓ | Sin actuador |
| pytest: SSH uptime + DB query | ✓ | Sin actuador |
| VNC: screenshot + OpenCV estado | ✓ | Ya validado en el POC |
| pynput: teclas USB HID → balanza | ✓ | Sin actuador |
| `poll_until_stable()` con vibración real | ✓ | Peor caso (servo vibra más que stepper) |
| `clean_state` fixture — aislamiento | ✓ | Concepto completo |
| Flujo end-to-end: actuador→API→VNC→DB | ✓ | Con 1 peso fijo |
| Múltiples valores de peso | ✗ | Requiere hardware final |

#### Adaptador POC (sin cambiar los tests)

```python
# conftest.py — interfaz unificada para ambos actuadores
class WeightActuatorPOC:
    def set(self, grams):      # ignora grams, simplemente baja
        requests.post(f"http://{ESP32_IP}/bajar")
    def zero(self):
        requests.post(f"http://{ESP32_IP}/subir")

class WeightActuatorFinal:    # mismo contrato, firmware del stepper
    def set(self, grams):
        requests.post(f"http://{ESP32_IP}/weight/set", json={"grams": grams})
    def zero(self):
        requests.post(f"http://{ESP32_IP}/weight/zero")

# Un flag en .env determina cuál usar:
# ACTUATOR_MODE=poc | final
```

Los tests nunca saben qué actuador está abajo. El reemplazo es un cambio de una línea.

#### Medición crítica del Sprint 0: tiempo de estabilización

Antes de escribir un solo test de pesaje, hay que medir cuánto tarda el sensor en estabilizarse después de que el servo mueve. Este dato define el parámetro `max_wait` de `poll_until_stable()`.

```python
# script: sprint0_estabilizacion.py
import requests, time, csv

def medir_estabilizacion(ip, muestras=50, intervalo=0.2):
    resultados = []
    # 1. Activar el actuador (bajar)
    requests.post(f"http://{ESP32_IP}/bajar")
    t0 = time.time()
    # 2. Muestrear GET /api/weight cada 200ms durante 10s
    for _ in range(muestras):
        r = requests.get(f"http://{ip}:7376/api/weight")
        peso = float(r.json()["weight"])
        resultados.append((round(time.time() - t0, 2), peso))
        time.sleep(intervalo)
    # 3. Guardar CSV para graficar
    with open("estabilizacion.csv", "w", newline="") as f:
        csv.writer(f).writerows([["t_seg", "peso_kg"]] + resultados)
    return resultados
```

Graficar el CSV. El tiempo en que la deriva queda bajo ±1g define `stable_reads` y `max_wait`.

#### Entregable del MVP

Al finalizar la Fase 0, se puede ejecutar:

```bash
# Test de conectividad — sin actuador
npx cypress run --spec "cypress/e2e/api/connectivity.cy.js"

# Flujo completo con POC
pytest tests/vnc/ventas/test_venta_pesable.py -s --actuator=poc
```

Y presentar pantalla + log mostrando: **actuador coloca peso → API lee → VNC verifica → DB confirma**.

#### Checklist de prerrequisitos — completar antes de Sprint 1

- [ ] Balanza encendida y accesible en la red (`ping NEO_IP`)
- [ ] `GET http://NEO_IP:7376/api/ping` responde `{"status":"pong"}` desde el PC de tests
- [ ] Panel web `http://NEO_IP:80` cargable en Chrome desde el PC de tests
- [ ] Credenciales SSH verificadas manualmente: `ssh NEO_SSH_USER@NEO_SSH_HOST`
- [ ] VNC accesible: `vncviewer NEO_VNC_HOST:5900` conecta y muestra pantalla
- [ ] ESP32 del POC online y respondiendo: `POST http://ESP32_IP/bajar` y `/subir`
- [ ] `.env.test` creado desde `.env.test.example` con todos los valores reales
- [ ] Sprint 0 ejecutado: curva de estabilización medida, `max_wait` y `stable_reads` definidos
- [ ] Firmware version del dispositivo identificada: `GET /api/signature → version`
- [ ] `SUPPORTED_FIRMWARE` en `conftest.py` actualizado con la versión actual

---

### Fase 1 — Suite Cypress: API REST

**Duración:** 1 semana  
**Prerequisito:** Balanza en red, IP configurada en `.env.test`

#### Archivos a crear

| Archivo | Contenido |
|---------|-----------|
| `cypress/package.json` | deps: cypress 13, dotenv |
| `cypress/cypress.config.js` | baseUrl API/web, env vars, timeouts |
| `cypress/support/commands.js` | `cy.loadPlu()`, `cy.createPlu()`, `cy.getWeight()` |
| `cypress/e2e/api/connectivity.cy.js` | GET /ping, /signature (MACs, WiFi dBm, versión) |
| `cypress/e2e/api/abm.cy.js` | POST /plu/create: 3 formatos, errores 400/401/409 |
| `cypress/e2e/api/pesaje.cy.js` | GET /weight: formato, rango, 503 cuando inactiva |
| `cypress/e2e/api/ventas.cy.js` | plu/load → product check → weight check |
| `.env.test.example` | Plantilla de todas las variables |

#### SLAs de conectividad (umbrales de los tests)

| Endpoint | Umbral máximo |
|----------|---------------|
| `GET /api/ping` | < 200 ms |
| SSH `uptime` | < 3 s |
| VNC handshake | < 5 s |

#### Validación de schema de API (`assertApiSchema`)

Toda respuesta de la API debe validarse contra un schema mínimo. Esto detecta cambios de contrato por actualizaciones de firmware antes de que los tests fallen con errores crípticos.

```javascript
// cypress/support/commands.js
const API_SCHEMAS = {
  weight:    { weight: "string", unit: "string" },
  ping:      { status: "string" },
  signature: { version: "string", mac: "string" },
  product:   { plu: "number" },
};

Cypress.Commands.add("assertApiSchema", (endpoint, body) => {
  const schema = API_SCHEMAS[endpoint];
  if (!schema) return;
  Object.entries(schema).forEach(([key, type]) => {
    expect(body, `response debe tener campo '${key}'`).to.have.property(key);
    expect(typeof body[key], `campo '${key}' debe ser ${type}`).to.equal(type);
  });
});

// Uso en tests:
// cy.getWeight().then(body => cy.assertApiSchema("weight", body))
```

---

### Fase 2 — Suite Cypress: Web E2E

**Duración:** 1 semana

| Archivo | Escenarios |
|---------|------------|
| `login.cy.js` | Roles: Admin, Vendedor, Consulta; acceso denegado |
| `abm_plu.cy.js` | CRUD completo, 6 solapas, tabla nutricional |
| `price_lists.cy.js` | Crear, vigencia desde/hasta, precio por lista |
| `reports.cy.js` | Filtros por fecha, PLU, vendedor; cierre de ventas |
| `config.cy.js` | Red, fecha/hora, backup, restore, valores fábrica |

#### Aislamiento de datos — namespace de test-data

Los tests web crean PLUs, usuarios y configuraciones. Sin aislamiento, el estado se acumula entre ejecuciones y el orden de los tests importa. Regla: todos los datos creados por tests usan el rango `90000–99999` para PLUs y prefijo `TEST_` para nombres.

```javascript
// cypress/support/e2e.js
const TEST_PLU_RANGE_START = 90000;

afterEach(() => {
  // Limpiar PLUs de test creados en la ejecución
  // Si la API tiene DELETE por rango:
  cy.request({ method: "DELETE", url: "/api/plu/range",
    body: { from: 90000, to: 99999 }, failOnStatusCode: false });
  // Si no, omitir — y limpiar manualmente antes de cada sesión
});
```

> **Nota:** Verificar antes de implementar si el panel web o la API exponen un endpoint de DELETE masivo. Si no existe, usar cleanup individual en los `after()` de cada test que crea datos.

---

### Fase 3 — Suite pytest: SSH + PostgreSQL

**Duración:** 1 semana  
**Dependencia adicional:** `pip install sshtunnel` — agregar a `requirements.txt`

> ⚠️ **RESTRICCIÓN CRÍTICA — SO con customizaciones Systel:**
> El sistema operativo de la balanza tiene modificaciones específicas del fabricante.
> **Está estrictamente prohibido ejecutar `apt update`, `apt upgrade`, `apt-get install`
> o cualquier comando que modifique paquetes del sistema.**
> Todos los tests SSH deben ser de solo lectura sobre el SO.
> Las actualizaciones del device solo pueden realizarse a través de firmware oficial de Systel
> o con intervención de un ATAS (Agente Técnico Autorizado Systel).

| Archivo | Qué verifica | Tipo de acceso |
|---------|--------------|----------------|
| `test_system_health.py` | uptime, disco, memoria, procesos activos | Solo lectura |
| `test_db_state.py` | PLUs y ventas en PostgreSQL vía túnel SSH | Solo lectura (SELECT) |
| `test_backup_restore.py` | backup → restore → verificar integridad | Operación de app (no SO) |
| `test_ftp_import.py` | SCP + trigger import + verificar en DB | Escritura de datos, no del SO |

#### Comandos SSH permitidos (solo lectura del SO)

```bash
# ✓ Permitidos — no modifican el sistema
uptime
df -h
free -m
ps aux | grep cuora
cat /var/log/cuora/app.log | tail -50
systemctl status cuora

# ✗ PROHIBIDOS — modifican paquetes del SO
apt update
apt upgrade
apt-get install <paquete>
pip install <paquete>   # en el device (en el PC de tests: sí está permitido)
```

#### Fixture SSH + túnel PostgreSQL (correcto)

> **Nota de corrección:** La implementación anterior usaba `psycopg2.extras.LoopbackConnection` que no es la API para tunneling y falla en ejecución. La implementación correcta usa `sshtunnel`:

```python
from sshtunnel import SSHTunnelForwarder
import psycopg2, os

@pytest.fixture(scope="session")
def db_conn():
    tunnel = SSHTunnelForwarder(
        os.environ["NEO_SSH_HOST"],
        ssh_username=os.environ["NEO_SSH_USER"],
        # Soporta key o password — el device puede no tener key auth por defecto
        ssh_pkey=os.environ.get("NEO_SSH_KEY_PATH") or None,
        ssh_password=os.environ.get("NEO_SSH_PASS") or None,
        remote_bind_address=("127.0.0.1", 5432),
    )
    tunnel.start()
    conn = psycopg2.connect(
        host="127.0.0.1",
        port=tunnel.local_bind_port,
        dbname=os.environ["NEO_DB_NAME"],
        user=os.environ["NEO_DB_USER"],
        password=os.environ.get("NEO_DB_PASS", ""),
    )
    yield conn
    conn.close()
    tunnel.stop()
```

> Verificar credenciales SSH manualmente (`ssh user@host`) antes de ejecutar los tests. El device puede requerir password en lugar de key.

---

### Fase 4 — Hardware completo: puente portal + NEMA 17

**Duración:** 2 semanas (1 fabricación + 1 integración)  
**Prerequisito:** Medidas del equipo físico, hardware construido y calibrado

#### Integración del actuador final

```python
# Misma interfaz del POC, nuevo firmware — un flag en .env cambia el adaptador
@pytest.fixture(scope="session")
def weight_actuator():
    mode = os.environ.get("ACTUATOR_MODE", "poc")
    if mode == "final":
        return WeightActuatorFinal(ip=os.environ["NEO_ESP32_IP"])
    return WeightActuatorPOC(ip=os.environ["NEO_ESP32_IP"])
```

#### Estado READY — definición formal

Antes y después de cada test, la balanza debe estar en estado READY. Esto se verifica mediante `clean_state` (ver Sección 8) con los siguientes criterios:

```python
# tests/vnc/pages/device_state.py
from dataclasses import dataclass

@dataclass
class DeviceReadyState:
    weight_kg: float     # debe ser < 0.003 (menos de 3g — tolerancia de celda)
    tare_active: bool    # debe ser False
    plu_loaded: int      # debe ser 0 (ningún PLU activo)
    screen_id: str       # debe ser "main_screen"

    def is_ready(self) -> bool:
        return (
            self.weight_kg < 0.003
            and not self.tare_active
            and self.plu_loaded == 0
            and self.screen_id == "main_screen"
        )
```

#### Inyección de teclas con verificación — press_and_verify

pynput envía teclas al foco activo en el PC. Si otro proceso tiene el foco (terminal, Cypress), las teclas van al lugar equivocado sin error visible. Usar siempre `press_and_verify` en lugar de `keyboard.press` directo:

```python
# tests/vnc/pages/vnc_base.py
def press_and_verify(keyboard, key, verify_fn, description="", timeout=2.0):
    """
    Envía una tecla y verifica que el estado del dispositivo cambió.
    Si verify_fn() no retorna True en timeout segundos, lanza AssertionError.
    """
    keyboard.press(key)
    keyboard.release(key)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if verify_fn():
            return
        time.sleep(0.2)
    raise AssertionError(
        f"Tecla '{key}' enviada ({description}) pero el estado no cambió en {timeout}s. "
        "¿El foco en el PC está en otro proceso?"
    )

# Ejemplo de uso:
press_and_verify(
    keyboard, Key.f1,   # tecla TARA
    verify_fn=lambda: float(api_client.get("/api/weight").json().get("tare", 0)) > 0,
    description="TARA",
)
```

#### Calibración de pesas — 15 combinaciones completas

```python
# tests/conftest.py
CALIBRATED_WEIGHTS_G = [
    200, 500, 700, 1000, 1200, 1500, 1700,
    2000, 2200, 2500, 2700, 3000, 3200, 3500, 3700
]

@pytest.fixture(scope="session")
def weight_calibration(weight_actuator, api_client, metrology):
    """
    Mide el peso real de las 15 combinaciones posibles con las pesas DOLZ.
    Los tests usan cal["700"] en lugar del valor nominal 700.
    Tiempo estimado: ~7-8 minutos por sesión.
    """
    cal = {}
    for nominal_g in CALIBRATED_WEIGHTS_G:
        weight_actuator.set(nominal_g)
        measured = poll_until_stable(
            api_client, metrology, expected_weight_kg=nominal_g / 1000
        )
        cal[str(nominal_g)] = measured
        weight_actuator.zero()
        poll_until_stable(api_client, metrology, expected_weight_kg=0.0, tolerance_g=2, max_wait_s=4)
    return cal
# Tests usan siempre: cal["700"], cal["1500"] — nunca el valor nominal directo
```

#### Verificación de deriva de calibración (por sesión)

```python
@pytest.fixture(scope="session", autouse=True)
def verify_tray_calibration(weight_actuator, api_client, metrology):
    """Detecta si el actuador derivó desde la última calibración mecánica."""
    weight_actuator.set(200)
    w = poll_until_stable(api_client, metrology, expected_weight_kg=0.200, tolerance_g=2, max_wait_s=6)
    weight_actuator.zero()
    assert 0.150 < w < 0.250, (
        f"Calibración derivada: nominal 200g, medido {w*1000:.0f}g. "
        "Ejecutar calibracion_bandeja.py para recalibrar."
    )
```

#### Tests habilitados en Fase 4 (no posibles con POC)

- `test_tara_directa.py` — envase (200g) + TARA + producto (500g) = neto 500g
- `test_tara_acumulativa.py` — taras sucesivas
- `test_ajuste_cero.py` — deriva + CERO (límite ±3% capacidad)
- `test_sobrecarga.py` — colocar >6 kg → verificar error de sobrecarga vía API
- `test_preempaque.py` — serie automática de etiquetas

---

## 5. Hardware — Puente portal actuador de peso

### 5.1 Diseño general

El actuador utiliza un **puente portal** que **estriba sobre la balanza**, con el motor y el mecanismo de descenso en el travesaño superior. El pin desciende verticalmente sobre el centro de la bandeja.

```
         [NEMA 17 en centro del travesaño]
         │
─────────┴──────────────────────────────────  travesaño 500mm
│   [CARRO — guías Ø8mm — lead screw M8]   │
│         ↕ viaje 280mm                    │
│    [MANGA Ø13mm → PIN FLOTANTE Ø10mm]    │
│         [PESAS DOLZ apiladas]            │
│              │                           │
│   ══════════════════════════════         │  ← bandeja ~130mm
│   [       BALANZA CUORA NEO      ]       │
│                  [MÁSTIL trasero]        │  ← libre, sin conflicto
│                  500mm ↑                 │
pata izq                               pata der
 TABLE                                   TABLE
   ←──────────── 500mm exterior ──────────→
         (balance 390mm + 55mm c/lado)
```

#### Ventajas del puente vs. riel lateral

| Aspecto | Puente portal |
|---------|---------------|
| Brazo en voladizo | Eliminado — pin baja vertical |
| Análisis de sección del brazo | No aplica |
| Estabilidad | Simétrica (dos patas) |
| Posición sobre la bandeja | Centro geométrico exacto |
| Conflicto con mástil | Ninguno (mástil trasero, patas laterales) |

### 5.2 Dimensiones

| Elemento | Valor |
|----------|-------|
| Ancho exterior del puente | 500 mm |
| Alto total (patas + travesaño) | 460 mm |
| Sección: patas y travesaño | Tubo cuadrado 25×25 mm S235 |
| Separación guías Ø8mm | 80 mm (centradas sobre bandeja) |
| Recorrido del carro | 280 mm |
| Carro | 80 × 60 × 5 mm (sin brazo) |
| Manga del pin | Ø13 mm int., 30 mm largo |
| Pin con collarines | Ø10 mm, 160 mm total |
| Almohadillas de goma AV | 4 × (10×10×5 mm), una por extremo de pata |

> ⚠ **Medir antes de cortar metal:** la altura real de la superficie de la bandeja desde la mesa determina el largo de las patas y la posición del home switch.

### 5.3 Motor y capacidad

| Parámetro | Valor |
|-----------|-------|
| Motor | NEMA 17, 40 Ncm, 1.8°/paso |
| Driver | DRV8825 (microstepping 1/32) |
| Lead screw | Varilla M8 roscada, paso 1.25 mm |
| Fuerza axial práctica | 35–50 kg |
| Carga real máxima | 4.2 kg (pesas 3.7 kg + carro 0.5 kg) |
| Margen de seguridad del motor | **8× – 12×** |
| Propiedad de seguridad | Rosca M8 autobloqueante — carro no cae sin corriente |

### 5.4 Pin Ø10 mm — análisis estructural

```
Carga dinámica de diseño (×2.5): 92 N
Brazo de momento (pesas al empotramiento): 60 mm
M = 5,520 Nmm  |  Z (Ø10) = 98.2 mm³  |  σ = 56 MPa
Límite S235 = 235 MPa  →  Factor seguridad = 4.2 ✓
```

No reducir a Ø8 mm.

---

## 6. Nivelación y calibración del sistema

> Esta sección describe los tres niveles de calibración necesarios antes de ejecutar cualquier test de pesaje.

### 6.1 Calibración de altura — Nivel 1: ajuste mecánico

**Quién:** Técnico de laboratorio  
**Cuándo:** Instalación inicial y cada vez que se reposiciona el equipo  
**Herramienta:** Llave de tuercas, nivel de burbuja

El carro tiene **ranuras verticales** (en vez de agujeros) para la fijación del pin. Esto da ±15 mm de ajuste sin modificar la estructura:

```
Procedimiento:
1. Colocar el puente portal sobre la mesa, flanqueando la balanza.
2. Encender balanza, esperar estado LISTO (pantalla principal).
3. Conectar ESP32 y ejecutar: POST /weight/zero  → carro al home (limit switch).
4. Bajar el carro manualmente (modo jog) hasta que el pin roce la bandeja.
5. Aflojar los 2 tornillos M6 del pin en el carro.
6. Ajustar la altura del pin hasta que toque la bandeja sin doblarla.
7. Verificar nivel horizontal con burbuja. Apretar tornillos. Listo.
```

### 6.2 Calibración de altura — Nivel 2: parámetro de software

**Quién:** Script de calibración automática  
**Cuándo:** Primera puesta en marcha y tras cualquier reajuste mecánico  
**Efecto:** Guarda `tray_contact_steps` en EEPROM del ESP32

```python
# calibracion_bandeja.py
def calibrar_contacto(api_url, esp_ip, umbral_g=30, velocidad_creep=80):
    """
    Baja el carro lentamente hasta detectar peso en la bandeja.
    Guarda el número de pasos en la EEPROM del ESP32.
    """
    requests.post(f"http://{esp_ip}/weight/home")   # ir al home (limit switch)
    time.sleep(2)
    
    pasos = 0
    while True:
        requests.post(f"http://{esp_ip}/weight/step", json={"steps": 10, "speed": velocidad_creep})
        pasos += 10
        peso = float(requests.get(f"{api_url}/api/weight").json()["weight"]) * 1000  # a gramos
        if peso > umbral_g:
            requests.post(f"http://{esp_ip}/weight/save_tray", json={"steps": pasos})
            print(f"Contacto detectado en {pasos} pasos. Guardado en EEPROM.")
            return pasos
        if pasos > 50000:
            raise RuntimeError("No se detectó contacto. Verificar posición del puente.")

# Ejecutar una sola vez:
# python calibracion_bandeja.py
```

### 6.3 Calibración de pesas — por sesión (15 combinaciones)

**Quién:** Fixture de pytest `weight_calibration` (automático)  
**Cuándo:** Al inicio de cada sesión de tests de pesaje  
**Por qué:** El peso nominal (500 g) difiere del medido (p.ej. 498 g) por posicionamiento sobre la bandeja  
**Tiempo estimado:** ~7–8 minutos por sesión

```python
# tests/conftest.py
CALIBRATED_WEIGHTS_G = [
    200, 500, 700, 1000, 1200, 1500, 1700,
    2000, 2200, 2500, 2700, 3000, 3200, 3500, 3700
]

@pytest.fixture(scope="session")
def weight_calibration(weight_actuator, api_client, metrology):
    """
    Mide el peso real de las 15 combinaciones posibles con las pesas DOLZ.
    Los tests usan cal["700"] en lugar del valor nominal 700.
    """
    cal = {}
    for nominal_g in CALIBRATED_WEIGHTS_G:
        weight_actuator.set(nominal_g)
        measured = poll_until_stable(
            api_client, metrology, expected_weight_kg=nominal_g / 1000
        )
        cal[str(nominal_g)] = measured
        weight_actuator.zero()
        poll_until_stable(api_client, metrology, expected_weight_kg=0.0, tolerance_g=2, max_wait_s=4)
        print(f"  {nominal_g}g nominal → {measured*1000:.1f}g medido")
    return cal
# Uso en tests: assert abs(cal["500"] - expected) < 0.005  (tolerancia ±5g)
```

### 6.4 Anti-backlash — regla de dirección del carro (firmware ESP32)

La varilla M8 tiene backlash de 0.1–0.3 mm. La posición final depende de la dirección del último movimiento. Para que la calibración sea repetible, **el firmware debe garantizar que toda posición final se alcanza siempre desde arriba** (movimiento descendente final):

```
Algoritmo set(target_steps):
  current_steps = get_encoder_position()
  if target_steps >= current_steps:
    move_to(target_steps)            // ya va a bajar → sin backlash
  else:
    overshoot = target_steps - BACKLASH_MARGIN_STEPS   // sube de más
    move_to(overshoot)               // sube al punto de sobrecarrera
    move_to(target_steps)            // baja al target desde arriba ✓

BACKLASH_MARGIN_STEPS = 40   // ~0.25mm — ajustar experimentalmente en Sprint 0
```

> **Consecuencia en el código:** `weight_actuator.set(200)` seguido de `weight_actuator.set(500)` siempre baja directamente (500 > 200). `weight_actuator.set(500)` seguido de `weight_actuator.set(200)` sube a 160 steps y luego baja a 200. El test no necesita saber nada de esto — es responsabilidad del firmware.

### 6.5 Calibración de estabilización (Sprint 0)

**Quién:** Script manual, una sola vez  
**Cuándo:** Antes de definir los parámetros de `poll_until_stable()`  
**Entregable:** Gráfico CSV con la curva de estabilización

```python
# sprint0_estabilizacion.py — ver sección Fase 0
# Resultado esperado: curva que baja a ±1g en menos de 5 segundos
# → configura max_wait=6, stable_reads=5, tolerance_g=1.0
```

### 6.5 Función poll_until_stable

Toda lectura de peso en los tests pasa por esta función. No usar `time.sleep()` fijo.

```python
from collections import deque
import time
from tests.metrology import MetrologyProfile
from tests.errors import StabilizationError

def poll_until_stable(
    api_client: "NEOApiClient",
    profile: MetrologyProfile,
    expected_weight_kg: float = 0.0,
    stable_reads: int = 5,
    max_wait_s: float = 8.0,
    poll_interval_s: float = 0.2,
    tolerance_g: float = None,    # override explícito; si None, deriva del profile
) -> float:
    """
    Espera hasta que stable_reads lecturas consecutivas difieran menos que la tolerancia.
    La tolerancia se deriva automáticamente del perfil metrológico y el peso esperado.
    Lanza StabilizationError si max_wait_s pasa sin convergencia.
    """
    effective_tol_kg = (tolerance_g or profile.tolerance_g_for(expected_weight_kg)) / 1000
    readings: deque = deque(maxlen=stable_reads)
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        w = api_client.get_weight(unit_to_kg=profile.unit_to_kg)
        readings.append(w)
        if len(readings) == stable_reads:
            if (max(readings) - min(readings)) <= effective_tol_kg:
                return readings[-1]
        time.sleep(poll_interval_s)
    raise StabilizationError(
        f"Peso no estabilizó en {max_wait_s}s. "
        f"Últimas lecturas: {[round(x*1000,1) for x in readings]}g. "
        f"Tolerancia activa: {effective_tol_kg*1000:.1f}g "
        f"(variante {profile.variant}, peso esperado {expected_weight_kg*1000:.0f}g)"
    )
```

> **Migración de llamadas existentes:** `poll_until_stable(api_client, tolerance_g=2)` pasa a `poll_until_stable(api_client, profile, expected_weight_kg=0.0, tolerance_g=2)`. En la mayoría de los casos el override no es necesario — basta con `poll_until_stable(api_client, profile, expected_weight_kg=peso_nominal)`.

---

## 7. Mecanismo de asentamiento del peso — Pin flotante

El pin **no está soldado rígidamente** al carro. Pasa por una manga con 5 mm de holgura axial. Esto garantiza que el 100% del peso de las pesas recaiga sobre la bandeja, sin fuerzas parásitas de la estructura.

```
ESTADO LEVANTADO          ESTADO APOYADO (medición)

[CARRO]──[MANGA]          [CARRO]──[MANGA]
          │                         │
    [COLLARÍN SUP]              5mm holgura libre ↕
          │                    [COLLARÍN SUP] (libre)
    [PIN]                      [PIN]
          │                         │
    [PESAS]                    [PESAS]
          │ (en aire)               │
       ───────               ════════════ BANDEJA
                             (peso pleno ✓ sin carga estructural ✓)
```

**Perfil de velocidad del motor:**
- **Fase rápida:** 500 steps/s hasta 30 mm antes del punto de contacto esperado
- **Fase creep:** 80 steps/s; el ESP32 consulta `/api/weight` cada 200 ms y detiene el motor cuando detecta > 30 g
- **Post-contacto:** `poll_until_stable()` espera estabilización antes de registrar

---

## 8. Aislamiento entre tests — Fixture clean_state

Cada test de hardware ejecuta este fixture automáticamente (antes y después). La versión robusta:
- Degrada si VNC no está disponible (no falla el setup innecesariamente)
- Verifica con API que el PLU está descargado y la bandeja libre
- Confirma en teardown que la bandeja quedó sin carga (detecta zero() fallido)

```python
@pytest.fixture(autouse=True)
def clean_state(weight_actuator, api_client, keyboard, screen, metrology):
    # ── SETUP: dejar la balanza en estado limpio ──────────────
    weight_actuator.zero()
    poll_until_stable(api_client, metrology, expected_weight_kg=0.0, tolerance_g=2)

    for _ in range(5):           # salir de cualquier menú abierto
        keyboard.press("escape")
        keyboard.release("escape")
        time.sleep(0.3)

    # Verificación primaria: API (siempre disponible)
    plu_loaded = api_client.get_product().get("plu", -1)
    assert plu_loaded == 0, f"PLU {plu_loaded} aún cargado tras reset — usar plu/unload"

    # Verificación secundaria: VNC (degrada si no está disponible)
    if screen.is_connected():
        assert screen.is_main_screen(), \
            "VNC disponible pero pantalla no es main — verificar estado de la balanza"

    yield                        # ← aquí ejecuta el test

    # ── TEARDOWN: dejar la bandeja libre ─────────────────────
    weight_actuator.zero()
    time.sleep(1.0)              # margen mecánico: pin flotante necesita ~0.5s para separarse
    final_w = poll_until_stable(api_client, metrology, expected_weight_kg=0.0, tolerance_g=2, max_wait_s=4)
    assert final_w < 0.003, (
        f"Bandeja no quedó libre post-test: {final_w}kg. "
        "El actuador puede estar atascado o el ESP32 no respondió."
    )
```

> **Por qué el `time.sleep(1.0)` en teardown:** el pin flotante tiene 5 mm de holgura axial. Al llamar `zero()`, el carro sube 5 mm antes de que el collarín inferior levante el pin. Si se verifica el peso inmediatamente, la lectura aún puede ser > 0 aunque el carro ya esté subiendo. El sleep garantiza que el pin se separó de la bandeja antes de la verificación.

---

## 9. Estructura de carpetas del proyecto

```
E:\Personal\Capacitaciones\Claude\NEO-Aut\
│
├── plan-automatizacion-cuora-neo.md    ← este documento
├── riel-actuador.svg                   ← plano del puente portal
├── .env.test.example                   ← plantilla de variables
│
├── config/
│   └── hardware_params.yaml            ← parámetros físicos y de timing (en git)
│
├── scripts/
│   ├── sprint0_estabilizacion.py       ← medir curva de estabilización
│   ├── calibracion_bandeja.py          ← calibrar tray_contact_steps en EEPROM del ESP32
│   └── flakiness_report.py             ← analizar runs históricos y detectar tests inestables
│
├── cypress/                            ← Suite 1 (JavaScript)
│   ├── cypress.config.js
│   ├── package.json
│   ├── support/
│   │   ├── commands.js                 ← cy.loadPlu, cy.createPlu, cy.getWeight
│   │   └── e2e.js
│   └── e2e/
│       ├── api/
│       │   ├── connectivity.cy.js
│       │   ├── pesaje.cy.js
│       │   ├── abm.cy.js
│       │   └── ventas.cy.js
│       └── web/
│           ├── login.cy.js
│           ├── abm_plu.cy.js
│           ├── price_lists.cy.js
│           ├── reports.cy.js
│           └── config.cy.js
│
├── tests/                              ← Suite 2 (Python)
│   ├── conftest.py                     ← fixtures: ssh, vnc, db, actuador, hw_config
│   ├── errors.py                       ← jerarquía de excepciones tipadas (§18)
│   ├── api_client.py                   ← NEOApiClient — único punto de acceso a la API (§17)
│   ├── metrology.py                    ← MetrologyProfile + MetrologyRange + build_profile (§23)
│   ├── assertions.py                   ← assert_weight, assert_overload_triggered, etc. (§24)
│   ├── ssh/
│   │   ├── conftest.py
│   │   ├── test_system_health.py
│   │   ├── test_db_state.py
│   │   ├── test_backup_restore.py
│   │   └── test_ftp_import.py
│   └── vnc/
│       ├── conftest.py
│       ├── golden/                     ← screenshots de referencia por firmware
│       ├── pages/
│       │   ├── vnc_base.py
│       │   └── pantalla_venta.py
│       ├── pesaje/
│       │   ├── test_tara_directa.py
│       │   ├── test_tara_acumulativa.py
│       │   └── test_ajuste_cero.py
│       └── ventas/
│           ├── test_venta_pesable.py
│           ├── test_venta_escurrida.py
│           └── test_preempaque.py
│
└── reports/                            ← generado automáticamente
    ├── cypress/
    └── pytest/
```

---

## 10. Variables de entorno — `.env.test.example`

```bash
# ── Dispositivo ──────────────────────────────────────────
NEO_IP=192.168.1.100
NEO_API_PORT=7376
NEO_WEB_PORT=80

# ── Credenciales web/API ──────────────────────────────────
NEO_WEB_USER=Supervisor
NEO_WEB_PASS=1234
NEO_API_USER=admin
NEO_API_PASS=1234

# ── SSH ───────────────────────────────────────────────────
NEO_SSH_HOST=192.168.1.100
NEO_SSH_PORT=22
NEO_SSH_USER=systel
NEO_SSH_KEY_PATH=~/.ssh/neo_rsa   # dejar vacío si el device usa password
NEO_SSH_PASS=                     # alternativa a key (sshtunnel soporta ambos)

# ── PostgreSQL (vía túnel SSH) ────────────────────────────
NEO_DB_NAME=cuora
NEO_DB_USER=cuora_user
NEO_DB_PASS=

# ── VNC (solo lectura) ───────────────────────────────────
NEO_VNC_HOST=192.168.1.100
NEO_VNC_PORT=5900
NEO_VNC_PASSWORD=

# ── Actuador ESP32 ───────────────────────────────────────
NEO_ESP32_IP=192.168.100.156
ACTUATOR_MODE=poc                 # poc | final
ACTUATOR_BACKLASH_STEPS=40        # pasos de margen para anti-backlash (ajustar en Sprint 0)

# ── Orchestration ─────────────────────────────────────────
RUN_ID=                           # vacío = generar automáticamente como YYYYMMDD_HHMMSS
RETRY_FAILED_PHASES=1             # cuántas veces reintentar una fase que falla
REPORTS_BASE_DIR=reports/runs

# ── Evidencia ─────────────────────────────────────────────
COLLECT_ALL_EVIDENCE=false        # true = recopilar evidencia también en tests PASSED

# ── Metrología ────────────────────────────────────────────
TEST_METROLOGY_PROFILE=AR         # AR | BR | US — perfil metrológico activo

# ── Firmware ──────────────────────────────────────────────
NEO_FW_VERSION_OVERRIDE=          # forzar versión específica (solo para CI sin device)
```

---

## 10b. Orchestration layer — Pipeline de ejecución

### Diseño incremental: PhaseResult + hooks

El objetivo es tener una estructura que hoy funciona como "4 comandos CLI coordinados" y mañana puede crecer a "pipeline con notificaciones y dashboard" **sin reescribir el código central**.

#### Contrato de resultado por fase

```python
# run_suite.py
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class TestFailure:
    test_id: str
    message: str
    evidence_path: Optional[str] = None

@dataclass
class PhaseResult:
    phase: str                          # "cypress_api" | "cypress_web" | "ssh" | "vnc"
    status: str                         # "passed" | "failed" | "skipped" | "error"
    duration_s: float
    tests_run: int
    failures: List[TestFailure] = field(default_factory=list)
    run_id: str = ""
    fw_version: str = ""
```

#### Hooks de extensión (noop hoy)

```python
# Definir hoy, implementar cuando se necesiten — sin cambios al pipeline
def on_preflight_fail(reason: str): pass       # mañana: notificación Slack
def on_phase_start(phase: str, run_id: str): pass
def on_phase_end(result: PhaseResult): pass    # mañana: webhook CI / email
def on_suite_end(results: List[PhaseResult]): pass  # mañana: HTML report / dashboard

# Pipeline central — no cambia al agregar features:
for phase in PHASES:
    on_phase_start(phase.name, RUN_ID)
    result = phase.run()
    results.append(result)
    on_phase_end(result)
on_suite_end(results)
```

#### run_id y estructura de reportes

```python
RUN_ID = os.environ.get("RUN_ID") or datetime.now().strftime("%Y%m%d_%H%M%S")
REPORTS_DIR = Path(os.environ.get("REPORTS_BASE_DIR", "reports/runs")) / RUN_ID
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
```

#### Estructura de directorios de evidencia

```
reports/runs/
  20260507_143021/                      ← run_id
    summary.json                        ← agregado final (ver contrato abajo)
    cypress/
      api-results.json                  ← generado por Cypress nativo
      web-results.json
    pytest/
      ssh--test_system_health--test_uptime/
        result.json
      vnc--pesaje--test_tara_directa/
        result.json
        vnc_before.png                  ← solo en failures (o con COLLECT_ALL_EVIDENCE)
        vnc_after.png
        api_timeline.json               ← [{t, endpoint, response_ms, weight}]
        weight_readings.csv
        ssh_log_tail.txt
```

Nombrado de subdirectorios: `{suite}--{module}--{test_name}` (doble guión, sin espacios). Compatible con Windows y Linux.

#### Contrato de summary.json

```json
{
  "run_id": "20260507_143021",
  "fw_version": "1.2.3",
  "device_ip": "192.168.1.100",
  "total_status": "failed",
  "duration_s": 847,
  "phases": [
    {"phase": "cypress_api",  "status": "passed", "tests_run": 18, "failures": []},
    {"phase": "cypress_web",  "status": "failed", "tests_run": 24,
     "failures": [{"test_id": "abm_plu::test_create_pesable", "message": "..."}]},
    {"phase": "ssh",          "status": "skipped","tests_run": 0, "failures": []},
    {"phase": "vnc",          "status": "skipped","tests_run": 0, "failures": []}
  ]
}
```

#### Plugin de evidencia (pytest hook, < 40 líneas)

```python
# tests/conftest.py — se activa automáticamente, sin decoradores en los tests
import pytest
from pathlib import Path

def pytest_runtest_makereport(item, call):
    if call.when == "call" and call.excinfo is not None:
        evidence_dir = _make_evidence_dir(item)
        _collect_vnc_screenshot(item, evidence_dir, tag="after_failure")
        _collect_api_timeline(item, evidence_dir)
        _collect_weight_readings(item, evidence_dir)

def _make_evidence_dir(item) -> Path:
    run_id = item.config.getoption("--run-id", default="unknown")
    name = item.nodeid.replace("::", "--").replace("/", "--").replace(".py", "")
    d = Path("reports/runs") / run_id / "pytest" / name
    d.mkdir(parents=True, exist_ok=True)
    return d
```

---

## 10c. Compatibilidad de firmware

### Version gate — preflight automático

```python
# tests/conftest.py
SUPPORTED_FIRMWARE = ["1.2.3"]   # agregar nueva versión solo después de validar y tomar goldens

@pytest.fixture(scope="session", autouse=True)
def firmware_preflight(api_client):
    try:
        sig = api_client.get("/api/signature").json()
    except Exception as e:
        pytest.skip(f"No se pudo contactar la balanza ({e}) — tests saltados")
    fw = sig.get("version", "unknown")
    if fw not in SUPPORTED_FIRMWARE:
        pytest.skip(
            f"Firmware {fw} no validado. Soportados: {SUPPORTED_FIRMWARE}. "
            "Pasos: (1) tomar golden screenshots, (2) agregar a SUPPORTED_FIRMWARE, "
            "(3) ejecutar suite completa y verificar."
        )
    return fw
```

### Golden screenshots por versión de firmware

```
tests/vnc/golden/
  fw_1.2.3/
    main_screen.png
    menu_abm.png
    pantalla_tara_activa.png
    dialogo_sobrecarga.png
  fw_1.3.0/            ← crear cuando llegue la nueva versión
    ...
```

Al detectar una nueva versión de firmware: no ejecutar tests, tomar nuevos goldens, agregar versión a `SUPPORTED_FIRMWARE`, re-ejecutar suite.

### Schema validation en Cypress (integrado en Fase 1)

Ver `assertApiSchema` en la Sección 4 — Fase 1. Esta validación es la primera barrera contra cambios silenciosos en la API por actualización de firmware.

---

## 11. Lista de materiales — Hardware de producción

### Electrónica

| Componente | Descripción | Cant. | USD aprox. |
|------------|-------------|:-----:|:----------:|
| ESP32 Dev Module | Disponible del POC | 1 | — |
| NEMA 17 stepper | 40 Ncm, 1.8°/paso (o motor de impresora 3D) | 1 | $8–15 |
| DRV8825 driver | Microstepping 1/32 | 1 | $3–5 |
| Fuente 12V 2A | Para el stepper | 1 | $8–12 |
| Microswitch homing | Limit switch posición HOME | 1 | $1–2 |
| Acoplador flexible M5→M8 | Eje motor → lead screw | 1 | $3–5 |
| Cables y conectores | — | — | $3–5 |

### Mecánica

| Componente | Descripción | Cant. | USD aprox. |
|------------|-------------|:-----:|:----------:|
| Varilla roscada M8 × 350 mm | Lead screw | 1 | $2–3 |
| Tuerca M8 (anti-backlash si hay) | Freno del carro | 2 | $0.50 |
| Guías lisas Ø8 mm × 300 mm | Varilla pulida | 2 | $4–8 |
| Rodamientos LM8UU | O bujes PTFE | 2 | $3–5 |
| Goma antivibración 5 mm | Base de patas | 4 piezas | $2 |

### Lo que fabrica el herrero (acero S235)

| Pieza | Material | Nota |
|-------|----------|------|
| 2 patas verticales ~430 mm | Tubo 25×25 mm | Largas a determinar tras medir bandeja |
| Travesaño superior 500 mm | Tubo 25×25 mm | Largo fijo |
| Carro 80×60 mm | Chapa 5 mm doblada | Sin brazo; manga en centro |
| Manga del pin | Tubo Ø13 mm int. × 30 mm | Soldada al carro |
| Pin con 2 collarines | Varilla Ø10 mm, 160 mm | Collarines = arandelas soldadas |
| Flange motor NEMA 17 | Chapa 4 mm | Patrón 31 mm, 4× M3 |

### Pesas (ya disponibles en laboratorio)

| Peso | Material | Forma |
|------|----------|-------|
| 2.000 g | Hierro fundido | Ranura en C — DOLZ certificadas |
| 1.000 g | Hierro fundido | Ranura en C |
| 500 g | Bronce | Ranura en C |
| 200 g | Bronce | Ranura en C |
| **Total: 3.700 g** | | **15 combinaciones posibles** |

Combinaciones disponibles (g): `200, 500, 700, 1000, 1200, 1500, 1700, 2000, 2200, 2500, 2700, 3000, 3200, 3500, 3700`

**Para test de sobrecarga:** adquirir una pesa de 5 kg (~$15–25 USD). Con 8.7 kg total se supera la capacidad de la balanza de 6 kg.

**Total estimado hardware de producción: ~$100–160 USD**

---

## 12. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|--------|:-------:|------------|
| 1 | Vibración del stepper desestabiliza la celda de carga | Alto | Pin flotante + perfil de velocidad en dos fases + `poll_until_stable()` |
| 2 | Estado corrupto entre tests (tara activa, menú abierto) | Alto | Fixture `clean_state` autouse en todos los tests de hardware |
| **3** | **`apt update/upgrade` en la balanza rompe el SO customizado** | **Crítico** | **Todos los tests SSH son solo lectura. Ver lista de comandos permitidos en §4 Fase 3. Prohibición documentada y registrada en memoria del proyecto.** |
| 4 | Template matching VNC falla por compresión JPEG | Medio | ORB feature matching + API como fuente de verdad para valores numéricos |
| 5 | Conflicto teclado: VNC + USB HID duplican teclas | Medio | VNC en view-only; pynput como único canal de entrada |
| 6 | Peso nominal ≠ peso medido (posicionamiento) | Medio | Fixture `weight_calibration` por sesión con valores reales (15 combos) |
| 7 | Backlash de lead screw M8 introduce error de posición | Medio | Firmware ESP32 garantiza aproximación siempre desde arriba (`BACKLASH_MARGIN_STEPS`) |
| 8 | Drift de `tray_contact_steps` con el tiempo | Medio | Fixture `verify_tray_calibration` detecta deriva >20g; re-ejecutar `calibracion_bandeja.py` |
| 9 | Cobertura de impresión no verificable sin OCR de papel | Bajo | SSH: leer log de la app. OCR de papel como deuda técnica |
| 10 | Motor 3D printer tiene engranaje de extrusor | Bajo | Extraer con calor + extractor. Eje Ø5 mm compatible con coupler M5→M8 |

---

## 13. Verificación end-to-end por fase

```bash
# Fase 0 — MVP con POC
pytest tests/vnc/ventas/test_venta_pesable.py -s --actuator=poc
# Esperado: PASSED — actuador baja → API lee peso → VNC verifica → DB confirma

# Fase 1 — Cypress API
npx cypress run --spec "cypress/e2e/api/"
# Esperado: 4 archivos, todos green

# Fase 2 — Cypress Web
npx cypress run --spec "cypress/e2e/web/" --headed

# Fase 3 — SSH + DB
pytest tests/ssh/ -v

# Fase 4 — Hardware completo
pytest tests/vnc/ -s -m hardware
```

---

## 14. Checklist de formalización por capa

Completar estos items **antes de escribir el primer test de cada capa**. Son prerrequisitos, no sugerencias.

### Antes de Cypress API (Fase 1)
- [ ] Versión de firmware del device identificada: `GET /api/signature → version`
- [ ] `SUPPORTED_FIRMWARE = ["x.y.z"]` actualizado en `tests/conftest.py`
- [ ] `assertApiSchema` implementado en `cypress/support/commands.js`
- [ ] `TEST_PLU_RANGE_START = 90000` y `afterEach` de limpieza en `cypress/support/e2e.js`
- [ ] `.env.test` completo con IP, credenciales, `ACTUATOR_MODE=poc`
- [ ] Conexión manual verificada: `curl http://NEO_IP:7376/api/ping` responde

### Antes de Cypress Web (Fase 2)
- [ ] Panel web `http://NEO_IP:80` cargable en Chrome desde el PC de tests
- [ ] Credenciales de cada rol verificadas: Admin (`Supervisor/1234`), Vendedor, Consulta
- [ ] Selectores del panel web relevados: inspeccionar con DevTools antes de escribir tests
- [ ] Mecanismo de cleanup de test-data definido (DELETE masivo o individual)

### Antes de pytest SSH (Fase 3)
- [ ] `sshtunnel` agregado a `requirements.txt`
- [ ] Fixture `db_conn` con implementación corregida (ver Sección 4 — Fase 3)
- [ ] Conexión SSH manual verificada: `ssh NEO_SSH_USER@NEO_SSH_HOST`
- [ ] Nombre de base de datos y usuario PostgreSQL confirmados en el device real
- [ ] `NEO_SSH_KEY_PATH` o `NEO_SSH_PASS` configurados según el método de auth del device

### Antes de pytest VNC / Hardware (Fase 4)
- [ ] Sprint 0 ejecutado: curva de estabilización medida y graficada
- [ ] `max_wait`, `stable_reads` y `tolerance_g` definidos en constantes
- [ ] `ACTUATOR_BACKLASH_STEPS` medido experimentalmente y configurado
- [ ] `calibracion_bandeja.py` ejecutado: `tray_contact_steps` guardado en EEPROM del ESP32
- [ ] Golden screenshots del fw actual tomadas y guardadas en `tests/vnc/golden/fw_{version}/`
- [ ] `DeviceReadyState` y `is_main_screen()` implementados en `tests/vnc/pages/device_state.py`
- [ ] `press_and_verify()` implementado en `tests/vnc/pages/vnc_base.py`
- [ ] VNC view-only verificado: conexión abre pantalla pero no envía input desde el PC
- [ ] pynput verificado: `keyboard.press(Key.enter)` llega a la balanza (verificar en pantalla)

---

## 15. Contratos de código formalizados

Esta sección centraliza los contratos de las abstracciones principales. Implementaciones que no cumplan estos contratos rompen la suite.

### WeightActuator — contrato de interfaz

```python
# tests/conftest.py
from typing import Protocol

class WeightActuatorContract(Protocol):
    def set(self, grams: int) -> None:
        """
        Posiciona las pesas sobre la bandeja.
        Precondición: carro en HOME (zero() completado y verificado).
        Postcondición: pin flotante apoyado sobre bandeja; pesas ejercen su peso por gravedad.
        Dirección de aproximación: SIEMPRE desde arriba (firmware garantiza anti-backlash).
        El caller debe llamar poll_until_stable() después de set() antes de leer el peso.
        Excepciones: ActuatorError si ESP32 no responde; ValueError si grams > MAX_GRAMS.
        """

    def zero(self) -> None:
        """
        Eleva el carro al home (limit switch).
        Bloquea hasta que el motor detiene el movimiento.
        IMPORTANTE: el pin flotante tarda ~0.5-1s en separarse de la bandeja post-retorno.
        El caller debe esperar poll_until_stable(tolerance_g=2) antes de verificar bandeja libre.
        """
```

### WeightActuator — implementaciones

```python
class WeightActuatorPOC:
    """Adaptador para el POC con servo. Ignora el valor de grams (solo baja/sube)."""
    def __init__(self, ip: str): self._ip = ip
    def set(self, grams: int) -> None:
        requests.post(f"http://{self._ip}/bajar", timeout=5)
    def zero(self) -> None:
        requests.post(f"http://{self._ip}/subir", timeout=5)

class WeightActuatorFinal:
    """Adaptador para el actuador de producción con NEMA 17 + DRV8825."""
    def __init__(self, ip: str): self._ip = ip
    def set(self, grams: int) -> None:
        requests.post(f"http://{self._ip}/weight/set", json={"grams": grams}, timeout=10)
    def zero(self) -> None:
        requests.post(f"http://{self._ip}/weight/zero", timeout=10)
```

### poll_until_stable — implementación de referencia

Ver §6.5 para la implementación completa con firma actualizada:

```python
def poll_until_stable(
    api_client: NEOApiClient,
    profile: MetrologyProfile,
    expected_weight_kg: float = 0.0,
    stable_reads: int = 5,
    max_wait_s: float = 8.0,
    poll_interval_s: float = 0.2,
    tolerance_g: float = None,    # override explícito; si None, deriva del profile
) -> float: ...
```

La tolerancia se calcula como `profile.tolerance_g_for(expected_weight_kg)` (≥ 2.5g siempre), salvo override explícito. Lanza `StabilizationError` al agotar `max_wait_s`.

### DeviceReadyState — contrato de estado READY

```python
# tests/vnc/pages/device_state.py
from dataclasses import dataclass

@dataclass
class DeviceReadyState:
    """Criterios para considerar la balanza en estado limpio entre tests."""
    weight_kg: float     # < 0.003 kg (menos de 3g — tolerancia de celda en reposo)
    tare_active: bool    # False — sin tara activa
    plu_loaded: int      # 0 — ningún PLU cargado en pantalla
    screen_id: str       # "main_screen" — verificado por OpenCV

    def is_ready(self) -> bool:
        return (
            self.weight_kg < 0.003
            and not self.tare_active
            and self.plu_loaded == 0
            and self.screen_id == "main_screen"
        )
```

### press_and_verify — contrato de inyección de teclas

```python
# tests/vnc/pages/vnc_base.py
def press_and_verify(keyboard, key, verify_fn, description="", timeout=2.0) -> None:
    """
    Envía una tecla vía USB HID y verifica que el dispositivo acusó el cambio.
    Si verify_fn() no retorna True en timeout segundos, lanza AssertionError.
    Usar SIEMPRE en lugar de keyboard.press() directo para detectar foco perdido.
    """
    keyboard.press(key)
    keyboard.release(key)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if verify_fn():
            return
        time.sleep(0.2)
    raise AssertionError(
        f"Tecla '{key}' ({description}) enviada pero estado no cambió en {timeout}s. "
        "Posible causa: el foco en el PC no está en la balanza."
    )
```

---

## 16. Separación de configuración y arquitectura

### Principio

El código y el documento describen **qué hace el sistema** (inmutable sin revisión de diseño). El archivo `config/hardware_params.yaml` describe **cómo está ajustado** (cambia por calibración o desgaste). Las variables de entorno describen **dónde está** (cambia por despliegue).

| Dónde vive | Qué contiene | En git | Quién cambia |
|---|---|:---:|---|
| Código Python / JS | Contratos, lógica, algoritmos | ✓ | Dev con revisión |
| `config/hardware_params.yaml` | Parámetros físicos y de timing | ✓ | Técnico de laboratorio |
| `.env.test` | IPs, credenciales, secrets | ✗ | Operador por entorno |

### Archivo `config/hardware_params.yaml`

```yaml
# config/hardware_params.yaml
# Ajustar tras Sprint 0 y cada sesión de calibración.
# Versionado en git: el historial muestra cómo evolucionó la calibración.

actuator:
  backlash_margin_steps: 40       # sobrecarrera anti-backlash (ajustar en Sprint 0)
  creep_speed_steps_per_s: 80     # fase lenta de aproximación al contacto
  fast_speed_steps_per_s: 500     # fase rápida de descenso
  contact_threshold_g: 30         # umbral de detección de contacto con bandeja
  approach_margin_steps: 300      # margen previo al punto de contacto esperado

stabilization:
  # tolerance_g ELIMINADO — derivado dinámicamente por MetrologyProfile.tolerance_g_for()
  stable_reads: 5                 # lecturas consecutivas estables requeridas
  poll_interval_s: 0.2            # intervalo entre lecturas de /api/weight
  max_wait_s: 8                   # tiempo máximo de espera

ready_state:
  max_weight_kg: 0.003            # peso máximo para considerar bandeja "libre"
  pin_float_settle_s: 1.0         # espera post-zero() para el pin flotante

calibration:
  drift_tolerance_g: 20           # deriva máxima aceptable de tray_contact_steps (10× e1)
  verification_weight_g: 200      # pesa usada para verificar calibración al inicio de sesión

api:
  timeout_s: 5                    # timeout para requests a la API REST
```

> **Por qué se eliminó `stabilization.tolerance_g`:** la tolerancia correcta depende del rango activo del instrumento y del peso que se está midiendo. Un valor fijo incorrecto para todos los rangos. `MetrologyProfile.tolerance_g_for(weight_kg)` calcula el valor apropiado en tiempo de ejecución según el perfil cargado vía `TEST_METROLOGY_PROFILE`.

### Carga en fixtures

```python
# tests/conftest.py
import yaml
from pathlib import Path

@pytest.fixture(scope="session")
def hw_config() -> dict:
    path = Path(__file__).parent.parent / "config" / "hardware_params.yaml"
    return yaml.safe_load(path.read_text())

# Uso en otros fixtures:
@pytest.fixture(scope="session")
def api_client(hw_config) -> "NEOApiClient":
    base = f"http://{os.environ['NEO_IP']}:{os.environ.get('NEO_API_PORT', 7376)}"
    return NEOApiClient(base, timeout_s=hw_config["api"]["timeout_s"])
```

> Los fixtures que hoy usan valores hardcodeados (`tolerance_g=1.0`, `max_wait=8`) deben recibir `hw_config` y leer desde el YAML. Así, recalibrar no implica modificar código ni buscar en múltiples archivos.

---

## 17. NEOApiClient — punto único de acceso a la API

Todos los accesos a la API REST pasan por esta clase. Ningún test importa `requests` directamente.

**Beneficios concretos:**
- La timeline de evidencia se recolecta automáticamente sin instrumentar los tests
- Los timeouts son uniformes (definidos en `hw_config`)
- Cuando un campo de la API cambia por firmware, se actualiza en un solo lugar
- Las excepciones tipadas alimentan la taxonomía de fallos (ver §18)

```python
# tests/api_client.py
import time, requests
from typing import List
from tests.errors import ConnectivityError, TimeoutError as NEOTimeout, ActuatorError

class NEOApiClient:
    def __init__(self, base_url: str, timeout_s: int = 5):
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s
        self._timeline: List[dict] = []

    # ── Endpoints tipados ──────────────────────────────────────
    def ping(self) -> str:
        return self._get("/api/ping")["status"]

    def signature(self) -> dict:
        return self._get("/api/signature")

    def get_weight(self, unit_to_kg: float = 1.0) -> float:
        """
        Retorna el peso en kg.
        unit_to_kg: factor de conversión del perfil metrológico activo.
          - kg (AR/BR): 1.0
          - lb (US):    0.453592
        Proveer vía metrology.unit_to_kg desde el fixture de sesión.
        """
        raw = self._get("/api/weight")
        w = float(raw["weight"])
        return w * unit_to_kg

    def get_product(self) -> dict:
        return self._get("/api/product")

    def load_plu(self, plu: int) -> dict:
        return self._post("/api/plu/load", {"plu": plu})

    def create_plu(self, data: dict) -> dict:
        return self._post("/api/plu/create", data)

    # ── Evidencia ──────────────────────────────────────────────
    def dump_timeline(self) -> List[dict]:
        return list(self._timeline)

    def clear_timeline(self):
        self._timeline.clear()

    # ── Infraestructura ────────────────────────────────────────
    def _get(self, path: str) -> dict:
        return self._request("GET", path)

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, json=body)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        t0 = time.monotonic()
        try:
            r = requests.request(method, f"{self._base}{path}",
                                 timeout=self._timeout, **kwargs)
            r.raise_for_status()
            body = r.json()
            self._timeline.append({
                "t_ms": round((time.monotonic() - t0) * 1000),
                "method": method, "path": path, "status": r.status_code,
            })
            return body
        except requests.Timeout:
            raise NEOTimeout(f"{method} {path} timeout después de {self._timeout}s")
        except requests.ConnectionError:
            raise ConnectivityError(f"Device no alcanzable: {self._base}")
        except requests.HTTPError as e:
            raise NEOTimeout(f"{method} {path} → HTTP {e.response.status_code}")
```

---

## 18. Failure taxonomy — jerarquía de excepciones

Todas las excepciones de la suite heredan de `NEOTestError` y tienen un atributo `category`. El pytest plugin extrae la categoría automáticamente al registrar el fallo en `summary.json`.

```python
# tests/errors.py
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
```

### Integración en el plugin de evidencia

```python
# tests/conftest.py — dentro del hook pytest_runtest_makereport
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        exc = call.excinfo.value if call.excinfo else None
        category = getattr(exc, "category", "unknown")
        # Guardar en el resultado para que run_suite.py lo recoja
        report.user_properties.append(("failure_category", category))
```

### Dónde lanzar cada excepción (contratos de uso)

| Excepción | Lanzada por |
|-----------|-------------|
| `ConnectivityError` | `NEOApiClient._request()`, `firmware_preflight`, SSH fixture |
| `StabilizationError` | `poll_until_stable()` al exceder `max_wait` |
| `ActuatorError` | `WeightActuator.set/zero()` si ESP32 no responde; `poll_until_stable()` si peso estabilizó en cero tras `set()` |
| `FirmwareMismatchError` | `firmware_preflight` fixture |
| `StateCorruptionError` | `clean_state` teardown si `final_w >= max_weight_kg` |
| `WeightAssertionError` | Tests de pesaje cuando la aserción de peso falla |
| `TimeoutError` | `press_and_verify()` si el estado no cambió en el timeout |

---

## 19. Ownership explícito por capa

### Tabla de responsabilidades

| Capa | Valida | NO debe validar |
|------|--------|-----------------|
| **Cypress API** | Contrato HTTP, schemas de respuesta, SLAs de latencia, códigos 4xx/5xx | Estado de pantalla táctil, persistencia en DB, lógica de negocio |
| **Cypress Web** | Flujos de usuario en panel `:80`, CRUD completo, roles y sesiones | Lecturas del sensor, estado del SO, schema de DB |
| **pytest SSH** | Estado del SO (solo lectura), integridad de tablas PostgreSQL | Formato de respuesta API, estado visual de pantalla |
| **pytest VNC** | Estado cualitativo de pantalla: ¿qué pantalla es?, ¿hay diálogo de error? | Valores numéricos (→ usar API), persistencia (→ usar SSH/DB) |
| **Hardware / actuador** | Respuesta física real del sensor a estímulos controlados | Lógica de negocio, estado del SO, presentación en pantalla |
| **PostgreSQL (vía SSH)** | Persistencia correcta post-operación en las tablas | Formato de respuesta API, estado de pantalla, SLAs de red |

### Regla de aplicación

> "Si podés verificar un dato sin esta capa, no uses esta capa para verificarlo."

Violaciones comunes a evitar:
- Test SSH que verifica que `/api/ping` responde → duplica Cypress API, falla por conectividad
- Test VNC que lee el valor de peso del display → duplica `api_client.get_weight()` con fragilidad por JPEG
- Test API que verifica que el PLU quedó en la DB → duplica pytest SSH
- Test de hardware que verifica el formato del ticket impreso → pertenece a VNC o al log de la app vía SSH

### Ownership de aserción en un test E2E completo

Cuando el flujo es "venta de 500g de jamón registrada correctamente", cada capa verifica su parte:

| Qué verificar | Capa responsable |
|---|---|
| `POST /api/plu/load` retornó 200 OK con schema válido | Cypress API |
| El actuador colocó ~500g y `GET /api/weight` devolvió dentro del rango | Hardware + API |
| La pantalla mostró estado "venta en curso" (cualitativo) | VNC |
| El registro en la tabla de ventas tiene `peso=0.500`, `plu=correcto` | PostgreSQL SSH |

Ninguna capa repite la verificación de otra.

---

## 20. Lifecycle formal del actuador

Formalizar el lifecycle elimina los race conditions que vienen de supuestos implícitos sobre quién espera qué.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  IDLE (HOME)                                                            │
│  weight ≈ 0, pin levantado, carro en limit switch                      │
└─────────────────────────────────────────┬───────────────────────────────┘
                  set(grams) llamado      │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  APPROACHING          Responsable: firmware ESP32                       │
│  Velocidad: fast_speed_steps_per_s                                      │
│  Hasta: tray_contact_steps - approach_margin_steps                      │
└─────────────────────────────────────────┬───────────────────────────────┘
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CREEPING             Responsable: firmware ESP32                       │
│  Velocidad: creep_speed_steps_per_s                                     │
│  ESP32 consulta GET /api/weight cada 200ms                              │
│  MOTOR DETIENE cuando weight > contact_threshold_g                      │
│  [pin flotante apoya sobre bandeja — pesas por gravedad]                │
└─────────────────────────────────────────┬───────────────────────────────┘
                   ownership → test code  │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STABILIZING          Responsable: poll_until_stable()                  │
│  Polls GET /api/weight cada poll_interval_s                             │
│  Lanza StabilizationError si max_wait_s supera sin convergencia         │
│  Lanza ActuatorError si weight estabilizó cerca de cero (sin contacto) │
└─────────────────────────────────────────┬───────────────────────────────┘
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  READY_FOR_ASSERTION  Responsable: código del test                      │
│  Test lee cal["500"], compara con tolerancia, hace assert               │
└─────────────────────────────────────────┬───────────────────────────────┘
                clean_state teardown inicia│
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LIFTING              Responsable: clean_state teardown                 │
│  zero() llamado. Carro sube.                                            │
│  time.sleep(pin_float_settle_s) ← ÚNICO sleep del proyecto             │
│  (mecánico: carro sube 5mm antes de que collarín levante el pin)       │
└─────────────────────────────────────────┬───────────────────────────────┘
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  VERIFIED_IDLE        Responsable: clean_state teardown                 │
│  poll_until_stable(tolerance_g=2) confirma bandeja libre                │
│  assert weight < ready_state.max_weight_kg                             │
│  Lanza StateCorruptionError si falla                                    │
└─────────────────────────────────────────────────────────────────────────┘
                        → IDLE, listo para el siguiente test
```

### Reglas de timing que se derivan del lifecycle

| Regla | Justificación |
|-------|---------------|
| NO `time.sleep()` en código de tests | Todo wait está en `poll_until_stable()` (adaptativo) |
| UN solo `time.sleep()` en todo el proyecto | En `clean_state` teardown — mecánico, no lógico |
| APPROACHING + CREEPING: timing en firmware | El test no sabe cuánto tarda el motor — no es su responsabilidad |
| STABILIZING: `poll_until_stable()` es el único que espera | Centraliza el wait, evita waits implícitos dispersos |
| VERIFIED_IDLE: verificación obligatoria post-teardown | Detecta `StateCorruptionError` antes del siguiente test |

---

## 21. Flakiness measurement

### Schema — dos campos adicionales en TestFailure

```python
# run_suite.py
from dataclasses import dataclass

@dataclass
class TestFailure:
    test_id: str
    message: str
    category: str = "unknown"    # de la taxonomía en tests/errors.py
    attempt: int = 1             # 1=primer intento, 2+=retry
    duration_s: float = 0.0
    evidence_path: str = ""
```

Estos campos se guardan en `summary.json` desde el primer run. El valor está en acumular datos — el reporte se puede correr en cualquier momento.

### Script de reporte — `scripts/flakiness_report.py`

```python
#!/usr/bin/env python3
"""
Analiza los runs históricos y reporta tests inestables.
Uso: python scripts/flakiness_report.py [reports/runs]
"""
from pathlib import Path
import json, sys
from collections import defaultdict

def report(runs_dir: str = "reports/runs"):
    runs = sorted(Path(runs_dir).glob("*/summary.json"))
    if not runs:
        print(f"No se encontraron runs en {runs_dir}")
        return

    stats = defaultdict(lambda: {
        "total_runs": 0, "retried": 0,
        "categories": defaultdict(int), "durations": []
    })
    for path in runs:
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        for phase in data.get("phases", []):
            for f in phase.get("failures", []):
                s = stats[f["test_id"]]
                s["total_runs"] += 1
                if f.get("attempt", 1) > 1:
                    s["retried"] += 1
                s["categories"][f.get("category", "unknown")] += 1
                if f.get("duration_s"):
                    s["durations"].append(f["duration_s"])

    rows = sorted(stats.items(),
                  key=lambda x: x[1]["retried"] / max(x[1]["total_runs"], 1),
                  reverse=True)

    print(f"\nFlakiness Report — {len(runs)} runs analizados")
    print(f"{'Test':<55} {'Runs':>5} {'Retried':>8} {'Rate':>6}  Top category")
    print("─" * 90)
    for test_id, s in rows[:20]:
        rate = s["retried"] / s["total_runs"]
        top = max(s["categories"], key=s["categories"].get, default="—")
        avg_dur = sum(s["durations"]) / len(s["durations"]) if s["durations"] else 0
        print(f"{test_id:<55} {s['total_runs']:>5} {s['retried']:>8} "
              f"{rate:>5.0%}  {top} (avg {avg_dur:.1f}s)")

if __name__ == "__main__":
    report(sys.argv[1] if len(sys.argv) > 1 else "reports/runs")
```

### Qué revelan los datos con el tiempo

| Métrica | Señal |
|---------|-------|
| `retry_rate > 20%` en `stabilization_failure` | Vibración o timing mecánico — ajustar `max_wait_s` o `tolerance_g` |
| `retry_rate > 20%` en `connectivity_failure` | Red inestable o device con uptime bajo |
| `retry_rate > 20%` en `actuator_failure` | Desgaste del actuador o drift de calibración |
| `avg_duration` creciente en tests de pesaje | `max_wait_s` cerca del límite — el sistema está degradando |
| `state_corruption` frecuente | `clean_state` tiene un bug o el device no responde al reset |

---

## 22. Datos metrológicos por variante — NEO-2 AR / BR / US

Los datos metrológicos condicionan directamente los parámetros de calibración, los umbrales de los tests y qué funcionalidades están disponibles por variante.

### 22.1 Tabla comparativa

| Característica | AR 🇦🇷 | BR 🇧🇷 | US 🇺🇸 |
|---|---|---|---|
| **Capacidades** | 6 / 15 / 30 kg | 6 / 15 / 30 kg | 15 / 30 / 60 lb |
| **Resolución e1/e2/e3** | 0,002 / 0,005 / 0,010 kg | 0,002 / 0,005 / 0,010 kg | 0,005 / 0,010 / 0,020 lb |
| **Límite de cero (3% Máx)** | 0,900 kg | 0,900 kg | 1,800 lb |
| **Límite de tara** | 6,000 kg | 6,000 kg | 15,000 lb |
| **Mínimo pesable (20e)** | 0,040 kg | 0,040 kg | 0,100 lb |
| **Máximo pesable** | 30,000 kg | 30,000 kg | 60,000 lb |
| **Máxima indicación negativa** | −0,040 kg | −0,040 kg | −0,100 lb |
| **Indicación sobre máximo** | **0e** (estricto) | 9e = 0,090 kg | 9e = 0,180 lb |
| **Tara en PLUs (5% Máx)** | 1,500 kg | 1,500 kg | 3,000 lb |
| **Cero inicial (auto-zero)** | **3,000 kg** | 1,000 kg | 1,000 lb |
| **Congelados** | **No** | Sí | Sí |
| **Escurridos** | Sí | Sí | Sí |

### 22.2 Implicaciones críticas para la suite

#### tolerance_g mínimo por rango de capacidad

La resolución metrológica (e) define el floor de `tolerance_g`. Si la API retorna valores redondeados a la división (como requiere la metrología), `poll_until_stable()` con `tolerance_g < e` nunca convergerá.

| Capacidad | e (resolución) | tolerance_g mínimo seguro |
|-----------|---------------|--------------------------|
| 6 kg (AR/BR) | 2g | **≥ 2,5g** (1.25× e) |
| 15 kg (AR/BR) | 5g | ≥ 6g |
| 30 kg (AR/BR) | 10g | ≥ 12g |
| 15 lb (US) | ~2,3g equiv. | ≥ 3g |

> ⚠️ **Bug identificado:** el valor actual `tolerance_g: 1.0` en `hardware_params.yaml` está por debajo de la resolución del instrumento para todos los rangos. El Sprint 0 debe verificar si `GET /api/weight` retorna resolución sub-división (raw ADC) o redondeada a `e`. El valor safe-floor provisional es `tolerance_g: 2.5` (rango 6kg).

> **Verificación Sprint 0:** graficar el CSV de estabilización. Si los valores saltan en pasos de 0.002 kg exactos → API retorna redondeado a `e` → `tolerance_g` debe ser ≥ 2g. Si los saltos son menores → API retorna resolución mayor → `tolerance_g: 1.0` es válido.

#### Sobrecarga: el umbral varía por variante

| Variante | Capacidad activa | Umbral de sobrecarga |
|----------|-----------------|----------------------|
| AR 🇦🇷 | 6 kg | > 6,000 kg (estricto — 0e) |
| BR 🇧🇷 | 6 kg | > 6,090 kg (9e de gracia) |
| US 🇺🇸 | 15 lb | > 15,180 lb (9e de gracia) |

El test `test_sobrecarga.py` debe leer el umbral del perfil metrológico de la variante, no hardcodearlo.

#### Cero inicial de AR (3 kg) afecta clean_state

En AR, la balanza puede auto-cerar hasta 3 kg de carga residual al arranque y vía la tecla CERO. Esto significa que `assert final_w < 0.003` puede pasar aunque haya carga real sobre la bandeja si el dispositivo la absorbió en el cero.

**Mitigación para AR:** después del teardown, verificar también que el indicador de "peso bajo" o "cero aplicado" no esté activo. Esto requiere VNC — si VNC no está disponible, documentar la limitación como known issue para la variante AR.

#### Congelados no disponible en AR

Tests de venta de congelados deben omitirse automáticamente cuando el perfil activo no soporta la feature. Ver §24 para el patrón completo de skip:

```python
# En el test:
def test_venta_congelados(metrology, ...):
    skip_if_no_frozen(metrology)   # sale con pytest.skip si metrology.frozen_mode == False
```

#### Unidades en US: kg vs. lb

`NEOApiClient.get_weight()` acepta `unit_to_kg` y retorna siempre en kg. El valor correcto proviene de `MetrologyProfile.unit_to_kg` (1.0 para AR/BR, 0.453592 para US). Ver §17 para la implementación completa y §23 para el cálculo del factor de conversión.

```python
# Uso en tests — via poll_until_stable que ya pasa unit_to_kg automáticamente:
w_kg = poll_until_stable(api_client, metrology, expected_weight_kg=1.134)
# → para US: api_client.get_weight(unit_to_kg=0.453592) → 2.5 lb × 0.453592 = 1.134 kg
```

### 22.3 Perfil metrológico en `config/hardware_params.yaml`

Seleccionar variante con `TEST_METROLOGY_PROFILE=AR|BR|US` en `.env.test`. La estructura usa objetos `ranges` (uno por rango de capacidad) con valores en unidades nativas y un factor `unit_to_kg` para conversión centralizada. Esto evita la proliferación de campos `_kg` / `_lb` en los tests.

```yaml
# config/hardware_params.yaml — sección de perfiles metrológicos
metrology:
  AR:
    unit: kg
    unit_to_kg: 1.0
    ranges:
      - capacity_native: 6.0
        division_native: 0.002      # e1 = 2g
      - capacity_native: 15.0
        division_native: 0.005      # e2 = 5g
      - capacity_native: 30.0
        division_native: 0.010      # e3 = 10g
    zero_limit_native: 0.900        # 3% de capacidad máxima
    tare_limit_native: 6.000        # 100% rango 1
    plu_tare_limit_native: 1.500    # 5% capacidad máxima
    above_max_divisions: 0          # 0e de gracia → overload estricto
    initial_zero_native: 3.000      # auto-zero al arranque (más permisivo)
    frozen_mode: false
    drained_mode: true

  BR:
    unit: kg
    unit_to_kg: 1.0
    ranges:
      - capacity_native: 6.0
        division_native: 0.002
      - capacity_native: 15.0
        division_native: 0.005
      - capacity_native: 30.0
        division_native: 0.010
    zero_limit_native: 0.900
    tare_limit_native: 6.000
    plu_tare_limit_native: 1.500
    above_max_divisions: 9          # 9e de gracia = 0.090 kg (rango 6kg)
    initial_zero_native: 1.000
    frozen_mode: true
    drained_mode: true

  US:
    unit: lb
    unit_to_kg: 0.453592
    ranges:
      - capacity_native: 15.0
        division_native: 0.005      # e1 = 5g (~2.3g equiv.)
      - capacity_native: 30.0
        division_native: 0.010
      - capacity_native: 60.0
        division_native: 0.020
    zero_limit_native: 1.800        # 3% de 60 lb
    tare_limit_native: 15.000
    plu_tare_limit_native: 3.000
    above_max_divisions: 9          # 9e de gracia = 0.180 lb (rango 15lb)
    initial_zero_native: 1.000
    frozen_mode: true
    drained_mode: true
```

> **Por qué `unit_to_kg`:** los valores en el YAML viven en unidades nativas (kg para AR/BR, lb para US). `MetrologyProfile` (§23) convierte a kg en un único punto, usando `unit_to_kg`. Los tests nunca hacen la conversión directamente.

### 22.4 Variables de entorno

```bash
# .env.test — agregar:
TEST_METROLOGY_PROFILE=AR    # AR | BR | US — selecciona perfil metrológico activo
```

### 22.5 Fixture de perfil metrológico

```python
# tests/conftest.py
@pytest.fixture(scope="session")
def metrology(hw_config) -> "MetrologyProfile":
    from tests.metrology import MetrologyProfile, build_profile
    variant = os.environ.get("TEST_METROLOGY_PROFILE", "AR")
    raw = hw_config["metrology"].get(variant)
    if not raw:
        pytest.exit(f"Variante desconocida: {variant}. Usar AR, BR o US.")
    return build_profile(variant, raw)
```

### 22.6 Impacto en los parámetros de calibración

La sección `stabilization.tolerance_g` del YAML **se elimina** — pasa a ser responsabilidad de `MetrologyProfile.tolerance_g_for(weight_kg)`. Ver §23 para el cálculo.

| Parámetro | Antes | Después |
|---|---|---|
| `stabilization.tolerance_g` | 1.0 (hardcodeado, incorrecto) | **eliminado** — derivado por profile |
| `ready_state.max_weight_kg` | 0.003 | 0.003 (correcto — < min_weighable) |
| `calibration.drift_tolerance_g` | 20 | 20 (correcto — 10× e1) |

---

## 23. MetrologyProfile — dataclass de perfil metrológico

`MetrologyProfile` es el único lugar en el código que conoce las reglas metrológicas. Los tests la reciben vía fixture y nunca acceden al YAML directamente. Ubicación: `tests/metrology.py`.

```python
# tests/metrology.py
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class MetrologyRange:
    """Un rango de capacidad de la balanza con su resolución (e)."""
    capacity_kg: float        # capacidad del rango en kg
    division_kg: float        # resolución e en kg

    @property
    def tolerance_g_floor(self) -> float:
        """Tolerance mínimo seguro para poll_until_stable(): 1.25 × e en gramos."""
        return self.division_kg * 1000 * 1.25


@dataclass(frozen=True)
class MetrologyProfile:
    """
    Perfil metrológico completo de una variante NEO-2.
    Todos los valores están en kg, independientemente de la unidad nativa.
    """
    variant: str
    unit: str                         # "kg" | "lb" — unidad nativa del device
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
        Tolerance mínimo seguro para poll_until_stable() al medir ese peso.
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
    f = raw["unit_to_kg"]   # factor nativo → kg
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
```

### Ejemplos de uso

```python
# En tests — usando el fixture metrology (ver §22.5):

# ¿Qué tolerancia usar para un peso de 500g?
tol = metrology.tolerance_g_for(0.5)   # → 2.5g (AR/BR rango 6kg: 1.25×2g=2.5g)

# ¿A qué peso exacto debe activarse overload para el rango de 6kg?
threshold = metrology.overload_threshold_kg(6.0)
# → AR: 6.000 + 0×0.002 + 0.002 = 6.002 kg
# → BR: 6.000 + 9×0.002 + 0.002 = 6.020 kg

# ¿Cuál es el mínimo pesable?
min_w = metrology.min_weighable_kg()   # → 0.040 kg (AR/BR), 0.100 lb conv. (US)

# Convertir valor de la API (lb) a kg:
w_kg = metrology.normalize_to_kg(2.5)  # US: 2.5 lb → 1.134 kg

# ¿Soporta congelados?
if not metrology.frozen_mode:
    pytest.skip(f"Congelados no disponible en {metrology.variant}")
```

### Tabla de resultados por variante

| Consulta | AR | BR | US |
|---|---|---|---|
| `tolerance_g_for(0.5)` | 2.5g | 2.5g | 2.9g |
| `overload_threshold_kg(6.0)` | 6.002 kg | 6.020 kg | — (US en lb) |
| `min_weighable_kg()` | 0.040 kg | 0.040 kg | 0.045 kg |
| `initial_zero_kg` | 3.000 kg | 1.000 kg | 0.454 kg |
| `frozen_mode` | False | True | True |

---

## 24. assertions.py — aserciones metrológicamente correctas

Las aserciones de pesaje deben conocer la resolución del instrumento. `assertions.py` centraliza esta lógica para que los tests expresen intención, no cálculos.

```python
# tests/assertions.py
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
```

### Patrones de skip por feature

Para features que no están disponibles en todas las variantes, usar funciones de skip con mensaje informativo:

```python
# tests/conftest.py — helpers de skip (agregar junto a los fixtures)

def skip_if_no_frozen(profile: MetrologyProfile):
    if not profile.frozen_mode:
        pytest.skip(
            f"Modo congelados no disponible en variante {profile.variant}. "
            "Solo disponible en BR y US."
        )

def skip_if_no_drained(profile: MetrologyProfile):
    if not profile.drained_mode:
        pytest.skip(f"Modo escurridos no disponible en variante {profile.variant}.")
```

```python
# Uso en tests:
def test_venta_congelados(metrology, weight_actuator, api_client, weight_calibration):
    skip_if_no_frozen(metrology)
    # ... resto del test sin condiciones adicionales

def test_tara_sobre_limite(metrology, weight_actuator, api_client):
    # Verificar que la balanza rechaza una tara excesiva
    tara_excesiva_kg = metrology.tare_limit_kg + 0.100
    weight_actuator.set(int(tara_excesiva_kg * 1000))
    poll_until_stable(api_client, metrology, expected_weight_kg=tara_excesiva_kg)
    # Presionar TARA con ese peso — debe rechazarlo
    keyboard.press(Key.f1)   # TARA
    time.sleep(0.5)
    state = api_client.get_product()
    assert state.get("tare", 0) < tara_excesiva_kg, "Balanza no rechazó tara excesiva"
```

### Tests de overload con umbral dinámico

```python
# tests/vnc/pesaje/test_sobrecarga.py
def test_overload_activa(metrology, weight_actuator, api_client, weight_calibration):
    """La balanza debe indicar sobrecarga al superar la capacidad del rango activo."""
    capacity_kg = metrology.ranges[0].capacity_kg   # rango menor activo
    overload_kg = metrology.overload_threshold_kg(capacity_kg)

    # Necesitamos superar el umbral — con las pesas DOLZ disponibles
    # Si 3.7 kg < umbral, el test es inválido para esa variante con las pesas actuales
    if weight_calibration.get("3700") and weight_calibration["3700"] < overload_kg:
        pytest.skip(
            f"Pesas disponibles (3.7 kg) insuficientes para sobrecarga "
            f"en {metrology.variant} (umbral {overload_kg:.3f} kg). "
            "Agregar pesa de 5 kg o más."
        )

    # Con pesas suficientes: usar la combinación que supere el umbral
    target_g = int(overload_kg * 1000) + 100   # 100g sobre el umbral
    weight_actuator.set(target_g)
    measured = poll_until_stable(api_client, metrology, expected_weight_kg=overload_kg)
    assert_overload_triggered(measured, capacity_kg, metrology)
```

---

*Documento generado por el equipo de I+D — CUORA NEO Automation Suite v2*  
*Revisión arquitectónica: 2026-05-07*  
*Datos metrológicos incorporados: 2026-05-07*  
*Para consultas técnicas sobre hardware, ver `riel-actuador.svg` en el mismo directorio.*
