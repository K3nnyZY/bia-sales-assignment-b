# Sprint 3 — Agent Runtime

Fecha: 2026-10-15. Alcance: Sprints 1 y 2 preservados; ejecución local autorizada,
LangGraph, billing sintético, Model Gateway y Playground. Sprint 4 no implementado.

La [verificación de cierre](sprint-3-verification.md) contrasta los criterios
con AGENTS y arquitectura, demuestra cinco escenarios HTTP, persistencia tras
reiniciar la API y deja explícita la validación pendiente del proveedor real.
Los IDs y hashes comprobados están en [la evidencia JSON](sprint-3-verification.json).

El [seguimiento de proveedor real](sprint-3-provider-check.md) documenta el
modelo aprobado, v2 y la respuesta real de OpenAI: `429 / credit_balance_exhausted`.
La generación exitosa permanece pendiente de saldo; no se convirtió en demo.

## Implementado

- StateGraph real con estado tipado, contexto confiable separado, rutas
  `invoice`, `compare`, `knowledge`, salida/fallo explícitos y límites de
  pasos, llamadas, reintentos y tiempo. Configuración fijada por snapshot/hash,
  modelo exacto, versiones de herramientas y workflow `billing_workflow_v1:1.0.0`.
- Tres adaptadores controlados: factura propia, mes calendario previo y
  tarifas/FAQ aprobadas/vigentes. Contratos anteriores del Registry preservados;
  se registra una nueva versión de lookup con evidencia completa.
- Cuatro facturas de dos clientes y dos fuentes sintéticas. `Decimal` calcula
  diferencias, porcentaje y efectos de consumo/tarifa con ajuste de redondeo.
  Septiembre del creator: 344.400 COP; agosto: 280.000 COP; diferencia:
  **64.400 COP** y **70 kWh**. Consumo: 56.000 COP; tarifa: 8.400 COP.
- Autorización de invocación por grant explícito de versión. Validación de
  identidad, permisos congelados y actuales, aprobación y definición exacta
  antes de cada herramienta y revalidación antes de liberar resultados.
  No se acepta identidad ni permisos desde el cuerpo o el prompt.
- Runtime API: `GET /api/v1/runtime/agents`, `POST /api/v1/runs`,
  `GET /api/v1/runs`, `GET /api/v1/runs/{id}` y `GET /api/v1/runs/{id}/trace`.
  Historial y trazas exclusivos del caller, sin bypass administrativo.
- Migración `0003_agent_runtime`: seis tablas, checks monetarios y temporales,
  FKs, grants solo a snapshots, identidad de run inmutable, finalización
  consistente, runs terminales inmutables y logs append-only.
- Gateway LiteLLM optativo para modelos aprobados openai/anthropic, secretos
  del servidor, timeout, sin reintentos/fallback. El modelo ordena afirmaciones
  y referencias calculadas, sin generar hechos adicionales o seleccionar tools.
- Modo determinista explícito con modelo sintético registrado; no llama a
  proveedores y conserva uso/coste nulos. El gateway registra únicamente tokens
  reportados por SDK y estimación de coste con precios congelados cuando procede.
- Playground funcional: versión/modo/tarea/factura/período/mensaje, resultado,
  cálculos, fuentes, nodos, intentos y errores reales; historial persistido.
- Timeouts de I/O async y consultas PostgreSQL; errores tipados sin exposición
  de excepciones privadas ni evidencia parcial después de una denegación.

## Archivos nuevos

| Grupo | Archivos |
| --- | --- |
| Billing | `apps/api/app/billing/{__init__,models,contracts,calculations,tools}.py` |
| Runtime | `apps/api/app/runtime/{__init__,context,errors,models,schemas,policy,graph,gateway,service,routes,seed}.py` |
| Migración | `apps/api/migrations/versions/0003_agent_runtime_agent_runtime.py` |
| Pruebas backend | `apps/api/tests/test_billing_unit.py`, `apps/api/tests/test_runtime_api.py` |
| Playground | `apps/web/src/app/playground/page.tsx`, `apps/web/src/lib/runtime.ts` |
| Smoke y E2E | `scripts/runtime_smoke.py`, `tests/e2e/runtime.spec.ts` |
| Documentación | Este reporte, `docs/decisions/ADR-011-agent-runtime.md`, `docs/sprint-3-verification.md` y `docs/sprint-3-verification.json` |

