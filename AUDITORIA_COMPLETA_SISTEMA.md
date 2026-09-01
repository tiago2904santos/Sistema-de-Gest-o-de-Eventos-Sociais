# Auditoria completa do sistema

**Escopo:** funcionamento, regras de negócio, permissões, UI/UX, componentes, acessibilidade, responsividade, desempenho e experiência de uso  
**Data da auditoria:** 31 de agosto de 2026  
**Sistema:** Solicitações de Eventos  
**Natureza do trabalho:** diagnóstico somente; nenhuma correção foi implementada

---

## 1. Resumo executivo

O sistema está tecnicamente saudável, visualmente coeso e com uma base automatizada acima da média para o seu porte. A suíte completa executou **214 testes com sucesso**, o `manage.py check` não apontou problemas e os fluxos centrais de solicitação de evento, Coffee Break e Demandas ASCOM puderam ser exercitados de ponta a ponta em uma base isolada.

O principal risco não está na estabilidade geral, mas em **autorização e governança de dados**. A regra atual permite que qualquer usuário autenticado que enxergue uma solicitação de evento registre o cancelamento de uma solicitação criada por outra pessoa. Esse comportamento é explícito no código e em teste automatizado. Também há visibilidade ampla de solicitações já enviadas, atribuição de responsáveis de Demandas ASCOM fora do setor e ausência de uma interface para vincular setores ao cadastrar usuários.

Na experiência de uso, o desenho institucional é consistente e os componentes principais funcionam bem. Os maiores atritos são validações que não aparecem para o usuário, linhas de tabela acionáveis apenas com mouse, uma busca que não responde ao Enter, páginas de erro desconectadas do produto e formulários muito longos no celular. A tela de detalhe de Demanda ASCOM tem ainda um defeito objetivo: seu título principal fica vazio.

### Avaliação global

- **Confiabilidade técnica:** boa. Suíte verde, transições importantes testadas e sem erros de sistema do Django.
- **Cobertura funcional:** boa nos três módulos, com lacunas operacionais nos cadastros de Coffee Break e na administração de acessos.
- **Segurança e permissões:** requer ação imediata. Há regras permissivas que precisam ser confirmadas ou restringidas.
- **UI/UX:** boa base visual; consistência e feedback podem melhorar nos fluxos de maior risco.
- **Acessibilidade:** parcial. Há semântica positiva em vários controles, mas falhas de teclado e associação de erros.
- **Responsividade:** funcional sem estouro horizontal global nas páginas avaliadas; densidade e navegação móvel ainda prejudicam a eficiência.
- **Desempenho:** adequado para o volume atual; existem consultas repetidas que escalam mal.

### Prioridades

1. Validar e restringir, se não for uma exigência formal, o cancelamento de eventos por terceiros.
2. Definir a política de visibilidade dos dossiês enviados e de atribuição de responsáveis entre setores.
3. Permitir a concessão de acesso por setor na administração de usuários.
4. Exibir todos os erros obrigatórios no envio de solicitação e impedir estados de domínio inválidos fora da camada de serviço.
5. Corrigir a operação por teclado das tabelas e o título vazio de Demanda ASCOM.

---

## 2. Método e limites

### Evidências utilizadas

- Leitura de URLs, views, forms, models, services, permissions, templates, componentes, JavaScript, CSS, configurações e testes.
- Execução de `manage.py check` e da suíte completa.
- Navegação real em navegador, com três perfis sintéticos: administrador, solicitante e gestor da DG.
- Exercício de criação, edição, transições, validações, filtros, ordenação, exportação, anexos e bloqueios por permissão.
- Verificação responsiva em desktop e celular, além de inspeções intermediárias de layout.
- Medição de consultas e tempo de resposta no servidor com o cliente de testes do Django.
- Comparação com os registros visuais anteriores existentes no repositório, apenas como evidência complementar.

### Isolamento

Todos os registros produzidos para a auditoria foram criados em uma **base PostgreSQL de teste isolada**. Nenhum dado de produção foi alterado. O código do produto não foi modificado.

### Limites

- Não houve teste com leitores de tela reais, dispositivos físicos, rede degradada ou alto volume concorrente.
- O desempenho medido é de servidor em ambiente local e com pouca massa; não representa capacidade de produção.
- Segurança de infraestrutura, cabeçalhos de proxy, TLS, backup, observabilidade e configuração do ambiente publicado não puderam ser comprovados apenas pelo repositório.
- Integrações externas, entrega de e-mail e antivírus de arquivos não foram exercitados em serviços reais.
- A auditoria avaliou o comportamento disponível; decisões de negócio não documentadas são marcadas como pontos de confirmação.

---

## 3. Inventário e mapa do sistema

### Dimensão

- 8 aplicações Django: `core`, `accounts`, `cadastros`, `solicitacoes`, `dashboard`, `auditoria`, `coffee_break` e `demandas_eventos`.
- 52 rotas nomeadas do produto fora do Django Admin.
- 30 templates de páginas/layouts e 18 componentes reutilizáveis.
- Uma folha de estilos principal com aproximadamente 3.304 linhas.
- Um arquivo JavaScript principal com aproximadamente 1.726 linhas.
- 38 modelos/objetos carregados pelo projeto; os domínios principais estão descritos abaixo.

