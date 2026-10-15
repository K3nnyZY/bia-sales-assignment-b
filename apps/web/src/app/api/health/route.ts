import { fetchBackendHealth } from "../../../lib/health";

export const dynamic = "force-dynamic";

export async function GET() {
  const result = await fetchBackendHealth(process.env.BACKEND_URL || "http://127.0.0.1:8000");
  return Response.json(result, {
    status: result.health?.status === "ok" ? 200 : 503,
    headers: { "Cache-Control": "no-store" },
  });
}
