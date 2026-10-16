import { allowedStudioPath } from "../../../../lib/studio";

export const dynamic = "force-dynamic";

async function forward(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (!allowedStudioPath(path))
    return Response.json({ detail: "Ruta no disponible" }, { status: 404 });
  const token = request.headers.get("authorization");
  if (!token || !/^Bearer [^\s]{1,512}$/i.test(token)) {
    return Response.json(
      { detail: "Introduce un token válido" },
      { status: 401 },
    );
  }
  if (Number(request.headers.get("content-length") || 0) > 131072) {
    return Response.json(
      { detail: "Solicitud demasiado grande" },
      { status: 413 },
    );
  }
  try {
    const base = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(
      /\/$/,
      "",
    );
    const body = request.method === "GET" ? undefined : await request.text();
    if (body && new TextEncoder().encode(body).length > 131072)
      return Response.json(
        { detail: "Solicitud demasiado grande" },
        { status: 413 },
      );
    const response = await fetch(
      `${base}/api/v1/${path.join("/")}${new URL(request.url).search}`,
      {
        method: request.method,
        headers: { Authorization: token, "Content-Type": "application/json" },
        body: body || undefined,
        cache: "no-store",
        signal: AbortSignal.timeout(
          path.join("/") === "runs" && request.method === "POST"
            ? 125000
            : 8000,
        ),
        redirect: "error",
      },
    );
    return new Response(
      response.status === 204 ? null : await response.text(),
      {
        status: response.status,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        },
      },
    );
  } catch {
    return Response.json(
      { detail: "El backend no está disponible. Intenta de nuevo." },
      { status: 503 },
    );
  }
}

export {
  forward as GET,
  forward as POST,
  forward as PUT,
  forward as PATCH,
  forward as DELETE,
};
