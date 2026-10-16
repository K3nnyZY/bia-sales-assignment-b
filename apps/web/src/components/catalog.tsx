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
  const [definition, setDefinition] = useState(
    JSON.stringify(templates[kind], null, 2),
  );
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  async function mutate(path: string, method: string, data?: unknown) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await api(path, method, data);
      setSuccess("Catálogo actualizado.");
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
      </section>
      <Feedback error={error || items.error} success={success} />
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
      {admin && (
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
