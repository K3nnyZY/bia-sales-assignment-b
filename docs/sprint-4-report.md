# Sprint 4 — Quality & Governance

Fecha: 2026-10-15. Alcance: Sprints 1–3 conservados, Sprint 4 implementado para
el entorno local. No se inició Sprint 5. Se revisaron AGENTS.md, arquitectura,
ADRs y código/pruebas existentes antes de implementar.

## 1. Implementado

- Módulo governance dentro del monolito existente; sin servicios/dependencias nuevos.
- Suites inmutables versionadas y runner billing-evaluator-v1: nueve checks reales
  del StateGraph sobre identidades/facturas sintéticas aisladas. Los checks verifican
  configuración, factura, comparación, conocimiento, acceso entre clientes, prompt
  injection, factura inexistente, permisos y período anterior no disponible.
- Evaluaciones/resultados durables, con hashes exactos de snapshot, suite y
  dependencias. El gate exige los ocho controles obligatorios, último resultado
  satisfactorio, cero fallos críticos, referencias aprobadas y aprobación vigente.
- Ciclo draft/testing/pending_approval/approved/published/deprecated/disabled en una
  entidad separada del snapshot inmutable. La API preserva los contratos del Sprint 2.
- Aprobación independiente: autor, propietario y solicitante no pueden aprobarse,
  incluso con rol administrador. Roles verificados en DB/backend; revisión optimista
  y bloqueos transaccionales, una sola publicación activa y rollback autorizado.
- Historial append-only para evaluaciones, decisiones finales, snapshots, auditoría,
  runs terminales y tool calls. No se elimina historial para cambiar una publicación.
- Runtime integra canales preview/published/evaluation. Published resuelve la versión
  activa y comprueba gate y modo evaluado; evaluation solo existe internamente.
  Se mantiene autorización por herramienta/recurso y StateGraph real del Sprint 3.
- Evaluation Center, Builder con selección explícita de workflow, Playground con
  canal publicado y Trace Viewer conectados al backend real. Auditor ve globalmente;
  caller ve sus runs; personal de calidad ve las trazas sintéticas autorizadas.
- Métricas SQL: conteos por estado/modelo/modo, herramientas/errores, latencia media,
  P50/P95, tokens reportados y costos estimados con cobertura conocida. Se excluyen
  evaluaciones; null se muestra como indisponible. No hay métricas precalculadas.
- Migración Alembic 0004, seeds reproducibles, smoke HTTP y E2E de ciclo completo.

## 2. Resultados ejecutados

| Comprobación | Resultado |
| --- | --- |
| `make verify` final, Docker | Exit 0; backend, frontend y tres smokes aprobados |
| Pytest completo, PostgreSQL 16 | **206 passed**, 33.72 s (64 unitarias, 142 integración) |
| Nuevas pruebas de gobernanza aisladas | **29 passed**, 18.34 s; incluye concurrencia y costos con doble del SDK |
| Ruff lint / formato | Sin errores; 70 archivos Python formateados |
| Build producción Next.js | Correcto en Docker |
| ESLint / TypeScript estricto | Sin errores |
| Pruebas frontend node:test | **13 passed**, ninguna omitida |
| Playwright / Chrome | **4 passed**, 6.5 s; recorrido de gobernanza 3.2 s |
| Alembic roundtrip/drift | Pytest verifica upgrade repetido → check sin drift → downgrade base → upgrade |
| Persistencia tras reinicio API | **PASS**: evaluación, auditoría y SHA-256 idéntico de tres trazas |
| CI remoto | No ejecutado; workflow local actualizado para los cuatro recorridos |

Los tests de seguridad usan autorización real; los dobles solo sustituyen el
límite de SDK/adapters para provocar fallos o uso reportado. El test de métricas
no es evidencia de una llamada real al proveedor. Las suites y smokes de producto
muestran explícitamente modo determinista, sin invención de generación/tokens/costo.

