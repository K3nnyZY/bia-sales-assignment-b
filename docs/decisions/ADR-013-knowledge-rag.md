# ADR-013 — Knowledge Registry y retrieval autorizado

Estado: implementado para Sprint 5. Fecha: 2026-10-16.

Se conserva el monolito FastAPI, PostgreSQL 16, LangGraph y el cliente Next.js.
La imagen PostgreSQL pasa a `pgvector/pgvector:0.8.7-pg16-bookworm`, conservando
el volumen existente. La migración 0005 crea `vector` en `public`; no elimina
la extensión al hacer downgrade porque puede estar compartida entre esquemas.
Alembic fija explícitamente el esquema de su tabla de revisión para evitar que
los tests aislados descubran por accidente la revisión de `public`.

## Contratos, identidad y aprobación

Cada colección tiene propietario, clasificación `internal|restricted` y estado
habilitado. Los creators crean colecciones internas propias y administran sus
documentos; solamente un administrador asigna otro propietario, crea colecciones
restringidas y concede/revoca grants. El grant tiene clearance explícito. Ser
administrador permite gestionar metadatos pero **no concede retrieval**. Reviewers
necesitan acceso a la colección para revisar. Solo reviewer/administrator aprueba
o revoca versiones documentales. La revocación es terminal; requiere una nueva
versión para volver a aprobar contenido. La separación de funciones de aprobación
de **agentes** del Sprint 4 se conserva sin excepciones.

El documento conserva ID, título y propietario. Cada versión conserva archivo,
fuente declarada, hash SHA-256, vigencia inclusiva, pipeline/embedding versionado,
creador, aprobador y estado de ingesta. Los chunks conservan texto exacto, offsets,
hash y ordinal. Triggers protegen documentos completados, chunks, originales y
logs contra actualización/eliminación; checks/FKs evitan aprobación sin ingesta
completa y asociaciones entre colecciones distintas. No existe borrado de historial.

## Pipeline pequeño y reproducible

Upload e ingesta son operaciones separadas. Se aceptan PDF con texto, TXT UTF-8 y
Markdown, hasta 2 MiB por archivo, 20 páginas y 100 000 caracteres. El cuerpo
multipart se limita también durante su lectura, antes del spooling. PDF se procesa
con pypdf en un subprocess con timeout de 10 s, CPU de 5 s y memoria acotada en
Linux. No hay OCR, renderizado, ejecución de scripts, descarga de URLs ni lectura
de rutas de usuario. Las fuentes son referencias, no destinos de red.

Los chunks tienen hasta 900 caracteres y 120 de solapamiento. Se usa **Model2Vec
0.7.0**, modelo multilingüe `minishlab/potion-multilingual-128M`, revisión
`73908c3438cf03b6a01bcb9611d62b23d0726f08`, normalizado y de 256 dimensiones.
Se descargan únicamente tokenizer/config/safetensors durante el build, sin código
remoto ni pickle; el runtime carga datos locales y no necesita red. No es hashing
ni una simulación semántica. El modelo añade aproximadamente 507 MiB al build.

La frontera `DatabaseObjectStore` guarda originales inmutables y deduplicados por
hash en PostgreSQL, con límite de 2 MiB. Es una elección deliberada para este MVP:
compartir transacción/backup evita otro servicio. **No hay S3/MinIO implementado**;
un backend externo queda detrás de la misma frontera cuando el volumen lo exija.
El límite por objeto no constituye una política global de cuotas o retención.

Mismo contenido y vigencia en el mismo documento devuelve la versión existente;
en otro documento de la misma colección produce 409. Un archivo diferente crea
otra versión. Reintentar ingesta fallida reutiliza su versión; reingestar una
versión ready es idempotente y no reemplaza sus embeddings. El cambio de modelo
está sujeto a una futura revisión explícita del pipeline y reindexación; no se
mezclan vectores de modelos distintos.

## Retrieval y evidencia

La relación SQL base filtra identidad activa, grants, colección habilitada,
clasificación, aprobación, ingesta completa y vigencia **antes del ranking**.
La fecha es el período comercial explícito, no necesariamente la fecha actual:
es válido consultar la tarifa histórica de una factura autorizada. No concede
acceso a otra clasificación ni a otra colección. Las búsquedas directas escogen
la última versión aprobada válida de cada documento; el runtime usa exclusivamente
las versiones fijadas en su snapshot, aunque se apruebe una más reciente.

