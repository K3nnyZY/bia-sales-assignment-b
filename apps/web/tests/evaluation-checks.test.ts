import assert from "node:assert/strict";
import test from "node:test";
import { checkMetadata, checkObservations, checkStatus, evaluationChecks, type CheckResult } from "../src/lib/evaluation-checks.ts";
import { helpCatalog } from "../src/lib/help.ts";

const result: CheckResult = { check: "invoice", critical: true, passed: false, error_code: null, details: {}, run_id: null, duration_ms: 0 };

test("all nine billing checks have meaningful metadata and unknown checks fall back", () => {
  assert.equal(Object.keys(evaluationChecks).length, 9);
  for (const key of Object.keys(evaluationChecks)) {
    const metadata = checkMetadata(key);
    assert.notEqual(metadata.name, key);
    assert.ok(metadata.purpose.length > 20 && metadata.expected.length > 20);
  }
  for (const key of ["new-check-v2", "__proto__", "constructor"]) {
    assert.equal(checkMetadata(key).name, "Prueba adicional");
    assert.match(checkMetadata(key).expected, /No disponible/);
  }
  assert.equal(Object.keys(helpCatalog).length, 10);
});

test("status separates assertions from reported infrastructure errors without guessing", () => {
  assert.equal(checkStatus({ ...result, passed: true }), "PASS");
  assert.equal(checkStatus({ ...result, error_code: "ASSERTION_FAILED" }), "FAIL");
  assert.equal(checkStatus({ ...result, error_code: "UNRECOGNIZED_CODE" }), "FAIL");
  assert.equal(checkStatus({ ...result, error_code: "CHECK_ERROR" }), "ERROR");
  assert.equal(checkStatus({ ...result, error_code: "EVALUATION_TIMEOUT" }), "ERROR");
  assert.equal(checkStatus({ ...result, details: { status: "failed", runtime_error: "PROVIDER_UNAVAILABLE" } }), "ERROR");
  assert.equal(checkStatus({ ...result, details: { status: "denied" } }), "FAIL");
});

test("readable observations use only reported backend values", () => {
  assert.deepEqual(checkObservations(result), []);
  assert.deepEqual(checkObservations({ ...result, details: { status: "completed", tool_calls: 2, nodes: 6, runtime_error: null } }), [
    { label: "Ejecución", value: "Completada" },
    { label: "Llamadas a herramientas", value: "2" },
    { label: "Pasos registrados", value: "6" },
    { label: "Error del runtime", value: "Sin error informado" },
  ]);
  assert.deepEqual(checkObservations({ ...result, details: { future_value: 42 } }), []);
});
