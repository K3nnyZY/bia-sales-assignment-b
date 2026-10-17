# Inicialización explícita de una demo desplegada

Fecha: 2026-10-16. Se conserva `APP_ENV=production`. Esta guía utiliza únicamente
clientes, facturas, catálogos y documentos sintéticos. No habilita identidad demo
ni preview local y no cambia la contraseña de PostgreSQL.

## Separación de responsabilidades

| Operación | Qué hace | Qué preserva |
| --- | --- | --- |
| `provision-identities` | Crea identidades sintéticas nuevas con roles/permisos explícitos del manifiesto y tokens privados con vencimiento. | Rechaza colisiones; no eleva usuarios existentes, no reactiva, no rota ni extiende credenciales existentes. |
| `load` | Crea catálogos, un agente/snapshot candidato, ocho facturas ficticias, una suite y dos documentos con embeddings reales. | No crea usuarios, tokens, grants de invocación/retrieval, aprobaciones de agentes ni publicaciones. |
| `status` | Consulta IDs, conteos, estado documental y dimensiones de vectores. | No escribe datos ni imprime hashes/tokens. |
| `revoke-access` | Revoca todos los tokens de las identidades administradas de esta demo, incluidas rotaciones, y desactiva esas cuentas. | No toca usuarios ajenos ni elimina facturas, ejecuciones, documentos o auditoría. |

Los cuatro entrypoints antiguos (`app.seed`, `app.runtime.seed`,
`app.governance.seed`, `app.knowledge.seed`) siguen bloqueados en producción.
Sus funciones de datos se reutilizan separadas de los wrappers locales de
identidad y grants. El predeploy ahora ejecuta **solo migraciones**; inicializar
una demo nunca ocurre automáticamente por desplegar o reiniciar.

La carga usa una transacción exterior y savepoints para contener los commits de
la ingesta existente. Si falla un embedding o documento, se revierte todo el
conjunto de datos, sin revertir las identidades provisionadas previamente. Un
lock transaccional serializa cargas concurrentes. Un evento de auditoría
inmutable `deployment.synthetic_loaded` identifica `billing-demo-v1`: después
la operación es de solo lectura, incluso si un operador cambió o revocó datos.
No es un comando de reparación ni sincronización.

## 1. Publicar el código actualizado y seleccionar el servicio existente

Publica estos cambios con tu procedimiento habitual. Si usas Railway CLI desde
la raíz del repositorio, el comando es:

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
export PATH="$PWD/.tools/railway-cli/node_modules/.bin:$PATH"
railway whoami
railway link
railway service link api
railway status
railway up --service api --ci
```

Selecciona tu proyecto y entorno ya existentes. Sustituye `api` si el backend
tiene otro nombre. No ejecutes `railway init`, `config apply` ni crees una base o
volumen nuevos para resolver este problema. El despliegue del código sí modifica
el servicio existente; los comandos de esta guía los ejecuta el operador de la
cuenta. No he ejecutado cambios sobre tu Railway.

Mantén en el backend:

```dotenv
APP_ENV=production
ENABLE_DEMO_AUTH=false
ENABLE_LOCAL_RUNTIME=false
ENABLE_ACCESS_TOKEN_AUTH=true
ENABLE_PUBLISHED_RUNTIME=true
```

Las variables de PostgreSQL y CORS deben conservar tu configuración correcta.
No copies `.env.example` a Railway. No se necesita una clave LLM para cargar datos
ni para las evaluaciones deterministas. La imagen de backend debe contener el
modelo local fijado por `scripts/download_embeddings.py`; el Dockerfile existente
lo incluye. Usa migraciones hasta `0006_private_access_tokens`; este cambio no
requiere una migración nueva.

## 2. Generar acceso privado en tu Mac

Requiere Python 3.14, igual que el proyecto:

```sh
python3 scripts/railway_credentials.py \
  --access-only \
  --directory .tools/railway-demo-access
