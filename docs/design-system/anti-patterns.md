# Antipadrões (com ocorrência medida)

| Antipadrão | Onde aparece | Em vez disso |
|---|---|---|
| `:focus-visible{outline:none}` global | `ds-v32.css:33` e 37 outras regras | anel `focus-ring` |
| Cor literal fora de token | ~400 ocorrências nos 3 CSS | `var(--t-color-…)` |
| `var(--token)` inexistente | `pdf-place.css` (13 tokens do DS antigo) | token v4 ou remover |
| Mesmo seletor em vários CSS | 308 seletores (design-system × ds-v32 × bridge) | um dono por componente |
| Tamanho de fonte ad hoc | 115 valores | escala `font.size.*` |
| Navegação com itens demais | Viagens (12) → overflow | agrupar / "Mais" |
| Menu de ações completo repetido por linha | lista de prestações (656 KB) | menu único reutilizado |
| Botão só com ícone sem nome | ver `reports/audit/static-findings.md` | `aria-label` |
| Tabela que empurra a página | listas de Viagens no tablet | contêiner com rolagem própria |
| Componente montado à mão em vez do include | achados da F2 (campos sem `form-controle`, cards inventados) | componente do DS |
