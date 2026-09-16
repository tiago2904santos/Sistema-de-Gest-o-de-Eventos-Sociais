/**
 * Arrastar para reordenar linhas de destino, pela alça.
 *
 * Saiu do `roteiro-editor.js` para ser o mesmo comportamento em toda tela que
 * usa o componente de destinos (o editor de roteiro e o cadastro de termo).
 *
 * Ponteiro, não o drag-and-drop do HTML5: a linha acompanha o cursor e as
 * vizinhas deslizam para abrir o lugar onde ela vai cair. Ao soltar, a ordem
 * do DOM muda de uma vez, sem salto, porque as linhas já estão desenhadas
 * onde vão ficar.
 *
 * Uso: DS.arrastarDestinos(lista, aoReordenar). `lista` é o elemento que
 * guarda as linhas `[data-destino]`; `aoReordenar` só é chamado quando a
 * ordem muda de verdade.
 */
(function () {
  "use strict";

  var LIMIAR_ARRASTE = 4;

  function slice(lista) { return Array.prototype.slice.call(lista); }

  window.DS = window.DS || {};

  window.DS.arrastarDestinos = function (lista, aoReordenar) {
    if (!lista) return;
    var arraste = null;

    function linhas() { return slice(lista.querySelectorAll("[data-destino]")); }

    function visiveis() {
      return linhas().filter(function (linha) { return !linha.hidden; });
    }

    function limparDeslocamentos() {
      linhas().forEach(function (linha) {
        linha.style.transform = "";
        linha.classList.remove("is-dragging");
      });
    }

    function prepararArraste() {
      var atuais = visiveis();
      var caixas = atuais.map(function (linha) { return linha.getBoundingClientRect(); });
      var origem = atuais.indexOf(arraste.linha);
      var vao = caixas.length > 1 ? Math.max(0, caixas[1].top - caixas[0].bottom) : 0;
      arraste.linhas = atuais;
      arraste.origem = origem;
      arraste.alvo = origem;
      arraste.centros = caixas.map(function (caixa) { return caixa.top + caixa.height / 2; });
      arraste.passo = caixas[origem].height + vao;
      arraste.minimo = caixas[0].top - caixas[origem].top;
      arraste.maximo = caixas[caixas.length - 1].top - caixas[origem].top;
      lista.classList.add("is-reordenando");
      arraste.linha.classList.add("is-dragging");
      document.body.classList.add("is-arrastando-destino");
    }

    function encerrarArraste() {
      arraste = null;
      limparDeslocamentos();
      lista.classList.remove("is-reordenando");
      document.body.classList.remove("is-arrastando-destino");
      document.removeEventListener("pointermove", aoMoverPonteiro);
      document.removeEventListener("pointerup", aoSoltarPonteiro);
      document.removeEventListener("pointercancel", encerrarArraste);
    }

    function aoMoverPonteiro(evento) {
      if (!arraste) return;
      var dy = evento.clientY - arraste.y;
      if (!arraste.ativo) {
        var dx = evento.clientX - arraste.x;
        if (Math.abs(dx) < LIMIAR_ARRASTE && Math.abs(dy) < LIMIAR_ARRASTE) return;
        arraste.ativo = true;
        prepararArraste();
      }
      evento.preventDefault();
      // A linha não sai da lista: para exatamente no primeiro e no último lugar.
      // As comparações abaixo aceitam empate, então as pontas continuam alcançáveis.
      dy = Math.max(arraste.minimo, Math.min(arraste.maximo, dy));
      arraste.linha.style.transform = "translateY(" + dy + "px)";

      // O lugar de destino é o da última vizinha cujo centro a linha já passou.
      var centro = arraste.centros[arraste.origem] + dy;
      var alvo = arraste.origem;
      arraste.centros.forEach(function (centroVizinha, indice) {
        if (indice < arraste.origem && centro <= centroVizinha) alvo = Math.min(alvo, indice);
        if (indice > arraste.origem && centro >= centroVizinha) alvo = Math.max(alvo, indice);
      });
      arraste.alvo = alvo;

      arraste.linhas.forEach(function (linha, indice) {
        if (indice === arraste.origem) return;
        var desloca = 0;
        if (arraste.origem < alvo && indice > arraste.origem && indice <= alvo) desloca = -arraste.passo;
        if (arraste.origem > alvo && indice >= alvo && indice < arraste.origem) desloca = arraste.passo;
        linha.style.transform = desloca ? "translateY(" + desloca + "px)" : "";
      });
    }

    function aoSoltarPonteiro(evento) {
      if (!arraste) return;
      if (!arraste.ativo) { encerrarArraste(); return; }
      evento.preventDefault();
      var atuais = arraste.linhas;
      var origem = arraste.origem;
      var alvo = arraste.alvo;
      var arrastada = arraste.linha;
      lista.classList.add("sem-transicao");
      if (alvo !== origem) {
        var referencia = alvo > origem ? atuais[alvo].nextSibling : atuais[alvo];
        lista.insertBefore(arrastada, referencia);
      }
      encerrarArraste();
      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () { lista.classList.remove("sem-transicao"); });
      });
      if (alvo === origem) return;
      if (aoReordenar) aoReordenar();
    }

    lista.addEventListener("pointerdown", function (evento) {
      if (evento.button !== 0) return;
      // Com um destino só não há o que reordenar.
      if (visiveis().length <= 1) return;
      if (!evento.target.closest("[data-destino-alca]")) return;
      var linha = evento.target.closest("[data-destino]");
      if (!linha) return;
      evento.preventDefault();
      encerrarArraste();
      arraste = { linha: linha, x: evento.clientX, y: evento.clientY, ativo: false };
      document.addEventListener("pointermove", aoMoverPonteiro);
      document.addEventListener("pointerup", aoSoltarPonteiro);
      document.addEventListener("pointercancel", encerrarArraste);
    });
  };
})();
