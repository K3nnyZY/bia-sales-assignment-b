import type { RunTrace } from "../lib/runtime";

export function TraceView({ trace }: { trace: RunTrace }) {
  const run = trace.run;
  return (
    <>
      <p>
        <span className="badge">{run.status}</span> · {run.channel} · {run.mode}
      </p>
      <p className="hash">
        Run: {run.id}
        <br />
        Agente: {run.agent_id} · v{run.version_number}
        <br />
        Configuración: {run.config_hash}
        <br />
        Modelo: {run.model_id}
        <br />
        Workflow: {run.workflow_version}
      </p>
      <p>
        Inicio: {run.started_at} · Fin: {run.completed_at || "En curso"}
      </p>
      {run.error_code && <p className="error">{run.error_code}</p>}
      <p className="runtime-answer">{run.answer}</p>
      <p className="hint">
        Tokens reportados: entrada {run.input_tokens ?? "No disponible"}, salida{" "}
        {run.output_tokens ?? "No disponible"}. Costo estimado según catálogo
        (USD): {run.estimated_cost_usd ?? "No disponible"}.
      </p>
      <details>
        <summary>Cálculos Python y referencias autorizadas</summary>
        <pre>
          {JSON.stringify(
            { calculations: run.calculations, references: run.references },
            null,
            2,
          )}
        </pre>
      </details>
      <h3>Nodos del StateGraph</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Paso</th>
              <th>Nodo</th>
              <th>Estado / error</th>
              <th>Duración real</th>
            </tr>
          </thead>
          <tbody>
            {trace.events.map((e, i) => (
              <tr key={i}>
                <td>{e.step}</td>
                <td>{e.node}</td>
                <td>
                  {e.status} {e.error_code}
                </td>
                <td>{e.duration_ms} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <KnowledgeTraceView searches={trace.knowledge_searches || []} />
      <h3>Herramientas</h3>
      {trace.tool_calls.length === 0 && <p>No se ejecutaron herramientas.</p>}
      {trace.tool_calls.map((c) => (
        <article className="catalog-item" key={c.id}>
          <h3>
            {c.tool_id} · {c.tool_version}
          </h3>
          <p>
            {c.status} · intento {c.attempt} · {c.duration_ms} ms ·{" "}
            {c.error_code}
          </p>
          <pre>
            {JSON.stringify(
              { arguments: c.arguments, references: c.result_references },
              null,
              2,
            )}
          </pre>
        </article>
      ))}
    </>
  );
}

export function KnowledgeTraceView({
  searches,
}: {
  searches: RunTrace["knowledge_searches"];
}) {
  return (
    <>
      <h3>Retrieval documental</h3>
      {searches.length === 0 && <p>Esta ejecución no utiliza Knowledge RAG.</p>}
      {searches.map((s) => (
        <article className="catalog-item" key={s.id}>
          <p>
            {s.mode} · {s.duration_ms} ms · {s.error_code || "Completado"}
          </p>
          <p className="hash">{s.embedding_version}</p>
          <p>
            Embeddings locales reales. No consume tokens de proveedor ni genera
            costos facturables de API.
          </p>
          <ul>
            {s.references.map((ref) => (
              <li key={ref.reference}>
                {ref.reference} · documento {ref.document_id} · versión{" "}
                {ref.version} · fragmento {ref.chunk}
              </li>
            ))}
          </ul>
        </article>
      ))}
    </>
  );
}
