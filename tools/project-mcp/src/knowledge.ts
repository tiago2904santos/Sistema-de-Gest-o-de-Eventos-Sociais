/**
 * knowledge_* — busca na base de conhecimento do projeto (docs, memória, skills, agentes,
 * docstrings de services/models) sem carregar tudo no contexto. Sempre devolve a fonte
 * (arquivo:linha + seção). Não gera texto: só recupera.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { ROOT, ok, safe } from "./util.ts";

type Chunk = { file: string; line: number; heading: string; text: string; area: string[] };

const AREAS: Record<string, RegExp> = {
  architecture: /^docs\/architecture\/|current-architecture|adr\//,
  business_rules: /^docs\/(PLANO_MESTRE|FASE_|product\/|metas-paridade|COFFEE_BREAK|EPROTOCOLO)|^code:/,
  design_system: /^docs\/design-system\/|^tokens\//,
  ux_decisions: /^docs\/(ux\/|auditoria-pratica|agent\/design-review-loop)|memory\/(decisions|approved-patterns|rejected-patterns)/,
  known_problems: /memory\/known-problems|auditoria-pratica/,
  migration_plan: /migration-matrix|parity-testing|PLANO_MESTRE|prompt-migracao/,
  product_docs: /^docs\/product\/|^README\.md|PLANO_MESTRE/,
  test_strategy: /^docs\/testing\/|^docs\/agent\/(audit-engine|lab-guide)/,
  integrations: /^docs\/integrations\/|EPROTOCOLO/,
  security_rules: /security|^AGENTS\.md|^CLAUDE\.md/,
  agent: /^docs\/agent\/|^\.claude\/|^CLAUDE\.md|^AGENTS\.md/,
};

const norm = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const STOP = new Set("a o e de da do das dos em no na nos nas para por com sem um uma que se the and of to in is are ser como mais ou ao".split(" "));
// Radical por prefixo (5 letras): "exclusão"/"excluir" → "exclu", "cascata"/"CASCADE" → "casca".
// Rudimentar, mas suficiente para português + termos técnicos em inglês sem dependência.
const stem = (t: string) => (t.length > 5 ? t.slice(0, 5) : t);
const tokens = (s: string) => norm(s).split(/[^a-z0-9_]+/).filter((t) => t.length > 1 && !STOP.has(t)).map(stem);

let INDEX: { chunks: Chunk[]; df: Map<string, number>; built: number } | null = null;

function listar(dir: string, ext: RegExp, out: string[] = []) {
  for (const n of readdirSync(dir)) {
    if ([".git", "node_modules", ".venv", "staticfiles", "media", ".lab", "reports", "design-import", "auditoria-visual-2026-09-02"].includes(n)) continue;
    const p = path.join(dir, n);
    const st = statSync(p);
    if (st.isDirectory()) listar(p, ext, out);
    else if (ext.test(n)) out.push(p);
  }
  return out;
}

function areasDe(file: string) {
  return Object.entries(AREAS).filter(([, re]) => re.test(file)).map(([k]) => k);
}

function build() {
  const chunks: Chunk[] = [];
  const md = [path.join(ROOT, "CLAUDE.md"), path.join(ROOT, "AGENTS.md"), path.join(ROOT, "README.md"), ...listar(path.join(ROOT, "docs"), /\.md$/), ...listar(path.join(ROOT, ".claude"), /\.md$/)];
  for (const f of md) {
    const rel = path.relative(ROOT, f).split(path.sep).join("/");
    const linhas = readFileSync(f, "utf-8").split("\n");
    let heading = rel, ini = 0, buf: string[] = [];
    const flush = () => { if (buf.join("").trim()) chunks.push({ file: rel, line: ini + 1, heading, text: buf.join("\n"), area: areasDe(rel) }); };
    linhas.forEach((l, i) => {
      if (/^#{1,4} /.test(l)) { flush(); heading = l.replace(/^#+ /, ""); ini = i; buf = [l]; } else buf.push(l);
    });
    flush();
  }
  // Regras de negócio escritas como docstring de módulo nos services/models.
  for (const f of listar(ROOT, /^(services|models|numeracao|permissions|diarias)\.py$/)) {
    if (f.includes("migrations") || f.includes("agent_lab")) continue;
    const txt = readFileSync(f, "utf-8");
    const m = txt.match(/^\s*(?:#.*\n)*\s*"""([\s\S]*?)"""/);
    if (m && m[1].trim().length > 60) chunks.push({ file: path.relative(ROOT, f).split(path.sep).join("/"), line: 1, heading: "docstring do módulo", text: m[1], area: ["business_rules", "code"] });
  }
  const df = new Map<string, number>();
  for (const c of chunks) for (const t of new Set(tokens(c.heading + " " + c.text))) df.set(t, (df.get(t) ?? 0) + 1);
  INDEX = { chunks, df, built: Date.now() };
}

export function search(query: string, area?: string, limit = 8) {
  if (!INDEX || Date.now() - INDEX.built > 60_000) build();
  const idx = INDEX!;
  const q = tokens(query);
  const N = idx.chunks.length;
  const res = idx.chunks
    .filter((c) => !area || c.area.includes(area))
    .map((c) => {
      const toks = tokens(c.heading + " " + c.heading + " " + c.text);
      const tf = new Map<string, number>();
      for (const t of toks) tf.set(t, (tf.get(t) ?? 0) + 1);
      let score = 0;
      for (const t of q) {
        const f = tf.get(t) ?? 0;
        if (!f) continue;
        const idf = Math.log(1 + (N - (idx.df.get(t) ?? 0) + 0.5) / ((idx.df.get(t) ?? 0) + 0.5));
        score += idf * ((f * 2.2) / (f + 1.2 * (0.25 + 0.75 * toks.length / 180)));
      }
      if (norm(c.text).includes(norm(query))) score *= 1.6;
      return { c, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
  return {
    query, area: area ?? "all", indexed_chunks: N,
    results: res.map(({ c, score }) => ({ source: `${c.file}:${c.line}`, section: c.heading, score: +score.toFixed(2), areas: c.area, excerpt: c.text.trim().slice(0, 900) })),
    note: res.length ? "Trechos literais das fontes; abra a fonte antes de afirmar algo novo." : "Nada encontrado — não invente: registre a lacuna ou procure no código.",
  };
}

export function registerKnowledge(server: McpServer) {
  const T = (name: string, description: string, shape: z.ZodRawShape, fn: (a: any) => Promise<ReturnType<typeof ok>>) =>
    server.registerTool(name, { description, inputSchema: shape }, safe(fn));
  T("knowledge_search", "Busca na base de conhecimento do projeto (docs, memória, skills, agentes, docstrings de regras). Devolve trechos com arquivo:linha.",
    { query: z.string(), area: z.enum(["", ...Object.keys(AREAS)] as [string, ...string[]]).default(""), limit: z.number().default(8) }, async (a) => ok(search(a.query, a.area || undefined, a.limit)));
  const atalhos: [string, string, string][] = [
    ["knowledge_search_architecture", "architecture", "Arquitetura: ADRs, arquitetura atual, dependências."],
    ["knowledge_search_business_rules", "business_rules", "Regras de negócio: plano mestre, fases, produto e docstrings de services/models."],
    ["knowledge_search_design_system", "design_system", "Design System: cores, tipografia, componentes, arquétipos, tokens."],
    ["knowledge_search_ux_decisions", "ux_decisions", "Decisões e padrões de UX aprovados/rejeitados."],
    ["knowledge_search_known_problems", "known_problems", "Problemas conhecidos e auditorias."],
    ["knowledge_search_migration_plan", "migration_plan", "Plano e matriz de migração, paridade."],
    ["knowledge_search_product_docs", "product_docs", "Documentação de produto/módulos."],
    ["knowledge_search_test_strategy", "test_strategy", "Estratégia de testes, laboratório, motor de auditoria."],
    ["knowledge_search_integrations", "integrations", "Integrações externas."],
    ["knowledge_search_security_rules", "security_rules", "Regras de segurança do agente e do projeto."],
  ];
  for (const [nome, area, desc] of atalhos) T(nome, desc, { query: z.string(), limit: z.number().default(6) }, async (a) => ok(search(a.query, area, a.limit)));
  T("knowledge_read_section", "Lê uma seção inteira de um arquivo de documentação (a partir da linha dada até o próximo título do mesmo nível).", { source: z.string().describe("arquivo:linha, como devolvido pela busca") }, async (a) => {
    const [arq, ln] = a.source.split(":");
    const linhas = readFileSync(path.join(ROOT, arq), "utf-8").split("\n");
    const i = Math.max(0, Number(ln || 1) - 1);
    const nivel = (linhas[i].match(/^(#+) /) ?? [, "#######"])[1]!.length;
    let fim = linhas.length;
    for (let j = i + 1; j < linhas.length; j++) { const m = linhas[j].match(/^(#+) /); if (m && m[1].length <= nivel) { fim = j; break; } }
    return ok({ source: a.source, text: linhas.slice(i, Math.min(fim, i + 400)).join("\n") });
  });
}
