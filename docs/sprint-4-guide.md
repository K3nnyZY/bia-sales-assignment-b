# Probar Sprint 4 en macOS

## Inicio desde cero o sobre los Sprints anteriores

Desde la raíz del proyecto, con Docker Desktop instalado:

```sh
cd /Users/kennyzhu/Documents/bia-sales-assignment-b
open -a Docker
docker info
make env
make demo-env
```

Espera a que `docker info` conecte. Si el puerto 8000 está ocupado, establece
`API_PORT=8001` en `.env` (ya configurado así en el Mac de verificación).
Conserva tus credenciales existentes. Para esta demo deben estar activos
`ENABLE_DEMO_AUTH=true` y `ENABLE_LOCAL_RUNTIME=true`. Los tokens nuevos son
`DEMO_REVIEWER_TOKEN`, `DEMO_APPROVER_TOKEN` y `DEMO_AUDITOR_TOKEN`, añadidos por
`make demo-env` sin reemplazar valores anteriores. No hacen falta claves LLM.

```sh
make verify
docker compose ps -a
docker compose exec -T api alembic -c apps/api/alembic.ini current
docker compose exec -T api alembic -c apps/api/alembic.ini check
curl -fsS http://localhost:8001/health/ready
curl -fsS http://localhost:3000/api/health
open http://localhost:3000/evaluations
```

Usa 8000 en el curl si conservaste el puerto por defecto. `migrate` debe estar
Exited (0); api, web y postgres deben estar healthy. La revisión es
`0004_quality_governance`. `make verify` ejecuta todos los checks y smokes sin
consumir OpenAI/Anthropic. No borra el volumen ni publica billing-assistant.
El smoke de gobernanza crea su propio agente `quality-smoke-*` y devuelve IDs
reales de evaluación y ejecuciones. Las versiones inseguras se conservan para
inspeccionar el bloqueo.

Para levantar sin repetir tests después de instalar:

```sh
make up
make seed
make runtime-seed
make governance-seed
make governance-smoke
```

Los seeds solo insertan datos que faltan; no reactivan herramientas, permisos o
tokens revocados. Los contenedores continúan en segundo plano al cerrar Terminal.
`make down` los detiene y conserva datos. No uses `down --volumes` para este flujo.

## Recorrido completo en el navegador

1. Abre `/agents`. Entra con el valor **DEMO_CREATOR_TOKEN** de tu `.env`.
   Crea un agente con un ID nuevo (por ejemplo `billing-quality-demo`), nombre,
   departamento y descripción. La identidad nunca viene del formulario de ejecución.
2. En el Builder introduce objetivo e instrucciones. Selecciona **Workflow →
   Billing StateGraph · v1.0.0** y modelo **synthetic-balanced-v1**. Marca solo:
   **get_customer_invoice v3.0.0**, **get_previous_invoice v1.0.0** y
   **search_billing_knowledge v1.0.0**. No selecciones los contratos antiguos de
   invoice v1/v2, que no tienen adaptadores de runtime.
3. Usa **12 pasos**, **5 llamadas**, **30 segundos**, y un límite de salida
   compatible (1000 tokens sirve). El alta ya creó v1 editable. Pulsa **Guardar borrador**, después
   **Crear snapshot**. La versión y su SHA-256 quedan inmutables.
4. En **Evaluaciones**, selecciona tu agente y v1, la suite **Billing runtime and
   security baseline v1** y modo **Determinista · sin LLM**. Pulsa **Evaluar versión**.
   Espera el resultado; los nueve escenarios deben pasar. Inspecciona cada resultado
   y abre sus trazas. Los rechazos de acceso son resultados esperados de las pruebas.
