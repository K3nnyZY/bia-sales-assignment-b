import assert from "node:assert/strict";
import test from "node:test";
import { fetchBackendHealth } from "../src/lib/health.ts";

const ready = { status: "ok", service: "bia-api", database: "ok", migrations: "ok" };

test("queries the real readiness URL without caching", async () => {
  const result = await fetchBackendHealth("http://api:8000/", async (url, init) => {
    assert.equal(url, "http://api:8000/health/ready");
    assert.equal(init?.cache, "no-store");
    assert.ok(init?.signal);
    return Response.json(ready);
  });
  assert.deepEqual(result, { health: ready, error: null });
});

test("preserves database failures from the API", async () => {
  const unhealthy = { ...ready, status: "error", database: "error", migrations: "unknown" };
  const result = await fetchBackendHealth("http://api:8000", async () => Response.json(unhealthy, { status: 503 }));
  assert.deepEqual(result.health, unhealthy);
});

test("preserves pending migrations", async () => {
  const health = { ...ready, status: "error", migrations: "pending" };
  const result = await fetchBackendHealth("http://api:8000", async () => Response.json(health, { status: 503 }));
  assert.deepEqual(result.health, health);
});

for (const [name, fetcher] of Object.entries({
  unreachable: async () => { throw new Error("connection refused"); },
  timeout: async () => { throw new DOMException("timed out", "TimeoutError"); },
  malformed: async () => Response.json({ status: "ok" }),
  inconsistent: async () => Response.json({ ...ready, database: "error" }),
  serverError: async () => Response.json(ready, { status: 500 }),
})) {
  test(`reports ${name} as unavailable`, async () => {
    const result = await fetchBackendHealth("http://api:8000", fetcher);
    assert.equal(result.health, null);
    assert.ok(result.error);
  });
}
