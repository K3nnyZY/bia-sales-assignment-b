# Auditoría Sprint 5 — Knowledge & RAG

Fecha: 2026-10-16. Se leyeron `AGENTS.md`, `docs/architecture.md`, ADR-010/011/012/013,
el código, las pruebas y README. Alcance: auditoría y corrección del Sprint 5;
**Sprint 6 no iniciado**. Los resultados siguientes corresponden a comandos ejecutados
nuevamente, no se reutilizan como prueba los resultados del reporte anterior.

## Resultado y hallazgo corregido

El flujo completo funciona después de corregir **KW-01**: `Evidence` heredaba
`str_strip_whitespace=True` del contrato de metadatos. Con fragmentos que empezaban
o terminaban con espacios/saltos de línea, Pydantic alteraba el texto, conservaba
el hash original y la reautorización devolvía un falso `403 KNOWLEDGE_CHANGED`.
La ingesta original y sus vectores estaban correctos; fallaba la serialización de
la evidencia antes de responder. Los documentos pequeños de los tests anteriores
no ejercitaban estos bordes.

Se reprodujo con una prueba nueva: **1 failed, 2.77 s**, antes del cambio.
Se corrigió exclusivamente el campo `Evidence.content` con
`StringConstraints(strip_whitespace=False)`. No se debilitan permisos ni comparación
de hashes, no se modifican chunks/versiones existentes, no cambian los contratos
JSON Schema de herramientas, ni se necesita otra migración. Después de la corrección
pasan **28 pruebas de Knowledge**, la regresión completa y la ingesta nueva multiformato.

Fallos críticos pendientes en las comprobaciones ejecutadas: **ninguno**.
Esto no equivale a certificar toda la arquitectura empresarial o seguridad productiva.

## Pruebas ejecutadas

| Comando | Resultado real |
| --- | --- |
| `make verify` inicial | Exit 0; 249 Pytest, 46.91 s; checks y smokes anteriores aprobados, aunque no cubrían KW-01 |
| `RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_knowledge_api.py -q` con los dos checks de filtros | 15 passed, 10.84 s |
| `RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_knowledge_api.py::test_audit_multichunk_evidence_preserves_whitespace_and_hashes -q` antes del fix | 1 failed, 2.77 s, error real `KNOWLEDGE_CHANGED` |
| `RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_knowledge_api.py apps/api/tests/test_knowledge_unit.py -q` después del fix | 28 passed, 13.40 s |
| `make verify` final | **Exit 0; 252 passed, 54.96 s**, PostgreSQL real; Ruff; build/lint/typecheck Next.js; **15/15 tests frontend**; smokes infraestructura/runtime/gobernanza/RAG |
| `docker compose exec -T api python - < scripts/knowledge_audit.py` | **Exit 0**, ingesta nueva PDF/TXT/Markdown, cotejo de vectores y citas SQL, reingesta, fechas y ejecución real |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | **6 passed, 8.4 s**, incluido carga/ingesta/aprobación/búsqueda/citas/Playground |
| `docker compose exec -T api alembic -c apps/api/alembic.ini check` | **No new upgrade operations detected** en la base persistida |
| `docker compose exec -T api python - < scripts/governance_audit.py` | **Exit 0**, métricas SQL/API y hashes de publicación coinciden; `findings: []` |
| `.venv/bin/ruff check apps/api scripts` | All checks passed |
| `.venv/bin/ruff format --check apps/api scripts` | 88 archivos formateados |
| `git diff --check` | Sin errores |

La regresión incluye Foundation/migraciones, Registry/configuraciones/versionamiento,
StateGraph, cálculos Decimal, herramientas/errores/timeouts, acceso entre clientes,
inyección, suites/evaluaciones, permisos de aprobación/publicación, hash exacto,
separación de funciones, inmutabilidad, rollback, auditoría, métricas y frontend.
Las pruebas de autorización usan identidades/grants reales en PostgreSQL; no
sustituyen la lógica de autorización.

Los intentos del script de auditoría también permitieron ajustar su uso al contrato
existente de grants (`POST` y motivo obligatorio); no se cambiaron esos contratos
ni se presentan los intentos incompletos como éxitos del pipeline.

## Evidencia de la ingesta completa

Se conservó el resultado real en [sprint-5-audit-evidence.json](sprint-5-audit-evidence.json).
El script crea datos nuevos y únicamente sintéticos mediante APIs autenticadas.
La lectura SQL posterior es una comprobación independiente de persistencia.

