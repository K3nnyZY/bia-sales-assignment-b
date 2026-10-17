import { expect, test, type Page } from "@playwright/test";
import type { Metrics } from "../../apps/web/src/lib/governance";
import type { RunTrace } from "../../apps/web/src/lib/runtime";

async function login(
  page: Page,
  role: "CREATOR" | "APPROVER" | "AUDITOR" | "VIEWER",
  path: string,
) {
  await page.goto(path);
  await page
    .getByLabel("Token de acceso")
    .fill(process.env[`DEMO_${role}_TOKEN`]!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Salir", exact: true }),
  ).toBeVisible();
}

test("configure, evaluate, independently approve, publish, execute and audit", async ({
  page,
}, testInfo) => {
  test.setTimeout(90000);
  page.setDefaultTimeout(10000);
  const id = `e2e-quality-${Date.now()}`;
  await login(page, "CREATOR", "/agents");
  await page.getByLabel("Identificador", { exact: true }).fill(id);
  await page.getByLabel("Nombre", { exact: true }).fill("E2E Governed Billing");
  await page.getByLabel("Departamento", { exact: true }).fill("Quality");
  await page.getByRole("button", { name: "Crear agente", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/agents/${id}$`));
  await page
    .getByRole("textbox", { name: "Objetivo", exact: true })
    .fill("Explicar facturas sintéticas autorizadas");
  await page
    .getByRole("textbox", { name: "Instrucciones", exact: true })
    .fill("Usar evidencia autorizada y cálculos Python.");
  await page.getByLabel("Workflow", { exact: true }).selectOption("billing");
  await page
    .getByLabel("Modelo aprobado")
    .selectOption("synthetic-balanced-v1");
  await page.getByLabel(/get_customer_invoice · v3.0.0/).check();
  await page.getByLabel(/get_previous_invoice · v1.0.0/).check();
  await page.getByLabel(/search_billing_knowledge · v1.0.0/).check();
  await page.getByLabel("Máximo de pasos", { exact: true }).fill("12");
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
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
  await page.getByRole("link", { name: "Evaluaciones", exact: true }).click();
  await page.getByLabel("Agente", { exact: true }).selectOption(id);
  await page
    .getByRole("button", { name: "Evaluar versión", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Evaluación passed: 9/9" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "PASS", exact: true }),
  ).toHaveCount(9);
  const invoiceCheck = page.locator("tr").filter({ has: page.locator("summary").filter({ hasText: "Consulta de factura autorizada" }) });
  await invoiceCheck.getByText("Consulta de factura autorizada", { exact: true }).click();
  await expect(invoiceCheck).toContainText("Resultado esperado (contrato de la prueba)");
  await expect(invoiceCheck).toContainText("Resultado obtenido (backend)");
  await expect(invoiceCheck).toContainText("Ejecución: Completada");
  await expect(invoiceCheck).toContainText("Llamadas a herramientas: 2");
  await invoiceCheck.getByText("Datos técnicos del backend", { exact: true }).click();
  await expect(invoiceCheck.locator("pre")).toContainText('"status": "completed"');
  await expect(invoiceCheck.getByRole("link", { name: "Abrir traza" })).toBeVisible();
  await page
    .getByRole("button", { name: "Solicitar aprobación", exact: true })
    .click();
  await expect(page.getByTestId("governance-stage")).toHaveText(
    "pending_approval",
  );
  await expect(
    page.getByRole("button", { name: "Aprobar", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Salir", exact: true }).click();
  await page
    .getByLabel("Token de acceso")
    .fill(process.env.DEMO_APPROVER_TOKEN!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByLabel("Agente", { exact: true }).selectOption(id);
  await expect(page.getByTestId("governance-stage")).toHaveText(
    "pending_approval",
  );
  await page
    .getByLabel("Motivo de decisión o rollback")
    .fill("Revisados los nueve resultados y trazas sintéticas");
  await page.getByRole("button", { name: "Aprobar", exact: true }).click();
  await expect(page.getByTestId("governance-stage")).toHaveText("approved");
  await page
    .getByRole("button", { name: "Publicar versión", exact: true })
    .click();
  await expect(page.getByTestId("governance-stage")).toHaveText("published");
  await login(page, "CREATOR", "/playground");
  await page.getByLabel("Versión del agente").selectOption(`${id}@1`);
  await page.getByLabel("Canal de ejecución").selectOption("published");
  await page.getByLabel("Consulta").selectOption("compare");
  await page
    .getByRole("button", { name: "Ejecutar agente", exact: true })
    .click();
  await expect(page.getByTestId("run-status")).toHaveText("completed");
  await expect(page.locator(".runtime-answer")).toContainText("64400.00 COP");
  const runId = (await page.locator(".hash").textContent())!.match(
    /run-[a-f0-9]{32}/,
  )![0];
  const observedMetrics = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/studio/metrics" && r.status() === 200,
  );
  const observedTrace = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === `/api/studio/runs/${runId}/trace` &&
      r.status() === 200,
  );
  await login(page, "AUDITOR", `/traces?run=${runId}`);
  const metrics: Metrics = await (await observedMetrics).json();
  const trace: RunTrace = await (await observedTrace).json();
  const directTrace = await page.request.get(
    `http://127.0.0.1:${process.env.API_PORT || "8000"}/api/v1/runs/${runId}/trace`,
    { headers: { Authorization: `Bearer ${process.env.DEMO_AUDITOR_TOKEN}` } },
  );
  expect(directTrace.status()).toBe(200);
  expect(await directTrace.json()).toEqual(trace);
  expect(trace.run.channel).toBe("published");
  expect(trace.events).toHaveLength(9);
  expect(trace.tool_calls).toHaveLength(3);
  await expect(page.locator(".hash")).toContainText(trace.run.config_hash);
  await expect(page.locator(".runtime-answer")).toHaveText(trace.run.answer!);
  for (const [label, count] of [
    ["Ejecuciones", metrics.runs],
    ["Completadas", metrics.completed],
    ["Fallidas", metrics.failed],
    ["Denegadas", metrics.denied],
    ["Escaladas", metrics.escalated],
    ["Herramientas", metrics.tool_calls],
    ["Errores de herramientas", metrics.tool_errors],
  ] as const) {
    const card = page.locator(".metric-grid > div").filter({
      has: page.locator("span").filter({ hasText: new RegExp(`^${label}$`) }),
    });
    await expect(card.locator("strong")).toHaveText(String(count));
  }
  expect(metrics.evaluation_runs_excluded).toBe(true);
  const history = await page.request.get(
    `/api/studio/audit-events?agent_id=${id}`,
    {
      headers: { Authorization: `Bearer ${process.env.DEMO_AUDITOR_TOKEN}` },
    },
  );
  expect(history.status()).toBe(200);
  expect(
    (await history.json()).some(
      (e: { action: string; agent_id: string }) =>
        e.action === "agent.created" && e.agent_id === id,
    ),
  ).toBe(true);
  await expect(
    page.locator("summary").filter({ hasText: `agent.created · ${id}` }),
  ).toBeVisible();
  await testInfo.attach("backend-observability.json", {
    body: JSON.stringify({ agent_id: id, metrics, trace }, null, 2),
    contentType: "application/json",
  });
  await expect(
    page.getByRole("heading", { name: "Traza persistida", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "validate_output", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".runtime-answer")).toContainText("64400.00 COP");
  await expect(
    page.getByText("version.published", { exact: false }).first(),
  ).toBeVisible();
  await page.reload();
  await page
    .getByLabel("Token de acceso")
    .fill(process.env.DEMO_AUDITOR_TOKEN!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.locator(".runtime-answer")).toContainText("64400.00 COP");
});

test("metadata history survives empty-agent deletion and remains scoped in Next.js", async ({
  page,
}) => {
  const id = `e2e-history-${Date.now()}`;
  await login(page, "CREATOR", "/agents");
  await page.getByLabel("Identificador", { exact: true }).fill(id);
  await page
    .getByLabel("Nombre", { exact: true })
    .fill("Auditable empty agent");
  await page.getByLabel("Departamento", { exact: true }).fill("Quality");
  await page.getByRole("button", { name: "Crear agente", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/agents/${id}$`));
  const headers = { Authorization: `Bearer ${process.env.DEMO_CREATOR_TOKEN}` };
  const edited = await page.request.patch(`/api/studio/agents/${id}`, {
    headers,
    data: { expected_revision: 1, description: "Auditable metadata edit" },
  });
  expect(edited.status()).toBe(200);
  const agent = await edited.json();
  const deleted = await page.request.delete(
    `/api/studio/agents/${id}?expected_revision=${agent.revision}`,
    { headers: { Authorization: `Bearer ${process.env.DEMO_ADMIN_TOKEN}` } },
  );
  expect(deleted.status()).toBe(204);
  await page.getByRole("link", { name: "Trazas", exact: true }).click();
  for (const action of ["agent.created", "agent.updated", "agent.deleted"]) {
    const summary = page
      .locator("summary")
      .filter({ hasText: `${action} · ${id}` });
    await expect(summary).toBeVisible();
    await expect(summary).not.toContainText("Catálogo");
  }
  const scoped = await page.request.get(
    `/api/studio/audit-events?agent_id=${id}`,
    { headers },
  );
  expect(
    (await scoped.json()).map((e: { action: string }) => e.action).filter((action: string) => action.startsWith("agent.")).sort(),
  ).toEqual(["agent.created", "agent.deleted", "agent.updated"]);
  await login(page, "VIEWER", "/traces");
  await expect(
    page.getByText("No hay eventos visibles.", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("summary").filter({ hasText: id })).toHaveCount(0);
  const denied = await page.request.get(
    `/api/studio/audit-events?agent_id=${id}`,
    {
      headers: { Authorization: `Bearer ${process.env.DEMO_VIEWER_TOKEN}` },
    },
  );
  expect(await denied.json()).toEqual([]);
});
