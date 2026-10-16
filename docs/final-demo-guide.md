# Preparar la demo local de entrega

Las comprobaciones funcionales locales pasan tras las
[correcciones verificadas](sprint-6-fixes.md). El despliegue público y la entrega
versionada siguen pendientes. No expongas el entorno con tokens demo.
La [auditoría final](final-audit.md) detalla los resultados actuales, la corrección
de migraciones desde cero y los riesgos pendientes de entrega y producción.

## 1. Preparación en el Mac

Requisitos: Docker Desktop, make; para Chrome automatizado, Node 24 y Google Chrome.
La primera construcción requiere Internet para imágenes, paquetes y pesos del
modelo de embeddings (aproximadamente 507 MiB). Mantener el volumen existente.

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
open -a Docker
docker info
make env
make demo-env
chmod 600 .env
make verify
```

El archivo local fue protegido con permisos 0600 durante la corrección. Mantén
esa protección, no sobreescribas `.env` ni publiques sus contenidos.
Para la demo, `APP_ENV=development`, `ENABLE_DEMO_AUTH=true` y
`ENABLE_LOCAL_RUNTIME=true` deben estar habilitados explícitamente. Nunca en
producción. No hace falta OPENAI_API_KEY para la demo determinista. Si una clave
se compartió fuera del repositorio y no fue rotada, revócala y reemplázala antes
de usar el gateway de proveedor. No introduzcas API keys del proveedor en Studio.

En este Mac `API_PORT=8001`, `WEB_PORT=3000`, `POSTGRES_PORT=55432`. En una máquina
nueva `.env.example` usa API 8000: cambia a 8001 si está ocupado y ajusta los curl.
No termines procesos ajenos ni borres la base para resolver un conflicto de puerto.

```sh
docker compose ps -a
curl -fsS http://localhost:8001/health/ready
curl -fsS http://localhost:3000/api/health
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
```

Esperado: API/web/PostgreSQL healthy, migrate Exited (0), revisión
`0005_knowledge_rag`, sin drift. `make verify` carga identidades, catálogo,
facturas, Knowledge y suites locales sin reemplazar registros revocados. Si el
seed falla por una revocación deliberada, inspecciónala; no reinicies permisos
ni borres historial a ciegas.

## 2. Preparación reproducible de un agente publicado desde la interfaz

```sh
npm ci
node scripts/final_ui_audit.mjs
```

El script usa Chrome real, lee tokens demo desde `.env`, no imprime sus valores
y realiza todo el recorrido con controles de la interfaz. No usa un proveedor
LLM ni sustituye respuestas de API. Crea documento nuevo, lo aprueba, crea agente
RAG, evalúa 9/9, solicita aprobación, entra con otra identidad, aprueba/publica,
ejecuta billing y abre Trace Viewer. Imprime `agent_id` y `run_id` reales.

Cada ejecución crea otros registros sintéticos y conserva su historial. No
modifica el billing-assistant original. La captura queda en `/tmp/bia-final-ui.png`
y el detalle en `/tmp/bia-final-audit-ui.json` (se reemplazan al repetir).
No uses un `trace.zip` como material público: puede contener bearer tokens demo.

El E2E estándar de Knowledge ahora crea una colección aislada por ejecución.
Conserva su consulta y sus comprobaciones de citas, sin borrar historial ni alterar
el ranking del producto. El recorrido adicional combina RAG con publicación.

```sh
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

Estado después de la corrección: **siete E2E aprobados**; Knowledge también pasó
dos repeticiones adicionales. Chromium puede
usarse para la suite estándar con `npx playwright install chromium` y
`npm run test:e2e`; el procedimiento adicional usa Google Chrome instalado.

## 3. Recorrido manual para presentar la demo

Abre `http://localhost:3000`. Los valores necesarios son los tokens **de Studio**
`DEMO_CREATOR_TOKEN`, `DEMO_ADMIN_TOKEN`, `DEMO_APPROVER_TOKEN` y
`DEMO_AUDITOR_TOKEN` de `.env`, no la clave de OpenAI. No los proyectes ni incluyas
en capturas. El login conserva el token solo en memoria; al recargar debes volver
a identificarte.

1. **Dashboard:** entra como creator y muestra inventario, métricas y últimas
   ejecuciones. Cambia a viewer para mostrar los estados vacíos de su scope.
   En **Infraestructura**, actualizar estado; mostrar la respuesta de API/DB/migración.
2. **Agentes:** entrar como creator; abrir el agente que creó el script. Mostrar
   versión, snapshot inmutable, herramientas aprobadas, referencias exactas y hash.
3. **Evaluaciones:** seleccionar ese agente/v1 y mostrar 9/9, decisión de otra
   identidad y estado published. Si ya está publicado, no reevaluarlo: clonar una
   nueva candidata para otra demo del proceso.
