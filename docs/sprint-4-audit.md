# Auditoría del Sprint 4

Fecha de revisión: **2026-10-16** (America/Bogota).

**Actualización:** AUD-01 está corregido y verificado. La última pasada terminó
con 224 pruebas backend y cinco E2E aprobados; el verificador devuelve
`findings: []`. Véase el [reporte de cierre de AUD-01](sprint-4-aud01-fix.md).
Los resultados y referencias siguientes conservan la evidencia de la auditoría inicial.

**Resultado de la auditoría inicial, antes de corregir AUD-01:** el flujo crítico local de evaluación → aprobación → publicación →
ejecución → rollback cumple las comprobaciones ejecutadas. No se encontró una
sustitución de configuración que evadiera el gate. Hay **un hallazgo funcional
medio pendiente en la consulta de auditoría**; no corresponde declarar todo el
Sprint 4 sin pendientes. No se inició Sprint 5.

Se revisaron AGENTS.md, los apartados de publicación, consistencia, evaluación,
observabilidad y seguridad de architecture.md, ADR-010/011/012, implementación,
pruebas y README. Esta revisión valida el entorno local y los escenarios descritos;
no equivale a una auditoría productiva o una garantía universal de seguridad.

## Hallazgo pendiente

### AUD-01 — Los filtros de auditoría omiten eventos de metadatos del agente

**Severidad: media. Estado actual: corregido y verificado; descripción histórica a continuación.**

`agent.created`, `agent.updated` y `agent.deleted` se registran con
`details.resource_id`, dejando `AuditEvent.agent_id` nulo. La consulta
`GET /audit-events?agent_id=...` solo filtra la columna `agent_id`. La vista del
propietario además hace un inner join usando esa columna. Como consecuencia,
los eventos de creación/edición no aparecen en su historial por agente; el visor
global del auditor los muestra como «Catálogo». Los eventos siguen en PostgreSQL:
no es una pérdida de persistencia ni permite publicar sin evaluación.

Evidencia de código:

- [agents/routes.py](../apps/api/app/agents/routes.py), líneas 48, 64 y 84:
  los eventos contienen `resource_id` pero no `agent_id`.
- [governance/routes.py](../apps/api/app/governance/routes.py), líneas 156–170:
  el filtro y el join usan exclusivamente `AuditEvent.agent_id`.
- [traces/page.tsx](../apps/web/src/app/traces/page.tsx): un evento sin agent_id
  se etiqueta como Catálogo.

Reproducción de solo lectura con `scripts/governance_audit.py`:

- Agente: `quality-smoke-d3648f6b586a`.
- Evento persistido y omitido: `aud-fe0cb81d81864068ae76334c6768a19d`.
- El evento queda fuera tanto del filtro del auditor como del propietario.
- El comando devolvió **exit 2**, indicando este hallazgo; no fue contado como PASS.

La corrección debe resolver la referencia de estos eventos de forma consistente
en la API y la UI, preservando la autorización y el historial de agentes eliminados.
Vincularlos simplemente mediante una FK obligatoria volvería a impedir eliminar
agentes vacíos, comportamiento permitido por Sprint 2. Conviene añadir regresión
específica para creación, edición, borrado y aislamiento entre propietarios.

## Pruebas ejecutadas y resultados reales

| Comando / comprobación | Resultado |
| --- | --- |
| `make verify` | **Exit 0**: arranque/migraciones/seeds, Pytest, Ruff, frontend y tres smokes |
| Pytest incluido en verify | **213 passed en 39.11 s**, sin fallos ni omisiones |
| Ruff lint y formato finales | **PASS**, 71 archivos Python formateados |
| ESLint, TypeScript, build Next.js | **PASS** dentro del flujo Docker |
| node:test del frontend | **13 passed**, ninguna omitida |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | **4 passed en 8.4 s**; ciclo de gobernanza en 4.5 s |
| Alembic current | `0004_quality_governance (head)` |
| Alembic check | `No new upgrade operations detected.` |
| Roundtrip de migraciones | PASS en Pytest: upgrade repetido, ausencia de drift, downgrade/base y upgrade en esquema temporal |
| Trazas después de reiniciar API | **PASS**: SHA-256 idénticos en tres trazas; evaluación y evento de rollback accesibles |
| Auditoría SQL/API independiente | Hashes y métricas **PASS**; consulta de metadatos **FAIL / exit 2**, AUD-01 |
| `git diff --check` | PASS |
| CI remoto / proveedor LLM real | No ejecutados en esta auditoría |

