# Despliegue manual en Railway

Preparación local: 2026-10-16. **No se ha desplegado ni verificado ninguna URL
de Railway.** Los comandos remotos de este documento los ejecuta el propietario
de la cuenta. `init`, `config apply`, `up` y los servicios/volumen generan consumo.
Revisa el plan y configura un límite de gasto en Railway antes de aplicarlo.
El mínimo de Hobby no es un precio fijo para estos tres servicios: se factura
el uso adicional. Consulta [precios](https://docs.railway.com/pricing) y
[control de costos](https://docs.railway.com/pricing/cost-control).

## 1. Preparar herramientas y acceso

Desde Terminal en tu Mac:

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
npm install --prefix .tools/railway-cli @railway/cli@5.69.0 --no-audit --no-fund
export PATH="$PWD/.tools/railway-cli/node_modules/.bin:$PATH"
railway --version
railway login --browserless
railway whoami
npm ci --prefix infra/railway
python3 scripts/railway_credentials.py
```

Completa el login en el navegador. No pegues credenciales en un chat.
El último comando crea tres archivos privados con permisos 0600 en `.tools/`:

- `railway-credentials.json`: tokens de acceso de los usuarios, válidos siete días.
- `railway-manifest.json`: identificadores, hashes y vencimientos, sin tokens.
- `railway-secrets.json`: contraseña aleatoria de PostgreSQL y manifiesto de hashes.

El generador rechaza sobrescribir archivos. Si ya existen, reutilízalos si aún
son válidos; no los borres/regeneres después de aprovisionar la base. Conserva
la contraseña de PostgreSQL en tu gestor de secretos: cambiarla en una variable
no cambia la contraseña de un volumen ya inicializado. Estos archivos están
excluidos de Git, Docker y la subida de código de Railway.

## 2. Crear un proyecto nuevo y revisar el plan

No enlaces esta configuración a un proyecto existente: gestiona tres servicios
y un volumen con nombres concretos.

```sh
railway init --name bia-agent-studio
railway status
railway config plan --file infra/railway/railway.ts
```

Selecciona tu workspace y comprueba el proyecto/entorno enlazados. El plan debe
crear `postgres`, `api`, `web` y `postgres-data` de 1 GiB. No debería eliminar
recursos. No utilices `--show-values`, `--decrypt-variables` ni compartas salidas
de variables o archivos de plan: pueden contener secretos.

La configuración usa [Railway IaC](https://docs.railway.com/infrastructure-as-code),
no `railway.json`/`railway.toml`, que la documentación actual de Railway declara
obsoletos para servicios nuevos.

Cuando aceptes el costo y hayas revisado ese plan:

```sh
railway config apply --file infra/railway/railway.ts
railway service status --service postgres
```

Espera que PostgreSQL esté activo antes de subir el backend. Si el plan no es
el esperado, detente; no añadas `--confirm-destructive` para forzarlo.

## 3. Configuración que queda aplicada

| Servicio | Build/imagen | Persistencia y conexión |
| --- | --- | --- |
| postgres | `pgvector/pgvector:0.8.7-pg16-bookworm` | Volumen `/var/lib/postgresql/data`; `PGDATA` en subdirectorio; sin dominio ni proxy TCP público. |
| api | Contexto raíz `/`, `apps/api/Dockerfile` | PostgreSQL por DNS privado; embeddings reales incluidos en imagen; originales, vectores, ejecuciones y trazas en PostgreSQL. |
| web | Contexto raíz `/`, `apps/web/Dockerfile` | `BACKEND_URL=http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000`, solo en servidor. |

Una réplica de cada servicio en Virginia (`us-east4-eqdc4a`). Límites iniciales:
API 2 CPU/2 GiB; web y PostgreSQL 1 CPU/512 MiB cada uno. Son límites de recursos,
no un presupuesto mensual garantizado. Ajusta tras observar métricas reales.

El backend usa `APP_ENV=production`, `ENABLE_ACCESS_TOKEN_AUTH=true`,
`ENABLE_PUBLISHED_RUNTIME=true`, `ENABLE_DEMO_AUTH=false` y
`ENABLE_LOCAL_RUNTIME=false`. Los tokens conocidos de `.env.example` no permiten
entrar. Los permisos y la separación entre creador/aprobador se verifican en
backend. No hay registro público ni API pública de emisión de tokens.

`CORS_ORIGINS=[]` bloquea llamadas de otros orígenes desde navegadores. Next.js
usa su proxy del mismo origen, por lo que el Studio funciona sin abrir CORS.
Si necesitas acceso directo desde una web diferente, añade exclusivamente su
origen HTTPS exacto en la configuración IaC y vuelve a revisar/aplicar el plan.

El predeploy ejecuta `scripts/railway-predeploy.sh`: Alembic `upgrade head` y
aprovisionamiento sintético idempotente. Un fallo detiene el despliegue. El
bootstrap no publica ni aprueba agentes y no restaura credenciales revocadas.
La configuración conserva las credenciales de bootstrap hasta su vencimiento;
no las renueva automáticamente. No se copia tu `.env` local.

## 4. Subir backend y frontend desde el monorepo

Ejecuta desde la raíz del repositorio, no desde `apps/api` ni `apps/web`:

```sh
railway up --service api --ci
railway service status --service api
railway up --service web --ci
railway service status --service web
railway domain --service web --port 3000
railway domain --service api --port 8000
```

Guarda las dos URLs HTTPS impresas. El backend expone su API protegida; las rutas
administrativas siguen exigiendo rol autorizado. Su healthcheck es
`/health/ready`; el de Next.js es `/health`. Un build enviado o encolado no prueba
que el servicio esté saludable: comprueba el estado final.

Si falla:

```sh
railway logs --service api
railway logs --service web
railway logs --service postgres
```

El primer build descarga los pesos de embeddings fijados por revisión. Si un
entorno no permite esa descarga, el build debe fallar; no se reemplazan los
vectores por resultados ficticios. No compartas logs sin revisar datos sensibles.

## 5. Comprobar las URLs

Sustituye los dominios por los impresos en el paso anterior:

```sh
export BIA_WEB_URL='https://TU-WEB.up.railway.app'
export BIA_API_URL='https://TU-API.up.railway.app'
curl --fail --silent --show-error "$BIA_API_URL/health/ready"
curl --fail --silent --show-error "$BIA_WEB_URL/health"
curl --silent --output /dev/null --write-out '%{http_code}\n' "$BIA_API_URL/api/v1/me"
```

Espera health HTTP 200 con migraciones `ok` y `/me` HTTP 401 sin credencial.
Esto todavía no verifica publicación ni facturación.

## 6. Probar el flujo desde la interfaz

Para copiar el token del creador al portapapeles sin imprimirlo:

```sh
python3 -c 'import json; print(json.load(open(".tools/railway-credentials.json"))["creator"]["token"], end="")' | pbcopy
open "$BIA_WEB_URL/agents"
```

Pégalo en **Token de acceso**. Los IDs `demo-*` identifican clientes y empleados
sintéticos; su acceso desplegado requiere los tokens privados recién emitidos.
Las cuentas de evaluación no tienen credenciales de login.

1. En **Agentes**, abre `billing-assistant`. El bootstrap crea snapshots
   candidatos, incluida una versión con RAG; aún no existe publicación activa.
2. Selecciona el snapshot con conocimiento (`billing-reference`, normalmente v2)
   y abre su gestión en **Evaluaciones**.
3. Ejecuta la suite `billing-runtime` v1 en modo determinista. Revisa los nueve
   resultados persistidos; deben pasar antes de solicitar aprobación.
4. Solicita aprobación como creador y cierra sesión.
5. Copia el token de `approver` usando el mismo comando anterior sustituyendo
   `"creator"` por `"approver"`. Entra con él, revisa la evaluación, escribe un
   motivo, aprueba y publica. El creador no puede aprobarse a sí mismo.
6. Vuelve a entrar como creador. En **Playground**, selecciona la publicación,
   canal **Published**, modo **Determinista**, factura `INV-1002`, período
   `2026-09` y tarea de comparación. Envía la consulta.
7. Comprueba diferencia **64.400 COP**, aumento **23 %**, referencias a documentos
   con versión/fragmento y traza con nodos y tres herramientas reales.
8. Abre **Trazas** y la ejecución. Las facturas deben venir de
   `invoice-lookup-v3`/`invoice-previous-v1`; el conocimiento, del retrieval RAG.
9. Como `customer-b`, la misma factura `INV-1002` debe ser denegada sin evidencia.
   Sus facturas permitidas son `INV-2001`/`INV-2002`.

Para probar **Builder** y toda la ingesta/publicación con un agente nuevo desde
el navegador automatizado, sin mocks ni llamadas a un proveedor LLM:

```sh
npm ci
E2E_BASE_URL="$BIA_WEB_URL" \
BIA_CREDENTIALS_FILE="$PWD/.tools/railway-credentials.json" \
PLAYWRIGHT_CHANNEL=chrome \
node scripts/final_ui_audit.mjs
```

Requiere Google Chrome instalado. El script crea una colección, carga/ingiere y
aprueba Markdown, configura un agente con ese documento, congela, evalúa,
solicita aprobación, cambia de usuario, publica, ejecuta y consulta trazas.
Escribe evidencia sin credenciales en `/tmp/bia-final-audit-ui.json` y una captura
en `/tmp/bia-final-ui.png`. Crea datos sintéticos persistentes en ese proyecto.
No confundas este comando documentado con una ejecución remota ya realizada.

Para comprobar persistencia, guarda el `run_id`, reinicia solo la API y vuelve
a consultar esa traza desde el Studio:

```sh
railway restart --service api
```

No borres el volumen ni el servicio PostgreSQL.

## 7. Credenciales y modelo real

Los tokens privados vencen después de siete días. Un operador con acceso al
servicio puede emitir otro token para un usuario existente, máximo 168 horas:

```sh
railway ssh --service api -- python -m app.identity.credentials issue --user-id demo-creator --hours 24 --output /tmp/creator-access.json
railway service link api
umask 077
railway service files download /tmp/creator-access.json .tools/creator-access.json
chmod 600 .tools/creator-access.json
```

El archivo de respuesta se entrega solo al operador y no se
imprime en logs. Para revocar el ID de un token:

```sh
railway ssh --service api -- python -m app.identity.credentials revoke --id pat-ID_DEL_TOKEN
```

La configuración inicial usa **generación determinista identificada como tal**.
LangGraph, SQL, cálculos, extracción, embeddings locales y pgvector sí son reales.
No hay tokens/costos de proveedor inventados ni consumo de OpenAI en este flujo.
No necesitas una API key para RAG. Para usar un LLM real se requieren clave
válida del servidor, cuota, modelo exacto aprobado, nueva versión, evaluación y
publicación en modo `provider`. No basta con añadir una API key al servicio.
No reutilices una clave que se haya compartido en un chat; rótala primero.

## Estado y límites

Los resultados locales se registran al final de esta guía. El primer plan de
Railway, el build remoto, la conectividad privada, las URLs y el smoke remoto
quedan **NOT VERIFIED** hasta ejecutarlos en tu cuenta. El proveedor LLM real
tampoco forma parte de la prueba determinista.

Este despliegue es una demo protegida con datos sintéticos, no una certificación
de producción empresarial. Quedan pendientes SSO/MFA, backups y restauración
verificados, alta disponibilidad, control de abuso/rate limits, recuperación
de runs interrumpidos y separación de credenciales PostgreSQL de migración y
aplicación. No subas datos reales de clientes.

## Verificación local ejecutada

| Comando / comprobación | Resultado real |
| --- | --- |
| `railway --version` / `railway whoami` | CLI 5.69.0 instalada; sin sesión autenticada. |
| `RUN_DB_TESTS=1 .venv/bin/pytest -q` | 258 PASS, 75,75 s; incluye PostgreSQL real, migración upgrade/downgrade/replay, seguridad y flujo de publicación con credenciales privadas. |
| `RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_deployment.py -q -x` | 5 PASS; bootstrap idempotente, rechazo de tokens demo, expiración, revocación, publicación independiente, LangGraph/RAG y acceso entre clientes. |
| `RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_database.py -q` | 2 PASS tras actualizar la lista esperada de tablas para `access_tokens`. La primera regresión había detectado esa expectativa obsoleta; se corrigió y se repitió la suite completa. |
| `.venv/bin/ruff check apps/api scripts` | PASS. |
| `.venv/bin/ruff format --check apps/api scripts` | PASS, 94 archivos. |
| `npm test` | 15 PASS. |
| `npm run lint` / `npm run typecheck` / `npm run build` | PASS. |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | 7 PASS, 13,2 s; interfaz local real sobre Docker, incluido Builder → evaluar → aprobar → publicar → ejecutar → traza y Knowledge/RAG. |
| `docker build --target production -f apps/api/Dockerfile -t bia-railway-api-check .` | PASS; imagen de backend con etapa predeterminada de producción. |
| `docker compose up --build --wait --wait-timeout 180` | PASS; migración terminada, PostgreSQL/API/web saludables. |
| `node_modules/.bin/tsc --noEmit --skipLibCheck --target es2022 --module nodenext --moduleResolution nodenext infra/railway/railway.ts` | PASS. |
| Validación local con `validateGraph` del SDK oficial `railway@3.16.0` | PASS: tres servicios y un volumen; secretos de prueba temporales; sin llamadas remotas. |
| `git diff --check` | PASS. |
| `railway config plan/apply`, builds remotos, dominios, smoke HTTPS y persistencia remota | **NOT VERIFIED: no ejecutados; requieren tu cuenta y consumo autorizado por ti.** |

Archivos de preparación: `.railwayignore`, `infra/railway/`, scripts de
credenciales/predeploy/arranque, módulo `app/deployment`, credenciales privadas
en `identity`, migración `0006_private_access_tokens`, configuración/runtime y
evaluador, healthcheck, Dockerfile de API, controles de Playground/login,
pruebas de despliegue/migraciones y selectores E2E, smoke UI parametrizable,
`.env.example`, README, arquitectura y ADR-014. No se modificaron servicios de
Railway ni se copiaron claves de proveedor. Estos cambios están en tu árbol de
trabajo; aún no los he confirmado en Git.
