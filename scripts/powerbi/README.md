# Integração com o Power BI

O Power BI conecta direto ao PostgreSQL (conector nativo) usando um usuário
somente-leitura que enxerga apenas as views de relatório.

## Views disponíveis (criadas pela migration `solicitacoes.0007`)

| View | Conteúdo |
| --- | --- |
| `vw_solicitacoes` | Uma linha por solicitação, desnormalizada: status e decisão com rótulos em português, município/região/estado, tipo de evento, órgão, mês/ano do evento (derivados da data de início), quantidades, datas. |
| `vw_solicitacao_servicos` | Uma linha por serviço vinculado a cada solicitação. |
| `vw_solicitacao_equipes` | Uma linha por equipe vinculada, com a quantidade de servidores da equipe. |
| `vw_tempos_workflow` | Timestamps de cada etapa (criação, envio, início da análise, encaminhamento, decisão) — calcule os tempos de tramitação no Power BI com DAX (`DATEDIFF`). |

## Passo a passo

1. Rode as migrations (`python manage.py migrate`) no banco PostgreSQL.
2. Edite `criar_usuario_powerbi.sql`, troque `TROQUE_ESTA_SENHA` por uma senha
   forte e execute o script como administrador do banco:
   ```
   psql -U postgres -h localhost -d eventos_sociais -f scripts/powerbi/criar_usuario_powerbi.sql
   ```
3. No Power BI Desktop: **Obter dados → Banco de dados PostgreSQL**
   - Servidor: `localhost` (ou o host do servidor de produção)
   - Banco de dados: `eventos_sociais`
   - Credenciais: usuário `powerbi_reader` e a senha definida no passo 2.
4. Selecione as quatro views e modele os relacionamentos por `solicitacao_id`.
5. Para atualização agendada no Power BI Service, instale o
   **gateway de dados local (on-premises data gateway)** na máquina/rede que
   enxerga o PostgreSQL.

## Observações

- As views são recriadas/atualizadas por migration — qualquer evolução de
  esquema para o BI deve ser feita criando uma nova migration, nunca editando
  as views manualmente no banco.
- O usuário `powerbi_reader` não tem acesso às tabelas (dados de auditoria,
  usuários etc.), apenas às views listadas.