Los 213 casos incluyen la regresión de Sprint 3: StateGraph real, respuesta
recalculada desde facturas persistidas, Decimal, acceso entre clientes, prompt y
document injection, herramientas revocadas, aislamiento de trazas, límites,
reintentos, fallos y timeouts de herramientas/SDK. Los dobles del SDK y adapters
solo se usan en pruebas aisladas para provocar situaciones controladas; la
autorización no se sustituye por mocks.

Los smokes y el recorrido UI de esta auditoría son deterministas: **cero llamadas
a proveedores**. Tokens y costos no disponibles permanecen nulos. Una prueba del
gateway con un doble del SDK comprueba conteos/costos reportados; no demuestra
que un proveedor real haya generado una respuesta exitosa.

## Comprobación específica de configuración evaluada y aprobada

Se añadieron **siete casos** al conjunto de integración, sin cambiar la lógica
de producción:

1. Evaluar y aprobar A; crear B con instrucciones distintas; intentar solicitar o
   publicar B usando el hash de A: **409**. Con el hash propio, B también se
   rechaza porque no está evaluada/aprobada.
2. Adjuntar `evaluation_id` y `approval_id` de A en el body de publicación de B:
   **422**, campos no admitidos.
3. Publicar A enviando el hash de B: **409 / CONFIG_HASH_MISMATCH**.
4. Editar A tras aprobación: **409**. Publicar A correctamente conserva el mismo
   snapshot y hash evaluados. Estos escenarios comparten un caso de prueba.
5. Clonar la misma configuración sin cambios: el nuevo snapshot tiene otro hash
   por su identidad/versión. Vincular por SQL evaluación/aprobación de A a B
   viola los triggers; transacción revertida, publicación original intacta.
6. Rollback con creator/viewer/reviewer/auditor: **403**, cuatro casos parametrizados.
7. Rollback a una versión antes aprobada después de revocar una herramienta:
   **409 / PUBLICATION_GATE_BLOCKED**, sin cambiar el puntero ni su revisión.

Son siete casos Pytest: un caso para la sustitución API, uno para SQL, cuatro
para roles y uno para rollback con dependencias revocadas. Se mantienen las
pruebas anteriores de autoaprobación, suites incompletas, fallos críticos,
reevaluación que invalida aprobación, inmutabilidad de historial y publicación
concurrente con un único ganador.

La protección se distribuye entre snapshot/hash canónico inmutable, gate de la
última evaluación exacta, aprobación asociada a esa evaluación y triggers de
consistencia. El hash por sí solo no concede aprobación ni permiso de publicación.

## Flujo real desde la interfaz

Playwright usó Next.js y FastAPI reales, sin interceptar ni simular APIs:

1. Creator creó el agente y configuró billing v1 con modelo sintético y herramientas
   registradas; guardó y congeló v1.
2. Ejecutó la suite **9/9**, solicitó aprobación y comprobó que creator no podía aprobar.
3. Otra identidad con rol approver aprobó y publicó.
4. Creator ejecutó por canal **published** y obtuvo **64.400 COP** de diferencia.
5. Auditor abrió la traza y la volvió a consultar tras recargar la interfaz.
6. La prueba capturó la respuesta real de `/api/studio/metrics` y comprobó que los
   contadores visibles coincidían. Capturó `/api/studio/runs/{id}/trace` y la
   comparó, completa, con `GET /api/v1/runs/{id}/trace` directo a FastAPI.
   Verificó hash visible, respuesta, nueve eventos y tres tool calls.

