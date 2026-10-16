# Verificación de cierre del Sprint 3

Fecha: 2026-10-15. Referencias: [AGENTS.md](../AGENTS.md),
[arquitectura](architecture.md), [ADR-010](decisions/ADR-010-agent-management.md),
[ADR-011](decisions/ADR-011-agent-runtime.md) y [reporte de implementación](sprint-3-report.md).

**Seguimiento:** la [prueba posterior con credencial real](sprint-3-provider-check.md)
provisionó v2 y alcanzó OpenAI, pero la generación fue rechazada por saldo agotado.
Las referencias a entorno sin credenciales describen la verificación inicial.

**Resultado:** runtime local y los cinco escenarios solicitados verificados.
**Pendiente:** validación end-to-end con un proveedor LLM real. No se declara
verificada esa integración contra un proveedor ni completada la Definition of
Done del MVP entero. No se implementó ni se avanzó al Sprint 4.

## Contraste de requisitos e implementación

| Requisito | Evidencia y estado |
| --- | --- |
| AGENTS §5: Control Plane y Execution Plane separados | Registry/catálogos en `agents/` y `catalogs/`; ejecución/política/gateway en `runtime/`; herramientas y dominio en `billing/`. Monolito modular, sin servicios adicionales. |
| AGENTS §7–8; arquitectura §7: LangGraph real | Contenedor: LangGraph **1.2.15**, objeto **`langgraph.graph.state.CompiledStateGraph`**. `graph.py` construye StateGraph, compila y `service.py` ejecuta `ainvoke`. Estado TypedDict y contexto confiable separado, START/END, ramas y failure explícitos. |
| Consulta y comparación | HTTP real contra facturas en PostgreSQL. 344.400 − 280.000 = **64.400 COP (23 %)**; diferencia de **70 kWh**, efecto consumo 56.000 y tarifa 8.400. Consulta individual: 8 nodos/2 tools; comparación: 9 nodos/3 tools. |
| AGENTS §9; arquitectura §9: identidad y autorización en backend | Identidad del token; no del mensaje/cuerpo/LLM. Grant exacto de versión, permisos del caller y snapshot, aprobación/contrato revalidados, consultas por ID y owner. Factura ajena denegada; traza ajena 404, incluso para admin. Pruebas de inyección y revocación sin sustituir la autorización. |
| AGENTS §10, §13: versiones y persistencia | Cada run referencia versión, hash, modelo y workflow. Grants solo a snapshots; runs terminales inmutables, logs append-only. Migración head `0003_agent_runtime`, roundtrip y drift probados. |
| AGENTS §12: determinismo y proveedor diferenciados | El modo de demo declara plantilla sin LLM; los valores proceden de lecturas y cálculos nuevos. Gateway opcional LiteLLM implementado, pero **no hay credenciales y el flag está deshabilitado**. Tests con dobles de SDK, no validación externa real. |
| AGENTS §15, §17: errores, límites y seguridad | Suite cubre budgets de pasos/llamadas, timeout global/modelo/tools, retries acotados, errores tipados, invalidación de evidencia, inyección y fugas de secretos. Timeout SQL real `pg_sleep` comprobado en esquema aislado. |
| AGENTS §16: interfaz funcional | Playground usa APIs reales; consulta/compara/deniega/escala, muestra traza, historial y métricas nulas cuando no existen. E2E verifica la ejecución exacta por ID tras recarga. |
| AGENTS §4: stack visual objetivo | Se conserva CSS existente, diferencia ya documentada en ADR-010. No se introdujo una migración a Tailwind/shadcn durante esta verificación. |
| Arquitectura §8: Knowledge/RAG | Tarifas/FAQ aprobadas y vigentes por SQL. Sin ingesta, embeddings, pgvector, RAG o Knowledge Registry completo. Limitación explícita, no se presenta como RAG. |
| AGENTS §22; arquitectura §12: MVP completo/publicación | No implementado: evaluación, aprobación, publicación y gating del Sprint 4. Los snapshots con grants solo permiten preview local. Autenticación demo y runtime local bloqueados en producción. |

## Qué es real y qué es determinista

- **Real en los dos modos:** StateGraph, autorización, consultas SQL, herramientas,
  cálculos `Decimal`, validación de evidencia, persistencia y trazas.
- **Modo actual `deterministic`:** Python construye una plantilla textual con
  los datos recuperados y calculados en esa petición. Sí hay frases de plantilla;
  no se presentan como generación de un modelo. La respuesta empieza por
  `Modo determinista de prueba; sin llamada a un proveedor`. El selector y la
  ayuda del Playground lo explicitan. Tokens y coste permanecen `null`.
- **Prueba contra respuesta fija:** en un esquema de integración aislado se
  cambia la factura a 421 kWh/345.220 COP. La siguiente ejecución devuelve
  **65.220 COP/71 kWh**, y la traza anterior conserva su resultado original.
  No se modificaron las facturas del entorno de demo para esta prueba.
