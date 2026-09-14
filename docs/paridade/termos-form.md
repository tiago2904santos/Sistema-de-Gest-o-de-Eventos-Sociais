# Meta 5 — Termos de autorização · Cadastro

**Origem:** `termos:novo` (`/termos/novo/`), `termos:editar` (`/termos/<pk>/editar/`) e `termos:api_buscar_oficios` (`/termos/api/oficios/`).
**Destino:** `viagens_termos:novo`, `viagens_termos:editar`, `viagens_termos:api_buscar_oficios`, em `pages/viagens_termos/form.html` com `viagens-picker-oficios.js` e `viagens-termos.js`.
**Data:** 14/09/2026.

Não há fotografia do cadastro da origem no repositório; a régua foi o `TermoAutorizacaoForm` portado na F4 (campos, regras de herança e de validação, destinos adicionais) e a busca de ofícios já usada nas justificativas (Meta 4). Fica registrado como desvio do protocolo (P23).

Capturas do destino: [termo avulso](imagens/meta5-termo-form-destino.png) ([antes](imagens/meta5-termo-form-antes.png)), [termo preso a um ofício](imagens/meta5-termo-form-oficio-destino.png), [erros](imagens/meta5-termo-form-erro-destino.png).

## Campos

| Campo | Na origem | Aqui | Situação |
|---|---|---|---|
| Ofício vinculado | busca remota de ofícios (`api_buscar_oficios`), opcional; só ofícios não cancelados | seletor com busca no servidor (número, protocolo, viajante, destino), um só ofício, teto de 30 resultados; mesmo endpoint das justificativas | igual |
| UF do destino / Município do destino | dois selects dependentes | selects pesquisáveis, município dependente do estado | igual |
| Destinos adicionais | pares estado/município, "Adicionar destino" (`acao=adicionar_destino`, `quantidade_destinos`) | iguais, sem gravar ao adicionar | igual |
| Data inicial / Data final | duas datas | um período (`date_range`, mesmos nomes `data_evento_inicio` / `data_evento_fim`); um dia: a final repete a inicial | igual (pele) |
| Servidores | múltipla escolha | lista com busca, um termo por servidor marcado; contagem "N servidores" | igual |
| Viatura | select opcional | select pesquisável, opcional | igual |
| Herança | em branco herda do ofício | aviso "Este termo herda do ofício: destino, período, servidores, viatura." ao editar | **adaptado**: torna a regra visível |

## Listagem

Não se aplica (tela de cadastro). O "Termo #N" do cabeçalho e o selo "Cancelado" vêm do registro.

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Salvar | grava e volta à lista | grava, "Termo #N salvo.", volta ao detalhe ou ao `?next=` | igual |
| Adicionar destino | reenvia o formulário com mais um par | igual (`formnovalidate`) | igual |
| Voltar | link | botão "Voltar" ao detalhe / lista / `?next=` | igual |
| Remover ofício | — | "×" no ofício escolhido | igual (pele do seletor) |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Sem destino e sem ofício com roteiro | "Informe o destino ou selecione um ofício com roteiro." | igual | igual |
| UF sem município | "Informe o município do destino." | igual | igual |
| Município de outro estado | "Escolha um município do estado selecionado." | igual | igual |
| Sem data e sem ofício com período | "Informe a data ou selecione um ofício com período." | igual | igual |
| Final antes da inicial | "A data final não pode ser anterior à inicial." | igual | igual |
| Adicional incompleto | "Selecione o município adicional." / "Selecione um município do estado informado." | iguais | igual |
| Resumo dos erros | — | aviso "Não foi possível salvar o termo" com a lista dos erros e ligação a cada campo | **adaptado** |
