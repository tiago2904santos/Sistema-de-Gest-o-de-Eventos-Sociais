/**
 * project_* (descoberta) e inventory_* (inventário) — respostas estruturadas com fonte.
 * Base: manage.py agent_query (agent_lab/query.py) e ui-inventory/*.json.
 */
import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { manageJson, ok, readJson, safe } from "./util.ts";

const SECOES = ["summary", "routes", "pages", "components", "forms", "tables", "modals", "dialogs", "navigation", "permissions", "integrations", "entities", "documents", "tokens", "assets", "styles", "states", "duplication-report"] as const;

export function registerProject(server: McpServer) {
  const T = (name: string, description: string, shape: z.ZodRawShape, fn: (a: any) => Promise<ReturnType<typeof ok>>) =>
    server.registerTool(name, { description, inputSchema: shape }, safe(fn));
  const q = (tipo: string, alvo = "") => manageJson(["agent_query", tipo, ...(alvo ? [alvo] : [])]);

  T("project_inspect_project", "Visão geral: stack, ambiente (LAB/DEV/…), branch, contagens do inventário, módulos e por onde começar.", {}, async () => ok(await q("project")));
  T("project_inspect_route", "Rota por nome (viagens_oficios:lista) ou caminho (/viagens/oficios/): view, arquivo:linha, decorators, templates, módulo exigido, começo do código da view.", { route: z.string() }, async (a) => ok(await q("route", a.route)));
  T("project_inspect_page", "Página por template (pages/…html) ou caminho: extends, componentes incluídos, estáticos, estados (vazio/erro…), arquétipo se for página-chave.", { page: z.string() }, async (a) => ok(await q("page", a.page)));
  T("project_inspect_component", "Componente de template: contrato (comentário do topo), quem usa, espécimes do UI Lab.", { component: z.string().describe("ex. page_header ou components/v32/page_header.html") }, async (a) => ok(await q("component", a.component)));
  T("project_inspect_form", "Formulário Django: campos (tipo, widget, obrigatório, rótulo), modelo, views que o usam.", { form: z.string().describe("ex. OficioForm") }, async (a) => ok(await q("form", a.form)));
  T("project_inspect_model", "Modelo: campos, choices, relações de/para (com on_delete), constraints, índices.", { model: z.string().describe("ex. viagens_oficios.Oficio") }, async (a) => ok(await q("model", a.model)));
  T("project_inspect_permission", "Permissão de um namespace/módulo: código do módulo, namespaces cobertos e quais papéis do lab acessam.", { target: z.string().describe("namespace (viagens_oficios) ou código (VIAGENS)") }, async (a) => ok(await q("permission", a.target)));
  T("project_inspect_integration", "Integrações externas (eProtocolo, ORS, WhatsApp, SMTP…): variáveis, modo padrão, hosts de saída.", { filter: z.string().default("") }, async (a) => ok(await q("integration", a.filter)));
  T("project_inspect_document", "Tipos documentais (registry), modelos DOCX, goldens e templates de PDF.", { filter: z.string().default("") }, async (a) => ok(await q("document", a.filter)));

  T("inventory_get_ui_inventory", "Uma seção de ui-inventory/*.json (regerado por inventory_refresh). Para listas grandes use 'filter' (substring no JSON de cada item).",
    { section: z.enum(SECOES), filter: z.string().optional(), limit: z.number().default(50) }, async (a) => {
      const d = readJson<Record<string, unknown>>(`ui-inventory/${a.section}.json`);
      if (!d) throw new Error("inventário ausente — chame inventory_refresh");
      if (!a.filter) {
        const cortado = Object.fromEntries(Object.entries(d).map(([k, v]) => [k, Array.isArray(v) ? v.slice(0, a.limit) : v]));
        return ok({ section: a.section, source: `ui-inventory/${a.section}.json`, ...cortado });
      }
      const out: Record<string, unknown> = { section: a.section, source: `ui-inventory/${a.section}.json`, filter: a.filter };
      for (const [k, v] of Object.entries(d)) if (Array.isArray(v)) out[k] = v.filter((x) => JSON.stringify(x).toLowerCase().includes(a.filter!.toLowerCase())).slice(0, a.limit);
      return ok(out);
    });
  T("inventory_refresh", "Regera ui-inventory/*.json a partir do código atual.", {}, async () => ok(await manageJson(["agent_inventory"])));
  T("inventory_get_component_usage", "Onde um componente é incluído.", { component: z.string() }, async (a) => ok(await q("component_usage", a.component)));
  T("inventory_get_duplicate_components", "Duplicação: templates idênticos, seletores CSS em vários arquivos, tokens conflitantes, funções JS repetidas.", {}, async () => ok(await q("duplicates")));
  T("inventory_get_dependency_graph", "Grafo de dependências (imports e FKs entre apps, ciclos, instabilidade). Filtre por app.", { app: z.string().default("") }, async (a) => ok(await q("dependency_graph", a.app)));
  T("inventory_get_page_archetypes", "Arquétipos de página (LIST, FORM, DETAIL…) com estrutura e regras.", {}, async () => ok(await q("archetypes")));
  T("inventory_get_known_problems", "Problemas conhecidos do produto (docs/agent/memory/known-problems.md), filtráveis por severidade.", { severity: z.string().default("") }, async (a) => ok(await q("known_problems", a.severity)));
  T("inventory_get_design_tokens", "Tokens: custom properties atuais (por categoria), tokens v4 (DTCG), tokens usados sem definição, relatório de contraste.", { category: z.enum(["", "color", "spacing", "sizing", "typography", "radius", "shadow", "motion", "z-index", "other"]).default("") }, async (a) => ok(await q("tokens", a.category)));
  T("inventory_get_migration_status", "Matriz de migração por módulo (atual → novo, status, risco).", { module: z.string().default("") }, async (a) => ok(await q("migration_status", a.module)));
  T("inventory_get_specimens", "Espécimes do UI Lab (componente × estado).", {}, async () => {
    const r = await fetch(`${(await import("./util.ts")).BASE_URL}/_lab/specimens.json`).catch(() => null);
    if (!r) throw new Error("servidor do lab fora do ar — chame lab_start");
    return ok(await r.json());
  });
}
