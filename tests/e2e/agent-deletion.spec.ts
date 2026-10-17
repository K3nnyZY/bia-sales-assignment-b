import { expect, test } from "@playwright/test";

test("draft deletion confirms, survives a stale revision, and refreshes the registry", async ({ page }) => {
  const id = `e2e-delete-${Date.now()}`;
  const headers = { Authorization: `Bearer ${process.env.DEMO_ADMIN_TOKEN}` };
  await page.goto("/agents");
  await page.getByLabel("Token de acceso").fill(process.env.DEMO_ADMIN_TOKEN!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByLabel("Identificador", { exact: true }).fill(id);
  await page.getByLabel("Nombre", { exact: true }).fill("Borrador para eliminar");
  await page.getByLabel("Departamento", { exact: true }).fill("Quality");
  await page.getByRole("button", { name: "Crear agente", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/agents/${id}$`));
  await page.getByLabel("Ayuda sobre Agent", { exact: true }).click();
  await expect(page.locator(".context-help p").filter({ hasText: /Crear un borrador no lo publica/ })).toBeVisible();
  await page.getByRole("button", { name: "Eliminar agente", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Eliminar agente", exact: true });
  await expect(dialog).toContainText("Borrador para eliminar");
  await expect(dialog).toContainText("irreversible");
  await dialog.getByRole("button", { name: "Cancelar", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect((await page.request.get(`/api/studio/agents/${id}`, { headers })).status()).toBe(200);
  await page.getByRole("button", { name: "Salir", exact: true }).click();
  await page.getByLabel("Token de acceso").fill(process.env.DEMO_VIEWER_TOKEN!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Borrador para eliminar", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Eliminar agente", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Salir", exact: true }).click();
  await page.getByLabel("Token de acceso").fill(process.env.DEMO_ADMIN_TOKEN!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("button", { name: "Eliminar agente", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  // A second editor changes metadata after this page loaded.
  expect((await page.request.patch(`/api/studio/agents/${id}`, {
    headers, data: { expected_revision: 1, description: "Edición concurrente" },
  })).status()).toBe(200);
  await page.getByRole("button", { name: "Eliminar agente", exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await dialog.getByRole("button", { name: "Eliminar definitivamente", exact: true }).click();
  await expect(page.locator(".error[role=alert]")).toContainText("Recarga los datos");
  expect((await page.request.get(`/api/studio/agents/${id}`, { headers })).status()).toBe(200);
  await expect(page.getByText(/revisión 2/).first()).toBeVisible();
  await page.getByRole("button", { name: "Eliminar agente", exact: true }).click();
  await dialog.getByRole("button", { name: "Eliminar definitivamente", exact: true }).click();
  await expect(page).toHaveURL(/\/agents$/);
  await expect(page.getByRole("status").filter({ hasText: "eliminado correctamente" })).toBeVisible();
  await expect(page.locator(`a[href="/agents/${id}"]`)).toHaveCount(0);
  expect((await page.request.get(`/api/studio/agents/${id}`, { headers })).status()).toBe(404);
});
