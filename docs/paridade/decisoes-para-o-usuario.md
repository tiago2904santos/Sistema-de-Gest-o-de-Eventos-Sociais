# Folha de decisões — 11 pendências da paridade

Respondido isto, a Meta 1 fecha e as Metas 2 a 7 destravam. Cada item traz o que está em jogo, os dados reais desta base (conferidos em 14/09/2026) e uma recomendação. Basta escrever **sim** ou **não** na linha de resposta, ou riscar e escrever outra coisa.

---

## A. Defeitos da origem que não deveríamos copiar

### P05 — Editar só o nome de um cargo desmarca o "padrão"

Na origem, o formulário rápido envia apenas o nome, mas o campo "é padrão" viaja junto como opcional. Resultado: corrigir uma letra do nome desmarca o padrão sem avisar. A pergunta é se podemos preservar o padrão ao editar apenas o nome.

**Recomendação: SIM, preservar.** Apagar configuração em silêncio não é comportamento a reproduzir. Fica registrado como adaptação na ficha da tela.

> Sua resposta: ______

### P06 — Editar o nome de uma unidade esvazia a lotação

Aqui é o contrário: o defeito é nosso. Na origem, a lotação só é sincronizada se o campo for enviado. No nosso, a edição rápida sincroniza mesmo sem o campo, ou seja, mexer no nome da unidade **remove os servidores lotados nela**. A pergunta é se a edição rápida pode preservar os vínculos, mantendo o formulário completo para gerenciar lotação.

**Recomendação: SIM, corrigir.** É perda de dado por efeito colateral, e a origem já faz certo.

> Sua resposta: ______

### P09 — O calendário da origem não preenche o campo oculto

Selecionando 01/11/2026 nos dois sistemas, a data aparece na tela em ambos, mas o campo oculto da origem fica vazio e o nosso leva `2026-11-01`. A pergunta é se mantemos o nosso comportamento.

**Recomendação: SIM, manter o nosso.** Campo oculto vazio é defeito, e a regra deste projeto é mandar data em formato ISO. Fica documentado como diferença deliberada.

> Sua resposta: ______

---

## B. Regras nossas que eu manteria, mesmo divergindo da origem

### P07 — Estado: encurtar o nome e tornar o código do IBGE opcional

A origem usa nome com 128 caracteres e permite estado sem código do IBGE. Aqui são 150 caracteres e o código é obrigatório. **Dados reais: 27 estados, o maior nome tem 19 caracteres, nenhum sem código do IBGE.**

**Recomendação: NÃO mudar nenhum dos dois.** O limite não aparece na tela para ninguém, e o modelo é compartilhado com o módulo de Eventos. Tornar o código opcional só abriria porta para cadastro incompleto de uma lista que tem 27 itens fixos e completos.

> Sua resposta: ______

### P08 — Diárias: aceitar valor mínimo de R$ 0,01

A origem aceita R$ 0,01 no formulário. Nós exigimos R$ 0,04, porque abaixo disso o derivado de 15% arredonda para zero e a tabela passa a produzir parcela nula.

**Recomendação: NÃO mudar.** É regra de dinheiro com motivo, e a própria origem tem restrição de derivados positivos no modelo. Fica documentado.

> Sua resposta: ______

### P13 — Cidades: nome maior, região opcional e coordenadas editáveis

Três mudanças num modelo compartilhado com Eventos. **Dados reais: 5.571 municípios, maior nome com 32 caracteres, nenhum sem região, 8 com coordenadas.**

**Recomendação: NÃO às três.** O nome maior não muda nada na prática. A região é o que liga o município à faixa da tabela de diárias, então município sem região é diária que não calcula. E coordenada digitada à mão erra sem ninguém perceber: ela vem de importação e geocodificação, e alimenta o mapa e o cálculo de rota.

> Sua resposta: ______

---

## C. Alinhamentos à origem que valem a pena

### P12 — Sigla do estado com exatamente dois caracteres

A origem exige dois. Nós aceitamos até dois, mas não exigimos. **Todas as 27 siglas já têm dois.**

**Recomendação: SIM, exigir.** É validação de entrada, não muda dado nenhum e evita sigla pela metade.

> Sua resposta: ______

### P15 — Limites de placa, RG e telefone

Três ajustes numa pergunta só, e eu responderia diferente para cada um. **Dados reais: 1 viatura com placa de 7 caracteres, maior RG com 13, telefone em branco.**

- **Placa de 10 para 7, sem separadores: SIM.** Já guardamos sem hífen, e placa brasileira tem 7. Nenhuma placa gravada perde caractere.
- **RG de 30 para 20: NÃO.** Não ganha nada e pode barrar documento de outro estado com formatação diferente.
- **Telefone de 16 para 20: SIM.** Só aumenta, acomoda número com código de país e não afeta nada gravado.

> Sua resposta: ______

### P10 — Configuração institucional com endereço e cidade-sede

A origem tem dez campos, com a unidade federativa preenchida pelo CEP em modo somente leitura e a cidade-sede resolvida a partir do endereço. O nosso pede unidade federativa e cidade-sede na mão, e tem campos que a origem não tem, como o prazo da justificativa. A pergunta é se alinhamos ao fluxo da origem preservando no banco os campos que saírem da tela.

**Recomendação: SIM, com uma condição.** Alinhe o bloco de endereço à origem, mas os campos que só existem aqui não podem sumir da tela: o prazo da justificativa é usado pela regra de prazo. Eles ficam numa seção própria, abaixo, em vez de serem removidos.

> Sua resposta: ______

---

## D. Escopo

### P01 — Assinantes de plano de trabalho e de ordem de serviço

A tela de configuração da origem cadastra assinantes para quatro tipos de documento. Dois deles, plano de trabalho e ordem de serviço, estão fora do escopo ratificado da unificação e não existem aqui.

**Recomendação: NÃO trazer, e autorizar a omissão.** Seriam campos órfãos, apontando para documentos que o sistema não emite. Fica registrado como ausência autorizada, que é o que falta para a Meta 1 poder fechar.

> Sua resposta: ______

---

## E. Limpeza do incidente

### P14 — Apagar o "ENSAIO DE CARGO" gravado no sistema antigo

Durante uma comparação, um cargo de teste foi gravado por engano no banco do Gerenciador de Viagens: o de número 34, chamado ENSAIO DE CARGO. Confirmei em 14/09/2026, por consulta somente leitura, que ele continua lá e não tem nenhum vínculo.

**Recomendação: apague você mesmo, pela tela do sistema antigo.** São dez segundos e o registro não tem vínculo. O agente já escreveu ali uma vez por engano, e a regra de nunca escrever na origem fica mais segura se continuar valendo sem exceção.

> Sua resposta: ______

---

## Resumo das recomendações

| Item | Assunto | Recomendação |
|---|---|---|
| P05 | Editar nome desmarca o padrão | Preservar o padrão |
| P06 | Editar unidade esvazia lotação | Corrigir, preservar vínculos |
| P09 | Campo oculto do calendário | Manter o nosso, em ISO |
| P07 | Nome e código do IBGE do estado | Não mudar |
| P08 | Mínimo da diária | Manter R$ 0,04 |
| P13 | Nome, região e coordenadas de cidade | Não mudar nenhum dos três |
| P12 | Sigla com dois caracteres | Exigir |
| P15 | Placa, RG e telefone | Placa sim, telefone sim, RG não |
| P10 | Configuração institucional | Alinhar, sem remover campos nossos |
| P01 | Assinantes de plano e ordem de serviço | Não trazer, autorizar a omissão |
| P14 | Cargo de ensaio na origem | Apagar você, pela tela |
