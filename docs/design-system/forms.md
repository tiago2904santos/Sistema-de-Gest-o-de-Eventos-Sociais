# Formulários

**Hoje**: componentes `input.html`, `select.html` (select aprimorado com busca, remoto, dependente), `textarea.html`,
`date_range.html`, `date_multi.html`, `endereco_campos.html`, `upload_anexos.html`; contrato documentado no topo de cada
template. Erros por campo (`erros`) com `aria-invalid` + `aria-describedby`. 62 formulários Django no inventário.

**Avaliação**: bom padrão de acessibilidade nos componentes; rótulo `.form-label` 11px `#777` reprova contraste;
algumas telas montam campos à mão (achado da F2: campos sem `form-controle`).

**Regra v4**: sempre o componente; rótulo visível; obrigatório marcado e anunciado; erro abaixo do campo + resumo no topo
em formulário longo; foco vai para o primeiro erro; seções numeradas (`section_card`).
