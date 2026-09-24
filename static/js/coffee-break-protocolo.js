/* Coffee Break — protocolo com a mesma máscara do protocolo de Viagens
   (viagens-oficios.js): 00.000.000-0. Número antigo em outro formato (mais
   de 9 dígitos) fica como está até alguém digitar nele. */
(function () {
  "use strict";
  function mascaraProtocolo(valor) {
    var d = (valor || "").replace(/\D/g, "").slice(0, 9);
    var s = d.slice(0, 2);
    if (d.length > 2) s += "." + d.slice(2, 5);
    if (d.length > 5) s += "." + d.slice(5, 8);
    if (d.length > 8) s += "-" + d.slice(8);
    return s;
  }
  ["protocolo_pcpr_oficio", "protocolo_pagamento"].forEach(function (nome) {
    var campo = document.querySelector('[name="' + nome + '"]');
    if (!campo || campo.type === "hidden") return;
    campo.placeholder = "00.000.000-0";
    if ((campo.value || "").replace(/\D/g, "").length <= 9) campo.value = mascaraProtocolo(campo.value);
    campo.addEventListener("input", function () { campo.value = mascaraProtocolo(campo.value); });
  });
})();
