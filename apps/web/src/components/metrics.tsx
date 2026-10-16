import type { Metrics } from "../lib/governance";

const measurement = (value: number | null | undefined) =>
  value == null ? "No disponible" : `${value.toFixed(1)} ms`;

export function MetricsPanel({
  data,
  error,
}: {
  data: Metrics | null;
  error: string | null;
}) {
  return (
    <section className="panel metrics-panel">
      <h2>Métricas observadas</h2>
      {!data && !error && <p role="status">Cargando mediciones…</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {data && (
        <>
          <p>
            Alcance: {data.scope}. Excluye las ejecuciones de evaluación;
            incluye preview y published.
          </p>
          {data.runs === 0 && <p>Aún no hay ejecuciones en tu alcance.</p>}
          <div className="metric-grid">
            {[
              ["Ejecuciones", data.runs, "runs"],
              ["Completadas", data.completed, "completed"],
              ["Fallidas", data.failed, "failed"],
              ["Denegadas", data.denied, "denied"],
              ["Escaladas", data.escalated, "escalated"],
              ["En curso", data.running, "running"],
              ["Herramientas", data.tool_calls, "tool-calls"],
              ["Errores de herramientas", data.tool_errors, "tool-errors"],
            ].map(([label, value, id]) => (
              <div key={label}>
                <span>{label}</span>
                <strong data-testid={`metric-${id}`}>{value}</strong>
              </div>
            ))}
          </div>
          <p>
            Latencia media: {measurement(data.latency_avg_ms)} · P50:{" "}
            {measurement(data.latency_p50_ms)} · P95:{" "}
            {measurement(data.latency_p95_ms)}
          </p>
          {data.models.length === 0 && <p>No hay uso de modelos registrado.</p>}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Modelo / modo</th>
                  <th>Runs</th>
                  <th>Tokens entrada / cobertura</th>
                  <th>Tokens salida / cobertura</th>
                  <th>Costo estimado USD / cobertura</th>
                </tr>
              </thead>
              <tbody>
                {data.models.map((m) => (
                  <tr key={`${m.model_id}:${m.mode}`}>
                    <td>
                      {m.model_id} · {m.mode}
                    </td>
                    <td>{m.runs}</td>
                    <td>
                      {m.input_tokens ?? "No disponible"} ·{" "}
                      {m.input_tokens_known_runs}/{m.runs}
                    </td>
                    <td>
                      {m.output_tokens ?? "No disponible"} ·{" "}
                      {m.output_tokens_known_runs}/{m.runs}
                    </td>
                    <td>
                      {m.estimated_cost_usd ?? "No disponible"} ·{" "}
                      {m.cost_known_runs}/{m.runs}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            Los tokens proceden del proveedor cuando los reporta. Los costos son
            estimaciones con esos tokens y precios del catálogo; no son cobros
            facturados. Las sumas solo incluyen runs con datos conocidos. La
            ausencia de datos no se muestra como cero.
          </p>
        </>
      )}
    </section>
  );
}
