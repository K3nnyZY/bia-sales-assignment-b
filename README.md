# BIA Agent Studio — Integración local

Para desplegarlo manualmente con Railway CLI, sigue la
[guía de Railway](docs/railway-deployment.md). Incluye tres servicios, pgvector,
migraciones y credenciales privadas con vencimiento. El despliegue y las URLs
remotas todavía no están verificados; no actives identidad demo en producción.

Si ya desplegaste API y PostgreSQL con `APP_ENV=production`, usa la
[guía de bootstrap sintético](docs/production-demo-bootstrap.md): provisión
explícita de identidades, carga atómica sin grants automáticos, verificación y
revocación del acceso. No ejecutes los seeds locales cambiando flags de producción.

**Verificación local (2026-10-16): comprobaciones funcionales aprobadas.**
Dashboard con datos reales, 280 pruebas backend, 15 frontend y siete E2E aprobados.
Se corrigieron el aislamiento de Knowledge y las dependencias Python vulnerables.
La entrega pública sigue pendiente: validación de hosting y del flujo remoto;
se preparó acceso privado con vencimiento, sin SSO/MFA. Quedan cinco avisos de tooling npm sin parche
publicado compatible. Consulta las [correcciones y resultados](docs/sprint-6-fixes.md),
la [auditoría final](docs/final-audit.md) y la [guía de demo](docs/final-demo-guide.md).

Monorepo con Next.js 16 (TypeScript, App Router), FastAPI, PostgreSQL 16,
SQLAlchemy 2, Alembic, Pytest y Ruff. Implementa Foundation, Agent Management
y Agent Runtime de [la arquitectura](docs/architecture.md). LangGraph ejecuta
un billing-assistant con facturas sintéticas, autorización por cliente,
cálculos Decimal, tarifas/FAQ aprobadas y trazas persistidas. Incluye Playground
y gateway LiteLLM opcional. Sprint 4 añade evaluaciones versionadas, aprobación
independiente, publicación con gate de hash exacto, rollback y observabilidad.
Sprint 5 integra colecciones/documentos versionados, ingesta PDF/TXT/Markdown,
embeddings semánticos locales, pgvector y búsqueda híbrida con filtros de permisos
y vigencia, citas verificables y trazas. Consulta la [guía del Sprint 5](docs/sprint-5-guide.md),
[ADR-013](docs/decisions/ADR-013-knowledge-rag.md), el
[reporte del Sprint 5](docs/sprint-5-report.md) y la [guía del Sprint 4](docs/sprint-4-guide.md),
[ADR-012](docs/decisions/ADR-012-quality-governance.md) y el
[reporte de verificación](docs/sprint-4-report.md).
La [auditoría del Sprint 5](docs/sprint-5-audit.md) verifica ingesta nueva,
vectores y referencias contra PostgreSQL; documenta y corrige KW-01
(preservación de espacios en evidencia).
La [auditoría del Sprint 4](docs/sprint-4-audit.md) del 16 de octubre documenta
la verificación inicial. El hallazgo de visibilidad por agente quedó
[corregido y verificado](docs/sprint-4-aud01-fix.md).
Las decisiones están en [ADR-010](docs/decisions/ADR-010-agent-management.md) y
[ADR-011](docs/decisions/ADR-011-agent-runtime.md); los resultados históricos del runtime
están en el [reporte del Sprint 3](docs/sprint-3-report.md) y su
[verificación de cierre con evidencia](docs/sprint-3-verification.md).

## Arranque y verificación en macOS

Requisitos: Docker Desktop con Docker Compose v2 o posterior y `make`
(incluido en las herramientas de línea de comandos de Xcode). La primera
ejecución necesita acceso a los registros de imágenes y paquetes. Si `make`
no está disponible, instala las herramientas con `xcode-select --install`.
No necesitas instalar Python, Node ni PostgreSQL en el Mac para este flujo.

Desde Terminal:

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
open -a Docker
# Espera a que Docker Desktop indique que el motor está listo.
docker info
make env
make demo-env
make verify
```

`make env` crea `.env` desde `.env.example` únicamente si no existe.
`make demo-env` añade únicamente las variables de demostración que falten en
un `.env` del Sprint 1, conservando valores existentes. Si has deshabilitado
`ENABLE_DEMO_AUTH`, debes activarlo explícitamente en desarrollo para usar
los registros de este sprint. Activa también `ENABLE_LOCAL_RUNTIME=true`
para el Playground; ambos flags se rechazan en producción. `make verify` valida Compose, construye y arranca
los servicios, aplica migraciones, carga seeds idempotentes, espera los health
checks y ejecuta:

1. Pytest, incluidas las pruebas reales contra PostgreSQL 16.
2. Ruff (lint y formato).
3. ESLint, TypeScript y pruebas de clientes HTTP y rutas permitidas del frontend.
4. Un smoke test HTTP de frontend → FastAPI → PostgreSQL y Alembic.
5. Un smoke test del runtime: comparación, traza y rechazo entre clientes.
6. Un smoke de gobernanza: configurar, evaluar, aprobar, publicar, ejecutar,
   auditar, rollback y bloqueo de una candidata con fallos críticos.
7. Un smoke RAG: embeddings reales, retrieval autorizado, citas, comparación y trazas.

Los smokes crean historial sintético real; no llaman a proveedores LLM.
El primer build descarga aproximadamente 507 MiB de pesos de embeddings locales
con revisión fija. Los archivos originales (máximo 2 MiB), vectores y trazas se
persisten en PostgreSQL. La imagen pgvector conserva el volumen PostgreSQL 16.

Los ejemplos HTTP directos de esta guía usan el puerto predeterminado 8000.
En el Mac verificado se cambió `.env` a `API_PORT=8001` por un conflicto de
puerto; usa `http://localhost:8001/docs` y sustituye 8000 por 8001 en los
comandos HTTP directos. Playground sigue en 3000 y los targets Make usan
la configuración de Compose.