4. **Playground:** como creator, seleccionar `agent_id@1`, canal Published, modo
   determinista, Compare e `INV-1002`. Ejecutar: 64400.00 COP y 23.00 %, con citas.
   Explicar que la plantilla determinista usa resultados reales de tools y retrieval,
   y que no fue redactada por un proveedor.
5. **Seguridad de factura:** repetir con `INV-2002` como creator. Debe terminar
   denied y sin evidencia ajena; no cambiar la identidad desde el mensaje.
6. **Knowledge:** abrir `billing-reference`. Mostrar documentos aprobados, vigencia,
   fragmentos e identificador del modelo de embeddings. Buscar por el ID completo
   del documento nuevo o una frase específica de su texto. Con una consulta muy
   genérica pueden aparecer documentos anteriores relevantes entre los primeros
   cuatro; no prometer que el más nuevo será el primero.
7. **Citas:** pulsar Verificar documento@versión#chunk. Mostrar texto y hash que
   devuelve el backend, no una cita inventada en el prompt.
8. **Traces:** Abrir Trace Viewer desde el run; mostrar nueve nodos, tres tools,
   retrieval, errores/duración y referencias. Como auditor se ven todas las
   ejecuciones; otros roles mantienen su scope. Mostrar costos/tokens como
   no disponibles si no hubo proveedor, nunca como gasto cero facturado.

Para demostrar creación completa a mano, sigue las mismas acciones del script:

- En Knowledge, crear un documento con ID único y cargar Markdown sintético.
- Ingestar, entrar como administrator y aprobar la versión.
- Como creator, crear agente, elegir workflow billing y modelo synthetic-balanced-v1.
- Seleccionar get_customer_invoice v3, get_previous_invoice v1 y
  search_billing_knowledge v2; excluir Knowledge v1; fijar al menos 9 pasos/3 tools.
- En el JSON de referencias usar tarifas/FAQ aprobadas y la versión nueva:

```json
{"documents":[{"document_id":"billing-tariffs-rag","version":1},{"document_id":"billing-faq-rag","version":1},{"document_id":"ID-NUEVO","version":1}]}
```

Reemplaza ID-NUEVO por un ID válido real. Guardar, congelar, evaluar, solicitar
aprobación y cambiar a approver independiente para aprobar/publicar. La colección
`billing-reference` ya tiene grants para las identidades sintéticas de evaluación.
Una colección nueva necesita grants de lectura explícitos, no permisos en el JSON.
No aprobares agentes propios usando otra pestaña con el mismo principal.

## 4. Pruebas de soporte y persistencia

```sh
docker compose exec -T api python - < scripts/knowledge_audit.py
docker compose exec -T api python - < scripts/governance_audit.py
```

El README ya incluye preparación del modelo y seed RAG para desarrollo nativo.
La preparación Docker descrita aquí es la comprobada de extremo a extremo.

El primer script ingiere PDF/TXT/Markdown nuevos, verifica vectores contra el
modelo local y PostgreSQL, reingesta idempotente y límites de vigencia. El segundo
reconcilia métricas y hashes del último quality-smoke. Conservan datos sintéticos.

Para verificar que una traza sobrevive al reinicio, en la misma terminal:

```sh
rag_proof=$(docker compose exec -T api python - < scripts/knowledge_smoke.py)
docker compose restart api
docker compose up -d --wait api
docker compose exec -T -e KNOWLEDGE_TRACE_PROOF="$rag_proof" api python - < scripts/knowledge_smoke.py
```

Debe indicar PASS. Los contenedores continúan en segundo plano; cerrar Terminal
no los detiene. Docker Desktop debe permanecer activo. `make down` los detiene
sin borrar el volumen. No usar `down -v` para preparar esta demo.

## 5. Cierre obligatorio antes de entrega definitiva

- Vigilar el parche de `braces`/ESLint: cinco avisos npm de desarrollo siguen
  abiertos. La auditoría Python actual devuelve cero y npm runtime cero.
- Mantener verdes la suite completa y el E2E Knowledge aislado; repetir tras cambios.
- Revisar y versionar los cambios reales S4–5 (sin `.env`, caches, logs o traces
  privados); repetir desde checkout limpio. El HEAD auditado solo contenía Sprint 3.
- Acordar y declarar demo **local**, no despliegue público. Una demo remota necesita
  una frontera de acceso real que no exponga los tokens demo; no se implementó aquí.
- Una nueva llamada LLM real, si se quiere presentar, requiere modelo aprobado,
  credenciales rotadas, cuota disponible y una prueba explícita. No confundir los
  embeddings locales reales con generación del proveedor ni prometer costos medidos.

No se certificaron despliegue público, cargas de producción, backup/restore,
escalado o seguridad empresarial. Estos pendientes no se ocultan en la demo.
