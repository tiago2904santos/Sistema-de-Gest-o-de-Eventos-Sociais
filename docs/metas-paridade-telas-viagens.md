# Metas — paridade de telas com o Gerenciador de Viagens

> Documento de metas para o Codex trabalhar em modo contínuo: ele só para quando **todas** estiverem concluídas e provadas.
> Copie tudo abaixo da linha e cole no Codex.

---

## 1. O problema, medido

A migração do domínio funcionou: modelos, regras, cálculo de diárias, numeração, geração de documentos e testes estão no lugar. **As telas, não.** O que foi entregue é um esqueleto genérico: formulário desenhado por laço sobre uma lista de campos, listagem com meia dúzia de colunas e um link "Abrir".

Números conferidos em 10/09/2026, contando os dois lados:

| Superfície | Gerenciador de Viagens | Aqui |
|---|---:|---:|
| Rotas dos apps no escopo | 161 | 52 |
| Templates de ofícios | 28 arquivos, 1.416 linhas | 9 arquivos, 131 linhas |
| Templates de termos | 10 | 3 |
| Templates de prestações | 51 | 18 |
| Templates de cadastros | 34 | 5 |
| Filtros na lista de ofícios | 9 | 4 |
| Formulário de ofício (`forms.py`) | 614 linhas | 132 |

Um exemplo concreto, para não restar dúvida do que "cru" significa. A lista de ofícios da origem tem abas de situação, busca, intervalo de datas de criação, intervalo de datas de viagem, ordenação escolhida pelo usuário, tamanho de página, um cartão por ofício com 190 linhas de conteúdo e um menu de ações por item. A daqui tem quatro filtros, uma tabela de seis colunas e a palavra "Abrir".

O formulário de ofício da origem são seis etapas com blocos próprios: identidade, motivo, equipe, transporte, cartão de motorista externo, roteiro com resumo da rota, conferência e resumo. O daqui percorre `secoes` num laço e joga tudo em `_campos.html`, o mesmo renderizador genérico para qualquer campo. Existe até um `form_simples.html` de 16 linhas.

## 2. A regra desta tarefa

**Paridade 1:1 de conteúdo e de comportamento. Só a pele muda.**

Uma ressalva necessária, para a instrução não ser impossível de cumprir ao pé da letra: **não dá para "mudar só o CSS"**. A origem usa django-cotton, com componentes e classes que este projeto não tem; o HTML precisa ser reescrito nos templates e componentes daqui. O que é 1:1 é tudo o que o usuário percebe e usa:

- todo campo, com o mesmo rótulo, na mesma ordem, com a mesma obrigatoriedade, a mesma ajuda, a mesma máscara e o mesmo valor inicial;
- toda coluna, filtro, aba, ordenação, paginação e tamanho de página;
- toda ação: no cabeçalho, na linha, no menu de item, em massa;
- todo estado: vazio, sem resultado de filtro, sem permissão, erro, carregando, bloqueado;
- toda mensagem, texto de apoio, aviso e confirmação, com as mesmas palavras;
- toda validação e toda regra de habilitar/desabilitar campo;
- todo comportamento de tela: autosave, cascata entre campos, cálculo ao vivo, prévia, abrir em nova aba, atalho.

O que muda, e só isso: as classes, os componentes visuais, a tipografia, as cores e a densidade, para caber no Design System V3.2 que já está no projeto (`static/css/ds-v32.css`, `templates/layouts/app_shell_v32.html` e os componentes em `templates/components/`).

## 3. Ambiente de comparação

O Gerenciador de Viagens **roda nesta máquina** e o banco tem dados reais: `central_viagens`, com 59 ofícios. Use isso. Toda meta é verificada com as duas telas abertas lado a lado, não de memória e não pela leitura do template.

- Origem: `C:\Users\tiago\OneDrive\Documentos\Gerenciador de Viagens` (**somente leitura**; nunca grave, edite ou rode migração lá).
- Destino: `C:\Users\tiago\OneDrive\Documentos\Solicitações de eventos`, servidor em `runserver 8021` (sempre com porta).
- A origem documenta as próprias telas em `docs/`: `PADRAO_CRUD.md`, `PADRAO_FORMS.md`, `COMPONENTES.md`, `COMPONENTES_DOMINIO.md`, `DESIGN_SYSTEM.md`, `OFICIOS_REGRAS_NEGOCIO.md`, `CADASTROS_FUNCIONAL.md`. Leia antes de desenhar.

## 4. Proibido

Foi assim que se chegou ao estado atual:

1. **Formulário renderizado por laço genérico sobre campos.** Cada tela desenha os próprios blocos, com os campos onde a origem os põe. `_campos.html` deixa de existir como renderizador de formulário de domínio.
2. **Versão "simples" de qualquer tela.** `form_simples.html` e equivalentes saem.
3. **Descartar filtro, coluna, aba, ação, estado ou mensagem** por julgar acessório. Se a origem tem, vem. Divergência só com autorização registrada.
4. **Trocar cartão por tabela, ou tabela por cartão**, sem reproduzir a mesma informação e as mesmas ações.
5. **Inventar tela, campo, filtro ou fluxo que a origem não tem.**
6. **Marcar meta como concluída sem o arquivo de prova** descrito na seção 6.

## 5. As metas

