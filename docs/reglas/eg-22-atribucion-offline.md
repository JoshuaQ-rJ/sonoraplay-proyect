# EG-22 · Offline play attribution (RN-04) / Atribución de reproducciones offline

> **Versión vigente:** [docs/datos/atribucion-offline.md](../datos/atribucion-offline.md) (en español). Este documento describe la primera versión de la EG-22: no incluye la primera liquidación abierta para ajustes muy tardíos ni la corrección del reloj por sesión.

## English — Academic documentation

### Objective
Implement a deterministic, pure Python rule that attributes an offline play to its actual UTC playback month when it is synchronized before the configured cutoff, or identifies a late synchronization as an adjustment without reopening a closed month.

### Inputs and outputs
`atribuir_reproduccion(reproducida_en, sincronizada_en, es_offline, cfg, *, reproducida_corregida_en=None)` accepts timezone-aware playback and synchronization timestamps, an offline flag, the immutable `AtribucionOfflineConfig`, and an optional previously corrected playback timestamp. It returns `ResultadoAtribucion`: actual playback month, settlement month, and `normal` or `ajuste`. Months are represented by their first calendar day in UTC.

### Rule and boundary
The cutoff is day 2 of the following month at 23:59 UTC, **inclusive of the whole 23:59 minute**. A September 28 play synchronized on October 2 at 23:59:59 UTC remains in September; synchronization on October 3 at 00:00 UTC is an October adjustment. Same-month synchronization is normal. For a late arrival, the result preserves the original playback month while indicating the settlement month in which the adjustment must be processed. This pure function does not itself write or modify any settlement.

### Clock correction
`corregir_reloj_online` compares an online device timestamp with the server timestamp; when the absolute difference exceeds the configurable tolerance (60 seconds by default), it returns the server timestamp. An offline playback cannot safely infer its original time from a much later server receipt; therefore the caller must supply a reliable corrected playback timestamp using `reproducida_corregida_en`. This function **does not implement device clock-offset estimation for offline events**. The upstream correction strategy must be validated by the integration team.

### Configuration and design
The cutoff day, hour, minute and online clock tolerance are in `src/sonoraplay/config.py`. All date calculations use UTC, consistent with ADR-0002. The rule is pure: no I/O, database writes, current system clock or mutable global state.

### Verification
`tests/reglas/test_atribucion.py` covers on-time and late synchronization, the minute before and after the cutoff, same-month synchronization, online behavior, corrected timestamps, UTC conversion, missing time zones, invalid chronology and year rollover. GitHub Actions runs tests, Ruff lint/format and secret scanning. Record the latest successful run before marking the PR ready for review.

### Files
- `src/sonoraplay/config.py` — configuration.
- `src/sonoraplay/reglas/atribucion.py` — pure rule.
- `tests/reglas/test_atribucion.py` — automated tests.
- `docs/adr/0002-zona-horaria-dia-mes.md` — UTC decision.

## Español — Documentación académica

### Objetivo
Implementar una regla pura y determinista en Python que atribuya una reproducción offline a su mes real de escucha en UTC si se sincroniza antes del corte configurado, o que identifique una sincronización tardía como ajuste sin reabrir un mes cerrado.

### Entradas y salidas
`atribuir_reproduccion(reproducida_en, sincronizada_en, es_offline, cfg, *, reproducida_corregida_en=None)` recibe las fechas de reproducción y sincronización con zona horaria, un indicador offline, la configuración inmutable `AtribucionOfflineConfig` y una fecha corregida opcional. Devuelve `ResultadoAtribucion`: mes real de reproducción, mes de liquidación y estado `normal` o `ajuste`. Los meses se representan mediante su primer día en UTC.

### Regla y límite
El corte ocurre el día 2 del mes siguiente a las 23:59 UTC e **incluye todo el minuto 23:59**. Una reproducción del 28 de septiembre sincronizada el 2 de octubre a las 23:59:59 UTC pertenece a septiembre; si llega el 3 de octubre a las 00:00 UTC, se trata como ajuste de octubre. Una sincronización dentro del mismo mes es normal. Para llegadas tardías se conserva el mes real y se indica el mes de liquidación del ajuste. La función pura no modifica liquidaciones por sí misma.

### Corrección del reloj
`corregir_reloj_online` compara el timestamp de un evento online con el del servidor; si la diferencia absoluta supera la tolerancia configurable (60 segundos por defecto), devuelve el timestamp del servidor. En eventos offline no es correcto deducir la hora original usando una recepción ocurrida mucho después; por eso quien invoque la función debe aportar una hora corregida confiable mediante `reproducida_corregida_en`. Esta función **no estima automáticamente el desfase del reloj en eventos offline**. El equipo debe validar cómo se obtendrá esa corrección al integrar los eventos.

### Configuración y diseño
El día, hora y minuto del corte y la tolerancia del reloj online están en `src/sonoraplay/config.py`. Los cálculos se hacen en UTC, de acuerdo con ADR-0002. La regla es pura: no lee ni escribe archivos, no consulta bases de datos ni utiliza el reloj del sistema.

### Verificación
`tests/reglas/test_atribucion.py` comprueba sincronización oportuna y tardía, minutos anterior y posterior al corte, mismo mes, eventos online, fechas corregidas, conversiones UTC, zonas ausentes, cronología inválida y cambio de año. GitHub Actions ejecuta pruebas, Ruff y revisión de secretos. Antes de solicitar revisión debe registrarse la última ejecución exitosa.

### Archivos
- `src/sonoraplay/config.py` — configuración.
- `src/sonoraplay/reglas/atribucion.py` — regla pura.
- `tests/reglas/test_atribucion.py` — pruebas automáticas.
- `docs/adr/0002-zona-horaria-dia-mes.md` — decisión de UTC.
