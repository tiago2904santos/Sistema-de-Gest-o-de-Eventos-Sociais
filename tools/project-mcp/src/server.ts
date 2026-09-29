#!/usr/bin/env node
/**
 * project-mcp — MCP do Sistema de Gestão de Eventos Sociais / Central de Viagens.
 *
 * Um servidor, vários namespaces (prefixos): project_, inventory_, lab_, testing_, browser_,
 * audit_, compare_, knowledge_, git_, report_, db_, api_, obs_, agent_.
 * Toda ferramenta executa trabalho real no laboratório (nunca simula) e devolve fonte/evidência.
 *
 * Execução: npx tsx tools/project-mcp/src/server.ts   (stdio)
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { registerAgentOps } from "./agentops.ts";
import { registerAudit } from "./audit.ts";
import { registerBrowser, shutdownBrowser } from "./browser.ts";
import { registerKnowledge } from "./knowledge.ts";
import { registerLab } from "./lab.ts";
import { registerProject } from "./project.ts";

export const VERSION = "1.0.0";

export function createServer() {
  const server = new McpServer({ name: "project-mcp", version: VERSION }, {
    instructions: [
      "MCP do projeto Django 'Sistema de Gestão de Eventos Sociais' (unificação com o Central de Viagens).",
      "Comece por project_inspect_project e knowledge_search. Antes de afirmar algo sobre o sistema, use a ferramenta de inspeção correspondente (retornam a fonte).",
      "Navegador: browser_open_page → browser_* (sessões com papel autenticado, relógio ancorado em 2026-09-15). Evidências ficam em reports/mcp/.",
      "Auditoria: audit_* devolvem achados P0–P4 com evidência e 'verification'. Laboratório: lab_* (banco próprio; reset só em LAB).",
      "Seleção de ferramenta: agent_select_tool; pipelines: agent_get_pipeline. Saúde: agent_doctor.",
    ].join("\n"),
  });
  registerProject(server);
  registerLab(server);
  registerBrowser(server);
  registerAudit(server);
  registerKnowledge(server);
  registerAgentOps(server);
  return server;
}

const main = async () => {
  const server = createServer();
  await server.connect(new StdioServerTransport());
  const sair = async () => { await shutdownBrowser(); process.exit(0); };
  process.on("SIGINT", sair);
  process.on("SIGTERM", sair);
  process.stdin.on("close", sair);
};

if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split(/[\\/]/).pop()!)) void main();