Ordem obrigatória. Cada meta é fechada e provada antes de a seguinte começar, e a suíte fica verde ao fim de cada uma.

**Meta 0 — Inventário.** Levantar as 161 rotas da origem nos apps no escopo (`cadastros`, `roteiros`, `oficios`, `justificativas`, `termos`, `prestacoes_contas`) e mapear cada uma para a rota correspondente aqui, marcando: existe e está fiel, existe e está incompleta, não existe, ou fora de escopo com o motivo. O resultado vai para `docs/paridade/00-inventario.md` e é a régua de todas as metas seguintes. Fora de escopo continuam: planos de trabalho, ordens de serviço, Drive, eProtocolo, área de trabalho e o app de eventos agrupadores.

**Meta 1 — Cadastros** (32 rotas na origem, 9 aqui). Servidores, viaturas, unidades, cargos, combustíveis, tabela de diárias e configuração. É a meta que estabelece o padrão de lista, de formulário e de exclusão que as demais reaproveitam.

**Meta 2 — Roteiros** (11 na origem, 14 aqui). Esta já foi feita com paridade em 02/09/2026: confira contra a origem, corrija o que divergir e **não reescreva o que está certo**. É o melhor exemplo do nível esperado nas outras metas.

**Meta 3 — Ofícios** (31 na origem, 15 aqui). A maior dívida. Inclui as seis etapas do formulário com seus blocos próprios, a listagem completa com abas e cartão, os menus de ação, a conferência, o resumo e as telas de catálogo de motivos.

**Meta 4 — Justificativas** (12 na origem). Modelos, aplicação de modelo ao texto, regra de prazo e as telas de catálogo.

**Meta 5 — Termos** (23 na origem, 9 aqui). Cadastro avulso, herança de valores do ofício, destinos adicionais, prévia, geração individual e em lote.

**Meta 6 — Prestações de contas** (52 na origem, 5 rotas e 18 templates aqui). Diário de bordo, relatório técnico, anexos, carimbo, consolidado, finalização e as telas públicas de assinatura.

**Meta 7 — Conferência final.** Percorrer o inventário da Meta 0 inteiro, com as duas telas abertas, e fechar as pendências que sobraram. Suíte completa verde em PostgreSQL e em SQLite, `makemigrations --check` limpo.

## 6. Como uma meta se prova

Para cada tela, um arquivo em `docs/paridade/<app>-<tela>.md` com quatro tabelas preenchidas olhando as duas telas:

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|

Uma tabela para **campos** (rótulo, tipo, obrigatório, ajuda, máscara, valor inicial, regra de habilitação), uma para **listagem** (colunas, filtros, abas, ordenação, paginação), uma para **ações** (onde fica, o que faz, confirmação, permissão) e uma para **estados e mensagens** (vazio, sem resultado, erro, sem permissão, texto de apoio).

"Situação" só aceita três valores: **igual**, **adaptado** (com a razão na mesma linha) ou **ausente** (com a autorização que dispensou). Meta com qualquer linha "ausente" sem autorização não está concluída.

Junto, para cada tela: uma captura da origem e uma do destino, lado a lado, em `docs/paridade/imagens/`.

## 7. Regras de front deste projeto

- Nunca `<select>` ou `<input type="date">` crus. Use `components/select.html`, `components/input.html` com `tipo="date"` e `components/date_range.html`, que o `app.js` transforma nos controles do sistema. O usuário rejeita o widget nativo do navegador.
- Município sempre com o estado que o filtra (`data-parent-value` + `dependente_de`).
- Campo oculto numérico ou de data que o JS lê ou reenvia vai em ISO e sem localização.
- A lateral fixa rola com a página; só a barra de ações fica presa no rodapé.
- Toda tela nova nasce no `app_shell_v32.html`. CSS novo vai em `ds-v32-bridge.css`, com comentário explicando o porquê. `ds-v32.css` não se edita.
- Telas de referência já prontas neste projeto, para copiar a composição: `templates/pages/solicitacoes/lista.html` (listagem), `detalhe.html` (detalhe com lateral), `form.html` (formulário longo com etapas), `templates/pages/dashboard/index.html` (painel) e `templates/pages/cadastros/` (cadastro).

## 8. Fechamento de cada meta

1. Suíte completa verde, com número de testes maior ou igual ao anterior.
2. `manage.py check` e `makemigrations --check --dry-run` limpos.
3. Arquivos de prova da seção 6 preenchidos, com as capturas.
4. As telas da meta exercitadas no navegador contra o banco de desenvolvimento, não só nos testes. Suíte verde não é tela conferida.
5. Nenhum arquivo do Gerenciador de Viagens alterado.

Não faça commit nem push sem pedir. Ao terminar cada meta, escreva o que ficou diferente da origem e por quê; ao terminar todas, atualize `docs/PLANO_MESTRE_UNIFICACAO.md`.

## 9. Pare e pergunte se

- uma tela da origem depender de função fora do escopo (Drive, eProtocolo, plano de trabalho, ordem de serviço, área de trabalho);
- a paridade exigir mudar regra de negócio, nome de campo ou permissão que já está em produção aqui;
- um comportamento da origem depender de biblioteca que este projeto não tem;
- você concluir que um elemento da origem é defeito e não deve ser reproduzido. Relate; não decida sozinho.