5. Pulsa **Solicitar aprobación**: estado `pending_approval`. Creator no puede
   aprobar. Cierra sesión con **Salir** e introduce **DEMO_APPROVER_TOKEN** o
   **DEMO_ADMIN_TOKEN**. Approver debe ser independiente; Admin puede decidir
   sobre cualquier candidata válida. En **Solicitudes e historial
   de aprobaciones**, pulsa **Revisar y aprobar** en la solicitud pendiente.
   Se seleccionan su agente y versión y se abre el panel **Revisión de aprobación**.
   Revisa los resultados y escribe **Motivo de decisión o rollback**; el motivo
   es obligatorio y la interfaz lo indica si el botón está deshabilitado. Después
   pulsa **Aprobar**. Estado `approved`. Pulsa **Publicar versión**: `published`.
   Con rol Approver, el servidor rechaza la decisión del autor, propietario o
   solicitante. Admin puede aprobarla con motivo y auditoría, sin omitir evaluaciones
   ni el gate del hash exacto. Requiere `0008_admin_approval`.
6. Entra en **Playground** con **DEMO_CREATOR_TOKEN**. Selecciona tu agente/v1,
   canal **Published · versión aprobada**, modo determinista, consulta **Comparar
   con el mes anterior**, factura **INV-1002**, período **2026-09**. Ejecuta.
   Debe resultar `completed`, diferencia **64.400 COP**, aumento **23 %**, nueve
   nodos y tres herramientas. Se muestra claramente que no hubo proveedor LLM.
7. Cambia factura a **INV-2002**: `denied / INVOICE_NOT_ACCESSIBLE`, sin evidencia
   de otro cliente. Cambia a **INV-1001**: `escalated /
   PREVIOUS_INVOICE_UNAVAILABLE`, con intento fallido persistido. No se inventa
   una factura anterior. Las pruebas automatizadas también provocan un fallo
   `UPSTREAM_UNAVAILABLE` y timeouts, sin añadir un interruptor de fallo al producto.
8. Abre **Trace Viewer** desde el resultado o **Trazas**. Revisa run_id, versión,
   hash, canal, modo, nodos, herramientas, errores y tiempos observados.
   Recarga e identifícate otra vez: la traza permanece. Con **DEMO_AUDITOR_TOKEN**
   puedes consultar ejecuciones globales y auditoría; creator ve sus propias
   ejecuciones y evaluaciones, sin acceso a facturas de otros clientes.
9. En Trazas, los conteos y latencias proceden de runs persistidos. Las ejecuciones
   de evaluación se excluyen de métricas operativas. Tokens y costo deterministas
   aparecen **No disponible**, no cero. Los costos del proveedor, cuando hay uso
   reportado y precios, son **estimaciones**, con cobertura de runs conocidos.

## Probar rollback y bloqueo de candidatas inseguras

1. Como creator, vuelve al Builder y usa **Nueva versión desde esta** sobre v1.
   Guarda y congela v2. Evalúa, solicita, aprueba con otra identidad y publica v2.
   v1 queda `deprecated`; su contenido no cambia.
2. Como approver, selecciona v1 en Evaluaciones, escribe un motivo y pulsa
   **Rollback a esta versión**. El puntero vuelve a v1; v2 queda deprecada. Solo se
   admiten versiones ya publicadas con aprobación y evaluación todavía vigentes.
3. Para comprobar el bloqueo, clona otra versión, establece **Máximo de llamadas
   a herramientas = 1**, guarda y congela. Evalúala. Las comparaciones fallan y
   el gate rechaza **Solicitar aprobación**. Tampoco es posible publicar vía API.
4. Una suite nueva sin los ocho checks obligatorios puede pasar sus propias
   pruebas, pero el gate informa `MANDATORY_CHECKS_MISSING`. No evita seguridad.
   Revocar un modelo/herramienta o cambiar evidencia/permisos evaluados también
   bloquea el gate. Las pruebas SQL verifican inmutabilidad y publicación sin aprobación.

## Endpoints y contratos

Todos requieren bearer token de identidad local activa. Swagger está en
`http://localhost:8001/docs` (o tu API_PORT).

