# Auto-recuperação

```text
detect (doctor) → diagnose (check + detalhe) → repair (só se recuperável e seguro) → retest (doctor de novo)
```

`npm run agent:doctor:fix` (ou `agent_doctor {fix:true}`):

| Problema detectado | Reparo automático |
|---|---|
| node_modules incompleto | `npm ci` |
| Chromium não abre | `npx playwright install chromium` |
| Banco do lab ausente/não-LAB/volume errado | `lab.py reset --scenario normal` (**só** o banco em `.lab/`) |
| Migrações pendentes no LAB | `migrate` no banco do LAB |
| Inventário desatualizado | `lab.py inventory` |
| tokens.css fora de sincronia | `build_tokens.py` |
| Ferramentas de dev ausentes | `pip install -r requirements-dev.txt` |
| .venv quebrado | `lab.py bootstrap --quick` |

Não repara (exige humano): conexões externas, skills/agentes inválidos, drift de docs, testes quebrados. Nunca repara nada
fora do laboratório: não há reparo que toque banco DEV/STAGING/PRODUCTION.
