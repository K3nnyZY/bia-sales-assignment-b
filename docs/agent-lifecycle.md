# Ciclo de vida de agentes y versiones

La configuración editable y el snapshot son estados de la misma fila
`AgentVersion`; no se crea otra entidad. `Agent.status` controla la edición del
registro y no sustituye el estado de publicación de Governance.

## Transiciones

| Operación | Condiciones | Resultado |
| --- | --- | --- |
| Crear agente | Creator o Admin; modelo aprobado y permisos válidos | Agente y v1 draft, atómicamente |
| Editar draft | Propietario Creator o Admin; revisión actual; agente editable | Misma versión, revisión incrementada |
| Congelar draft | Mismos permisos; referencias aprobadas y válidas | snapshot inmutable con hash |
| Crear nueva versión | Sin draft activo; origen snapshot del mismo agente y revisión actual | Nuevo draft con source_version; número creciente |
| Descartar draft posterior | Propietario Creator o Admin; snapshot previo; revisión actual | discarded terminal; conserva configuración y auditoría |
| Eliminar agente | Solo Admin, cualquier propietario; ningún snapshot; revisión actual | Retiro lógico irreversible; draft descartado; historial conservado |

Creator, Reviewer, Approver, Auditor y Viewer nunca eliminan agentes. El borrador
inicial no puede descartarse por separado: debe congelarse o Admin puede retirar
el agente completo. Un snapshot no puede editarse, descartarse ni eliminarse.
La evaluación, aprobación y publicación siguen los contratos existentes de
Governance, sobre el hash exacto del snapshot. No se cambian sus políticas.

El retiro utiliza `deleted_at` y estado deprecated. El agente desaparece de las
APIs de inventario/detalle; sus filas, relaciones y auditoría permanecen. El ID
queda reservado y no existe restauración. No se borran evaluaciones, aprobaciones,
ejecuciones ni snapshots. La auditoría sigue consultándose con los permisos existentes.

El alta anterior que solo enviaba metadatos sigue aceptándose: el backend elige
un modelo de chat aprobado, preferentemente balanced y después por ID. Puede
indicarse `model_profile` y herramientas, o una `configuration` completa. Si no hay
modelo compatible aprobado, devuelve 422 y revierte toda el alta. No llama al LLM,
no aprueba catálogos ni concede permisos.

## API

```text
POST   /api/v1/agents
PUT    /api/v1/agents/{id}/versions/{number}
POST   /api/v1/agents/{id}/versions/{number}/snapshot
POST   /api/v1/agents/{id}/versions
DELETE /api/v1/agents/{id}/versions/{number}?expected_revision=N
DELETE /api/v1/agents/{id}?expected_revision=N
GET    /api/v1/agents/{id}/versions
GET    /api/v1/audit-events?agent_id={id}
```

Guardar usa `{"expected_revision":1,"configuration":{...}}`; congelar,
`{"expected_revision":1}`; derivar,
`{"source_version":1,"expected_source_revision":2}`. La derivación permite
además `configuration` para aplicar cambios validados conservando el origen.
Los descartes y eliminaciones devuelven 204. Conflictos de revisión y de ciclo de
vida devuelven 409; falta de rol o propiedad, 403. El historial devuelve también
`discarded`, `discarded_at` y `discard_reason`.

## Integridad y migración

`0007_agent_lifecycle` depende de `0006_private_access_tokens`. Los bloqueos
FOR UPDATE sobre Agent serializan creación, edición, congelación, descarte y
eliminación. El índice único parcial `uq_agent_versions_active_draft` impide dos
drafts activos. Los triggers refuerzan el origen congelado, la inmutabilidad y la
prohibición de retirar agentes con snapshots. Se mantienen las FKs RESTRICT.

En datos históricos, un draft anterior a otro draft o a un snapshot posterior
se marca discarded con razón `legacy_superseded_draft`. Se conserva cada fila,
configuración, fuente, relación, snapshot y hash; no se inventa un actor humano.
Solo permanece activo el último draft posterior a los snapshots, si existe.
Los agentes históricos sin versiones se conservan y pueden crear su primer
borrador mediante el contrato anterior. Una fuente histórica que apuntaba a otro
draft no se reescribe; las nuevas
versiones requieren un snapshot. El downgrade restaura los drafts conservados y
la semántica anterior; no es un mecanismo para restaurar agentes eliminados.

