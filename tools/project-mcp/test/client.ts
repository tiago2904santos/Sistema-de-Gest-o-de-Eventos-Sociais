/** Cliente MCP mínimo para testar o project-mcp de verdade (stdio, protocolo real). */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

export async function connect() {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [path.join(ROOT, "node_modules", "tsx", "dist", "cli.mjs"), path.join(ROOT, "tools", "project-mcp", "src", "server.ts")],
    cwd: ROOT,
    // O SDK repassa só um ambiente mínimo por padrão; o servidor precisa de PATH,
    // PLAYWRIGHT_BROWSERS_PATH, proxy etc. como um cliente MCP real (Claude Code) faz.
    env: Object.fromEntries(Object.entries(process.env).filter(([, v]) => v !== undefined)) as Record<string, string>,
    stderr: "pipe",
  });
  const client = new Client({ name: "project-mcp-test", version: "1.0.0" });
  await client.connect(transport);
  return client;
}

export type CallResult = { ok: boolean; data: any; images: number; ms: number };

export async function call(client: Client, name: string, args: Record<string, unknown> = {}): Promise<CallResult> {
  const t0 = Date.now();
  const r = (await client.callTool({ name, arguments: args }, undefined, { timeout: 1_500_000 })) as { isError?: boolean; content: { type: string; text?: string }[] };
  const txt = r.content.find((c) => c.type === "text")?.text ?? "";
  let data: any = txt;
  try { data = JSON.parse(txt); } catch { /* texto */ }
  return { ok: !r.isError, data, images: r.content.filter((c) => c.type === "image").length, ms: Date.now() - t0 };
}
