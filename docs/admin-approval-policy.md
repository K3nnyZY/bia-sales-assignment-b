# Aprobación administrativa de agentes

Cambio solicitado explícitamente por el propietario del proyecto: Admin puede
aprobar cualquier candidata válida, incluidas las versiones que creó, posee o
envió a aprobación. Se sustituye la política anterior que exigía independencia
también a Admin. Este cambio no concede permisos de negocio ni publica automáticamente.

| Rol autenticado | Decidir sobre versión propia | Decidir sobre otra versión |
| --- | --- | --- |
| administrator | Sí, con motivo y auditoría | Sí, con motivo y auditoría |
| approver | No si es propietario, autor o solicitante | Sí, si es independiente |
| creator / reviewer / auditor / viewer | No | No |

## Controles que se conservan

La versión debe ser un snapshot, el agente debe estar habilitado y debe existir
una solicitud pending_approval. La decisión exige revisión vigente, hash exacto
y motivo no vacío. Aprobar revalida el Publication Gate: evaluación vigente y
satisfactoria, controles críticos completos, modelo y herramientas aprobados,
permisos del propietario y dependencias actuales. Admin no puede aprobar una
configuración diferente de la evaluada ni saltarse fallos críticos.

La excepción no permite editar snapshots, reescribir decisiones previas, borrar
historial, modificar roles desde cabeceras ni conceder acceso a facturas. Un Admin
que configure herramientas sigue limitado por los permisos del propietario.

Cada decisión registra actor, motivo, versión, evaluación y hash. Se añaden los
metadatos `decision_role` y `administrator_override`. Este último es true solo
cuando un Admin decide sobre una versión que posee, creó o solicitó; no significa
que se haya omitido una evaluación. Las decisiones y eventos históricos permanecen
inmutables. La creación de tokens no forma parte de este cambio.

## Implementación y migración

- `app/governance/service.py`: autorización del rol confiable y excepción de Admin.
- `app/governance/models.py`: la restricción decision conserva los campos de decisión;
  la separación de funciones depende del rol y la aplica el trigger.
- `0008_admin_approval`: sustituye la función guard_approval y la restricción decision.
  PostgreSQL permite Admin y exige independencia para Approver. Mantiene hash,
  evaluación aprobada, estados e inmutabilidad; exige motivo para futuras decisiones.
- `app/api/health.py`: exige head 0008_admin_approval.
- Frontend: ayuda contextual y mensajes explican las dos políticas por rol.

No se reescriben ni borran filas durante upgrade. El downgrade restaura la regla
anterior para futuras decisiones y conserva las aprobaciones administrativas
existentes. Su restricción antigua se añade NOT VALID para no invalidar registros
históricos con solicitante=aprobador; sigue comprobándose en escrituras nuevas.
El trigger anterior vuelve a bloquear nuevas autoaprobaciones administrativas.

Antes de usar la política en un despliegue, debe aplicarse:

```sh
python -m alembic -c apps/api/alembic.ini upgrade head
python -m alembic -c apps/api/alembic.ini check
```

Actualiza backend y frontend con esta revisión. El Pre-deploy de Railway ya
configurado ejecuta el primer comando mediante scripts/railway-predeploy.sh.
Este trabajo prepara cambios locales; no ejecuta un despliegue en Railway.

## Probar en la interfaz

1. Usa una candidata congelada con configuración y permisos válidos.
2. Entra como Admin, evalúa el snapshot y solicita aprobación.
3. En Solicitudes e historial de aprobaciones, pulsa Revisar y aprobar.
4. Escribe el motivo. La ayuda indica que Admin puede decidir sobre agentes propios.
5. Pulsa Aprobar: debe pasar a approved. Publicar continúa siendo una acción separada.
6. En auditoría consulta approval.approved: decision_role=administrator y, si el
   Admin era propietario, autor o solicitante, administrator_override=true.
7. Con Approver se mantiene el rechazo de una versión propia.

## Comandos de comprobación

Las pruebas usan esquemas PostgreSQL aislados, sin mocks de autorización. Para
reproducir con PostgreSQL local y dependencias instaladas, configura DATABASE_URL:

