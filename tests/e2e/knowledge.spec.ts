import { expect, test, type Page } from "@playwright/test";
import type { RunTrace } from "../../apps/web/src/lib/runtime";

async function login(page: Page, role: "CREATOR" | "ADMIN", path: string) {
  await page.goto(path);
  await page
    .getByLabel("Token de demostración")
    .fill(process.env[`DEMO_${role}_TOKEN`]!);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Salir", exact: true }),
  ).toBeVisible();
}

test("upload, ingest, approve, search, verify citations and inspect a real RAG trace", async ({
  page,
}, testInfo) => {
  test.setTimeout(90000);
  const id = `e2e-rag-${Date.now()}`;
  await login(page, "CREATOR", "/knowledge");
  // Isolate the search corpus through the real UI. Repeated runs must not depend
  // on the ranking of equally relevant documents accumulated by earlier tests.
  await page
    .locator("summary")
    .filter({ hasText: /^Crear colección$/ })
    .click();
  await page.getByLabel("ID de colección", { exact: true }).fill(id);
  await page
    .getByLabel("Nombre de colección", { exact: true })
    .fill("Knowledge E2E");
  await page
    .getByRole("button", { name: "Crear colección", exact: true })
    .click();
  await expect(page.getByLabel("Colección", { exact: true })).toHaveValue(id);
  await page.getByText("Crear documento", { exact: true }).first().click();
  await page.getByLabel("ID de documento", { exact: true }).fill(id);
  await page
    .getByLabel("Título", { exact: true })
    .fill("FAQ sintética de energía E2E");
  await page
    .getByRole("button", { name: "Crear documento", exact: true })
    .click();
  await expect(page.getByLabel("Documento", { exact: true })).toHaveValue(id);
  await page.getByLabel("Archivo PDF, TXT o Markdown").setInputFiles({
    name: "faq.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      `# FAQ sintética E2E ${id}\nEl cargo de electricidad usa el consumo de energía y la tarifa del período. Datos sintéticos de facturación.`,
    ),
  });
  await page
    .getByLabel("Fuente", { exact: true })
    .fill("synthetic://e2e/" + id);
  await page
    .getByRole("button", { name: "Cargar versión", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Ejecutar ingesta v1", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Ejecutar ingesta v1", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Ingesta: ready");
  await login(page, "ADMIN", "/knowledge");
  await page.getByLabel("Colección", { exact: true }).selectOption(id);
  await page.getByLabel("Documento", { exact: true }).selectOption(id);
  await page
    .getByRole("button", { name: "Aprobar documento v1", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Versión aprobada");
  await login(page, "CREATOR", "/knowledge");
  await page.getByLabel("Colección", { exact: true }).selectOption(id);
  await page
    .getByLabel("Consulta", { exact: true })
    .fill("FAQ sintética E2E cargo electricidad consumo energía tarifa");
  await page
    .getByRole("button", { name: "Buscar evidencia", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: `Verificar ${id}@1#chunk-0`,
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: `Verificar ${id}@1#chunk-0`, exact: true })
    .click();
  await expect(
    page.getByText("Fragmento verificado por backend", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Playground", exact: true }).click();
  const catalogResponse = await page.request.get(
    "/api/studio/agents/billing-assistant/versions",
    { headers: { Authorization: `Bearer ${process.env.DEMO_CREATOR_TOKEN}` } },
  );
  const catalog = (await catalogResponse.json()) as {
    number: number;
    status: string;
    model_id: string;
    configuration: { knowledge?: object };
  }[];
  const chosen = catalog
    .filter(
      (v) =>
        v.status === "snapshot" &&
        v.model_id === "synthetic-balanced-v1" &&
        v.configuration.knowledge,
    )
    .sort((a, b) => b.number - a.number)[0];
  expect(chosen).toBeTruthy();
  const version = `billing-assistant@${chosen.number}`;
  await page.getByLabel("Versión del agente").selectOption(version);
  await page.getByLabel("Consulta").selectOption("compare");
  await page.getByLabel("Factura", { exact: true }).fill("INV-1002");
  const responsePromise = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/studio/runs") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Ejecutar agente", exact: true })
    .click();
  const run = await (await responsePromise).json();
  expect(run.status).toBe("completed");
  expect(run.calculations.difference_cop).toBe("64400.00");
  expect(
    run.references.some((r: string) => r.includes("#chunk-")),
  ).toBeTruthy();
  const traceResponse = await page.request.get(
    `/api/studio/runs/${run.id}/trace`,
    { headers: { Authorization: `Bearer ${process.env.DEMO_CREATOR_TOKEN}` } },
  );
  const trace = (await traceResponse.json()) as RunTrace;
  expect(trace.knowledge_searches.length).toBe(1);
  expect(trace.events.length).toBe(9);
  await expect(
    page.getByText("hybrid-semantic", { exact: false }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("billing-tariffs-rag@1#chunk-0", { exact: false }).first(),
  ).toBeVisible();
  await testInfo.attach("backend-rag-trace", {
    body: JSON.stringify(trace, null, 2),
    contentType: "application/json",
  });
});
