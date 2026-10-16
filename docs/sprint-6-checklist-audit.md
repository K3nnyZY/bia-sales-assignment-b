# Comprobación del checklist Sprint 6

> Actualización posterior: se corrigieron el dashboard, el E2E Knowledge, las
> dependencias Python, los permisos de `.env` y las instrucciones nativas.
> Consulta [las correcciones verificadas](sprint-6-fixes.md) para el estado actual.
> Los resultados y el dictamen de abajo corresponden a la revisión previa.


Fecha: 2026-10-16. Comprobación del árbol de trabajo existente; no implementación
de Sprint 6 ni aprobación de entrega. Se releyeron AGENTS.md, arquitectura y ADRs
aplicables. El texto recibido contiene 17 criterios identificables, aunque indica
18/18. No se inventa un criterio adicional.

Resultado: **14 criterios verificados para demo local y tres parciales**.
"Verificado" describe los escenarios ejecutados, no una certificación universal.

| Criterio | Estado | Evidencia o límite |
| --- | --- | --- |
| Dashboard | Parcial | Portada con salud real de API/DB/migraciones; métricas operativas en Trazas. No hay dashboard consolidado de producto. |
| Agent Registry | Verificado | Playwright crea, lista y abre agentes persistidos. |
| Agent Builder | Verificado | UI guarda configuración con modelo y herramientas aprobados; backend valida permisos. |
| Versionamiento | Verificado | Playwright congela/clona/reabre versiones; Pytest comprueba rechazo de edición de snapshots/publicados también en SQL. |
| Knowledge | Verificado | UI carga Markdown, ingesta, consulta estado ready y aprueba; pruebas de PDF/TXT y errores dentro de la regresión. |
| RAG | Verificado | Consulta y verificación de cita desde UI, búsqueda pgvector híbrida y evidencia autorizada; smoke y pruebas reales contra PostgreSQL. |
| Evaluaciones | Verificado | Suite 9/9 ejecutada y resultados persistidos visibles en UI. |
| Aprobaciones | Verificado | Creator solicita; approver distinto aprueba/publica. Pruebas backend rechazan roles y autoaprobación. |
| Publicación | Verificado | Smokes y Pytest bloquean controles críticos fallidos, dependencias revocadas y hash distinto del evaluado. |
| Playground | Verificado | Ejecución published con nueve nodos del StateGraph real. |
| Facturación | Verificado | Herramientas transaccionales para facturas y Python Decimal: 64400.00 COP, 23.00 %. |
| Seguridad entre clientes | Verificado | Pytest, smoke y Playwright rechazan factura ajena y acceso a trazas fuera del scope. |
| Trazas | Verificado | UI y backend muestran nueve nodos, tres tools, un retrieval; fallo de herramienta persistido por smoke. Métricas contrastadas con SQL. |
| UX | Verificado con alcance limitado | Navegación, token inválido, listas vacías y carga reales; nueve pantallas sin desbordamiento horizontal a 390×844. No certifica toda accesibilidad/dispositivos. |
| Pruebas E2E | Parcial | El flujo crítico completo pasa, pero la suite estándar termina con cinco pases y un fallo Knowledge. |
| Regresión | Parcial | 252 Pytest y checks frontend pasan; permanece el fallo E2E del Sprint 5. |
| URLs y persistencia | Verificado localmente | Web localhost:3000, API localhost:8001; trazas conservan hash tras reiniciar API. No hay despliegue público validado. |

## Comandos y resultados actuales

Ejecutados desde la raíz, con el entorno Docker local existente:

