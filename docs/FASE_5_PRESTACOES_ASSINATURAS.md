# Fase 5 — Prestações de contas e assinatura pública

Implementação iniciada em 09/09/2026 e encerramento em 10/09/2026. Nenhum comando
de commit ou push foi executado por esta tarefa. Baseline antes do porte:
**737 testes**, PostgreSQL, 228,000 s, sem falhas, quatro testes ignorados por
dependências opcionais; `check` limpo e nenhuma migração pendente. Os relatórios
das fases 3 e 4 foram consultados antes das alterações.

## Entrega F5a

- App `viagens_prestacoes`, sem área/tenancy: prestação 1:1 com ofício, parte
  individual por servidor, relatório técnico compartilhado com saída individual,
  modelos de texto, diário e trechos, anexos e posições de carimbo.
- Diário antes do RT, seguido de documentos e PDF final. Telas V3.2 com filas,
  busca, navegação individual, campos de data e seleção do sistema, lateral que
  acompanha a rolagem e ações de salvar, finalizar, reabrir e arquivar.
- Estados preservados: pendente, em preenchimento, enviada, aprovada e reprovada.
  Finalização e arquivamento são flags independentes, conforme o GV; finalizar
  não exige os mesmos pré-requisitos que gerar o PDF final.
- Remoção reversível: linhas preenchidas saem do manager de ativos, mas continuam
  em `PrestacaoServidor.todos`; a volta à equipe recupera anexos, solicitação e
  assinaturas. Somente linhas sem dados coletados são excluídas. A reconciliação
  também cobre alterações pela relação M2M reversa.
- Roteiro ajustado criado sob transação e bloqueio da prestação, copiando trechos
  e componentes da F2. O ofício permanece com seu roteiro original. Motorista
  efetivo do diário pode diferir do motorista inicialmente indicado no ofício.
- Quilometragem validada no formulário e autosave; alterações conjuntas dos dois
  valores são validadas em conjunto. Valores por servidor adaptam o total da F2
  ao contrato individual do GV. Datas documentais usam horário local e dinheiro
  usa a localização do Django.
- Despachos e comprovantes aceitam múltiplos anexos. PDFs assinados de ofício,
  RT e diário têm substituição controlada. Limite de 10 MB com validação de
  extensão e conteúdo: PDF legível ou imagem realmente identificada pelo Pillow.
  Arquivos são servidos por views autorizadas, sem rota pública `MEDIA_URL`.
- Carimbo transporta o deslocamento entre número e nome na referência gerada
  para o nome no PDF recebido. Número é lido de `numero_solicitacao` ao desenhar.
  Original é preservado para recarimbar sem acumular texto. Uma âncora ausente
  recusa a operação; não há fallback para coordenada absoluta. Fragmentos de
  texto produzidos pelo Word e página adicional de protocolo estão cobertos.
- RT DOCX/PDF e diário XLSX/PDF pela façade F3, síncronos. Planilha usa Excel/COM
  ou LibreOffice para preservar o formulário; erro amigável se não houver motor
  disponível. `reportlab>=5.0,<6.0`, na faixa do GV, suporta os overlays.
  Não há QR no fluxo portado, portanto `qrcode` não é dependência necessária.
- A sonda de disponibilidade do Excel inicializa e libera COM na thread que
  atende o pedido. O defeito foi reproduzido na máquina: principal retornava
  disponível, worker retornava indisponível. Após a correção, ambas detectam o
  Excel; conversão real em worker produziu PDF de uma página. Dois testes
  adicionais verificam a inicialização e a liberação inclusive em falha.
- Consolidação por `pypdf`, na ordem **ofício → despacho(s) → RT(s) → diário(s)
  → comprovante(s)**. Dentro de cada documento, prevalece o PDF assinado enviado
  pelo operador, depois a assinatura eletrônica, depois o gerado. O painel de
  downloads diferencia explicitamente original e assinado.
- Novos tipos e formato XLSX no núcleo documental, FK de origem em
  `DocumentoArtefato`, modelos binários e goldens RT/diário copiados do GV.

## F5b e correção do mecanismo de assinatura (§5.6)

