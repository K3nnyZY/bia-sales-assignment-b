# ADR-012 — Quality & Governance sobre snapshots del Registry

Estado: implementado para demo local en Sprint 4 (2026-10-15).

## Contexto y decisión

Se conserva el monolito modular, el StateGraph real y los contratos de Sprints
1–3. `governance/` incorpora suites, evaluaciones, aprobación independiente,
publicación transaccional, rollback, auditoría y consultas de observabilidad.
No se añaden servicios, dependencias, graders LLM ni funcionalidades de Sprint 5.

Un `AgentVersion` congelado conserva su fila y hash inmutables. Cambiar su estado
para publicar rompería el trigger del Sprint 2. Por eso `version_governance`
almacena el ciclo por separado: draft → testing → pending_approval → approved →
published → deprecated/disabled. `agent_publications` apunta a la única versión
activa. `Agent.status` sigue representando disponibilidad del registro lógico;
`AgentVersion.status` sigue siendo draft/snapshot. El estado de publicación se
consulta en `/governance`, no se deduce del antiguo `Agent.state`.

Los cambios serializan sobre el agente y exigen revisión y hash esperados.
La publicación también exige revisión del puntero, de forma que una pestaña
antigua no puede reemplazar silenciosamente una publicación. Constraints y
triggers PostgreSQL verifican transiciones, FKs, aprobación, separación de
personas, resultados finales e inmutabilidad. Un constraint diferido verifica
que el puntero y el estado published coincidan al confirmar la transacción.

## Evaluaciones y Publication Gate

Las suites son contratos inmutables `(id, version, suite_hash)` con nombres de
pruebas registrados; no ejecutan código proporcionado por usuarios. La política
del servidor exige ocho controles: configuration, invoice, comparison, knowledge,
cross_customer, prompt_injection, missing_invoice y tool_permission. La suite
base añade missing_previous. Una suite reducida puede ejecutarse y pasar, pero
no habilita publicación. No hay una API para subir resultados aprobados.

El runner `billing-evaluator-v1` ejecuta el mismo `execute_run`/StateGraph con
principales sintéticos reservados sin tokens expuestos y facturas INV-9001/9002
e INV-9101/9102. No utiliza facturas del creador para evaluar. Solo las ejecuciones
internas asociadas a una evaluación running del snapshot exacto admiten esas
identidades. Mantienen la autorización de herramienta, permisos y propiedad
real de cada factura. La API pública no acepta channel=evaluation ni evaluation_id.
Los resultados enlazan las trazas persistidas de sus ejecuciones.

Cada evaluación conserva el hash exacto de snapshot, suite y dependencias:
modelo/herramientas actuales, permisos/estado del propietario, fixtures,
principales reservados y conocimiento aprobado/vigente del escenario. Se
comprueban nuevamente antes de aprobar, publicar, hacer rollback y ejecutar
por el canal published. La evaluación más reciente es la autoridad; un pase
antiguo no oculta un fallo nuevo. Evaluar otra vez invalida la aprobación de
una candidata. Una versión que ya se publicó debe clonarse para reevaluarse.
Un cambio de dependencias puede bloquear una publicación existente; se necesita
una nueva candidata evaluada, o restaurar exactamente las dependencias válidas.

Las aserciones son deterministas aun cuando se seleccione explícitamente el
modo provider para un snapshot de proveedor. El runner no reemplaza el modelo
congelado por uno ficticio. El modo determinista solo acepta modelos synthetic y
no contacta al SDK. Un error de proveedor o timeout produce fallos persistidos y
bloquea el gate. No hay fallback ni consumo de proveedor en verify/CI.

## Aprobación, publicación y rollback

Creator propietario, administrator o reviewer pueden evaluar; las solicitudes
las presenta el propietario creator o administrator. Solo approver/administrator
pueden decidir, publicar, deshabilitar o volver a una publicación anterior.
Ni propietario, autor del snapshot ni solicitante pueden aprobarlo, incluso
si tienen rol administrator. El motivo y actor quedan auditados. Una decisión
es final; reevaluar y volver a solicitar crea otra aprobación.

