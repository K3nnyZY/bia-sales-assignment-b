"use client";

import Link from "next/link";
import { Feedback, StudioShell, useResource } from "../../components/studio";
import { MetricsPanel } from "../../components/metrics";
import type { Agent } from "../../lib/studio";
import type { Metrics } from "../../lib/governance";
import type { RunResult } from "../../lib/runtime";

function Dashboard() {
  const agents = useResource<Agent[]>("/agents");
  const collections = useResource<{ id: string }[]>("/knowledge/collections");
  const runs = useResource<RunResult[]>("/runs?limit=5");
  const metrics = useResource<Metrics>("/metrics");
  return (
    <>
      <section className="intro compact">
        <p className="eyebrow">DASHBOARD</p>
        <h1>Tu plataforma, en un vistazo.</h1>
        <p>Inventario y actividad consultados al backend según tus permisos.</p>
      </section>
      <button
        className="secondary"
        onClick={() => {
          agents.refresh();
          collections.refresh();
          runs.refresh();
          metrics.refresh();
        }}
      >
        Actualizar dashboard
      </button>
      <Feedback error={agents.error || collections.error || runs.error} />
      <section className="panel dashboard-panel">
        <h2>Inventario visible</h2>
        {((!agents.data && !agents.error) ||
          (!collections.data && !collections.error)) && (
          <p role="status">Cargando inventario…</p>
        )}
        <div className="metric-grid">
          <div>
            <span>Agentes registrados</span>
            <strong data-testid="dashboard-agents">
              {agents.data?.length ?? "No disponible"}
            </strong>
            <Link href="/agents">Ver agentes</Link>
          </div>
          <div>
            <span>Colecciones visibles</span>
            <strong data-testid="dashboard-collections">
              {collections.data?.length ?? "No disponible"}
            </strong>
            <Link href="/knowledge">Ver conocimiento</Link>
          </div>
        </div>
        {agents.data?.length === 0 && (
          <p>Todavía no hay agentes registrados.</p>
        )}
        {collections.data?.length === 0 && (
          <p>No hay colecciones visibles para tu identidad.</p>
        )}
        <p className="hint">
          Ver una colección no concede acceso a sus documentos. El backend
          autoriza cada consulta.
        </p>
      </section>
      <MetricsPanel data={metrics.data} error={metrics.error} />
      <section className="panel dashboard-panel">
        <h2>Últimas ejecuciones visibles</h2>
        {!runs.data && !runs.error && (
          <p role="status">Cargando ejecuciones…</p>
        )}
        {runs.data?.length === 0 && (
          <p>
            No hay ejecuciones visibles. Usa el Playground con una versión
            autorizada.
          </p>
        )}
        {runs.data?.map((run) => (
          <Link
            className="agent-card dashboard-run"
            href={`/traces?run=${run.id}`}
            key={run.id}
          >
            <div>
              <h3>
                {run.agent_id} · v{run.version_number}
              </h3>
              <small>
                {run.channel} · {run.mode} · {run.started_at}
              </small>
            </div>
            <span className="badge">{run.status}</span>
          </Link>
        ))}
        <Link href="/playground">Abrir Playground</Link>
        <p className="hint">
          Se muestran hasta cinco ejecuciones visibles, incluidas las
          evaluaciones autorizadas. Las métricas excluyen evaluaciones.
        </p>
      </section>
    </>
  );
}

export default function DashboardPage() {
  return (
    <StudioShell>
      <Dashboard />
    </StudioShell>
  );
}