El build de producción de Next.js se ejecuta al construir su imagen.
Los servicios quedan disponibles al terminar. Para comprobarlos desde el Mac:

```sh
docker compose ps -a
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/health/ready
curl -fsS http://localhost:3000/health
curl -fsS http://localhost:3000/api/health
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
docker compose exec -T postgres psql -U bia -d bia_studio -c 'SELECT version_num FROM alembic_version;'
open http://localhost:3000
open http://localhost:3000/dashboard
open http://localhost:3000/agents
open http://localhost:3000/knowledge
open http://localhost:3000/playground
open http://localhost:3000/evaluations
open http://localhost:3000/traces
```

La API de readiness debe devolver:

```json
{"status":"ok","service":"bia-api","database":"ok","migrations":"ok"}
```

La ruta del frontend `/api/health` debe envolver esa respuesta en
`{"health":{...},"error":null}`. La pantalla consulta esa ruta al abrirse y al
pulsar **Actualizar estado**. Los indicadores proceden de la API; no hay
métricas simuladas. La documentación OpenAPI está en `http://localhost:8000/docs`.
El servicio `migrate` debe aparecer como `Exited (0)`; es un trabajo de una sola ejecución.

## Dashboard

Abre `http://localhost:3000/dashboard` y entra con un token de Studio. El panel
consulta el inventario visible, `/metrics` y las últimas cinco ejecuciones;
respeta el scope que aplica el backend. Permite actualizar datos y abrir una
traza real. Un viewer sin ejecuciones ve estados vacíos, sin costos ni latencias
inventadas. El panel de métricas se comparte con Trazas. La portada `/` conserva
la comprobación pública de infraestructura.

## Usar Agent Management

Abre `http://localhost:3000/agents` y entra con el valor de
`DEMO_CREATOR_TOKEN` de tu `.env`. El token es local y sintético; permanece solo
en memoria y se pierde al recargar. La identidad se verifica contra hashes en
PostgreSQL; enviar `X-Role` o `X-User-Id` no concede acceso.

1. Crea un agente con ID, nombre, departamento y descripción.
2. Configura objetivo e instrucciones, modelo aprobado, herramientas y límites.
3. Guarda la primera versión; puedes editarla con **Guardar borrador**.
4. Con los cambios guardados, usa **Crear snapshot**. El formulario pasa a solo
   lectura y muestra el hash y el contenido efectivo conservado.
5. Usa **Nueva versión desde esta** para derivar otro borrador. Selecciona las
   versiones en el historial y comprueba que la anterior permanece intacta.
6. Recarga, identifícate de nuevo y comprueba la persistencia.

Las páginas `/models` y `/tools` muestran catálogos reales. El administrador
(`DEMO_ADMIN_TOKEN`) puede registrar definiciones JSON, aprobar, revocar y
eliminar registros sin referencias. Los contratos publicados en el catálogo
son inmutables; para cambiar su definición hay que registrar otra versión.
El visor (`DEMO_VIEWER_TOKEN`) solo puede leer.

Los modelos `synthetic-*` son contratos ficticios; no conectan con proveedores.
Los contratos anteriores `invoice-read-v1` e `invoice-read-v2` se conservan
inmutables y no tienen adaptador ejecutable. El seed del runtime añade contratos
con salida completa y adaptadores controlados; consulta la siguiente sección.
`invoice-read-v1` requiere `invoices:read`, concedido a
los propietarios sintéticos creator/administrator. Exportación y escritura
permiten comprobar rechazos de permisos; las herramientas de escritura no
pueden asignarse en este sprint. No hay métricas operativas simuladas.

## Ejecutar billing-assistant en Playground

`make verify` ejecuta primero `make seed` y después `make runtime-seed`.
El segundo crea cuatro facturas de dos clientes, documentos aprobados, tres
contratos ejecutables y un snapshot de `billing-assistant`. Un grant explícito
por cliente y versión autoriza su invocación local. Un snapshot sigue sin ser
una publicación; no se pueden ejecutar borradores editables ni concederse
invocaciones desde una configuración. Solo está habilitado en development/test.

1. Abre `http://localhost:3000/playground` e introduce `DEMO_CREATOR_TOKEN` de `.env`.
2. Selecciona `billing-assistant`, su versión sintética y **deterministic**.
3. Para una consulta simple, elige **Consultar factura**, `INV-1002` y ejecuta:
   debe mostrar 344.400 COP, sin consultar el período previo. Luego cambia a
   **Comparar con el mes anterior**, mantén `INV-1002` y el mensaje
   `Compara mi factura con el mes anterior y explica la diferencia`.
