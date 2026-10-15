export type Health = {
  status: "ok" | "error";
  service: string;
  database: "ok" | "error";
  migrations: "ok" | "pending" | "unknown";
};

export type HealthResult = { health: Health | null; error: string | null };

function isHealth(value: unknown): value is Health {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  return (
    ["ok", "error"].includes(String(data.status)) &&
    data.service === "bia-api" &&
    ["ok", "error"].includes(String(data.database)) &&
    ["ok", "pending", "unknown"].includes(String(data.migrations))
  );
}

export async function fetchBackendHealth(
  baseUrl: string,
  fetcher: typeof fetch = fetch,
): Promise<HealthResult> {
  try {
    const response = await fetcher(`${baseUrl.replace(/\/$/, "")}/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (response.status !== 200 && response.status !== 503) {
      throw new Error("Unexpected backend status");
    }
    const health: unknown = await response.json();
    if (!isHealth(health)) throw new Error("Invalid backend response");
    if (response.ok !== (health.status === "ok")) throw new Error("Inconsistent status");
    if (health.status === "ok" && (health.database !== "ok" || health.migrations !== "ok")) {
      throw new Error("Inconsistent readiness");
    }
    return { health, error: null };
  } catch {
    return { health: null, error: "No se pudo consultar el backend. Revisa que la API esté disponible." };
  }
}
