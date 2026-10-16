# Sprint 5 — Knowledge & RAG

Auditoría posterior: [verificación independiente del pipeline](sprint-5-audit.md)
conserva los resultados históricos de este reporte y añade la corrección KW-01
para fragmentos con espacios en sus bordes, 252 tests y evidencia SQL reproducible.

Fecha: 2026-10-16. Alcance: Sprints 1–5; Sprint 6 no iniciado.

## Implementado

- Knowledge Registry con colecciones, propietarios, clasificación y grants explícitos administrados por backend; documentos y versiones con vigencia, fuente, hashes, ingesta y aprobación/revocación.
- Pipeline real de PDF con texto, TXT y Markdown: extracción aislada/acotada, chunking con solapamiento, embeddings multilingües Model2Vec fijados a revisión inmutable, almacenamiento `vector(256)` y búsqueda híbrida coseno + texto español/RRF.
- Filtros SQL de identidad, colección, clasificación, aprobación y vigencia antes del ranking; reautorización antes de devolver evidencia. Citas documento/versión/chunk verificables y logs persistidos con latencia real, referencias y errores.
- Originales inmutables en la abstracción `DatabaseObjectStore` de PostgreSQL, sin servicio adicional. Upload multipart acotado en backend y proxy Next.js.
- Configuraciones/snapshots con referencias documentales exactas y hash del pipeline/modelo. Integración con evaluación y Publication Gate; nuevas versiones de documentos no reemplazan fuentes fijadas. La revocación bloquea uso/publicación sin alterar historial.
- Adaptador aprobado `billing-knowledge-v2` conectado al StateGraph real existente. Herramientas de facturas, identidad de cliente y cálculos Decimal permanecen operativos. El adaptador v1 conserva snapshots anteriores.
- Interfaz `/knowledge`: crear colecciones/documentos, cargar versiones, ejecutar/reintentar ingesta, aprobar/revocar, gestionar grants administrativos, buscar y verificar fragmentos. Builder configura referencias documentales; Playground y Trace Viewer muestran retrieval real.
- Seeds idempotentes de tarifas/FAQ sintéticas y nuevo snapshot de `billing-assistant`. En este Mac el snapshot RAG es v3; el número depende del historial y lo imprime el seed.

## Archivos de este sprint

Nuevos:

- `apps/api/app/knowledge/{__init__,models,schemas,service,routes,embeddings,extract,upload_limit,runtime,seed}.py`.
- `apps/api/migrations/versions/0005_knowledge_rag.py`.
- `apps/api/tests/test_knowledge_api.py`, `test_knowledge_unit.py`.
- `apps/web/src/app/knowledge/page.tsx`.
- `scripts/download_embeddings.py`, `scripts/knowledge_smoke.py`.
- `tests/e2e/knowledge.spec.ts`.
- `docs/decisions/ADR-013-knowledge-rag.md`, `docs/sprint-5-guide.md`, este reporte.

Modificados para integrar S5:

- `.gitignore`, `.dockerignore`, `.env.example`, `compose.yaml`, `Makefile`, `pyproject.toml`, `uv.lock`, `apps/api/Dockerfile`, `.github/workflows/ci.yml`.
- Backend: `agents/{schemas,service}.py`, `billing/tools.py`, `runtime/{graph,policy,routes,schemas}.py`, `governance/{policy,evaluator}.py`, `core/config.py`, `db/models.py`, `main.py`, `api/health.py`, `migrations/env.py`.
- Tests existentes: `conftest.py`, `test_database.py`, `test_health.py`.
- Frontend: Builder `app/agents/[id]/page.tsx`, proxy `app/api/studio/[...path]/route.ts`, `components/{studio,trace}.tsx`, `app/playground/page.tsx`, `lib/{studio,runtime}.ts`, `tests/studio.test.ts`.
- `README.md`, `docs/architecture.md`.

El árbol ya contenía cambios sin commit del Sprint 4. Se conservaron; no se atribuyen todos los archivos de `git status` al Sprint 5. No se hicieron commits ni se eliminó el volumen existente.

## Comandos y resultados reales