4. La factura de septiembre de 2026 tiene 420 kWh × 820 = **344.400 COP**;
   agosto, 350 × 800 = **280.000 COP**. Diferencia: **64.400 COP**, descompuesta
   en consumo **56.000 COP** y tarifa **8.400 COP**. Solo hay cargos por consumo.
5. Consulta las referencias, los nueve nodos y las tres llamadas a herramientas.
   La respuesta identifica explícitamente el modo determinista. Tokens y coste
   permanecen `null`, mostrados como no reportados/no disponible.
6. Intenta `INV-2002`: termina `denied / INVOICE_NOT_ACCESSIBLE`, sin evidencia.
   Cierra sesión y entra con `DEMO_CUSTOMER_B_TOKEN`: esa factura sí está
   autorizada para B; `INV-1002` queda denegada. B no puede consultar las trazas
   del creator. El administrador tampoco puede consultar ejecuciones preview/published ajenas.
   El rol auditor sí puede inspeccionarlas de forma explícita.
7. Con el token creator, compara `INV-1001`: falta la factura de julio y la
   herramienta de período anterior falla con `PREVIOUS_INVOICE_UNAVAILABLE`.
   El run termina `escalated`; la traza muestra el intento fallido y `failure`,
   sin devolver una comparación inventada. No modifica los datos de demo.
8. Recarga e identifícate de nuevo: el historial y sus trazas están persistidos.

Las tareas `invoice`, `compare` y `knowledge` tienen rutas explícitas. `auto`
resuelve una intención básica mediante reglas, sin un clasificador LLM. En una
consulta de tarifas/FAQ sin factura se usa el período indicado (por defecto
septiembre de 2026). Para facturas se usa su período real. El mes anterior es
el mes calendario inmediatamente anterior, no cualquier factura histórica.
La falta de factura previa o tarifa vigente produce `escalated` sin inventar datos.

Los documentos son datos sintéticos aprobados con versión y vigencia. Se
consultan mediante SQL controlado en snapshots legacy del Sprint 3. Los snapshots
con `knowledge.documents` y `billing-knowledge-v2` utilizan el pipeline RAG del
Sprint 5; consulta [su guía](docs/sprint-5-guide.md).
La identidad viene exclusivamente del token autenticado. Cada acceso vuelve a
validar permisos del caller, permisos congelados del agente, grant, aprobación
y definición exacta de modelo/herramienta. Al liberar la respuesta se revalida
la evidencia, incluidas las revocaciones durante la generación.

### Runtime API

| Operación | Endpoint | Acceso |
| --- | --- | --- |
| Versiones disponibles y modos | `GET /api/v1/runtime/agents` | Solo grants explícitos del caller |
| Ejecutar snapshot local | `POST /api/v1/runs` | Grant + políticas + propiedad de cada factura |
| Historial | `GET /api/v1/runs` | Caller; auditor global; evaluaciones según rol/propietario |
| Resultado persistido | `GET /api/v1/runs/{id}` | Caller, auditor o evaluación autorizada; resto 404 |
| Traza persistida | `GET /api/v1/runs/{id}/trace` | Caller, auditor o evaluación autorizada; resto 404 |

Ejemplo después de cargar los seeds; en una base nueva la versión es 1. Usa
`GET /api/v1/runtime/agents` para elegir el número exacto si ya hay historial:

```sh
read -r -s BIA_TOKEN
curl -fsS http://localhost:8000/api/v1/runs \
  -H "Authorization: Bearer $BIA_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"billing-assistant","version":1,"mode":"deterministic","task":"compare","invoice_id":"INV-1002","message":"Explica la diferencia con agosto"}'
# Sustituye el ID por el devuelto en la respuesta:
curl -fsS 'http://localhost:8000/api/v1/runs/<run-id>/trace' \
  -H "Authorization: Bearer $BIA_TOKEN"
unset BIA_TOKEN
# Prueba automática sin copiar tokens ni IDs:
make runtime-smoke
```

`POST /runs` es síncrono y devuelve 201 cuando crea una ejecución durable,
incluso si su resultado es `denied`, `failed` o `escalated`: comprueba `status`
y `error_code`. Los rechazos de admisión usan 401/403/404/409/503 antes de crear
una ejecución; una petición inválida devuelve 422. El cuerpo no admite
`customer_id`, `caller_id`, permisos ni estado de LangGraph. La traza conserva
nodos, tiempos medidos, intentos, argumentos tipados mínimos y referencias;
no almacena el prompt, secretos ni respuestas completas de las herramientas.

### Model Gateway con proveedor opcional

El modo predeterminado es determinista y usa el modelo registrado
`synthetic-balanced-v1`; nunca llama a LiteLLM. El modo `provider` exige:

1. Un administrador registra y aprueba en `/models` un modelo real con proveedor
   `openai` o `anthropic`, identificador exacto compatible con ese proveedor,
   precios explícitos y capacidades `chat`, `tool_calling`, `structured_output`.
   Usa un perfil libre (por ejemplo `advanced`) si `balanced` ya está aprobado.
2. Configura `ENABLE_PROVIDER_RUNTIME=true` y `OPENAI_API_KEY` o
   `ANTHROPIC_API_KEY` únicamente en `.env` del servidor. Ejecuta `make up`
   para recrear la API con ese entorno. No añadas un prefijo de proveedor al
   `model_identifier`: el gateway lo fija desde el catálogo aprobado.