### Áreas e jornadas

#### Autenticação e conta

- Entrar e sair.
- Recuperar e redefinir senha.
- Alterar a própria senha.
- Ver, criar, editar e ativar/desativar usuários, quando administrador.
- Acessar notificações, abrir uma notificação e marcar todas como lidas.

#### Portal e painel

- Portal inicial com cartões dos módulos habilitados.
- Indicadores executivos.
- Gráfico por período.
- Lista de solicitações recentes.

#### Solicitações de Eventos

- Listar por filas, buscar, filtrar, ordenar e escolher colunas.
- Exportar CSV.
- Criar e editar rascunho.
- Informar evento, solicitante, serviços, equipes, unidade móvel, motorista e anexos.
- Enviar para despacho da DG.
- Ajustar quantidades e decidir: atender, devolver, não atender ou cancelar.
- Concluir atendimento e registrar cancelamento.
- Consultar resumo, checklist, linha do tempo e histórico.

#### Coffee Break

- Consultar painel, lotes e saldo.
- Listar, criar, editar, cancelar e reativar solicitações.
- Registrar quantidade, município, evento, lotação e marcos financeiros.
- Consultar fornecedor, contrato e lote relacionado.

#### Demandas ASCOM

- Consultar painel e lista.
- Criar, editar e detalhar demandas.
- Informar tipo, evento, solicitante, local, período, responsável, status, contato, pauta, setores e palestrantes.
- Manter temas, palestrantes e respostas padrão.

#### Cadastros centrais

- Tipos de evento.
- Serviços.
- Equipes.
- Órgãos responsáveis.
- Municípios e regiões.
- Motoristas.
- Unidades móveis.

### Modelo de dados essencial

- **Contas:** usuário, setor e módulo. Usuários pertencem a setores; módulos são relacionados a setores.
- **Eventos:** solicitação, serviços solicitados, equipes solicitadas, anexos e histórico.
- **Cadastros:** tipos, serviços, equipes, órgãos, regiões, estados, municípios, motoristas e unidades móveis.
- **Coffee Break:** fornecedor, contrato, lote e solicitação.
- **Demandas ASCOM:** tema, palestrante, resposta padrão e demanda.
- **Núcleo:** notificações.
- **Auditoria:** log de auditoria.

### Perfis e fronteiras observadas

- **Solicitante:** cria eventos, consulta os módulos liberados pelo setor e acompanha os registros visíveis.
- **Gestor DG:** além da consulta, despacha solicitações de eventos.
- **Administrador/superusuário:** gerencia cadastros e usuários e possui amplos privilégios de correção.
- **Acesso por módulo:** decorre do vínculo do usuário a setores relacionados ao módulo.
- **Demandas ASCOM:** a consulta é filtrada por setores; os cadastros compartilhados são editáveis por qualquer usuário com acesso ao módulo.
- **Coffee Break:** a operação é centralizada; qualquer usuário habilitado no módulo enxerga e opera o conjunto disponível.

---

## 4. Cobertura executada

### Testes automatizados

- `manage.py check`: **sem problemas identificados**.
- Suíte completa: **214 testes aprovados**, 0 falhas, em aproximadamente 90 segundos.
- Foram cobertos no código os principais serviços, permissões, transições, views, filtros, formulários e componentes.

### Navegação funcional

- Login válido, login inválido e persistência da sessão.
- Portal por perfil, dashboard e troca do período do gráfico.
- Todas as listas de cadastros e formulários representativos.
- Lista de eventos, filas, busca, filtros avançados, ordenação, seleção de colunas e CSV.
- Criação de rascunho, autopreenchimento, campos condicionais, anexos, envio incompleto, detalhe, despacho, ajuste de quantidade, conclusão e cancelamento.
- Painel, lotes, saldo, lista, criação, validação de quantidade e detalhe de Coffee Break.
- Painel, lista, criação inválida, criação válida, detalhe, edição e cadastros de Demandas ASCOM.
- Lista, criação e validação de usuários; alteração de senha e notificações.
- Acesso direto negado a páginas administrativas com perfil comum.

### Campos e regras exercitados

#### Solicitação de evento

- Intervalo de datas, tipo de evento, estado, município, órgão solicitante e cargo.
- Serviços e equipes, incluindo quantidade condicional.
- Unidade móvel, unidade e motorista condicionais.
- Anexos.
- Motivo de devolução, não atendimento ou cancelamento.
- Decisão da DG e ajuste de quantitativos.
- Autopreenchimento de “Paraná em Ação” funcionou como esperado.
- Alternar unidade móvel limpou os valores ocultos.
- Desmarcar equipe desabilitou a quantidade; o valor permanece visualmente e volta ao remarcar.

#### Coffee Break

- Lote, município, número, evento, lotação, quantidade e observações.
- Datas original e estruturada.
- Empenho, envio de ordem bancária, atesto, entrega de nota fiscal, pagamento e cancelamento.
- O saldo exibido reagiu à seleção do lote.
- Quantidade acima do saldo foi bloqueada com mensagem inline.

#### Demanda ASCOM

