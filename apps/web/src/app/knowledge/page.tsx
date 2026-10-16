"use client";

import { useState, type FormEvent } from "react";
import {
  StudioShell,
  Feedback,
  useStudio,
  useResource,
} from "../../components/studio";

type Collection = {
  id: string;
  name: string;
  owner_id: string;
  classification: string;
  enabled: boolean;
};
type Document = { id: string; title: string; owner_id: string };
type Version = {
  document_id: string;
  number: number;
  status: string;
  approval: string;
  chunk_count: number;
  error_code: string | null;
  embedding_version: string;
  content_hash: string;
  source: string;
  valid_from: string;
  valid_to: string;
};
type Evidence = {
  reference: string;
  collection_id: string;
  document_id: string;
  version: number;
  chunk: number;
  content: string;
  title: string;
  source: string;
  content_hash: string;
  semantic_similarity: number;
  lexical_rank: number;
  char_start: number;
  char_end: number;
};
type Search = {
  id: string;
  mode: string;
  embedding_version: string;
  duration_ms: number;
  evidence: Evidence[];
};

export default function KnowledgePage() {
  return (
    <StudioShell>
      <Knowledge />
    </StudioShell>
  );
}

function Knowledge() {
  const { api, user } = useStudio();
  const collections = useResource<Collection[]>("/knowledge/collections");
  const [selected, setSelected] = useState("");
  const cid = selected || collections.data?.[0]?.id || "";
  const documents = useResource<Document[]>(
    cid ? `/knowledge/collections/${cid}/documents` : null,
  );
  const [selectedDoc, setSelectedDoc] = useState("");
  const docid = selectedDoc || documents.data?.[0]?.id || "";
  const versions = useResource<Version[]>(
    docid ? `/knowledge/documents/${docid}/versions` : null,
  );
  const users = useResource<{ id: string; name: string }[]>(
    user?.role === "administrator" ? "/users" : null,
  );
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Search | null>(null);
  const [verified, setVerified] = useState("");
  const [asOf, setAsOf] = useState("2026-09-01");
  const coll = collections.data?.find((c) => c.id === cid);
  const canEdit =
    user?.role === "administrator" ||
    (user?.role === "creator" && coll?.owner_id === user.id);
  const canReview = user?.role === "administrator" || user?.role === "reviewer";
  async function perform(work: () => Promise<void>) {
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      await work();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function createCollection(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    void perform(async () => {
      const c = await api<Collection>("/knowledge/collections", "POST", {
        id: data.get("id"),
        name: data.get("name"),
        classification: data.get("classification"),
      });
      collections.refresh();
      setSelected(c.id);
      setSelectedDoc("");
      form.reset();
      setSuccess("Colección creada. Los grants se administran en backend.");
    });
  }
  function createDocument(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    void perform(async () => {
      const doc = await api<Document>(
        `/knowledge/collections/${cid}/documents`,
        "POST",
        { id: data.get("id"), title: data.get("title") },
      );
      documents.refresh();
      setSelectedDoc(doc.id);
      form.reset();
      setSuccess("Documento creado. Carga su primera versión.");
    });
  }
  function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    void perform(async () => {
      const version = await api<Version>(
        `/knowledge/documents/${docid}/versions`,
        "POST",
        data,
      );
      versions.refresh();
      setSuccess(
        `Versión ${version.number}: ${version.status}. Ejecuta la ingesta y solicita revisión.`,
      );
      form.reset();
    });
  }
  function search(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setResult(null);
    setVerified("");
    void perform(async () => {
      setResult(
        await api<Search>("/knowledge/search", "POST", {
          query: data.get("query"),
          collection_ids: [cid],
          as_of: asOf,
        }),
      );
    });
  }
  return (
    <>
      <section className="panel">
        <p className="eyebrow">KNOWLEDGE REGISTRY</p>
        <h1>Conocimiento con evidencia.</h1>
        <p>
          PDF con texto, TXT y Markdown · máximo 2 MiB y 20 páginas. Embeddings
          semánticos locales multilingües, búsqueda vectorial pgvector y texto
          en español. Sin OCR.
        </p>
        <Feedback
          error={
            error || collections.error || documents.error || versions.error
          }
          success={success}
        />
        {!collections.data && !collections.error && (
          <p>Cargando colecciones…</p>
        )}
        {collections.data?.length === 0 && (
          <p>No tienes colecciones disponibles. Crea una o solicita acceso.</p>
        )}
        <label>
          Colección
          <select
            aria-label="Colección"
            value={cid}
            onChange={(e) => {
              setSelected(e.target.value);
              setSelectedDoc("");
              setResult(null);
            }}
          >
            <option value="">Selecciona</option>
            {collections.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.classification} ·{" "}
                {c.enabled ? "activa" : "deshabilitada"}
              </option>
            ))}
          </select>
        </label>
        {coll && (
          <p>
            Propietario: {coll.owner_id}. La lectura requiere un grant explícito
            y clasificación compatible; ser administrador no concede acceso
            documental.
          </p>
        )}
        {(user?.role === "creator" || user?.role === "administrator") && (
          <details>
            <summary>Crear colección</summary>
            <form onSubmit={createCollection}>
              <label>
                ID de colección
                <input name="id" required pattern="[a-z][a-z0-9_-]{2,79}" />
              </label>
              <label>
                Nombre de colección
                <input name="name" required maxLength={120} />
              </label>
              <label>
                Clasificación
                <select name="classification">
                  <option value="internal">Interna</option>
                  {user?.role === "administrator" && (
                    <option value="restricted">Restringida</option>
                  )}
                </select>
              </label>
              <button disabled={busy}>Crear colección</button>
            </form>
          </details>
        )}
        {user?.role === "administrator" && cid && (
          <details>
            <summary>Administrar acceso</summary>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const data = new FormData(e.currentTarget);
                void perform(async () => {
                  await api(`/knowledge/collections/${cid}/grants`, "PUT", {
                    user_id: data.get("user_id"),
                    clearance: data.get("clearance"),
                    enabled: data.get("enabled") === "true",
                  });
                  setSuccess("Grant actualizado y auditado.");
                });
              }}
            >
              <label>
                Usuario
                <select name="user_id" required>
                  {users.data?.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} · {u.id}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Autorización de clasificación
                <select name="clearance">
                  <option value="internal">Interna</option>
                  <option value="restricted">Restringida</option>
                </select>
              </label>
              <label>
                Acceso
                <select name="enabled">
                  <option value="true">Conceder</option>
                  <option value="false">Revocar</option>
                </select>
              </label>
              <button disabled={busy}>Guardar acceso</button>
            </form>
          </details>
        )}
      </section>
      {cid && (
        <section className="panel">
          <h2>Documentos y versiones</h2>
          <label>
            Documento
            <select
              aria-label="Documento"
              value={docid}
              onChange={(e) => setSelectedDoc(e.target.value)}
            >
              <option value="">Selecciona</option>
              {documents.data?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title} · {d.id}
                </option>
              ))}
            </select>
          </label>
          {documents.data?.length === 0 && (
            <p>Esta colección todavía no tiene documentos.</p>
          )}
          {canEdit && (
            <details>
              <summary>Crear documento</summary>
              <form onSubmit={createDocument}>
                <label>
                  ID de documento
                  <input name="id" required pattern="[a-z][a-z0-9_-]{2,79}" />
                </label>
                <label>
                  Título
                  <input name="title" required maxLength={120} />
                </label>
                <button disabled={busy}>Crear documento</button>
              </form>
            </details>
          )}
          {canEdit && docid && (
            <form onSubmit={upload}>
              <h3>Cargar versión documental</h3>
              <label>
                Archivo PDF, TXT o Markdown
                <input
                  name="file"
                  type="file"
                  accept=".pdf,.txt,.md"
                  required
                />
              </label>
              <label>
                Fuente
                <input
                  name="source"
                  placeholder="synthetic://billing/faq"
                  required
                  maxLength={240}
                />
              </label>
              <div className="form-grid">
                <label>
                  Vigente desde
                  <input
                    name="valid_from"
                    type="date"
                    defaultValue="2026-08-01"
                    required
                  />
                </label>
                <label>
                  Vigente hasta
                  <input
                    name="valid_to"
                    type="date"
                    defaultValue="2026-12-31"
                    required
                  />
                </label>
              </div>
              <button disabled={busy}>Cargar versión</button>
            </form>
          )}
          {versions.data?.length === 0 && (
            <p>No hay versiones. Carga un documento para comenzar.</p>
          )}
          {versions.data?.map((v) => (
            <article className="catalog-item" key={v.number}>
              <h3>
                {v.document_id} · v{v.number}
              </h3>
              <p>
                <span className="badge">{v.status}</span> · {v.approval} ·{" "}
                {v.chunk_count} fragmentos
              </p>
              <p>
                {v.valid_from} → {v.valid_to} · {v.source}
              </p>
              <p className="hash">
                SHA-256 {v.content_hash}
                <br />
                {v.embedding_version}
              </p>
              {v.error_code && <p className="error">{v.error_code}</p>}
              {canEdit && ["pending", "failed"].includes(v.status) && (
                <button
                  disabled={busy}
                  onClick={() =>
                    void perform(async () => {
                      const r = await api<Version>(
                        `/knowledge/documents/${docid}/versions/${v.number}/ingest`,
                        "POST",
                      );
                      versions.refresh();
                      setSuccess(
                        `Ingesta: ${r.status}${r.error_code ? " · " + r.error_code : ""}`,
                      );
                    })
                  }
                >
                  Ejecutar ingesta v{v.number}
                </button>
              )}
              {canReview &&
                v.status === "ready" &&
                v.approval === "pending" && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void perform(async () => {
                        await api(
                          `/knowledge/documents/${docid}/versions/${v.number}`,
                          "PATCH",
                          { approval: "approved" },
                        );
                        versions.refresh();
                        setSuccess(
                          "Versión aprobada para retrieval autorizado.",
                        );
                      })
                    }
                  >
                    Aprobar documento v{v.number}
                  </button>
                )}
              {canReview && v.approval === "approved" && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    void perform(async () => {
                      await api(
                        `/knowledge/documents/${docid}/versions/${v.number}`,
                        "PATCH",
                        { approval: "revoked" },
                      );
                      versions.refresh();
                      setResult(null);
                      setSuccess(
                        "Versión revocada; los snapshots que la referencian quedan bloqueados.",
                      );
                    })
                  }
                >
                  Revocar documento v{v.number}
                </button>
              )}
            </article>
          ))}
        </section>
      )}
      {cid && (
        <section className="panel">
          <h2>Probar búsqueda autorizada</h2>
          <p>
            Solo versiones aprobadas y vigentes para la fecha seleccionada. Una
            búsqueda sin evidencia no inventa una respuesta.
          </p>
          <form onSubmit={search}>
            <label>
              Consulta
              <input
                name="query"
                defaultValue="¿Por qué cambia el cargo por consumo y cuál es la tarifa?"
                required
                maxLength={1000}
              />
            </label>
            <label>
              Fecha de la consulta
              <input
                type="date"
                value={asOf}
                onChange={(e) => {
                  setAsOf(e.target.value);
                  setResult(null);
                }}
                required
              />
            </label>
            <button disabled={busy}>
              {busy ? "Procesando…" : "Buscar evidencia"}
            </button>
          </form>
          {result && (
            <>
              <p>
                {result.mode} · {result.duration_ms} ms medidos · {result.id}
              </p>
              <p className="hash">{result.embedding_version}</p>
              {result.evidence.length === 0 && (
                <p>No se encontró evidencia aprobada y vigente.</p>
              )}
              {result.evidence.map((e) => (
                <article className="catalog-item" key={e.reference}>
                  <h3>{e.title}</h3>
                  <p>
                    {e.reference} · {e.source}
                  </p>
                  <p>{e.content}</p>
                  <p className="hint">
                    Similitud coseno: {e.semantic_similarity.toFixed(4)} ·
                    relevancia léxica: {e.lexical_rank.toFixed(4)} · caracteres{" "}
                    {e.char_start}–{e.char_end}. Son puntuaciones de búsqueda,
                    no probabilidades de veracidad.
                  </p>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      void perform(async () => {
                        const source = await api(
                          `/knowledge/documents/${e.document_id}/versions/${e.version}/chunks/${e.chunk}?as_of=${asOf}`,
                        );
                        setVerified(JSON.stringify(source, null, 2));
                      })
                    }
                  >
                    Verificar {e.reference}
                  </button>
                </article>
              ))}
            </>
          )}
          {verified && (
            <details open>
              <summary>Fragmento verificado por backend</summary>
              <pre>{verified}</pre>
            </details>
          )}
        </section>
      )}
    </>
  );
}
