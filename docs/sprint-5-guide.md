# Sprint 5 — Verificación local en Mac

Desde el directorio del repositorio, con Docker Desktop en marcha:

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
open -a Docker
docker info
make env
make demo-env
make verify
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

El último comando requiere Node 24, `npm ci` y Google Chrome instalado. Alternativa
reproducible con el navegador de Playwright:

```sh
npm ci
npx playwright install chromium
npm run test:e2e
```

`make verify` construye API/web, descarga en el build el modelo público de embeddings
con revisión fija, conserva el volumen PostgreSQL 16, instala pgvector y aplica
migraciones. Ejecuta seeds idempotentes y todas las pruebas/checks/smokes S1–5.
No borres el volumen con `down -v`: no es necesario para instalar pgvector.
La descarga inicial del modelo ocupa aproximadamente 507 MiB y necesita red;
las consultas posteriores se ejecutan localmente. No requiere API key de OpenAI.

Puertos del Mac actual: API **8001**, web **3000**, PostgreSQL **55432**. En una
instalación nueva `.env.example` usa 8000: configura `API_PORT=8001` si está ocupado.
Los comandos Make utilizan los puertos internos de Compose y no dependen de esto.

```sh
docker compose ps -a
curl -fsS http://localhost:8001/health/ready
curl -fsS http://localhost:3000/api/health
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
docker compose exec -T postgres psql -U bia -d bia_studio -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
make knowledge-smoke
open http://localhost:3000/knowledge
```

## Interfaz: documentos y retrieval

1. Entra con el **valor** de `DEMO_CREATOR_TOKEN` de tu `.env`, nunca con la API key
   del proveedor. El token de Studio permanece solo en memoria.
2. Abre **Conocimiento**. Selecciona `billing-reference`. Hay tarifas y FAQ sintéticas
   aprobadas. Sus fechas cubren agosto–diciembre de 2026.
3. **Crear documento**: usa un ID nuevo, por ejemplo `mi-faq-sintetica`, y un título.
4. **Cargar versión**: selecciona PDF con texto, `.txt` UTF-8 o `.md`, indica fuente
   `synthetic://local/faq`, vigencia `2026-08-01` a `2026-12-31`. Máximo 2 MiB.
5. Pulsa **Ejecutar ingesta v1**. Debe pasar de pending a ready, mostrar fragmentos,
   hash y modelo de embeddings. Un fallo muestra su código real y permite reintento.
6. Sal e ingresa con `DEMO_ADMIN_TOKEN`. Selecciona colección/documento y pulsa
   **Aprobar documento v1**. Creator no puede aprobar ni concederse grants.
   Reviewer puede aprobar si un administrador le concedió acceso a la colección.
7. Vuelve como creator. Busca en fecha `2026-09-01`, por ejemplo
   `¿Cuál es la tarifa y por qué cambia el cargo por consumo?`.
8. Comprueba texto, fuente, versión, fragmento y scores. **Verificar documento@1#chunk-0**
   vuelve a consultar el backend y muestra contenido/offsets/hash autorizados.
9. Una fecha fuera de vigencia devuelve sin evidencia. Un viewer sin grant obtiene
   rechazo seguro. Una colección restricted requiere clearance restricted explícito.
10. Para otro contenido carga un archivo modificado: se crea v2; v1 no cambia.
    Un upload idéntico con la misma vigencia devuelve la versión existente.

## Playground y configuración

1. Abre **Playground** como creator. Selecciona la versión de `billing-assistant`
   anunciada por `make knowledge-seed`: en el Mac existente es **v3**; en una base
   nueva suele ser v2. El seed imprime el número real. v1 conserva el adaptador
   anterior sin RAG; v2 de este Mac usa un proveedor y no es el demo RAG.
2. Canal preview, modo determinista, consulta compare, factura `INV-1002`.
3. Ejecuta. Debe mostrar **64.400 COP**, **23 %**, evidencia `billing-tariffs-rag@1#chunk-0`
   / `billing-faq-rag@1#chunk-0`, nueve nodos LangGraph y tres tool calls.
4. En **Retrieval documental**, revisa duración, embedding versionado y referencias
   procedentes del backend. La generación indica que es determinista; no simula LLM.
5. `INV-2002` como creator debe terminar denied sin sus datos. Como customer B con
   su grant de invocación permite su propia factura, no la de creator.