- Data, tipo, evento, solicitante, local, responsável, status, contato, assunto, resumo e observações.
- Período textual e período estruturado.
- Setores, palestrantes e cadastros auxiliares.
- Os campos obrigatórios testados mostraram erros inline, exceto nas exceções descritas nos achados.

#### Usuário

- Nome, e-mail, perfil, senha, confirmação, ativo e acesso administrativo.
- A obrigatoriedade de e-mail foi validada no servidor, embora a apresentação não indique corretamente essa exigência.

### Responsividade

- Em desktop, os painéis, formulários, tabelas e barras laterais mantiveram hierarquia e alinhamento.
- Em 390 × 844, as páginas avaliadas não produziram estouro horizontal global; tabelas ficaram em regiões roláveis.
- Portal, lista/detalhe/formulário de Eventos, Coffee Break e Demandas foram verificados em celular.
- As páginas continuam utilizáveis, mas formulários e filtros geram rolagem longa e a navegação de módulos perde descobribilidade.

---

## 5. Pontos fortes

- Linguagem visual institucional consistente, com boa hierarquia de títulos, cartões, badges e ações.
- Fluxo de Eventos mais maduro: resumo lateral, checklist, histórico e linha do tempo tornam o estado compreensível.
- Destruições e transições relevantes usam POST e proteção CSRF.
- Permissões administrativas e de despacho são verificadas no servidor, não apenas escondidas na interface.
- Bloqueio correto de páginas administrativas para solicitante comum.
- Filtros, ordenação, colunas configuráveis e CSV melhoram o trabalho operacional com Eventos.
- Componentes de data e seleção têm comportamento de teclado elaborado.
- Badges usam texto, não dependem apenas de cor.
- Regiões roláveis de tabela possuem, em geral, rótulo e papel semântico.
- Validação de saldo de Coffee Break oferece feedback direto e impede excesso.
- Estado e histórico de Eventos são registrados de forma clara.
- Suíte automatizada ampla para o tamanho do produto.

---

## 6. Achados detalhados

### EVT-ACL-01 — Qualquer usuário visível pode cancelar evento de terceiro

- **Página/fluxo:** detalhe de Solicitação de Evento → “Registrar cancelamento do evento”.
- **Componente:** política `pode_cancelar`, view de cancelamento e ação lateral.
- **Severidade:** **P0 — crítica**.
- **Como reproduzir:** criar e enviar uma solicitação com o usuário A; entrar com o usuário B, sem perfil DG; abrir o detalhe da solicitação de A; informar um motivo e confirmar o cancelamento.
- **Resultado atual:** a solicitação passa para cancelada. O teste automatizado `test_qualquer_usuario_cancela_evento_via_view` exige explicitamente esse comportamento.
- **Resultado esperado:** somente o criador, um responsável formal, gestor autorizado ou administrador deveria cancelar, salvo regra institucional documentada em contrário.
- **Impacto:** interrupção indevida de atendimento, perda operacional e risco de responsabilização sem segregação de função.
- **Causa provável:** `pode_cancelar` delega para `pode_ver`; como todo registro enviado é amplamente visível, visibilidade se converte em poder de transição.
- **Solução recomendada:** validar a regra com a área dona do processo; separar “ver” de “cancelar”; definir perfis autorizados; registrar autor, motivo e confirmação; adicionar teste negativo para terceiro comum.
- **Impacto UX:** o botão comunica uma autoridade que o usuário provavelmente não espera possuir.

### EVT-VIS-01 — Dossiês enviados são visíveis a todos os usuários autenticados

- **Página/fluxo:** lista e detalhe de Solicitações de Eventos.
- **Severidade:** **P1 — alta; requer decisão de negócio**.
- **Como reproduzir:** entrar como solicitante B e abrir uma solicitação enviada por A.
- **Resultado atual:** B consulta dados completos do evento, solicitante, recursos, histórico e anexos permitidos; apenas rascunhos ficam privados.
- **Resultado esperado:** escopo por criador, setor, região ou papel, se os dossiês não forem deliberadamente públicos internamente.
- **Impacto:** exposição interna excessiva de dados operacionais e amplificação do risco EVT-ACL-01.
- **Causa provável:** o queryset visível restringe rascunhos, mas não segmenta registros enviados.
- **Solução recomendada:** documentar a matriz de visibilidade; restringir queryset e downloads de anexos com a mesma política; manter visão transversal apenas para papéis definidos.

### EVT-VAL-01 — Erros de serviços e equipes não aparecem no envio incompleto

- **Página/fluxo:** nova/editar solicitação → “Enviar para DG”.
- **Severidade:** **P1 — alta**.
- **Como reproduzir:** preencher datas, município e órgão, mas não selecionar serviço/equipe; enviar.
- **Resultado atual:** o servidor rejeita corretamente, mas a página não renderiza os erros de “ao menos um serviço” e “ao menos uma equipe”. Só os erros de campos simples aparecem.
- **Resultado esperado:** todos os bloqueios devem ser exibidos junto ao grupo correspondente e em um resumo no topo.
- **Impacto:** usuário fica preso sem saber o que falta e tende a repetir o envio.
- **Causa provável:** erros não associados a campos ou grupos não são renderizados pelo template.
- **Solução recomendada:** renderizar erros não-campo e erros dos grupos; mover foco para um resumo; criar links para os controles inválidos.

