"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { ContextHelp } from "../../components/help";
import { checkMetadata, checkObservations, checkStatus } from "../../lib/evaluation-checks";
import { gateGuidance } from "../../lib/help";
import {
  Feedback,
  StudioShell,
  useResource,
  useStudio,
} from "../../components/studio";
import type { Agent, AgentVersion } from "../../lib/studio";
import type {
  Approval,
  Evaluation,
  EvaluationDetail,
  Governance,
  Suite,
} from "../../lib/governance";

function EvaluationCenter() {
  const { api, user } = useStudio();
  const agents = useResource<Agent[]>("/agents");
  const suites = useResource<Suite[]>("/evaluation-suites");
  const evaluations = useResource<Evaluation[]>("/evaluations");
  const approvals = useResource<Approval[]>("/approvals");
  const [agentId, setAgentId] = useState("billing-assistant");
  const versions = useResource<AgentVersion[]>(`/agents/${agentId}/versions`);
  const [number, setNumber] = useState(0);
  const version =
    versions.data?.find((v) => v.number === number) || versions.data?.[0];
  const base = version ? `/agents/${agentId}/versions/${version.number}` : null;
  const governance = useResource<Governance>(
    base ? `${base}/governance` : null,
  );
  const [suiteKey, setSuiteKey] = useState("billing-runtime@1");
  const suite =
    suites.data?.find((s) => `${s.id}@${s.version}` === suiteKey) ||
    suites.data?.[0];
  const [mode, setMode] = useState("deterministic");
  const [evaluationId, setEvaluationId] = useState("");
  const detail = useResource<EvaluationDetail>(
    evaluationId ? `/evaluations/${evaluationId}` : null,
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const decisionPanel = useRef<HTMLElement>(null);
  const state = governance.data;
  const selectedAgent = agents.data?.find((a) => a.id === agentId);
  const canEvaluate =
    user &&
    (user.role === "administrator" ||
      user.role === "reviewer" ||
      (user.role === "creator" && selectedAgent?.owner_id === user.id));
  const canSubmit =
    user &&
    (user.role === "administrator" ||
      (user.role === "creator" && selectedAgent?.owner_id === user.id));
  const canApprove = user && ["administrator", "approver"].includes(user.role);
  const pendingApprovals = approvals.data?.filter((a) => a.status === "pending") || [];
  const approvalHint = !canApprove
    ? "La aprobación requiere un usuario con rol Admin o Approver."
    : state?.stage !== "pending_approval"
      ? "Selecciona una solicitud pendiente del historial. La versión debe estar en pending_approval."
      : !reason.trim()
        ? "Escribe un motivo de decisión para habilitar Aprobar y Rechazar."
        : "Puedes registrar la decisión. El backend verificará que seas un aprobador independiente.";
  function reviewApproval(approval: Approval) {
    setAgentId(approval.agent_id);
    setNumber(approval.version_number);
    setReason("");
    setError("");
    setSuccess("");
    governance.refresh();
    decisionPanel.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    decisionPanel.current?.focus({ preventScroll: true });
  }
  async function perform(operation: string) {
    if (!base || !state || busy) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const revision = {
        expected_revision: state.revision,
        expected_config_hash: state.config_hash,
      };
      if (operation === "evaluations") {
        if (!suite) throw new Error("Selecciona una suite");
        const result = await api<Evaluation>(`${base}/evaluations`, "POST", {
          expected_config_hash: state.config_hash,
          suite_id: suite.id,
          suite_version: suite.version,
          mode,
        });
        setEvaluationId(result.id);
        detail.refresh();
        setSuccess(
          `Evaluación ${result.status}: ${result.passed_count}/${result.total}; fallos críticos: ${result.critical_failures}`,
        );
      } else if (operation === "approved" || operation === "rejected") {
        await api(`${base}/approve`, "POST", {
          ...revision,
          decision: operation,
          reason,
        });
        setSuccess(
          operation === "approved"
            ? "Aprobación registrada"
            : "Rechazo registrado",
        );
      } else if (operation === "rollback") {
        await api(`/agents/${agentId}/rollback`, "POST", {
          target_version: version!.number,
          expected_publication_revision: state.publication_revision,
          reason,
        });
        setSuccess("Rollback registrado y publicación actualizada");
      } else {
        await api(
          `${base}/${operation}`,
          "POST",
          operation === "publish"
            ? {
                ...revision,
                expected_publication_revision: state.publication_revision,
              }
            : revision,
        );
        setSuccess(
          {
            submit: "Aprobación solicitada",
            publish: "Versión publicada",
            disable: "Versión deshabilitada",
          }[operation] || "Cambio registrado",
        );
      }
      governance.refresh();
      evaluations.refresh();
      approvals.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <section className="intro compact">
        <p className="eyebrow">QUALITY & GOVERNANCE</p>
        <h1>Evaluation Center.</h1>
        <ContextHelp term="Evaluation" />
        <p>
          Evalúa un snapshot exacto, solicita revisión independiente y publica
          una versión autorizada.
        </p>
        <p className="notice">
          Las pruebas ejecutan LangGraph con clientes sintéticos aislados. El
          modo determinista no llama a un proveedor. El modo proveedor requiere
          credenciales, consume cuota y puede fallar.
        </p>
      </section>
      <Feedback
        error={
          error ||
          agents.error ||
          versions.error ||
          governance.error ||
          suites.error ||
          evaluations.error ||
          approvals.error ||
          detail.error
        }
        success={success}
      />
      {canApprove && pendingApprovals.length > 0 && (
        <p className="notice">
          En este historial hay {pendingApprovals.length} solicitudes pendientes. Abre{" "}
          <a href="#approval-history">Solicitudes e historial de aprobaciones</a>{" "}
          y pulsa Revisar y aprobar en la versión que quieras revisar.
        </p>
      )}
      <div className="workspace detail">
        <aside>
          <section className="panel">
            <h2>Versión candidata</h2>
            <label>
              Agente
              <select
                aria-label="Agente"
                value={agentId}
                onChange={(e) => {
                  setAgentId(e.target.value);
                  setNumber(0);
                }}
              >
                {agents.data?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Versión
              <select
                aria-label="Versión"
                value={version?.number || ""}
                onChange={(e) => setNumber(Number(e.target.value))}
              >
                {versions.data?.map((v) => (
                  <option key={v.number} value={v.number}>
                    v{v.number} · {v.status}
                  </option>
                ))}
              </select>
            </label>
            {versions.data?.length === 0 && (
              <p>
                Crea una versión en{" "}
                <Link href={`/agents/${agentId}`}>el Builder</Link>.
              </p>
            )}
            {version?.status === "draft" && (
              <p>
                Guarda y congela el borrador en{" "}
                <Link href={`/agents/${agentId}`}>el Builder</Link> antes de
                evaluarlo.
              </p>
            )}
            <label>
              Suite versionada
              <select
                value={suite ? `${suite.id}@${suite.version}` : ""}
                onChange={(e) => setSuiteKey(e.target.value)}
              >
                {suites.data?.map((s) => (
                  <option
                    key={`${s.id}@${s.version}`}
                    value={`${s.id}@${s.version}`}
                  >
                    {s.name} · v{s.version}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Modo de evaluación
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="deterministic">Determinista · sin LLM</option>
                <option value="provider">Proveedor real · LiteLLM</option>
              </select>
            </label>
            {suite && <p className="hint">La suite fija las pruebas y su versión; no cambia la configuración del agente.</p>}
            {suites.data?.length === 0 && <p className="notice">No hay suites disponibles. Solicita a un administrador o reviewer que registre una suite antes de evaluar.</p>}
            <button
              disabled={
                busy ||
                !canEvaluate ||
                version?.status !== "snapshot" ||
                state?.ever_published ||
                !state ||
                !suite ||
                state.stage === "disabled"
              }
              onClick={() => perform("evaluations")}
            >
              {busy ? "Procesando…" : "Evaluar versión"}
            </button>
            <p className="hint">
              Una nueva evaluación invalida la aprobación de una candidata. Las
              versiones publicadas se clonan para volver a evaluarlas.
            </p>
            <button
              className="secondary"
              onClick={() => {
                versions.refresh();
                governance.refresh();
                evaluations.refresh();
                approvals.refresh();
              }}
            >
              Actualizar
            </button>
          </section>
        </aside>
        <section
          className="panel"
          ref={decisionPanel}
          tabIndex={-1}
          aria-labelledby="publication-gate-title"
        >
          <h2 id="publication-gate-title">Publication Gate</h2>
          <ContextHelp term="Publication Gate" />
          {!state && !governance.error && (
            <p role="status">Selecciona una versión; cargando gobernanza…</p>
          )}
          {state && (
            <>
              <p>
                <span className="badge" data-testid="governance-stage">
                  {state.stage}
                </span>{" "}
                · revisión {state.revision}
              </p>
              <p className="hash">
                SHA-256: {state.config_hash || "Borrador sin snapshot"}
              </p>
              <p>
                Publicación activa:{" "}
                {state.publication_enabled
                  ? `v${state.publication_version}`
                  : "Ninguna"}
              </p>
              <p>
                {state.gate.eligible
                  ? "Gate aprobado para esta configuración."
                  : "Bloqueos: " + state.gate.reasons.join(", ")}
              </p>
              {!state.gate.eligible && <ul>{state.gate.reasons.map((code) => (
                <li key={code}>{gateGuidance[code] || "El backend ha bloqueado esta configuración; consulta el código y las evaluaciones."} <small>({code})</small></li>
              ))}</ul>}
              <div className="actions">
                <button
                  disabled={busy || !canSubmit || state.stage !== "testing"}
                  onClick={() => perform("submit")}
                >
                  Solicitar aprobación
                </button>
                <button
                  disabled={
                    busy ||
                    !canApprove ||
                    state.stage !== "approved" ||
                    !state.gate.eligible
                  }
                  onClick={() => perform("publish")}
                >
                  Publicar versión
                </button>
                <button
                  className="secondary"
                  disabled={
                    busy ||
                    !canApprove ||
                    !["approved", "published", "deprecated"].includes(
                      state.stage,
                    )
                  }
                  onClick={() => perform("disable")}
                >
                  Deshabilitar versión
                </button>
              </div>
              <h3>Revisión de aprobación</h3>
              <p>
                {selectedAgent?.name || agentId} · v{version?.number}. La decisión
                se registra sobre el hash de configuración mostrado arriba.
              </p>
              <label>
                Motivo de decisión o rollback
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={2000}
                  aria-describedby="approval-action-hint"
                />
              </label>
              <p className="hint" id="approval-action-hint" role="status">
                {busy ? "Procesando la operación…" : approvalHint}
              </p>
              <div className="actions">
                <button
                  disabled={
                    busy ||
                    !canApprove ||
                    !reason.trim() ||
                    state.stage !== "pending_approval"
                  }
                  onClick={() => perform("approved")}
                >
                  Aprobar
                </button>
                <button
                  className="secondary"
                  disabled={
                    busy ||
                    !canApprove ||
                    !reason.trim() ||
                    state.stage !== "pending_approval"
                  }
                  onClick={() => perform("rejected")}
                >
                  Rechazar
                </button>
                <button
                  className="secondary"
                  disabled={
                    busy ||
                    !canApprove ||
                    !reason.trim() ||
                    !state.ever_published ||
                    !["deprecated", "disabled"].includes(state.stage)
                  }
                  onClick={() => perform("rollback")}
                >
                  Rollback a esta versión
                </button>
              </div>
              <p className="hint">
                El backend rechaza la autoaprobación y vuelve a validar
                permisos, hash, suite, modelo, herramientas y revisión vigente.
              </p>
              <ContextHelp term="Approval" />
            </>
          )}
        </section>
      </div>
      <section className="panel">
        <h2>Evaluaciones persistidas</h2>
        {evaluations.data?.length === 0 && <p>No hay evaluaciones visibles.</p>}
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Agente / versión</th>
                <th>Resultado</th>
                <th>Modo</th>
                <th>Críticos</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              {evaluations.data?.map((e) => (
                <tr key={e.id}>
                  <td>
                    {e.agent_id} · v{e.version_number}
                  </td>
                  <td>
                    {e.status} · {e.passed_count}/{e.total}
                  </td>
                  <td>{e.mode}</td>
                  <td>{e.critical_failures}</td>
                  <td>
                    <button
                      className="secondary"
                      onClick={() => {
                        setEvaluationId(e.id);
                        detail.refresh();
                      }}
                    >
                      Ver resultados
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {detail.data && (
        <section className="panel">
          <h2>Resultados de la suite</h2>
          <p className="hint">PASS: cumple la comprobación. FAIL: no cumple lo esperado. ERROR: el backend informa un error de ejecución, de comprobación o un timeout. Los códigos sin diagnóstico se conservan sin atribuirles una causa.</p>
          <p className="hash">
            {detail.data.evaluation.id}
            <br />
            Configuración: {detail.data.evaluation.config_hash}
            <br />
            Suite: {detail.data.evaluation.suite_hash}
            <br />
            Dependencias: {detail.data.evaluation.environment_hash}
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Prueba</th>
                  <th>Crítica</th>
                  <th>Resultado</th>
                  <th>Tiempo real</th>
                  <th>Traza</th>
                </tr>
              </thead>
              <tbody>
                {detail.data.results.map((r) => (
                  <tr key={r.check}>
                    <td>
                      <details className="check-detail">
                        <summary>{checkMetadata(r.check).name}</summary>
                        <p>{checkMetadata(r.check).purpose}</p>
                        <dl>
                          <dt>Estado</dt><dd>{checkStatus(r)}</dd>
                          <dt>Resultado esperado (contrato de la prueba)</dt><dd>{checkMetadata(r.check).expected}</dd>
                          <dt>Resultado obtenido (backend)</dt>
                          <dd>
                            {checkObservations(r).length ? (
                              <ul>{checkObservations(r).map(({ label, value }) => (
                                <li key={label}>{label}: {value}</li>
                              ))}</ul>
                            ) : "No disponible: el backend no guardó observaciones reconocidas."}
                            {Object.keys(r.details).length > 0 && (
                              <details>
                                <summary>Datos técnicos del backend</summary>
                                <pre>{JSON.stringify(r.details, null, 2)}</pre>
                              </details>
                            )}
                          </dd>
                          <dt>Error informado</dt><dd>{r.error_code || "Sin error informado."}</dd>
                        </dl>
                        <p className="hint">Los importes obtenidos solo pueden consultarse en la traza cuando estén disponibles; no se deducen del contrato esperado.</p>
                      </details>
                      <small className="technical-id">{r.check}</small>
                    </td>
                    <td>{r.critical ? "Sí" : "No"}</td>
                    <td><span className={`check-status ${checkStatus(r).toLowerCase()}`}>{checkStatus(r)}</span></td>
                    <td>{r.duration_ms} ms</td>
                    <td>
                      {r.run_id ? (
                        <Link href={`/traces?run=${r.run_id}`}>
                          Abrir traza
                        </Link>
                      ) : (
                        "Sin llamada al runtime"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <section className="panel" id="approval-history">
        <h2>Solicitudes e historial de aprobaciones</h2>
        {approvals.data?.length === 0 && <p>No hay solicitudes visibles.</p>}
        {approvals.data?.map((a) => (
          <article className="catalog-item" key={a.id}>
            <h3>
              {a.agent_id} · v{a.version_number} · {a.status}
            </h3>
            <p>
              Solicitó: {a.requested_by} · Decidió:{" "}
              {a.decided_by || "Pendiente"}
            </p>
            <p>{a.reason}</p>
            {a.status === "pending" && canApprove && (
              <button disabled={busy} onClick={() => reviewApproval(a)}>
                Revisar y aprobar
              </button>
            )}
          </article>
        ))}
      </section>
    </>
  );
}
export default function EvaluationPage() {
  return (
    <StudioShell>
      <EvaluationCenter />
    </StudioShell>
  );
}