Antes de actualizar un despliegue, respalda PostgreSQL y aplica la migración
mediante el proceso existente. Backend y frontend deben desplegarse juntos.
No se han ejecutado cambios en Railway como parte de este trabajo.

## Comprobar en la interfaz

1. Con Creator, crea un agente: aparece v1 draft editable y no aparece Eliminar agente.
2. Guarda cambios. Nueva versión desde esta está deshabilitado y explica el borrador activo.
3. Congela v1. El formulario queda de solo lectura. Deriva v2 desde v1.
4. Selecciona v1: no permite derivar otra versión mientras v2 sea draft.
5. En v2, pulsa Descartar borrador y confirma. v2 queda discarded; v1 permanece intacta.
6. Selecciona v1 y deriva v3; los números descartados no se reutilizan.
7. Entra como Admin: este agente con snapshots no muestra Eliminar agente.
8. Crea otro agente sin congelarlo. Admin ve Eliminar agente y confirma su nombre.
   Desaparece del inventario; en Trazas/auditoría figuran agent.deleted y version.discarded.
9. Verifica Evaluaciones → solicitar aprobación → aprobar con otro usuario → publicar →
   Playground → consulta → traza, usando las instrucciones existentes del README.

## Reproducción local

Con Docker disponible y el entorno local de demostración configurado según README:

```sh
make migrate
make up
make seed
make runtime-seed
make governance-seed
make knowledge-seed
make test
make lint
make web-check
npm run test:e2e
```

Para ejecutar solo las pruebas del ciclo de vida usando PostgreSQL local y las
dependencias instaladas, configura DATABASE_URL sin imprimir sus credenciales:

```sh
RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_agent_lifecycle.py \
  apps/api/tests/test_management_api.py apps/api/tests/test_audit_history_api.py -q
.venv/bin/ruff check apps/api scripts
.venv/bin/ruff format --check apps/api scripts
npm run lint
npm run typecheck
npm test
npm run build
```

## Evidencia de esta implementación

Entorno local aislado: PostgreSQL **17.9 + pgvector**, base bia_lifecycle_tests,
puerto 55439; FastAPI 18039; Next.js 13039; Chrome/Playwright. Docker no estaba
disponible. No se utilizaron credenciales LLM ni se modificó Railway.

| Comprobación | Resultado real |
| --- | --- |
| Pytest completo con integración y seguridad | **301 PASS, 1 FAIL** en 63.37 s |
| Fallo pendiente | test_postgres_migration_roundtrip_and_readiness exige PostgreSQL 16; el servidor devuelve 170009 |
| Pruebas dedicadas de ciclo de vida | **15 PASS**, incluida migración poblada ida/vuelta, roles del propietario, restricciones SQL y carreras |
| Migración CLI desde esquema limpio, replay, check, downgrade base y upgrade | PASS, incluida en Pytest completo |
| Flujo de despliegue protegido | PASS; identidad real, grants explícitos, RAG, evaluación y publicación |
| Ruff y formato | PASS, 99 archivos Python |
| ESLint y TypeScript | PASS |
| Pruebas unitarias web | **19 PASS** |
| Build Next.js | PASS |
| Playwright completo | **9 PASS** en 12.4 s |
| Playwright de gestión repetido con Admin sobre agente de otro propietario con snapshots | **2 PASS** |
| Smoke HTTP de gobernanza actualizado | PASS: 9/9, dos publicaciones, rollback y bloqueo de 4 fallos críticos |

El flujo E2E de gestión verifica borrador inicial, edición, congelación, derivación,
bloqueo mientras hay draft, descarte de v2, nueva v3 y snapshot v1 intacto tras
recargar. El E2E de eliminación comprueba confirmación, cancelación, conflicto de
revisión, usuario sin privilegios, pantalla móvil y lista actualizada. Los demás
E2E verifican aprobación independiente, publicación, LangGraph, cálculo de 64.400
COP/23 %, RAG y trazas reales. Las respuestas de modelo de estas pruebas usan el
modo determinista identificado; no son generación de proveedor.

Smoke persistido localmente: agente quality-smoke-a4809ab34695, evaluación
eval-e9d237bc8f364c449acb9790584f7dfe, ejecución autorizada
run-39470a7e0c8e4dbcb990404f6ac47b01 y denegada
run-b43eb22932fe490b8bca41660b63c0ee. El script informó provider_calls=0.

