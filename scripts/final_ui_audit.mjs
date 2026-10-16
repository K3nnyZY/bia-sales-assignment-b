// Delivery audit only: uses real UI/APIs and creates synthetic records. No provider generation.
import { chromium, expect } from "@playwright/test";
import fs from "node:fs";
import assert from "node:assert/strict";
const privateCredentials = process.env.BIA_CREDENTIALS_FILE
  ? JSON.parse(fs.readFileSync(process.env.BIA_CREDENTIALS_FILE, "utf8"))
  : null;
if (!privateCredentials) process.loadEnvFile(new URL("../.env", import.meta.url));
function tokenFor(role) {
  if (privateCredentials) {
    const key = role === "ADMIN" ? "administrator" : role.toLowerCase();
    assert.ok(privateCredentials[key]?.token, `Missing private credential for ${key}`);
    return privateCredentials[key].token;
  }
  return process.env[`DEMO_${role}_TOKEN`];
}
const base = process.env.E2E_BASE_URL || `http://127.0.0.1:${process.env.WEB_PORT || "3000"}`;
if (!/^https:\/\//.test(base) && !/^http:\/\/(127\.0\.0\.1|localhost):/.test(base)) {
  throw new Error("Remote smoke tests require HTTPS");
}
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || "chrome", headless: true });
const page = await browser.newPage({ baseURL: base });
page.setDefaultTimeout(15000);
const id = `final-audit-${Date.now()}`;
const proof = { agent_id: id, document_id: id, steps: [] };
async function login(role, path) {
  await page.goto(path);
  await page
    .getByLabel("Token de acceso")
    .fill(tokenFor(role));
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Salir", exact: true }),
  ).toBeVisible();
}
try {
  await login("CREATOR", "/knowledge");
  await page
    .getByLabel("Colección", { exact: true })
    .selectOption("billing-reference");
  await page.getByText("Crear documento", { exact: true }).first().click();
  await page.getByLabel("ID de documento", { exact: true }).fill(id);
  await page
    .getByLabel("Título", { exact: true })
    .fill("FAQ sintética final de entrega");
  await page
    .getByRole("button", { name: "Crear documento", exact: true })
    .click();
  await expect(page.getByLabel("Documento", { exact: true })).toHaveValue(id);
  await page
    .getByLabel("Archivo PDF, TXT o Markdown")
    .setInputFiles({
      name: "final.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(
        `# Auditoria ${id}\nLa facturacion sintetica compara consumo de energia y tarifa. En septiembre de 2026 la tarifa de referencia es 820 COP/kWh. Los calculos de facturas se realizan en Python.`,
      ),
    });
  await page
    .getByLabel("Fuente", { exact: true })
    .fill("synthetic://final/" + id);
  await page
    .getByRole("button", { name: "Cargar versión", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Ejecutar ingesta v1", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Ingesta: ready");
  proof.steps.push("document_upload_and_ingestion_ui");
  await login("ADMIN", "/knowledge");
  await page
    .getByLabel("Colección", { exact: true })
    .selectOption("billing-reference");
  await page.getByLabel("Documento", { exact: true }).selectOption(id);
  await page
    .getByRole("button", { name: "Aprobar documento v1", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Versión aprobada");
  await login("CREATOR", "/knowledge");
  await page
    .getByLabel("Colección", { exact: true })
    .selectOption("billing-reference");
  await page.getByLabel("Consulta", { exact: true }).fill("Auditoria " + id);
  await page
    .getByRole("button", { name: "Buscar evidencia", exact: true })
    .click();
  await page
    .getByRole("button", { name: `Verificar ${id}@1#chunk-0`, exact: true })
    .click();
  await expect(
    page.getByText("Fragmento verificado por backend", { exact: true }),
  ).toBeVisible();
  proof.steps.push("document_approval_search_citation_ui");
  await page.getByRole("link", { name: "Agentes", exact: true }).click();
  await page.getByLabel("Identificador", { exact: true }).fill(id);
  await page
    .getByLabel("Nombre", { exact: true })
    .fill("Final audit billing RAG");
  await page.getByLabel("Departamento", { exact: true }).fill("quality");
  await page.getByRole("button", { name: "Crear agente", exact: true }).click();
  await expect(page).toHaveURL(new RegExp("/agents/" + id + "$"));
  await page
    .getByLabel("Objetivo", { exact: true })
    .fill("Explicar facturas sinteticas con evidencia aprobada");
  await page
    .getByLabel("Instrucciones", { exact: true })
    .fill("Usar herramientas autorizadas y calculos Python.");
  await page.getByLabel("Workflow", { exact: true }).selectOption("billing");
  await page
    .getByLabel("Modelo aprobado")
    .selectOption("synthetic-balanced-v1");
  await page.getByLabel(/get_customer_invoice · v3.0.0/).check();
  await page.getByLabel(/get_previous_invoice · v1.0.0/).check();
  await page.getByLabel(/search_billing_knowledge · v2.0.0/).check();
  await page.getByLabel("Referencias de conocimiento").fill(
    JSON.stringify({
      documents: [
        { document_id: "billing-tariffs-rag", version: 1 },
        { document_id: "billing-faq-rag", version: 1 },
        { document_id: id, version: 1 },
      ],
    }),
  );
  await page.getByLabel("Máximo de pasos", { exact: true }).fill("12");
  await page
    .getByRole("button", { name: "Crear primera versión", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Versión 1 · draft", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Crear snapshot", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Versión 1 · snapshot", exact: true }),
  ).toBeVisible();
  proof.steps.push("agent_configuration_and_frozen_snapshot_ui");
  await page.getByRole("link", { name: "Evaluaciones", exact: true }).click();
  await page.getByLabel("Agente", { exact: true }).selectOption(id);
  await page
    .getByRole("button", { name: "Evaluar versión", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Evaluación passed: 9/9" }),
  ).toBeVisible({ timeout: 90000 });
  await page
    .getByRole("button", { name: "Solicitar aprobación", exact: true })
    .click();
  await expect(page.getByTestId("governance-stage")).toHaveText(
    "pending_approval",
  );
  proof.steps.push("evaluation_9_of_9_and_submission_ui");
  await login("APPROVER", "/evaluations");
  await page.getByLabel("Agente", { exact: true }).selectOption(id);
  await expect(page.getByTestId("governance-stage")).toHaveText(
    "pending_approval",
  );
  await page
    .getByLabel("Motivo de decisión o rollback")
    .fill("Auditoria final: snapshot y nueve controles RAG revisados");
  await page.getByRole("button", { name: "Aprobar", exact: true }).click();
  await expect(page.getByTestId("governance-stage")).toHaveText("approved");
  await page
    .getByRole("button", { name: "Publicar versión", exact: true })
    .click();
  await expect(page.getByTestId("governance-stage")).toHaveText("published");
  proof.steps.push("independent_approval_and_publication_ui");
  await login("CREATOR", "/playground");
  await page.getByLabel("Versión del agente").selectOption(id + "@1");
  await page.getByLabel("Canal de ejecución").selectOption("published");
  await page.getByLabel("Consulta").selectOption("compare");
  const pending = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/studio/runs" &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Ejecutar agente", exact: true })
    .click();
  const response = await pending;
  assert.equal(response.status(), 201);
  const run = await response.json();
  assert.equal(run.status, "completed");
  assert.equal(run.channel, "published");
  assert.equal(run.calculations.difference_cop, "64400.00");
  assert.equal(run.calculations.percentage_change, "23.00");
  assert(run.references.includes(id + "@1#chunk-0"));
  await expect(page.getByTestId("run-status")).toHaveText("completed");
  await expect(
    page.getByText("hybrid-semantic", { exact: false }).first(),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Abrir Trace Viewer", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Traces & Audit.", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".runtime-answer")).toHaveText(run.answer);
  await expect(
    page.getByRole("cell", { name: "validate_output", exact: true }),
  ).toBeVisible();
  const headers = { Authorization: "Bearer " + tokenFor("CREATOR") };
  const trace = await (
    await page.request.get(`/api/studio/runs/${run.id}/trace`, { headers })
  ).json();
  assert.equal(trace.events.length, 9);
  assert.equal(trace.tool_calls.length, 3);
  assert.equal(trace.knowledge_searches.length, 1);
  assert.equal(trace.run.config_hash, run.config_hash);
  proof.steps.push("published_langgraph_invoice_rag_and_trace_ui");
  proof.run = run;
  proof.trace = trace;
  await page.screenshot({ path: "/tmp/bia-final-ui.png", fullPage: true });
  fs.writeFileSync(
    "/tmp/bia-final-audit-ui.json",
    JSON.stringify(proof, null, 2),
  );
  console.log(
    JSON.stringify(
      {
        agent_id: id,
        run_id: run.id,
        channel: run.channel,
        steps: proof.steps,
        status: "passed",
      },
      null,
      2,
    ),
  );
} catch (error) {
  fs.writeFileSync(
    "/tmp/bia-final-audit-ui-partial.json",
    JSON.stringify(proof, null, 2),
  );
  await page.screenshot({
    path: "/tmp/bia-final-ui-error.png",
    fullPage: true,
  });
  throw error;
} finally {
  await browser.close();
}