- **Modo opcional `provider`:** `runtime/gateway.py` llama a
  `litellm.acompletion` con modelo aprobado fijado en snapshot, credencial del
  servidor, timeout y sin fallback. En este primer diseño el LLM **solo ordena
  afirmaciones y citas calculadas por Python**; no redacta libremente, elige
  herramientas ni calcula importes. La UI también advierte esta limitación.
- **En este entorno ninguna parte llamó a un LLM real:**
  `ENABLE_PROVIDER_RUNTIME=false`, sin claves OpenAI/Anthropic y solo modelos
  sintéticos aprobados. Los tests sustituyen la frontera de I/O del SDK; sus
  conteos de tokens son fixtures, no uso real. No se inventan métricas ni se
  declara un proveedor probado. Para verificarlo faltan credenciales del
  servidor y un modelo real aprobado/compatible, como documenta README.

## Demostración HTTP y SQL después del reinicio

Los IDs completos y hashes están en [la evidencia JSON](sprint-3-verification.json).
Todos corresponden a ejecuciones nuevas reales, en `billing-assistant` v1,
hash de snapshot `3033f6ef1a4d05cc5d76a1d0bd0c0134b2faf9053e6b421d02621adb0c6f2442`.

| Caso | Run ID | Resultado comprobado |
| --- | --- | --- |
| Consulta autorizada INV-1002 | `run-9f5ab56396ec45bf9f5b925a4d15baab` | completed; 344.400 COP; 8 eventos, 2 calls |
| Comparación INV-1002 con agosto | `run-5cdea5f9a995496c91bcac56db9ca706` | completed; +64.400 COP/+70 kWh; 9 eventos, 3 calls |
| Creator solicita INV-2002 de B | `run-e285ff6f0fe946b4bfc284dcd1ca08a3` | denied / INVOICE_NOT_ACCESSIBLE; sin evidencia liberada; 4 eventos, 1 call |
| Falla herramienta del período previo: INV-1001 sin julio | `run-f10e664f6c224dee8497132e29278595` | escalated / PREVIOUS_INVOICE_UNAVAILABLE; previous failed → failure; 5 eventos, 2 calls |
| B consulta su INV-2002 | `run-0c9db57ab6284c489a03145aabfbc1ef` | completed; +27.000 COP; 9 eventos, 3 calls; traza del creator no accesible para B |

Se reinició la API y se volvieron a consultar **las mismas cinco trazas**:
los cinco SHA-256 se conservaron exactamente. Una sesión SQL independiente
confirmó cada run, estado, número de eventos y llamadas después del reinicio.
Esto demuestra persistencia más allá de memoria del proceso. No equivale a
recuperación automática de un run interrumpido, que todavía no está implementada.

El caso de herramienta ausente no es una simulación de proveedor: falta realmente
la factura de julio en los datos sintéticos. Además, el test de timeout sustituye
solo el adaptador de I/O por `SELECT pg_sleep(3)` contra PostgreSQL real y confirma
`TOOL_TIMEOUT` con dos intentos acotados; no se añade ningún interruptor de fallos
a las APIs de producción ni se sustituye la autorización.

## Comandos ejecutados y resultados

```sh
make verify > /tmp/bia-sprint3-audit-verify.log 2>&1
.venv/bin/pytest -m 'not integration' -q
.venv/bin/ruff check apps/api scripts
.venv/bin/ruff format --check apps/api scripts
git diff --check
RUN_DB_TESTS=1 .venv/bin/pytest -v apps/api/tests/test_runtime_api.py -k 'real_stategraph or recomputed or invoice_only or durable_failed or cross_customer or adapter_uses_postgres'
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
docker compose ps -a
```

| Check | Resultado final |
| --- | --- |
| make verify | exit 0: build, migraciones, seeds, suite, lint, frontend y ambos smoke |
| Pytest completo PostgreSQL 16 | **169 passed**: 56 unitarias y 113 integración; 16,39 s |
| Unitarias nativas | **56 passed**, 113 deselected |
| Seis casos críticos aislados | **6 passed**, 42 deselected; 3,36 s |
| Ruff | sin errores; 54 archivos formateados |
| Frontend | build producción, ESLint y TypeScript correctos; **13 tests passed** |
| Playwright Chrome | **3 passed**, 3,1 s; recorrido runtime ampliado con los cinco pasos y persistencia |
| Alembic | head `0003_agent_runtime`; `No new upgrade operations detected.` |
| Servicios después de reinicio | api/web/postgres healthy; migrate Exited (0) |

El primer intento del E2E ampliado terminó con 2 passed/1 failed porque el
selector exacto no encontraba el desplegable Consulta. Se corrigió el selector
de la prueba; la repetición terminó con 3 passed. No se ocultó el fallo ni se
alteró autorización o lógica de negocio para hacer pasar el test.

La inspección Python dentro del contenedor verificó el tipo real del grafo,
la versión de LangGraph y la ausencia de credenciales sin imprimir secretos.
También se leyeron las cinco filas y sus contadores mediante SQLAlchemy en
otra sesión. GitHub Actions remoto no se ejecutó; esta es evidencia local.
Se mantiene el pendiente de cinco avisos previos del tooling ESLint documentado
en README; esta revisión no actualiza esas dependencias.

