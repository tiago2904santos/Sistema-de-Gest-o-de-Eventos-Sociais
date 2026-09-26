/* Coffee Break — etapa 1: a 2ª linha mostra o lote que o município recebe.

   Cada opção do município traz os dados do lote (`data-lote-rotulo`,
   `data-fornecedor`, `data-contrato`, `data-vigencia`, `data-saldo`,
   `data-empenho`, `data-perto`, vindos de `_opcoes_municipios`). Ao escolher
   o município, a linha se preenche; sem lote, some. */
(function () {
  "use strict";
  var linha = document.querySelector("[data-cb-lote]");
  var select = document.querySelector("select[name=municipio]");
  if (!linha || !select) return;
  var lista = linha.querySelector("ul");
  var icones = linha.querySelector("template[data-cb-lote-icones]");

  function icone(nome) {
    var molde = icones && icones.content.querySelector('[data-icone="' + nome + '"]');
    return molde ? molde.innerHTML : "";
  }

  function fato(nome, texto, url) {
    var li = document.createElement("li");
    li.className = "tm-fato";
    li.innerHTML = icone(nome);
    var valor = document.createElement("span");
    valor.className = "vg-fato__valor";
    if (url) {
      var a = document.createElement("a");
      a.href = url;
      a.textContent = texto;
      valor.appendChild(a);
    } else {
      valor.textContent = texto;
    }
    li.appendChild(valor);
    return li;
  }

  function mostrar() {
    var opcao = select.options[select.selectedIndex];
    var d = opcao ? opcao.dataset : {};
    if (!d.loteRotulo) { linha.hidden = true; return; }
    lista.innerHTML = "";
    lista.appendChild(fato("clipboard", d.loteRotulo, d.loteUrl));
    if (d.fornecedor) lista.appendChild(fato("landmark", d.fornecedor));
    if (d.contrato) lista.appendChild(fato("document", d.contrato));
    if (d.vigencia) lista.appendChild(fato("clock", d.vigencia));
    if (d.saldo) lista.appendChild(fato("coffee", "Saldo " + d.saldo));
    if (d.empenho) lista.appendChild(fato("checklist", d.empenho));
    if (d.perto) lista.appendChild(fato("map-pin", "Fora da lista do lote: sede mais próxima em " + d.perto));
    linha.hidden = false;
  }

  select.addEventListener("change", mostrar);
  if (select.value) mostrar();
})();

/* Coffee Break — etapa 1: local de entrega e responsável já usados no
   município. Ao escolher o município, lista os pares mais recentes de lá
   (`coffee_break:locais_entrega`); um clique preenche os dois campos. Nada é
   preenchido sem o clique, e tudo continua editável — como a sugestão do
   solicitante nas outras telas (sugestao-solicitante.js). */
(function () {
  "use strict";
  var caixa = document.querySelector("[data-cb-locais]");
  var select = document.querySelector("select[name=municipio]");
  var formulario = caixa && caixa.closest("form");
  if (!caixa || !select || !formulario || select.disabled) return;
  var pedido = 0;

  function el(tag, classe, texto) {
    var elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto) elemento.textContent = texto;
    return elemento;
  }

  function esconder() {
    caixa.hidden = true;
    caixa.textContent = "";
  }

  function definir(nome, valor) {
    var campo = formulario.querySelector('[name="' + nome + '"]');
    if (!campo || campo.disabled || campo.readOnly) return;
    campo.value = valor;
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function mostrar(resultados) {
    caixa.textContent = "";
    if (!resultados.length) { esconder(); return; }
    caixa.appendChild(el("p", "sugestao-solicitante__titulo", "Já entregues neste município — clique para preencher o local e o responsável:"));
    var lista = el("ul", "sugestao-solicitante__lista");
    resultados.forEach(function (item) {
      var li = el("li");
      var botao = el("button", "sugestao-solicitante__item");
      botao.type = "button";
      botao.appendChild(el("b", "", item.nome));
      if (item.detalhe) botao.appendChild(el("small", "", item.detalhe));
      botao.addEventListener("click", function () {
        Object.keys(item.campos || {}).forEach(function (chave) { definir(chave, item.campos[chave]); });
        esconder();
      });
      li.appendChild(botao);
      lista.appendChild(li);
    });
    caixa.appendChild(lista);
    var fechar = el("button", "sugestao-solicitante__fechar", "Fechar");
    fechar.type = "button";
    fechar.addEventListener("click", esconder);
    caixa.appendChild(fechar);
    caixa.hidden = false;
  }

  function buscar() {
    var numero = ++pedido;
    if (!select.value) { esconder(); return; }
    fetch(caixa.getAttribute("data-url") + "?municipio=" + encodeURIComponent(select.value), {
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    })
      .then(function (resposta) { return resposta.ok ? resposta.json() : null; })
      .then(function (dados) {
        if (dados && numero === pedido) mostrar(dados.resultados || []);
      })
      .catch(function () { /* sugestão é ajuda: sem ela, a tela segue igual */ });
  }

  // Só quando o município muda na tela; ao abrir, o que já está preenchido fica como está.
  select.addEventListener("change", buscar);
})();
