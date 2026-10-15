# BIA Agent Studio — Sprint 2: Agent Management

Monorepo con Next.js 16 (TypeScript, App Router), FastAPI, PostgreSQL 16,
SQLAlchemy 2, Alembic, Pytest y Ruff. Implementa Foundation y Agent Management
de [la arquitectura](docs/architecture.md): agentes, catálogos aprobados,
borradores editables y snapshots inmutables. No incluye LangGraph, RAG,
publicación ni ejecución de agentes. Las decisiones y diferencias respecto
al diseño futuro están en [ADR-010](docs/decisions/ADR-010-agent-management.md).

## Arranque y verificación en macOS

Requisitos: Docker Desktop con Docker Compose v2 o posterior y `make`
(incluido en las herramientas de línea de comandos de Xcode). La primera
ejecución necesita acceso a los registros de imágenes y paquetes. Si `make`
no está disponible, instala las herramientas con `xcode-select --install`.
No necesitas instalar Python, Node ni PostgreSQL en el Mac para este flujo.

Desde Terminal:

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
open -a Docker
# Espera a que Docker Desktop indique que el motor está listo.
docker info
make env
make demo-env
make verify
```

`make env` crea `.env` desde `.env.example` únicamente si no existe.
`make demo-env` añade únicamente las variables de demostración que falten en
un `.env` del Sprint 1, conservando valores existentes. Si has deshabilitado
`ENABLE_DEMO_AUTH`, debes activarlo explícitamente en desarrollo para usar
los registros de este sprint. `make verify` valida Compose, construye y arranca
los servicios, aplica migraciones, carga seeds idempotentes, espera los health
checks y ejecuta:

1. Pytest, incluidas las pruebas reales contra PostgreSQL 16.
2. Ruff (lint y formato).
3. ESLint, TypeScript y pruebas de clientes HTTP y rutas permitidas del frontend.
4. Un smoke test HTTP de frontend → FastAPI → PostgreSQL y Alembic.

El build de producción de Next.js se ejecuta al construir su imagen.
Los servicios quedan disponibles al terminar. Para comprobarlos desde el Mac:

```sh
docker compose ps -a
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/health/ready
curl -fsS http://localhost:3000/health
curl -fsS http://localhost:3000/api/health
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
docker compose exec -T postgres psql -U bia -d bia_studio -c 'SELECT version_num FROM alembic_version;'
open http://localhost:3000
open http://localhost:3000/agents
```

La API de readiness debe devolver:

```json
{"status":"ok","service":"bia-api","database":"ok","migrations":"ok"}
```

La ruta del frontend `/api/health` debe envolver esa respuesta en
`{"health":{...},"error":null}`. La pantalla consulta esa ruta al abrirse y al
pulsar **Actualizar estado**. Los indicadores proceden de la API; no hay
métricas simuladas. La documentación OpenAPI está en `http://localhost:8000/docs`.
El servicio `migrate` debe aparecer como `Exited (0)`; es un trabajo de una sola ejecución.

## Usar Agent Management

Abre `http://localhost:3000/agents` y entra con el valor de
`DEMO_CREATOR_TOKEN` de tu `.env`. El token es local y sintético; permanece solo
en memoria y se pierde al recargar. La identidad se verifica contra hashes en
PostgreSQL; enviar `X-Role` o `X-User-Id` no concede acceso.

1. Crea un agente con ID, nombre, departamento y descripción.
2. Configura objetivo e instrucciones, modelo aprobado, herramientas y límites.
3. Guarda la primera versión; puedes editarla con **Guardar borrador**.
4. Con los cambios guardados, usa **Crear snapshot**. El formulario pasa a solo
   lectura y muestra el hash y el contenido efectivo conservado.
5. Usa **Nueva versión desde esta** para derivar otro borrador. Selecciona las
   versiones en el historial y comprueba que la anterior permanece intacta.
6. Recarga, identifícate de nuevo y comprueba la persistencia.