**O destino guarda somente SHA-256 de `secrets.token_urlsafe(32)`, com validade
padrão de sete dias. Não existe campo para token recuperável nem uso de Fernet
nesta fase.** O link completo aparece somente na resposta da emissão. Para
obter outro link, o operador emite novamente e revoga o anterior.

Há uma divergência entre a descrição recebida e a cópia do GV disponível:
o `AssinaturaDocumento` daquela cópia ainda declara token cifrado e sua
confirmação solicita CPF completo. Foram seguidas as exigências explícitas da
tarefa: hash sem token armazenado, confirmação do nome e **cinco primeiros
dígitos do CPF**, sem solicitar o restante. Esta adaptação é deliberada; não se
atribui ao código do GV um comportamento que ele ainda não tem nessa cópia.

O fluxo permite assinatura por seis fontes manuscritas locais ou desenho à
mão, com PNG transparente produzido no navegador, arraste, redimensionamento
e seleção de página. As fontes preservam os avisos de autoria dos binários
e a licença OFL 1.1 junto aos arquivos. Não há envio automático de mensagens.

Cada emissão guarda um PDF de origem próprio, hash do conteúdo, nome e HMAC do
prefixo de CPF esperado. A assinatura verifica o hash de origem e carimba esse
snapshot, mesmo que o RT seja posteriormente editado. PNG, PDF resultante,
horário, IP, posição, modo, hash do assinado e código de verificação são
persistidos. O código tem unicidade no banco e uma página pública de consulta.

Reenviar a assinatura é recusado, sem sobrepor outro carimbo. Revogação e nova
emissão mantêm os PDFs, PNGs, hashes e código anteriores na trilha histórica.
A verificação de um documento revogado mostra essa condição. Na interface, a
reabertura de assinatura exige revogar e emitir novamente.

### Proteções acrescentadas ou reforçadas

- Token inexistente, expirado, adulterado e revogado recebe o mesmo status 410
  e corpo genérico em todas as rotas que usam token, inclusive PDF e conclusão.
- Cinco erros de identidade bloqueiam o documento por 15 minutos. A contagem
  e o bloqueio ficam no banco, protegidos por transação, resistindo a novas
  sessões, IPs e reinícios do cache. Há ainda limite geral de 120 requisições
  por IP/minuto no cache; esse limite geral é por processo quando se utiliza
  o cache local padrão, enquanto o bloqueio de identidade permanece compartilhado.
- A sessão armazena somente uma chave derivada do hash do token para liberar o
  PDF. O hash de prefixo de CPF usa HMAC com a chave da aplicação; não se guarda
  uma segunda cópia do CPF completo na assinatura.
- Páginas HTML públicas mostram apenas nome e documento do signatário, sem
  telefone ou equipe. O PDF só é liberado após confirmação e pode conter o CPF
  exigido pelo modelo documental; essa distinção faz parte do contrato.
- CSRF permanece obrigatório. A exceção autorizada pelo usuário se restringe
  ao namespace `viagens_assinaturas` no middleware de troca obrigatória de senha.
  O namespace público não é registrado no middleware de módulo; as rotas de
  emissão, revogação e downloads internos continuam sob VIAGENS e permissões
  de operação. Um usuário com senha pendente também pode assinar publicamente.
- Respostas públicas usam `no-store`, `nosniff`, `noindex` e política de referência
  `same-origin`: não envia o token a outro site e preserva o cabeçalho Origin
  necessário ao CSRF. O navegador revelou que `no-referrer` produzia Origin
  `null` neste fluxo; a correção manteve a validação CSRF estrita.
- PNG exige conteúdo válido, transparência, traços visíveis, até 2 MB e até
  oito milhões de pixels; é reprocessado para remover metadados. Coordenadas
  não finitas, posição fora da página e número de página inválido são recusados.
- O código de verificação tem linha própria na legenda, sem ser truncado por
  nomes extensos. A posição continua sendo escolhida pelo signatário.
- Auditoria registra o nome da rota pública, sem copiar o token do caminho.
  Hash do token e HMAC do CPF não entram nos deltas de auditoria. Eventos de
  criação, confirmação, assinatura e revogação seguem a auditoria por signals.
