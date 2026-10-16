# Auditoría final de BIA Agent Studio — Sprints 1–6

Fecha: **2026-10-16**. Alcance: árbol de trabajo actual, HEAD `2a0035b` (Sprint 3)
con cambios locales posteriores. **El flujo funcional local está verificado;
la entrega no queda aprobada sin condiciones y producción no está habilitada.**
La generación real del proveedor falla por falta de saldo, hay avisos npm de
herramientas de desarrollo y el commit actual no contiene todos los archivos
probados. No se sustituyen esos pendientes por resultados del modo determinista.

Evidencia sanitizada: [final-audit-evidence.json](final-audit-evidence.json).
Preparación manual: [final-demo-guide.md](final-demo-guide.md).
Este reporte reemplaza el dictamen final anterior; los reportes de cada sprint
son históricos y no sustituyen estas verificaciones.

## Alcance y método

Se revisaron AGENTS.md, arquitectura, ADR-010–013, identidad, registros, contratos,
versionamiento, facturación, runtime/gateway, gobernanza, Knowledge, modelos SQL,
migraciones, seeds, scripts, frontend/proxy, pruebas, dependencias, Docker,
Compose, CI y README. Se buscaron secretos, ejecución arbitraria, destinos de red,
almacenamiento de tokens, renderizado HTML, placeholders, botones sin handlers y
métricas aleatorias. El escaneo incluye fuentes no ignoradas, historia Git y
recursos públicos; no constituye un pentest ni garantiza ausencia de todo secreto.

PostgreSQL 16, pgvector, Model2Vec, StateGraph y Chrome se ejecutaron realmente.
La autorización no se sustituye en las pruebas de seguridad. Los tests de fallos
usan dobles únicamente en límites de SDK/adaptadores, cuando corresponde. Se
intentó además generación real: el smoke falló y la repetición diagnóstica
confirmó el rechazo por cuota.
No se añadieron funcionalidades, servicios de producto ni refactorizaciones.

## Tabla de resultados

PASS significa comprobado en el alcance indicado. FAIL identifica un fallo o
requisito pendiente real. NOT VERIFIED significa que no se obtuvo evidencia
suficiente; no se considera un pase.

