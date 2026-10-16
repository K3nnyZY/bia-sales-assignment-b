# Sprint 2 — Agent Management

Validación local: 15 de octubre de 2026, macOS ARM64, PostgreSQL 16 en Docker.

## Implementado

- CRUD de agentes con propietario, departamento, búsqueda, estados y control de
  revisión. El borrado solo permite agentes sin versiones; se conserva el historial.
- Contrato de alta con ID generado opcionalmente, alias `owner`, perfil y
  herramientas por nombre/ID; creación atómica del primer borrador y referencia
  `initial_configuration`. Respuesta `state: DRAFT` junto con el `status` existente.
  PATCH parcial conserva los metadatos omitidos y exige revisión actual.
- Model Registry con proveedor, identificador/release exactos, perfil,
  capacidades, límites, costes declarativos y política de datos. Los perfiles
  aprobados se resuelven de forma unívoca a un modelo concreto.
- Tool Registry con versiones, contratos JSON Schema, permisos, operación,
  timeout, reintentos, auditoría y aprobación administrados por administrator.
- Manifiestos Pydantic que rechazan campos desconocidos y concesiones de
  privilegios. Aprobación, límites, capacidades y permisos se verifican en backend.
- Borradores editables, snapshots efectivos con SHA-256 y nuevas versiones
  derivadas de una configuración existente. Revisiones obsoletas devuelven 409.
- Relaciones SQLAlchemy y migración `0002_agent_management` con claves foráneas,
  unicidad, checks, índice parcial por perfil y triggers de inmutabilidad/coherencia.
- Identidades y catálogos sintéticos, seed explícito e idempotente. Autenticación
  demo deshabilitada por defecto en código y bloqueada en producción.
- Interfaz real de inventario, creación, configuración, historial, snapshots y
  catálogos administrables; proxy limitado a las APIs implementadas.

## Archivos añadidos

| Área | Archivos |
| --- | --- |
| Identidad | `apps/api/app/identity/__init__.py`, `models.py`, `auth.py` |
| Catálogos | `apps/api/app/catalogs/__init__.py`, `models.py`, `schemas.py`, `routes.py` |
| Agentes | `apps/api/app/agents/__init__.py`, `models.py`, `schemas.py`, `service.py`, `routes.py` |
| Registro ORM y seed | `apps/api/app/db/models.py`, `apps/api/app/seed.py` |
| Migración | `apps/api/migrations/versions/0002_agent_management_agent_management.py` |
| Pruebas backend | `apps/api/tests/test_management_unit.py`, `apps/api/tests/test_management_api.py`, `apps/api/tests/test_agent_contract.py` |
| Páginas | `apps/web/src/app/agents/page.tsx`, `apps/web/src/app/agents/[id]/page.tsx`, `apps/web/src/app/models/page.tsx`, `apps/web/src/app/tools/page.tsx` |
| Componentes y cliente | `apps/web/src/components/studio.tsx`, `apps/web/src/components/catalog.tsx`, `apps/web/src/lib/studio.ts` |
| Proxy | `apps/web/src/app/api/studio/[...path]/route.ts` |
| Pruebas frontend | `apps/web/tests/studio.test.ts`, `playwright.config.ts`, `tests/e2e/management.spec.ts` |
| Entorno local | `scripts/demo-env.sh` |
| Documentación | `docs/decisions/ADR-010-agent-management.md`, este reporte |

## Archivos existentes modificados

- Backend: `apps/api/app/main.py`, `apps/api/app/core/config.py`,
  `apps/api/app/api/health.py`, `apps/api/migrations/env.py`.
- Pruebas existentes: `apps/api/tests/conftest.py`,
  `apps/api/tests/test_database.py`.
- Frontend existente: `apps/web/src/app/layout.tsx`,
  `apps/web/src/app/page.tsx`, `apps/web/src/app/globals.css`.
- Dependencias: `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`.
- Operación/documentación: `.env.example`, `.gitignore`, `Makefile`,
  `.github/workflows/ci.yml`, `README.md`.

Se añadieron a `.env` local las variables demo que faltaban, sin sobrescribir
valores existentes. `.env` está excluido de Git. `AGENTS.md` y
`docs/architecture.md` se leyeron y no se modificaron. La documentación distingue
la arquitectura futura de las funcionalidades entregadas.

## Pruebas y resultados

| Comando ejecutado | Resultado final |
| --- | --- |
| `.venv/bin/alembic -c apps/api/alembic.ini upgrade head` | Migración aplicada |
| `.venv/bin/alembic -c apps/api/alembic.ini check` | Sin operaciones pendientes |
| `make verify` | Finalizó con código 0; build y arranque, seed, pruebas, lint y smoke |
| Pytest dentro de `make verify` | **107 passed**, sin pruebas omitidas: 42 unitarias y 65 de integración/seguridad |
| Ruff dentro de `make verify` | Lint y formato correctos, 34 archivos Python |
| Frontend dentro de `make verify` | ESLint, TypeScript y build correctos; **13 pruebas HTTP/proxy passed** |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | **2 passed**, con Chrome real en modo headless |
| `python3 scripts/smoke.py` | Correcto desde los puertos publicados en el Mac |
| `docker compose exec -T api alembic -c apps/api/alembic.ini current` | `0002_agent_management (head)` |
| `docker compose exec -T api alembic -c apps/api/alembic.ini check` | Sin operaciones pendientes |
| `docker compose exec -T postgres psql -U bia -d bia_studio -c 'SELECT version_num FROM alembic_version;'` | Revisión `0002_agent_management` persistida |
| `npm audit --omit=dev --audit-level=high` | 0 vulnerabilidades de ejecución |
| `git diff --check` | Sin errores de whitespace |

