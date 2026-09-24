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