Comandos ejecutados para repetir la evidencia de reinicio sin copiar tokens:

```sh
docker compose exec -T api python - < scripts/runtime_smoke.py > /tmp/bia-sprint3-audit-flow.log
docker compose restart api
docker compose up -d --wait --wait-timeout 60 api web
BIA_RUNTIME_PROOF="$(head -n 1 /tmp/bia-sprint3-audit-flow.log)"
docker compose exec -T -e RUNTIME_TRACE_PROOF="$BIA_RUNTIME_PROOF" api python - < scripts/runtime_smoke.py
```

El último comando devolvió:
`PASS: all five persisted traces retain their exact SHA-256 after API restart.`
El archivo de evidencia solo contiene IDs/hashes/resultados sintéticos, no tokens.

## Archivos modificados en esta revisión

- `apps/api/tests/test_runtime_api.py`: tipo CompiledStateGraph, recálculo dinámico,
  consulta individual y fallo con persistencia consultada en sesión independiente.
- `scripts/runtime_smoke.py`: cinco escenarios HTTP, datos de B, IDs, hashes de
  trazas y comprobación opcional de persistencia después de reinicio.
- `tests/e2e/runtime.spec.ts`: consulta/comparación/denegación/fallo y reapertura
  de la ejecución exacta por ID, además de la identificación del modo.
- `apps/web/src/app/playground/page.tsx`: aclaración visible de plantilla
  determinista y alcance limitado del proveedor.
- `README.md`, `docs/sprint-3-report.md`: pasos, resultados actualizados y puerto.
- `docs/sprint-3-verification.md` y `.json`: matriz y evidencia verificable.

El listado completo de archivos del Sprint 3 permanece en el reporte principal.
Se conservaron cambios anteriores y `.vscode/` del usuario. `.env` mantiene el
puerto 8001 de la corrección anterior y continúa ignorado por Git.

## Pasos exactos desde el Playground

1. En Terminal, desde la raíz, ejecuta `make demo-env` y `make verify` con
   Docker Desktop listo. El `.env` debe tener `ENABLE_DEMO_AUTH=true` y
   `ENABLE_LOCAL_RUNTIME=true` en development; se preservan valores existentes.
2. Abre `http://localhost:3000/playground`. La API de este Mac está en
   `http://localhost:8001/docs` por el conflicto anterior con 8000.
3. Inicia sesión con el **valor** de `DEMO_CREATOR_TOKEN` de `.env`. Selecciona
   Billing Assistant v1 / synthetic-balanced-v1 y **Determinista · sin proveedor**.
   Usa un mensaje como `Explica esta factura con los datos disponibles`.
4. Consulta **Consultar factura**, `INV-1002`: ejecuta y comprueba completed,
   344.400 COP, 8 nodos y 2 herramientas. No hay consulta de factura previa.
5. Cambia a **Comparar con el mes anterior**, misma factura: ejecuta y comprueba
   64.400 COP, 23 %, 70 kWh; abre **Cálculos deterministas en Python** y revisa
   56.000 COP por consumo y 8.400 por tarifa. La traza contiene 9 nodos y 3 calls.
6. Mantén comparación y solicita `INV-2002`: debe mostrar denied,
   INVOICE_NOT_ACCESSIBLE y ninguna evidencia de la factura ajena.
7. Compara `INV-1001`: debe mostrar escalated, PREVIOUS_INVOICE_UNAVAILABLE,
   intento fallido de invoice-previous-v1 y nodo failure; no comparación inventada.
8. Recarga e identifícate otra vez. En **Mis ejecuciones** abre los IDs recién
   creados y comprueba que cada resultado conserva su traza. El ID del run, hash
   de snapshot y versión del workflow aparecen sobre la respuesta.
9. Cierra sesión, entra con el valor de `DEMO_CUSTOMER_B_TOKEN`: compara
   `INV-2002` y comprueba +27.000 COP. `INV-1002` debe denegarse y el historial
   no debe mostrar ejecuciones del creator.
10. Comprueba el rótulo determinista y que tokens/coste dicen no reportados/no
    disponible. No selecciones proveedor esperando generación real sin haber
    registrado un modelo aprobado y configurado las credenciales del servidor.

## Pendientes y condición de cierre

La validación real del proveedor sigue pendiente. El gateway está implementado
con pruebas de contrato y errores, pero no se considera probado contra un LLM
externo. Antes de declarar cerrado ese criterio hace falta aprobar un modelo
compatible, configurar su credencial en servidor, ejecutar `provider` e inspeccionar
respuesta, referencias, errores y uso realmente reportado. No se inventa esa prueba.

Otros pendientes explícitos: SSO, ciclo de publicación/evaluaciones/aprobaciones,
Knowledge Registry/RAG completos, recuperación de ejecuciones interrumpidas y
operación de producción. El runtime síncrono puede dejar un run running si el
proceso muere abruptamente; conservar trazas no implica reanudar el workflow.

No se avanzó al Sprint 4. Los criterios críticos del runtime local están
verificados; la verificación con proveedor externo queda abierta y el MVP
completo no se declara terminado.
