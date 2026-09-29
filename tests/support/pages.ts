import type { Role } from "./roles";

/**
 * Páginas-chave auditadas por padrão (smoke, a11y, visual, responsivo, perf).
 * `archetype` segue docs/design-system/page-archetypes.md.
 * Para auditar todas as rotas, use tests/smoke/routes.spec.ts (lê ui-inventory/routes.json).
 */
export type KeyPage = { id: string; path: string; role: Role; archetype: string; module: string };

export const KEY_PAGES: KeyPage[] = [
  { id: "login", path: "/conta/entrar/", role: "admin", archetype: "AUTH", module: "accounts" },
  { id: "hub", path: "/", role: "admin", archetype: "DASHBOARD", module: "core" },
  { id: "dashboard", path: "/dashboard/", role: "gestorDg", archetype: "DASHBOARD", module: "dashboard" },
  { id: "agenda", path: "/agenda/", role: "admin", archetype: "CALENDAR", module: "agenda" },
  { id: "solicitacoes-lista", path: "/solicitacoes/", role: "gestorDg", archetype: "LIST", module: "solicitacoes" },
  { id: "solicitacoes-nova", path: "/solicitacoes/nova/", role: "solicitante", archetype: "FORM", module: "solicitacoes" },
  { id: "cadastros", path: "/cadastros/", role: "administrador", archetype: "SETTINGS", module: "cadastros" },
  { id: "coffee-lista", path: "/coffee-break/", role: "ascom", archetype: "LIST", module: "coffee_break" },
  { id: "palestras-lista", path: "/ascom/palestras/", role: "ascom", archetype: "LIST", module: "demandas_eventos" },
  { id: "publicacoes-lista", path: "/ascom/publicacoes/", role: "ascom", archetype: "LIST", module: "publicacoes" },
  { id: "imprensa-lista", path: "/ascom/imprensa/", role: "ascom", archetype: "LIST", module: "atendimento_imprensa" },
  { id: "roteiros-lista", path: "/viagens/roteiros/", role: "viagensGestor", archetype: "LIST", module: "viagens_roteiros" },
  { id: "oficios-lista", path: "/viagens/oficios/", role: "viagensGestor", archetype: "LIST", module: "viagens_oficios" },
  { id: "termos-lista", path: "/viagens/termos/", role: "viagensGestor", archetype: "LIST", module: "viagens_termos" },
  { id: "viagem-lista", path: "/viagens/viagem/", role: "viagensGestor", archetype: "LIST", module: "viagens_viagem" },
  { id: "ordens-lista", path: "/viagens/ordens/", role: "viagensGestor", archetype: "LIST", module: "viagens_ordens" },
  { id: "planos-lista", path: "/viagens/planos/", role: "viagensGestor", archetype: "LIST", module: "viagens_planos" },
  { id: "prestacoes-lista", path: "/viagens/prestacoes/", role: "viagensGestor", archetype: "LIST", module: "viagens_prestacoes" },
  { id: "viagens-cadastros", path: "/viagens/cadastros/", role: "viagensGestor", archetype: "SETTINGS", module: "viagens_cadastros" },
  { id: "relatorios", path: "/relatorios/", role: "gestorDg", archetype: "REPORT", module: "relatorios" },
  { id: "erro-404", path: "/_lab/erro/404/", role: "admin", archetype: "ERROR", module: "core" },
];

export const pageById = (id: string) => KEY_PAGES.find((p) => p.id === id)!;
