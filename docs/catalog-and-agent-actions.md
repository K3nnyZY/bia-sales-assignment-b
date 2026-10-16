# Herramientas versionadas y eliminación visible

Fecha: 2026-10-16. Cambios locales; no se ejecutaron comandos en Railway.

## Herramientas

Un administrador ve **Añadir herramienta** al principio de `/tools`. Abre dos
opciones: registrar cada adaptador implementado o introducir un contrato JSON
manual para una nueva versión. El formulario deja claro que registrar una
definición no instala código ejecutable.

Las plantillas se obtienen de `GET /api/v1/tool-templates`, con autenticación y
rol administrator comprobados en backend. Los esquemas se generan desde los
tipos Pydantic de los adaptadores existentes, no se mantienen copias en el frontend.

| ID | Herramienta | Versión |
| --- | --- | --- |
| invoice-lookup-v3 | get_customer_invoice | 3.0.0 |
| invoice-previous-v1 | get_previous_invoice | 1.0.0 |
| billing-knowledge-v1 | search_billing_knowledge (legacy) | 1.0.0 |
| billing-knowledge-v2 | search_billing_knowledge (RAG) | 2.0.0 |

Cada botón registra mediante `POST /api/v1/tools` con estado pending. Después,
**Aprobar** usa el PATCH existente. Leer plantillas no escribe en la base de datos.
Los botones se deshabilitan para IDs registrados y muestran su estado; no restauran
aprobaciones revocadas ni alteran definiciones existentes. Las restricciones de
unicidad y los permisos administrativos del POST siguen vigentes frente a carreras
o peticiones directas.

Las versiones de conocimiento son alternativas. RAG necesita colecciones,
documentos aprobados y grants, además de las facturas transaccionales y permisos
de invocación correspondientes. Registrar el catálogo no crea esos recursos ni
concede permisos de negocio al administrador o a un agente.

## Eliminación

El botón **Eliminar agente** está arriba en el detalle para el propietario creator
o administrador, incluso cuando está bloqueado. La explicación diferencia el estado
del registro lógico del historial de versiones. Un agente publicado puede conservar
`Agent.status=draft`; eso no lo hace eliminable.

Se mantiene la política del backend: estado draft, revisión actual y ausencia de
cualquier versión o auditoría directamente vinculada. El historial de ejecuciones,
aprobaciones y publicación requiere versiones y se conserva mediante FKs RESTRICT.
Los borradores con versiones editables también se conservan. Deshabilitar está
disponible en el formulario existente; no se añade un borrado en cascada.

La carga fallida de modelos/herramientas ya no oculta los metadatos y el botón.
Si no se puede comprobar el historial de versiones, la eliminación queda bloqueada.
El DELETE continúa revalidando todo en el servidor después de la confirmación.

## Archivos

- `apps/api/app/catalogs/templates.py`: contratos de los cuatro adaptadores.
- `apps/api/app/catalogs/routes.py`: lectura administrativa de plantillas.
- `apps/web/src/components/catalog.tsx`: botón visible, altas y registro manual.
- `apps/web/src/app/globals.css`: botones de plantilla adaptados a pantallas pequeñas.
- `apps/web/src/lib/studio.ts`: allowlist del proxy para la nueva ruta.
- `apps/web/src/app/agents/[id]/page.tsx`: acción visible y causas de bloqueo.
- `apps/api/tests/test_management_api.py`, `apps/web/tests/studio.test.ts`,
  `tests/e2e/tools.spec.ts` y `tests/e2e/management.spec.ts`: pruebas de contratos,
  permisos, persistencia, duplicados y controles de interfaz.
- README, arquitectura, guía UX y este informe.

No se añaden dependencias, migraciones ni cambios a las políticas de publicación.

## Verificación ejecutada

Se utilizó PostgreSQL temporal local en 127.0.0.1:55439, Next.js en 13039 y
FastAPI en 18039. Los binarios disponibles son PostgreSQL 17.9 + pgvector;
Docker no estaba disponible. Las credenciales de proveedor permanecieron sin uso.

```sh
DATABASE_URL=postgresql+psycopg://kennyzhu@127.0.0.1:55439/bia_ux_test \
  RUN_DB_TESTS=1 .venv/bin/pytest \
  apps/api/tests/test_management_api.py apps/api/tests/test_audit_history_api.py -q
DATABASE_URL=postgresql+psycopg://kennyzhu@127.0.0.1:55439/bia_ux_test \
  RUN_DB_TESTS=1 .venv/bin/pytest -q
.venv/bin/ruff check apps/api scripts
.venv/bin/ruff format --check apps/api scripts
npm run lint
npm run typecheck
npm test
npm run build
E2E_BASE_URL=http://127.0.0.1:13039 API_PORT=18039 \
  PLAYWRIGHT_CHANNEL=chrome npm run test:e2e -- tests/e2e/tools.spec.ts
E2E_BASE_URL=http://127.0.0.1:13039 API_PORT=18039 \
  PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

| Comprobación | Resultado |
| --- | --- |
| Backend focalizado: permisos, administración y auditoría | 65 PASS |
| Web unitarias, allowlist y clientes | 19 PASS |
| Ruff / formato | PASS, 97 archivos |
| ESLint, typecheck y build | PASS |
| E2E con catálogo sin adaptadores de Billing | 1 PASS; altas reales de las cuatro herramientas |
| E2E completo con datos y catálogos existentes | 9 PASS en 9.2 s, incluida vista de herramientas a 390 px |
| Pytest completo | 285 PASS, 1 FAIL: el roundtrip exige PostgreSQL 16 y el entorno disponible es 17.9 |

La prueba E2E del catálogo se ejecutó primero contra una base nueva llamada
`bia_tools_frontend`, migrada desde cero y con solo el seed de identidades y
catálogos genéricos. Se añadieron los cuatro adaptadores desde el navegador como
pending. También se registraron dos versiones manuales independientes, se aprobó
una y se comprobó que la otra no la modificaba. Después se repitió con el entorno
completo para comprobar el tratamiento de herramientas ya existentes.

## Cómo verlo

1. Despliega los cambios del backend y frontend; la nueva UI necesita la ruta
   de plantillas del backend actualizado. No es necesario cambiar flags de auth.
2. Inicia sesión con un token cuyo rol real en `/api/v1/me` sea administrator.
3. Abre Herramientas → Añadir herramienta. Elige una versión faltante y después
   apruébala explícitamente desde el catálogo si corresponde.
4. Para otra definición, utiliza Registro manual, otro ID y la versión deseada.
5. Abre el detalle de un agente: Eliminar agente está arriba. Si está bloqueado,
   lee la explicación. Un borrador sin versiones permite confirmar y eliminar.

No se verificaron URLs ni se modificaron servicios de Railway. La verificación
del roundtrip específico en PostgreSQL 16 requiere repetir `make verify` con
Docker disponible; no se debilita ni omite esa exigencia.