### USR-ACL-01 — Administração de usuários não permite vincular setores

- **Página/fluxo:** portal administrativo → novo/editar usuário.
- **Severidade:** **P1 — alta**.
- **Resultado atual:** o portal anuncia cadastro, perfil e vínculo a setores, mas o formulário não possui o campo de setores. Como o acesso aos módulos depende desse vínculo, a concessão completa exige Django Admin ou intervenção técnica.
- **Resultado esperado:** administrador funcional deve escolher setores/módulos autorizados, com explicação da consequência.
- **Impacto:** onboarding incompleto, dependência de equipe técnica e risco de acesso incorreto.
- **Causa provável:** `UsuarioForm` não expõe a relação `setores`.
- **Solução recomendada:** adicionar seleção de setores com resumo dos módulos derivados, validação de ao menos um setor quando aplicável e histórico da alteração.

### DEM-ACL-01 — Responsável de Demanda pode ser escolhido fora do setor

- **Página/fluxo:** nova/editar Demanda ASCOM → responsável pelo atendimento.
- **Severidade:** **P1 — alta**.
- **Resultado atual:** o campo lista todos os usuários ativos, inclusive pessoas sem vínculo com o setor/módulo da demanda.
- **Resultado esperado:** somente usuários elegíveis pelos setores selecionados e com acesso ao módulo.
- **Impacto:** atribuição impossível de executar, vazamento de nomes e relatórios inconsistentes.
- **Causa provável:** queryset global de usuários ativos no formulário.
- **Solução recomendada:** filtrar dinamicamente por setor/módulo e validar novamente no servidor.

### DEM-WF-01 — Status de Demanda não possui transições ou papéis controlados

- **Página/fluxo:** criação e edição de Demanda ASCOM.
- **Severidade:** **P1 — alta**.
- **Resultado atual:** usuário com acesso ao módulo pode escolher diretamente qualquer status, inclusive estados finais, sem transição, motivo ou trilha específica.
- **Resultado esperado:** máquina de estados explícita, ações nomeadas, papéis autorizados e justificativa nos estados sensíveis.
- **Impacto:** fechamento/cancelamento acidental, indicadores pouco confiáveis e ausência de responsabilização.
- **Solução recomendada:** separar edição de dados das transições; definir estados e permissões; registrar cada mudança.

### CFB-WF-01 — Marcos financeiros não têm cronologia nem imutabilidade suficiente

- **Página/fluxo:** editar solicitação de Coffee Break.
- **Severidade:** **P1 — alta**.
- **Resultado atual:** o status financeiro é derivado principalmente da presença de datas. Não há evidência de validação completa da ordem cronológica; lote e quantidade continuam editáveis mesmo após marcos avançados.
- **Resultado esperado:** sequência coerente entre empenho, ordem bancária, atesto, nota fiscal e pagamento; campos-base congelados após compromisso financeiro ou corrigidos em fluxo auditado.
- **Impacto:** status incorreto, saldo retroativo e divergência entre operação e financeiro.
- **Solução recomendada:** implementar invariantes cronológicas e bloqueios por fase; exigir justificativa para correção e guardar valores anteriores.

### AUD-TRAIL-01 — Coffee Break e Demandas não têm histórico equivalente ao de Eventos

- **Página/fluxo:** detalhes de Coffee Break e Demandas ASCOM.
- **Severidade:** **P1 — alta**.
- **Resultado atual:** a tela mostra o estado atual e alguns campos de autoria, mas não uma sequência completa de alterações, atribuições e transições.
- **Resultado esperado:** linha do tempo com data, autor, ação, estado anterior/novo e justificativa.
- **Impacto:** apuração difícil, baixa rastreabilidade e maior risco em correções concorrentes.
- **Solução recomendada:** adotar histórico de domínio semelhante ao módulo de Eventos e definir retenção.

### A11Y-ROW-01 — Linhas clicáveis funcionam apenas com mouse

- **Página/fluxo:** tabelas de Eventos, Coffee Break e outras listas com `data-linha-url`.
- **Severidade:** **P1 — alta**.
- **Como reproduzir:** navegar com Tab e tentar abrir uma linha com Enter/Espaço.
- **Resultado atual:** a linha não recebe foco e o JavaScript escuta apenas clique. Em Coffee Break não há sequer um link equivalente dentro da linha.
- **Resultado esperado:** destino principal exposto como link real; se a linha inteira continuar acionável, suporte a foco e teclado sem duplicar semântica.
- **Impacto:** fluxo principal indisponível para teclado e tecnologias assistivas.
- **Solução recomendada:** inserir link descritivo na primeira coluna; tornar toda a área clicável como aprimoramento progressivo.

### DEM-UI-01 — Detalhe de Demanda apresenta título principal vazio

