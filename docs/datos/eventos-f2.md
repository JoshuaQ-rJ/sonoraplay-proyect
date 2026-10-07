# Eventos F2 · Reproducciones (HU 06 · EG-15)

Fuente F2 de SonoraPlay: los eventos que envía la app cada vez que una reproducción empieza, se pausa, se reanuda, se salta o termina. Con ellos se reconstruyen las reproducciones que evalúan RN-01/RN-02 (EG-17), RN-03 (EG-18) y RN-04 (EG-22).

- Esquema: [`schemas/f2_evento.schema.json`](../../schemas/f2_evento.schema.json) (JSON Schema draft 2020-12).
- Decisiones (deduplicación por `event_id`, UTC con `Z`, versionado): [ADR-0004](../adr/0004-esquema-eventos-f2.md).
- Ejemplos: `schemas/ejemplos/validos/` (uno por `event_type`), `invalidos/` y `defectos/`.
- Pruebas: `tests/schemas/test_evento_f2.py`.

## Cómo validar

```python
import json
from jsonschema import Draft202012Validator, FormatChecker

esquema = json.load(open("schemas/f2_evento.schema.json", encoding="utf-8"))
validador = Draft202012Validator(esquema, format_checker=FormatChecker())
validador.validate(evento)  # lanza ValidationError si el formato es incorrecto
```

Sin `format_checker`, jsonschema **no** revisa `uuid` ni `date-time`. Además, `date-time` solo se revisa si está instalado `rfc3339-validator`; hoy llega con el grupo dev, así que en producción el patrón con `Z` es la garantía mínima de UTC y la prueba `test_format_checker_valida_de_verdad_uuid_y_date_time` avisa si el checker deja de funcionar (ADR-0004).

## Campos

Todos son **obligatorios** y no se admiten campos extra (`additionalProperties: false`). El esquema describe el evento **tal como queda en la cola**, después de que la API de ingesta le añade `server_ts`.

| Campo | Tipo y restricción | Ejemplo | Para qué / regla que lo usa |
|---|---|---|---|
| `schema_version` | string, `const "1.0"` | `"1.0"` | Versionado del contrato. Un cambio incompatible crea `"2.0"` (ADR-0004). |
| `event_id` | string, `format: uuid` | `"c7e1d0a4-0001-4f2b-9a6e-5b3c2d1e0f01"` | Lo genera el dispositivo; un reintento reenvía el mismo. Llave de **deduplicación** (RNF-04, ADR-0004). |
| `event_type` | enum `start`, `pause`, `resume`, `skip`, `end` | `"pause"` | Abre y cierra los tramos continuos de RN-01. |
| `user_id` | string, `format: uuid` | `"3b6f1a2c-5d4e-4f7a-9b8c-1d2e3f4a5b6c"` | Cuenta que escucha = `usuario_id` de F3. RN-02 (tope por usuario y día), RN-03 (señales por cuenta), RN-10 (cuenta familiar, país de facturación). |
| `device_id` | string de 1 a 64, `^[A-Za-z0-9_-]+$` | `"android-7f3a9c21"` | RN-03 señal 3 (dispositivo con más de 5 cuentas). Es opaco: no está en F3. |
| `track_id` | string, `^[0-9A-Za-z]{22}$` | `"23Mcmg5O8rBKAOzxvrTjnD"` | Pista del catálogo F1 → artista y titular. RN-01/RN-02 (por pista), RN-03 señal 2 (artista). Que exista en F1 se revisa en calidad de datos. |
| `session_id` | string, `format: uuid` | `"a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"` | Agrupa los eventos de **una** reproducción de **un** track (de su `start` a su `end` o `skip`). |
| `device_ts` | string `date-time` en UTC con `Z` | `"2026-09-15T14:00:45.000Z"` | Momento real del evento según el dispositivo. Define el día (RN-02) y el mes (RN-04, RN-05, RN-07) en UTC (ADR-0002). |
| `server_ts` | string `date-time` en UTC con `Z` | `"2026-09-15T14:00:45.210Z"` | Cuándo lo recibió la API de ingesta. Corte offline de RN-04 (día 2, 23:59 UTC) y detección de relojes desfasados. |
| `position_ms` | entero ≥ 0 | `45000` | Posición dentro del track en el momento del evento. La diferencia entre eventos da los ms escuchados (RN-01, RN-03 señal 1). |
| `country_playback` | string, `^[A-Z]{2}$` (ISO 3166-1 alfa-2) | `"CO"` | País donde se reproduce: exclusiones territoriales (RN-08) y analítica. **No** define la bolsa: esa la define el país de facturación de F3 (EG-11 Q6, ADR-0008). |
| `is_offline` | boolean | `false` | `true` si se escuchó sin conexión y se sincronizó después (RN-04). |