La publicación concede al propietario únicamente invocación sobre esa versión,
sin conceder permisos de negocio ni reactivar un grant previamente revocado.
El endpoint de grants requiere administrator y audita altas/revocaciones.
Un rollback solo acepta una versión realmente publicada antes, con su aprobación
y evaluación todavía válidas. Cambia el puntero y depreca la anterior de forma
atómica; no modifica configuraciones ni borra historial.

## Runtime, trazas y métricas

`POST /runs` admite preview (predeterminado compatible con Sprint 3) y published.
Preview sigue siendo una prueba local explícita con grants y autorización.
Published resuelve el puntero activo si no se indica versión y exige el modo
evaluado; no permite fijar una versión distinta ni saltar el gate. Ambos canales
siguen bloqueados en producción mientras solo exista identidad demo. Cada
acceso y la liberación de evidencia revalidan autorización. Deshabilitar una
versión impide su ejecución incluso por preview.

El caller conserva acceso a sus runs. Auditor puede consultar todos; los roles
de calidad y el propietario pueden consultar las trazas sintéticas de sus
evaluaciones. Administrator no recibe acceso a facturas de otros callers por
su rol. Audit events son append-only; incluyen configuración, evaluación,
aprobación, publicación, rollback, grants, catálogo y finalización de runs.
No se guardan credenciales, prompts completos ni resultados crudos de herramientas.

`/metrics` agrega observaciones persistidas según la misma visibilidad. Excluye
el canal evaluation y separa modelos/modos. Informa estados, llamadas/errores de
herramientas y latencias media/P50/P95. Tokens son únicamente los reportados por
el SDK. Costos son estimaciones de catálogo con cobertura conocida, nunca cobros
reales. Null indica indisponible, sin sustituirlo por cero. No hay streaming de
métricas ni conciliación de facturas del proveedor.

## Límites y consecuencias

El evaluador está acotado por timeout global y por límites del runtime, usa
fixtures locales explícitos y solo cubre billing_workflow_v1. No demuestra calidad
de lenguaje universal ni resistencia a cualquier ataque. Las pruebas de regresión
además ejercitan fallos de SDK/adapters sin simular resultados reales en producto.
Una caída abrupta puede dejar evaluación/run running y bloquea publicación;
no hay recuperación de workers/checkpoints. Una nueva candidata permite continuar.

La integridad SQL refuerza el backend; un administrador de PostgreSQL capaz de
alterar triggers sigue fuera de la frontera de confianza. La autorización de
roles ocurre en el backend con identidades confiables, no en prompts ni headers
de rol enviados por el cliente. SSO, despliegue productivo, RAG, ingestión,
pgvector y recuperación distribuida continúan pendientes.


## Corrección AUD-01 — Resolución de metadatos de agente (2026-10-16)

Los eventos agent.created/updated/deleted conservan una referencia desacoplada
`details.resource_id`, permitiendo eliminar agentes sin versiones sin borrar
su historial. Los eventos nuevos también congelan `details.owner_id`, obtenido
por el servidor del agente, no del manifiesto ni de un campo libre del cliente.
Su visibilidad para no-staff corresponde al propietario registrado en cada evento,
incluso después de borrar o transferir el agente. Los eventos vinculados a una
versión mantienen la autorización por propietario del agente existente.

El endpoint resuelve `agent_id` en la respuesta para esas tres acciones exactas;
el filtro y el label de Next.js reciben el mismo sujeto resuelto. Nunca interpreta
un resource_id de catálogo como agente. No actualiza filas históricas ni añade
FKs que impidan borrar agentes vacíos. No hace falta otra migración.

Para eventos legacy sin owner_id, el propietario actual puede leerlos si el agente
existía cuando se registró el evento. La comparación de created_at impide que
reutilizar un ID exponga el historial de un agente anterior a otro usuario.
Si el agente legacy ya se eliminó y no consta propietario, solo los roles de
gobernanza autorizados pueden consultar esos eventos; no se inventa una relación
de propiedad a partir del actor. Auditor siempre puede consultar el historial.

Ver la [corrección y pruebas](../sprint-4-aud01-fix.md).
