# Verificación del bootstrap sintético

Fecha: 2026-10-16. Resultados **locales**, con PostgreSQL 16/pgvector reales.
No se modificó ni verificó el servicio remoto de Railway en esta tarea.

| Comando / prueba ejecutada | Resultado |
| --- | --- |
| `RUN_DB_TESTS=1 .venv/bin/pytest -q` | **280 PASS**, 74,84 s; unitarias, integración, seguridad y regresión de los Sprints existentes. |
| `RUN_DB_TESTS=1 .venv/bin/pytest apps/api/tests/test_bootstrap.py apps/api/tests/test_deployment.py -q -x` | **21 PASS**, 7,70 s; bootstrap y flujo protegido completo, con autorización real y PostgreSQL. |
| `.venv/bin/ruff check apps/api scripts` | **PASS**. |
| `.venv/bin/ruff format --check apps/api scripts` | **PASS**, 96 archivos. |
| `docker compose up --build --wait --wait-timeout 180` | **PASS**; Alembic terminó, PostgreSQL/API/web saludables. |
| `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | **7 PASS**, 10,1 s; Builder, publicación independiente, LangGraph, facturación, Knowledge/RAG y trazas en la interfaz local. |
| `node_modules/.bin/tsc --noEmit --skipLibCheck --target es2022 --module nodenext --moduleResolution nodenext infra/railway/railway.ts` | **PASS**; se retiró el manifiesto del aprovisionamiento automático. |
| `git diff --check` | **PASS**. |
| Smoke CLI desde base temporal vacía, `APP_ENV=production` | **8 comandos con exit 0**: generar acceso, migrar, provisionar, cargar, repetir carga, consultar estado, revocar y consultar estado. |
| Comandos SSH, URLs y datos en Railway | **NOT VERIFIED**; los ejecuta el operador siguiendo la guía. |

El smoke CLI se ejecutó con
`PYTHONPATH=apps/api .venv/bin/python /tmp/bia-bootstrap-cli-smoke.py`. El script
creó una base PostgreSQL local con nombre aleatorio, ejecutó los comandos reales
como procesos independientes y eliminó únicamente esa base y las credenciales
temporales al terminar. La evidencia persistida, sin secretos y con rutas
sustituidas, está en [bootstrap-verification.json](bootstrap-verification.json).
Los mismos entrypoints y pasos están en la [guía reproducible](production-demo-bootstrap.md).

El estado consultado en PostgreSQL confirmó ocho facturas sintéticas, cuatro
modelos, nueve herramientas, un snapshot, una suite, dos documentos listos y
aprobados, dos vectores reales de 256 dimensiones con modelo identificado y cero
evaluaciones ejecutadas artificialmente. Las siete credenciales inicialmente
válidas pasaron a cero tras `revoke-access`; los documentos permanecieron iguales.

## Controles verificados

- Los cuatro entrypoints antiguos siguen rechazando producción. Los flags
  `ENABLE_DEMO_AUTH` y `ENABLE_LOCAL_RUNTIME` permanecen deshabilitados.
- Los datos no crean/modifican identidades ni tokens y no crean grants.
- El manifiesto declara privilegios explícitos; rechaza roles/permisos mayores,
  duplicados y la toma de control de un usuario existente.
- Los tokens son aleatorios, privados, expiran y admiten revocación. Los errores
  de un manifiesto incorrecto no imprimen credenciales en texto plano.
- Replay conserva todos los registros mediante hashes de filas de todas las
  tablas, incluidos cambios de operador, desactivación y revocaciones.
- Se preservan catálogos y usuarios preexistentes; las colisiones reservadas
  fallan sin sobrescribir agente, facturas o colección.
- El fallo del segundo embedding revierte también el primer documento, catálogo,
  agente y facturas. Las identidades previas se conservan.
- Dos cargas concurrentes producen una inicialización y una repetición sin cambios.
- Sin grant, ni siquiera el propietario recupera documentos.
- Después de grants administrativos explícitos, el flujo protegido evalúa nueve
  controles, exige aprobación independiente, publica y ejecuta LangGraph con
  facturas/cálculos/RAG. Otro cliente recibe denegación sin evidencia.
- La revocación alcanza tokens rotados, conserva usuarios ajenos e historial y
  no se deshace con replay del manifiesto o la carga.

Durante la preparación, un fixture intentó editar el nombre de un modelo ya
inmutable: PostgreSQL lo rechazó correctamente. Se cambió el fixture para probar
una transición de aprobación permitida; no se alteraron los constraints.
La suite completa posterior pasó sin fallos.

## Archivos modificados

- Los cuatro módulos de seed: `app/seed.py`, `runtime/seed.py`,
  `governance/seed.py` y `knowledge/seed.py`, separando funciones de datos.
- `app/deployment/bootstrap.py`: CLI explícita, provisión, carga, estado y revocación.
- `scripts/railway_credentials.py`: manifiesto de permisos y `--access-only`.
- `scripts/railway-predeploy.sh` e `infra/railway/railway.ts`: sin bootstrap automático.
- `test_deployment.py`, `test_bootstrap.py`, `test_bootstrap_unit.py`.
- README, arquitectura, ADR-014 y guías/evidencia de bootstrap/despliegue.

No se agregaron migraciones, servicios, dependencias, endpoints ni cambios en
los cálculos, el grafo, el gateway o las políticas de publicación del agente.

## Límites

Los IDs y fechas del dataset son fijos. No se adopta una carga anterior sin
recibo ni se reparan recursos en conflicto. Una demo RAG requiere grants
administrativos explícitos y una versión nueva creada/evaluada/publicada por el
flujo existente. La carga solo crea la suite; no fabrica resultados o aprobaciones.
SSO/MFA y endurecimiento empresarial siguen pendientes. No se avanzó a otro sprint.
