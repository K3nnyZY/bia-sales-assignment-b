import { expect, test } from "@playwright/test";

test("run billing assistant, inspect persisted trace, and reject cross-customer access", async ({
  page,
}) => {
  await page.goto("/playground");
  await page
    .getByLabel("Token de acceso")
    .fill(process.env.DEMO_CREATOR_TOKEN!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Playground de facturación." }),
  ).toBeVisible();
  await expect(page.getByLabel("Modo de ejecución")).toHaveValue(
    "deterministic",
  );
  await expect(
    page.getByText(
      "Plantilla de prueba calculada desde las facturas; sin llamada a un LLM.",
    ),
  ).toBeVisible();
  await page.getByLabel("Consulta").selectOption("invoice");
  await page.getByLabel("Factura", { exact: true }).fill("INV-1002");
  await page
    .getByRole("button", { name: "Ejecutar agente", exact: true })
    .click();
  await expect(page.getByTestId("run-status")).toHaveText("completed");
  await expect(page.locator(".runtime-answer")).toContainText("344400.00 COP");
  await expect(
    page.getByRole("cell", { name: "previous", exact: true }),
  ).toHaveCount(0);
  const invoiceRunText = await page.locator(".hash").textContent();
  await page.getByLabel("Consulta").selectOption("compare");
  await page
    .getByRole("button", { name: "Ejecutar agente", exact: true })
    .click();
  await expect(page.locator(".hash")).not.toHaveText(invoiceRunText!);
  await expect(page.getByTestId("run-status")).toHaveText("completed");
  await expect(page.locator(".runtime-answer")).toContainText("64400.00 COP");
  await expect(page.locator(".runtime-answer")).toContainText(
    "sin llamada a un proveedor",
  );
  await expect(
    page.getByRole("cell", { name: "invoice", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "validate_output", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "invoice-lookup-v3 · v3.0.0" }),
  ).toBeVisible();
  await expect(
    page.getByText("Tokens de entrada: No reportados", { exact: false }),
  ).toBeVisible();
  const compareRunId = (await page.locator(".hash").textContent())!.match(
    /run-[a-f0-9]{32}/,
  )![0];
  await page.getByLabel("Factura", { exact: true }).fill("INV-2002");
  await page
    .getByRole("button", { name: "Ejecutar agente", exact: true })
    .click();
  await expect(page.getByTestId("run-status")).toHaveText("denied");
  await expect(
    page.getByRole("alert").filter({ hasText: "INVOICE_NOT_ACCESSIBLE" }),
  ).toBeVisible();
  await expect(page.locator(".runtime-answer")).not.toContainText("123000");
  await page.getByLabel("Factura", { exact: true }).fill("INV-1001");
  await page
    .getByRole("button", { name: "Ejecutar agente", exact: true })
    .click();
  await expect(page.getByTestId("run-status")).toHaveText("escalated");
  await expect(
    page.getByRole("alert").filter({ hasText: "PREVIOUS_INVOICE_UNAVAILABLE" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "failure", exact: true }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByLabel("Token de acceso")
    .fill(process.env.DEMO_CREATOR_TOKEN!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page
      .locator(".version-button")
      .filter({ hasText: "deterministic · denied" })
      .first(),
  ).toBeVisible();
  await page
    .locator(".version-button")
    .filter({ hasText: compareRunId })
    .click();
  await expect(page.getByTestId("run-status")).toHaveText("completed");
  await expect(page.locator(".runtime-answer")).toContainText("64400.00 COP");
});
