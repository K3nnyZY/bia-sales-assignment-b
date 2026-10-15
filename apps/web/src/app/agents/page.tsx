"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import {
  Feedback,
  StudioShell,
  useResource,
  useStudio,
} from "../../components/studio";
import type { Agent } from "../../lib/studio";

function AgentList() {
  const { api, user } = useStudio();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const agents = useResource<Agent[]>(
    `/agents?q=${encodeURIComponent(search)}${status ? `&status=${status}` : ""}`,
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const canCreate = user?.role === "creator" || user?.role === "administrator";
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const agent = await api<Agent>("/agents", "POST", {
        id: form.get("id"),
        name: form.get("name"),
        department: form.get("department"),
        description: form.get("description"),
      });
      router.push(`/agents/${agent.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <section className="intro compact">
        <p className="eyebrow">AGENT REGISTRY</p>
        <h1>Agentes de tu organización.</h1>
        <p>
          Define su propósito, selecciona capacidades aprobadas y conserva cada
          versión.
        </p>
      </section>
      <div className="workspace">
        <section className="panel">
          <h2>Inventario</h2>
          <form
            className="filters"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(query);
            }}
          >
            <label>
              Buscar por nombre
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <label>
              Estado
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
              >
                <option value="">Todos</option>
                <option value="draft">Borrador</option>
                <option value="disabled">Deshabilitado</option>
                <option value="deprecated">Deprecado</option>
              </select>
            </label>
            <button>Buscar</button>
          </form>
          <Feedback error={agents.error} />
          {!agents.data && !agents.error && (
            <p role="status">Cargando agentes…</p>
          )}
          {agents.data?.length === 0 && (
            <p>No hay agentes con estos filtros.</p>
          )}
          <div className="agent-list">
            {agents.data?.map((agent) => (
              <Link
                className="agent-card"
                href={`/agents/${agent.id}`}
                key={agent.id}
              >
                <div>
                  <h3>{agent.name}</h3>
                  <p>{agent.description || agent.department}</p>
                  <small>
                    {agent.owner_id} · {agent.id}
                  </small>
                </div>
                <span className="badge">{agent.status}</span>
              </Link>
            ))}
          </div>
          <button className="secondary" onClick={agents.refresh}>
            Actualizar lista
          </button>
        </section>
        {canCreate && (
          <section className="panel">
            <h2>Crear agente</h2>
            <p className="hint">
              Comenzará como borrador y será de tu propiedad.
            </p>
            <form onSubmit={create}>
              <label>
                Identificador
                <input
                  name="id"
                  pattern="[a-z][a-z0-9_-]{2,79}"
                  placeholder="billing-assistant"
                  required
                  maxLength={80}
                />
              </label>
              <label>
                Nombre
                <input name="name" required maxLength={120} />
              </label>
              <label>
                Departamento
                <input name="department" required maxLength={120} />
              </label>
              <label>
                Descripción
                <textarea name="description" maxLength={4000} />
              </label>
              <button disabled={busy}>
                {busy ? "Creando…" : "Crear agente"}
              </button>
            </form>
            <Feedback error={error} />
          </section>
        )}
      </div>
    </>
  );
}

export default function AgentsPage() {
  return (
    <StudioShell>
      <AgentList />
    </StudioShell>
  );
}