6. En **Trazas**, abre el run. Los registros siguen disponibles tras reiniciar API.

Para configurar otro agente, en el Builder selecciona `billing_workflow_v1`,
modelo sintético aprobado, `invoice-lookup-v3`, `invoice-previous-v1`,
`billing-knowledge-v2` (excluye v1), al menos 9 pasos/3 llamadas. En **Documentos de
conocimiento** introduce referencias exactas, sin permisos:

```json
{"documents":[{"document_id":"billing-tariffs-rag","version":1},{"document_id":"billing-faq-rag","version":1}]}
```

Guarda, congela, evalúa en Evaluation Center, solicita aprobación y entra como
approver independiente para aprobar/publicar. El Publication Gate conserva hash
exacto y dependencias. Publicar concede invocación al propietario, no acceso a nuevas
colecciones. En una colección nueva, el administrador debe otorgar acceso también
a `evaluation-customer-a`, `evaluation-customer-b` y `evaluation-no-permission`
para ejecutar la suite sintética existente; no alteres sus permisos de negocio.
Una revocación documental bloquea versiones que la fijan. No hay auto-publicación.

## Terminal y persistencia

Sin revelar tokens en el historial del shell, los smokes leen credenciales desde
el entorno **dentro del contenedor**:

```sh
make knowledge-seed
make knowledge-smoke
make runtime-smoke
make governance-smoke
docker compose exec -T api python - < scripts/governance_audit.py
make test
make lint
make web-check
```

Para verificar persistencia exacta tras reiniciar (ejecútalos en la misma terminal):

```sh
rag_proof=$(docker compose exec -T api python - < scripts/knowledge_smoke.py)
docker compose restart api
docker compose exec -T -e KNOWLEDGE_TRACE_PROOF="$rag_proof" api python - < scripts/knowledge_smoke.py
```

`rag_proof` contiene solo IDs/hashes sintéticos, ninguna credencial. API necesita
unos segundos para volver a estar healthy; si aún no responde, espera y repite el
último comando.

Endpoints principales bajo `/api/v1/knowledge`: `GET/POST /collections`,
`PUT /collections/{id}/grants`, `PATCH /collections/{id}/status`,
`GET/POST /collections/{id}/documents`, `GET/POST /documents/{id}/versions`,
`POST /documents/{id}/versions/{n}/ingest`, `PATCH /documents/{id}/versions/{n}`,
`POST /search`, `GET /searches`, `GET /documents/{id}/versions/{n}/chunks/{c}?as_of=2026-09-01`.
La documentación interactiva y contratos multipart están en `http://localhost:8001/docs`.
No envíes `caller_id`, roles ni grants en la configuración: la API los rechaza.

Para trabajar sin Docker: instala PostgreSQL 16 **con pgvector 0.8.7**, Node 24 y
uv/Python 3.14. Con PostgreSQL nativo configurado en `.env`:

```sh
make install
make knowledge-model
export PYTHONPATH=apps/api
uv run --frozen alembic -c apps/api/alembic.ini upgrade head
uv run --frozen python -m app.seed
uv run --frozen python -m app.runtime.seed
uv run --frozen python -m app.governance.seed
uv run --frozen python -m app.knowledge.seed
RUN_DB_TESTS=1 uv run --frozen pytest
make dev-api
# Otra terminal:
make dev-web
```

Ajusta `BACKEND_URL=http://127.0.0.1:8001` y `API_PORT=8001`. Los procesos nativos
permanecen vinculados a sus terminales; Compose los deja en segundo plano.


## Auditoría completa de ingesta y PostgreSQL

Después de `make verify`, ejecuta desde el Mac:

```sh
docker compose exec -T api python - < scripts/knowledge_audit.py
```

Crea una colección, documentos PDF/TXT/Markdown y un agente de auditoría con IDs
nuevos. No publica ni modifica el billing-assistant existente. Conserva el historial
sintético creado; repetir genera otro corpus independiente. La auditoría comprueba
extracción, varios chunks por documento, vectores reales de 256 dimensiones,
reingesta sin duplicados, límites inclusivos de vigencia, rechazo sin grants,
facturas en `invoices`, ejecución StateGraph y citas existentes en PostgreSQL.
No llama a un LLM externo; la generación es determinista y los embeddings son reales.
Resultados y límites en [la auditoría S5](sprint-5-audit.md).
