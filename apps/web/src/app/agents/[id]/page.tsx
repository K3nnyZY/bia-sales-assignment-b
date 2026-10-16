"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import {
  Feedback,
  StudioShell,
  useResource,
  useStudio,
} from "../../../components/studio";
import type {
  Agent,
  AgentVersion,
  CatalogModel,
  CatalogTool,
  Configuration,
  Principal,
} from "../../../lib/studio";

function MetadataForm({
  agent,
  refresh,
}: {
  agent: Agent;
  refresh: () => void;
}) {
  const { api, user } = useStudio();
  const owners = useResource<Principal[]>(
    user?.role === "administrator" ? "/users" : null,
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const editable =
    user?.role === "administrator" ||
    (user?.role === "creator" && user.id === agent.owner_id);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await api(`/agents/${agent.id}`, "PATCH", {
        expected_revision: agent.revision,
        name: form.get("name"),
        description: form.get("description"),
        department: form.get("department"),
        owner_id: form.get("owner_id") || agent.owner_id,
        status: form.get("status"),
      });
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>Identidad y estado</h2>
      <p className="hint">
        Propietario: {agent.owner_id} · revisión {agent.revision}
      </p>
      <form onSubmit={save}>
        <fieldset disabled={!editable || busy}>
          <label>
            Nombre del agente
            <input
              name="name"
              defaultValue={agent.name}
              required
              maxLength={120}
            />
          </label>
          <label>
            Descripción
            <textarea
              name="description"
              defaultValue={agent.description}
              maxLength={4000}
            />
          </label>
          <label>
            Departamento
            <input
              name="department"
              defaultValue={agent.department}
              required
              maxLength={120}
            />
          </label>
          {user?.role === "administrator" && (
            <label>
              Propietario
              <select name="owner_id" defaultValue={agent.owner_id}>
                {owners.data
                  ?.filter(
                    (owner) =>
                      owner.active &&
                      ["creator", "administrator"].includes(owner.role),
                  )
                  .map((owner) => (
                    <option key={owner.id} value={owner.id}>
                      {owner.name}
                    </option>
                  )) || (
                  <option value={agent.owner_id}>{agent.owner_id}</option>
                )}
              </select>
            </label>
          )}
          <label>
            Estado del agente
            <select name="status" defaultValue={agent.status}>
              <option value="draft">Borrador</option>
              <option value="disabled">Deshabilitado</option>
              <option value="deprecated">Deprecado</option>
            </select>
          </label>
          {editable && <button>Guardar identidad</button>}
        </fieldset>
      </form>
      <Feedback error={error || owners.error} />
    </section>
  );
}

