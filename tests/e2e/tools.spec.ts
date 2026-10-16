import { expect, test } from "@playwright/test";
import type { CatalogTool } from "../../apps/web/src/lib/studio";

test("administrator adds implemented tools and independent custom versions from the frontend", async ({ page }) => {
  await page.goto("/tools");
  await page.getByLabel("Token de acceso").fill(process.env.DEMO_VIEWER_TOKEN!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Catálogo aprobado", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Añadir herramienta", exact: true })).toHaveCount(0);
  const denied = await page.request.get("/api/studio/tool-templates", {
    headers: { Authorization: `Bearer ${process.env.DEMO_VIEWER_TOKEN}`, "X-Role": "administrator" },
  });
  expect(denied.status()).toBe(403);
  await page.getByRole("button", { name: "Salir", exact: true }).click();
  await page.getByLabel("Token de acceso").fill(process.env.DEMO_ADMIN_TOKEN!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  const headers = { Authorization: `Bearer ${process.env.DEMO_ADMIN_TOKEN}` };
  const definitions = await page.request.get("/api/studio/tool-templates", { headers });
  expect(definitions.status()).toBe(200);
  const templates: CatalogTool[] = await definitions.json();
  expect(templates).toHaveLength(4);
  const existing: CatalogTool[] = await (await page.request.get("/api/studio/tools?approved_only=false", { headers })).json();
  await page.getByRole("button", { name: "Añadir herramienta", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Añadir versión de herramienta", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".tool-template")).toHaveCount(4);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  for (const tool of templates) {
    const add = page.getByRole("button", { name: `Añadir ${tool.name} v${tool.version}`, exact: true });
    await expect(add).toBeVisible();
    if (existing.some((item) => item.id === tool.id)) {
      await expect(add).toBeDisabled();
    } else {
      await add.click();
      await expect(page.locator(".success[role=status]")).toContainText("registrada como pendiente");
      await expect(add).toBeDisabled();
      const persisted = await page.request.get(`/api/studio/tools/${tool.id}`, { headers });
      expect(await persisted.json()).toEqual(tool);
    }
  }
  // The manual path can register another version without changing the first.
  const id = `e2e-tool-${Date.now()}`;
  const definition = { ...templates[0], id, name: id.replaceAll("-", "_"), version: "1.0.0" };
  const register = async (spec: typeof definition) => {
    await page.getByLabel("Contrato JSON").fill(JSON.stringify(spec));
    await page.getByRole("button", { name: "Registrar en catálogo", exact: true }).click();
    const record = page.locator("article").filter({
      has: page.getByText(`Ver contrato de ${spec.id}`, { exact: true }),
    });
    await expect(record.locator(".badge")).toHaveText("pending");
    return record;
  };
  const first = await register(definition);
  await first.getByRole("button", { name: "Aprobar", exact: true }).click();
  await expect(first.locator(".badge")).toHaveText("approved");
  const second = await register({ ...definition, id: `${id}-v2`, version: "2.0.0" });
  await expect(first.locator(".badge")).toHaveText("approved");
  expect(await (await page.request.get(`/api/studio/tools/${id}`, { headers })).json()).toEqual({ ...definition, status: "approved" });
  await first.getByRole("button", { name: `Eliminar ${id}`, exact: true }).click();
  await expect(first).toHaveCount(0);
  await second.getByRole("button", { name: `Eliminar ${id}-v2`, exact: true }).click();
  await expect(second).toHaveCount(0);
});
