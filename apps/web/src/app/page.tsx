"use client";

import { SiteHeader } from "../components/studio";
import { useEffect, useState } from "react";
import type { HealthResult } from "../lib/health";

async function queryHealth(): Promise<HealthResult> {
  try {
    const response = await fetch("/api/health", {
      cache: "no-store",
      signal: AbortSignal.timeout(7000),
    });
    return await response.json();
  } catch {
    return {
      health: null,
      error: "No se pudo consultar el estado. Intenta de nuevo.",
    };
  }
}

export default function Home() {
  const [result, setResult] = useState<HealthResult | null>(null);
  const [loading, setLoading] = useState(true);
  async function refresh() {
    setLoading(true);
    setResult(await queryHealth());
    setLoading(false);
  }

  useEffect(() => {
    let active = true;
    void queryHealth().then((data) => {
      if (active) {
        setResult(data);
        setLoading(false);
      }
    });
    return () => {
      active = false;
    };
  }, []);
  const health = result?.health;
  const checks = [
    ["API", health ? "ok" : "unknown", "FastAPI · /health/ready"],
    [
      "Base de datos",
      health?.database || "unknown",
      "PostgreSQL 16 · conexión SQL",
    ],
    [
      "Migraciones",
      health?.migrations || "unknown",
      "Alembic · revisión del esquema",
    ],
  ];
  const label = (state: string) =>
    loading
      ? "Consultando…"
      : {
          ok: "Disponible",
          error: "No disponible",
          pending: "Pendiente",
          unknown: "Sin confirmar",
        }[state];

  return (
    <main>
      <SiteHeader />
      <section className="intro">
        <p className="eyebrow">PLATAFORMA INTERNA</p>
        <h1>Una base para construir.</h1>
        <p>
          Comprueba la conexión entre la interfaz, la API y la base de datos
          antes de continuar.
        </p>
      </section>
      <section className="panel" aria-labelledby="status-title">
        <div className="panel-heading">
          <div>
            <h2 id="status-title">Estado de infraestructura</h2>
            <p>Datos consultados al backend en cada actualización.</p>
          </div>
          <button onClick={() => void refresh()} disabled={loading}>
            {loading ? "Consultando…" : "Actualizar estado"}
          </button>
        </div>
        <div aria-live="polite" aria-busy={loading}>
          {checks.map(([name, state, detail]) => (
            <div className="check" key={name}>
              <div>
                <h3>{name}</h3>
                <p>{detail}</p>
              </div>
              <span className={`badge ${loading ? "unknown" : state}`}>
                {label(state)}
              </span>
            </div>
          ))}
          {!loading && result?.error && (
            <p className="error" role="alert">
              {result.error}
            </p>
          )}
          {!loading && health?.migrations === "pending" && (
            <p className="error" role="alert">
              La base de datos responde, pero sus migraciones están pendientes.
            </p>
          )}
        </div>
      </section>
      <footer>Foundation · Configuración, conectividad y migraciones.</footer>
    </main>
  );
}
