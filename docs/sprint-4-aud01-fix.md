# Corrección de AUD-01

Fecha: 2026-10-16. Estado: **corregido y verificado**. Alcance: cierre del fallo
de historial del Sprint 4; no se inició Sprint 5.

## Comportamiento corregido

`GET /api/v1/audit-events?agent_id=...` ahora encuentra los eventos
agent.created, agent.updated y agent.deleted mediante su referencia de recurso.
La API devuelve el agent_id resuelto; Next.js muestra el identificador correcto
en lugar de etiquetar esos eventos como «Catálogo». Las consultas sin filtro del
propietario también incluyen sus eventos de metadatos.

Se conservan las filas append-only existentes. Los eventos nuevos añaden el
propietario del agente en details.owner_id desde el contexto confiable del backend.
Ese propietario puede consultar sus eventos incluso tras borrar un agente vacío;
la eliminación sigue permitida, sin destruir ni reescribir el historial.

La visibilidad de metadatos nuevos corresponde al propietario registrado en el
momento de cada evento. Los eventos legacy sin propietario se resuelven contra
un agente existente que ya existiera al registrar el evento. Reutilizar un ID no
concede acceso al historial de otro propietario. Los IDs de catálogos no se
interpretan como referencias a agentes. Se mantiene la visibilidad de eventos
de versiones por propietario y de todos los eventos para roles de gobernanza.

Para un evento legacy cuyo agente ya se eliminó y no tenga propietario registrado,
los roles de gobernanza conservan acceso; no se atribuye ese evento a un usuario
sin evidencia. Esta es una decisión de autorización conservadora sobre información
histórica incompleta, documentada en ADR-012.

## Verificación ejecutada

Se reprodujo el defecto antes de cambiar el código: el test del propietario obtuvo
historial vacío en vez de creación/edición (**1 failed**, detención en primer fallo).
Después de corregirlo, los **nueve casos nuevos pasaron**, cubriendo:

- Creación/edición por administrador visibles al propietario y los cuatro roles de gobernanza.
- Aislamiento de otro propietario y del viewer; colisión de ID con un evento de catálogo.
- Persistencia de creación, edición y eliminación después de borrar un agente vacío.
- Reutilización de IDs sin filtrar eventos antiguos al nuevo propietario.
- Lectura de eventos legacy sin modificar sus datos ni fechas.
- Propiedad congelada por evento cuando un administrador transfiere el agente.

Resultados finales:

| Comprobación | Resultado real |
| --- | --- |
| `make verify` | **Exit 0** |
| Pytest completo con PostgreSQL 16 | **224 passed en 35.96 s**, incluidas regresiones de Sprints 3 y 4 |
| Ruff lint / formato | **PASS**, 72 archivos Python |
| Build Next.js, ESLint y TypeScript | **PASS** |
| Pruebas frontend | **13 passed** |
| Playwright con Chrome | **5 passed en 10.2 s** |
| `scripts/governance_audit.py` | **Exit 0**, `findings: []`, métricas SQL y cadena de hashes coinciden |
| Evento original de AUD-01 | Visible al creator y al auditor con su agent_id resuelto |
| `git diff --check` | PASS |

El evento histórico `aud-fe0cb81d81864068ae76334c6768a19d` del agente
`quality-smoke-d3648f6b586a` se consultó de nuevo usando ambas identidades reales.
Su payload sigue sin owner_id, confirmando que la consulta lo resuelve sin
necesitar una reescritura. Las pruebas PostgreSQL además comparan los detalles,
FK y fecha antes/después de consultar.

En Chrome se comprobó el ciclo completo de publicación y un flujo adicional de
agente vacío: crear, editar, eliminar y consultar los tres eventos desde Trazas;
viewer no puede verlos. Se mantienen las comparaciones entre UI, proxy y FastAPI
para métricas y trazas reales. Ninguna comprobación de esta corrección llamó a
un proveedor LLM.

## Comandos utilizados

```sh
RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_audit_history_api.py -x -q --tb=short
RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_audit_history_api.py -q --tb=short
make verify > /tmp/bia-aud01-verify.log 2>&1
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e > /tmp/bia-aud01-e2e.log 2>&1
docker compose exec -T api python - < scripts/governance_audit.py
.venv/bin/ruff check apps/api scripts
.venv/bin/ruff format --check apps/api scripts
git diff --check
```

El primer comando muestra la reproducción previa; repetirlo sobre el código
corregido debe pasar. El acceso al evento histórico original se verificó con
un script de solo lectura mediante urllib dentro del contenedor, usando los tokens
del entorno para creator/auditor, sin mostrarlos. Los IDs citados pertenecen a la
base local y no se crean artificialmente en una instalación nueva.

No se requieren tablas, dependencias ni migraciones nuevas. `make verify` volvió
a comprobar el roundtrip de migraciones y la compatibilidad del esquema 0004.

## Archivos de esta corrección

- `apps/api/app/agents/routes.py`: propietario confiable en eventos nuevos de metadatos.
- `apps/api/app/governance/audit.py`: acciones exactas de metadatos de agente.
- `apps/api/app/governance/routes.py`: resolución del recurso y autorización en backend.
- `apps/api/tests/test_audit_history_api.py`: nueve casos de regresión/seguridad nuevos.
- `tests/e2e/governance.spec.ts`: assertions de etiquetas y nuevo flujo UI de borrado/historial.
- `scripts/governance_audit.py`: descripción del verificador, que ahora pasa sin omisiones.
- `docs/decisions/ADR-012-quality-governance.md`: política de visibilidad y compatibilidad legacy.
- `docs/sprint-4-audit.md`, `README.md` y este documento: estado actualizado y evidencia.

## Verificación manual

```sh
make verify
open http://localhost:3000/traces
docker compose exec -T api python - < scripts/governance_audit.py
```

Entra con DEMO_CREATOR_TOKEN y pulsa **Actualizar observabilidad**. Los eventos
visibles de creación/edición muestran el ID del agente. Con DEMO_AUDITOR_TOKEN
puedes ver el historial global. El verificador debe terminar con findings vacío.
Los demás límites locales y de proveedor documentados en Sprint 4 siguen vigentes;
esta corrección cierra específicamente AUD-01.
