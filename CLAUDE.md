# CUORA NEO Automation Suite

Proyecto HIL para balanza Systel CUORA NEO. Estado actual: **solo diseño — ningún archivo de código existe**.
Leer `AVANCE.md` para estado detallado, próximos pasos y mapa de secciones del plan.

---

## Reglas críticas — no violar

### 1. SSH: prohibido modificar el SO del device

`apt update`, `apt upgrade`, `apt-get install`, `pip install` en el device → **PROHIBIDO**.
El SO tiene customizaciones Systel. Una actualización puede dejarlo inutilizable.
Todos los comandos SSH son solo lectura: `uptime`, `df`, `ps`, `cat logs`, `SELECT` en PostgreSQL.

### 2. API REST = única fuente de valores numéricos

Peso, precio y código PLU se leen **siempre** de la API (`GET /api/weight`, `GET /api/product`).
Nunca leer esos valores por OCR de VNC ni por pantalla.

### 3. VNC = solo observación

VNC siempre en modo view-only. Nunca enviar teclas ni clics por VNC.
`pynput` USB HID es el **único** canal de input hacia la balanza.
VNC + HID simultáneos duplican keystrokes sin error visible.

### 4. Estabilización: `poll_until_stable()`, nunca `time.sleep()` fijo

```python
# Firma actual (§6.5 del plan):
poll_until_stable(api_client, profile, expected_weight_kg, ...)
# profile es obligatorio — determina la tolerancia automáticamente
```

### 5. Tolerancia metrológica: nunca hardcodear

`tolerance_g` siempre desde `profile.tolerance_g_for(weight_kg)` — mínimo 2.5g.
Perfil activo: `TEST_METROLOGY_PROFILE=AR|BR|US` en `.env.test`.
`tolerance_g=1.0` fijo está **por debajo de la resolución del instrumento** en todos los rangos.

---

## Archivos clave

| Archivo | Para qué |
|---|---|
| `AVANCE.md` | Estado del proyecto, próximos pasos, mapa de §§ del plan |
| `plan-automatizacion-cuora-neo.md` | Plan completo (24 secciones) |
| `config/hardware_params.yaml` | Parámetros físicos y timing — **a crear** |
| `tests/metrology.py` | `MetrologyProfile` + `build_profile()` — **a crear** |
| `tests/assertions.py` | `assert_weight`, `assert_overload_triggered` — **a crear** |
| `tests/api_client.py` | `NEOApiClient` — **a crear** |
| `tests/errors.py` | Jerarquía de excepciones tipadas — **a crear** |

---

## Contexto extendido (leer según tarea)

- `.claude/ai-skills/core-architecture.md` — principios generales, ownership por capa
- `.claude/ai-skills/hardware-hil.md` — lifecycle del actuador, pin flotante, anti-backlash
- `.claude/ai-skills/metrology-rules.md` — perfiles AR/BR/US, overload, mínimo pesable
- `.claude/ai-skills/project-evolution-rules.md` — qué NO agregar todavía