```sh
RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_admin_approval.py \
  apps/api/tests/test_governance_api.py -q --tb=short
RUN_DB_TESTS=1 .venv/bin/pytest -q --tb=short
.venv/bin/ruff check apps/api scripts
.venv/bin/ruff format --check apps/api scripts
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

En Docker, con el entorno local del README preparado: make migrate, make up,
make test y make web-check. No habilites autenticación de desarrollo en producción.

## Resultados reales de esta implementación

Entorno: PostgreSQL 17.9 + pgvector en 127.0.0.1:55439, base sintética
bia_lifecycle_tests; FastAPI 18039; Next.js 13039; Chrome/Playwright. No hubo
llamadas a proveedores LLM ni cambios en Railway.

| Comprobación | Resultado |
| --- | --- |
| Gobernanza y política nueva, ejecución focalizada final | 57 PASS en 24.87 s; 19 casos nuevos |
| Suite backend completa | 318 PASS, 1 FAIL en 68.88 s |
| Fallo pendiente del entorno | test_postgres_migration_roundtrip_and_readiness exige PostgreSQL 16; el servidor disponible devuelve 170009 |
| Migración desde esquema limpio, replay, downgrade base y upgrade | PASS en el test CLI de la suite completa |
| Downgrade/upgrade con una autoaprobación administrativa ya registrada | PASS; conserva aprobación y auditoría y vuelve a bloquear nuevas autoaprobaciones durante downgrade |
| Ruff y formato | PASS, 101 archivos Python |
| ESLint, typecheck y build | PASS |
| Unitarias web | 19 PASS |
| Playwright completo | 10 PASS en 21.0 s |

Después de la suite completa se añadieron dos controles SQL de motivo vacío y
hash inmutable, y se repitió el conjunto focalizado de 57 casos. La prueba de
PostgreSQL 16 sigue pendiente de ejecución con ese servidor; no se debilitó ni
omitió su aserción.

Los E2E comprueban que el mismo Admin crea un borrador v2 desde un snapshot,
lo congela, evalúa, solicita, aprueba y publica. Después Creator ejecuta Billing
y Auditor verifica la traza y administrator_override=true. El caso de Approver
independiente conserva administrator_override=false. También pasan RAG, facturas,
acceso entre clientes, herramientas y las demás pantallas.

Comandos ejecutados, con las variables locales de conexión:

```sh
DATABASE_URL=postgresql+psycopg://kennyzhu@127.0.0.1:55439/bia_lifecycle_tests \
  RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_admin_approval.py \
  apps/api/tests/test_governance_api.py -q --tb=short
DATABASE_URL=postgresql+psycopg://kennyzhu@127.0.0.1:55439/bia_lifecycle_tests \
  RUN_DB_TESTS=1 .venv/bin/pytest -q --tb=short
DATABASE_URL=postgresql+psycopg://kennyzhu@127.0.0.1:55439/bia_lifecycle_tests \
  .venv/bin/python -m alembic -c apps/api/alembic.ini upgrade head
DATABASE_URL=postgresql+psycopg://kennyzhu@127.0.0.1:55439/bia_lifecycle_tests \
  .venv/bin/python -m alembic -c apps/api/alembic.ini check
.venv/bin/ruff check apps/api scripts
.venv/bin/ruff format --check apps/api scripts
npm run lint
npm run typecheck
npm test
npm run build
E2E_BASE_URL=http://127.0.0.1:13039 API_PORT=18039 \
  PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

## Archivos modificados

- apps/api/app/governance/service.py y models.py: autorización, auditoría y constraint.
- apps/api/app/api/health.py: nueva revisión esperada.
- apps/api/migrations/versions/0008_admin_approval.py: migración nueva.
- apps/api/tests/test_admin_approval.py y test_governance_api.py: permisos, gates,
  SQL directo, historial y migraciones.
- apps/web/src/app/evaluations/page.tsx y src/lib/help.ts: mensajes de aprobación.
- tests/e2e/governance.spec.ts: autoaprobación Admin y aprobación independiente.
- README.md, docs/architecture.md, docs/decisions/ADR-012-quality-governance.md,
  docs/sprint-4-guide.md, docs/production-demo-bootstrap.md y este documento.

Los cambios quedan preparados localmente, siguiendo la decisión de no desplegar.
No se modifica el sprint ni se añaden servicios, roles, usuarios o credenciales.
