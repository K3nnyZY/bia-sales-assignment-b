"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ContextHelp } from "../../components/help";
import { Feedback, StudioShell, useResource } from "../../components/studio";
import { TraceView } from "../../components/trace";
import { MetricsPanel } from "../../components/metrics";
import type { Audit, Metrics } from "../../lib/governance";
import type { RunResult, RunTrace } from "../../lib/runtime";

function TraceCenter() {
  const query = useSearchParams();
  const [selected, setSelected] = useState(query.get("run") || "");
  const runs = useResource<RunResult[]>("/runs?limit=100");
  const metrics = useResource<Metrics>("/metrics");
  const audit = useResource<Audit[]>("/audit-events?limit=100");
  const trace = useResource<RunTrace>(
    /^run-[a-f0-9]{32}$/.test(selected) ? `/runs/${selected}/trace` : null,
  );
  return (
    <>
      <section className="intro compact">
        <p className="eyebrow">OBSERVABILIDAD</p>
        <h1>Traces & Audit.</h1>
        <ContextHelp term="Trace" />
        <p>
          Ejecuciones, mediciones e historial persistidos. Cada consulta aplica
          permisos en el backend.
        </p>
      </section>
      <Feedback error={runs.error || audit.error || trace.error} />
      <button
        className="secondary"
        onClick={() => {
          runs.refresh();
          metrics.refresh();
          audit.refresh();
          trace.refresh();
        }}
      >
        Actualizar observabilidad
      </button>
      <MetricsPanel data={metrics.data} error={metrics.error} />
      <div className="workspace detail">
        <aside className="panel versions">
          <h2>Ejecuciones visibles</h2>
          {runs.data?.length === 0 && <p>No hay ejecuciones visibles.</p>}
          {runs.data?.map((r) => (
            <button
              className={`version-button ${selected === r.id ? "selected" : ""}`}
              key={r.id}
              onClick={() => setSelected(r.id)}
            >
              <span>
                {r.agent_id} · v{r.version_number}
              </span>
              <small>
                {r.status} · {r.channel} · {r.mode}
              </small>
              <small>{r.id}</small>
            </button>
          ))}
        </aside>
        <section className="panel">
          <h2>Traza persistida</h2>
          {!selected && <p>Selecciona una ejecución.</p>}
          {selected && !trace.data && !trace.error && (
            <p role="status">Cargando traza…</p>
          )}
          {trace.data && <TraceView trace={trace.data} />}
        </section>
      </div>
      <section className="panel">
        <h2>Historial de auditoría</h2>
        {audit.data?.length === 0 && <p>No hay eventos visibles.</p>}
        {audit.data?.map((e) => (
          <details key={e.id} className="catalog-item">
            <summary>
              {e.action} · {e.agent_id || "Catálogo"}{" "}
              {e.version_number ? `v${e.version_number}` : ""} · {e.actor_id}
            </summary>
            <p>{e.created_at}</p>
            <pre>{JSON.stringify(e.details, null, 2)}</pre>
          </details>
        ))}
      </section>
    </>
  );
}
export default function TracesPage() {
  return (
    <StudioShell>
      <Suspense fallback={<p>Cargando…</p>}>
        <TraceCenter />
      </Suspense>
    </StudioShell>
  );
}
