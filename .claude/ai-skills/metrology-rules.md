# Metrology Rules — CUORA NEO

## Principio general

El comportamiento de la balanza depende del:
- país
- regulación
- perfil metrológico

No asumir comportamiento universal.

---

# Perfiles soportados

Ejemplos:
- AR
- BR
- US

Cada perfil define:
- rangos
- resolución e/e1/e2/e3
- límites
- sobrecarga
- capacidades funcionales

---

# Resolución metrológica

La tolerancia depende del:
- rango activo
- e vigente

Está prohibido usar:
- tolerancias fijas hardcodeadas

Ejemplo incorrecto:

```python
tolerance_g = 1
```

La tolerancia debe derivarse:
- dinámicamente
- desde el perfil metrológico activo

---

# Overload behavior

El comportamiento de sobrecarga cambia por región.

Ejemplo:
- US → +9e
- AR → 0e

Los tests deben validar:
- comportamiento esperado por perfil
- no asumir lógica universal

---

# Features regulatorias

Capacidades como:
- frozen
- drained

dependen del perfil metrológico.

No asumir disponibilidad universal.

---

# Minimum weighable

El mínimo pesable depende de:
- e
- regulación

Debe derivarse desde:
- profile configuration

No hardcodear.

---

# Assertions metrológicas

Toda assertion de peso debe considerar:
- e activo
- rango activo
- perfil metrológico
- tolerancia válida

---

# Configuración

Los perfiles deben vivir:
- fuera del código
- versionados
- centralizados

Los datos de todos los perfiles (AR, BR, US) viven en una única sección del archivo de
configuración del laboratorio. No separar en archivos por región hasta que exista
necesidad concreta (más de ~5 variantes o equipos de trabajo separados por país).

```text
config/hardware_params.yaml
  └── metrology:
        AR: { ranges, unit_to_kg, frozen_mode, ... }
        BR: { ... }
        US: { unit: lb, unit_to_kg: 0.453592, ... }
```

El perfil activo se selecciona con la variable de entorno:

```bash
TEST_METROLOGY_PROFILE=AR   # AR | BR | US
```

La clase `MetrologyProfile` (`tests/metrology.py`) carga este YAML y expone
métodos derivados (`tolerance_g_for`, `overload_threshold_kg`, etc.).
Los tests nunca leen el YAML directamente.

---

# Objetivo

Mantener:
- consistencia regulatoria
- mantenibilidad
- claridad

sin construir un framework regulatorio complejo.