| Área / criterio | Estado | Evidencia y alcance |
| --- | --- | --- |
| Arquitectura modular y separación de responsabilidades | PASS | Control plane, runtime, billing, Knowledge y gobernanza mantienen módulos explícitos; permisos en backend. CSS propio documentado en ADR-010; no se afirma implementar toda la arquitectura empresarial propuesta. |
| Configuración y dependencias reproducibles | PASS | Settings/Pydantic, uv.lock, package-lock, builds y Compose; sin credenciales del proveedor en cliente web. |
| Arranque Docker local | PASS | `make verify` final exit 0, API/web/PostgreSQL healthy, migrate exit 0; puertos publicados solo en 127.0.0.1. |
| Migraciones desde PostgreSQL vacío | PASS | **Se encontró y corrigió AUD-FINAL-01**. Instancia PG16 nueva: cero tablas/cero extensión vector → 27 tablas y pgvector 0.8.7. |
| Commit de CLI, replay, downgrade/upgrade y ausencia de drift | PASS | Nueva regresión ejecuta procesos Alembic reales; dos pruebas dirigidas pasan. Comprobación adicional en PG vacío y `alembic check`. |
| Seeds e instalación Docker con datos nuevos | PASS | Cuatro seeds repetidos dos veces en la base temporal, sin duplicar entidades; readiness 200 y ejecución RAG real. |
| Agent Registry / Builder / versiones | PASS | Playwright crea, configura, congela, clona y vuelve a consultar; modelos/tools aprobados y permisos revalidados en backend. |
| Inmutabilidad y restricciones SQL | PASS | Pytest verifica snapshots, relaciones, FKs/checks, historial append-only y rechazo de cambios publicados, también con SQL directo. |
| Evaluación, gate exacto y aprobación independiente | PASS | UI 9/9; snapshot/evaluación/aprobación/run con idéntico hash y versión; creator y approver distintos. |
| Bloqueo crítico y rollback | PASS | Pytest y governance smoke rechazan fallos críticos, suites incompletas, autoaprobación, dependencias revocadas, evaluaciones de otra versión y rollback a candidatas nunca publicadas. |
| LangGraph real | PASS | `CompiledStateGraph`, estado tipado, nueve nodos en la ejecución satisfactoria, ramas/fallos/límites/timeouts probados. |
| Facturas transaccionales y cálculos | PASS | `invoices` mediante lookup/previous autorizados; Decimal: **64400.00 COP, 23.00 %**, efectos 56000.00 y 8400.00 COP. No se obtienen facturas por RAG. |
| Autorización por recurso y aislamiento entre clientes | PASS | Consulta SQL por invoice_id y caller autenticado; API/security tests, smokes y navegador rechazan factura/traza ajena y privilegios desde body/prompt. |
| Herramientas y ataques de inyección | PASS | Allowlist/versiones/esquemas y permisos antes de cada intento; pruebas de herramientas no autorizadas, revocaciones, resultados hostiles y límites. No es una garantía universal contra toda inyección. |
| Knowledge / ingesta / deduplicación | PASS | PDF, TXT y Markdown nuevos → extracción → seis chunks; reingesta conserva versiones/vectores. Límites y fallos controlados en tests. |
| Embeddings y pgvector reales | PASS | Vectores `vector(256)` coinciden con Model2Vec local versionado; SQL usa distancia coseno y ranking léxico/RRF. No se etiqueta keyword search como semántica. |
| Permisos y vigencia antes de retrieval | PASS | SQL filtra grants, clasificación, aprobación y fechas antes del ranking; viewer/admin sin grant reciben 403; revalidación antes de liberar evidencia. |
| Citas y evidencia documental | PASS | IDs de documento, versión, chunk, offsets y hashes verificados contra PostgreSQL y desde la UI. |
| Runs, tools, errores y persistencia de trazas | PASS | Trace Viewer consulta API real; run/eventos/tools/retrieval mantienen hash después de reiniciar API. |
| Métricas y costos sin invenciones | PASS | Conciliación SQL/API sin hallazgos; tokens solo reportados por SDK, estimaciones etiquetadas, null si no disponibles. Datos sintéticos locales, no benchmarks productivos. |
| Dashboard, navegación y botones funcionales | PASS | Siete E2E y recorrido adicional con APIs reales; controles conectados a acciones/estados. No se encontraron botones ficticios ni métricas aleatorias. No se probó cada combinación posible de roles/formularios. |
| UX básica y móvil | PASS | Diez pantallas a 390×844 sin desbordamiento horizontal de página, carga, vacíos y error de token comprobados; no certifica toda accesibilidad/dispositivos. |
| Unitarias, integración, seguridad y regresión S1–6 | PASS | **253 Pytest aprobadas**, PostgreSQL real, incluidas regresión nueva de CLI y pruebas de permisos/gobernanza/RAG/runtime. |
| Ruff, ESLint, TypeScript, frontend tests y build | PASS | Ruff 88 archivos, 15 pruebas frontend, lint/typecheck y Next production build correctos. |
| Playwright completo | PASS | **7/7, 13.8 s** sobre la imagen final; incluye Dashboard, gobernanza, metadatos/auditoría, Knowledge, gestión/catálogos y runtime. |
| Acceso anónimo y endpoints administrativos | PASS | 14 recursos devuelven 401 aun con X-Role/X-User-Id falsos; viewer recibe 403 en users/catálogos completos. Mutaciones administrativas y publicación cubiertas por Pytest con identidad real persistida. |
| Secretos en fuentes/historia/bundles revisados | PASS | Sin hallazgos de patrones ni coincidencias con la clave configurada; `.env` ignorado/no versionado, modo 0600, ausente de imágenes. Resultado limitado al escaneo, no una certificación absoluta. |
| Demo auth bloqueada en producción | PASS | Tres combinaciones inseguras rechazadas al configurar production; desactivadas ambas opciones, APIs protegidas dan 503, sin bypass. |
| Autenticación productiva operativa | FAIL | No existe otro proveedor de identidad: production tiene liveness 200, pero me/runs 503. Los tokens demo no sirven como autenticación productiva. |
| Dependencias Python / npm runtime | PASS | pip-audit: **107 paquetes, cero avisos conocidos**. npm omit-dev: cero avisos. Imagen API usa pypdf 6.19.0 y multipart 0.0.31. |
| Dependencias npm completas | FAIL | **Cinco avisos high** en cadena de tooling ESLint/fast-glob/micromatch/braces; sigue pendiente parche compatible. No se hizo downgrade ni se ocultaron avisos. |
| Generación LLM real satisfactoria | FAIL | `make provider-smoke` falla; diagnóstico real confirma **HTTP 429 / credit_balance_exhausted / insufficient_quota**. Sin fallback, tokens/costo null. |
| Manejo del fallo real del proveedor | PASS | Run failed y eventos generate/failure persistidos; error controlado, sin fabricar una respuesta exitosa ni uso/costo. |
| Entrega completa en el commit actual | FAIL | HEAD Sprint 3, 40 entradas modificadas y 41 no versionadas; governance/knowledge tienen cero archivos registrados en Git. Se probó el árbol de trabajo, no un clon entregable de Sprints 1–6. |
| Checkout limpio y GitHub Actions remoto | NOT VERIFIED | No se hizo commit/push ni se ejecutó CI remoto; requiere incluir los archivos revisados y verificar una copia limpia. |
| Despliegue público, TLS y acceso externo | NOT VERIFIED | Solo se verificó localhost. No hay hosting público validado; Next production build no equivale a API productiva. |
| CVEs del sistema operativo de las imágenes | NOT VERIFIED | Se auditaron dependencias Python/npm; no se ejecutó escáner completo de paquetes del SO. Bases Python/Node usan tags móviles. |
| Carga, backup/restore y recuperación de procesos | NOT VERIFIED | Sin pruebas productivas de carga/recuperación; una caída abrupta puede dejar runs/evaluaciones running. No hay workers/checkpoints de recuperación. |
| Instalación nativa completa desde cero | NOT VERIFIED | Instrucciones revisadas y checks nativos ejecutados; no se repitió todo el arranque nativo en una máquina nueva. Docker sí se verificó con base vacía. |
| Rotación de la clave compartida externamente | NOT VERIFIED | No se puede certificar desde el repositorio; no se imprime ni se considera rotada por estar en `.env`. |

