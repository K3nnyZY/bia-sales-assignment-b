# Correcciones verificadas de integración local

Fecha: 2026-10-16. Este trabajo modifica implementación y pruebas; el documento
registra los resultados posteriores a la auditoría. No es una aprobación de
producción ni un avance a Sprint 7.

## Cambios implementados

- **Dashboard `/dashboard`:** inventario visible de agentes/colecciones, ejecuciones
  por estado, tools/errores, latencia, uso de modelos con cobertura y últimas cinco
  ejecuciones enlazadas a su traza. Usa las APIs existentes con bearer y scope
  backend. Incluye carga, actualización, errores y vacíos. No concede permisos.
- **Métricas compartidas:** Dashboard y Trazas usan `MetricsPanel`, conservando
  null como no disponible y costos como estimaciones, nunca cobros reales.
  `/` conserva el health público de infraestructura.
- **E2E Knowledge:** cada ejecución crea una colección propia desde la UI, carga,
  ingesta, aprueba, busca y verifica la cita. Se mantiene la consulta genérica y
  sus aserciones; se elimina la dependencia del top-k del corpus compartido.
  No se borra historial ni se modifica el ranking de producción.
- **Dependencias Python:** `pypdf` 6.10.2 → 6.19.0 y `python-multipart` 0.0.22 →
  0.0.31, con lock reproducible. La imagen activa usa esas versiones.
- **Secretos locales:** `.env` pasó de 0644 a 0600 sin cambiar su contenido.
- **README:** preparación nativa de pesos/seed Knowledge, migración 0005,
  estructura del módulo y uso del dashboard. Auditorías previas se conservan
  como históricas y enlazan este resultado.

No se añadieron servicios, tablas, permisos, migraciones, autenticación ficticia
para producción, respuestas simuladas de proveedor ni métricas inventadas.

## Pruebas y resultados ejecutados