function ConfigurationForm({
  agent,
  version,
  models,
  tools,
  refresh,
}: {
  agent: Agent;
  version: AgentVersion | null;
  models: CatalogModel[];
  tools: CatalogTool[];
  refresh: () => void;
}) {
  const { api, user } = useStudio();
  const initial = version?.configuration;
  const [objective, setObjective] = useState(initial?.objective || "");
  const [instructions, setInstructions] = useState(initial?.instructions || "");
  const [modelId, setModelId] = useState(
    initial?.model.model_id || models[0]?.id || "",
  );
  const [billingWorkflow, setBillingWorkflow] = useState(
    Boolean(initial?.workflow),
  );
  const [knowledgeText, setKnowledgeText] = useState(
    initial?.knowledge ? JSON.stringify(initial.knowledge, null, 2) : "",
  );
  const [toolIds, setToolIds] = useState(initial?.tool_ids || []);
  const [capabilities, setCapabilities] = useState(
    initial?.required_capabilities || ["chat"],
  );
  const [output, setOutput] = useState(
    initial?.model.max_output_tokens || 1000,
  );
  const [steps, setSteps] = useState(initial?.limits.max_steps || 6);
  const [calls, setCalls] = useState(initial?.limits.max_tool_calls ?? 5);
  const [timeout, setTimeout] = useState(initial?.limits.timeout_seconds || 30);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const canEdit =
    agent.status === "draft" &&
    (user?.role === "administrator" ||
      (user?.role === "creator" && user.id === agent.owner_id));
  const frozen = version?.status === "snapshot";
  const configuration: Configuration = {
    api_version: "bia.ai/v1",
    kind: "AgentConfiguration",
    objective,
    instructions,
    ...(billingWorkflow
      ? {
          workflow: {
            id: "billing_workflow_v1" as const,
            version: "1.0.0" as const,
          },
        }
      : {}),
    model: { model_id: modelId, max_output_tokens: output },
    tool_ids: [...toolIds].sort(),
    required_capabilities: capabilities,
    limits: {
      max_steps: steps,
      max_tool_calls: calls,
      timeout_seconds: timeout,
    },
    security: {
      require_authentication: true,
      resource_scope: "caller_owned",
      allow_financial_writes: false,
    },
  };
  async function mutate(path: string, method: string, body: unknown) {
    setBusy(true);
    setError("");
    try {
      await api(path, method, body);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function save(event: FormEvent) {
    event.preventDefault();
    let selectedKnowledge: unknown;
    try {
      selectedKnowledge = knowledgeText.trim()
        ? JSON.parse(knowledgeText)
        : undefined;
    } catch {
      setError("Las referencias de conocimiento deben ser JSON válido.");
      return;
    }
    const configured = {
      ...configuration,
      ...(selectedKnowledge ? { knowledge: selectedKnowledge } : {}),
    };
    void mutate(
      `/agents/${agent.id}/versions${version ? `/${version.number}` : ""}`,
      version ? "PUT" : "POST",
      version
        ? { expected_revision: version.revision, configuration: configured }
        : { configuration: configured },
    );
  }
  function toggle(
    value: string,
    values: string[],
    setter: (value: string[]) => void,
  ) {
    setter(
      values.includes(value)
        ? values.filter((item) => item !== value)
        : [...values, value],
    );
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>
            {version
              ? `Versión ${version.number} · ${version.status}`
              : "Primera configuración"}
          </h2>
          <p>
            {version
              ? `Revisión ${version.revision}${version.source_version ? ` · derivada de v${version.source_version}` : ""}`
              : "Selecciona capacidades de los catálogos aprobados."}
          </p>
        </div>
      </div>
      {frozen && (
        <p className="notice">
          Snapshot inmutable. Consulta su evaluación y publicación en el
          Evaluation Center. Crea una nueva versión para realizar cambios.
        </p>
      )}
      <form onSubmit={save} onChange={() => setDirty(true)}>
        <fieldset disabled={!canEdit || frozen || busy}>
          <label>
            Objetivo
            <textarea
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              required
              maxLength={4000}
            />
          </label>
          <label>
            Instrucciones
            <textarea
              className="instructions"
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              required
              maxLength={12000}
            />
          </label>
          <label>
            Workflow
            <select
              aria-label="Workflow"
              value={billingWorkflow ? "billing" : "none"}
              onChange={(e) => setBillingWorkflow(e.target.value === "billing")}
            >
              <option value="none">Sin runtime</option>
              <option value="billing">Billing StateGraph · v1.0.0</option>
            </select>
          </label>
          <p className="hint">
            Billing requiere get_customer_invoice v3, get_previous_invoice v1,
            search_billing_knowledge v1 (legacy) o v2 (RAG con documentos
            fijados), al menos 9 pasos y 3 llamadas.
          </p>
          <label>
            Documentos de conocimiento (JSON opcional)
            <textarea
              aria-label="Referencias de conocimiento"
              value={knowledgeText}
              onChange={(e) => setKnowledgeText(e.target.value)}
              placeholder={
                '{"documents":[{"document_id":"billing-faq-rag","version":1}]}'
              }
            />
          </label>
          <p className="hint">
            Selecciona versiones aprobadas desde Conocimiento. RAG requiere
            billing-knowledge-v2 y excluye v1. El backend verifica los grants
            del propietario; este JSON no concede permisos.
          </p>
          <label>
            Modelo aprobado
            <select
              value={modelId}
              onChange={(event) => setModelId(event.target.value)}
              required
            >
              <option value="">Selecciona un modelo</option>
              {!models.some((model) => model.id === modelId) && modelId && (
                <option value={modelId}>
                  {modelId} · no aprobado actualmente
                </option>
              )}
              {models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name} · {model.profile}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="choices">
            <legend>Capacidades requeridas</legend>
            {["chat", "tool_calling", "structured_output", "vision"].map(
              (capability) => (
                <label key={capability}>
                  <input
                    type="checkbox"
                    checked={capabilities.includes(capability)}
                    onChange={() =>
                      toggle(capability, capabilities, setCapabilities)
                    }
                  />
                  {capability}
                </label>
              ),
            )}
          </fieldset>
          <fieldset className="choices">
            <legend>Herramientas aprobadas</legend>
            {tools
              .filter((tool) => tool.operation === "read")
              .map((tool) => (
                <label key={tool.id}>
                  <input
                    type="checkbox"
                    checked={toolIds.includes(tool.id)}
                    onChange={() => toggle(tool.id, toolIds, setToolIds)}
                  />
                  <span>
                    {tool.name} · v{tool.version}
                    <small>
                      {tool.permissions.join(", ") ||
                        "Sin permisos adicionales"}
                    </small>
                  </span>
                </label>
              ))}
            {toolIds
              .filter((id) => !tools.some((tool) => tool.id === id))
              .map((id) => (
                <label key={id}>
                  <input
                    type="checkbox"
                    checked
                    onChange={() =>
                      setToolIds(toolIds.filter((value) => value !== id))
                    }
                  />
                  {id} · no aprobada actualmente
                </label>
              ))}
          </fieldset>
          <div className="form-grid">
            <label>
              Máximo de tokens de salida
              <input
                type="number"
                min={1}
                max={1000000}
                required
                value={output}
                onChange={(event) => setOutput(Number(event.target.value))}
              />
            </label>
            <label>
              Máximo de pasos
              <input
                type="number"
                min={1}
                max={50}
                required
                value={steps}
                onChange={(event) => setSteps(Number(event.target.value))}
              />
            </label>
            <label>
              Máximo de llamadas a herramientas
              <input
                type="number"
                min={0}
                max={20}
                required
                value={calls}
                onChange={(event) => setCalls(Number(event.target.value))}
              />
            </label>
            <label>
              Tiempo máximo (segundos)
              <input
                type="number"
                min={1}
                max={120}
                required
                value={timeout}
                onChange={(event) => setTimeout(Number(event.target.value))}
              />
            </label>
          </div>
          <p className="hint">
            Autenticación obligatoria · recursos del solicitante · sin
            escrituras financieras. Los permisos se derivan en el servidor.
          </p>
          {canEdit && !frozen && (
            <button disabled={busy || !modelId}>
              {busy
                ? "Guardando…"
                : version
                  ? "Guardar borrador"
                  : "Crear primera versión"}
            </button>
          )}
        </fieldset>
      </form>
      {canEdit && version && (
        <div className="actions">
          {!frozen && (
            <button
              disabled={busy || dirty}
              onClick={() =>
                void mutate(
                  `/agents/${agent.id}/versions/${version.number}/snapshot`,
                  "POST",
                  { expected_revision: version.revision },
                )
              }
            >
              Crear snapshot
            </button>
          )}
          <button
            className="secondary"
            disabled={busy || dirty}
            onClick={() =>
              void mutate(`/agents/${agent.id}/versions`, "POST", {
                source_version: version.number,
                expected_source_revision: version.revision,
              })
            }
          >
            Nueva versión desde esta
          </button>
          {dirty && (
            <p className="hint">
              Guarda los cambios antes de crear un snapshot o una nueva versión.
            </p>
          )}
        </div>
      )}
      <Feedback error={error} />
      {version?.config_hash && (
        <p className="hash">SHA-256: {version.config_hash}</p>
      )}
      <details>
        <summary>Configuración declarativa</summary>
        <pre>{JSON.stringify(configuration, null, 2)}</pre>
      </details>
      {version?.snapshot && (
        <details>
          <summary>Snapshot efectivo guardado</summary>
          <pre>{JSON.stringify(version.snapshot, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}

function AgentDetail() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const { api, user } = useStudio();
  const agent = useResource<Agent>(`/agents/${id}`);
  const versions = useResource<AgentVersion[]>(`/agents/${id}/versions`);
  const models = useResource<CatalogModel[]>("/models");
  const tools = useResource<CatalogTool[]>("/tools");
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const current =
    versions.data?.find((version) => version.number === selected) ||
    versions.data?.[0] ||
    null;
  const editable =
    user?.role === "administrator" ||
    (user?.role === "creator" && user.id === agent.data?.owner_id);
  function refreshVersions() {
    setSuccess("Versión guardada correctamente.");
    setSelected(null);
    versions.refresh();
  }
  async function remove() {
    if (!agent.data) return;
    setBusy(true);
    setError("");
    try {
      await api(
        `/agents/${id}?expected_revision=${agent.data.revision}`,
        "DELETE",
      );
      router.push("/agents");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const loadError =
    agent.error || versions.error || models.error || tools.error;
  return (
    <>
      <section className="intro compact">
        <Link href="/agents">← Inventario de agentes</Link>
        <h1>{agent.data?.name || "Detalle del agente"}</h1>
        <Link href="/evaluations">Evaluaciones y publicación</Link>
        <p>{id}</p>
      </section>
      <Feedback error={loadError || error} success={success} />
      {loadError && (
        <button
          className="secondary"
          onClick={() => {
            agent.refresh();
            versions.refresh();
            models.refresh();
            tools.refresh();
          }}
        >
          Reintentar carga
        </button>
      )}
      {agent.data && versions.data && models.data && tools.data ? (
        <div className="workspace detail">
          <aside>
            <MetadataForm
              key={agent.data.revision}
              agent={agent.data}
              refresh={() => {
                setSuccess("Identidad guardada correctamente.");
                agent.refresh();
              }}
            />
            <section className="panel versions">
              <h2>Historial de versiones</h2>
              {versions.data.length === 0 && <p>Aún no hay versiones.</p>}
              {versions.data.map((version) => (
                <button
                  className={`version-button ${current?.number === version.number ? "selected" : ""}`}
                  key={version.number}
                  onClick={() => setSelected(version.number)}
                >
                  v{version.number} · {version.status}
                </button>
              ))}
              {editable && versions.data.length === 0 && (
                <button
                  className="danger"
                  disabled={busy}
                  onClick={() => void remove()}
                >
                  Eliminar agente sin historial
                </button>
              )}
            </section>
          </aside>
          <ConfigurationForm
            key={`${current?.number || 0}:${current?.revision || 0}:${agent.data.revision}`}
            agent={agent.data}
            version={current}
            models={models.data}
            tools={tools.data}
            refresh={refreshVersions}
          />
        </div>
      ) : (
        !loadError && <p role="status">Cargando configuración…</p>
      )}
    </>
  );
}

export default function AgentDetailPage() {
  return (
    <StudioShell>
      <AgentDetail />
    </StudioShell>
  );
}
