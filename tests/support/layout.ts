import type { Page } from "@playwright/test";
import { layoutIssuesSource } from "../tools/layout-source.mjs";

export type LayoutIssue = { kind: "page-overflow-x" | "element-overflow" | "clipped-text" | "tiny-target"; detail: string; selector?: string };

/** Varre o DOM atrás de problemas de layout que um humano veria na tela. */
export async function layoutIssues(page: Page): Promise<LayoutIssue[]> {
  return page.evaluate(layoutIssuesSource) as Promise<LayoutIssue[]>;
}