| Comando | Resultado |
| --- | --- |
| `make verify` | **Exit 0: 252 Pytest aprobadas en 54.46 s**, PostgreSQL real, roundtrip de migraciones, Ruff (88 archivos), ESLint/TypeScript, build Next, 15 pruebas frontend y smokes S1–5. |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | **Exit 0: 7/7 en 10.7 s** en la última ejecución, incluyendo nuevo Dashboard. Primera ejecución completa también pasó 7/7. |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e -- tests/e2e/knowledge.spec.ts --repeat-each=2` | **Exit 0: 2/2 en 5.1 s**, con historial existente y nuevos corpus aislados. |
| `node scripts/final_ui_audit.mjs` | Exit 0: Markdown → ingesta → aprobación documental → búsqueda/cita → configurar → snapshot → evaluar 9/9 → solicitar → otro aprobador → publicar → LangGraph + factura + RAG → Trace Viewer. |
| `docker compose exec -T api python - < scripts/knowledge_audit.py` | Exit 0: PDF/TXT/Markdown, extracción, seis chunks, embeddings reales cotejados con vector(256), idempotencia, vigencia, autorización y comparación. |
| `docker compose exec -T api python - < scripts/governance_audit.py` | Exit 0: métricas API/SQL y cadena de hashes coinciden; findings vacío. |
| `docker compose exec -T api alembic -c apps/api/alembic.ini current` | `0005_knowledge_rag (head)`. |
| `docker compose exec -T api alembic -c apps/api/alembic.ini check` | Sin nuevas operaciones de upgrade. |
| `npm run lint`, `npm run typecheck`, `npm test` | Exit 0; además comprobados dentro de `make verify`. |
| `.venv/bin/uv tool run --cache-dir /tmp/bia-final-uv-cache pip-audit --path .venv/lib/python3.14/site-packages --format json --output /tmp/bia-s6-fix-python.json` | **Exit 0: 107 paquetes, cero avisos conocidos**. |
| `npm audit --json` | Cinco avisos high en tooling de desarrollo; no corregidos. |
| `npm audit --omit=dev --json` | Cero avisos de dependencias de ejecución frontend. |
| `git diff --check` | Sin errores. |

Se ejecutó también el auxiliar temporal `node /tmp/bia-s6-fix-ux.mjs`: diez
pantallas a 390×844, esperando cada URL antes de medir; ninguna desborda el ancho
de página. Incluye estados vacíos, error de token y carga con latencia real de
red introducida mediante Chrome DevTools, sin mocks de API/autorización. Se
inspeccionó la captura móvil. El E2E permanente del dashboard verifica los
valores contra `/metrics`, el scope del viewer, vacíos y navegación a una traza.
No se certifica toda la accesibilidad o matriz de dispositivos.

Los cálculos siguen siendo **64400.00 COP y 23.00 %**, con nueve nodos de un
`CompiledStateGraph` real, tres tool calls y un retrieval. La ejecución de UI
es **determinista y etiquetada**; no se hizo una nueva llamada LLM pagada.
Tokens/costo permanecen null en ese run. Embeddings locales sí son reales.
IDs, versiones y resultados están en [la evidencia](sprint-6-fixes-evidence.json).

Persistencia verificada con:

```sh
rag_proof=$(docker compose exec -T api python - < scripts/knowledge_smoke.py)
docker compose restart api
docker compose up -d --wait api
docker compose exec -T -e KNOWLEDGE_TRACE_PROOF="$rag_proof" api python - < scripts/knowledge_smoke.py
```

PASS: run, nodos, herramientas y retrieval mantienen el hash tras reiniciar API.
Health API y proxy web devuelven database/migrations ok. No se eliminó el volumen.

## Archivos modificados en esta corrección

- `apps/web/src/app/dashboard/page.tsx` (nuevo).
- `apps/web/src/components/metrics.tsx` (nuevo).
- `apps/web/src/app/traces/page.tsx` (reutiliza el panel).
- `apps/web/src/components/studio.tsx`, `apps/web/src/app/globals.css`.
- `tests/e2e/dashboard.spec.ts` (nuevo), `tests/e2e/knowledge.spec.ts`.
- `pyproject.toml`, `uv.lock`.
- `README.md`, `docs/architecture.md`, `docs/final-demo-guide.md`.
- Aviso de actualización en `docs/final-audit.md` y `docs/sprint-6-checklist-audit.md`.
- Este reporte y `docs/sprint-6-fixes-evidence.json`.
- Permiso local de `.env`; su contenido no se versiona ni se imprime.

El árbol ya contenía cambios S4–5 antes de este trabajo. Se conservaron; no se
atribuyen todos los cambios de `git diff` a esta corrección. No se hizo commit,
push ni publicación externa.

## Pendientes reales

Los tres parciales funcionales locales —Dashboard, E2E y regresión— quedaron
resueltos en los escenarios comprobados. El checklist recibido tenía 17 criterios;
no se inventa un criterio 18 para declarar 18/18.

- **Tooling npm:** `braces@3.0.3` sigue afectado. El registro consultado devuelve
  esa misma versión como latest; `eslint-config-next@latest` sigue siendo 16.4.2
  y depende de la misma cadena. No hay un parche publicado compatible identificado.
  No se degradó Next/ESLint ni se deshabilitaron reglas para ocultar avisos.
- **Producción:** sigue sin proveedor de identidad productivo y sin hosting
  público validado. Las protecciones que rechazan demo auth en production se
  conservan. La demo continúa limitada a loopback en Docker.
- **Entrega reproducible en Git:** falta revisar/versionar los cambios existentes
  S4–6 y validar un checkout limpio/CI remoto. El HEAD previo es Sprint 3.
- **Secretos externos:** no se puede certificar la rotación de una clave compartida
  anteriormente. El escaneo local de código/historia/bundles no encontró claves.
- Se corrigieron las instrucciones nativas, pero no se repitió un arranque nativo
  completo desde cero. El procedimiento comprobado es Docker.

## Cómo probar desde el Mac

Requiere Docker Desktop; para navegador automatizado, Node 24 y Google Chrome.

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
open -a Docker
make env
make demo-env
make verify
npm ci
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
node scripts/final_ui_audit.mjs
open http://localhost:3000/dashboard
```

En Dashboard entra con un token **de Studio** de `.env`, nunca la API key de
OpenAI. Creator muestra sus métricas; viewer sin ejecuciones muestra vacíos.
Desde el menú abre Playground: selecciona la versión publicada del agente que
imprime el procedimiento, canal Published, modo deterministic, Compare e
INV-1002. Debe dar 64400.00 COP/23.00 %, referencias y enlace a la traza.
INV-2002 debe ser denegada para creator. API: http://localhost:8001/docs en este Mac;
`.env.example` usa 8000 si no se cambia. No hace falta un LLM externo.

Logs de esta corrección: `/tmp/bia-s6-fix-verify.log`, `bia-s6-fix-e2e-final.log`,
`bia-s6-fix-e2e-repeat.log`, `bia-s6-fix-ui.log`, `bia-s6-fix-rag.json`,
`bia-s6-fix-ux.log`, `bia-s6-fix-persistence.log`, `bia-s6-fix-python.json`,
`bia-s6-fix-npm.json`, `bia-s6-fix-npm-runtime.json`, `bia-s6-fix-metrics.json`, todos
bajo `/tmp`. No compartir trace.zip con cabeceras bearer.
