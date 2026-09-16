/**
 * Justificativas — no modal de cadastro, o modelo escolhido preenche o texto.
 * O modal chega por fetch (ds-v32.js), então a escuta é por delegação.
 */
(function () {
  "use strict";

  document.addEventListener("change", function (evento) {
    var seletor = evento.target;
    if (!seletor || seletor.name !== "modelo") return;
    var form = seletor.closest("[data-jt-form]");
    if (!form) return;
    var fonte = form.querySelector("#jt-modelos-texto");
    var texto = form.querySelector('textarea[name="texto"]');
    if (!fonte || !texto || !seletor.value) return;
    var modelos = {};
    try { modelos = JSON.parse(fonte.textContent || "{}"); } catch (erro) { modelos = {}; }
    var valor = modelos[seletor.value];
    if (valor === undefined) return;
    texto.value = valor;
    texto.dispatchEvent(new Event("input", { bubbles: true }));
  });
})();
