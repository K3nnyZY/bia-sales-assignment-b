"use client";

import { useState, type FormEvent } from "react";
import { ContextHelp } from "./help";
import { Feedback, StudioShell, useResource, useStudio } from "./studio";
import type { CatalogModel, CatalogTool } from "../lib/studio";

const templates = {
  models: {
    id: "synthetic-new-v1",
    name: "Synthetic new",
    provider: "synthetic",
    model_identifier: "synthetic/new-v1",
    release: "demo-1",
    profile: "advanced",
    capabilities: ["chat", "tool_calling"],
    context_window: 16000,
    max_output_tokens: 4000,
    input_cost_per_million: "0",
    output_cost_per_million: "0",
    data_policy: "Synthetic catalog entry; no provider connected.",
    status: "pending",
  },
  tools: {
    id: "synthetic-tool-v1",
    name: "synthetic_tool",
    version: "1.0.0",
    description: "Synthetic contract only; no execution.",
    input_schema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
    output_schema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
    permissions: ["invoices:read"],
    operation: "read",
    timeout_seconds: 5,
    max_retries: 0,
    requires_resource_authorization: true,
    audit_required: true,
    status: "pending",
  },
};

function Catalog({ kind }: { kind: "models" | "tools" }) {
  const { user, api } = useStudio();
  const admin = user?.role === "administrator";
  const items = useResource<(CatalogModel | CatalogTool)[]>(
    `/${kind}${admin ? "?approved_only=false" : ""}`,
  );
  const builtin = useResource<CatalogTool[]>(
    admin && kind === "tools" ? "/tool-templates" : null,
  );
  const [showCreate, setShowCreate] = useState(false);
  const [definition, setDefinition] = useState(
    JSON.stringify(templates[kind], null, 2),
  );
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  async function mutate(
    path: string,
    method: string,
    data?: unknown,
    message = "Catálogo actualizado.",
  ) {
    if (busy) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await api(path, method, data);
      setSuccess(message);
      items.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function create(event: FormEvent) {
    event.preventDefault();
    try {
      const data: unknown = JSON.parse(definition);
      void mutate(`/${kind}`, "POST", data);
    } catch {
      setError("El contrato debe ser JSON válido.");
    }
  }
  return (
    <>
      <section className="intro compact">
        <p className="eyebrow">
          {kind === "models" ? "MODEL REGISTRY" : "TOOL REGISTRY"}
        </p>
        <h1>
          {kind === "models"
            ? "Modelos y perfiles."
            : "Herramientas versionadas."}
        </h1>
        <p>
          {admin
            ? "Administra aprobaciones y registra nuevas definiciones inmutables."
            : "Consulta las capacidades aprobadas por tu organización."}{" "}
          Los registros sintéticos no invocan proveedores ni ejecutan
          herramientas.
        </p>
        <ContextHelp term={kind === "models" ? "Model" : "Tools"} />
        {!admin && kind === "tools" && (
          <p className="hint">
            Para añadir o aprobar herramientas necesitas una sesión con rol
            administrator. El rol se obtiene del backend al iniciar sesión.
          </p>
        )}
        {admin && kind === "tools" && (
          <button
            aria-expanded={showCreate}
            aria-controls="tool-registration"
            onClick={() => setShowCreate((value) => !value)}
          >
            Añadir herramienta
          </button>
        )}
      </section>
      <Feedback error={error || items.error} success={success} />
      {admin && kind === "tools" && showCreate && (
        <section className="panel catalog-create" id="tool-registration">
          <h2>Añadir versión de herramienta</h2>
          <p>
            Registra las herramientas implementadas de Billing o crea un contrato
            nuevo. Las plantillas se añaden como pendientes: debes revisarlas y
            aprobarlas explícitamente antes de seleccionarlas en un agente.
          </p>
          <h3>Herramientas de Billing disponibles</h3>
          <p className="hint">
            Las dos versiones de conocimiento son alternativas. RAG requiere
            documentos aprobados y permisos de colección. Registrar herramientas
            no crea facturas, documentos ni permisos.
          </p>
          <Feedback error={builtin.error} />
          {!builtin.data && !builtin.error && <p role="status">Cargando plantillas…</p>}
          {builtin.error && (
            <button className="secondary" onClick={builtin.refresh}>
              Reintentar plantillas
            </button>
          )}
          {builtin.data?.map((tool) => {
            const registered = items.data?.find((item) => item.id === tool.id);
            return (
              <article className="catalog-item tool-template" key={tool.id}>
                <h4>{tool.description}</h4>
                <p className="technical-id">{tool.name} · v{tool.version} · {tool.id}</p>
                <p className="hint">Permisos requeridos: {tool.permissions.join(", ")}</p>
                <button
                  className="secondary"
                  disabled={busy || !items.data || Boolean(registered)}
                  onClick={() => void mutate(
                    "/tools", "POST", tool,
                    `Herramienta ${tool.name} v${tool.version} registrada como pendiente. Revísala y pulsa Aprobar en el catálogo.`,
                  )}
                >
                  Añadir {tool.name} v{tool.version}
                </button>
                {registered && (
                  <p>Ya registrada · {registered.status}. No se sobrescribe su definición ni su aprobación.</p>
                )}
              </article>
            );
          })}
          <h3>Registro manual de una nueva versión</h3>
          <p className="hint">
            Para cambiar un contrato usa otro identificador y versión. Registrar
            una definición no instala código ni habilita adaptadores inexistentes.
          </p>
          <form onSubmit={create}>
            <label>
              Contrato JSON
              <textarea
                className="json-editor"
                value={definition}
                onChange={(event) => setDefinition(event.target.value)}
                required
                spellCheck={false}
              />
            </label>
            <button disabled={busy}>Registrar en catálogo</button>
          </form>
        </section>
      )}
      <section className="panel">
        <div className="panel-heading">
          <h2>Catálogo {admin ? "completo" : "aprobado"}</h2>
          <button className="secondary" onClick={items.refresh}>
            Actualizar catálogo
          </button>
        </div>
        {!items.data && !items.error && <p role="status">Cargando catálogo…</p>}
        {items.data?.length === 0 && <p>El catálogo está vacío.</p>}
        {items.data?.map((item) => (
          <article className="catalog-item" key={item.id}>
            <div className="panel-heading">
              <div>
                <h3>{item.name}</h3>
                <p>
                  {"profile" in item
                    ? `${item.profile} · ${item.provider} · ${item.model_identifier}`
                    : `v${item.version} · ${item.operation} · ${item.permissions.join(", ")}`}
                </p>
              </div>
              <span className="badge">{item.status}</span>
            </div>
            {"capabilities" in item && (
              <p className="hint">
                {item.capabilities.join(" · ")} · contexto {item.context_window}{" "}
                · salida máxima {item.max_output_tokens}
              </p>
            )}
            <details>
              <summary>Ver contrato de {item.id}</summary>
              <pre>{JSON.stringify(item, null, 2)}</pre>
            </details>
            {admin && (
              <div className="actions">
                {["pending", "approved", "revoked"]
                  .filter((status) => status !== item.status)
                  .map((status) => (
                    <button
                      className="secondary"
                      disabled={busy}
                      key={status}
                      onClick={() =>
                        void mutate(`/${kind}/${item.id}`, "PATCH", { status })
                      }
                    >
                      {status === "approved"
                        ? "Aprobar"
                        : status === "revoked"
                          ? "Revocar"
                          : "Marcar pendiente"}
                    </button>
                  ))}
                <button
                  className="danger"
                  disabled={busy}
                  onClick={() => void mutate(`/${kind}/${item.id}`, "DELETE")}
                >
                  Eliminar {item.id}
                </button>
              </div>
            )}
          </article>
        ))}
      </section>
      {admin && kind === "models" && (
        <section className="panel catalog-create">
          <h2>
            Registrar {kind === "models" ? "modelo" : "versión de herramienta"}
          </h2>
          <p>
            Las definiciones se conservan. Para cambiar un contrato, registra
            una nueva versión con otro identificador.
          </p>
          <form onSubmit={create}>
            <label>
              Contrato JSON
              <textarea
                className="json-editor"
                value={definition}
                onChange={(event) => setDefinition(event.target.value)}
                required
                spellCheck={false}
              />
            </label>
            <button disabled={busy}>Registrar en catálogo</button>
          </form>
        </section>
      )}
    </>
  );
}

export function CatalogPage({ kind }: { kind: "models" | "tools" }) {
  return (
    <StudioShell>
      <Catalog kind={kind} />
    </StudioShell>
  );
}
