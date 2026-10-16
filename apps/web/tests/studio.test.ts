import assert from "node:assert/strict";
import test from "node:test";
import {
  allowedStudioPath,
  ApiError,
  studioRequest,
} from "../src/lib/studio.ts";

test("proxy allows only management routes", () => {
  for (const path of [
    "agents",
    "agents/billing-assistant",
    "agents/billing-assistant/versions/1/snapshot",
    "models/synthetic-balanced-v1",
    "tools/invoice-read-v1",
    "tool-templates",
    "me",
    "users",
    "runs",
    "evaluation-suites",
    "evaluations/eval-0123456789abcdef0123456789abcdef",
    "agents/billing-assistant/versions/1/evaluations",
    "agents/billing-assistant/versions/1/governance",
    "agents/billing-assistant/versions/1/submit",
    "agents/billing-assistant/versions/1/approve",
    "agents/billing-assistant/versions/1/publish",
    "agents/billing-assistant/rollback",
    "metrics",
    "audit-events",
    "runtime/agents",
    "runs/run-0123456789abcdef0123456789abcdef/trace",
  ])
    assert.ok(allowedStudioPath(path.split("/")), path);
  for (const path of [
    "",
    "../health",
    "runs/arbitrary-user-input",
    "evaluations/arbitrary-id",
    "evaluation-suites/execute",
    "tool-templates/execute",
    "agents/billing-assistant/versions/0/publish",
    "agents/billing-assistant/versions/1/set-role",
    "runs/run-0123456789abcdef0123456789abcdef/execute",
    "agents/../users",
    "agents/a%2Fb",
    "agents/foo/execute",
    "https://untrusted.example",
    "agents/test-agent/versions/0",
    "models/foo/../../me",
  ])
    assert.equal(allowedStudioPath(path.split("/")), false, path);
});

test("typed client sends credentials and JSON without caching", async (context) => {
  context.mock.method(
    globalThis,
    "fetch",
    async (path: string, init: RequestInit) => {
      assert.equal(path, "/api/studio/agents");
      assert.equal(init.method, "POST");
      assert.equal(init.cache, "no-store");
      assert.deepEqual(init.headers, {
        Authorization: "Bearer user-token",
        "Content-Type": "application/json",
      });
      assert.equal(init.body, JSON.stringify({ id: "test-agent" }));
      return Response.json({ id: "test-agent" }, { status: 201 });
    },
  );
  assert.deepEqual(
    await studioRequest("/agents", "user-token", "POST", { id: "test-agent" }),
    { id: "test-agent" },
  );
});

test("backend authorization failures are preserved", async (context) => {
  context.mock.method(globalThis, "fetch", async () =>
    Response.json(
      { detail: { code: "FORBIDDEN", message: "Owner permission required" } },
      { status: 403 },
    ),
  );
  await assert.rejects(
    studioRequest("/models", "user-token"),
    (error: unknown) =>
      error instanceof ApiError &&
      error.status === 403 &&
      error.message === "Owner permission required",
  );
});

test("validation errors identify the failing field", async (context) => {
  context.mock.method(globalThis, "fetch", async () =>
    Response.json(
      {
        detail: [
          {
            loc: ["body", "configuration", "permissions"],
            msg: "Extra inputs are not permitted",
          },
        ],
      },
      { status: 422 },
    ),
  );
  await assert.rejects(
    studioRequest("/agents", "user-token", "POST", {}),
    /configuration.permissions/,
  );
});

test("known error guidance preserves the backend code and unknown diagnoses stay untouched", async (context) => {
  for (const code of ["STALE_REVISION", "HISTORY_EXISTS", "DELETE_NOT_ALLOWED", "UNKNOWN_ERROR", "constructor"]) {
    context.mock.method(globalThis, "fetch", async () => Response.json(
      { detail: { code, message: "Backend message" } }, { status: 409 },
    ));
    await assert.rejects(studioRequest("/agents/test-agent", "token", "DELETE"), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.code, code);
      assert.ok(error.message.startsWith("Backend message"));
      if (["UNKNOWN_ERROR", "constructor"].includes(code)) assert.equal(error.message, "Backend message");
      else assert.ok(error.message.length > "Backend message".length);
      return true;
    });
  }
});

test("delete accepts empty 204 responses", async (context) => {
  context.mock.method(
    globalThis,
    "fetch",
    async () => new Response(null, { status: 204 }),
  );
  assert.equal(
    await studioRequest("/agents/test-agent", "user-token", "DELETE"),
    undefined,
  );
});

test("knowledge proxy paths preserve the bounded API surface", () => {
  for (const path of [
    "knowledge/collections",
    "knowledge/collections/billing-reference/documents",
    "knowledge/collections/billing-reference/grants",
    "knowledge/collections/billing-reference/status",
    "knowledge/documents/billing-faq-rag/versions",
    "knowledge/documents/billing-faq-rag/versions/1/ingest",
    "knowledge/documents/billing-faq-rag/versions/1/chunks/0",
    "knowledge/search",
    "knowledge/searches",
  ])
    assert.ok(allowedStudioPath(path.split("/")), path);
  for (const path of [
    "knowledge/documents/foo/versions/0",
    "knowledge/documents/foo/download/../../secrets",
    "knowledge/embeddings/provider",
    "knowledge/search/execute",
    "knowledge/documents/foo/versions/1/chunks/-1",
  ])
    assert.equal(allowedStudioPath(path.split("/")), false, path);
});

test("document uploads send multipart without overriding its boundary", async (context) => {
  const body = new FormData();
  body.set("file", new File(["Synthetic FAQ"], "faq.md"));
  context.mock.method(
    globalThis,
    "fetch",
    async (path: string, init: RequestInit) => {
      assert.equal(
        path,
        "/api/studio/knowledge/documents/billing-faq-rag/versions",
      );
      assert.equal(init.body, body);
      assert.deepEqual(init.headers, { Authorization: "Bearer user-token" });
      return Response.json({ number: 1 }, { status: 201 });
    },
  );
  assert.deepEqual(
    await studioRequest(
      "/knowledge/documents/billing-faq-rag/versions",
      "user-token",
      "POST",
      body,
    ),
    { number: 1 },
  );
});
