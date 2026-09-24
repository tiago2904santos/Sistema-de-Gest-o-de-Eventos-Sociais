/* Coffee Break — visualizador de PDF inline (etapa 3), sem editor.

   Cada `[data-cb-pdf="<url>"]` mora num cartão <details> fechado. Ao abrir o
   cartão, o PDF é buscado e cada página é desenhada num <canvas> pelo pdf.js
   (vendorizado em static/vendor/pdfjs/) — funciona em qualquer navegador,
   inclusive os que não mostram PDF dentro da página. Desenha uma vez só. */
(function () {
  "use strict";
  var raiz = document.querySelector("[data-cb-pdf-worker]");
  if (typeof pdfjsLib === "undefined") return;
  if (raiz) pdfjsLib.GlobalWorkerOptions.workerSrc = raiz.getAttribute("data-cb-pdf-worker");

  function estado(alvo, texto) {
    alvo.innerHTML = "";
    var p = document.createElement("p");
    p.className = "cb-pdf__estado";
    p.textContent = texto;
    alvo.appendChild(p);
  }

  function desenhar(alvo) {
    if (alvo.hasAttribute("data-cb-pdf-feito")) return;
    alvo.setAttribute("data-cb-pdf-feito", "");
    estado(alvo, "Carregando o documento…");
    pdfjsLib.getDocument({ url: alvo.getAttribute("data-cb-pdf"), withCredentials: true }).promise
      .then(function (pdf) {
        alvo.innerHTML = "";
        var largura = Math.min(alvo.clientWidth - 24, 820);
        var escalaTela = window.devicePixelRatio || 1;
        var fila = Promise.resolve();
        for (var n = 1; n <= pdf.numPages; n++) {
          (function (numero) {
            fila = fila.then(function () {
              return pdf.getPage(numero).then(function (pagina) {
                var base = pagina.getViewport({ scale: 1 });
                var escala = largura / base.width;
                var vista = pagina.getViewport({ scale: escala * escalaTela });
                var canvas = document.createElement("canvas");
                canvas.className = "cb-pdf__pagina";
                canvas.width = Math.floor(vista.width);
                canvas.height = Math.floor(vista.height);
                canvas.style.width = Math.floor(vista.width / escalaTela) + "px";
                canvas.setAttribute("aria-label", "Página " + numero + " de " + pdf.numPages);
                alvo.appendChild(canvas);
                return pagina.render({ canvasContext: canvas.getContext("2d"), viewport: vista }).promise;
              });
            });
          })(n);
        }
        return fila;
      })
      .catch(function () {
        alvo.removeAttribute("data-cb-pdf-feito");
        estado(alvo, "Não foi possível abrir o documento aqui. Use “Abrir em nova aba”.");
      });
  }

  document.querySelectorAll("[data-cb-pdf]").forEach(function (alvo) {
    var cartao = alvo.closest("details");
    if (!cartao) { desenhar(alvo); return; }
    cartao.addEventListener("toggle", function () { if (cartao.open) desenhar(alvo); });
    if (cartao.open) desenhar(alvo);
  });
})();
