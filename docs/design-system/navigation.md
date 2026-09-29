# Navegação

**Hoje**: faixa de identidade + navbar contextual por módulo (`MODULOS_PORTAL`, `ui-inventory/navigation.json`);
hub de módulos após o login; trilha `breadcrumb.html` (40 usos). Viagens tem **12 itens** na barra do módulo.

**Problema medido**: a barra de Viagens transborda e cria rolagem horizontal da página em todas as larguras ≥ tablet,
inclusive 1440px (KP-04).

**Regra v4**: no máximo ~7 itens visíveis; agrupar (Documentos: ofícios, justificativas, termos, planos, ordens · Execução:
viagens, roteiros, prestações · Configuração: cadastros, modelos, configurações, textos); excesso vai para "Mais";
no celular, gaveta.
