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
    "me",
    "users",
    "runs",
    "runtime/agents",
    "runs/run-0123456789abcdef0123456789abcdef/trace",
  ])
    assert.ok(allowedStudioPath(path.split("/")), path);
  for (const path of [
    "",
    "../health",
    "runs/arbitrary-user-input",
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