Fallos intermedios corregidos: tipo de fecha SQL en el fingerprint, test de
revocación ajustado al contrato real `revoked`, selección explícita de
billing-assistant en el smoke anterior y etiquetas accesibles de los selectores.
El test de navegador también usa la etiqueta existente de Consulta correctamente.
Los fallos no se cuentan como comprobaciones aprobadas antes de su repetición.

## 3. Evidencia HTTP persistida

Último smoke del `make verify` final:

- Agente: `quality-smoke-8e4937724ccc`.
- Evaluación: `eval-0759133a13d242dc8bdeba8e25822048`, **9/9 PASS**.
- Run publicado autorizado: `run-32dd4f4eab174450a1497847146e9f33`.
  Comparación Python: **64.400 COP**, **23 %**, 70 kWh; nueve nodos y tres herramientas.
- Rechazo entre clientes: `run-db979251dda24c8c831f4d3dd707cfbf`, sin evidencia ajena.
- Fallo por período anterior ausente: `run-5ff52474a9e14dd88d304a520c7ca58f`, escalated.
- Segunda versión evaluada/aprobada/publicada y rollback a v1 auditados.
- Candidata con max_tool_calls=1: **cuatro fallos críticos**, submit devuelve **409**.
- El smoke de Sprint 3 también pasó para ambos clientes con su grant y facturas
  respectivas, rechazo cruzado, consulta simple y comparación.

Estos IDs pertenecen a la base local verificada; una instalación nueva devuelve
otros. Pueden consultarse en `/evaluations/{id}`, `/runs/{id}/trace` y auditoría
con la identidad autorizada. Los traces de runtime son eventos del StateGraph,
no listas estáticas mostradas como ejecuciones. El código del grafo permanece en
`apps/api/app/runtime/graph.py`; el evaluador llama a ese mismo runtime.

## 4. Comandos ejecutados

Desde la raíz (logs locales en `/tmp/bia-s4-*`; no contienen credenciales):

```sh
sh scripts/demo-env.sh
RUN_DB_TESTS=1 .venv/bin/pytest -q --tb=short
RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_governance_api.py -q --tb=short
.venv/bin/ruff check apps/api scripts
.venv/bin/ruff format --check apps/api scripts
npm run typecheck
npm run lint
npm test
make up
make governance-seed
make governance-smoke
make verify
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
git diff --check
```

La migración generada se revisó y añadió triggers/constraints manuales antes de
aplicarse. Usa `make migrate`/`make verify` para reproducir la instalación;
no generes otra revisión para instalar.
Los comandos contra DB/Docker/Chrome se ejecutaron con acceso al entorno local;
no se desplegó ni publicó nada fuera de esta base de demo.

También se ejecutaron:

```sh
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
curl -fsS http://localhost:8001/health/ready
```

Resultado: `0004_quality_governance (head)`, `No new upgrade operations detected`,
y readiness ok. Se extrajo la última prueba JSON del log de verify a
`/tmp/bia-governance-proof.json` y se ejecutó:

```sh
docker compose restart api
docker compose up -d --wait api
docker compose exec -T -e GOVERNANCE_TRACE_PROOF="$(cat /tmp/bia-governance-proof.json)" api python - < scripts/governance_smoke.py
```

Resultado real: `PASS: evaluation, rollback audit and exact trace hashes survived backend restart.`
La guía incluye cómo generar ese archivo de prueba sin depender del log.


## 5. Verificación manual

Sigue [la guía completa de Sprint 4](sprint-4-guide.md), con instrucciones desde
cero, los tokens/roles correspondientes, configuración de herramientas y límites,
publicación, Playground, rollback y prueba de una versión insegura.

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
open -a Docker
make demo-env
make verify
open http://localhost:3000/agents
open http://localhost:3000/evaluations
open http://localhost:3000/playground
open http://localhost:3000/traces
```

En este Mac: API `http://localhost:8001/docs`, web 3000, PostgreSQL 55432.
Creator configura/evalúa/solicita; approver independiente aprueba/publica;
creator ejecuta por canal Published; auditor revisa trazas y auditoría.