| Comando | Resultado |
| --- | --- |
| `make verify` | Exit 0; 252 Pytest en 56.17 s, Ruff check/formato (88 archivos), ESLint, TypeScript, 15 pruebas frontend, construcción de imágenes y smokes S1–5. |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | Exit 1; 5 passed, 1 failed, 14.1 s. |
| `node scripts/final_ui_audit.mjs` | Exit 0; documento → ingesta → aprobación documental → búsqueda/cita → agente → snapshot → evaluación → aprobación independiente → publicación → billing/RAG → Trace Viewer. |
| `node /tmp/bia-s6-ux-check.mjs` | Exit 0; procedimiento auxiliar Chrome sin mocks de API ni autorización, tamaño 390×844, estados vacíos/carga/error. |
| `docker compose exec -T api alembic -c apps/api/alembic.ini current` | `0005_knowledge_rag (head)`. |
| `docker compose exec -T api alembic -c apps/api/alembic.ini check` | No new upgrade operations detected. |
| `docker compose exec -T api python - < scripts/governance_audit.py` | Exit 0; métricas API/SQL y cadena de hashes coinciden, findings vacío. |
| `curl -fsS http://127.0.0.1:8001/health/ready` | API, database y migrations ok. |
| `curl -fsS http://127.0.0.1:3000/api/health` | Health backend ok, error null. |
| `git diff --check`, `node --check scripts/final_ui_audit.mjs` | Exit 0. |

La comprobación de persistencia se ejecutó con:

```sh
rag_proof=$(docker compose exec -T api python - < scripts/knowledge_smoke.py)
docker compose restart api
docker compose up -d --wait api
docker compose exec -T -e KNOWLEDGE_TRACE_PROOF="$rag_proof" api python - < scripts/knowledge_smoke.py
```

Resultado: PASS, el hash de la traza completa coincide tras el reinicio.

## Evidencia de interfaz y límites

- Agente nuevo: `final-audit-1792140134596`, versión 1, published.
- Run: `run-317af86b82414983829c413464d3c6c8`, completed, canal published.
- Modo deterministic explícito; no llamada a proveedor LLM. Tokens y costo null.
- Nueve nodos, tres tools, un registro de retrieval y referencias verificadas.
- Prueba móvil en `/`, `/agents`, `/models`, `/tools`, `/knowledge`, `/playground`,
  `/evaluations`, `/traces` y `/agents/billing-assistant`: ancho de página 390 px
  con viewport 390 px. Incluye navegación autenticada. No se probó toda matriz
  de tamaños, todos los formularios ni un lector de pantalla.
- Estados vacíos comprobados en Registry con búsqueda sin coincidencias y Trazas
  con viewer sin ejecuciones. Carga comprobada con latencia de red introducida
  mediante Chrome DevTools; se mantienen respuestas reales del backend.
- Conciliación SQL/API: 271 runs no-evaluation, 578 tools y 122 errores de tools
  al consultar. Incluyen fallos sintéticos deliberados, no tráfico productivo.

El fallo `tests/e2e/knowledge.spec.ts:77` sigue esperando el documento recién
creado dentro del top 4 de una consulta genérica sobre un corpus acumulado.
El recorrido adicional usa una consulta identificable y pasa. No se modificaron
el test, el ranking ni el historial para ocultar el fallo.

Los avisos de dependencias, cambios S4–5 sin versionar, autenticación productiva
ausente e instrucciones nativas incompletas de la [auditoría final](final-audit.md)
siguen pendientes; no se repitieron aquí los auditores de dependencias ni el
escaneo de secretos. Una demo local funcional no cierra esos hallazgos.

Solo se añadió este reporte. No se modificó funcionalidad, dependencias ni tests.
No se implementó Sprint 7 ni se declara Sprint 6 aprobado.

Logs actuales en `/tmp/bia-s6-check-{verify,e2e,ui,ux,persistence}.log`, prueba UX
en `/tmp/bia-s6-check-ux.json` y conciliación en `/tmp/bia-s6-check-metrics.json`.
El procedimiento UI escribe `/tmp/bia-final-audit-ui.json` y
`/tmp/bia-final-ui.png`. No publicar trace.zip: puede contener bearer tokens demo.
Preparación de demo: [final-demo-guide.md](final-demo-guide.md).
