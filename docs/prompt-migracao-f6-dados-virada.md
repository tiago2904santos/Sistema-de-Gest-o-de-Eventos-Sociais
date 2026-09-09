# Prompt para o Codex — Fase 6 da unificação: migração dos dados e virada

> Só comece depois que as **Fases 3, 4 e 5** estiverem entregues e verdes: não se migra dado para tabela que ainda não existe.
> Esta é a fase que mexe com dado real de gente real. Nada aqui roda em produção sem ensaio.
> Copie tudo abaixo da linha e cole no Codex.

---

## 1. Quem é você nesta tarefa

Você é um desenvolvedor Django sênior no repositório **Sistema de Gestão de Eventos Sociais** da Polícia Civil do Paraná (PCPR), em `C:\Users\tiago\OneDrive\Documentos\Solicitações de eventos`.

O domínio do **Gerenciador de Viagens** (Central de Viagens 3, daqui em diante **GV**) foi portado para cá ao longo das fases 1 a 5, conforme `docs/PLANO_MESTRE_UNIFICACAO.md`. **Sua tarefa é a Fase 6: trazer os dados que hoje vivem no banco do GV e preparar a virada**, em que o GV passa a ser somente leitura e os usuários operam aqui.

Código do GV, **somente leitura**, para consultar esquema e regras:

```
C:\Users\tiago\OneDrive\Documentos\Gerenciador de Viagens
```

**Nunca grave, edite ou rode nada dentro dessa pasta, e nunca escreva no banco do GV.** A fonte é lida, jamais alterada.

Regra número um desta fase: **nada é irreversível.** Todo comando roda em simulação por padrão, toda linha importada carrega a marca da origem, e existe um caminho de volta.

## 2. Ambiente e comandos

- Django 6.1, Python 3.14, virtualenv em `.venv`. Windows.
- Interpretador: `.venv\Scripts\python.exe`. Testes: `.venv\Scripts\python.exe manage.py test`.
- Servidor: `.venv\Scripts\python.exe manage.py runserver 8021` — **sempre com porta**.
- Banco de destino em dev: PostgreSQL `eventos_sociais`, com dados reais de produção de eventos. Trate como se fosse produção.
- Banco de origem: PostgreSQL do GV (nome definido por `DB_NAME` no `.env` dele; em dev costuma ser `central_viagens_3`, em `127.0.0.1:5432`).
- Antes de escrever: rode a suíte inteira e **anote o número de testes**; leia os relatórios das fases 1 a 5 em `docs/` e a seção 10 de `docs/AUDITORIA_UNIFICACAO_2026-08.md`, que define a técnica que você vai seguir.

## 3. Como a leitura da origem funciona

Sem acoplamento de código entre os dois projetos. Você configura uma segunda conexão de banco chamada `legado` em `config/settings.py`, preenchida por variáveis de ambiente (`LEGADO_DB_NAME`, `LEGADO_DB_USER`, `LEGADO_DB_PASSWORD`, `LEGADO_DB_HOST`, `LEGADO_DB_PORT`), e lê por SQL ou por modelos não gerenciados **em pasta separada**, nunca importando código do GV.

Se as variáveis não estiverem definidas, o projeto tem que subir normalmente e a suíte tem que passar: a conexão `legado` é opcional e só existe quando alguém vai migrar.

## 4. O que você vai entregar

1. Um comando de migração por entidade, na ordem de dependência, idempotente e reversível.
2. Um relatório de execução com contagens e rejeições, e uma quarentena para arquivos que não passarem na revalidação.
3. Um comando que desfaz exatamente o que foi importado.
4. Uma matriz de paridade que prova que o que chegou é o que existia lá.
5. Um roteiro de virada, escrito, com o que fazer antes, durante e depois da janela.

## 5. Decisões já tomadas — não reabra