## Archivos existentes modificados por Sprint 3

- Backend: `apps/api/app/agents/schemas.py` (workflow opcional compatible),
  `app/core/config.py`, `app/db/models.py`, `app/main.py`, `app/api/health.py`.
- Prueba de migraciones: `apps/api/tests/test_database.py` (13 tablas y roundtrip).
- Frontend: `apps/web/src/app/agents/[id]/page.tsx` (preservar workflow),
  `src/app/api/studio/[...path]/route.ts`, `src/lib/studio.ts` (allowlist y timeout),
  `src/components/studio.tsx`, `src/app/globals.css`, `tests/studio.test.ts`.
- Dependencias/configuración: `pyproject.toml`, `uv.lock`, `.env.example`,
  `scripts/demo-env.sh`, `Makefile`, `.github/workflows/ci.yml`.
- Documentación: `README.md`, nota de estado implementado en `docs/architecture.md`.

Se conservaron los cambios de Sprint 2 que ya estaban en el checkout, incluidos
el contrato de alta con configuración inicial, `test_agent_contract.py` y sus
cambios de documentación. `.gitignore` ya existía; se verificó que ignora `.env`,
`.venv`, `node_modules` y `.next`. No se añadieron secretos ni se borraron datos.

## Pruebas y resultados reales

Verificación final contra PostgreSQL 16 y stack Docker local:

| Comprobación | Comando ejecutado | Resultado |
| --- | --- | --- |
| Stack, migraciones, seeds, suite y smoke | `make verify` | Exit 0 |
| Pytest completo dentro de Docker | Incluido en `make verify` → `make test` | **169 passed**; 56 unitarias y 113 de integración |
| Unitarias nativas | `.venv/bin/pytest -m 'not integration' -q` | **56 passed**, 113 deselected |
| Ruff lint/formato | Incluido en `make verify` → `make lint` | Sin errores; 54 archivos formateados |
| Next.js build de producción | `make verify` → imagen web y `make web-check` | Correcto; ruta `/playground` compilada |
| ESLint / TypeScript / tests web | `make verify` → `make web-check` | Correctos; **13 tests passed** |
| Navegador real | `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | **3 passed** |
| Head de Alembic | `docker compose exec -T api alembic -c apps/api/alembic.ini current` | `0003_agent_runtime (head)` |
| Drift | `docker compose exec -T api alembic -c apps/api/alembic.ini check` | `No new upgrade operations detected.` |
| Salud del stack | `docker compose ps -a` | api/web/postgres healthy; migrate Exited (0) |
| Importación real del SDK en contenedor | `docker compose exec -T api python -c 'import os; os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"; import litellm; from importlib.metadata import version; print("LiteLLM", version("litellm"), "acompletion:", callable(litellm.acompletion))'` | LiteLLM 1.105.1, acompletion disponible; sin llamada a proveedor |
| Auditoría de dependencias de ejecución | `npm audit --omit=dev` | 0 vulnerabilidades |
| Auditoría incluyendo tooling | `npm audit --json` | Exit 1: 5 avisos altos previos, derivados de braces/ESLint; detalle en README |
| Whitespace e ignorados | `git diff --check`, `git check-ignore .env node_modules apps/web/.next .venv` | Correctos |

Las nuevas pruebas añaden 14 unitarias y 48 casos de integración a las 107
existentes. Cubren el StateGraph real y su traza, persistencia, cálculos con
fracciones/descensos/base cero/cambio de año, acceso entre clientes, identidad
inyectada en cuerpo/prompt, inyección desde documentos, permisos y catálogos
revocados, revocación durante generación, grants, límites, SQL directo sobre
runs/logs, fallos transitorios, timeout real `pg_sleep`, reintentos acotados,
respuesta inválida, secretos en excepciones y métricas ausentes.

Los tests del gateway sustituyen únicamente la frontera de I/O del proveedor;
no sustituyen la autorización. Los valores de uso en esos tests son fixtures,
no resultados de un proveedor real. También se comprueba la delegación del
wrapper a `litellm.acompletion` mediante un doble del SDK. La suite no hizo llamadas
reales a proveedores. El seguimiento posterior intentó OpenAI y recibió un
rechazo de cuota; no hay generación exitosa ni métricas de uso externo reportadas.

El smoke HTTP final creó una ejecución real del grafo en modo determinista,
comprobó **64.400 COP**, tres tool calls y nueve eventos, y verificó denegación
de factura ajena y 404 al consultar otra traza. Playwright verificó creación/
snapshot/clonación de agentes, administración de catálogos y Playground con
persistencia y acceso denegado. Los identificadores de run varían por ejecución.

La auditoría final amplió el smoke y E2E con consulta individual y fallo real
por factura previa ausente. Las cinco trazas conservaron su SHA-256 después de
reiniciar la API; una sesión SQL independiente confirmó los runs y eventos.
El primer intento del E2E ampliado falló por un selector exacto del desplegable
Consulta; se corrigió el selector y la repetición terminó con tres pruebas aprobadas.

GitHub Actions quedó configurado para estos checks y tres flujos con Chromium;
no se ejecutó CI remoto. El aviso de Playwright sobre `NO_COLOR`/`FORCE_COLOR`
no impidió ejecutar las pruebas. El pendiente previo del tooling ESLint se
mantiene documentado en README; no se aplicaron actualizaciones forzadas.

## Reproducir en macOS

Docker Desktop y make bastan para stack, backend, frontend y smoke. En Terminal:

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
open -a Docker
# Espera a que el motor esté listo:
docker info
make env
make demo-env
make verify
docker compose ps -a
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
make runtime-smoke
open http://localhost:3000/playground
```

