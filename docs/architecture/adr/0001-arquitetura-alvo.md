# ADR 0001 — Arquitetura-alvo: monólito Django com frontend reconstruído por dentro

- **Status**: proposta (aguarda ratificação do Tiago)
- **Data**: 29/09/2026
- **Contexto medido**: `docs/architecture/current-architecture.md`

## Problema

A missão autoriza trocar tudo (React, Next.js, SPA, greenfield). A pergunta é técnica: qual arquitetura
entrega o melhor produto com o menor risco para um sistema institucional com regras de dinheiro,
numeração oficial e documentos protocolados, mantido por uma pessoa com apoio de agentes de IA?

## Alternativas avaliadas

| | A. Monólito Django + DS v4 + JS em módulos (recomendada) | B. Django API + SPA React/TS (Vite) | C. Next.js full-stack (Node) | D. Greenfield paralelo |
|---|---|---|---|---|
| Reuso do domínio testado | total | total (atrás de API) | nenhum (reescrever) | parcial |
| Trabalho novo | DS + migração de templates | API p/ 600 rotas + 62 formulários + SPA inteira | tudo | tudo + sincronizar dois sistemas |
| Risco em dinheiro/documentos | baixo | médio (validação duplicada) | alto | alto |
| Ganho para o usuário | resolve os problemas medidos (contraste, foco, overflow, consistência) | idem + interatividade que hoje não é gargalo | idem | idem |
| Desempenho | já bom (LCP < 0,5 s) | pior no 1º carregamento | similar | — |
| Deploy (Windows/waitress + VPS) | igual ao atual | + build Node, + CORS/sessão | troca de runtime | dois deploys |
| Operação por uma pessoa + agentes | simples | 2 stacks, 2 suítes | stack nova | a pior |

## Decisão

**A.** Manter Django como núcleo e reconstruir a camada de apresentação dentro do monólito:

1. **Design System v4** em camadas (`@layer tokens, base, components, patterns, utilities`), gerado de
   `tokens/*.json` (DTCG) → `static/css/tokens.css`; um CSS por componente; substitui `design-system.css` +
   `ds-v32.css` + `ds-v32-bridge.css` ao fim da migração.
2. **Componentes de template com contrato** (`templates/components/v4/`), usando `{% partialdef %}` do Django 6
   para variações; cada componente tem espécimes no UI Lab e teste visual + axe.
3. **Novo casco** `layouts/app_shell_v4.html` convivendo com o v3.2: páginas migram uma a uma (estrangulamento),
   protegidas por testes de paridade (`parity-testing.md`).
4. **JS em módulos ES** com um núcleo único (CSRF, fetch, diálogos, anúncios) em vez de helpers duplicados; TypeScript
   com `// @ts-check` + JSDoc primeiro; bundler (Vite/esbuild) só quando o número de módulos justificar.
5. **Interatividade parcial** via fragmentos de template (partials) e, se necessário, htmx — sem SPA.
6. **Desacoplamento**: quebrar o ciclo de 19 apps extraindo contratos para `core` (que não pode importar domínio).

## Gatilhos para reavaliar (B ou API)

- Um cliente não-web (app móvel nativo, integração de terceiros) precisar dos mesmos dados → API com django-ninja/DRF + OpenAPI.
- O diário de campo (PWA) crescer para offline-first com sincronização complexa.
- Uma tela precisar de estado de cliente que partials não resolvam (editor colaborativo em tempo real).

## Consequências

- Nenhuma regra de negócio é reescrita; os 3.054 testes seguem válidos.
- O laboratório (`agent_lab`, Playwright, catracas) é o que garante que cada página migrada não regrediu.
- Custo: disciplina de migração página a página e a retirada gradual dos três CSS atuais.
