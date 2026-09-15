/**
 * Justificativas — inclusão rápida: o modelo escolhido preenche o texto, e o
 * painel abre já focado na busca de ofícios. O seletor de ofícios em si é o
 * `viagens-picker-oficios.js`, compartilhado com o cadastro de termos.
 */
(function () {
  "use strict";

  var form = document.querySelector("[data-jt-rapida]");
  if (!form) return;

  var modelos = {};
  try { modelos = JSON.parse(document.getElementById("oficio-modelos-texto").textContent); } catch (erro) { modelos = {}; }
  var seletor = document.getElementById("id_rapida-modelo");
  var texto = document.getElementById("id_rapida-texto");
  if (seletor && texto) {
    seletor.addEventListener("change", function () {
      var valor = (modelos["rapida-modelo"] || {})[seletor.value];
      if (valor !== undefined) {
        texto.value = valor;
        texto.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
  }

  var busca = form.querySelector("[data-picker-busca]");
  document.querySelectorAll('[data-expande="#inclusao-rapida"]').forEach(function (botao) {
    botao.addEventListener("click", function () {
      var painel = document.getElementById("inclusao-rapida");
      if (painel && !painel.hidden && busca) setTimeout(function () { busca.focus(); }, 50);
    });
  });
})();
