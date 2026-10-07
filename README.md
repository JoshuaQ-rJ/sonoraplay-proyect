# SonoraPlay Regalías

Plataforma de datos que decide qué reproducciones de música son válidas y, con ellas, liquida las regalías de los titulares (sellos, distribuidoras y sociedades de gestión) de **SonoraPlay Media**, un servicio de streaming ficticio con 900 mil suscriptores en Latinoamérica.

Proyecto 08 del programa de ingeniería de datos de Riwi. Equipo: Joshua Quintero, María Clara Manjarrés y Andrea Zárate.

> **Estado:** Sprint 1 (descubrimiento y diseño). Hoy el repositorio tiene la estructura base, el CI y la detección de secretos. El seed, las reglas de negocio y los demás componentes se agregan historia por historia.

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

## Eventos F2 (EG-15)

Esquema JSON (draft 2020-12) de los eventos de reproducción: `schemas/f2_evento.schema.json`. Campos, defectos inyectados y cómo se reconstruye una reproducción a partir de los eventos: `docs/datos/eventos-f2.md`. Deduplicación por `event_id`: [ADR-0004](docs/adr/0004-esquema-eventos-f2.md).

```bash
uv run pytest tests/schemas -v     # ejemplos válidos, inválidos y con defectos
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
docs/datos/                    Modelos de datos y decisiones
schemas/                       Esquema JSON de eventos F2 y ejemplos
src/sonoraplay/                Código del paquete (src layout)
src/sonoraplay/seed/           Generador del seed F3
src/sonoraplay/catalogo/       Limpieza del catálogo F1 y titulares
data/samples/                  Muestras pequeñas versionadas para pruebas
notebooks/                     Exploración de datos
tests/                         Pruebas con pytest
docker-compose.yml             PostgreSQL 16 local
.env.example                   Variables de entorno sin valores reales
.pre-commit-config.yaml        Revisiones antes de cada commit (Ruff y Gitleaks)
LICENSE                        Licencia MIT
pyproject.toml                 Proyecto, dependencias y configuración de Ruff y pytest
uv.lock                        Versiones exactas de las dependencias
```

Se irán agregando con sus historias: `docs/arquitectura/` y `docs/adr/` y, desde el Sprint 2, los servicios, `spark/`, `dags/` e `infra/`.

## Documentación

- Arquitectura y decisiones (ADR): `docs/arquitectura/` y `docs/adr/` (EG-16).
- Tablero del proyecto: Jira, proyecto **EG**.