Las páginas `/models` y `/tools` muestran catálogos reales. El administrador
(`DEMO_ADMIN_TOKEN`) puede registrar definiciones JSON, aprobar, revocar y
eliminar registros sin referencias. Los contratos publicados en el catálogo
son inmutables; para cambiar su definición hay que registrar otra versión.
El visor (`DEMO_VIEWER_TOKEN`) solo puede leer.

Los modelos `synthetic-*` son contratos ficticios; no conectan con proveedores.
Las herramientas `invoice-*` describen esquemas, permisos y políticas, sin
ejecutar operaciones. `invoice-read-v1` requiere `invoices:read`, concedido a
los propietarios sintéticos creator/administrator. Exportación y escritura
permiten comprobar rechazos de permisos; las herramientas de escritura no
pueden asignarse en este sprint. No hay métricas operativas simuladas.

## API y autorización

Todos los endpoints `/api/v1` requieren `Authorization: Bearer <token>`.
Los health checks permanecen públicos. Los tokens se obtienen del entorno de
demostración, nunca del manifiesto del agente. `/docs` documenta los contratos.

| Operación | Endpoint | Autorización |
| --- | --- | --- |
| Identidad actual | `GET /api/v1/me` | Identidad activa |
| Propietarios disponibles | `GET /api/v1/users` | Administrator |
| Inventario, búsqueda y filtros | `GET /api/v1/agents?q=&status=&owner_id=&limit=100&offset=0` | Identidad activa |
| Crear agente | `POST /api/v1/agents` | Creator/administrator; owner actual salvo admin |
| Ver agente | `GET /api/v1/agents/{id}` | Identidad activa |
| Editar metadatos/estado | `PATCH /api/v1/agents/{id}` | Propietario creator o administrator |
| Eliminar sin historial | `DELETE /api/v1/agents/{id}?expected_revision=1` | Propietario creator o administrator |
| Listar/consultar versiones | `GET /api/v1/agents/{id}/versions[/{number}]` | Identidad activa |
| Crear o clonar versión | `POST /api/v1/agents/{id}/versions` | Propietario creator o administrator |
| Editar borrador | `PUT /api/v1/agents/{id}/versions/{number}` | Propietario creator o administrator |
| Congelar configuración | `POST /api/v1/agents/{id}/versions/{number}/snapshot` | Propietario creator o administrator |
| Catálogos aprobados | `GET /api/v1/models`, `GET /api/v1/tools` y detalle por ID | Identidad activa |
| Catálogo completo | `GET /api/v1/models?approved_only=false`, equivalente tools | Administrator |
| Crear definición | `POST /api/v1/models`, `POST /api/v1/tools` | Administrator |
| Cambiar aprobación | `PATCH /api/v1/models/{id}`, equivalente tools | Administrator |
| Eliminar sin referencias | `DELETE /api/v1/models/{id}`, equivalente tools | Administrator |

Los permisos se controlan en backend. Ser administrator no concede al propietario
permisos de herramientas que no tenga asignados. Todos los usuarios activos
pueden consultar el inventario interno y las configuraciones; editar un agente
ajeno requiere administrator. No existe API para editar roles o concederse permisos.

Ejemplo de creación de una versión con perfil resuelto por el servidor:

```json
{
  "configuration": {
    "api_version": "bia.ai/v1",
    "kind": "AgentConfiguration",
    "objective": "Explain synthetic authorized invoices",
    "instructions": "Use only approved evidence.",
    "model": {"profile": "balanced", "max_output_tokens": 1000},
    "tool_ids": ["invoice-read-v1"],
    "required_capabilities": ["chat"],
    "limits": {"max_steps": 6, "max_tool_calls": 5, "timeout_seconds": 30},
    "security": {
      "require_authentication": true,
      "resource_scope": "caller_owned",
      "allow_financial_writes": false
    }
  }
}
```