## Fallo crítico corregido: AUD-FINAL-01

`migrate(connection)` consulta `current_schema()` antes de configurar Alembic.
SQLAlchemy inicia una transacción implícita. Cuando la CLI abría su conexión con
`engine.connect()`, Alembic la trataba como transacción externa y no la confirmaba;
al cerrar la conexión se revertía todo. Un comando podía terminar sin error y no
conservar tablas. Los tests anteriores proporcionaban `engine.begin()` desde
fuera, por lo que no reproducían el camino defectuoso de la CLI.

Corrección mínima: la conexión propia usa **`engine.begin()`** y confirma al salir
con éxito; las conexiones proporcionadas por el caller conservan su control.
No se cambiaron revisiones Alembic ni el esquema de datos.

La nueva prueba `test_alembic_cli_commits_migrations_on_its_own_connection` crea un
esquema único, ejecuta procesos CLI, consulta tablas desde otra conexión y verifica
replay/check/downgrade/upgrade. **Antes: FAIL, 1 prueba en 0.65 s, cero tablas
persistidas. Después: las dos pruebas de migración PASS en 2.68 s**. La suite
completa posterior pasa 253 pruebas.

Se comprobó además un contenedor PostgreSQL efímero, sin puertos publicados ni
credenciales reales: inicialmente cero tablas y cero extensión vector; después
27 tablas, revisión 0005, PG16.15 y pgvector 0.8.7. Replay, downgrade/upgrade y
check pasan. Dos vueltas de los cuatro seeds conservan: 10 usuarios, un agente,
dos versiones de agente, ocho facturas, dos versiones documentales y dos chunks.
Una ejecución con identidades aleatorias de esa base compara 64400.00 COP y
rechaza otra factura. El contenedor se eliminó; la base de demo y su historial
se conservaron.

## Evidencia del flujo real de interfaz

El script de navegador `scripts/final_ui_audit.mjs` ejecutó sin interceptar APIs:

