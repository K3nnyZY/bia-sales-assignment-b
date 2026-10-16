export const helpCatalog = {
  Agent: "Un agente reúne un propósito, un propietario y configuraciones versionadas. Crear un borrador no lo publica ni permite ejecutarlo automáticamente.",
  Model: "El modelo genera la explicación. Solo puedes seleccionar modelos aprobados con las capacidades y límites necesarios. Un modelo sintético usa respuestas deterministas, sin proveedor LLM.",
  Tools: "Las herramientas consultan recursos mediante contratos aprobados. El backend comprueba los permisos del propietario, del solicitante y del recurso; seleccionarlas no concede permisos.",
  Workflow: "Secuencia de pasos y decisiones que ejecuta el agente. Billing StateGraph consulta facturas mediante herramientas y calcula diferencias con Python.",
  Snapshot: "Copia inmutable de una configuración y sus referencias exactas. Permite evaluar siempre el mismo contenido; no equivale a aprobación ni publicación. Para cambiarla, crea otra versión.",
  Evaluation: "Una suite versionada comprueba comportamiento y seguridad sobre el hash exacto del snapshot. Superar una evaluación no elimina la necesidad de aprobación independiente.",
  Approval: "Decisión registrada por un aprobador autorizado e independiente del propietario, autor y solicitante. No puedes aprobar tu propia candidata.",
  "Publication Gate": "Control del backend que comprueba configuración, dependencias, evaluaciones y aprobación antes de publicar. Un fallo crítico bloquea la publicación.",
  Runtime: "Motor que ejecuta la versión autorizada mediante LangGraph, aplica límites y permisos y persiste el resultado. El modo proveedor puede consumir cuota; el determinista no llama a un LLM.",
  Trace: "Registro persistido de una ejecución: pasos, herramientas, referencias, tiempos y errores. Su consulta está limitada por los permisos del backend.",
} as const;

export type HelpTerm = keyof typeof helpCatalog;

export const errorGuidance: Record<string, string> = {
  UNAUTHENTICATED: "Inicia sesión con un token vigente. Si no tienes acceso, solicita una credencial al administrador.",
  STALE_REVISION: "El recurso cambió. Recarga los datos antes de volver a guardar o eliminar.",
  DELETE_NOT_ALLOWED: "Solo se pueden eliminar agentes en borrador sin historial. Conserva este agente; puedes deshabilitarlo desde Identidad y estado.",
  HISTORY_EXISTS: "Este agente tiene historial que debe conservarse. Deshabilítalo desde Identidad y estado en lugar de eliminarlo.",
  MODEL_NOT_APPROVED: "Selecciona un modelo actualmente aprobado. Si necesitas otro, solicita su revisión a un administrador.",
  TOOL_NOT_APPROVED: "Selecciona únicamente herramientas actualmente aprobadas en el catálogo.",
  TOOL_PERMISSION: "Falta un permiso de herramienta. Solicita al administrador que revise los permisos; la configuración no puede concederlos.",
  MODEL_LIMIT: "Reduce los tokens de salida al límite del modelo seleccionado.",
  MODEL_CAPABILITY: "Selecciona un modelo compatible con todas las capacidades requeridas.",
  CONFIG_HASH_MISMATCH: "Recarga la versión: el hash solicitado no corresponde a la configuración congelada.",
};

export const gateGuidance: Record<string, string> = {
  INVALID_OR_REVOKED_CONFIGURATION: "La configuración no es válida actualmente. Revisa modelo, herramientas, workflow, permisos y referencias de conocimiento. Este código no identifica cuál falló.",
  EVALUATION_REQUIRED: "Ejecuta una suite válida sobre este snapshot antes de continuar.",
  APPROVAL_REQUIRED: "Solicita una aprobación y pide la decisión de un aprobador independiente.",
};