- Contexto transacional de arquivos compensa os arquivos novos se a gravação
  falhar. Abrange uploads, carimbos, assinatura e artefatos gerados pela F3.
  Arquivos anteriores não são removidos antes do commit.

## Migrações e manutenção

- `viagens_prestacoes/0001`: modelos da prestação; `0002`: campos privados com
  compensação de gravação; `0003`: assinatura pública; `0004`: unicidade do código.
- `documentos/0003`: FK da prestação e ampliação dos tipos/formatos.
- Migrações de esquema aplicadas no desenvolvimento, sem importação de dados
  do GV, flush ou limpeza de dados reais.
- `sincronizar_prestacao_servidores`: diagnóstico por padrão; `--confirmar`
  aplica a mesma remoção reversível dos signals.
- `diagnosticar_roteiros_ajustados`: somente leitura.
- `mesclar_roteiros_ajustados_identicos`: diagnóstico por padrão; `--confirmar`
  aplica somente às cópias idênticas, revalidando dentro da transação.
- `limpar_arquivos_orfaos`: cruza todos os FileFields, incluindo assinaturas
  revogadas; lista por padrão e só remove com `--apagar`.

Os quatro comandos foram executados em modo diagnóstico no desenvolvimento:
equipe sincronizada, nenhum roteiro ajustado candidato e nenhum arquivo órfão
ao final. Resíduos de 188 fixtures das primeiras execuções foram retirados de
`media` com cópia ZIP e manifesto SHA-256 em `logs`, sem tocar documentos
referenciados. Os testes da F5 agora isolam seu próprio MEDIA_ROOT, inclusive
quando executados pelo comando habitual `manage.py test`.

## Validação

- F5a foi fechada antes da F5b com **1.005 testes**, PostgreSQL, 138,824 s,
  sem falhas e quatro skips opcionais.
- Suítes completas com os hashers normais de senha: **1.048 testes** em
  PostgreSQL (552,951 s, quatro skips) e SQLite (529,140 s, cinco skips), verdes.
- Após a correção da sonda Excel e seus dois testes novos, o gate completo final
  ficou em **1.050 testes**: PostgreSQL **216,149 s** e SQLite
  **94,195 s**, ambos verdes. Nesta repetição, apenas o hasher
  de senha foi trocado por MD5 no ambiente de teste para reduzir o tempo;
  nenhum teste, motor documental ou persistência foi desligado.
- Quatro skips são do WeasyPrint sem bibliotecas nativas, já presentes no
  baseline. SQLite tem ainda o skip de concorrência por advisory lock exclusivo
  do PostgreSQL. Os motores Word, LibreOffice e fallback simples foram exercitados.
- Os 306 testes do app também passaram no PostgreSQL após isolar os diretórios
  temporários das fixtures. Excel real foi detectado e converteu XLSX em uma
  thread de trabalho; testes simulados cobrem a liberação de COM em falha.
- `manage.py check`: nenhum problema. `makemigrations --check --dry-run`:
  nenhuma alteração pendente. Goldens RT DOCX e diário XLSX verdes, incluindo
  o manifesto binário SHA-256.
- Logs locais: `f5-baseline.txt`, `f5a-postgresql-verde.txt`,
  `f5-final-postgresql.txt`, `f5-final-sqlite.txt`,
  `f5-gate-final-postgresql.txt`, `f5-gate-final-sqlite.txt` e
  `f5-isolamento-postgresql.txt`, em `logs/`. O runner local usa `call_command`
  do Django, banco PostgreSQL de teste exclusivo e MEDIA_ROOT temporário;
  não reutiliza o banco de testes de outras tarefas nem o banco de dev.

Os arquivos de testes solicitados foram portados, inclusive as duas superfícies
de assinatura e os casos de remoção/retorno seguro dependentes da F5b. Não foram
portados os três arquivos expressamente excluídos por dependerem de área ou da
régua de desempenho da origem.

Gates adicionais cobrem remoção/restauração, consolidação com contagem e ordem
de páginas, transporte da âncora após página extra, autorização, falhas de
gravação sem órfãos, comparação de tokens inválidos, CSRF, throttle persistente,
snapshot adulterado, preservação histórica, recusa de carimbo duplicado e
prioridade dos documentos assinados.

### Conferência pela interface contra o PostgreSQL de desenvolvimento

