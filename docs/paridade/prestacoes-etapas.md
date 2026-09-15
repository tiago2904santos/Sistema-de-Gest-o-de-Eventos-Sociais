# Meta 6 — Prestações de contas · Etapas por servidor

**Origem:** `diario_servidor` (+ `diario_servidor_editar_roteiro`, `diario_servidor_motorista`, `diario_servidor_autosave`, `diario_download[_formato]`, `assinatura_db_*`), `rt_servidor` (+ `rt_servidor_autosave`, `rt_download_servidor[_formato]`, `assinatura_rt_*`), `documentos_servidor` (+ `prestacao_arquivo_autosave`, `prestacao_servidor_arquivo_autosave`, `*_assinado_anexar`, `prestacao_carimbo_ajustar`, `prestacao_oficio_assinado_cru`, `prestacao_documento_delete/conteudo`), `consolidado_servidor` (+ `consolidado_download`), e as rotas de compatibilidade por prestação (`diario_criar`, `rt_criar`, `documentos`, `consolidado`, `prestacao_arquivar`, `prestacao_finalizar`, `diario_editar_roteiro`, `diario_motorista`).
**Destino:** as mesmas rotas em `viagens_prestacoes`, com `viagens_prestacoes/base.html` (esqueleto das etapas), `diario_bordo_form.html`, `diario_motorista_form.html`, `relatorio_tecnico_form.html`, `documentos_form.html`, `consolidado.html`, `carimbo_ajustar.html` e `assinatura/_card.html`.
**Data:** 14/09/2026.

Sem fotografia das etapas da origem no repositório: a régua foram os formulários, serviços e o stepper portados na F5 (`contexto_do_fluxo`, `_build_prestacao_steps`, `_build_identificacao`). Fica registrado como desvio do protocolo (P25).

Capturas do destino: [diário de bordo](imagens/meta6-prestacao-diario-destino.png) ([antes](imagens/meta6-prestacao-diario-antes.png)), [motorista e viatura](imagens/meta6-prestacao-motorista-destino.png) ([antes](imagens/meta6-prestacao-motorista-antes.png)), [relatório técnico](imagens/meta6-prestacao-rt-destino.png) ([antes](imagens/meta6-prestacao-rt-antes.png)), [documentos](imagens/meta6-prestacao-documentos-destino.png) ([antes](imagens/meta6-prestacao-documentos-antes.png)), [PDF final](imagens/meta6-prestacao-consolidado-destino.png) ([antes](imagens/meta6-prestacao-consolidado-antes.png)).

## Esqueleto comum

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Cabeçalho | módulo, "Voltar à lista", etapa, servidor, ofício | "Etapa N · nome", selo da situação, servidor (motorista), ofício com protocolo, destino e período | igual |
| Etapas | quatro: Diário de Bordo, Relatório Técnico, Documentos, PDF Final, com estado (Concluído / Em edição / A seguir) | iguais, na lateral | igual |
| Equipe | navegação por servidor | lista da equipe; clicar troca de servidor sem sair da etapa | igual |
| Saíram da equipe | bloco com os dados preservados | "Saíram da equipe · dados preservados" com quem, quando e o que ficou guardado | igual |
| Resumo do ofício | — | número, protocolo, data, custeio, destino, período | **adaptado**: lateral V3.2 |
| Laço genérico de campos | — | `_campos.html` saiu de todas as etapas | igual à origem |

## Campos

| Etapa | Na origem | Aqui | Situação |
|---|---|---|---|
| Diário — motorista e viatura | motorista efetivo (com a origem: do ofício, outro servidor, de outro ofício), viatura; "Trocar motorista / viatura"; "Ajustar roteiro realizado" | iguais, com selo "Trocados neste diário" e a lista das alterações de datas/horários do roteiro ajustado | igual |
| Diário — deslocamentos | por trecho: rota, saída, chegada, km inicial, km final, necessidade de abastecimento (Sim/Não); grava sozinho | tabela com os mesmos campos (`form-N-km_inicial`, `form-N-km_final`, `form-N-abastecimento`), autosave em `diario_servidor_autosave` | igual |
| Diário — documento | PDF (inline) e planilha | "Visualizar PDF" e "Baixar planilha" no cabeçalho | igual |
| Diário — diárias recalculadas | aviso quando o roteiro ajustado muda o valor | aviso com valor e quantidade do ofício e do ajustado | igual |
| Motorista / viatura | preencher a partir de outro ofício; modos do motorista (manter, outro servidor, de outro ofício com nome, CPF, ofício e protocolo); modos da viatura (manter, do cadastro, manual com modelo, placa, tipo, combustível) | iguais; cada modo abre só os seus campos; CPF, protocolo e placa com máscara | igual |
| RT — custeio | diária; translado, combustível e passagem com "Outro" | iguais; "Outro" abre o campo de texto | igual |
| RT — textos | cinco textos com modelo (descrição do evento, objetivo da participação, conclusão, medidas, informações complementares); link para gerenciar modelos que volta ao RT | iguais (`modelo_<campo>` + texto); "Modelos de texto" com `?next=` e `#grupo-<campo>` | igual |
| RT — diária recebida | por servidor, com "Diária ajustada" | igual (`ps-<pk>-diaria_valor_override`) | igual |
| RT — documento | DOCX, PDF inline | "Visualizar PDF", "Baixar DOCX", "Baixar PDF" | igual |
| Documentos — solicitação | número, liberação, prazo de saque | iguais (gravam pelo `index` ou pelo autosave) | igual |
| Documentos — anexos | despacho (vários), ofício assinado (carimbado), comprovante (vários), RT assinado, diário assinado | cinco cartões com o estado (Anexado/Pendente), os arquivos (ver, remover), escolher/anexar; "Ajustar posição do número de solicitação" no ofício | igual |
| PDF final | pendências ou "Baixar pacote (PDF final)"; documentos em original e assinado | iguais, mais situação, solicitação e datas | igual |
| Assinatura eletrônica (diário e RT) | signatário, gerar link com validade, revogar, código de verificação | iguais; link emitido com "Copiar link" | igual |

## Ações

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Diário → RT | "Salvar e continuar" | "Salvar e continuar para o RT" | igual |
| RT | salvar; salvar e continuar | "Salvar relatório", "Salvar e continuar" (→ Documentos), "Voltar ao diário" | igual |
| Documentos | → PDF final | "Conferir e finalizar", "Voltar ao RT" | igual |
| PDF final | finalizar / reabrir; arquivar | "Finalizar prestação" / "Reabrir prestação" (confirmação), "Arquivar prestação" / "Desarquivar", "Ir para Documentos" | igual |
| Carimbo | arrastar o número sobre o ofício assinado | mesma tela (`pdf-place`), no esqueleto das etapas | igual |

## Estados e mensagens

| Elemento | Na origem | Aqui | Situação |
|---|---|---|---|
| Validação da troca | "Selecione um servidor do ofício.", "Informe o nome do motorista.", "Selecione uma viatura do cadastro.", "Informe o modelo da viatura." | as mesmas, no campo e no resumo do topo | igual |
| Gravação | "Diário de bordo salvo.", "Texto do relatório técnico salvo.", "Diário de bordo atualizado (motorista/viatura)." | iguais | igual |
| Pendências do pacote | frases de `pendencias_consolidado` | as mesmas, em "Falta para fechar o PDF final" | igual |
| Sem trechos | — | "O roteiro ainda não possui trechos. Use “Ajustar roteiro realizado” para registrá-los." | igual |
| Sem CPF do signatário | "Cadastre o CPF do …" | igual | igual |