Puede elegirse `model_id` o `profile`, de forma exclusiva. El servidor fija el
modelo exacto al guardar. Campos desconocidos —incluido `permissions`— se
rechazan. Se verifican capacidades, límites, aprobación y permisos del
propietario en cada guardado, clonación y snapshot. Los esquemas de herramientas
se validan como JSON Schema 2020-12 y no pueden referenciar recursos externos.

Editar un borrador requiere `{"expected_revision":1,"configuration":{...}}`;
crear un snapshot requiere `{"expected_revision":1}`; clonar usa
`{"source_version":1,"expected_source_revision":2}`. Un conflicto de revisión
devuelve 409 y exige recargar; no sobrescribe silenciosamente cambios ajenos.

El agente admite `draft`, `disabled` y `deprecated`. Solo `draft` permite cambios
de configuración; `deprecated` es terminal. Las versiones admiten `draft` y
`snapshot`. Un snapshot **no equivale a publicar**. Un agente con versiones no
se elimina: se deshabilita para conservar el historial. La transferencia de
propiedad es administrativa, revalida los borradores y se bloquea si hay snapshots.

## Estructura

```text
apps/
  api/
    app/
      api/health.py       # Rutas y contratos de salud
      identity/          # Identidades y autorización local explícita
      catalogs/          # Modelos y herramientas: modelos, schemas y rutas
      agents/            # Registry, configuraciones y versionamiento
      core/config.py      # Variables de entorno validadas con Pydantic
      db/base.py          # Base declarativa y nombres de constraints
      db/session.py       # Engine y sesiones por petición
      main.py             # Factory y ciclo de vida de FastAPI
    migrations/           # Revisiones Alembic versionadas
    tests/                # Pruebas unitarias y de integración
    alembic.ini
    Dockerfile
  web/
    src/app/              # App Router, interfaz y rutas HTTP
    src/lib/health.ts     # Cliente tipado con timeout y validación
    tests/                # Pruebas con node:test
    Dockerfile
scripts/smoke.py           # Verificación HTTP entre servicios
tests/e2e/                # Flujos reales con Playwright
.github/workflows/ci.yml   # Mismos checks con Docker en CI
compose.yaml
Makefile
pyproject.toml / uv.lock
package.json / package-lock.json
```

El backend es un monolito modular. Las futuras funcionalidades se añadirán
por dominio, sin crear un servicio por agente. No se crean tablas de negocio
por adelantado ni se ejecuta `create_all()` al arrancar.

## Configuración

`.env.example` documenta todos los valores de desarrollo. `.env` se ignora
en Git y en el contexto de Docker. Python carga el `.env` raíz y permite que
las variables del proceso lo sobrescriban. El frontend recibe sus variables
mediante Compose o `make dev-web`.

| Variable | Uso / valor predeterminado |
| --- | --- |
| `APP_ENV` | `development`, `test` o `production` |
| `ENABLE_DEMO_AUTH` | `false` por defecto en código; `.env.example` la activa solo para demo local |
| `DEMO_ADMIN_TOKEN`, `DEMO_CREATOR_TOKEN`, `DEMO_VIEWER_TOKEN` | Credenciales sintéticas para el seed explícito |
| `POSTGRES_DB` | `bia_studio` |
| `POSTGRES_USER` | `bia` |
| `POSTGRES_PASSWORD` | Credencial de desarrollo local |
| `POSTGRES_HOST` | `127.0.0.1` en desarrollo nativo; `postgres` en Compose |
| `POSTGRES_PORT` | `55432` en el Mac; `5432` entre contenedores |
| `API_PORT` | Puerto publicado de FastAPI: `8000` |
| `WEB_PORT` | Puerto publicado de Next.js: `3000` |
| `BACKEND_URL` | URL usada por el servidor Next.js; Compose fija `http://api:8000` |
| `CORS_ORIGINS` | Array JSON, por ejemplo `["http://localhost:3000"]` |
| `DATABASE_URL` | Override opcional para API/Alembic nativos, con `postgresql+psycopg://` |