3. Provisiona una nueva versión congelada con el ID exacto del catálogo:

   ```sh
   docker compose run --rm migrate python -m app.runtime.seed --model-id ID_DEL_MODELO_APROBADO
   ```

4. Selecciona esa versión y `provider` en el Playground. El gateway utiliza
   LiteLLM con credencial del servidor, modelo fijado, timeout y cero reintentos.
   No admite una URL de proveedor enviada por el cliente ni fallback silencioso.

El LLM ordena las afirmaciones y citas previamente calculadas por Python;
debe copiarlas completas, sin añadir hechos. La salida JSON se valida y se
rechaza si modifica números, referencias o intenta invocar herramientas. Esta
primera integración prioriza evidencia verificable y tiene redacción limitada.
Las herramientas se seleccionan mediante el workflow, nunca por instrucciones
recibidas del modelo o de documentos. Solo se registran tokens reportados por
el SDK; el coste es una estimación con los precios del snapshot cuando existen
ambos conteos. La ausencia de uso reportado permanece `null`. Un fallo del
proveedor termina en error controlado, sin convertirlo en respuesta determinista.

La suite automatizada usa dobles en el límite del SDK y no consume saldo.
En la [prueba real posterior](docs/sprint-3-provider-check.md), OpenAI aceptó
la credencial para consultar el modelo, pero rechazó la generación con
`429 / credit_balance_exhausted / insufficient_quota`. La ejecución quedó
persistida como failed, sin fallback ni métricas inventadas. La generación
exitosa sigue pendiente de agregar créditos a la organización API.

En este Mac ya está aprobado `openai-gpt54-mini-20260317` y provisionado
billing-assistant v2 con ese modelo. Después de habilitar saldo:

```sh
make up
make provider-smoke
open http://localhost:3000/playground
```

