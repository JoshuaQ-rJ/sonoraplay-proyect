# SonoraPlay Regalías

Plataforma de datos que decide qué reproducciones de música son válidas y, con ellas, liquida las regalías de los titulares (sellos, distribuidoras y sociedades de gestión) de **SonoraPlay Media**, un servicio de streaming ficticio con 900 mil suscriptores en Latinoamérica.

Proyecto 08 del programa de ingeniería de datos de Riwi. Equipo: Joshua Quintero, María Clara Manjarrés y Andrea Zárate.

> **Estado:** Sprint 1 (descubrimiento y diseño) terminado. En `develop` están EG-10 a EG-18 con los ADR 0001–0005 y 0020:
>
> - EG-10: repositorio base, CI y detección de secretos.
> - EG-11: ambigüedades de las reglas de negocio y supuestos.
> - EG-12: catálogo F1 limpio y titulares.
> - EG-13: seed F3 de suscripciones.
> - EG-14: seed F4 de contratos.
> - EG-15: esquema JSON de eventos F2.
> - EG-16: arquitectura v1 y registro de ADR.
> - EG-17: RN-01 y RN-02 (validez y tope diario).
> - EG-18: RN-03 (detección de granjas).
>
> Falta fusionar `develop` en `main` con la etiqueta `v0.1.0-sprint1`.

---

## Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| [Git](https://git-scm.com/) | 2.40 o superior | Control de versiones |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | 0.8 o superior | Instala Python 3.12 y las dependencias |
| [Docker Desktop](https://docs.docker.com/desktop/) | Reciente | PostgreSQL local (a partir de la EG-13) y Gitleaks en pre-commit |

No hace falta instalar Python a mano: uv descarga la versión fijada en `.python-version`.

## Instalación

```bash
git clone https://github.com/JoshuaQ-rJ/sonoraplay-proyect.git
cd sonoraplay-proyect
git checkout develop
uv sync
uv run python -m pre_commit install
```

- `uv sync` crea el entorno `.venv` e instala exactamente las versiones de `uv.lock`.
- `pre_commit install` activa las revisiones automáticas (Ruff y Gitleaks) antes de cada commit. Gitleaks corre en Docker, así que Docker Desktop debe estar encendido al hacer commit.

Copia las variables de entorno y completa los valores. El archivo `.env` **nunca** se sube al repositorio:

```bash
cp .env.example .env
```

> **Windows:** clona el proyecto fuera de OneDrive (por ejemplo, en `C:\dev`). OneDrive bloquea archivos de `.venv` mientras sincroniza y provoca errores de `Acceso denegado`.

## Pruebas y calidad de código

| Qué | Windows | macOS / Linux |
|---|---|---|
| Pruebas | `uv run python -m pytest` | `uv run pytest` |
| Pruebas con cobertura | `uv run python -m pytest --cov=sonoraplay` | `uv run pytest --cov=sonoraplay` |
| Lint | `uv run python -m ruff check .` | `uv run ruff check .` |
| Formato (revisar) | `uv run python -m ruff format --check .` | `uv run ruff format --check .` |
| Formato (corregir) | `uv run python -m ruff format .` | `uv run ruff format .` |

> En Windows se usa `python -m` porque el Control de aplicaciones puede bloquear los ejecutables que uv crea en `.venv\Scripts\`.

## Seed F3 de suscripciones (EG-13)

Seed reproducible e idempotente de la base F3 de suscripciones (PostgreSQL 16).

```bash
cp .env.example .env            # y cambia POSTGRES_PASSWORD
uv sync
docker compose up -d --wait     # aplica db/ddl/ al crear el volumen
uv run --env-file .env python -m sonoraplay.seed --modo dev        # 10.000 usuarios
uv run --env-file .env python -m sonoraplay.seed --modo completo   # 900.000 usuarios
uv run --env-file .env python -m pytest tests/seed -v
```

Opciones: `--semilla N` (por defecto `SEED`=42), `--usuarios N`, `--tasa-defectos 0.02`.

Si el puerto 5432 está ocupado, cambia `PG_PORT` y el puerto de las dos URLs en `.env`. Para RDS (Sprint 3, EG-28) solo cambia `DATABASE_URL`.

Comportamientos a conocer:

1. El volumen es un objetivo: la última familia puede sumar hasta 5 usuarios extra; dev es prefijo exacto de completo.
2. Otra semilla sobre una base cargada agrega un segundo conjunto de datos aparte.
3. Cambiar la tasa de defectos exige base vacía (`docker compose down -v`): las filas existentes no se actualizan.
4. Si cambias el DDL, corre `docker compose down -v` (el entrypoint solo aplica scripts con el volumen vacío).

Modelo y decisiones: `docs/datos/modelo-f3.md`.

## Catálogo F1 (EG-12)

Limpia el catálogo de pistas (F1): una fila por `track_id`, género principal, tabla puente de géneros y un titular de derechos por artista. Decisión y cifras en [ADR-0003](docs/adr/0003-duplicados-f1.md); exploración en `notebooks/01_exploracion_f1.ipynb`.

1. Descarga el CSV del [Spotify Tracks Dataset](https://www.kaggle.com/datasets/maharshipandya/-spotify-tracks-dataset) (Kaggle, 114.000 filas) y guárdalo como `data/raw/dataset.csv`. `data/raw/` y `data/processed/` no se suben al repositorio.
2. Corre el pipeline:

```bash
uv run python -m sonoraplay.catalogo     # Windows y macOS / Linux
```

Escribe en `data/processed/`:

| Archivo | Contenido |
|---|---|
| `catalogo_f1.parquet` | Una fila por `track_id`, con `genero_principal`, `artista_principal` y `titular_id` |
| `track_generos.parquet` | Tabla puente (`track_id`, `genero`) con todos los géneros de cada pista |
| `titulares.parquet` | 1.500 titulares (sello, distribuidora o sociedad de gestión) con UUID determinista |

Opciones: `--entrada`, `--salida`, `--titulares N` (por defecto 1.500) y `--semilla N` (por defecto 42). La misma semilla produce exactamente los mismos archivos.

Las pruebas (`tests/catalogo`) usan solo la muestra versionada `data/samples/f1_muestra.csv` (200 filas con los casos difíciles). Para regenerarla: `uv run python -m sonoraplay.catalogo.muestra`.

## Seed F4 de contratos (EG-14)

Carga en PostgreSQL los titulares de derechos y sus contratos: el % de cada pista con su vigencia (RN-07, con cambios a mitad de mes), una condición territorial opcional que se suma a la general (Q7) y las exclusiones por país (RN-08). Lee los titulares y las pistas del catálogo F1, así que **primero hay que correr el catálogo**:

```bash
uv run python -m sonoraplay.catalogo
uv run --env-file .env python -m sonoraplay.seed.f4_contratos
uv run --env-file .env python -m pytest tests/seed/test_seed_f4.py -v
```

Opciones: `--datos-f1` (carpeta con `titulares.parquet` y `catalogo_f1.parquet`; por defecto `data/processed`) y `--semilla N` (por defecto 42). Es idempotente: reejecutarlo no duplica filas.

Modelo y reglas: [docs/datos/modelo-f4.md](docs/datos/modelo-f4.md).

## API de contratos F4 (EG-20)

API interna con FastAPI y SQLModel. Spark la consulta para obtener el % vigente de un titular en una fecha (RN-07), con su condición territorial (Q7) y sus exclusiones (RN-08). Mapea las tablas F4 de la EG-14 sin modificar el DDL. No pasa por el ALB: en AWS se llama por DNS privado.

| Endpoint | Para qué |
|---|---|
| `GET /health` | Estado de la API y de PostgreSQL (503 si la base no responde) |
| `GET /titulares/{titular_id}/porcentaje?fecha=YYYY-MM-DD&track_id=&pais=` | % vigente en la fecha |
| `GET /titulares/{titular_id}/condiciones?limit=&offset=` | Períodos de vigencia y exclusiones, paginados |

```bash
# Local (requiere PostgreSQL con el seed F4 cargado)
uv run --env-file .env python -m uvicorn sonoraplay.api_contratos.main:app --port 8000
# Abrir http://localhost:8000/docs

# En Docker
docker compose up -d --build api-contratos
curl http://localhost:8000/health

# Pruebas
uv run --env-file .env python -m pytest tests/api_contratos -v
```

Reglas, ejemplos de request y response y despliegue: [docs/servicios/api-contratos.md](docs/servicios/api-contratos.md).

## Eventos F2 (EG-15)

Esquema JSON (draft 2020-12) de los eventos de reproducción: `schemas/f2_evento.schema.json`. Campos, defectos inyectados y cómo se reconstruye una reproducción a partir de los eventos: `docs/datos/eventos-f2.md`. Deduplicación por `event_id`: [ADR-0004](docs/adr/0004-esquema-eventos-f2.md).

```bash
uv run pytest tests/schemas -v     # ejemplos válidos, inválidos y con defectos
```

## Reglas de negocio (EG-17, EG-18)

RN-01 (reproducción válida: 30 s continuos), RN-02 (tope diario por pista y usuario) y RN-03 (señales de granja) son funciones puras en `src/sonoraplay/reglas/` (`validez.py` y `fraude.py`), sin base de datos ni Spark, para probarlas en aislamiento y reutilizarlas en la capa Silver. Los umbrales están en `src/sonoraplay/config.py` y se justifican en [ADR-0002](docs/adr/0002-zona-horaria-dia-mes.md) (día y mes en UTC) y [ADR-0005](docs/adr/0005-umbrales-granjas.md) (umbrales de granja).

```bash
uv run python -m pytest tests/reglas -v
```

## Integración continua

Cada push a `main` o `develop`, y cada Pull Request, ejecuta tres revisiones en GitHub Actions (`.github/workflows/ci.yml`):

| Job | Qué revisa |
|---|---|
| `lint` | Estilo y errores comunes con Ruff (PEP 8) |
| `test` | Pruebas automatizadas con pytest y cobertura |
| `secretos` | Credenciales expuestas con [Gitleaks](https://github.com/gitleaks/gitleaks) |

`main` y `develop` están protegidas: solo reciben cambios por Pull Request, con **1 aprobación** y los **3 jobs en verde**.

## Flujo de trabajo

### Ramas

| Rama | Uso |
|---|---|
| `main` | Lo entregado al final de cada sprint |
| `develop` | Integración diaria (rama por defecto) |
| `feature/EG-XX-descripcion-corta` | Una por historia de Jira; sale de `develop` actualizado |

Para empezar una historia:

```bash
git checkout develop
git pull
git checkout -b feature/EG-17-rn01-rn02
```

### Commits

Formato [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/) con la clave de Jira al final:

```text
feat(reglas): RN-01 validez de 30 segundos [EG-17]
fix(seed): evita duplicados al reejecutar [EG-13]
docs(adr): ADR-0003 duplicados de F1 [EG-12]
```

Tipos: `feat`, `fix`, `test`, `docs`, `chore`, `ci`, `style`, `refactor`.

### Definition of Done

Un ítem se cierra en Jira solo si:

- [ ] El código está en `develop` y lo revisó otra persona del equipo.
- [ ] Tiene pruebas automatizadas que pasan, incluida la de su RN o CA.
- [ ] El CI está en verde y no expone secretos.
- [ ] Si implicó una decisión técnica, su ADR está escrito en la misma historia.
- [ ] La documentación que toca está actualizada.
- [ ] La rama, los commits y el PR citan la clave de Jira.

## Secretos

- Las credenciales **nunca** van en el código ni en commits.
- En local van en `.env` (ignorado por Git); en el repositorio solo existe `.env.example`, con los nombres de las variables.
- En AWS (desde el Sprint 3) van en SSM Parameter Store.
- Si Gitleaks detecta un secreto en un PR, el merge queda bloqueado. Una credencial real expuesta se revoca de inmediato, aunque luego se borre del código.

## Estructura del repositorio

```text
.github/
  workflows/ci.yml             CI: lint, pruebas y secretos
  pull_request_template.md     Checklist de la Definition of Done
db/ddl/                        DDL de PostgreSQL (se aplica al crear el volumen)
docs/analisis/                 Ambigüedades de las reglas de negocio y supuestos (EG-11)
docs/arquitectura/             Arquitectura v1 y diagrama (EG-16)
docs/adr/                      Registro de decisiones de arquitectura (ADR)
docs/datos/                    Modelos de datos y decisiones
docs/servicios/                Documentación de los servicios (API de contratos F4)
docker/                        Dockerfiles por componente (api-contratos)
schemas/                       Esquema JSON de eventos F2 y ejemplos
src/sonoraplay/                Código del paquete (src layout)
src/sonoraplay/config.py       Parámetros de negocio y umbrales centralizados
src/sonoraplay/reglas/         RN-01, RN-02 y RN-03 como funciones puras
src/sonoraplay/seed/           Seeds F3 (suscripciones) y F4 (contratos)
src/sonoraplay/api_contratos/  API de contratos F4 (FastAPI + SQLModel)
src/sonoraplay/catalogo/       Limpieza del catálogo F1 y titulares
data/samples/                  Muestras pequeñas versionadas para pruebas
notebooks/                     Exploración de datos
tests/                         Pruebas con pytest
docker-compose.yml             PostgreSQL 16 local y la API de contratos F4
.dockerignore                  Lo que nunca entra a una imagen (.env, .venv, datos)
.env.example                   Variables de entorno sin valores reales
.pre-commit-config.yaml        Revisiones antes de cada commit (Ruff y Gitleaks)
LICENSE                        Licencia MIT
pyproject.toml                 Proyecto, dependencias y configuración de Ruff y pytest
uv.lock                        Versiones exactas de las dependencias
```

Se irán agregando con sus historias desde el Sprint 2: los servicios, `spark/`, `dags/` e `infra/terraform/`.

## Documentación

- Arquitectura: [docs/arquitectura/arquitectura-v1.md](docs/arquitectura/arquitectura-v1.md) (EG-16).
- Decisiones de arquitectura: [registro de ADR](docs/adr/README.md). El entorno AWS está apagado por defecto y solo se prende en ventanas de prueba y la semana de la demo ([ADR-0020](docs/adr/0020-ventanas-encendido-aws.md)).
- Supuestos de las reglas de negocio: [docs/analisis/ambiguedades-rn.md](docs/analisis/ambiguedades-rn.md) (EG-11).
- Tablero del proyecto: Jira, proyecto **EG**.