Pytest verifica migración desde base, repetición idempotente, downgrade y nuevo
upgrade; persistencia en sesiones distintas; rollback de configuraciones
rechazadas; restricciones SQL; acceso entre usuarios; roles persistidos sin
mocks de autorización; referencias pendientes/revocadas; límites y capacidades;
permiso del propietario incluso cuando configura un admin; snapshots y enlaces
inmutables ante SQL directo; clones y numeración concurrente.

Playwright verifica creación → edición → snapshot → nueva versión → edición
independiente → recarga y consulta del snapshot original. El segundo flujo
verifica rechazo administrativo para un viewer con una cabecera de rol falsa,
y creación/aprobación/revocación/eliminación de un modelo por administrator.

Se corrigieron los fallos detectados durante el desarrollo y se repitieron sus
verificaciones antes de reportar estos resultados. GitHub Actions quedó
configurado con los mismos checks y Chromium, pero no se ejecutó remotamente
desde esta sesión.

## Verificación manual desde el Mac

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
open -a Docker
# Esperar a que Docker Desktop esté listo.
docker info
make demo-env
make verify

# Para las pruebas de navegador con Google Chrome instalado:
npm ci
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e

docker compose ps -a
curl -fsS http://localhost:8000/health/ready
curl -fsS http://localhost:3000/api/health
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
open http://localhost:3000/agents
```

Entra con `DEMO_CREATOR_TOKEN` de `.env` para crear/configurar agentes y con
`DEMO_ADMIN_TOKEN` para administrar catálogos. `DEMO_VIEWER_TOKEN` sirve para
comprobar el acceso de lectura. Tras recargar hay que identificarse de nuevo.
Para detener los servicios conservando los datos, usa `make down`.

La API, Next.js y PostgreSQL quedaron saludables; `migrate` terminó con código 0.
PostgreSQL conserva el puerto local 55432 establecido en Sprint 1.

## Límites y siguiente hito

- Solo Sprint 2. No se implementó ni inició Sprint 3: LangGraph, RAG y ejecución
  permanecen fuera del código. Tampoco hay publicación, evaluación ni aprobación.
- Los snapshots no son versiones publicadas ni autorizan ejecución.
- Identidad sintética local, sin SSO, expiración de sesión o administración de
  permisos por API. El seed no rota tokens ni restablece aprobaciones.
- Los agentes/versiones son un inventario interno legible para toda identidad
  activa; las escrituras se limitan al propietario creator o administrator.
- Se conservó el CSS existente en lugar de migrar a Tailwind/shadcn; decisión
  explícita en ADR-010 para evitar una refactorización visual ajena al alcance.
- Pytest emite una advertencia de deprecación de Starlette para su integración
  actual con httpx; las 107 pruebas pasan. Continúan los cinco avisos altos del
  tooling de desarrollo de ESLint ya documentados en Sprint 1; runtime npm sin
  vulnerabilidades detectadas. No se aplicaron degradaciones forzadas.
- Playwright deja agentes sintéticos `e2e-*` con historial; la suite de integración
  utiliza esquemas temporales independientes que elimina al terminar.

El siguiente hito del roadmap es Agent Runtime; requiere una instrucción nueva
antes de iniciarlo.

## Ajuste posterior del contrato de endpoints

Se modificaron `apps/api/app/agents/{models,schemas,service,routes}.py` y
`apps/api/tests/test_management_unit.py`; se añadió
`apps/api/tests/test_agent_contract.py`. Se actualizaron README, ADR-010 y este
reporte. No se modificó el esquema: `alembic check` confirmó ausencia de drift.

Comandos ejecutados para la verificación del ajuste:

```sh
.venv/bin/pytest -m 'not integration'
RUN_DB_TESTS=1 .venv/bin/pytest -x --tb=short
make verify
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
docker compose exec -T api alembic -c apps/api/alembic.ini check
git diff --check
```

Resultados: 107 pruebas Pytest, 13 pruebas web y 2 flujos Chrome aprobados;
Ruff, ESLint, TypeScript, build y smoke test correctos. También se comprobaron
por HTTP real las ocho rutas propuestas, incluidos creación con ID generado y
primera configuración, PATCH parcial y creación/consulta de otra versión.
Los casos de selección no aprobada, permisos insuficientes, propietarios no
válidos y herramientas ambiguas se verificaron con PostgreSQL real y rollback.