| Operación | Endpoint `/api/v1` | Rol |
| --- | --- | --- |
| Listar/crear suites inmutables | `GET/POST /evaluation-suites` | Lectura activa; alta reviewer/admin |
| Evaluar snapshot | `POST /agents/{id}/versions/{n}/evaluations` | Creator propietario, reviewer/admin |
| Listar/ver resultados | `GET /evaluations`, `GET /evaluations/{id}` | Propietario o personal de gobernanza |
| Ver gate y revisión | `GET /agents/{id}/versions/{n}/governance` | Propietario o personal de gobernanza |
| Solicitar aprobación | `POST /agents/{id}/versions/{n}/submit` | Creator propietario/admin |
| Aprobar/rechazar | `POST /agents/{id}/versions/{n}/approve` | Approver independiente o Admin |
| Listar aprobaciones | `GET /approvals` | Propietario o personal de gobernanza |
| Publicar/deshabilitar | `POST /agents/{id}/versions/{n}/publish`, `/disable` | Approver/admin |
| Rollback | `POST /agents/{id}/rollback` | Approver/admin |
| Conceder/revocar invocación | `POST /agents/{id}/versions/{n}/invocations` | Solo admin; no concede permisos de facturas |
| Ejecutar | `POST /runs` | Grant explícito y políticas de recurso |
| Runs/trazas | `GET /runs`, `/runs/{id}`, `/runs/{id}/trace` | Caller; auditor global; evaluación según permisos |
| Métricas | `GET /metrics` | Datos propios; auditor global |
| Auditoría | `GET /audit-events?agent_id=...` | Propietario o personal de gobernanza |

Evaluar requiere `expected_config_hash`, y admite `suite_id`, `suite_version`,
`mode`. Submit/disable requieren `expected_revision` y `expected_config_hash`.
Approve añade `decision: approved|rejected` y `reason`. Publish añade
`expected_publication_revision` (0 si no existe). Obtén siempre esos valores de
`/governance`; no los inventes. Rollback recibe `target_version`,
`expected_publication_revision` y `reason`. Un conflicto devuelve 409.

Ejemplo de ejecución publicada en Swagger (la API resuelve la versión activa):

```json
{
  "agent_id": "billing-quality-demo",
  "channel": "published",
  "mode": "deterministic",
  "task": "compare",
  "invoice_id": "INV-1002",
  "message": "Compara mi factura con agosto"
}
```

Preview sigue disponible para las pruebas del Sprint 3, explícitamente etiquetado,
con grants y permisos de negocio; no representa una publicación.

## Pruebas y persistencia

```sh
make test
make lint
make web-check
make runtime-smoke
make governance-smoke
# Requiere Node 24 y Google Chrome en el Mac:
npm ci
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

Para demostrar persistencia sobre un reinicio, sin claves ni tokens en comandos:

```sh
docker compose exec -T api python - < scripts/governance_smoke.py > /tmp/bia-governance-proof.json
docker compose restart api
docker compose up -d --wait api
docker compose exec -T -e GOVERNANCE_TRACE_PROOF="$(cat /tmp/bia-governance-proof.json)" api python - < scripts/governance_smoke.py
```

La última comprobación compara SHA-256 de las tres trazas y consulta la evaluación
y el evento de rollback. No borra historial. Para desarrollo nativo sigue el
README y añade `PYTHONPATH=apps/api uv run --frozen python -m app.governance.seed`.

## Alcance pendiente

El runner local solo cubre billing v1 con fixtures sintéticos; no es un grader
universal. SSO productivo, workers/recovery, retención/exportación de auditoría,
conciliación de costos y pruebas de carga quedan pendientes. RAG/ingestión no se
implementan. La generación real depende de credenciales/cuota y se prueba aparte
con `make provider-smoke`; puede consumir saldo y no forma parte de verify/CI.
La última evidencia del Sprint 3 fue un rechazo de cuota; este Sprint 4 no afirma
que haya habido generación real exitosa. No se avanzó al Sprint 5.