Selecciona **v2**, modo **Proveedor · LiteLLM**, comparación e `INV-1002`.
`make provider-smoke` realiza una ejecución de proveedor y puede consumir saldo;
no forma parte de `make verify` ni CI. v1 sigue disponible en modo determinista.
La [definición JSON del modelo](docs/examples/openai-gpt54-mini.json) usa el
snapshot y los precios de la [ficha oficial](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
No se registran ni aprueban modelos automáticamente al ejecutar el smoke.

## Quality & Governance

La [guía paso a paso](docs/sprint-4-guide.md) documenta roles, endpoints,
contratos, pruebas de seguridad, publicación, rollback y uso del Trace Viewer.

```sh
make demo-env
make governance-seed
make governance-smoke
open http://localhost:3000/evaluations
open http://localhost:3000/traces
```

`make verify` incluye estos seeds y el smoke. El escenario crea un agente
`quality-smoke-*`; no publica ni modifica billing-assistant automáticamente.
La selección **Published** del Playground exige una publicación aprobada
vigente; **Preview** conserva el flujo de pruebas local del Sprint 3.

## API y autorización

Todos los endpoints `/api/v1` requieren `Authorization: Bearer <token>`.
Los health checks permanecen públicos. Los tokens se obtienen del entorno de
demostración, nunca del manifiesto del agente. `/docs` documenta los contratos.

| Operación | Endpoint | Autorización |
| --- | --- | --- |
| Identidad actual | `GET /api/v1/me` | Identidad activa |
| Propietarios disponibles | `GET /api/v1/users` | Administrator |
| Inventario, búsqueda y filtros | `GET /api/v1/agents?q=&status=&owner_id=&limit=100&offset=0` | Identidad activa |
| Crear agente | `POST /api/v1/agents` | Creator/administrator; owner actual salvo admin |
| Ver agente | `GET /api/v1/agents/{id}` | Identidad activa |
| Editar metadatos/estado | `PATCH /api/v1/agents/{id}` | Propietario creator o administrator |
| Eliminar sin historial | `DELETE /api/v1/agents/{id}?expected_revision=1` | Propietario creator o administrator |
| Listar/consultar versiones | `GET /api/v1/agents/{id}/versions[/{number}]` | Identidad activa |
| Crear o clonar versión | `POST /api/v1/agents/{id}/versions` | Propietario creator o administrator |
| Editar borrador | `PUT /api/v1/agents/{id}/versions/{number}` | Propietario creator o administrator |
| Congelar configuración | `POST /api/v1/agents/{id}/versions/{number}/snapshot` | Propietario creator o administrator |
| Catálogos aprobados | `GET /api/v1/models`, `GET /api/v1/tools` y detalle por ID | Identidad activa |
| Catálogo completo | `GET /api/v1/models?approved_only=false`, equivalente tools | Administrator |
| Crear definición | `POST /api/v1/models`, `POST /api/v1/tools` | Administrator |
| Cambiar aprobación | `PATCH /api/v1/models/{id}`, equivalente tools | Administrator |
| Eliminar sin referencias | `DELETE /api/v1/models/{id}`, equivalente tools | Administrator |

Los permisos se controlan en backend. Ser administrator no concede al propietario
permisos de herramientas que no tenga asignados. Todos los usuarios activos
pueden consultar el inventario interno y las configuraciones; editar un agente
ajeno requiere administrator. No existe API para editar roles o concederse permisos.

### Crear agente y configuración inicial en una petición

`POST /api/v1/agents` admite un ID opcional: si se omite, genera uno único.
Al enviar `model_profile`, crea también la versión 1 editable y sus relaciones
en la misma transacción. `owner` es un alias de `owner_id` y debe ser un
principal existente y autorizado; no crea un equipo ni concede permisos.

Ejemplo compatible con los datos sintéticos incluidos:

```sh
# Introduce el valor de DEMO_CREATOR_TOKEN de .env, sin mostrarlo:
read -r -s BIA_TOKEN
curl -fsS http://localhost:8000/api/v1/agents \
  -H "Authorization: Bearer $BIA_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Billing Assistant",
    "description": "Explica facturas a clientes",
    "department": "customer_service",
    "owner": "demo-creator",
    "model_profile": "balanced",
    "tools": ["invoice-lookup-v3"]
  }'
unset BIA_TOKEN
```

La respuesta 201 incluye `id`, `state: "DRAFT"` y `initial_configuration`, que
apunta a `/api/v1/agents/<id-generado>/versions/1`. La cabecera `Location`
apunta al agente. `status: "draft"` conserva el formato de los clientes
existentes; `state` se calcula a partir del mismo estado, sin almacenarlo dos veces.

Los nombres de herramientas se resuelven a IDs y versiones aprobadas. Si hay
varias versiones aprobadas del mismo nombre, devuelve 409 y exige usar el ID
exacto del catálogo. Si una selección no está aprobada o faltan permisos,
revierte toda la creación. `search_billing_knowledge` se registra al ejecutar
`make runtime-seed`; `billing-team` no es un propietario del seed.

La configuración inicial usa la descripción (o el nombre) como objetivo e
instrucciones de plantilla explícitas, sin generar contenido mediante un LLM.
Sus límites se validan contra el modelo elegido y pueden editarse después.
Enviar `tools` exige `model_profile`. Se mantiene el alta de solo metadatos
usada por la interfaz: sin perfil, no crea una versión y devuelve
`initial_configuration: null` hasta guardar la primera configuración.

`PATCH /api/v1/agents/{id}` admite metadatos parciales y conserva los campos
omitidos, por ejemplo `{"expected_revision":1,"description":"Nueva descripción"}`.
Sigue exigiendo revisión actual y autorización; rechaza cambios vacíos, valores
nulos y campos que intenten modificar configuración o privilegios.

Ejemplo de creación de una versión con perfil resuelto por el servidor:

```json
{
  "configuration": {
    "api_version": "bia.ai/v1",
    "kind": "AgentConfiguration",
    "objective": "Explain synthetic authorized invoices",
    "instructions": "Use only approved evidence.",
    "model": {"profile": "balanced", "max_output_tokens": 1000},
    "tool_ids": ["invoice-read-v1"],
    "required_capabilities": ["chat"],
    "limits": {"max_steps": 6, "max_tool_calls": 5, "timeout_seconds": 30},
    "security": {
      "require_authentication": true,
      "resource_scope": "caller_owned",
      "allow_financial_writes": false
    }
  }
}
```

Puede elegirse `model_id` o `profile`, de forma exclusiva. El servidor fija el
modelo exacto al guardar. Campos desconocidos —incluido `permissions`— se
rechazan. Se verifican capacidades, límites, aprobación y permisos del
propietario en cada guardado, clonación y snapshot. Los esquemas de herramientas
se validan como JSON Schema 2020-12 y no pueden referenciar recursos externos.

Editar un borrador requiere `{"expected_revision":1,"configuration":{...}}`;
crear un snapshot requiere `{"expected_revision":1}`; clonar usa
`{"source_version":1,"expected_source_revision":2}`. Un conflicto de revisión
devuelve 409 y exige recargar; no sobrescribe silenciosamente cambios ajenos.

El agente admite `draft`, `disabled` y `deprecated`. Solo `draft` permite cambios
de configuración; `deprecated` es terminal. Las versiones admiten `draft` y
`snapshot`. Un snapshot **no equivale a publicar**. Un agente con versiones no
se elimina: se deshabilita para conservar el historial. La transferencia de
propiedad es administrativa, revalida los borradores y se bloquea si hay snapshots.

### Ayuda, evaluaciones y eliminación segura

La ayuda contextual se abre con ratón, teclado o toque; el glosario explica los
conceptos de configuración, evaluación, aprobación y ejecución. Los errores
conocidos añaden un siguiente paso sin sustituir el código ni mensaje de la API.

Evaluation Center muestra nombres comprensibles para las nueve pruebas de billing.
Expande una prueba para consultar propósito, contrato esperado, detalles realmente
persistidos, error y enlace a la traza disponible. El contrato esperado es ayuda
del evaluador, no un resultado obtenido. `PASS` indica comprobación superada;
`FAIL`, una aserción no satisfecha; `ERROR`, `CHECK_ERROR`, `EVALUATION_TIMEOUT`
o una ejecución marcada como `failed`. Los datos ausentes se indican como no
disponibles y las pruebas desconocidas conservan su identificador sin inventar
su propósito ni diagnóstico.

En **Herramientas → Añadir herramienta**, un administrador puede registrar las
cuatro versiones implementadas de Billing, con contratos exactos obtenidos del
backend, o introducir un contrato manual. Las plantillas se crean pendientes de
aprobación. Un registro existente, incluso revocado, no se sobrescribe ni reactiva.
Registrar herramientas no carga facturas, documentos ni concede permisos.

El botón **Eliminar agente** aparece arriba en el detalle para el propietario
creator o administrador. Solo se habilita cuando el registro está en `draft` y
no tiene versiones; en otros casos explica por qué está bloqueado. DRAFT en el
registro no es el estado de publicación de sus versiones. Exige confirmación con
el nombre del agente. `DELETE /api/v1/agents/{id}?expected_revision=N` revalida
autorización, revisión, estado e historial bajo bloqueo en el servidor. Se conserva
la política existente: **también las versiones editables impiden borrar el agente**,
pues tienen historial de auditoría que debe preservarse. Los agentes con historial
pueden deshabilitarse desde Identidad y estado. La eliminación conserva los eventos
de metadatos y registra `agent.deleted`. No requiere una migración nueva.

Ver [detalles y verificación de UX](docs/ux-context-evaluations-deletion.md).
La mejora posterior de acciones está documentada en
[herramientas y eliminación visible](docs/catalog-and-agent-actions.md).

## Estructura

```text
apps/
  api/
    app/
      api/health.py       # Rutas y contratos de salud
      identity/          # Identidades y autorización local explícita
      catalogs/          # Modelos y herramientas: modelos, schemas y rutas
      agents/            # Registry, configuraciones y versionamiento
      billing/           # Facturas, contratos, adaptadores y cálculos Decimal
      runtime/           # LangGraph, política, gateway, runs, trazas y seed
      governance/        # Suites, evaluación, gate, aprobación, publicación y métricas
      knowledge/         # Ingesta, embeddings, retrieval autorizado y referencias
      core/config.py      # Variables de entorno validadas con Pydantic
      db/base.py          # Base declarativa y nombres de constraints
      db/session.py       # Engine y sesiones por petición
      main.py             # Factory y ciclo de vida de FastAPI
    migrations/           # Revisiones Alembic versionadas
    tests/                # Pruebas unitarias y de integración
    alembic.ini
    Dockerfile
  web/
    src/app/              # App Router, interfaz y rutas HTTP
    src/lib/health.ts     # Cliente tipado con timeout y validación
    tests/                # Pruebas con node:test
    Dockerfile
scripts/smoke.py           # Verificación HTTP entre servicios
scripts/runtime_smoke.py   # Ejecución real, evidencia y aislamiento por cliente
tests/e2e/                # Flujos reales con Playwright
.github/workflows/ci.yml   # Mismos checks con Docker en CI
compose.yaml
Makefile
pyproject.toml / uv.lock
package.json / package-lock.json
```

El backend es un monolito modular. Las futuras funcionalidades se añadirán
por dominio, sin crear un servicio por agente. No se crean tablas de negocio
por adelantado ni se ejecuta `create_all()` al arrancar.

## Configuración

`.env.example` documenta todos los valores de desarrollo. `.env` se ignora
en Git y en el contexto de Docker. Python carga el `.env` raíz y permite que
las variables del proceso lo sobrescriban. El frontend recibe sus variables
mediante Compose o `make dev-web`.

| Variable | Uso / valor predeterminado |
| --- | --- |
| `APP_ENV` | `development`, `test` o `production` |
| `ENABLE_DEMO_AUTH` | `false` por defecto en código; `.env.example` la activa solo para demo local |
| `DEMO_ADMIN_TOKEN`, `DEMO_CREATOR_TOKEN`, `DEMO_VIEWER_TOKEN` | Credenciales sintéticas para el seed explícito |
| `DEMO_CUSTOMER_B_TOKEN` | Segundo cliente de facturación, mínimo 24 caracteres |
| `DEMO_REVIEWER_TOKEN`, `DEMO_APPROVER_TOKEN`, `DEMO_AUDITOR_TOKEN` | Roles de calidad separados, seed explícito |
| `EVALUATION_TIMEOUT_SECONDS` | 60 s; timeout global del evaluador, máximo 90 s |
| `ENABLE_LOCAL_RUNTIME` | `false` en código; habilita preview local explícito, bloqueado en producción |
| `ENABLE_PROVIDER_RUNTIME` | `false`; requiere también modelo aprobado y credencial del servidor |
| `RUNTIME_TIMEOUT_SECONDS` | 30 s; límite del servidor (máximo configurable 120 s) |
| `MODEL_TIMEOUT_SECONDS` | 15 s; timeout del proveedor (máximo 60 s) |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | Secretos opcionales solo del backend |
| `LANGSMITH_TRACING`, `LANGCHAIN_TRACING_V2` | `false` en demo; sin exportación de trazas |
| `LITELLM_LOCAL_MODEL_COST_MAP` | `True`; evita descargar precios remotos al importar el SDK |
| `POSTGRES_DB` | `bia_studio` |
| `POSTGRES_USER` | `bia` |
| `POSTGRES_PASSWORD` | Credencial de desarrollo local |
| `POSTGRES_HOST` | `127.0.0.1` en desarrollo nativo; `postgres` en Compose |
| `POSTGRES_PORT` | `55432` en el Mac; `5432` entre contenedores |
| `API_PORT` | Puerto publicado de FastAPI: `8000` |
| `WEB_PORT` | Puerto publicado de Next.js: `3000` |
| `BACKEND_URL` | URL usada por el servidor Next.js; Compose fija `http://api:8000` |
| `CORS_ORIGINS` | Array JSON, por ejemplo `["http://localhost:3000"]` |
| `DATABASE_URL` | Override opcional para API/Alembic nativos, con `postgresql+psycopg://` |

Compose usa siempre `POSTGRES_*` y sobrescribe los hosts y puertos internos;
ignora `DATABASE_URL` para evitar que una URL del Mac rompa la red de contenedores.
Las contraseñas de `POSTGRES_PASSWORD` se manejan con `URL.create` en Python;
si escribes una `DATABASE_URL`, codifica los caracteres reservados de la contraseña.
No se envían credenciales ni `BACKEND_URL` al navegador y las peticiones de
estado tienen `Cache-Control: no-store`.

Los puertos publicados se limitan a `127.0.0.1`. Si un puerto está ocupado,
cambia su valor en `.env` y ejecuta `make up`. Para ejecución nativa, ajusta
también `BACKEND_URL` si cambia `API_PORT`, y `CORS_ORIGINS` si cambia `WEB_PORT`.

## Migraciones

La auditoría final corrigió la transacción de la CLI de Alembic: una conexión
propia confirma el upgrade al salir. La regresión ejecuta la CLI en procesos
separados y verifica tablas persistidas, replay y downgrade/upgrade. También se
probó en un PostgreSQL temporal sin tablas ni extensión vector preexistentes.

`migrate` espera a PostgreSQL y ejecuta `alembic upgrade head`. La API espera
a que ese proceso termine correctamente; el frontend espera a la API.
Una migración fallida impide completar el arranque.

La revisión `0001_foundation` es una línea base sin tablas de negocio.
Alembic crea `alembic_version` y guarda la revisión de forma transaccional.
`0002_agent_management` añade `users`, `agents`, `agent_versions`, `models`,
`tools` y `agent_tools`, junto con claves foráneas, checks, índices y triggers.
Estos impiden modificar/borrar snapshots y sus enlaces, cambiar definiciones de
catálogo o introducir enlaces no aprobados/inconsistentes. La coherencia entre
JSON y relaciones de herramientas se verifica al confirmar la transacción.
`0003_agent_runtime` añade `invoices`, `billing_knowledge`, `agent_invocations`,
`agent_runs`, `tool_calls` y `run_events`. Incluye restricciones monetarias,
FKs de versión y triggers para grants a snapshots, identidad de ejecución
inmutable, finalización consistente, runs finalizados inmutables y logs append-only.
`0004_quality_governance` añade siete tablas de gobernanza, canal/FK de
evaluación en runs, gates y triggers de historial inmutable/publicación atómica.
`0005_knowledge_rag` añade colecciones, grants, originales, documentos/versiones,
chunks vectoriales, búsquedas y restricciones de inmutabilidad.
La prueba de integración usa un esquema temporal único y verifica:
estado sin migrar → upgrade → repetición idempotente → ausencia de drift →
downgrade a base → nuevo upgrade. El esquema temporal se elimina al terminar;
las tablas de la aplicación permanecen intactas.

```sh
make migrate
make seed
make runtime-seed
make governance-seed
make knowledge-seed
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
docker compose exec -T api alembic -c apps/api/alembic.ini upgrade head --sql
```

Para crear una migración futura, importa los modelos nuevos en el entorno
de Alembic, genera la revisión en el checkout y revisa el SQL antes de aplicarlo:

```sh
uv run --frozen alembic -c apps/api/alembic.ini revision --autogenerate -m "describe change"
uv run --frozen alembic -c apps/api/alembic.ini upgrade head
```

Actualiza `SCHEMA_REVISION` en `apps/api/app/api/health.py` junto con cada
nueva revisión. `/health` solo indica que el proceso está vivo;
`/health/ready` exige conexión SQL y la revisión esperada. Devuelve HTTP 503
cuando la base de datos no está disponible o faltan migraciones, sin exponer
detalles de conexión. `/health` del frontend comprueba su propio proceso;
`/api/health` comprueba la cadena completa y propaga HTTP 503 si falla.

## Desarrollo nativo opcional

Requiere Python 3.14, uv y Node.js 24. `.python-version` y `.nvmrc` indican
las versiones. Las instalaciones usan `uv.lock` y `package-lock.json`;
no regeneres los archivos de bloqueo durante un arranque normal.

Primero detén el stack completo si está activo, instala dependencias y
arranca únicamente PostgreSQL:

```sh
make down
make demo-env
make install
make knowledge-model
docker compose up -d --wait postgres
uv run --frozen alembic -c apps/api/alembic.ini upgrade head
PYTHONPATH=apps/api uv run --frozen python -m app.seed
PYTHONPATH=apps/api uv run --frozen python -m app.runtime.seed
PYTHONPATH=apps/api uv run --frozen python -m app.governance.seed
PYTHONPATH=apps/api uv run --frozen python -m app.knowledge.seed
```

En dos terminales, desde la raíz:

```sh
# Terminal 1
make dev-api
```

```sh
# Terminal 2
make dev-web
```

Pruebas y checks nativos:

```sh
make test-unit
RUN_DB_TESTS=1 uv run --frozen pytest
uv run --frozen ruff check apps/api scripts
uv run --frozen ruff format --check apps/api scripts
npm run lint
npm run typecheck
npm test
npm run build
python3 scripts/smoke.py
# Con Google Chrome instalado, y el stack Docker activo:
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
# Alternativa con Chromium descargado por Playwright:
npx playwright install chromium
npm run test:e2e
```

Sin `RUN_DB_TESTS=1`, Pytest omite explícitamente la prueba de PostgreSQL;
las pruebas unitarias no necesitan una base de datos. `make test` sí ejecuta
la suite completa contra PostgreSQL con Docker.

Las pruebas de integración crean y eliminan esquemas temporales únicos; no
modifican los registros del entorno de demostración. Verifican persistencia,
restricciones de base de datos, rollback, versionamiento, concurrencia,
aprobaciones/revocaciones, acceso entre propietarios y SQL directo sobre snapshots.
También ejecutan el StateGraph real, cálculos, timeouts de SQL y
proveedor, fallos de herramientas, presupuestos, revocaciones y ataques de
prompt injection sin sustituir la autorización.
Playwright usa el stack real, sin mocks de API o autorización; deja agentes
sintéticos `e2e-*` con historial para comprobar persistencia y elimina su modelo
temporal, además de ejecuciones sintéticas de facturación. CI está configurado
para `make verify` y siete flujos de navegador con Chromium; no se ha ejecutado
CI remoto durante esta entrega.

## Operación y diagnóstico

```sh
make up           # Construir y arrancar; no ejecuta la suite
make seed         # Cargar identidades y catálogos sintéticos explícitamente
make runtime-seed # Provisionar facturas, adapters, snapshot y grants locales
make governance-seed # Roles de calidad, suite y fixtures aislados
make governance-smoke # Ciclo completo y gate; sin consumo LLM
make runtime-smoke # Flujo determinista y rechazo de acceso entre clientes
make provider-smoke # Prueba optativa contra proveedor; puede consumir saldo
make test         # Pytest con PostgreSQL real
make lint         # Ruff
make web-check    # Build, ESLint, TypeScript y pruebas web en Docker
make smoke        # Comprobar la cadena HTTP con el stack activo
make logs         # Logs; Ctrl+C para salir
make down         # Detener sin eliminar datos
```

El seed solo inserta registros que falten: no restaura aprobaciones revocadas,
no modifica permisos y no rota tokens ya guardados. Si cambias un token del
entorno después del seed, debes rotar su hash mediante un procedimiento
administrativo de desarrollo o usar una base de demostración nueva. Repetir el
seed no cambia credenciales existentes. Los tokens deben ser distintos y tener
al menos 24 caracteres; no sirven como autenticación de producción.

`make down` conserva el volumen `postgres_data`. Las credenciales de
PostgreSQL se inicializan solo al crear el volumen: cambiar `.env` no cambia
las credenciales de una base ya existente. Para reinicializar datos locales
de forma deliberada, `docker compose --profile test down --volumes` elimina
el volumen y todos sus datos; después ejecuta `make verify`.

Si el arranque falla, revisa `docker compose ps -a` y
`docker compose logs --tail=100 postgres migrate api web`. Un fallo de conexión
se distingue de una migración pendiente mediante `/health/ready`. El frontend
muestra la indisponibilidad y permite reintentar con **Actualizar estado**.

## Límites y dependencias

Esta entrega cubre los Sprints 1–6 y preparación para una demo protegida en Railway.
El modo local conserva sus identidades demo; el modo desplegado requiere
credenciales privadas con vencimiento y revocación. No hay SSO/MFA: el proceso
sigue rechazando autenticación demo o runtime local con `APP_ENV=production`.
El runtime desplegado admite únicamente publicaciones aprobadas, y las
evaluaciones usan fixtures sintéticos aislados; no hay grader LLM.
El despliegue y su flujo remoto todavía no se han verificado. Los snapshots legacy
conservan SQL documental y los snapshots con referencias Knowledge utilizan RAG.
El flujo determinista no requiere claves de proveedores.
La ejecución síncrona está acotada, sin workers, colas ni recuperación de
checkpoints. Una interrupción abrupta del proceso puede dejar un run o evaluación `running`;
no se implementa reconciliación automática. Las facturas son hipotéticas y
solo modelan cargos por consumo, sin impuestos ni cargos fijos.

La base del Sprint 1 emplea CSS propio y un cliente ligero; se conserva para
evitar una migración visual no necesaria a Tailwind/shadcn. La configuración
incorpora un workflow tipado y versionado
(`billing_workflow_v1:1.0.0`); no hay un catálogo administrable de workflows
y el Knowledge Registry se limita al pipeline documentado en
[ADR-013](docs/decisions/ADR-013-knowledge-rag.md). Las referencias documentales
se fijan en el snapshot y se comprueban antes de responder. No hay OCR, S3,
conectores externos, workers de ingesta ni cuotas globales.

La auditoría de npm durante la validación del 15 de octubre de 2026 mostró
cero vulnerabilidades en dependencias de ejecución (`npm audit --omit=dev`)
y cinco avisos altos derivados de `braces`, transitiva del tooling de ESLint
de Next.js ([aviso del proyecto](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)).
La ruta de corrección propuesta por `npm audit` requiere cambiar a
`eslint-config-next@14.2.35`, una versión mayor anterior a la del proyecto.
Se conserva la configuración actual y el pendiente queda documentado.
No ejecutes `npm audit fix --force`: propone degradar Next.js ESLint a una
versión mayor anterior. Revisa `npm audit` al actualizar dependencias.
