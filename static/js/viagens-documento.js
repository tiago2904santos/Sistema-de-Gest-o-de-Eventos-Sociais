/* Prévia A4 do documento (viagens_oficios/documento.html).

   A folha vive num iframe da mesma origem. Aqui a página ajusta a altura do
   quadro ao conteúdo, para o documento rolar com a página como se estivesse
   nela — e é daqui que o editor de campos vai conversar com a folha. */
(function () {
  'use strict';

  var quadro = document.getElementById('dc-folha');
  if (!quadro) return;

  function ajustar() {
    var doc = quadro.contentDocument;
    if (!doc || !doc.documentElement) return;
    var altura = doc.documentElement.scrollHeight;
    if (altura > 0) quadro.style.height = altura + 'px';
  }

  function ligar() {
    var doc = quadro.contentDocument;
    if (!doc) return;
    ajustar();
    if (window.ResizeObserver) new ResizeObserver(ajustar).observe(doc.documentElement);
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(ajustar);
  }

  quadro.addEventListener('load', ligar);
  if (quadro.contentDocument && quadro.contentDocument.readyState === 'complete' && quadro.contentDocument.body && quadro.contentDocument.body.children.length) ligar();
})();
