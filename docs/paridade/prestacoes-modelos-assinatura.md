# Meta 6 — Prestações de contas · Modelos de texto e assinatura pública

**Origem:** `modelos_index`, `modelo_update`, `modelo_delete` (`/prestacoes-contas/modelos-texto/…`); `assinatura_landing`, `assinatura_identidade`, `assinatura_assinar`, `assinatura_pdf_origem`, `assinatura_concluido` (`/prestacoes-contas/assinar/<token>/…`).
**Destino:** `viagens_prestacoes:modelos_index`, `modelo_update`, `modelo_delete` em `viagens_prestacoes/modelos.html`; `viagens_assinaturas:assinatura_*` em `viagens_prestacoes/assinatura/*.html` (páginas públicas, sem login, com o `base_publico.html`).
**Data:** 14/09/2026.

Sem fotografia dessas telas na origem; régua: as views portadas e os testes que já cobriam o fluxo público (`tests_assinatura.py`, `test_assinatura_seguranca_f5.py`). Registrado como desvio do protocolo (P25).

Capturas do destino: [modelos de texto](imagens/meta6-prestacao-modelos-destino.png) ([antes](imagens/meta6-prestacao-modelos-antes.png)).

## Campos

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Modelo de texto | campo do relatório, nome, texto | iguais (select, nome com ajuda, texto com ajuda) | igual |
| Identidade (pública) | confirmação do nome e os cinco primeiros dígitos do CPF | iguais | igual |
| Assinar (pública) | fonte manuscrita ou desenho, posição no PDF | iguais | igual |

## Listagem

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Grupos por campo | um grupo por campo do relatório | abas por campo (`?campo=`), com `aria-current` na ativa | igual |
| Busca | por nome | busca por nome dentro do campo | igual |
| Inclusão rápida | formulário no próprio grupo, antes da lista | idem | igual |
| Lista | nome, campo, texto | cartão com nome, campo, ordem e texto | igual |
| Voltar ao RT | `?next=` | "Voltar para o relatório técnico" quando veio de lá | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Salvar modelo | grava e volta ao grupo | "Modelo de texto salvo." e volta ao grupo (ou ao `next`) | igual |
| Editar | rota própria | mesma tela em modo de edição, com "Cancelar" | igual |
| Excluir | confirmação | confirmação em dois cliques; "Modelo excluído." | igual |
| Assinatura pública | começar → identidade → assinar → concluído | iguais | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Sem modelo | — | "Nenhum modelo de <campo> cadastrado ainda. Use o formulário acima." | **adaptado** |
| Link inválido / expirado | "Este link de assinatura é inválido ou expirou." | igual | igual |
| Tentativas | "Muitas tentativas incorretas. Aguarde 15 minutos…" | igual | igual |
| Verificação | código, data, hash do PDF; "revogada" | iguais | igual |