Se combinan distancia coseno de pgvector y `tsvector`/`plainto_tsquery` en español
mediante Reciprocal Rank Fusion (k=60). Hay índice GIN léxico. Se hace búsqueda
vectorial exacta sobre el subconjunto autorizado; no se añade ANN/HNSW a un corpus
pequeño. Esto evita resultados incompletos por filtrar después de un índice ANN.
Los scores son relevancia de búsqueda, no confianza en la veracidad. No existe un
benchmark de calidad general ni garantía de cobertura para cualquier consulta.

Cada evidencia incluye colección, documento, versión, chunk, fuente, offsets,
contenido y hash. El campo Pydantic de contenido preserva todos los espacios
del fragmento extraído: no aplica el recorte de strings de los metadatos, porque
invalidaría sus offsets y su SHA-256 (corrección KW-01 de la auditoría S5). Las citas usan `documento@versión#chunk-N` y se verifican contra
un endpoint que vuelve a autorizar el acceso. Una consulta sin evidencia devuelve
lista vacía; el agente escala cuando no obtiene ninguna evidencia autorizada.

## Seguridad e integración con Sprints 3–4

Las instrucciones hostiles conocidas se rechazan en el texto completo, metadatos
y consulta; se normalizan Unicode y caracteres invisibles. Los rechazos quedan
persistidos. Se vuelve a inspeccionar el contenido recuperado. Este filtro es
**defensa adicional**, no una promesa de detectar toda inyección. La frontera
principal sigue siendo permisos en SQL/backend, rutas explícitas de LangGraph,
herramientas allowlist y validación cerrada de la salida del modelo. Los documentos
no pueden cambiar identidad, permisos, herramientas ni instrucciones del sistema.

La configuración añade opcionalmente `knowledge.documents: [{document_id,version}]`.
Se verifican grants del propietario y aprobación antes de congelar. El snapshot
incluye hashes, colecciones, fechas y versiones exactas de embedding/pipeline.
La evaluación y Publication Gate incluyen esas dependencias y sus grants efectivos.
Una revocación bloquea runtime/gate sin reescribir snapshots o resultados históricos.
Publicar contenido diferente del evaluado sigue requiriendo otra versión y evaluación.

Se añade el adaptador registrado `billing-knowledge-v2` / `search_billing_knowledge`
2.0.0. Conserva la entrada período pero devuelve evidencia tipada del servicio
compartido. El StateGraph v1 mantiene sus nueve nodos; el nodo knowledge elige el
adaptador fijado según la configuración. Sus herramientas de factura y cálculos
Decimal permanecen intactos. El adaptador anterior v1 y las configuraciones sin
knowledge conservan su ejecución y sus hashes. No se cambian definiciones inmutables.

La generación continúa usando el gateway existente: modo determinista claramente
etiquetado, o LiteLLM con modelo aprobado y credenciales del servidor. El proveedor
puede ordenar afirmaciones verificadas y citas; no introducir cálculos o citas
inventadas. **Embeddings locales reales no equivalen a generación LLM real**.
No se reportan tokens/costos de proveedor para embeddings locales, ni se estima
costo de CPU sin medición. Esta verificación no necesita llamadas LLM pagadas.

Cada búsqueda registra duración real, errores, caller, run opcional, fecha,
embedding versionado y documentos/versiones/chunks recuperados. Se guarda hash de
consulta, no su texto ni el archivo. El Trace Viewer muestra esos registros del
backend. Runs y tool calls conservan sus controles de visibilidad anteriores.

## Límites explícitos

Ingesta síncrona pequeña, sin workers/recuperación, OCR, antivirus, clasificación
automática, conectores externos, streaming ni cuotas globales. Un crash puede dejar
una operación pendiente. El modelo estático tiene menor capacidad contextual que
un transformer y requiere evaluar calidad por corpus. La autenticación local de
demostración sigue bloqueada en producción. No se implementa Sprint 6.

Referencias primarias: [modelo y dimensiones](https://huggingface.co/minishlab/potion-multilingual-128M),
[Model2Vec](https://minish.ai/packages/model2vec/inference/),
[pgvector](https://github.com/pgvector/pgvector),
[integración SQLAlchemy](https://github.com/pgvector/pgvector-python),
[extracción PDF](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
