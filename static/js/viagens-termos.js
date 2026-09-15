/**
 * Cadastro do termo: contagem e busca na lista de servidores.
 * O seletor de ofício é o `viagens-picker-oficios.js`.
 */
(function () {
  "use strict";

  var form = document.getElementById("form-termo");
  if (!form) return;
  var equipe = form.querySelector("[data-equipe]");
  if (!equipe) return;

  function atualizar() {
    var total = form.querySelectorAll('input[name="servidores"]:checked').length;
    equipe.querySelectorAll("[data-pessoa]").forEach(function (pessoa) {
      pessoa.classList.toggle("of-membro--viaja", pessoa.querySelector('input[name="servidores"]').checked);
    });
    var contagem = form.querySelector("[data-equipe-contagem]");
    if (contagem) contagem.textContent = total === 1 ? "1 servidor" : total + " servidores";
  }
  equipe.addEventListener("change", atualizar);
  var busca = form.querySelector("[data-equipe-busca]");
  if (busca) {
    busca.addEventListener("input", function () {
      var termo = busca.value.trim().toLowerCase();
      equipe.querySelectorAll("[data-pessoa]").forEach(function (pessoa) {
        var texto = (pessoa.dataset.busca || "").toLowerCase();
        pessoa.hidden = termo !== "" && texto.indexOf(termo) === -1 && !pessoa.querySelector('input[name="servidores"]').checked;
      });
    });
  }
  atualizar();
})();