Compose usa siempre `POSTGRES_*` y sobrescribe los hosts y puertos internos;
ignora `DATABASE_URL` para evitar que una URL del Mac rompa la red de contenedores.
Las contraseñas de `POSTGRES_PASSWORD` se manejan con `URL.create` en Python;
si escribes una `DATABASE_URL`, codifica los caracteres reservados de la contraseña.
No se envían credenciales ni `BACKEND_URL` al navegador y las peticiones de
estado tienen `Cache-Control: no-store`.

Los puertos publicados se limitan a `127.0.0.1`. Si un puerto está ocupado,
cambia su valor en `.env` y ejecuta `make up`. Para ejecución nativa, ajusta
también `BACKEND_URL` si cambia `API_PORT`, y `CORS_ORIGINS` si cambia `WEB_PORT`.

## Migraciones

`migrate` espera a PostgreSQL y ejecuta `alembic upgrade head`. La API espera
a que ese proceso termine correctamente; el frontend espera a la API.
Una migración fallida impide completar el arranque.

La revisión `0001_foundation` es una línea base sin tablas de negocio.
Alembic crea `alembic_version` y guarda la revisión de forma transaccional.
`0002_agent_management` añade `users`, `agents`, `agent_versions`, `models`,
`tools` y `agent_tools`, junto con claves foráneas, checks, índices y triggers.
Estos impiden modificar/borrar snapshots y sus enlaces, cambiar definiciones de
catálogo o introducir enlaces no aprobados/inconsistentes. La coherencia entre
JSON y relaciones de herramientas se verifica al confirmar la transacción.
La prueba de integración usa un esquema temporal único y verifica:
estado sin migrar → upgrade → repetición idempotente → ausencia de drift →
downgrade a base → nuevo upgrade. El esquema temporal se elimina al terminar;
las tablas de la aplicación permanecen intactas.

```sh
make migrate
make seed
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
docker compose exec -T api alembic -c apps/api/alembic.ini upgrade head --sql
```

Para crear una migración futura, importa los modelos nuevos en el entorno
de Alembic, genera la revisión en el checkout y revisa el SQL antes de aplicarlo:

```sh
uv run --frozen alembic -c apps/api/alembic.ini revision --autogenerate -m "describe change"
uv run --frozen alembic -c apps/api/alembic.ini upgrade head
```

Actualiza `SCHEMA_REVISION` en `apps/api/app/api/health.py` junto con cada
nueva revisión. `/health` solo indica que el proceso está vivo;
`/health/ready` exige conexión SQL y la revisión esperada. Devuelve HTTP 503
cuando la base de datos no está disponible o faltan migraciones, sin exponer
detalles de conexión. `/health` del frontend comprueba su propio proceso;
`/api/health` comprueba la cadena completa y propaga HTTP 503 si falla.

## Desarrollo nativo opcional

Requiere Python 3.14, uv y Node.js 24. `.python-version` y `.nvmrc` indican
las versiones. Las instalaciones usan `uv.lock` y `package-lock.json`;
no regeneres los archivos de bloqueo durante un arranque normal.

Primero detén el stack completo si está activo, instala dependencias y
arranca únicamente PostgreSQL:

```sh
make down
make demo-env
make install
docker compose up -d --wait postgres
uv run --frozen alembic -c apps/api/alembic.ini upgrade head
PYTHONPATH=apps/api uv run --frozen python -m app.seed
```

En dos terminales, desde la raíz:

```sh
# Terminal 1
make dev-api
```

```sh
# Terminal 2
make dev-web
```

Pruebas y checks nativos:

```sh
make test-unit
RUN_DB_TESTS=1 uv run --frozen pytest
uv run --frozen ruff check apps/api scripts
uv run --frozen ruff format --check apps/api scripts
npm run lint
npm run typecheck
npm test
npm run build
python3 scripts/smoke.py
# Con Google Chrome instalado, y el stack Docker activo:
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
# Alternativa con Chromium descargado por Playwright:
npx playwright install chromium
npm run test:e2e
```