Comandos ejecutados para las comprobaciones finales (también se ejecutaron las
pruebas focalizadas durante la corrección):

```sh
DATABASE_URL=postgresql+psycopg://kennyzhu@127.0.0.1:55439/bia_lifecycle_tests \
  RUN_DB_TESTS=1 .venv/bin/pytest -q --tb=short
DATABASE_URL=postgresql+psycopg://kennyzhu@127.0.0.1:55439/bia_lifecycle_tests \
  RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_agent_lifecycle.py -q --tb=short
.venv/bin/ruff check apps/api scripts
.venv/bin/ruff format --check apps/api scripts
npm run lint
npm run typecheck
npm test
npm run build
E2E_BASE_URL=http://127.0.0.1:13039 API_PORT=18039 \
  PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
E2E_BASE_URL=http://127.0.0.1:13039 API_PORT=18039 \
  PLAYWRIGHT_CHANNEL=chrome npm run test:e2e -- tests/e2e/management.spec.ts
```

Se preparó exclusivamente la nueva base local mediante command.upgrade(head),
command.check y los cuatro seeds existentes, con Settings app_env=test,
enable_demo_auth=true, enable_local_runtime=true, enable_access_token_auth=false,
enable_published_runtime=false y enable_provider_runtime=false. Los tokens se
leyeron de Settings sin imprimirlos. Para iniciar los servidores se ejecutó:

```sh
DATABASE_URL=postgresql+psycopg://kennyzhu@127.0.0.1:55439/bia_lifecycle_tests \
  APP_ENV=test ENABLE_DEMO_AUTH=true ENABLE_ACCESS_TOKEN_AUTH=false \
  ENABLE_LOCAL_RUNTIME=true ENABLE_PUBLISHED_RUNTIME=false ENABLE_PROVIDER_RUNTIME=false \
  .venv/bin/uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 18039
BACKEND_URL=http://127.0.0.1:18039 npm run dev --workspace @bia/web -- --port 13039
```

El smoke HTTP se lanzó con este wrapper, que solo copia los tokens locales al
entorno del script y no los muestra:

```sh
PYTHONPATH=apps/api SMOKE_API_URL=http://127.0.0.1:18039 .venv/bin/python - <<'PYCODE'
import os
import runpy
from app.core.config import Settings
settings = Settings()
for role in ("creator", "approver", "auditor"):
    os.environ["DEMO_" + role.upper() + "_TOKEN"] = getattr(
        settings, "demo_" + role + "_token"
    ).get_secret_value()
runpy.run_path("scripts/governance_smoke.py", run_name="__main__")
PYCODE
```

Los servidores de comprobación se detuvieron al terminar. La base temporal conserva
sus datos sintéticos. Los logs de esta sesión están en /private/tmp/bia-lifecycle-*.

## Archivos modificados

- Backend: apps/api/app/agents/{models,schemas,service,routes}.py y app/api/health.py.
- Migración nueva: apps/api/migrations/versions/0007_agent_lifecycle.py.
- Seeds compatibles: apps/api/app/runtime/seed.py y app/knowledge/seed.py.
- Prueba nueva: apps/api/tests/test_agent_lifecycle.py.
- Regresión adaptada: test_management_api.py, test_management_unit.py,
  test_agent_contract.py, test_audit_history_api.py, test_runtime_api.py,
  test_governance_api.py y test_deployment.py, en apps/api/tests.
- Frontend: apps/web/src/app/agents/[id]/page.tsx,
  src/components/delete-agent-dialog.tsx, src/lib/studio.ts y src/lib/help.ts.
- E2E: tests/e2e/{agent-deletion,management,governance}.spec.ts.
- Smoke: scripts/governance_smoke.py.
- Documentación: README.md, docs/architecture.md, este documento,
  docs/decisions/ADR-010-agent-management.md y notas de sustitución en las guías
  docs/catalog-and-agent-actions.md y docs/ux-context-evaluations-deletion.md.

## Pendientes y límites

Falta repetir la comprobación específica de PostgreSQL 16 con Docker disponible
(`make test`, usando la imagen pgvector/pgvector de Compose). No se debilitó ni
omitió la aserción de versión para presentar todo en verde. Tampoco se verificó
Railway ni se invocó un proveedor LLM real. Los cambios están implementados y
probados localmente con la salvedad anterior; no constituyen validación de producción.
No se añaden nuevas reglas de evaluación, aprobación, publicación ni permisos.