**Restricciones que van más allá del formato JSON:**

- `device_ts` y `server_ts` **deben** terminar en `Z`. Un desfase como `-05:00` es una fecha válida en RFC 3339, pero el patrón lo rechaza (ADR-0002, regla 1).
- `country_playback` solo valida el formato (dos letras mayúsculas), no que el código exista; la lista de países se revisa en calidad de datos.
- No hay campo de duración ni de artista: la duración sale de `position_ms` y el artista del catálogo F1.

### Contrato de la app para RN-01

Un **seek** (saltar a otra parte del track) no tiene `event_type` propio: la app lo envía como `pause` en la posición de origen seguido de `resume` en la posición de destino. Así un seek antes de los 30 s abre un tramo nuevo, como pide EG-11 Q1.

## Ejemplos

| Carpeta | Contenido | Qué se prueba |
|---|---|---|
| `validos/` | `start`, `pause`, `resume`, `end` de una misma sesión online, y un `skip` offline sincronizado el 2-oct (RN-04) | Pasan el esquema; hay uno por `event_type` |
| `invalidos/` | El `start` válido con una sola mutación: sin `event_id`, sin `server_ts`, `event_type` desconocido (`seek`), `position_ms` negativa o decimal, `event_id` que no es UUID, `device_ts` sin zona o con desfase `-05:00`, fecha imposible (30-feb), país en minúsculas o de 3 letras, `track_id` vacío, `is_offline` como texto, `schema_version` desconocida, campo extra | Fallan el esquema |
| `defectos/` | Un archivo por defecto de negocio (ver abajo), con `defecto`, `descripcion`, `contexto` y `eventos` | Cada evento **pasa** el esquema y el defecto está presente |

## Defectos inyectados

Son defectos de **negocio**, no de formato: todos sus eventos pasan el esquema y se detectan al reconstruir las reproducciones o al cruzar con F1 y F3.

| Defecto | Archivo | Cómo se ve en los eventos | Cómo se detecta y trata |
|---|---|---|---|
| Evento sin fin | `evento_sin_fin.json` | `start` → `pause` → `resume` y nunca llega `end` ni `skip` | Al cerrar la sesión el último tramo queda abierto: cuenta **0 ms** (no se puede saber cuánto duró) y la reproducción se marca `sin_fin`. Los tramos cerrados sí cuentan. |
| Reloj del dispositivo desfasado | `reloj_desfasado.json` | Evento online (`is_offline=false`) con `device_ts` 3 h antes que `server_ts` | En un evento online `server_ts − device_ts` debería ser de milisegundos. Si supera la tolerancia se corrige `device_ts` con ese desfase (RN-04, ADR-0002 regla 2); el umbral y la corrección se fijan en EG-22. |
| Track desconocido | `track_desconocido.json` | `track_id` con formato correcto que no está en F1 | El cruce con el catálogo no encuentra artista ni titular: la reproducción va a cuarentena y no entra en la bolsa ni en RN-03 señal 2. |
| Duplicado por reintento | `duplicado_por_reintento.json` | Dos eventos con el **mismo `event_id`** y el mismo contenido; solo cambia `server_ts` | Se deduplica por `event_id` y se conserva el de menor `server_ts` (ADR-0004). Comparar el evento completo **no** sirve, porque `server_ts` difiere. |
| País de facturación ≠ país de reproducción | `pais_facturacion_distinto.json` | `country_playback = "MX"` para una cuenta que factura en `"CO"` en F3 | Se ve al cruzar `user_id` con F3. No es un error: la reproducción cuenta en la bolsa del país de facturación (EG-11 Q6, ADR-0008) y `country_playback` solo se usa para RN-08 y analítica. |

## De eventos a reproducciones

Este es el contrato que usan EG-17 (RN-01, RN-02) y EG-18 (RN-03). Una **sesión** (`session_id`) produce como máximo **una reproducción**.

### Pasos

