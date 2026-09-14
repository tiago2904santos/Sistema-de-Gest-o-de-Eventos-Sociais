/* Como no GV, Tab e Shift+Tab circulam entre as ações da confirmação.
   O diálogo nativo mantém Escape e a devolução de foco ao botão de abertura. */
(() => {
  document.querySelectorAll("[data-catalogo-dialog]").forEach(dialog => {
    dialog.addEventListener("keydown", event => {
      if (!dialog.open || event.key !== "Tab") return;
      const controles = [...dialog.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )].filter(elemento => !elemento.hidden && elemento.getAttribute("aria-hidden") !== "true");
      const primeiro = controles[0];
      const ultimo = controles[controles.length - 1];
      if (event.shiftKey && document.activeElement === primeiro && ultimo) {
        event.preventDefault();
        ultimo.focus();
      } else if (!event.shiftKey && document.activeElement === ultimo && primeiro) {
        event.preventDefault();
        primeiro.focus();
      }
    });
  });
})();