Colección y agente de auditoría: `s5-audit-f591c0b050de`, snapshot v1.
Hash: `e6a1568617e2a6978b1eec9763c678de7621ecd8d0677569e698cac5c17a22e0`.
El billing-assistant existente y sus publicaciones no se alteraron.

| Documento nuevo | Extracción | Versiones después de repetir upload/ingesta | Chunks | Tipo PostgreSQL |
| --- | ---: | ---: | ---: | --- |
| `s5-audit-f591c0b050de-txt` | 1188 caracteres | 1 | 2 | vector(256) |
| `s5-audit-f591c0b050de-md` | 1187 caracteres | 1 | 2 | vector(256) |
| `s5-audit-f591c0b050de-pdf` | 1188 caracteres | 1 | 2 | vector(256) |

Se comprobaron bytes originales en `knowledge_objects`, SHA-256 del archivo,
texto extraído y offsets de todos los chunks. Se recalcularon **los seis vectores**
con los pesos locales de Model2Vec y se compararon con los almacenados usando
`numpy.allclose(atol=1e-7)`; también se comprobó norma cercana a uno y dimensiones
mediante `pg_typeof(embedding)` y `vector_dims(embedding)` en PostgreSQL.
Los hashes de texto y de vectores no cambiaron tras repetir las cargas e ingestas.

Modelo real: `minishlab/potion-multilingual-128M`, revisión
`73908c3438cf03b6a01bcb9611d62b23d0726f08`, Model2Vec 0.7.0, 256 dimensiones.
La prueba semántica multilingüe existente también pasó. No se emplearon vectores
hash simulados ni se sustituyó el modelo para esta comprobación.

## Permisos antes del retrieval y vigencia

La prueba nueva de preautorización captura el SQL de una petición sin grant y
comprueba que **no consulta `knowledge_chunks` ni alcanza el límite de embeddings**.
Solo se sustituye el límite de embeddings por una aserción para detectar llamadas
indebidas; identidad, permisos, API y base de datos son reales. El rechazo queda
registrado con referencias vacías y `KNOWLEDGE_FORBIDDEN`.

La prueba de ranking inspecciona las ocho consultas reales (semántica y léxica,
cuatro fechas) y confirma joins/predicados de usuario activo, grants activos,
clasificación, aprobación y límites de vigencia antes del ordenamiento/limit.
El backend vuelve a comprobar la evidencia antes de devolverla y antes de liberar
la respuesta del agente. La revocación durante generación sigue cubierta.

Los documentos nuevos son válidos **del 2026-08-01 al 2026-09-30**, inclusivos:

| Fecha consultada | Fragmentos devueltos |
| --- | ---: |
| 2026-07-31 | 0 |
| 2026-08-01 | 6 |
| 2026-09-30 | 6 |
| 2026-10-01 | 0 |

Por tanto, estar vencidos respecto al día de la auditoría no impide una consulta
histórica autorizada: se usa la fecha comercial consultada. Creator puede consultar
su colección; viewer sin grant y administrator sin grant de lectura reciben **403**.
Ser administrador del catálogo no concede acceso documental implícito. Los tests
existentes verifican además clearance restricted, colecciones mixtas, fuentes
no aprobadas, revocación y rechazo de instrucciones hostiles.

## Búsqueda → LangGraph → referencias PostgreSQL

- Búsqueda nueva: `search-9e2fcf56f8414cf0a8a09f1120fc4413`.
- Run: `run-afc08307f91f46b2a4a3a09c91eb7971`, completed, nueve nodos reales:
  authorize → route → invoice → previous → knowledge → calculate → generate →
  validate_output → finalize.
- Herramientas, en orden: `invoice-lookup-v3`, `invoice-previous-v1`, `billing-knowledge-v2`.
- Citas liberadas y verificadas en `knowledge_chunks`, incluyendo su contenido/hash:
  `s5-audit-f591c0b050de-pdf@1#chunk-0`,
  `s5-audit-f591c0b050de-txt@1#chunk-0`,
  `s5-audit-f591c0b050de-md@1#chunk-0`,
  `s5-audit-f591c0b050de-md@1#chunk-1`.

Cada cita aparece tanto en las referencias como en la respuesta del run y en el
registro de retrieval. El endpoint de verificación de fragmentos devolvió texto
y hash coincidentes con la evidencia de búsqueda.

