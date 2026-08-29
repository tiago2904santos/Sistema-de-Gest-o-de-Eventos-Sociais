/**
 * JS leve do Sistema de Gestão de Eventos Sociais.
 * Sem frameworks — apenas melhorias progressivas.
 */
(function () {
  "use strict";

  // Fecha alertas automaticamente após 6 segundos.
  document.querySelectorAll(".alerta").forEach(function (alerta) {
    setTimeout(function () {
      alerta.style.transition = "opacity 0.4s ease";
      alerta.style.opacity = "0";
      setTimeout(function () {
        alerta.remove();
      }, 400);
    }, 6000);
  });
})();