- **Página/fluxo:** `/ascom/demandas/demandas/<id>/`.
- **Severidade:** **P1 — alta**.
- **Resultado atual:** existe um `<h1>` vazio; visualmente aparece apenas o subtítulo/tipo da demanda.
- **Resultado esperado:** “Demanda #<número>” como título principal.
- **Impacto:** orientação ruim, quebra de hierarquia e prejuízo para leitores de tela.
- **Causa provável:** concatenação de string com identificador inteiro usando o filtro `add` no argumento do componente.
- **Solução recomendada:** compor o título antes da inclusão ou permitir prefixo/valor no componente; adicionar teste de conteúdo e heading.

### DATA-INTEGRITY-01 — Invariantes críticas dependem da camada de serviço

- **Página/fluxo:** envio/despacho de Eventos e criação de Demandas.
- **Severidade:** **P1 — alta**.
- **Resultado atual:** regras como possuir serviço/equipe antes do envio ou setor em Demanda são garantidas pelo formulário/serviço, mas não por invariantes abrangentes no modelo/banco. Django Admin, importação ou código futuro podem produzir estados impossíveis.
- **Resultado esperado:** regras críticas protegidas no menor nível viável e caminhos alternativos obrigados a usar o serviço de domínio.
- **Impacto:** registros inconsistentes que as telas não conseguem explicar.
- **Solução recomendada:** concentrar transições; aplicar `clean`, constraints quando expressáveis e validações no Admin/importadores.

### UPLOAD-01 — Validação de anexos é baseada em extensão e tamanho

- **Página/fluxo:** anexos de Solicitação de Evento.
- **Severidade:** **P1 — alta em ambiente exposto; requer avaliação de infraestrutura**.
- **Resultado atual:** há limite de tamanho e extensões, mas não foi identificada validação robusta de assinatura/MIME ou varredura de conteúdo.
- **Resultado esperado:** tipo real conferido, armazenamento não executável, download seguro e, conforme risco, antivírus.
- **Impacto:** upload de conteúdo disfarçado e distribuição interna de arquivo malicioso.
- **Solução recomendada:** validar magic bytes/MIME; usar nomes opacos; definir `Content-Disposition`; integrar varredura e política de retenção.

### SEARCH-01 — Enter na busca de Eventos não executa a pesquisa

- **Página/fluxo:** lista de Solicitações de Eventos → campo de busca.
- **Severidade:** **P2 — média**.
- **Resultado atual:** digitar e pressionar Enter mantém a mesma URL. O formulário depende do evento `change` e não possui botão explícito de busca.
- **Resultado esperado:** Enter e botão “Buscar” devem submeter; filtros automáticos podem continuar como conveniência.
- **Impacto:** comando básico parece quebrado e afeta teclado.
- **Solução recomendada:** usar submissão nativa e botão visível; JavaScript apenas aprimora.

### USR-FORM-01 — E-mail obrigatório não é indicado antes do envio

- **Página/fluxo:** novo usuário.
- **Severidade:** **P2 — média**.
- **Resultado atual:** o rótulo não possui marcador de obrigatório e o controle não expõe `required`, mas o servidor rejeita o vazio.
- **Resultado esperado:** rótulo, atributo e instruções consistentes com a validação real.
- **Impacto:** retrabalho e inconsistência de confiança.

### A11Y-LIVE-01 — Mensagens globais não são anunciadas

- **Página/fluxo:** alertas de sucesso e erro no layout principal.
- **Severidade:** **P2 — média**.
- **Resultado atual:** alertas visuais não possuem `role="alert"`, `role="status"` ou região `aria-live` adequada.
- **Resultado esperado:** mensagens urgentes e informativas anunciadas sem reposicionar indevidamente o foco.

### A11Y-ERROR-01 — Erros não estão programaticamente associados aos campos

- **Página/fluxo:** formulários em geral.
- **Severidade:** **P2 — média**.
- **Resultado atual:** mensagens usam classe visual, mas nem sempre possuem identificador ligado por `aria-describedby`; controles customizados podem ganhar `aria-invalid` sem referência à explicação.
- **Resultado esperado:** cada erro ligado ao controle e resumo de erros focável.

### ERR-403-01 — Página 403 é uma resposta crua fora do produto

- **Página/fluxo:** acesso direto a cadastros/usuários sem autorização.
- **Severidade:** **P2 — média**.
- **Resultado atual:** backend bloqueia corretamente, porém mostra apenas “403 Forbidden”.
- **Resultado esperado:** página institucional com explicação, retorno seguro, início e forma de solicitar acesso.

### MOBILE-NAV-01 — Navegação móvel oculta módulos sem affordance

- **Página/fluxo:** cabeçalho em 390 px.
- **Severidade:** **P2 — média**.
- **Resultado atual:** apenas os primeiros destinos ficam evidentes; demais itens exigem rolagem horizontal pouco sinalizada.
- **Resultado esperado:** menu compacto, botão “Mais” ou indicação clara de continuidade.

### MOBILE-DENSITY-01 — Formulários e listas têm carga excessiva no celular

- **Página/fluxo:** novo Evento, nova Demanda, filtros e detalhes.
- **Severidade:** **P2 — média**.
- **Resultado atual:** páginas podem ultrapassar aproximadamente 2.600–3.900 px de altura; filtros ocupam a primeira dobra e ações principais ficam distantes.
- **Resultado esperado:** seções recolhíveis, resumo persistente, ações próximas e filtros compactos por padrão.