```

Crea exclusivamente dos archivos 0600, ignorados por Git/Docker/subidas de código:

- `railway-credentials.json`: tokens en texto plano para entrega privada al usuario.
- `railway-manifest.json`: IDs, roles, permisos explícitos, hashes SHA-256 y vencimientos.

`--access-only` **no genera ni cambia credenciales de PostgreSQL**. Los tokens
contienen 256 bits aleatorios y vencen como máximo en siete días. El generador
rechaza sobrescribir archivos. No lo repitas con otro manifiesto para intentar
reemplazar cuentas existentes: la provisión también rechazará esa colisión.
Usa el comando existente de rotación `app.identity.credentials issue` si una
cuenta administrada necesita otra credencial.

Revisa el manifiesto localmente antes de aplicarlo. Declara siete identidades:

| ID | Rol | Permiso de negocio explícito |
| --- | --- | --- |
| `demo-administrator` | administrator | Ninguno; administra catálogos y acceso. |
| `demo-creator` | creator | `invoices:read`, limitado por propiedad/entitlement. |
| `demo-customer-b` | viewer | `invoices:read`, limitado a sus propias facturas. |
| `demo-viewer` | viewer | Ninguno. |
| `demo-reviewer` | reviewer | Ninguno. |
| `demo-approver` | approver | Ninguno; aprobación independiente. |
| `demo-auditor` | auditor | Ninguno; acceso a trazas según política existente. |

Los nombres `demo-*` son IDs sintéticos, no tokens ni autenticación de desarrollo.
También se provisionan tres principales internos de evaluación, con scopes
sintéticos y **sin tokens de acceso**. La operación no permite permisos de
escritura, roles arbitrarios ni aprobaciones automáticas. Solo un operador con acceso al
contenedor/base puede ejecutarla; no hay endpoint público para bootstrap.

## 3. Provisionar identidades explícitamente

Sube **solo el manifiesto de hashes**, nunca `railway-credentials.json`:

```sh
railway service link api
railway service files upload \
  .tools/railway-demo-access/railway-manifest.json \
  /tmp/bia-bootstrap-manifest.json

railway ssh --service api -- python -m app.deployment.bootstrap \
  provision-identities \
  --manifest /tmp/bia-bootstrap-manifest.json \
  --confirm-synthetic-demo
```

Una respuesta satisfactoria indica `identities_provisioned: true` y
`tokens_logged: false`. Repetir el mismo manifiesto preserva los usuarios,
permisos, actividad, vencimientos y revocaciones existentes.
Un manifiesto con formato anterior sin `role`/`permissions` se rechaza: no se
infieren privilegios. No cambies las flags de producción para evitar ese error.

## 4. Ejecutar la carga de datos una sola vez

```sh
railway ssh --service api -- python -m app.deployment.bootstrap \
  load --confirm-synthetic-demo

railway ssh --service api -- python -m app.deployment.bootstrap status
```

Primera carga: `already_initialized: false`. Una repetición devuelve
`already_initialized: true` sin modificar datos. Si hay un fallo, la transacción
revierte la carga y no guarda el recibo de finalización; corrige la causa y
repite el mismo comando. No borres datos ni revocaciones para forzar una carga.

En una base inicialmente vacía, `status` debe informar:

- `initialized: true`, `principals_provisioned: true`.
- `catalog_models: 4`, `catalog_tools: 9`.
- `billing_versions: 1`, `synthetic_invoices: 8`, `evaluation_suites: 1`.
- Dos documentos `ready`/`approved`, dos vectores de 256 dimensiones y versión
  identificada del modelo de embeddings.
- `evaluation_runs: 0`: no se inventan evaluaciones ni pases.
- `valid_demo_tokens: 7` mientras las siete credenciales sigan activas y vigentes.

Los conteos de catálogos pueden ser mayores si ya había otras definiciones.
Las facturas de usuario son `INV-1001/1002` para el creador y `INV-2001/2002` para
el cliente B. Las otras cuatro pertenecen a principales aislados de evaluación.
El agente inicial tiene snapshot v1 sin publicar y herramientas transaccionales;
los documentos RAG están ingeridos, pero **nadie obtiene acceso documental por
el hecho de ejecutar `load`**. La suite es `billing-runtime` v1. Los documentos
son `billing-tariffs-rag@1` y `billing-faq-rag@1`, vigentes de agosto a diciembre
2026. Para estas facturas consulta septiembre de 2026.

Después de provisionar, elimina el archivo temporal de hashes:

```sh
railway ssh --service api -- rm /tmp/bia-bootstrap-manifest.json
```

Si mantienes una variable antigua `BIA_BOOTSTRAP_MANIFEST`, retírala de la
configuración de Railway después de esta operación; el nuevo predeploy no la
consume. El archivo local de tokens es privado: no lo subas ni lo adjuntes a logs.

## 5. Habilitar RAG y publicar mediante las autorizaciones existentes

Para entrar, copia una credencial al portapapeles sin imprimirla:

```sh
python3 -c 'import json; print(json.load(open(".tools/railway-demo-access/railway-credentials.json"))["administrator"]["token"], end="")' | pbcopy
```

1. Entra al frontend por HTTPS con **Token de acceso**.
2. Como administrador, ve a **Conocimiento → billing-reference → Administrar
   acceso**. Concede clasificación **Interna**, con **Guardar acceso**, solo a
   los participantes que hayas autorizado. Para la demo RAG mínima: `demo-creator`,
   `evaluation-customer-a`, `evaluation-customer-b` y `evaluation-no-permission`.
   Para el flujo de cliente B con conocimiento, concede explícitamente también
   `demo-customer-b`. Estos grants son decisiones administrativas auditadas, no
   efectos del bootstrap. `evaluation-no-permission` sigue sin `invoices:read`;
   ese caso debe fallar antes de ejecutar herramientas.
3. Cierra sesión y entra como `creator` copiando su token con el mismo comando.
   En **Agentes → billing-assistant**, selecciona v1 y **Nueva versión desde esta**.
4. En el borrador nuevo conserva `invoice-lookup-v3` y `invoice-previous-v1`;
   selecciona `billing-knowledge-v2` y elimina `billing-knowledge-v1`.
   En **Referencias de conocimiento** usa:

```json
{"documents":[{"document_id":"billing-tariffs-rag","version":1},{"document_id":"billing-faq-rag","version":1}]}
```

5. Guarda el borrador y crea el snapshot. En **Evaluaciones**, ejecuta
   `billing-runtime` v1, modo **Determinista**. Revisa los nueve resultados reales
   y solicita aprobación únicamente cuando pasen.
6. Entra como `approver`, revisa, registra el motivo, aprueba y publica. El creador
   con rol creator no puede autoaprobarse. Con `0008_admin_approval`, Admin puede
   aprobar cualquier candidata válida, incluida una propia, con motivo y auditoría.
   Ningún paso anterior publica automáticamente.
7. Entra como creador. En **Playground**, selecciona **Published**, factura
   `INV-1002`, tarea comparar, período `2026-09`. Debe mostrar diferencia de
   **64.400 COP**, **23 %**, citas documentales y traza LangGraph con herramientas
   de facturas y retrieval separados. Los tokens/costos LLM permanecen no
   disponibles en modo determinista; no hubo llamada al proveedor.

La publicación concede al propietario la invocación de esa versión según la
política existente. El cliente B no obtiene invocación automáticamente. Para
probarlo con él, un administrador puede conceder explícitamente el grant usando
la API existente. Sustituye URL y número de versión por los reales:

```sh
export BIA_API_URL='https://TU-API.up.railway.app'
export BIA_AGENT_VERSION='2'
python3 - <<'PY'
import json, os, urllib.request
base = os.environ['BIA_API_URL'].rstrip('/')
assert base.startswith('https://'), 'Usa HTTPS'
version = int(os.environ['BIA_AGENT_VERSION'])
token = json.load(open('.tools/railway-demo-access/railway-credentials.json'))['administrator']['token']
body = json.dumps({'user_id': 'demo-customer-b', 'enabled': True,
                   'reason': 'Acceso explícito a demo sintética entregable'}).encode()
