"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import {
  Feedback,
  StudioShell,
  useResource,
  useStudio,
} from "../../components/studio";
import { KnowledgeTraceView } from "../../components/trace";
import type { ExecutableVersion, RunResult, RunTrace } from "../../lib/runtime";

function Playground() {
  const { api, user } = useStudio();
  const options = useResource<ExecutableVersion[]>("/runtime/agents");
  const history = useResource<RunResult[]>("/runs?limit=20");
  const [versionKey, setVersionKey] = useState("");
  const [mode, setMode] = useState<"deterministic" | "provider">(
    "deterministic",
  );
  const [channel, setChannel] = useState<"preview" | "published">("preview");
  const [task, setTask] = useState("auto");
  const [invoiceId, setInvoiceId] = useState(
    user?.id === "demo-customer-b" ? "INV-2002" : "INV-1002",
  );
  const [period, setPeriod] = useState("2026-09");
  const [message, setMessage] = useState(
    "¿Por qué cambió mi factura respecto al período anterior?",
  );
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const trace = useResource<RunTrace>(runId ? `/runs/${runId}/trace` : null);
  const selected =
    options.data?.find(
      (item) => `${item.agent_id}@${item.version}` === versionKey,
    ) || options.data?.[0];
  const chosenMode = selected?.available_modes.includes(mode)
    ? mode
    : selected?.available_modes[0];
  const chosenChannel = selected?.local_preview ? channel : "published";
  const result = trace.data?.run;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected || !chosenMode || busy) return;
    setBusy(true);
    setError("");
    try {
      const run = await api<RunResult>("/runs", "POST", {
        agent_id: selected.agent_id,
        version: selected.version,
        channel: chosenChannel,
        mode: chosenMode,
        message,
        task,
        invoice_id: task === "knowledge" || !invoiceId ? null : invoiceId,
        period: `${period}-01`,
      });
      setRunId(run.id);
      history.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="intro compact">
        <p className="eyebrow">AGENT RUNTIME</p>
        <h1>Playground de facturación.</h1>
        <p>
          Ejecuta una versión congelada con acceso explícito y consulta su
          respuesta y traza reales.
        </p>
        <p className="notice">
          Datos sintéticos. Preview local prueba snapshots con grants
          explícitos; Published exige una publicación aprobada y vigente.
        </p>
      </section>
      <Feedback
        error={error || options.error || history.error || trace.error}
      />
      <div className="workspace detail">
        <aside>
          <section className="panel">
            <h2>Nueva ejecución</h2>
            {!options.data && !options.error && (
              <p role="status">Cargando versiones autorizadas…</p>
            )}
            {options.data?.length === 0 && (
              <p>
                No tienes versiones habilitadas. Solicita el permiso de
                invocación a un administrador.
              </p>
            )}
            <form onSubmit={submit}>
              <fieldset disabled={busy || !selected}>
                <label>
                  Versión del agente
                  <select
                    value={
                      selected ? `${selected.agent_id}@${selected.version}` : ""
                    }
                    onChange={(event) => setVersionKey(event.target.value)}
                    required
                  >
                    {options.data?.map((item) => (
                      <option
                        key={`${item.agent_id}@${item.version}`}
                        value={`${item.agent_id}@${item.version}`}
                      >
                        {item.name} · v{item.version} · {item.model_id}
                        {item.published ? " · PUBLISHED" : " · PREVIEW"}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Canal de ejecución
                  <select
                    value={chosenChannel}
                    onChange={(e) =>
                      setChannel(e.target.value as "preview" | "published")
                    }
                  >
                    {selected?.local_preview && (
                      <option value="preview">Preview · prueba local</option>
                    )}
                    <option value="published" disabled={!selected?.published}>
                      Published · versión aprobada
                    </option>
                  </select>
                </label>
                <label>
                  Modo de ejecución
                  <select
                    value={chosenMode || ""}
                    onChange={(event) =>
                      setMode(
                        event.target.value as "deterministic" | "provider",
                      )
                    }
                    required
                  >
                    {!chosenMode && (
                      <option value="">Proveedor no configurado</option>
                    )}
                    {selected?.available_modes.map((value) => (
                      <option key={value} value={value}>
                        {value === "deterministic"
                          ? "Determinista · sin proveedor"
                          : "Proveedor · LiteLLM"}
                      </option>
                    ))}
                  </select>
                </label>
                {chosenMode && (
                  <p className="hint">
                    {chosenMode === "deterministic"
                      ? "Plantilla de prueba calculada desde las facturas; sin llamada a un LLM."
                      : "El proveedor solo ordena afirmaciones y referencias verificadas; no redacta libremente ni calcula importes."}
                  </p>
                )}
                <label>
                  Consulta
                  <select
                    value={task}
                    onChange={(event) => setTask(event.target.value)}
                  >
                    <option value="auto">Automática</option>
                    <option value="compare">
                      Comparar con el mes anterior
                    </option>
                    <option value="invoice">Consultar factura</option>
                    <option value="knowledge">Tarifas y FAQ</option>
                  </select>
                </label>
                <label>
                  Factura
                  <input
                    value={invoiceId}
                    onChange={(event) => setInvoiceId(event.target.value)}
                    disabled={task === "knowledge"}
                    placeholder="INV-1002"
                    pattern="INV-[0-9]{4,12}"
                  />
                </label>
                <label>
                  Período de tarifas/FAQ
                  <input
                    type="month"
                    value={period}
                    onChange={(event) => setPeriod(event.target.value)}
                    required
                  />
                </label>
                <label>
                  Mensaje
                  <textarea
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    required
                    maxLength={4000}
                  />
                </label>
                <button disabled={busy || !chosenMode}>
                  {busy ? "Ejecutando…" : "Ejecutar agente"}
                </button>
              </fieldset>
            </form>
            <p className="hint">
              La identidad proviene de tu sesión autenticada. El mensaje no
              cambia permisos ni acceso a facturas.
            </p>
            <button
              className="secondary"
              onClick={options.refresh}
              disabled={busy}
            >
              Actualizar versiones
            </button>
          </section>
          <section className="panel versions">
            <h2>Mis ejecuciones</h2>
            {history.data?.length === 0 && <p>Aún no hay ejecuciones.</p>}
            {history.data?.map((run) => (
              <button
                className={`version-button ${run.id === runId ? "selected" : ""}`}
                key={run.id}
                onClick={() => setRunId(run.id)}
              >
                <span>{run.id}</span>
                <small>
                  v{run.version_number} · {run.mode} · {run.status}
                </small>
              </button>
            ))}
            <button className="secondary" onClick={history.refresh}>
              Actualizar historial
            </button>
          </section>
        </aside>
        <section className="panel">
          <h2>Resultado y traza</h2>
          {!runId && (
            <p>Ejecuta el agente o selecciona una ejecución guardada.</p>
          )}
          {runId && !trace.data && !trace.error && (
            <p role="status">Cargando la ejecución persistida…</p>
          )}
          {result && (
            <>
              <div className="actions">
                <span className="badge" data-testid="run-status">
                  {result.status}
                </span>
                <span className="badge">{result.mode}</span>
                <span className="badge">{result.channel}</span>
                <Link href={`/traces?run=${result.id}`}>
                  Abrir Trace Viewer
                </Link>
              </div>
              <p className="hash">
                Run: {result.id}
                <br />
                Snapshot: {result.config_hash}
                <br />
                Workflow: {result.workflow_version}
              </p>
              {result.error_code && (
                <p className="error" role="alert">
                  {result.error_code}
                </p>
              )}
              <h3>Respuesta</h3>
              <p className="runtime-answer">{result.answer}</p>
              <p className="hint">
                Tokens de entrada: {result.input_tokens ?? "No reportados"} ·
                salida: {result.output_tokens ?? "No reportados"}
                <br />
                Coste estimado según catálogo (USD):{" "}
                {result.estimated_cost_usd ?? "No disponible"}
              </p>
              {Object.keys(result.calculations).length > 0 && (
                <details>
                  <summary>Cálculos deterministas en Python</summary>
                  <pre>{JSON.stringify(result.calculations, null, 2)}</pre>
                </details>
              )}
              <p className="hint">
                Referencias:{" "}
                {result.references.join(", ") || "Sin evidencia liberada"}
              </p>
              <KnowledgeTraceView
                searches={trace.data?.knowledge_searches || []}
              />
              <h3 className="trace-heading">Nodos del StateGraph</h3>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Paso</th>
                      <th>Nodo</th>
                      <th>Estado</th>
                      <th>Duración real</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trace.data?.events.map((event, index) => (
                      <tr key={`${event.node}:${index}`}>
                        <td>{event.step}</td>
                        <td>{event.node}</td>
                        <td>
                          {event.status}
                          {event.error_code ? ` · ${event.error_code}` : ""}
                        </td>
                        <td>{event.duration_ms} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3 className="trace-heading">Llamadas a herramientas</h3>
              {trace.data?.tool_calls.map((call) => (
                <article className="catalog-item" key={call.id}>
                  <h3>
                    {call.tool_id} · v{call.tool_version}
                  </h3>
                  <p className="hint">
                    {call.status} · intento {call.attempt} · {call.duration_ms}{" "}
                    ms{call.error_code ? ` · ${call.error_code}` : ""}
                  </p>
                  <pre>
                    {JSON.stringify(
                      {
                        arguments: call.arguments,
                        references: call.result_references,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </article>
              ))}
              {trace.data?.tool_calls.length === 0 && (
                <p>No se realizaron llamadas a herramientas.</p>
              )}
            </>
          )}
          {trace.error && (
            <button className="secondary" onClick={trace.refresh}>
              Reintentar carga de traza
            </button>
          )}
        </section>
      </div>
    </>
  );
}

export default function PlaygroundPage() {
  return (
    <StudioShell>
      <Playground />
    </StudioShell>
  );
}