1. **Idempotência por marca de origem.** Toda linha importada grava `legado_origem="gerenciador_viagens"` e `legado_pk` (o id na origem), com `UniqueConstraint` condicional. Reexecutar atualiza, nunca duplica. O padrão já existe em `viagens_cadastros/models.py` (campos `legado_origem`/`legado_pk` e a constraint condicional) — siga-o, e acrescente os campos aos modelos das fases 2 a 5 que ainda não os tiverem, em **migração de esquema própria**.
2. **Simulação por padrão.** Todo comando roda em `--dry-run` e só grava com `--commit` explícito. Nenhuma exceção.
3. **Sem multi-tenancy no destino.** A origem recorta tudo por `AreaTrabalho`; aqui não existe área. O comando recebe `--area` (uma ou mais) para escolher o que importar, e a coluna some no destino.
4. **Usuários vêm com o hash da senha.** Os dois lados usam PBKDF2 do Django, então o hash é compatível: ninguém precisa redefinir senha na virada. Usuário do GV que já existe aqui (mesmo `username` ou e-mail) é **vinculado**, não duplicado — e nesse caso a senha que vale é a daqui.
5. **Documentos não são regerados por padrão.** O arquivo que foi assinado e protocolado é o que vale: copie o binário e confira pelo hash. Regerar é opção explícita (`--regerar-documentos`), para casos em que o arquivo se perdeu.
6. **Anexo que falhar na revalidação vai para quarentena**, com relatório. Nunca descarte em silêncio.
7. **Fora de escopo continuam fora**: planos de trabalho, ordens de serviço, Google Drive, eProtocolo e o app de eventos agrupadores do GV. Dado dessas áreas não vem. Se uma FK apontar para lá, ela chega vazia e o motivo entra no relatório.

## 6. Ordem dos comandos

Um comando por entidade, em `viagens_cadastros/management/commands/` e nos apps correspondentes, ou todos num app novo `migracao_legado` — escolha e justifique no relatório. A ordem de execução é de dependência, e o comando de cada etapa recusa rodar se a anterior não rodou:

1. **Usuários** — contas do GV para `accounts.User`, com hash, vínculo ao setor e ao módulo `VIAGENS`.
2. **Cadastros** — unidades, cargos, combustíveis, servidores, viaturas, tabelas de diária (com vigência).
3. **Geografia** — completar `cadastros.Municipio` com o que a base do GV tiver a mais (capital, latitude, longitude), sem apagar o que já existe aqui.
4. **Roteiros** — roteiros, destinos, trechos e componentes de diária gravados.
5. **Ofícios** — ofícios, numeração e lacunas, justificativas, termos de autorização.
6. **Documentos** — artefatos gerados, com arquivo e hash.
7. **Prestações** — prestações, servidores da prestação, relatórios técnicos, diários de bordo e trechos, anexos, carimbos, assinaturas.

Cada comando aceita `--dry-run` (padrão), `--commit`, `--area`, `--limite` (para ensaio), e escreve um relatório com criadas, atualizadas, ignoradas e reprovadas, mais o arquivo de rejeições com o motivo linha a linha.

### Reversão

`desfazer_migracao_viagens --commit` remove exatamente o que foi importado, na ordem inversa, e **só o que ninguém referenciou depois**: antes de apagar, verifica FKs reversas de origem nativa e recusa a remoção, listando os bloqueios.

## 7. Arquivos

Os binários vivem em `media/` no GV. O comando copia para o `media/` daqui, preservando a relação com o registro, e:

- confere hash quando a origem tiver hash gravado;
- revalida extensão e tamanho pelas regras deste sistema;
- manda para quarentena (pasta própria + linha no relatório) o que não passar;
- nunca sobrescreve arquivo existente sem que o hash bata.

Meça o volume total antes de rodar: `media/` do GV pode ser grande, e o destino roda em disco sob OneDrive, que é lento e sincroniza. Se o volume for alto, avise no relatório antes de copiar.

## 8. Matriz de paridade

Depois de cada ensaio, gere e confira. Tudo isto tem que bater:

| Verificação | Critério |
| --- | --- |
| Contagem por entidade | destino = origem, menos as rejeições justificadas no relatório |
| Ofícios por ano e número | mesma sequência, sem colisão e sem lacuna nova |
| Soma das diárias por roteiro | idêntica ao centavo |
| Componentes de diária | mesma vigência de tabela apontada, parcela a parcela |
| Documentos | mesmo hash dos arquivos copiados; nenhum artefato órfão |
| Prestações finalizadas | mesmo status, mesmo conjunto de servidores, mesmos anexos |
| Assinaturas válidas | mesma quantidade; nenhum token importado em texto claro |
| Usuários | todos conseguem autenticar com a senha antiga (teste com hash real em homologação) |
| Amostra dirigida | 20 ofícios, 10 prestações e 10 roteiros conferidos campo a campo contra a tela do GV |

Escreva a matriz como **comando** (`paridade_migracao --area X`), não como planilha manual: ela vai rodar mais de uma vez.

## 9. Ensaios e virada

**Ensaios:** pelo menos duas execuções completas em ambiente de homologação, com a matriz verde, antes de qualquer janela. Registre o tempo de cada etapa — é o que dimensiona a janela.

**Roteiro de virada** (escreva em `docs/VIRADA_VIAGENS.md`):