1. Crear/cargar Markdown, ingestar y aprobar el documento.
2. Buscar evidencia y verificar su cita con el backend.
3. Crear agente, configurar herramientas/modelo/referencias exactas y congelar.
4. Evaluar **9/9**, solicitar como creator y aprobar/publicar como otro principal.
5. Ejecutar por canal published en Playground y abrir Trace Viewer.

- Agente: `final-audit-1792141809869`, v1, published.
- Run: `run-09d0d33e71ba40ec8b2ab735e8b155a9`, completed.
- Evaluación: `eval-c12c9cb6dcd34afc8d009883e38b476d`, 9/9.
- Aprobación: `apr-20599f7467964f09af0d726a367cab23`.
- Solicitante `demo-creator`; aprobador `demo-approver`.
- SQL confirmó hash idéntico en snapshot, evaluación, aprobación y run:
  `63add8c8c6db6699079117698fc2362b3b101dcc8c009444f6f85ad79f030dcb`.
- Nueve nodos, tres herramientas y un retrieval, con citas existentes.

Este run usa **modo determinista etiquetado** y resultados reales de herramientas
+ retrieval. No fue generado por un proveedor. Los embeddings sí son reales:
Model2Vec 0.7.0, minishlab/potion-multilingual-128M, revisión fija
73908c3438cf03b6a01bcb9611d62b23d0726f08, 256 dimensiones.

La auditoría RAG creó `s5-audit-e4c612b95ab1`: PDF/TXT/Markdown, dos chunks por
formato. Vectores, texto, offsets y SHA-256 coinciden con PostgreSQL. Fechas:
2026-07-31 → 0 fragmentos, 08-01 → 6, 09-30 → 6, 10-01 → 0. Reingesta sin
versiones/chunks activos duplicados. Run: `run-fe4aed2ccf4e4e59bbe4f81d1c171b4a`.
Facturas INV-1001/1002 provienen de herramientas transaccionales; RAG aporta FAQ y tarifas, nunca las facturas ni los cálculos.

La conciliación de métricas midió 352 runs no-evaluation, 766 tool calls y 151
errores de tools, incluidos escenarios deliberados; SQL y API coinciden. P50
47.654 ms y P95 238.05575 ms en ese instante. No son métricas de producción ni
benchmarks de calidad; cambiarán con nuevas pruebas.

## Comandos ejecutados y resultados

Desde la raíz del repositorio, con Docker Desktop y el `.env` existente:

| Comando | Resultado real |
| --- | --- |
| `make verify` inicial | Exit 0, 252 pruebas; todavía no detectaba AUD-FINAL-01. No se utiliza para afirmar arranque desde cero. |
| `RUN_DB_TESTS=1 .venv/bin/python -m pytest apps/api/tests/test_database.py::test_alembic_cli_commits_migrations_on_its_own_connection -q` antes del fix | Exit 1; confirmó que upgrade no conservaba tablas. |
| `RUN_DB_TESTS=1 .venv/bin/python -m pytest apps/api/tests/test_database.py -q` después del fix | Exit 0; 2 passed en 2.68 s. |
| `make verify` después del fix | Un intento exit 2 por timeout al obtener token de ghcr.io durante build de lint; sus 253 Pytest sí pasaron. `make lint` reintentado pasó. |
| **`make verify` final** | **Exit 0; 253 passed en 57.09 s**, lint/formato, checks frontend y smokes completos. |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` final | Exit 0; 7 passed en 13.8 s. |
| `node scripts/final_ui_audit.mjs` final | Exit 0; flujo publicado completo con RAG y traza. |
| `docker compose exec -T api python - < scripts/knowledge_audit.py` | Exit 0; formatos, vectores reales, fechas, permisos, reingesta y runtime. |
| `docker compose exec -T api python - < scripts/governance_audit.py` | Exit 0; SQL/API y hashes coinciden, findings vacío. |
| `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` | Sin errores; 15 pruebas frontend, compilación Next.js production correcta. |
| `.venv/bin/ruff check apps/api scripts`, `.venv/bin/ruff format --check apps/api scripts` | Sin errores; 88 archivos. También comprobado en Docker. |
| `docker compose exec -T api alembic -c apps/api/alembic.ini current` | `0005_knowledge_rag (head)`. |
| `docker compose exec -T api alembic -c apps/api/alembic.ini check` | No new upgrade operations detected. |
| `docker compose config --quiet`, `docker compose ps -a` | Configuración válida; API/web/PG healthy y migrate Exited (0). |
| `curl -fsS http://127.0.0.1:8001/health/ready` | API/database/migrations ok. |
| `curl -fsS http://127.0.0.1:3000/api/health` | Health backend ok, error null. |
| `.venv/bin/uv tool run --cache-dir /tmp/bia-final-uv-cache pip-audit --path .venv/lib/python3.14/site-packages --format json --output /tmp/bia-delivery-python.json` | Exit 0; 107 paquetes, cero avisos. |
| `npm audit --json` | Exit 1; cinco avisos high de desarrollo. |
| `npm audit --omit=dev --json` | Exit 0; cero avisos runtime. |
| `make provider-smoke` | **Exit 2**; run failed/MODEL_UNAVAILABLE, sin fallback. |
| Diagnóstico transparente del mismo gateway mediante `docker compose exec -T api python -` | Procedimiento exit 0; **generación fallida**, RateLimitError 429/credit_balance_exhausted/insufficient_quota, uso/costo null. No se imprimieron claves ni excepciones completas. |
| `git diff --check`, validación JSON de evidencia | Sin errores. |

