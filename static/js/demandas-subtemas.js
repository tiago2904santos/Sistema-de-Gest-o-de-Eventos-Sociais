(function () {
  "use strict";

  function atualizarEscopo() {
    var campo = document.getElementById("id_subtema");
    var destino = document.getElementById("id_subtema_escopo");
    if (!campo || !destino) return;

    var opcao = campo.options[campo.selectedIndex];
    var escopo = opcao ? (opcao.getAttribute("data-escopo") || "").trim() : "";
    destino.textContent = escopo ? "Escopo cadastrado: " + escopo : "";
    destino.hidden = !escopo;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var campo = document.getElementById("id_subtema");
    if (!campo) return;
    campo.addEventListener("change", atualizarEscopo);
    atualizarEscopo();
  });
}());