1. Avisar os usuários com antecedência combinada.
2. `pg_dump` do destino antes de tudo.
3. GV em somente leitura (o modo e como ligá-lo, descrito passo a passo).
4. Rodar os comandos na ordem, com `--commit`, guardando os relatórios.
5. Rodar a matriz de paridade.
6. Ligar os setores ao módulo `VIAGENS` para quem precisa (decisão DA6 do plano, ainda aberta — pergunte ao dono do produto quais setores).
7. Comunicar o novo endereço e o que mudou.
8. Critério de rollback: qual falha justifica desfazer, e quem decide.

Deixe explícito no documento o que **não** vem junto (planos de trabalho, ordens de serviço, Drive, eProtocolo) e que o GV continua disponível como consulta.

## 10. Armadilhas conhecidas

- **Nunca edite arquivo com acento usando `Set-Content` / `Get-Content` do PowerShell.**
- **Migração de dados nunca divide arquivo com migração de esquema.** Foi assim que a F1 quebrou em PostgreSQL: o banco recusa alterar tabela com gatilho pendente na mesma transação.
- **Rode a suíte em PostgreSQL e em SQLite.**
- **Data e hora do banco estão em UTC**: ao comparar com o GV, compare no mesmo fuso, senão a paridade acusa diferença que não existe.
- **Dado normalizado no destino**: aqui CPF é só dígito, placa é sem hífen e nome de servidor é maiúsculo. A comparação da paridade tem que normalizar dos dois lados antes de comparar.
- **Fusão de duplicados**: a F1 já fundiu motoristas que eram a mesma pessoa. Ao trazer servidores, um CPF que já existe aqui é a **mesma pessoa** — vincule, não crie outro.
- **Transação e arquivo não se misturam bem**: copie o arquivo fora da transação que grava a linha, ou trate o órfão.

## 11. Testes

Testes viajam com o código. Obrigatórios:

1. Cada comando roda em `--dry-run` sem gravar nada.
2. Rodar duas vezes com `--commit` produz o mesmo resultado (idempotência), sem duplicar.
3. Linha da origem com dado inválido é rejeitada com motivo, sem derrubar a execução.
4. `desfazer_migracao_viagens` remove o que foi importado e **recusa** remover o que ganhou referência nativa depois.
5. Servidor com CPF já existente é vinculado, não duplicado.
6. Usuário importado autentica com o hash migrado.
7. A matriz de paridade acusa diferença quando você planta uma de propósito (o teste que prova que a matriz serve para alguma coisa).
8. Anexo reprovado vai para quarentena e aparece no relatório.

Use uma base de origem sintética nos testes (fixtures ou banco de teste alimentado pelo próprio teste). Não dependa do banco real do GV para a suíte passar.

## 12. Gates de saída

1. Suíte inteira verde, com número de testes maior que o baseline; verde também em SQLite.
2. `makemigrations --check --dry-run` limpo; `manage.py check` sem avisos novos.
3. Dois ensaios completos documentados, com a matriz de paridade verde e o tempo de cada etapa registrado.
4. Reversão exercitada de verdade: importar, desfazer, conferir que o destino voltou ao estado anterior.
5. `docs/VIRADA_VIAGENS.md` escrito e revisável por quem não acompanhou o desenvolvimento.
6. Nenhum arquivo do repositório do GV alterado e nenhuma escrita no banco de origem.

## 13. Como entregar

Commits pequenos, nesta ordem, cada um com a suíte verde:

1. Conexão `legado` opcional + leitura da origem + campos `legado_origem`/`legado_pk` faltantes (migração de esquema).
2. Usuários.
3. Cadastros e geografia.
4. Roteiros.
5. Ofícios, justificativas e termos.
6. Documentos e arquivos.
7. Prestações, anexos e assinaturas.
8. Comando de reversão.
9. Matriz de paridade.
10. Documento de virada e relatório final.

Relatório final em `docs/`, no estilo das seções de fase do plano mestre: o que foi migrado, contagens dos ensaios, o que foi rejeitado e por quê, o que ficou de fora, e as decisões que ainda dependem do dono do produto (DA4, DA5 e DA6 do plano continuam abertas). Atualize a seção "Fase 6" do `PLANO_MESTRE_UNIFICACAO.md`.

**Não faça commit nem push sem pedir. Não rode nada com `--commit` contra produção sem autorização explícita do dono do produto.**

## 14. Pare e pergunte se

- o esquema da origem divergir do que as fases 1 a 5 assumiram, a ponto de exigir campo novo no destino;
- houver dado na origem que não tem para onde ir aqui (por exemplo, ofício ligado a plano de trabalho);
- o volume de `media/` inviabilizar a cópia na janela prevista;
- a paridade não fechar e a diferença não tiver explicação documentável;
- alguém pedir para rodar em produção sem os dois ensaios.