En el Mac verificado se usa `API_PORT=8001` y
`BACKEND_URL=http://127.0.0.1:8001` por el conflicto previo con 8000.
Playground sigue en 3000; `make verify` usa los valores actuales de `.env`.

Si el `.env` existente tiene flags deshabilitados, activa explícitamente
`ENABLE_DEMO_AUTH=true` y `ENABLE_LOCAL_RUNTIME=true` en development; el script
preserva valores existentes. El seed conserva revocaciones y registros, no
restaura permisos. No hace falta eliminar el volumen para ejecutar el sprint.

Para los tres E2E desde el Mac, instala Node.js 24 y Google Chrome:

```sh
npm ci
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

Con Chromium administrado por Playwright, como alternativa:

```sh
npx playwright install chromium
npm run test:e2e
```

En Playground usa `DEMO_CREATOR_TOKEN` de `.env`, versión sintética de
`billing-assistant`, modo determinista, comparación e `INV-1002`. Comprueba
64.400 COP y 70 kWh; inspecciona nodos y referencias. Intenta `INV-2002` y
comprueba denegación. Inicia sesión con `DEMO_CUSTOMER_B_TOKEN` y verifica su
factura `INV-2002`; la del creator sigue denegada. Recarga y consulta historial.

La [guía README](../README.md) documenta curl, entorno, API, activación opcional
de proveedor y preparación de una versión con un modelo aprobado real.

## Limitaciones y siguiente hito

- Solo preview local con autenticación de demostración; no SSO ni publicación.
- Facturación sintética con cargos por consumo, no impuestos/cargos fijos.
- Tarifas/FAQ por SQL aprobado y vigente; sin RAG o Knowledge Registry completo.
- Gateway con redacción cerrada; proveedor real pendiente de verificación con
  credenciales e identificador aprobados del entorno del usuario.
- Runtime síncrono acotado; sin colas, checkpoints, recuperación tras caída
  abrupta ni reconciliación de runs que queden `running`.
- UI de trazas básica dentro del Playground; sin plataforma de observabilidad,
  evaluación o aprobación de Sprint 4.

El siguiente hito previsto es Sprint 4: Quality and Governance. No se avanzó
a su implementación ni se presentan snapshots como versiones publicadas.