- `.venv/bin/uv add 'pgvector==0.4.2' 'pypdf==6.10.2' 'python-multipart==0.0.22' 'model2vec==0.7.0'`: dependencias instaladas y lock actualizado.
- `.venv/bin/python scripts/download_embeddings.py`: descarga real de pesos públicos, revisión `73908c3438cf03b6a01bcb9611d62b23d0726f08`. Inferencia local, sin proveedor pagado.
- `docker compose up -d --wait postgres`: PostgreSQL 16 pasó a imagen con pgvector conservando datos.
- `PYTHONPATH=apps/api .venv/bin/alembic -c apps/api/alembic.ini upgrade head`: aplicado 0005.
- `PYTHONPATH=apps/api .venv/bin/python -m app.knowledge.seed`: ingesta y embeddings reales; snapshot v3.
- `RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_knowledge_unit.py apps/api/tests/test_knowledge_api.py -q`: **25 passed, 10.40 s**, antes de extender el caso de publicación.
- `RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_knowledge_api.py::test_rag_evaluation_publication_gate_and_revoked_evidence -q`: **1 passed, 3.91 s**, incluyendo evaluación → aprobación independiente → publicación → ejecución → bloqueo por revocación.
- `make verify`: **exit 0**. Última ejecución completa: **249 Pytest passed, 50.69 s**, contra PostgreSQL real; roundtrip de migraciones, repetición idempotente y `alembic check`; Ruff lint y formato (**87 archivos**); ESLint, TypeScript, build Next.js y **15 pruebas frontend**; smokes HTTP, runtime, gobernanza y RAG.
- `.venv/bin/ruff check apps/api scripts`, `.venv/bin/ruff format --check apps/api scripts`, `git diff --check`: sin errores.
- `make web-check` tras corregir el Playground: **exit 0**, build Next.js, ESLint, TypeScript y **15/15** pruebas frontend.
- `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e`: **6 passed, 10.0 s**. Incluye cargar → ingerir → aprobar documento → buscar → verificar cita → ejecutar agente → inspeccionar retrieval, además de los cinco flujos anteriores.
- `docker compose exec -T api alembic -c apps/api/alembic.ini check`: **No new upgrade operations detected** sobre la base persistida, además del roundtrip aislado.
- `docker compose exec -T postgres psql -U bia -d bia_studio -c "SELECT extversion FROM pg_extension WHERE extname='vector';"`: **0.8.7**.
- `docker compose exec -T api python - < scripts/governance_audit.py`: **exit 0**, métricas SQL/API y cadena snapshot/evaluación/aprobación coincidentes, `findings: []`.
- Captura mediante `scripts/knowledge_smoke.py`, `docker compose restart api`, `docker compose up -d --wait api` y repetición con `KNOWLEDGE_TRACE_PROOF`: **PASS**, hash exacto de run, nodos, herramientas y retrieval conservado tras reinicio. Run persistido `run-d00ee2d450694eaa9676f24531ecac7e`.

La suite de seguridad no sustituye la lógica de autorización. Incluye acceso ajeno, grants/clasificación, evidencia no aprobada/expirada/revocada, revocación durante generación, prompt injection, metadatos hostiles, upload acotado, duplicados, reingesta, inmutabilidad SQL y persistencia. Se mantienen las regresiones de cálculo, herramientas, permisos, publicación, rollback y auditoría S1–4.

La verificación detectó y corrigió nombres duplicados de constraints, aislamiento de la tabla Alembic al compartir `public.vector`, credenciales inconsistentes entre fixtures y el ejecutable Python del build. Los intentos iniciales no se reportan como aprobados. El test de navegador se ajustó para esperar datos asíncronos y usar contenido único: repetir contenido idéntico en otro documento debe producir 409. También detectó un fallo real de interfaz: faltaba mostrar el retrieval en Playground. Se corrigió reutilizando el mismo componente del Trace Viewer y se repitieron los seis E2E, todos aprobados. Docker Desktop dejó de estar disponible durante otro intento; se restauró y las verificaciones finales se hicieron con el stack healthy. Ningún intento interrumpido se cuenta como aprobado.

## Evidencia del smoke final

`make verify` produjo:

- Run RAG: `run-995797a11e1f4bf3ab58284b4d392345`.
- Search: `search-d92c2f437bcc44a58357e54a406c4b3e`.
- Diferencia: **64400.00 COP**, **23.00 %**.
- Referencias: `INV-1002`, `INV-1001`, `billing-tariffs-rag@1#chunk-0`, `billing-faq-rag@1#chunk-0`.
- Nueve nodos reales StateGraph, tres tool calls, registro de retrieval asociado.
- Run ajeno rechazado: `run-c66321317265477bb461097567aa11a1`.
- Gobernanza: suite 9/9 y candidata insegura bloqueada con cuatro fallos críticos; agente sintético independiente `quality-smoke-05ef5c2e8e14`.

Los logs de trabajo de esta sesión están en `/tmp/bia-s5-verify-final.log`, `/tmp/bia-s5-focused-2.log`, `/tmp/bia-s5-publication.log`, `/tmp/bia-s5-web-check-final.log`, `/tmp/bia-s5-e2e-complete.log`, `/tmp/bia-s5-persistence-result.log` y `/tmp/bia-s5-governance-audit-final.log`. Son archivos locales temporales; los IDs anteriores están persistidos en la base local.

## Verificación manual y límites

Pasos completos, endpoints, permisos y comandos Mac en [la guía](sprint-5-guide.md).
Arquitectura y decisiones en [ADR-013](decisions/ADR-013-knowledge-rag.md).

Embeddings: semánticos reales, locales y multilingües. Generación verificada: **modo determinista**, explícitamente etiquetado; no se llamó OpenAI/Anthropic en esta verificación. El gateway LiteLLM existente sigue disponible para modelos aprobados y credenciales del servidor; no se afirma validación actual de cuota/proveedor. Uso/costos del proveedor permanecen no disponibles si no existe una llamada real verificable.

Límites: ingesta síncrona pequeña, sin OCR, S3, antivirus, conectores externos, colas/recuperación o cuotas globales. Chunking por caracteres con solapamiento, no parser estructural completo. Embeddings estáticos y umbrales requieren evaluación de calidad para otro corpus. Los filtros de inyección son defensa adicional y no garantizan detectar todas las formulaciones; permisos y salida se controlan independientemente en backend. La autenticación de demostración no es desplegable en producción.

Fallos críticos pendientes en los checks ejecutados: **ninguno**. Las limitaciones anteriores siguen explícitamente fuera de alcance.

Próximo milestone: Sprint 6, **no iniciado**.
