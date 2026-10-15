# ADR-010: Agent Management y snapshots locales

Estado: implementado en Sprint 2.

## Contexto

Sprint 1 proporciona Next.js, FastAPI, PostgreSQL 16 y migraciones reproducibles.
Sprint 2 necesita registros administrables y configuraciones versionadas sin
adelantar el runtime ni los controles de publicación de futuros sprints.

## Decisión

- Mantener el monolito modular. Añadir `identity`, `catalogs` y `agents` dentro
  del backend existente, con contratos Pydantic, modelos y rutas separados.
- Usar identidades sintéticas explícitas para desarrollo/test. El backend
  verifica tokens bearer contra hashes SHA-256 almacenados y obtiene el rol y
  los permisos desde PostgreSQL. No acepta identidad, roles ni privilegios de
  cabeceras auxiliares o del manifiesto. El mecanismo está deshabilitado por
  defecto y no se puede habilitar con `APP_ENV=production`.
- Permitir lectura del inventario y sus versiones a identidades activas;
  edición solo al propietario con rol creator o al administrator. Solo el
  administrator administra catálogos y asigna otro propietario. Incluso un
  administrator configura herramientas dentro de los permisos del propietario.
- Representar el estado del agente en este sprint con `draft`, `disabled` y
  `deprecated`. La deprecación es terminal. Publicación y activación ejecutable
  requieren fases posteriores; no se aceptan estados que las aparenten.
- Representar versiones con `draft` y `snapshot`. Un snapshot es un checkpoint
  inmutable de configuración, no una publicación ni una evaluación aprobada.
  Guarda identificador exacto del modelo, release, contratos/versiones de
  herramientas, política efectiva y hash de JSON canónico. No contiene secretos.
- Resolver perfiles al guardar borradores y fijar el ID concreto. Revalidar
  aprobación, capacidades, límites y permisos en edición, clonación y snapshot.
  Una revocación bloquea nuevas configuraciones y snapshots; conserva el
  contenido histórico de los snapshots existentes.
- Mantener definiciones de catálogo inmutables desde su creación; solo cambia
  su aprobación. Las modificaciones de contrato requieren otro registro/version.
  Un índice parcial permite un modelo aprobado por perfil. Se puede administrar
  el estado de modelos y herramientas sin reescribir snapshots históricos.
- Aplicar claves foráneas, unicidad, checks y triggers PostgreSQL. Los triggers
  protegen snapshots y sus enlaces, exigen referencias aprobadas y verifican
  de forma diferida que los enlaces de herramientas coincidan con el JSON.
  El acceso normal de aplicación no puede borrar un agente con historial.
- Usar `expected_revision` y bloqueos por agente para evitar pérdidas de edición
  y números de versión duplicados bajo concurrencia. Las operaciones completas
  se confirman o se revierten en una transacción.
- El manifiesto no tiene un campo para conceder permisos. Su política exige
  autenticación, recursos del solicitante y ausencia de escrituras financieras.
  Las herramientas de escritura pueden catalogarse para demostrar rechazo,
  pero no asignarse a agentes en este sprint.
- Mantener el CSS y el cliente ligero del Sprint 1 para evitar una migración
  visual innecesaria. `AGENTS.md` propone Tailwind/shadcn para la plataforma;
  la base existente usa CSS propio. Se conserva y documenta esta diferencia.
  Los formularios, estados y datos son funcionales y están respaldados por la API.
- Probar los flujos críticos con Playwright. La UI guarda el token introducido
  por el usuario solo en memoria y lo envía por un proxy limitado a rutas de
  gestión. No hay una credencial administrativa incrustada en el frontend.

## Alternativas y consecuencias

SSO corporativo requiere un proveedor y validación propios, fuera de este sprint.
Una cabecera libre con el nombre de usuario o rol permitiría suplantación y se
descarta. El seed no restaura ni sobrescribe aprobaciones, roles, permisos o
tokens existentes; no es un mecanismo de administración de identidades.

Usar solo validaciones ORM no protegería SQL directo; por eso la inmutabilidad
también se aplica en PostgreSQL. Las funciones y triggers están dentro de la
migración y se verifican mediante upgrade/downgrade en esquemas aislados. El
usuario de base de datos de demostración no sustituye la separación de roles
de base de datos y operaciones que requerirá un despliegue real.

No se implementan estados TESTING/PENDING_APPROVAL/PUBLISHED, evaluación,
aprobación, LangGraph, RAG, ejecución, llamadas a proveedores ni acceso a
facturas reales. Los snapshots no deben utilizarse como permiso para ejecutar.
