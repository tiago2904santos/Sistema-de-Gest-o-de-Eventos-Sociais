import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

export type AxeSummary = {
  url: string;
  counts: Record<"critical" | "serious" | "moderate" | "minor", number>;
  violations: { id: string; impact: string | null; help: string; helpUrl: string; nodes: number; targets: string[] }[];
};

/** Roda o axe (WCAG 2.0/2.1/2.2 A+AA + boas práticas) e resume por impacto. */
export async function runAxe(page: Page, opts: { include?: string; exclude?: string[] } = {}): Promise<AxeSummary> {
  let b = new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]);
  if (opts.include) b = b.include(opts.include);
  for (const e of opts.exclude ?? []) b = b.exclude(e);
  const r = await b.analyze();
  const counts = { critical: 0, serious: 0, moderate: 0, minor: 0 };
  for (const v of r.violations) {
    const k = (v.impact ?? "minor") as keyof typeof counts;
    counts[k] += v.nodes.length;
  }
  return {
    url: page.url(),
    counts,
    violations: r.violations.map((v) => ({
      id: v.id, impact: v.impact ?? null, help: v.help, helpUrl: v.helpUrl, nodes: v.nodes.length,
      targets: v.nodes.slice(0, 5).map((n) => n.target.join(" ")),
    })),
  };
}

/** Mapa axe → severidade do motor de auditoria (docs/agent/audit-engine.md). */
export const axeSeverity = (impact: string | null) =>
  ({ critical: "P1", serious: "P2", moderate: "P3", minor: "P4" } as Record<string, string>)[impact ?? "minor"] ?? "P4";