### CFB-MASTER-01 — Cadastros de Coffee Break dependem do Django Admin

- **Página/fluxo:** fornecedores, contratos e lotes.
- **Severidade:** **P2 — média**.
- **Resultado atual:** a interface do módulo consulta lotes, mas a manutenção dos dados mestres ocorre fora da experiência institucional.
- **Resultado esperado:** backoffice funcional com regras, permissões e histórico, ou decisão explícita de manter o Admin como ferramenta operacional.
- **Impacto:** treinamento duplicado e maior risco de contornar regras de domínio.

### DEM-FILTER-01 — Filtros e exportação de Demandas são insuficientes para operação

- **Página/fluxo:** lista de Demandas ASCOM.
- **Severidade:** **P2 — média**.
- **Resultado atual:** busca, status, tipo e município estão disponíveis; faltam período, responsável, setor e exportação.
- **Resultado esperado:** filtros alinhados às perguntas operacionais e preservados na paginação/exportação.

### PERF-USERS-01 — Lista de usuários apresenta padrão N+1

- **Página/fluxo:** administração de usuários.
- **Severidade:** **P2 — média**.
- **Evidência:** 10 consultas com apenas 3 usuários. O perfil/grupo é obtido repetidamente por usuário.
- **Resultado esperado:** grupos e setores pré-carregados, com quantidade de consultas aproximadamente constante por página.
- **Solução recomendada:** `prefetch_related` e cálculo único do perfil.

### PERF-QUEUE-01 — Contadores de filas usam consultas separadas

- **Página/fluxo:** lista de Solicitações de Eventos.
- **Severidade:** **P2 — média**.
- **Resultado atual:** cada contador de fila executa contagem própria.
- **Resultado esperado:** agregação condicional em uma ou poucas consultas.

### DATA-DATE-01 — Períodos textual e estruturado podem divergir

- **Página/fluxo:** Coffee Break e Demandas ASCOM.
- **Severidade:** **P2 — média**.
- **Resultado atual:** campos de texto original e datas estruturadas podem coexistir sem regra clara de precedência e consistência.
- **Resultado esperado:** uma fonte oficial ou estado explícito de “data ainda não estruturada”, com validação de exclusividade.

### CONCURRENCY-01 — Edições concorrentes podem sobrescrever alterações

- **Página/fluxo:** formulários compartilhados de Coffee Break, Demandas e correções administrativas.
- **Severidade:** **P2 — média**.
- **Resultado atual:** não foi identificado controle otimista por versão/`updated_at` no envio do formulário.
- **Resultado esperado:** detectar que o registro mudou desde a abertura e oferecer recarregar/comparar.

### ARCH-DUP-01 — Padrões de lista e helpers são duplicados

- **Área:** views/templates dos módulos.
- **Severidade:** **P2 — média**.
- **Resultado atual:** paginação, ordenação, breadcrumbs, opções e ações de tabela são reconstruídos em diversos pontos. O componente de tabela é pouco usado e várias listas são manuais.
- **Impacto:** pequenas divergências de teclado, responsividade e manutenção.
- **Solução recomendada:** consolidar primitivas estáveis de filtro, tabela, paginação e ações, mantendo variações de domínio explícitas.

### ARCH-ASSET-01 — CSS e JavaScript centrais cresceram como monólitos

- **Área:** `design-system.css` e `app.js`.
- **Severidade:** **P2 — média**.
- **Resultado atual:** arquivos concentram muitos componentes e comportamentos; o escopo de regressão fica amplo.
- **Solução recomendada:** modularizar por fundação, componentes e módulos; preservar um único bundle se desejado, mas com fontes separadas e testes dos comportamentos críticos.

### TABLE-CONSISTENCY-01 — Tabelas têm padrões de ação diferentes

- **Área:** listas de Eventos, Coffee Break, Demandas e cadastros.
- **Severidade:** **P2 — média**.
- **Resultado atual:** algumas linhas contêm links, outras dependem totalmente do clique na linha; menus, ações e coluna principal variam.
- **Resultado esperado:** destino principal e menu de ações previsíveis em todas as listas.

### UI-STYLE-01 — Cores e estilos pontuais escapam aos tokens

- **Área:** CSS e templates.
- **Severidade:** **P3 — baixa**.
- **Resultado atual:** existem valores hexadecimais e estilos inline fora das variáveis do design system.
- **Impacto:** tema e manutenção ficam menos previsíveis.

### REPORT-01 — Coffee Break não oferece exportação operacional

- **Página/fluxo:** solicitações/lotes de Coffee Break.
- **Severidade:** **P3 — baixa**.
- **Resultado atual:** não há exportação equivalente à lista de Eventos.
- **Solução recomendada:** confirmar necessidade de conciliação e disponibilizar CSV com filtros aplicados.

### HELP-01 — Regras complexas têm pouca ajuda contextual

- **Página/fluxo:** decisões DG, marcos financeiros, períodos e vinculação por setor.
- **Severidade:** **P3 — baixa**.
- **Resultado atual:** a interface é rotulada, mas não explica sempre consequências, ordem e quem pode agir.
- **Solução recomendada:** microcopy curta, exemplos e confirmação nas transições irreversíveis.