Las facturas **no proceden del índice RAG**. Las dos herramientas transaccionales
resolvieron `INV-1002` e `INV-1001`, y la comprobación SQL de `invoices`, restringida
al caller, reconcilió la diferencia **64400.00 COP y 23.00 %**. Los chunks nuevos
no contienen esos identificadores de factura. La búsqueda documental del runtime
solo recibe el período y las referencias autorizadas, no una identidad del prompt.

Acceso a factura ajena: `run-963a5aa6f67b48a689d4834d91052252`, denied; sin
referencias liberadas y **sin retrieval posterior** al rechazo de la herramienta.
Consulta documental del 2026-10-01: `run-2003d5d85cec409ea41c90ed3cdbd667`, escalated,
`KNOWLEDGE_UNAVAILABLE`; no inventa evidencia vencida.

Generación: **modo determinista etiquetado**. Embeddings: **reales y locales**.
No se invocó OpenAI/Anthropic para generar estas respuestas; tokens/costos de
proveedor se mantuvieron no disponibles. El gateway LiteLLM permanece implementado,
pero esta auditoría no certifica una llamada externa ni su cuota actual.

## Archivos modificados en esta auditoría

- `apps/api/app/knowledge/schemas.py`: corrección KW-01, conserva el texto de evidencia.
- `apps/api/tests/test_knowledge_api.py`: tres pruebas nuevas: rechazo antes del acceso,
  filtros SQL/vigencia inclusiva y preservación de espacios/hash en varios chunks.
- `scripts/knowledge_audit.py`: nuevo procedimiento reproducible HTTP + SQL.
- `docs/sprint-5-audit.md`, `docs/sprint-5-audit-evidence.json`: reporte y evidencia real.
- `docs/decisions/ADR-013-knowledge-rag.md`, `docs/sprint-5-guide.md`,
  `docs/sprint-5-report.md`, `README.md`: aclaración de preservación de texto y guía de auditoría.

El repositorio ya tenía cambios sin commit de Sprints 4–5. Se conservaron. No se
atribuyen a esta auditoría todos los archivos que aparecen en `git status`.
No hubo migraciones nuevas ni refactorizaciones fuera del hallazgo.

## Reproducción desde el Mac y limitaciones

Con Docker Desktop activo, desde la raíz:

```sh
make verify
docker compose exec -T api python - < scripts/knowledge_audit.py
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
docker compose exec -T api alembic -c apps/api/alembic.ini check
docker compose exec -T api python - < scripts/governance_audit.py
```

E2E requiere `npm ci`, Node 24 y Chrome; alternativamente instala Chromium con
`npx playwright install chromium` y ejecuta `npm run test:e2e` sin especificar canal.
El script de auditoría crea historial sintético nuevo y lo conserva. Desde Studio,
usa `DEMO_CREATOR_TOKEN`, abre Playground y selecciona el agente de auditoría que
imprima el script para inspeccionar su traza, o `/traces?run=<run_id>` tras iniciar sesión.
API local actual: 8001; frontend: 3000. No hacen falta claves LLM para estos comandos.

Límites/diferencias respecto a la arquitectura objetivo: chunking por caracteres
con solapamiento, no parser estructural; clasificación por colección; originales
en PostgreSQL detrás de una abstracción, sin S3; no OCR, antivirus, cuotas globales,
workers/recuperación o conectores externos. El billing workflow utiliza una consulta
documental fija para tarifas/FAQ, sin planificación de retrieval por LLM. Los
embeddings estáticos y el ranking requieren calibración para otros corpus; no se
ha medido calidad general ni resistencia universal a inyección. Las fronteras de
permisos backend y validación cerrada de salida siguen siendo necesarias. La
autenticación local continúa deshabilitada para producción. El frontend conserva
el CSS propio documentado en ADR-010 en lugar de migrar a Tailwind/shadcn.

Logs reales de esta sesión: `/tmp/bia-s5-audit-verify-final.log`,
`/tmp/bia-s5-audit-focused-final.log`, `/tmp/bia-s5-audit-whitespace-before.log`,
`/tmp/bia-s5-audit-pipeline-proof.log`, `/tmp/bia-s5-audit-e2e.log`,
`/tmp/bia-s5-audit-governance.log`. La evidencia JSON del repositorio y los runs
persistidos permiten inspeccionar los resultados después de esta sesión.

Próximo milestone: Sprint 6, **no iniciado**.