Sin `RUN_DB_TESTS=1`, Pytest omite explícitamente la prueba de PostgreSQL;
las pruebas unitarias no necesitan una base de datos. `make test` sí ejecuta
la suite completa contra PostgreSQL con Docker.

Las pruebas de integración crean y eliminan esquemas temporales únicos; no
modifican los registros del entorno de demostración. Verifican persistencia,
restricciones de base de datos, rollback, versionamiento, concurrencia,
aprobaciones/revocaciones, acceso entre propietarios y SQL directo sobre snapshots.
Playwright usa el stack real, sin mocks de API o autorización; deja agentes
sintéticos `e2e-*` con historial para comprobar persistencia y elimina su modelo
temporal. CI ejecuta `make verify` y los dos flujos de navegador con Chromium.

## Operación y diagnóstico

```sh
make up           # Construir y arrancar; no ejecuta la suite
make seed         # Cargar identidades y catálogos sintéticos explícitamente
make test         # Pytest con PostgreSQL real
make lint         # Ruff
make web-check    # Build, ESLint, TypeScript y pruebas web en Docker
make smoke        # Comprobar la cadena HTTP con el stack activo
make logs         # Logs; Ctrl+C para salir
make down         # Detener sin eliminar datos
```

El seed solo inserta registros que falten: no restaura aprobaciones revocadas,
no modifica permisos y no rota tokens ya guardados. Si cambias un token del
entorno después del seed, debes rotar su hash mediante un procedimiento
administrativo de desarrollo o usar una base de demostración nueva. Repetir el
seed no cambia credenciales existentes. Los tokens deben ser distintos y tener
al menos 24 caracteres; no sirven como autenticación de producción.

`make down` conserva el volumen `postgres_data`. Las credenciales de
PostgreSQL se inicializan solo al crear el volumen: cambiar `.env` no cambia
las credenciales de una base ya existente. Para reinicializar datos locales
de forma deliberada, `docker compose --profile test down --volumes` elimina
el volumen y todos sus datos; después ejecuta `make verify`.

Si el arranque falla, revisa `docker compose ps -a` y
`docker compose logs --tail=100 postgres migrate api web`. Un fallo de conexión
se distingue de una migración pendiente mediante `/health/ready`. El frontend
muestra la indisponibilidad y permite reintentar con **Actualizar estado**.

## Límites y dependencias

Esta entrega cubre solo Sprint 1 y Sprint 2. La autenticación es una demo local
explícita, no SSO de producción: el proceso rechaza `ENABLE_DEMO_AUTH=true` con
`APP_ENV=production`. Sin un proveedor de identidad real, las APIs de gestión
fallan cerradas cuando se desactiva la demo. No hay LangGraph, RAG, ejecución,
evaluación ni publicación y no se requiere ninguna clave de proveedores.

La base del Sprint 1 emplea CSS propio y un cliente ligero; se conserva para
evitar una migración visual no necesaria a Tailwind/shadcn. La configuración no
incluye referencias a workflows, conocimiento o evaluaciones aún inexistentes;
los campos se añadirán con contratos y migraciones cuando esos módulos existan.

La auditoría de npm durante la validación del 15 de octubre de 2026 mostró
cero vulnerabilidades en dependencias de ejecución (`npm audit --omit=dev`)
y cinco avisos altos derivados de `braces`, transitiva del tooling de ESLint
de Next.js ([aviso del proyecto](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)).
La versión publicada de `braces` sigue siendo 3.0.3, sin arreglo compatible;
se conserva la configuración oficial y el pendiente queda documentado.
No ejecutes `npm audit fix --force`: propone degradar Next.js ESLint a una
versión mayor anterior. Revisa `npm audit` al actualizar dependencias.
