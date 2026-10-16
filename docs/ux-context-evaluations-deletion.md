# Ayuda contextual, evaluaciones y eliminación segura

Fecha: 2026-10-16. Se conserva el monolito, CSS, proxy autenticado y contratos de
gobernanza existentes. No se ejecutaron operaciones en Railway.

## Comportamiento

- `apps/web/src/lib/help.ts`: glosario de diez conceptos y orientación por códigos
  conocidos. `ContextHelp` utiliza `title` y un disclosure nativo para ratón,
  teclado y pantallas táctiles. No requiere dependencias nuevas.
- `apps/web/src/lib/evaluation-checks.ts`: nombres, propósito y contrato del
  evaluador billing para las nueve pruebas, con fallback para pruebas desconocidas.
- La vista distingue el contrato esperado de `details` recibido del backend.
  Estado de ejecución, llamadas y pasos se muestran con etiquetas comprensibles;
  el JSON original queda en un desplegable secundario.
  No reconstruye importes obtenidos ni atribuye causas a `CHECK_ERROR`.
  Duración y run_id se leen de los resultados persistidos. La traza conserva
  los controles de acceso existentes.
- La clasificación visual usa `passed`; para resultados no aprobados, solo
  `CHECK_ERROR`, `EVALUATION_TIMEOUT` o `details.status=failed` se muestran como
  ERROR. Los demás son FAIL, sin inferir un diagnóstico. No modifica el gate,
  los resultados persistidos ni los controles críticos del backend.
- El DELETE existente exige owner creator/administrator, revisión actual,
  estado draft y ausencia de versiones e historial directamente vinculado.
  Runs, aprobaciones, publicaciones y grants requieren versiones mediante FKs
  RESTRICT. Los eventos desacoplados de metadatos se conservan. Una pestaña
  obsoleta recibe 409 y recarga los datos antes de permitir otro intento.
- El diálogo nativo presenta nombre y advertencia, permite cancelar y bloquea
  botones durante la petición. Tras éxito, navega al inventario que vuelve a
  consultar la API y muestra una notificación descartable en memoria.

No hay archivado nuevo. Deshabilitar mediante el formulario existente conserva
el historial. Un borrador con versión editable tampoco se borra: es una decisión
conservadora que respeta la auditoría y las restricciones vigentes.

## Comandos ejecutados

Docker no estaba disponible. Se inicializó una base aislada y efímera con los
binarios PostgreSQL 17.9 + pgvector ya presentes en el Mac, escuchando únicamente
en localhost. No se utilizaron datos ni credenciales de producción.

```sh
/private/tmp/autism-insight-pgembed/pgembed/pginstall/bin/initdb \
  -D /private/tmp/bia-ux-postgres --auth=trust --no-locale -E UTF8
/private/tmp/autism-insight-pgembed/pgembed/pginstall/bin/pg_ctl \
  -D /private/tmp/bia-ux-postgres -l /private/tmp/bia-ux-postgres.log \
  -o '-h 127.0.0.1 -p 55439 -k /private/tmp' start

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
  PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

Para E2E se aplicó `alembic upgrade head` y los cuatro seeds existentes **solo en
la base temporal**, con APP_ENV=test, autenticación demo explícita, proveedor
deshabilitado y los tokens locales leídos sin imprimirlos. FastAPI se inició en
127.0.0.1:18039 y Next.js en 127.0.0.1:13039 usando BACKEND_URL local.

## Resultados

| Comprobación | Resultado |
| --- | --- |
| Gestión y auditoría focalizadas | 63 PASS |
| Pytest completo en PostgreSQL 17.9 | 283 PASS, 1 FAIL |
| Fallo pendiente | El roundtrip exige PostgreSQL 16; recibió server_version_num=170009 |
| Ruff y formato | PASS, 96 archivos |
| ESLint, typecheck, build | PASS |
| Pruebas web | 19 PASS |
| Playwright final | 8 PASS en 8.2 s |

El fallo de versión de PostgreSQL no se omitió ni se alteró la prueba. Las
migraciones se aplicaron a esquemas limpios en las pruebas de integración,
pero el roundtrip específico sobre PostgreSQL 16 queda pendiente. Los primeros
E2E detectaron selectores ambiguos en la prueba nueva y una dependencia previa
del Dashboard de runs preexistentes; se corrigieron los selectores y el fixture
para que cada prueba cree sus propios datos.

El E2E nuevo comprobó confirmación/cancelación, botón oculto para viewer,
rechazo por revisión obsoleta, persistencia después del rechazo, presentación
en 390 px, eliminación confirmada, notificación e inventario actualizado.
El flujo de gobernanza comprobó los textos comprensibles del resultado y los
datos técnicos recibidos del backend, además de sus trazas reales.

## Verificación desde Mac

Con Docker disponible y el entorno local preparado según README:

```sh
make verify
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

1. Inicia sesión como creator y crea un agente sin configuración. Abre la ayuda.
2. Pulsa Eliminar agente: comprueba el nombre, cancela y verifica que continúa.
3. Confirma la eliminación y comprueba notificación y ausencia en el inventario.
4. Guarda una versión de otro agente: el botón queda deshabilitado y se explica cómo
   conservar su historial deshabilitándolo. El DELETE directo debe devolver 409.
5. En Evaluaciones ejecuta la suite sobre un snapshot autorizado. Expande una
   prueba para ver su contrato, observaciones reales, error y traza disponible.
6. Comprueba que un viewer u otro creator no puede eliminar el agente ajeno.

No se verificó ni modificó el despliegue remoto. La ayuda no provisiona suites,
modelos, herramientas, identidades ni permisos faltantes en producción.

## Archivos modificados

- Backend: `apps/api/app/agents/routes.py`.
- Pruebas backend: `apps/api/tests/test_management_api.py`,
  `apps/api/tests/test_governance_api.py`.
- Ayuda y resultados: `apps/web/src/lib/help.ts`,
  `apps/web/src/lib/evaluation-checks.ts`, `apps/web/src/lib/studio.ts`,
  `apps/web/src/lib/governance.ts`.
- Componentes: `apps/web/src/components/help.tsx`,
  `apps/web/src/components/delete-agent-dialog.tsx`,
  `apps/web/src/components/studio.tsx`, `apps/web/src/components/catalog.tsx`.
- Páginas: `apps/web/src/app/agents/page.tsx`,
  `apps/web/src/app/agents/[id]/page.tsx`,
  `apps/web/src/app/evaluations/page.tsx`,
  `apps/web/src/app/playground/page.tsx`, `apps/web/src/app/traces/page.tsx`.
- Estilo: `apps/web/src/app/globals.css`.
- Pruebas frontend: `apps/web/tests/studio.test.ts`,
  `apps/web/tests/evaluation-checks.test.ts`.
- E2E: `tests/e2e/agent-deletion.spec.ts`, `tests/e2e/management.spec.ts`,
  `tests/e2e/governance.spec.ts`, `tests/e2e/dashboard.spec.ts`.
- Documentación: `README.md`, `docs/decisions/ADR-010-agent-management.md`
  y este informe.