## 6. Limitaciones

- Identidad demo y runtime/evaluador locales, bloqueados en producción. Pendiente
  SSO y validación productiva independiente. No se afirma producción empresarial.
- Solo billing v1, escenarios sintéticos explícitos y aserciones deterministas;
  no grader universal ni garantía de protección ante cualquier prompt injection.
- Ejecución síncrona acotada, sin workers, recuperación automática ni checkpoint
  durable. Una caída abrupta puede dejar running y bloquear esa candidata.
- Cambios de dependencias bloquean gates antiguos. Para reevaluar una versión
  ya publicada se crea otra candidata; no se modifica su aprobación histórica.
- Métricas agregadas sobre historial visible, no streaming; UI muestra hasta 100
  runs/eventos recientes. Costos estimados de catálogo, sin conciliación de cobros.
- El gateway LiteLLM real existente se conserva. No se realizaron llamadas pagadas
  en Sprint 4; el modo proveedor requiere evaluación explícita compatible y cuota.
  La última prueba real documentada del Sprint 3 fue rechazada por cuota insuficiente.
- No se implementaron RAG, pgvector, ingestión ni otro alcance del Sprint 5.

## 7. Siguiente hito

Sprint 5 queda pendiente y no se inició. Ver los límites y decisiones en
[ADR-012](decisions/ADR-012-quality-governance.md). La ejecución de CI remoto y
un proveedor con cuota requieren verificaciones independientes del entorno local.

## Inventario de archivos nuevos/modificados

- `.env.example`
- `.github/workflows/ci.yml`
- `Makefile`
- `README.md`
- `apps/api/app/agents/routes.py`
- `apps/api/app/api/health.py`
- `apps/api/app/catalogs/routes.py`
- `apps/api/app/core/config.py`
- `apps/api/app/db/models.py`
- `apps/api/app/governance/__init__.py`
- `apps/api/app/governance/audit.py`
- `apps/api/app/governance/evaluator.py`
- `apps/api/app/governance/models.py`
- `apps/api/app/governance/observability.py`
- `apps/api/app/governance/policy.py`
- `apps/api/app/governance/routes.py`
- `apps/api/app/governance/runtime.py`
- `apps/api/app/governance/schemas.py`
- `apps/api/app/governance/seed.py`
- `apps/api/app/governance/service.py`
- `apps/api/app/main.py`
- `apps/api/app/runtime/models.py`
- `apps/api/app/runtime/policy.py`
- `apps/api/app/runtime/routes.py`
- `apps/api/app/runtime/schemas.py`
- `apps/api/app/runtime/service.py`
- `apps/api/migrations/versions/0004_quality_governance_quality_governance.py`
- `apps/api/tests/test_database.py`
- `apps/api/tests/test_governance_api.py`
- `apps/api/tests/test_governance_unit.py`
- `apps/web/src/app/agents/[id]/page.tsx`
- `apps/web/src/app/api/studio/[...path]/route.ts`
- `apps/web/src/app/evaluations/page.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/app/playground/page.tsx`
- `apps/web/src/app/traces/page.tsx`
- `apps/web/src/components/studio.tsx`
- `apps/web/src/components/trace.tsx`
- `apps/web/src/lib/governance.ts`
- `apps/web/src/lib/runtime.ts`
- `apps/web/src/lib/studio.ts`
- `apps/web/tests/studio.test.ts`
- `docs/architecture.md`
- `docs/decisions/ADR-012-quality-governance.md`
- `docs/sprint-4-guide.md`
- `docs/sprint-4-report.md`
- `scripts/demo-env.sh`
- `scripts/governance_smoke.py`
- `scripts/runtime_smoke.py`
- `tests/e2e/governance.spec.ts`

Total: 50 archivos nuevos/modificados. `.env` local permanece ignorado;
no se incluyeron secretos ni se modificaron lockfiles de dependencias.
