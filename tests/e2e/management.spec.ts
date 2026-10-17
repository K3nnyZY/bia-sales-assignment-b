import { expect, test, type Page } from "@playwright/test";

const creator = process.env.DEMO_CREATOR_TOKEN!;
const admin = process.env.DEMO_ADMIN_TOKEN!;
const viewer = process.env.DEMO_VIEWER_TOKEN!;

async function login(page: Page, token: string, path = "/agents") {
  await page.goto(path);
  await page.getByLabel("Token de acceso").fill(token);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Salir", exact: true }),
  ).toBeVisible();
}

test("create, edit, snapshot, clone and reload a persisted agent", async ({
  page,
}) => {
  const id = `e2e-agent-${Date.now()}`;
  await login(page, creator);
  await page.getByLabel("Identificador", { exact: true }).fill(id);
  await page.getByLabel("Nombre", { exact: true }).fill("E2E Billing Agent");
  await page
    .getByLabel("Departamento", { exact: true })
    .fill("Synthetic billing");
  await page.getByRole("button", { name: "Crear agente", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/agents/${id}$`));
  await page
    .getByRole("textbox", { name: "Objetivo", exact: true })
    .fill("Explain synthetic authorized invoices");
  await page
    .getByRole("textbox", { name: "Instrucciones", exact: true })
    .fill("Use the approved invoice contract.");
  await page
    .getByLabel("Modelo aprobado")
    .selectOption("synthetic-balanced-v1");
  await page.getByLabel(/get_customer_invoice · v1.0.0/).check();
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Versión 1 · draft", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Eliminar agente", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Nueva versión desde esta", exact: true })).toBeDisabled();
  await expect(page.locator("#new-version-reason")).toContainText("borrador");
  await page
    .getByRole("textbox", { name: "Instrucciones", exact: true })
    .fill("Updated approved instructions.");
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Crear snapshot", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Crear snapshot", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Versión 1 · snapshot", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Objetivo", exact: true }),
  ).toBeDisabled();
  const original = await page.request.get(
    `/api/studio/agents/${id}/versions/1`,
    { headers: { Authorization: `Bearer ${creator}` } },
  );
  expect(original.status()).toBe(200);
  const snapshot = await original.json();
  expect(snapshot.config_hash).toMatch(/^[a-f0-9]{64}$/);
  await page
    .getByRole("button", { name: "Nueva versión desde esta", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Versión 2 · draft", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Objetivo", exact: true })
    .fill("A different objective for version two");
  await page
    .getByRole("button", { name: "Guardar borrador", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Crear snapshot", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "v1 · snapshot", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Objetivo", exact: true }),
  ).toHaveValue("Explain synthetic authorized invoices");
  await expect(page.getByRole("button", { name: "Nueva versión desde esta", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "v2 · draft", exact: true }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Descartar borrador", exact: true }).click();
  await expect(page.getByRole("button", { name: "v2 · discarded", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "v1 · snapshot", exact: true }).click();
  await expect(page.getByRole("button", { name: "Nueva versión desde esta", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Nueva versión desde esta", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Versión 3 · draft", exact: true })).toBeVisible();
  await login(page, creator, `/agents/${id}`); // Reload removes the in-memory credential.
  await expect(
    page.getByRole("button", { name: "v1 · snapshot", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "v2 · discarded", exact: true }),
  ).toBeVisible();
  const persisted = await page.request.get(
    `/api/studio/agents/${id}/versions/1`,
    { headers: { Authorization: `Bearer ${creator}` } },
  );
  expect(await persisted.json()).toEqual(snapshot);
  await login(page, admin, `/agents/${id}`);
  await expect(page.getByRole("button", { name: "Eliminar agente", exact: true })).toHaveCount(0);
  await expect(page.locator("#agent-deletion-reason")).toContainText("snapshots congelados");
});

test("catalog management requires administrator identity", async ({ page }) => {
  await login(page, viewer, "/models");
  await expect(
    page.getByRole("heading", { name: "Catálogo aprobado" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Registrar en catálogo" }),
  ).toHaveCount(0);
  const denied = await page.request.patch(
    "/api/studio/models/synthetic-balanced-v1",
    {
      headers: { Authorization: `Bearer ${viewer}`, "X-Role": "administrator" },
      data: { status: "revoked" },
    },
  );
  expect(denied.status()).toBe(403);
  await page.getByRole("button", { name: "Salir", exact: true }).click();
  await page.getByLabel("Token de acceso").fill(admin);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  const catalogResponse = await page.request.get(
    "/api/studio/models?approved_only=false",
    { headers: { Authorization: `Bearer ${admin}` } },
  );
  expect(catalogResponse.ok()).toBeTruthy();
  const catalog: { profile: string; status: string }[] =
    await catalogResponse.json();
  const approvedProfiles = new Set(
    catalog
      .filter((item) => item.status === "approved")
      .map((item) => item.profile),
  );
  const freeProfile = ["advanced", "restricted", "economy", "balanced"].find(
    (profile) => !approvedProfiles.has(profile),
  );
  expect(
    freeProfile,
    "The catalog test requires one unassigned profile",
  ).toBeDefined();
  const id = `e2e-model-${Date.now()}`;
  const model = {
    id,
    name: id,
    provider: "synthetic",
    model_identifier: `synthetic/${id}`,
    release: "1",
    profile: freeProfile,
    capabilities: ["chat"],
    context_window: 10000,
    max_output_tokens: 1000,
    input_cost_per_million: "0",
    output_cost_per_million: "0",
    data_policy: "Synthetic browser test",
    status: "pending",
  };
  await page.getByLabel("Contrato JSON").fill(JSON.stringify(model));
  await page
    .getByRole("button", { name: "Registrar en catálogo", exact: true })
    .click();
  const record = page
    .locator("article")
    .filter({ has: page.getByRole("heading", { name: id, exact: true }) });
  await expect(record).toBeVisible();
  await record.getByRole("button", { name: "Aprobar", exact: true }).click();
  await expect(record.locator(".badge")).toHaveText("approved");
  await record.getByRole("button", { name: "Revocar", exact: true }).click();
  await expect(record.locator(".badge")).toHaveText("revoked");
  await record
    .getByRole("button", { name: `Eliminar ${id}`, exact: true })
    .click();
  await expect(record).toHaveCount(0);
});
