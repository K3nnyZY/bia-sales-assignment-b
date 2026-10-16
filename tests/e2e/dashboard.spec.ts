import { expect, test, type Page } from "@playwright/test";
import type { Metrics } from "../../apps/web/src/lib/governance";

async function login(page: Page, role: "VIEWER" | "CREATOR") {
  await page.goto("/dashboard");
  await page
    .getByLabel("Token de demostración")
    .fill(process.env[`DEMO_${role}_TOKEN`]!);
  const pending = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/studio/metrics",
  );
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  return (await response.json()) as Metrics;
}

test("dashboard displays scoped backend metrics, empty states and real trace links", async ({
  page,
}) => {
  const viewer = await login(page, "VIEWER");
  expect(viewer.runs).toBe(0);
  await expect(page.getByTestId("metric-runs")).toHaveText("0");
  await expect(
    page.getByText("Aún no hay ejecuciones en tu alcance.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No hay uso de modelos registrado.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No hay colecciones visibles para tu identidad.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "No hay ejecuciones visibles. Usa el Playground con una versión autorizada.",
      { exact: true },
    ),
  ).toBeVisible();

  const metrics = await login(page, "CREATOR");
  for (const [key, value] of [
    ["runs", metrics.runs],
    ["completed", metrics.completed],
    ["denied", metrics.denied],
    ["tool-calls", metrics.tool_calls],
  ] as const) {
    await expect(page.getByTestId(`metric-${key}`)).toHaveText(String(value));
  }
  const headers = { Authorization: `Bearer ${process.env.DEMO_CREATOR_TOKEN}` };
  const agents = await (
    await page.request.get("/api/studio/agents", { headers })
  ).json();
  await expect(page.getByTestId("dashboard-agents")).toHaveText(
    String(agents.length),
  );
  const runLink = page.locator('a[href^="/traces?run="]').first();
  await expect(runLink).toBeVisible();
  await runLink.click();
  await expect(
    page.getByRole("heading", { name: "Traces & Audit.", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".runtime-answer")).toBeVisible();

  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(page).toHaveURL("/dashboard");
  await expect(
    page.getByRole("heading", {
      name: "Tu plataforma, en un vistazo.",
      exact: true,
    }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("metric-runs")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