request = urllib.request.Request(
    f'{base}/api/v1/agents/billing-assistant/versions/{version}/invocations',
    data=body, method='POST',
    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
with urllib.request.urlopen(request, timeout=15) as response:
    print('Grant auditado, HTTP', response.status)
PY
```

Como `customer-b`, `INV-1002` debe terminar denegada sin datos ni referencias;
`INV-2002` debe funcionar. Un prompt que afirme ser otro cliente no cambia la
identidad. Consulta después las trazas con cada cuenta o el auditor autorizado.

## 6. Revocar acceso después de la entrega

Revoca todas las credenciales de las siete identidades administradas de esta
demo, incluidas credenciales rotadas, y desactívalas:

```sh
railway ssh --service api -- python -m app.deployment.bootstrap \
  revoke-access --confirm-synthetic-demo

railway ssh --service api -- python -m app.deployment.bootstrap status
```

Espera `access_revoked: true` y `valid_demo_tokens: 0`. Un intento de login con
cualquiera de esas credenciales debe recibir HTTP 401. Repetir `load` o volver a
aplicar el manifiesto no restaura el acceso. Las cuentas de evaluación quedan
sin credenciales externas. No se elimina el historial.

Para una revocación individual sigue disponible:

```sh
railway ssh --service api -- python -m app.identity.credentials revoke --id pat-ID_REAL
```

No borres el volumen para retirar acceso. Guarda o elimina los archivos locales
de credenciales según tu política después de revocar; borrar un archivo por sí
solo no revoca un token en el backend.

## Colisiones y límites

Si ya existen IDs reservados de agente/colección/documentos/facturas sin un
recibo de este bootstrap, la carga se detiene sin sobrescribirlos. También se
rechaza tomar control de una identidad existente mediante otro manifiesto.
No se adopta ni "repara" silenciosamente una demo creada con el bootstrap
anterior. Revisa ese caso con el operador; no elimines datos de producción ni
cambies flags para sortearlo. Los catálogos existentes se conservan, incluyendo
sus aprobaciones/revocaciones; una dependencia revocada puede bloquear la carga.

La demo usa fechas y versiones fijas. Una actualización futura requiere una
versión de dataset nueva y revisión; repetir este comando no renueva tarifas.
No añade SSO/MFA, recuperación de ejecuciones, workers ni características nuevas
del agente. No modifica los endpoints ni la autorización del runtime.

## Verificación ejecutada

Resultados locales reales y comandos en [bootstrap-verification.md](bootstrap-verification.md).
La ejecución remota en Railway queda pendiente del operador: no he autenticado
ni modificado tu despliegue para esta tarea.