### MOBILE-TABLE-01 — Rolagem de tabela é funcional, mas pouco descoberta

- **Página/fluxo:** listas em celular.
- **Severidade:** **P3 — baixa**.
- **Resultado atual:** a região rola horizontalmente, porém não há pista persistente de colunas adicionais.
- **Solução recomendada:** coluna principal fixa, máscara/indicador de continuidade ou cartões móveis para tabelas essenciais.

### PROD-SEC-01 — Hardening de produção não é comprovável pelo repositório

- **Área:** implantação.
- **Severidade:** **P3 — verificação necessária**.
- **Resultado atual:** não foi possível confirmar no escopo local HSTS, cookies seguros, redirecionamento HTTPS, cabeçalhos do proxy, rotação de segredos e backup testado.
- **Solução recomendada:** checklist de implantação e teste no ambiente real; não tratar a ausência no repositório como prova de ausência em produção.

---

## 7. Desempenho observado

As medições abaixo são locais, com base pequena e sem latência de rede. Servem para detectar padrões, não para definir SLA.

- Portal: 12 consultas; cerca de 178 ms na primeira medição.
- Dashboard: 18 consultas; cerca de 39 ms.
- Lista de Eventos: 15 consultas; cerca de 36 ms.
- Detalhe de Evento: 21 consultas; cerca de 76 ms.
- Índice de cadastros: 11 consultas; cerca de 11 ms.
- Lista de municípios: 6 consultas; cerca de 20 ms.
- Lista de usuários: 10 consultas com 3 usuários; cerca de 27 ms.
- Painel Coffee Break: 7 consultas; cerca de 24 ms.
- Lotes Coffee Break: 7 consultas; cerca de 18 ms.
- Solicitações Coffee Break: 8 consultas; cerca de 20 ms.
- Painel Demandas ASCOM: 9 consultas; cerca de 15 ms.
- Lista Demandas ASCOM: 8 consultas; cerca de 22 ms.
- Notificações: 8 consultas; cerca de 13 ms.

Conclusão: o tempo local é confortável. As prioridades de desempenho são eliminar o N+1 de usuários, consolidar contadores de filas e repetir as medições com massa representativa antes de qualquer otimização ampla.

---

## 8. Quick wins

### Até dois dias

- Corrigir o título vazio de Demanda ASCOM.
- Fazer Enter e botão explícito executarem a busca de Eventos.
- Indicar e marcar o e-mail obrigatório no cadastro de usuário.
- Renderizar erros de serviços/equipes e um resumo de erros no envio.
- Adicionar `role`/`aria-live` às mensagens globais.
- Ligar mensagens de erro aos controles por `aria-describedby`.
- Criar página 403 institucional.

### Até uma semana

- Inserir links reais e operáveis por teclado nas tabelas.
- Filtrar responsáveis de Demandas por setor/módulo.
- Pré-carregar grupos/setores na lista de usuários.
- Agregar contadores de filas.
- Expor setores no formulário administrativo de usuário.
- Documentar e obter aceite formal para visibilidade e cancelamento por terceiros.

---

## 9. Backlog priorizado

### P0 — antes de ampliar uso

1. **EVT-ACL-01:** decidir e corrigir a autoridade de cancelamento de solicitações de terceiros; revisar logs e testes.

### P1 — próximo ciclo

1. **EVT-VIS-01:** formalizar matriz de visibilidade e aplicar a dossiês/anexos.
2. **EVT-VAL-01:** exibir todos os bloqueios do envio.
3. **USR-ACL-01:** administrar setores e módulos pela interface.
4. **DEM-ACL-01:** restringir responsáveis elegíveis.
5. **DEM-WF-01:** criar transições e papéis de Demanda.
6. **CFB-WF-01:** validar cronologia e congelamento financeiro.
7. **AUD-TRAIL-01:** histórico de Coffee Break e Demandas.
8. **A11Y-ROW-01:** operação de tabelas por teclado.
9. **DEM-UI-01:** corrigir heading da Demanda.
10. **DATA-INTEGRITY-01:** proteger invariantes fora dos formulários.
11. **UPLOAD-01:** endurecer o pipeline de anexos.

### P2 — dois a três ciclos

1. **SEARCH-01**, **USR-FORM-01**, **A11Y-LIVE-01** e **A11Y-ERROR-01**.
2. **ERR-403-01**, **MOBILE-NAV-01** e **MOBILE-DENSITY-01**.
3. **CFB-MASTER-01** e **DEM-FILTER-01**.
4. **PERF-USERS-01** e **PERF-QUEUE-01**.
5. **DATA-DATE-01** e **CONCURRENCY-01**.
6. **ARCH-DUP-01**, **ARCH-ASSET-01** e **TABLE-CONSISTENCY-01**.

### P3 — melhoria contínua

1. **UI-STYLE-01:** concentrar cores e estilos nos tokens.
2. **REPORT-01:** avaliar exportação Coffee Break.
3. **HELP-01:** microcopy para regras sensíveis.
4. **MOBILE-TABLE-01:** melhorar descoberta de colunas.
5. **PROD-SEC-01:** comprovar hardening no ambiente publicado.

