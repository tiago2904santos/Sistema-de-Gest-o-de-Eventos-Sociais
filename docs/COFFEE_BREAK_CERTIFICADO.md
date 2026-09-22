# Certificado da solicitação de coffee break

Antes, a única saída do módulo era o CSV do recorte inteiro
(`coffee_break/views.py :: exportar_solicitacoes`): para anexar **um** pedido
ao processo, alguém imprimia a tela. Agora cada solicitação tem um certificado
em PDF, na folha institucional, gerado direto do registro.

## O que acontece na tela

| Onde | Comportamento |
|---|---|
| Lista de solicitações, menu da linha (⋮) | "Certificado em PDF" abre o documento numa aba nova |
| Tela da solicitação, ações do topo | Mesmo botão, ao lado de "Salvar solicitação" |
| Solicitação **cancelada** ou **concluída** | O botão continua lá. A tela é só leitura, mas é justamente quando o papel serve — o certificado abre com a faixa do cancelamento e o motivo |
| Servidor sem o runtime do WeasyPrint (GTK/Pango/Cairo) | O pedido continua acessível; a tela avisa o que falta instalar e volta para a solicitação |

O certificado **não** é armazenado. Ele é recalculado do banco a cada pedido,
e por isso nunca diverge do que a tela mostra. A rota é um GET sem efeito
colateral: nada é gravado, nada é versionado.

## O que o documento traz

Cabeçalho, brasão e rodapé são os mesmos dos documentos de Viagens — a folha
ASCOM do termo e da justificativa —, vindos de `ConfiguracaoSistema.atual()`,
isto é, da configuração do setor de quem gera.

O corpo é uma leitura do registro, em quatro partes:

1. **Pedido** — número, data da solicitação, quantidade, situação financeira,
   evento e período.
2. **Lote, contrato e fornecedor** — lote e exercício, contrato e GMS,
   empenho, fiscal, razão social, CNPJ e os municípios do lote.
3. **Fluxo financeiro** — os cinco marcos na ordem real (NF → protocolo →
   atesto → ordem bancária → envio à empresa). **Marco sem registro sai como
   "Pendente"**: o documento existe para mostrar até onde o pedido chegou,
   e o que falta é metade dessa informação.
4. **Observações**, quando houver.

No pé, o local e a hora da emissão, quem registrou a solicitação, quem emitiu
o certificado e a ressalva de que o papel vale como espelho da data da
emissão — a situação corrente é sempre a do sistema.

## Por que não passa pela façade documental

`documentos.services.facade` existe para persistir artefato, versionar
template DOCX e validar payload canônico. O certificado não tem nada disso a
guardar: é HTML renderizado pelo mesmo motor dos outros tipos
(`documentos.services.pdf_renderer`), sem tipo no `DocumentoRegistry` e sem
migração. Trocar o motor de PDF continua sendo mudança de um lugar só.

## Onde mora o código

```
coffee_break/
  documents.py                  # contexto do certificado e a chamada do renderizador
  views.py :: certificado_solicitacao
  urls.py  :: coffee_break:certificado
templates/documentos/pdf/
  coffee_break_certificado.html # a folha, estendendo base_institucional.html
  coffee_break_certificado.css  # geometria e tipografia do modelo
```

## Testes

`coffee_break.tests.CertificadoCoffeeBreakTests`. O HTML é testado sempre (é
template Django puro); os dois testes que geram PDF de fato têm
`skipUnless(weasyprint_disponivel())`, como os demais tipos documentais do
projeto — o runner sem GTK roda o resto.
