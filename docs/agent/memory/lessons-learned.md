# Lições aprendidas

- **Suíte verde não é tela conferida** (lição da F2, reconfirmada): a varredura de 20 páginas com axe/responsivo achou em minutos
  problemas que 3.054 testes de backend não veem (overflow de navegação, contraste, tokens inexistentes).
- **Medir antes de propor**: a hipótese "GET cria rascunho" caiu ao ler a view; a hipótese "Django é o gargalo" caiu com LCP < 500 ms.
- **Determinismo é o que torna o visual útil**: sem âncora de data, a lista de ofícios muda todo dia ("faltam N dias").
- **Ferramenta do lab também precisa de teste**: o detector de tokens indefinidos começou com 34 falsos positivos (tokens definidos em `style=` e via JS); os testes do `agent_lab` pegam regressões assim.
- **Ambientes montados têm regras próprias** (sem delete, CRLF): verificar o efeito colateral de cada ferramenta antes de rodar na pasta do usuário.