---

## 10. Roadmap sugerido

### Fase 0 — contenção e decisão, 1 semana

- Reunião curta com dono do processo para fechar matriz de permissões.
- Decisão registrada sobre cancelamento e visibilidade ampla.
- Mitigação do cancelamento por terceiros, se não intencional.
- Correção do título de Demanda e das validações invisíveis.

### Fase 1 — integridade e acesso, 2 a 3 semanas

- Administração de setores/módulos.
- Elegibilidade de responsáveis.
- Transições formais de Demanda e Coffee Break.
- Invariantes de domínio e endurecimento de anexos.
- Testes automatizados positivos e negativos por papel.

### Fase 2 — acessibilidade e produtividade, 2 semanas

- Tabelas, busca, mensagens e erros acessíveis.
- Página 403 e navegação móvel.
- Filtros/exportação Demandas; avaliação de Coffee Break.
- Teste manual com teclado e leitor de tela.

### Fase 3 — rastreabilidade e escala, 2 a 4 semanas

- Histórico de Demandas e Coffee Break.
- Controle de concorrência.
- Otimização de consultas com massa real.
- Modularização gradual de CSS/JS e consolidação de componentes.

### Critérios de saída

- Nenhum usuário sem papel explícito altera o estado de registro de terceiro.
- Matriz de acesso coberta por testes negativos.
- Todos os erros obrigatórios aparecem e recebem foco/anúncio.
- Jornadas principais podem ser concluídas só com teclado.
- Histórico mostra autor, momento, antes/depois e justificativa.
- Consultas por página permanecem estáveis ao crescer a paginação.

---

## 11. Conclusão

O produto não precisa de uma reconstrução. A arquitetura e o design atual sustentam evolução incremental, e o fluxo de Eventos demonstra um bom padrão de maturidade que pode ser reaproveitado pelos outros módulos. A ordem correta é primeiro resolver governança e integridade; depois acessibilidade e produtividade; por fim modularização e escala.

O risco mais urgente é conhecido e reproduzível: **ver uma solicitação hoje concede, em determinados estados, o poder de cancelá-la**. Uma decisão explícita sobre essa regra deve preceder as demais melhorias.

---

## 12. Implementação das correções — 01/09/2026

As correções página a página dos módulos Eventos Sociais, Coffee Break e Demandas ASCOM foram implementadas após esta auditoria.

### Eventos Sociais

- Visibilidade limitada ao criador, com visão transversal somente para gestor DG, administrador e superusuário; anexos seguem a mesma regra.
- Cancelamento separado da permissão de leitura e validado novamente no serviço de domínio.
- Resumo de erros e mensagens específicas para serviços/equipes obrigatórios.
- Busca com botão explícito e suporte a Enter; identificador principal das tabelas virou link real.
- Validação de assinatura de PDF, PNG, JPEG e documentos de escritório, além de extensão e tamanho.
- Contadores de filas consolidados em uma agregação e estados de workflow protegidos no Admin.

### Coffee Break

- Sequência financeira validada no modelo/formulário; datas cronológicas protegidas também no banco quando compatíveis com o legado.
- Dados-base congelados após o início financeiro; registros concluídos ou cancelados ficam somente para consulta.
- Cancelamento exige motivo e não é permitido após conclusão; reativação revalida o saldo sob bloqueio transacional.
- Histórico de criação, edição, cancelamento e reativação; controle otimista de concorrência.
- Exportação CSV preservando filtros, links reais nas tabelas e ajuda contextual do fluxo.
- Backoffice institucional para fornecedores, contratos e lotes, restrito a administradores e com validação de capacidade consumida.

### Demandas ASCOM

- Responsáveis limitados aos setores elegíveis, filtrados em tempo real no formulário e validados no servidor.
- Status removido da edição livre e substituído por transições explícitas, com justificativa em cancelamento/não atendimento.
- Estados finais bloqueados para edição; histórico registra criação, alterações e transições.
- Título de detalhe corrigido, período unificado, controle de concorrência e importação com trilha de criação.
- Filtros por período, responsável e setor; exportação CSV respeitando o recorte de visibilidade.
- Datas inválidas em filtros são ignoradas com segurança em vez de causar erro 500.

### Plataforma compartilhada

- Administração de usuários agora vincula setores; alterações M2M também entram na auditoria.
- Mensagens globais possuem regiões vivas; erros estão associados por `aria-describedby` e resumos recebem foco.
- Página 403 institucional, hardening configurável de produção e proteção contra segredo inseguro fora de debug.
- Navegação móvel sinalizada, indicação de tabelas roláveis e ações de formulário persistentes em telas estreitas.

### Verificação da implementação

- 224 testes dos módulos afetados passaram.
- Migrações aplicadas com sucesso em base PostgreSQL isolada e `makemigrations --check` sem diferenças.
- Jornadas reais verificadas no navegador em desktop e 390 × 844 px, sem overflow global.
- A suíte completa executou 405 testes; 404 passaram. A única falha está em um teste preexistente e fora do escopo, no módulo Viagens, que ainda procura a marcação antiga do formulário depois do redesign desse módulo.
