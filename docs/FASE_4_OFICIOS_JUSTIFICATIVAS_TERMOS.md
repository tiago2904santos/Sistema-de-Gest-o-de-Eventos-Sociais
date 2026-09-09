# Fase 4 — Ofícios, justificativas e termos

Implementação em 09/09/2026, sem commit ou push. Baseline antes das alterações:
**645 testes**, PostgreSQL, sem falhas; migrações sem alterações pendentes.

## Entrega

- `viagens_oficios`: ofício, numeração anual global, lacunas, piso configurável,
  motivos, justificativa 1:1 e modelos de justificativa. Reserva transacional com
  advisory lock no PostgreSQL, alternativa `select_for_update`, constraint
  identificada pelo nome e repetição após colisão real. Excluir libera a menor
  lacuna; saltos manuais não criam lacunas implícitas.
- Formulário longo V3.2: viajantes, transporte cadastrado ou manual, roteiro F2,
  justificativa e resumo. Listagem com busca/status/ano/cancelamento, documentos,
  arquivamento, cancelamento/reativação e marcas de retificação/complementação.
  A lateral acompanha a rolagem; só as ações ficam presas no rodapé.
- `viagens_termos`: cadastro próprio, inclusive avulso, herança de valores do
  ofício, destinos adicionais, prévia, geração individual e lote ZIP. Variantes
  automática com viatura, automática sem viatura e semipreenchida, pela façade F3.
- FKs opcionais de origem no artefato e no recorte de cache/persistência, em
  `documentos/0002`, sem migração de dados no arquivo de esquema. Modelos binários
  automáticos e goldens copiados do GV sem alteração.
- Anexação e revogação de PDF assinado pela persistência versionada da F3;
  download e visualização de artefato servem a versão assinada vigente.
- Rotas sob VIAGENS; consultas para leitores, mutações para operador/gestor,
  configuração de numeração e institucional para gestor. Navegação e auditoria
  dos dois apps integradas à base.
- Com autorização expressa do usuário, `ConfiguracaoSistema` global e
  `AssinaturaConfiguracao` foram acrescentadas a `viagens_cadastros`, com telas
  de configuração e assinantes, sem os tipos exclusivos de PT/OS.

## Adaptações e limites do porte

1. **Representação das diárias na F2:** o GV guarda valor por servidor; a F2
   guarda o total da equipe. A F4 divide pelo efetivo do roteiro antes de aplicar
   o snapshot do ofício. Exemplo coberto: roteiro de três servidores, R$ 130,74;
   ofício de dois, R$ 87,16. Nenhum cálculo da F2 foi alterado. Exclusão cadastral
   e edição apenas de metadados preservam o snapshot; mudança deliberada de equipe
   o atualiza.
2. **Datas da F2:** horários podem existir somente nos trechos. Os contextos da
   F4 usam os campos do roteiro e, na ausência deles, os trechos ordenados. Datas
   documentais usam horário local; valores monetários usam localização brasileira.
3. **Interface:** FBVs e componentes V3.2 substituem wizard, Cotton, seletores e
   menus do GV. A escolha de modelo preenche o texto; municípios dependem da UF;
   datas ocultas usam ISO. O lote entrega um arquivo por servidor em ZIP. O piso
   é configurável pelo gestor; o formulário operacional reserva o número e não
   oferece renumeração manual.
4. **Fora do escopo:** tenancy/área, FK para `eventos.Evento`, campos/documentos
   exclusivos de plano de trabalho e ordem de serviço, Drive, eProtocolo,
   Celery/filas, rotas legadas e editor de mapa do GV. O mapa continua na F2.
   Assinatura pública por token continua prevista para F5b.
5. **Dados oficiais:** a configuração institucional nasce vazia. Unidade, sede,
   endereço, destinatário e assinantes devem ser preenchidos pelo gestor antes
   do uso administrativo. Os dados faltantes do cadastro de servidores não foram
   inventados; os PDFs de validação exibem os campos ausentes como no GV.

## Evidências de validação

- PostgreSQL: **737 testes, 296,138 s, zero falhas, quatro skips** de WeasyPrint
  por ausência de bibliotecas nativas. Log: `logs/f4-pg-final.txt`.
- SQLite: **737 testes, 253,574 s, zero falhas, cinco skips** (os quatro
  anteriores e a concorrência exclusiva de PostgreSQL). Execução sem variáveis
  `POSTGRES_*` e com `PYTHON_DOTENV_DISABLED=1`; log: `logs/f4-sqlite-final.txt`.
  Aumento de **92 testes** sobre o baseline. Goldens dos dois modelos novos verdes.
- Regressões portadas/adaptadas: numeração e colisão, modelos, assunto,
  capitalização, destinatário, rodapé, motorista, diárias, bate-volta e prazo da
  justificativa. Testes de integração reexpressam o fluxo V3.2, autorização,
  transporte manual, herança do termo, lote, cache por origem e assinatura manual.
  Contratos de HTML/rotas específicos do wizard e dos apps excluídos não são
  reproduzidos literalmente.
- `check` sem problemas; `makemigrations --check --dry-run` sem alterações.
  Migrações aditivas aplicadas no desenvolvimento, sem flush, reimportação ou
  alteração dos registros existentes. Porta de validação: **8021**.
- Pela interface foi criado o **Ofício 01/2026, ID 1**, identificado como
  “VALIDAÇÃO F4 — SEM EFEITO ADMINISTRATIVO”, com dois servidores. Gerados ofício,
  justificativa e termos individuais/lotes DOCX/PDF. O roteiro final é o ID 5;
  o documento mostra **R$ 755,44**, saída em **09/11/2026 às 08:00** e retorno
  em **10/11/2026 às 19:00**. Também foi criado o termo avulso ID 1 e emitida a
  variante sem viatura. Arquivamento, cancelamento e reativação do ofício foram
  exercitados pela interface; ele permanece arquivado. O termo avulso de teste
  foi cancelado com motivo explícito; o modelo de justificativa usado na prova
  foi desativado.