1. Ofício de validação `01/2026`: abrir prestação, preencher diário com KM
   12000→12250→12500, salvar RT de teste, informar solicitação, anexar despacho
   e comprovante, baixar consolidado de cinco páginas e finalizar o servidor.
   O PDF foi aberto e as páginas RT e diário foram conferidas visualmente.
2. Ofício gerado pela cadeia nativa recebeu uma página inicial sintética de
   protocolo. O upload localizou a âncora do servidor na página seguinte e
   carimbou o número. Isso não substitui o aceite futuro com um PDF real
   devolvido pelo protocolo; nenhum PDF real com âncora ausente foi encontrado.
3. Ofício `900005/2026`, claramente destinado à validação, com signatário
   fictício: emitir link pela tela, abrir contexto Chromium sem autenticação,
   confirmar nome e prefixo, escolher fonte, arrastar e enviar o RT. Repetir
   no diário com desenho à mão e redimensionamento. Baixar os PDFs assinados
   pelo painel interno, abrir e conferir os campos e códigos. Sem erros JS.
4. Revogar e reemitir pela interface preservou os resultados anteriores. A
   trilha do banco foi conferida: caminhos públicos sem token e eventos de
   confirmação/assinatura registrados.

Evidências locais em `logs/f5-ui/`: `consolidado-teste.pdf`,
`protocolo-sintetico-teste.pdf`, `rt-assinado-publico.pdf`,
`db-assinado-publico.pdf` e capturas das etapas. Os artefatos são de teste,
sem efeito administrativo. Não se atribuíram CPFs fictícios aos servidores
reais existentes. Dados institucionais ausentes continuam sem ser inventados.

Foram comparados novamente os SHA-256 dos **105 arquivos de origem** registrados
antes do porte: nenhuma divergência. Nenhum comando foi executado com diretório
de trabalho dentro do GV e nenhum arquivo de lá foi alterado.

## O que a Fase 6 precisa migrar e conferir

1. Mapear IDs legados de ofício, servidor, prestação e parte individual,
   incluindo linhas removidas e todas as flags, datas e valores individuais.
   Colapsar áreas somente depois de resolver colisões de unicidade global.
2. Migrar RT compartilhado, modelos de texto e diários/trechos, mantendo a
   diferença entre motorista do ofício e motorista efetivo, e preservando
   roteiro ajustado com seus componentes de diária.
3. Copiar anexos e originais sem alteração de bytes, gerar manifestos por hash,
   verificar tamanho/conteúdo e colocar inconsistências em quarentena. Não
   descartar originais de carimbo nem recriar PDFs assinados durante o ETL.
4. Preservar snapshot, PNG, PDF assinado, hashes, código, horários, posições e
   condição de revogação das assinaturas. Resolver colisões de código em
   quarentena, sem substituir silenciosamente o valor impresso no PDF.
5. **Links do GV não são importáveis como tokens recuperáveis neste modelo.**
   O ETL deve encerrar links pendentes antigos e planejar novas emissões sob o
   domínio de destino. Copiar evidências assinadas não implica reabrir links.
   Não transportar Fernet/ciphertext para um campo inexistente nem presumir que
   os HMACs de CPF de ambientes com chaves diferentes são intercambiáveis.
6. Relacionar artefatos F3 às prestações e reconciliar arquivos de todos os
   modelos, inclusive registros removidos/revogados, antes de qualquer limpeza.
7. Validar sob o usuário real do serviço Windows a geração Word/Excel ou
   LibreOffice, permissões do storage privado, domínio público/HTTPS, coleta
   de estáticos e política do proxy para não registrar tokens em URLs.
   Configurar cache compartilhado se houver múltiplos processos e se for
   necessário que o throttle geral por IP tenha limite global.
8. Conferir nome/CPF cadastral e configuração institucional antes de emissão
   administrativa. A virada precisa de PDF real de protocolo para aceite da
   âncora, além dos casos sintéticos e nativos já exercitados.

Não foram introduzidos Drive, eProtocolo, Celery, plano de trabalho ou ordem
de serviço. Helpers de nomenclatura usados pelos documentos foram extraídos
sem transportar dependências de negócio desses domínios.