Esto comprueba el origen de los datos en el backend, además de inspeccionar el
cliente `useResource`, el proxy y las consultas SQL de observabilidad. Las
mediciones corresponden a ejecuciones locales/sintéticas; no representan un
benchmark de rendimiento de un LLM productivo.

## Evidencia de backend y persistencia

Último smoke de gobernanza:

- Agente: `quality-smoke-d3648f6b586a`, publicación activa v1 tras rollback.
- Evaluación: `eval-a9464627ba4d407d8c569300a10aa575`, **9/9 PASS**.
- Aprobación: `apr-9cd867cd259045d0922b949be9edd673`.
- Hash verificado por SHA-256 independiente, snapshot = evaluación = aprobación:
  `bd242abe7c8a522564f866771c5694ccb28e52b883e9d8865838f905d0679843`.
- Consulta autorizada: `run-d19f7f852459483790e0e75b7fa1016c`.
- Acceso denegado: `run-03dbcd93a13f40ca9a437c774b21bddb`.
- Período anterior ausente: `run-4c9341d7bce84fb8a02ef914dd79724a`.
- La candidata con max_tool_calls=1 tuvo **cuatro fallos críticos** y quedó bloqueada.
- Esas tres trazas conservaron exactamente su SHA-256 tras reiniciar el backend.

La comparación independiente SQL/API observó, en ese momento, **116 runs no
pertenecientes a evaluación**, **247 tool calls**, **51 tool calls con estado
no completed**, P50 **35.651 ms** y P95 **152.012 ms**. Todos coincidieron con el
endpoint. Son acumulados de la base local; cambiarán con nuevas ejecuciones.

## Funcionalidades parciales y diferencias frente al diseño objetivo

| Área | Alcance actual / pendiente |
| --- | --- |
| Auditoría | Historial append-only del ciclo de versiones funciona; AUD-01 omite metadatos en filtros. Los rechazos tempranos de acciones de gobernanza tampoco generan un audit_event específico; los runs denegados sí quedan registrados. |
| Evaluaciones | Solo nueve escenarios predefinidos para billing v1, con fixtures aislados. No hay grader de calidad lingüística, umbrales de groundedness/relevancia ni benchmark representativo. Suites nuevas se administran por API; UI selecciona/ejecuta existentes. |
| LLM | Gateway LiteLLM real presente; modo proveedor opcional requiere cuota/credenciales y evaluación compatible. No hubo prueba real de proveedor aquí. La salida permite ordenar afirmaciones verificadas, no generación libre. |
| Métricas / FinOps | Conteos, latencias y uso por modelo/modo reales. Costos solo estimados con uso conocido; faltan conciliación, costo por departamento/tarea correcta y presupuestos monetarios por agente/departamento. |
| Recuperación | Evaluaciones y runs síncronos/acotados. Caída abrupta puede dejar running; no hay reconciliación/checkpoints persistentes ni workers de recuperación. |
| Publicación | Solo entorno local explícito. Preview permite probar snapshots con grant sin publicación/evaluación; únicamente Published exige el gate. Agent.status conserva disponibilidad draft/disabled/deprecated; el ciclo published vive en version_governance. No debe interpretarse el antiguo Agent.state como estado de publicación. |
| Conocimiento | Aprobación/vigencia, referencias por run y fingerprint de dependencias. No hay selección de colecciones/referencias de conocimiento fijadas en el manifiesto publicado como propone AGENTS §10; falta Knowledge Registry/RAG, fuera de este sprint. |
| UI / historial | Runs/auditoría muestran hasta 100 recientes; evaluaciones/aprobaciones hasta 30. No hay navegación completa de historial antiguo. Se conserva CSS propio y cliente ligero, diferencia documentada en ADR-010 frente a Tailwind/shadcn del diseño objetivo. |
| Autenticación / despliegue | Tokens demo confiables para local, bloqueados en producción. SSO, endurecimiento, separación operativa de roles de DB, carga y CI remoto quedan sin verificar. |

Estas limitaciones no permiten afirmar cumplimiento completo de la definición
empresarial de MVP de AGENTS §22. Los controles críticos locales de publicación
y regresión sí pasaron las pruebas descritas.