Comprobación de persistencia ejecutada y aprobada:

```sh
rag_proof=$(docker compose exec -T api python - < scripts/knowledge_smoke.py)
docker compose restart api
docker compose up -d --wait api
docker compose exec -T -e KNOWLEDGE_TRACE_PROOF="$rag_proof" api python - < scripts/knowledge_smoke.py
```

Auxiliares de esta auditoría ejecutados en el Mac:
`python3 /tmp/bia-delivery-clean-db.py`, `node /tmp/bia-delivery-ux.mjs` y
`python3 /tmp/bia-final-secret-scan.py`. La prueba de base vacía ejecuta Docker
run de PG16 sin puertos, una imagen API con entorno aleatorio propio, upgrades,
downgrade, check, seeds y TestClient/runtime; elimina solo su contenedor temporal.
Su primera espera por socket detectó prematuramente el servidor de inicialización;
se corrigió a TCP antes del resultado final. El error transaccional posterior sí
fue un fallo de producto y quedó cubierto por la regresión permanente indicada.
Los auxiliares y logs `/tmp` no se consideran archivos del producto ni se necesitan
para ejecutar el README; las pruebas permanentes y la evidencia JSON se entregan.

## Seguridad, riesgos y estado de producción

- Los endpoints administrativos existen para roles autorizados; no son APIs
  anónimas. El backend no confía en X-Role, X-User-Id, identidad del prompt ni
  permisos declarados en una configuración. Las credenciales de proveedor solo
  llegan al backend; la imagen web no recibe esas variables.
- `.env.example` contiene **tokens sintéticos conocidos** para una demo local.
  Quien conozca esos tokens puede actuar con su rol en ese entorno. Son identidad
  de prueba explícita, sin expiración/SSO productivos; no se certifica seguridad
  fuera de la demo aislada. Production rechaza demo auth/runtime local. No existe
  una identidad productiva alternativa operativa.
- `.env` tiene 0600. Está fuera de Git/contexto Docker/imágenes. El escaneo revisa
  patrones y coincidencias exactas con la clave configurada, sin imprimir valores.
  Una clave compartida fuera del repositorio requiere rotación verificable; esta
  auditoría no puede certificarla.
- API/web corren con UID 1000; puertos host solo en loopback. La cuenta PG de
  demo también ejecuta migraciones; faltan credenciales separadas y privilegios
  mínimos productivos. Las bases de imágenes no están fijadas por digest.
- Los cinco avisos npm proceden de ESLint → fast-glob/micromatch → braces. En la
  consulta de corrección previa no se identificó un parche compatible publicado;
  la auditoría actual sigue detectándolos. No se aplicó el downgrade automático
  sugerido por npm ni se debilitó lint para ocultarlos.
- El proveedor real rechazó dos intentos; el segundo registró únicamente clase
  /status/códigos sanitizados del SDK y confirmó falta de saldo. Run diagnóstico:
  `run-1b79561ec864467f84df670eedd90f51`. Una nueva prueba requiere saldo disponible;
  no se afirma que la generación real haya pasado ni que la cuota esté resuelta.
