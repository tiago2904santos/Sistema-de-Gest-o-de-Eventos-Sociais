import { defineConfig, devices } from "@playwright/test";
import { VIEWPORTS } from "./tests/support/viewports";

/**
 * Laboratório de QA do agente.
 *
 * O servidor é o Django do laboratório (banco próprio em .lab/, relógio
 * ancorado em 2026-09-15 10:00 −03, integrações externas desligadas). Nada
 * aqui toca o banco de desenvolvimento de quem programa.
 */
const PORT = Number(process.env.LAB_PORT ?? 8031);
const BASE_URL = process.env.LAB_BASE_URL ?? `http://127.0.0.1:${PORT}`;
const desktop = { ...devices["Desktop Chrome"], viewport: VIEWPORTS.desktop, locale: "pt-BR", timezoneId: "America/Sao_Paulo" };

export default defineConfig({
  testDir: "./tests",
  outputDir: "reports/testing/artifacts",
  snapshotPathTemplate: "tests/visual/snapshots/{projectName}/{testFilePath}/{arg}{ext}",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: { maxDiffPixelRatio: 0.002, animations: "disabled", caret: "hide", scale: "css" },
  },
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: !!process.env.CI,
  reporter: [
    ["list"],
    ["html", { outputFolder: "reports/testing/playwright-html", open: "never" }],
    ["json", { outputFile: "reports/testing/playwright-results.json" }],
  ],
  globalSetup: "./tests/support/global-setup.ts",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
  },
  webServer: process.env.LAB_BASE_URL
    ? undefined
    : {
        command: `node scripts/agent/run.mjs serve --port ${PORT}`,
        url: `${BASE_URL}/_lab/health/`,
        reuseExistingServer: true,
        timeout: 240_000,
        stdout: "ignore",
        stderr: process.env.LAB_SERVER_LOG ? "pipe" : "ignore",
      },
  projects: [
    { name: "smoke", testDir: "./tests/smoke", use: desktop },
    { name: "e2e", testDir: "./tests/e2e", use: desktop },
    { name: "regression", testDir: "./tests/regression", use: desktop },
    { name: "a11y", testDir: "./tests/a11y", use: desktop },
    { name: "visual", testDir: "./tests/visual/specs", use: desktop },
    { name: "responsive", testDir: "./tests/responsive", use: { ...devices["Desktop Chrome"], locale: "pt-BR", timezoneId: "America/Sao_Paulo" } },
    { name: "perf", testDir: "./tests/perf", use: desktop, workers: 1 } as never,
  ],
});
