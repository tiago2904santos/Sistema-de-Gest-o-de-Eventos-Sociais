/* Coffee Break — número da OS sugerido pelo município.
   Cada opção de município traz o próximo número do lote que a atende
   (data-proximo). Ao escolher o município, o campo recebe esse número,
   a menos que a pessoa já tenha digitado um. Em registro existente, só
   sugere quando o município leva a outro lote. */
(function () {
  "use strict";
  var campo = document.querySelector("[data-numero-os]");
  var municipio = document.querySelector("select[name=municipio]");
  if (!campo || !municipio || campo.disabled) return;

  var digitado = false;
  campo.addEventListener("input", function () { digitado = campo.value !== ""; });

  function sugerir() {
    var opcao = municipio.options[municipio.selectedIndex];
    if (!opcao || !opcao.dataset.proximo || digitado) return;
    var loteAtual = campo.dataset.loteAtual;
    if (loteAtual && opcao.dataset.loteId === loteAtual) return;
    campo.value = opcao.dataset.proximo;
  }

  municipio.addEventListener("change", sugerir);
  if (!campo.value) sugerir();
})();
