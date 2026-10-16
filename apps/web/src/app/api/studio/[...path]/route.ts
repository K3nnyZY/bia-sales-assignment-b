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
  const multipart =
    request.headers.get("content-type")?.startsWith("multipart/form-data") &&
    /^knowledge\/documents\/[a-z][a-z0-9_-]{2,79}\/versions$/.test(
      path.join("/"),
    );
  const maxBytes = multipart ? 2113536 : 131072;
  if (Number(request.headers.get("content-length") || 0) > maxBytes) {
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
    let body: Uint8Array<ArrayBuffer> | undefined;
    if (request.method !== "GET" && request.body) {
      const reader = request.body.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > maxBytes) {
          await reader.cancel();
          return Response.json(
            { detail: "Solicitud demasiado grande" },
            { status: 413 },
          );
        }
        chunks.push(value);
      }
      body = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        body.set(chunk, offset);
        offset += chunk.byteLength;
      }
    }
    if (body && body.byteLength > maxBytes)
      return Response.json(
        { detail: "Solicitud demasiado grande" },
        { status: 413 },
      );
    const response = await fetch(
      `${base}/api/v1/${path.join("/")}${new URL(request.url).search}`,
      {
        method: request.method,
        headers: {
          Authorization: token,
          "Content-Type": multipart
            ? request.headers.get("content-type")!
            : "application/json",
        },
        body: body || undefined,
        cache: "no-store",
        signal: AbortSignal.timeout(
          (path.join("/") === "runs" ||
            path.at(-1) === "evaluations" ||
            path.at(-1) === "ingest" ||
            path.join("/") === "knowledge/search") &&
            request.method === "POST"
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