## Comandos utilizados y reproducción

Desde la raíz del checkout:

```sh
make verify > /tmp/bia-s4-audit-verify.log 2>&1
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e > /tmp/bia-s4-audit-e2e.log 2>&1
.venv/bin/ruff check apps/api scripts
.venv/bin/ruff format --check apps/api scripts
git diff --check
docker compose ps -a
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
docker compose exec -T api python - < scripts/governance_audit.py
```

El último comando es de solo lectura, compara SQL/API y devuelve **2** mientras
AUD-01 siga presente. Necesita los seeds y un quality-smoke creado por verify;
no es un error de conexión ni un test crítico de publicación fallido.

Para extraer exactamente el mismo proof del verify y comprobar reinicio:

```sh
python3 - <<'PY'
import json
from pathlib import Path
lines = Path('/tmp/bia-s4-audit-verify.log').read_text().splitlines()
proof = next(json.loads(line) for line in reversed(lines)
             if line.startswith('{"agent_id": "quality-smoke-'))
Path('/tmp/bia-s4-audit-proof.json').write_text(json.dumps(proof))
PY
docker compose restart api
docker compose up -d --wait api
docker compose exec -T -e GOVERNANCE_TRACE_PROOF="$(cat /tmp/bia-s4-audit-proof.json)" api python - < scripts/governance_smoke.py
```

Este reinicio y el último comando se ejecutaron y terminaron en PASS. En una
instalación nueva los IDs/hashes/mediciones serán distintos. La API de este Mac
está en 8001, la web en 3000. No se borraron datos ni se llamó al proveedor LLM.

## Archivos de esta auditoría

- `apps/api/tests/test_governance_api.py`: siete casos adicionales de seguridad/gate/rollback.
- `tests/e2e/governance.spec.ts`: comparación UI/proxy/FastAPI de métricas y trazas.
- `scripts/governance_audit.py`: verificación independiente de solo lectura y reproducción de AUD-01.
- `docs/sprint-4-audit.md`: este reporte, con resultados y pendientes.
- `README.md`: enlace a esta auditoría.

Se conservaron los cambios previos de Sprint 4 que ya estaban en el checkout.
La lógica de aplicación no se modificó en esta auditoría. AUD-01 sigue pendiente;
Sprint 5 no se implementó.

## Comprobación adicional del checklist

A petición del checklist, se añadieron dos pruebas específicas:

- Crear por API una suite `billing-checklist` v2 como reviewer, ejecutarla sobre
  billing-assistant y volver a consultar sus nueve resultados persistidos,
  severidad crítica/no crítica, duración y estado PASS/FAIL.
- Inyectar únicamente en la prueba una regresión numérica de Python (60.000 COP
  y 20 % en lugar de 64.400 COP y 23 %), manteniendo grafo, herramientas y
  autorización reales. La comparación falla, la evaluación queda failed y se
  rechazan solicitud y publicación con 409. El fallo no se introdujo en producto.

Comando realmente ejecutado tras añadir estas pruebas:

```sh
RUN_DB_TESTS=1 .venv/bin/pytest -q --tb=short
.venv/bin/ruff check apps/api scripts
.venv/bin/ruff format --check apps/api scripts
git diff --check
```

Resultado actualizado del backend: **215 passed en 47.20 s**. Ruff y formato
aprobados (71 archivos). El frontend no cambió desde los 13 tests y cuatro E2E
aprobados de la auditoría anterior. Este resultado complementa los 213 casos
registrados arriba; no representa otra ejecución de los checks frontend.

El checklist funcional de publicación, hash, permisos, separación de funciones,
inmutabilidad, rollback, trazas y regresión pasó. Resultados usan severidad
binaria crítica/no crítica; no hay niveles adicionales de severidad. Las suites
se crean por API; la UI permite ejecutarlas. Los costos siguen siendo
estimaciones cuando hay uso conocido; de otro modo, se muestran no disponibles.
AUD-01 permanece pendiente, por lo que no debe afirmarse cierre total sin
pendientes. Sprint 5 no se inició como parte de esta comprobación.