- DOCX abertos com `python-docx`; PDFs produzidos por **Word/COM**, abertos com
  `pypdf` e conferidos visualmente após renderização Poppler. Cada PDF conferido
  tem uma página. O visualizador PDF do navegador integrado exibiu tela vazia;
  a conferência visual foi feita nas páginas renderizadas dos mesmos arquivos.
  Cópias, textos extraídos e manifesto: `logs/fase4-documentos/` (ignorado pelo Git).
- Telas conferidas no navegador: lista/criação/edição/resumo de ofício, catálogos
  de motivo/justificativa, configuração institucional, assinantes, numeração,
  lista/criação/edição/resumo/prévia de termo e anexação de PDF assinado. Calendário,
  filtro UF→município e aplicação de modelo exercitados na interface.
- Os dois binários novos são idênticos aos do GV (SHA-256):
  `d06aee505d3212bae8e3d5457582a6f06fec66ecb90c577ec617a0b9ab03b586` e
  `0dd889636f6e82c5810e46709907bceeae18c948ec43cd0ab50453c687fdf7f1`.
  Todas as operações nesta tarefa sobre a pasta GV foram somente leituras;
  nenhum comando foi executado com aquele diretório de trabalho.

## Achados existentes e próxima fase

O teste histórico de migração da F1 restaura o grafo até seu alvo antigo e pode
remover tabelas de fases posteriores no banco de testes. Seu código não foi
alterado: o teste transacional novo restabelece as folhas do grafo antes da prova
concorrente. Houve também interferência entre execuções simultâneas no banco de
testes padrão; a prova final PostgreSQL usou `test_eventos_sociais_f4_validation`
como `DATABASES['default']['TEST']['NAME']`, preservando o banco de desenvolvimento.
O diagnóstico nativo RPC do Word já observado na F3 reapareceu sem falhar a suíte.

A F5 deve ligar prestações/servidores ao ofício, preencher os números de
solicitação no contexto documental (`_solicitacoes_por_servidor` está vazio nesta
fase), acrescentar suas origens documentais em migração própria e respeitar o
cancelamento, o snapshot do efetivo e os artefatos assinados/versionados. A F6
deverá importar números históricos, pisos e lacunas deliberadas antes da virada.
As alterações preexistentes de cadastros, solicitações e interface foram
preservadas. A organização em commits fica pendente da autorização do usuário.

## Revisão da fase (09/09/2026)

Revisão independente, com os gates reexecutados. Confirmados: `check` e
`makemigrations --check` limpos; os dois modelos binários novos e seus goldens
idênticos aos da origem; repositório do GV intocado; ausência de tenancy e de
vínculo com o app de eventos da origem; unicidade global `(ano, numero)`;
autorização por módulo em todas as rotas, perfil de operador em toda escrita e
perfil de gestor na configuração da numeração; nenhum controle nativo de data ou
seleção nos formulários; e os sete testes que o plano exigia, incluindo duas
reservas simultâneas e o reaproveitamento da menor lacuna. Isolada, a fase roda
com **90 testes verdes**; junto com a F1, **177 verdes**.

Dois ajustes foram aplicados sobre o que foi entregue.

1. **Arredondamento do dinheiro na origem.** A conversão do total da equipe para
   o valor por servidor dividia sem arredondar: R$ 100,00 para três produzia um
   `Decimal` de 28 casas. O documento saía certo, porque o formatador arredonda
   ao imprimir, mas o valor cru ia para o instantâneo gravado no artefato e seria
   herdado pela prestação de contas na F5. Agora a divisão é arredondada a
   centavos, com a mesma regra do formatador. Junto, o caso em que o efetivo do
   ofício é igual ao do roteiro passou a devolver o total já persistido pela F2,
   em vez de dividir e multiplicar de volta — a ida e volta devolvia
   99,999... no lugar de 100,00. O caso de um servidor, que já era tratado assim,
   virou um subconjunto dessa regra. Dois testes novos fixam os dois
   comportamentos.
2. **Documentação da numeração recuperada.** O módulo portado explicava, na
   origem, por que a colisão é identificada pelo metadado da exceção e não pelo
   texto da mensagem; o porte reduziu isso a uma linha, e o argumento que impede
   alguém de "simplificar" de volta se perdeu. O texto foi restaurado e adaptado
   (escopo global por ano, um único documento numerado) e as mensagens citadas
   foram medidas nesta instalação, nos dois bancos. Uma observação nova: aqui o
   PostgreSQL responde **em português**, o que torna a leitura de texto ainda
   mais frágil do que era na origem.

Pontos deixados como estão: o app de termos não tem pasta de testes própria (os
testes de termo vivem no app de ofícios); e o relatório afirma autorização
expressa para acrescentar `ConfiguracaoSistema` e `AssinaturaConfiguracao` ao app
de cadastros da F1, o que não pôde ser confirmado nesta revisão.

Estado da suíte completa no momento da revisão: **vermelha por causa da F5 em
obras** — modelos de relatório técnico e diário de bordo entraram sem os
respectivos goldens, e os testes de prestações ainda falham. Três testes de
integração da F4 também acusam erro apenas na suíte completa, e passam quando a
fase roda sozinha ou pareada com a F1: há estado compartilhado entre apps a
investigar quando a F5 fechar.