- El árbol probado contiene código S4–6 no incluido en HEAD. Antes de entregar
  por Git hay que revisar/versionar los archivos sin secretos/caches/trazas y
  verificar checkout limpio y CI. No se hizo commit ni push por esta auditoría.

Límites funcionales conocidos: datos exclusivamente sintéticos, un workflow de
billing fijo/versionado, adaptadores explícitos (registrar un contrato no añade
código ejecutable), generación restringida a afirmaciones verificadas, chunking
por caracteres, embeddings estáticos locales, retrieval tarifario con consulta
fija, sin OCR/S3/conectores, cuotas globales, workers, recuperación de checkpoints
o protección universal contra inyección. La API es síncrona y una caída puede
requerir intervención sobre operaciones running; no se certificó recuperación.

**Estado de producción: no operativo/no aprobado.** El build de Next.js es
production, pero el backend de demo usa development. No se verificaron hosting
externo, TLS, identidad corporativa, backups, carga o respuesta a incidentes.
Un health verde y una publicación de agente no constituyen un despliegue seguro.

## Archivos modificados por esta auditoría

1. `apps/api/migrations/env.py`: transacción propia confirmada por CLI.
2. `apps/api/tests/test_database.py`: regresión de CLI con conexiones/procesos reales.
3. `README.md`: resultado actual de 253 pruebas, alcance local S1–6 y explicación
   de la corrección de migraciones desde cero.
4. `docs/final-demo-guide.md`: enlace al dictamen actual.
5. `docs/final-audit.md`: este reporte.
6. `docs/final-audit-evidence.json`: evidencia actual sanitizada.

Los otros cambios locales preexistían; no se atribuye todo `git diff` a esta
revisión. No se cambiaron secretos, permisos, catálogos aprobados, revisiones SQL,
workflows, modelos, herramientas o frontend funcional durante esta auditoría.
Los registros sintéticos creados en la demo conservan su historial.

## Preparar y verificar la demo

Requisitos: Docker Desktop y make; para E2E, Node 24 y Chrome. Primer build con
Internet para registros/paquetes y pesos Model2Vec. Desde este Mac:

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
open -a Docker
docker info
make env
make demo-env
make verify
npm ci
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
node scripts/final_ui_audit.mjs
open http://localhost:3000/dashboard
```

Entra con un token de Studio, no con la API key del proveedor. El script imprime
un agente publicado y run reales; ábrelo en Evaluaciones y Playground, canal
Published, modo deterministic, Compare e INV-1002. Debe mostrar 64400.00 COP,
23.00 %, citas y enlace a Trace Viewer. INV-2002 debe ser denegada para creator.
API local: http://localhost:8001/docs; `.env.example` usa 8000 si no se cambia.
Mantén el volumen existente; no usar down -v para preparar la presentación.

Para una demo con LLM real, primero resolver saldo y rotación de clave y repetir
`make provider-smoke`; su resultado actual es FAIL. No presentar texto determinista
como generación del proveedor. No declarar entrega completa/producción lista
mientras sus FAIL o comprobaciones críticas exigidas sigan pendientes.

Logs actuales bajo `/tmp`: `bia-delivery-verify-complete.log`,
`bia-delivery-e2e-final.log`, `bia-delivery-ui-final.log`, `bia-delivery-clean-db.json`,
`bia-delivery-migration-red.log`, `bia-delivery-migration-green.log`,
`bia-delivery-rag.json`, `bia-delivery-security.json`, `bia-delivery-web-image.json`,
`bia-delivery-ui-sql.json`, `bia-delivery-metrics.json`, `bia-delivery-ux.json`,
`bia-delivery-persistence.log`, `bia-delivery-provider.log`,
`bia-delivery-provider-diagnostic.json`, `bia-delivery-python.json` y
`bia-delivery-npm*.json`. Captura de UI `/tmp/bia-final-ui.png`; móvil
`/tmp/bia-delivery-dashboard.png`. No distribuir trace.zip: puede contener bearer
tokens demo en las peticiones. La evidencia portable está en el JSON del reporte.