1. **Deduplicar** por `event_id`; si se repite, se conserva el de menor `server_ts` (ADR-0004).
2. **Agrupar** por `session_id`. Todos sus eventos deben tener el mismo `user_id`, `device_id` y `track_id`; si no, la sesión va a cuarentena.
3. **Corregir el reloj** de los eventos online desfasados (defecto 2, EG-22) y **ordenar** por `device_ts` corregido; a igual `device_ts`, por `server_ts`.
4. **Armar tramos continuos.** Un tramo **abre** con `start` o `resume` y **cierra** con el siguiente `pause`, `skip` o `end`.
   - ms del tramo = `position_ms` al cerrar − `position_ms` al abrir.
   - Si sale negativo, o si avanza más que el tiempo transcurrido entre los dos `device_ts` (más una tolerancia), el tramo es inconsistente: cuenta `min(Δposition_ms, Δdevice_ts)` y se marca para calidad.
   - Un tramo sin cierre (defecto 1) cuenta 0 ms.
   - Eventos fuera de orden (p. ej. `pause` sin tramo abierto) se ignoran y se marcan.
5. **Resolver el artista** con el catálogo F1: `track_id` → `artista_principal`. Sin coincidencia → cuarentena (defecto 3).
6. **Emitir la reproducción** con los campos de la tabla siguiente.

### Correspondencia con `Reproduccion` (`src/sonoraplay/reglas/fraude.py`)

| Reproducción | Sale de | ¿Existe hoy en `Reproduccion`? |
|---|---|---|
| `cuenta_id` | `user_id` | Sí, **con otro nombre** (F2 usa `user_id`, F3 usa `usuario_id`) |
| `dispositivo_id` | `device_id` | Sí, **con otro nombre** |
| `artista_id` | `track_id` → `artista_principal` del catálogo F1 | Sí, pero **F1 no tiene un id de artista**: hoy es el nombre del artista principal (texto). Dos artistas homónimos se juntarían. |
| `inicio` | `device_ts` corregido del `start`, en UTC | Sí (aware y normalizado a UTC) |
| `ms_escuchados` | **suma** de los ms de todos los tramos | Sí. RN-03 señal 1 lo usa como horas escuchadas. |
| `track_id` | `track_id` | **No.** RN-02 (10 por pista, usuario y día) lo necesita; se agrega en EG-17. |
| `ms_tramo_max` | el **mayor** tramo continuo | **No.** RN-01 lo necesita: válida si ≥ 30 000 ms (EG-11 Q1); se agrega en EG-17. |
| `pais_reproduccion`, `is_offline`, `sincronizado` (`server_ts` del último evento) | `country_playback`, `is_offline`, `server_ts` | **No.** RN-08 y RN-04 (EG-22). |

**Ojo con `Reproduccion.fin`:** se calcula como `inicio + ms_escuchados`, es decir, como si los tramos fueran seguidos. Con pausas largas el fin real es más tarde. Para RN-03 señal 1 la diferencia es menor (cuenta lo escuchado, no lo transcurrido), pero si EG-18 necesita precisión se deberían pasar los tramos en vez de una sola reproducción.

### Ejemplo

La sesión de `schemas/ejemplos/validos/` (`start`, `pause`, `resume`, `end`):

| Evento | `device_ts` | `position_ms` | Tramo |
|---|---|---|---|
| `start` | 14:00:00.000Z | 0 | abre tramo 1 |
| `pause` | 14:00:45.000Z | 45 000 | cierra tramo 1 = **45 000 ms** |
| `resume` | 14:01:30.000Z | 45 000 | abre tramo 2 |
| `end` | 14:04:15.760Z | 210 760 | cierra tramo 2 = **165 760 ms** |

Resultado: `cuenta_id = 3b6f1a2c-…`, `dispositivo_id = android-7f3a9c21`, `track_id = 23Mcmg5O8rBKAOzxvrTjnD`, `artista_id = "Kitri"`, `inicio = 2026-09-15T14:00:00Z`, `ms_escuchados = 210 760`, `ms_tramo_max = 165 760` → válida para RN-01.

En `evento_sin_fin.json` el tramo 1 cierra con 40 000 ms y el tramo 2 queda abierto (0 ms): `ms_escuchados = 40 000`, `ms_tramo_max = 40 000` → válida para RN-01 aunque nunca llegó el `end`, y marcada `sin_fin`.
