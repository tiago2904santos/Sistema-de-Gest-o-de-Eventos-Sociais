/* Palco do editor do documento (documentos/editor/embutido.html): as páginas,
   o zoom e o tamanho do quadro.

   A folha vive num iframe da mesma origem e chega como uma folha contínua.
   Aqui ela vira páginas A4 separadas, como num editor de texto: os blocos do
   corpo (tabelas, parágrafos, seções) são distribuídos pelas páginas na ordem,
   um bloco que não cabe vai inteiro para a página seguinte, e as quebras
   forçadas (quebra de página inserida, `break-before/after: page` do CSS do
   tipo) abrem página nova. Cada página repete cabeçalho e rodapé. É uma
   aproximação do que o WeasyPrint faz — blocos não se partem no meio, como
   as regras `page-break-inside: avoid` dos documentos já pedem.

   O zoom escala o quadro inteiro (transform), e a caixa em volta ganha o
   tamanho visível, para a página rolar certo. O editor
   (`documento-editor.js`) chama `palco.atualizar()` quando a folha muda e
   lê `palco.escala()` para posicionar o balão do campo. */
(function () {
  'use strict';

  /* Um palco por editor montado (`raiz` = o `.de-app` do editor): o editor
     embutido no fim dos formulários monta e desmonta conforme o documento
     aberto. Devolve o que o editor usa e `desmontar`. */
  function montarPalco(raiz) {
  var quadro = raiz.querySelector('.dc-folha');
  var caixa = raiz.querySelector('[data-de-folha-caixa]');
  if (!quadro) return null;

  var seletorZoom = raiz.querySelector('[data-de-zoom]');
  var CHAVE_ZOOM = 'documento-editor:zoom';
  var zoom = 1;
  var observador = null;

  function lerZoomGuardado() {
    try { var v = parseFloat(window.localStorage.getItem(CHAVE_ZOOM)); return v > 0 ? v : 1; } catch (e) { return 1; }
  }
  function guardarZoom(v) {
    try { window.localStorage.setItem(CHAVE_ZOOM, String(v)); } catch (e) { /* sem armazenamento: vale só nesta visita */ }
  }

  function documentoDaFolha() { return quadro.contentDocument; }
  function px(valor) { return parseFloat(valor) || 0; }

  /* ---- Páginas ------------------------------------------------------- */

  // Junta de volta numa folha só o que uma paginação anterior espalhou.
  function desfazerPaginas(doc) {
    var folhas = doc.querySelectorAll('.folha');
    if (!folhas.length) return null;
    var primeira = folhas[0];
    var corpo = primeira.querySelector('.doc-corpo');
    for (var i = 1; i < folhas.length; i++) {
      var outro = folhas[i].querySelector('.doc-corpo');
      while (corpo && outro && outro.firstChild) corpo.appendChild(outro.firstChild);
      folhas[i].remove();
    }
    primeira.style.height = '';
    return primeira;
  }

  function quebraForcadaAntes(estilo) { return estilo.breakBefore === 'page' || estilo.pageBreakBefore === 'always'; }
  function quebraForcadaDepois(el, estilo) {
    return estilo.breakAfter === 'page' || estilo.pageBreakAfter === 'always' || el.classList.contains('doc-quebra');
  }

  function paginar() {
    var doc = documentoDaFolha();
    if (!doc || !doc.body) return;
    var folha = desfazerPaginas(doc);
    if (!folha) return;
    var corpo = folha.querySelector('.doc-corpo');
    var janela = doc.defaultView;
    var estiloFolha = janela.getComputedStyle(folha);
    var alturaPagina = px(estiloFolha.minHeight);
    if (!corpo || !alturaPagina) return;
    var topo = px(estiloFolha.paddingTop);
    var util = alturaPagina - topo - px(estiloFolha.paddingBottom);

    // Distribui os blocos: cada página guarda onde começou (em y da folha).
    var paginas = [[]];
    var inicio = null;
    Array.prototype.forEach.call(corpo.children, function (bloco) {
      var estilo = janela.getComputedStyle(bloco);
      var cima = bloco.offsetTop - topo - px(estilo.marginTop);
      var baixo = bloco.offsetTop - topo + bloco.offsetHeight + px(estilo.marginBottom);
      var atual = paginas[paginas.length - 1];
      if (inicio === null) inicio = cima;
      if (atual.length && (quebraForcadaAntes(estilo) || baixo - inicio > util)) {
        paginas.push([]);
        atual = paginas[paginas.length - 1];
        inicio = cima;
      }
      atual.push(bloco);
      if (quebraForcadaDepois(bloco, estilo)) { paginas.push([]); inicio = null; }
    });
    paginas = paginas.filter(function (p) { return p.length; });

    folha.style.height = alturaPagina + 'px';
    if (paginas.length < 2) return;

    var cabecalho = folha.querySelector('.doc-cabecalho');
    var rodape = folha.querySelector('.doc-rodape');
    var anterior = folha;
    for (var i = 1; i < paginas.length; i++) {
      var pagina = folha.cloneNode(false);
      pagina.classList.add('folha--seguinte');
      pagina.style.height = alturaPagina + 'px';
      [cabecalho, rodape].forEach(function (parte) {
        if (!parte) return;
        var copia = parte.cloneNode(true);
        copia.removeAttribute('id');
        copia.setAttribute('aria-hidden', 'true');
        pagina.appendChild(copia);
      });
      var novoCorpo = corpo.cloneNode(false);
      paginas[i].forEach(function (bloco) { novoCorpo.appendChild(bloco); });
      pagina.appendChild(novoCorpo);
      anterior.after(pagina);
      anterior = pagina;
    }
  }

  /* ---- Tamanho e zoom ------------------------------------------------ */

  function ajustar() {
    var doc = documentoDaFolha();
    if (!doc || !doc.documentElement) return;
    var folha = doc.querySelector('.folha');
    var largura = folha ? folha.offsetWidth + 64 : quadro.offsetWidth;
    var altura = doc.documentElement.scrollHeight;
    if (largura > 0) quadro.style.width = largura + 'px';
    if (altura > 0) quadro.style.height = altura + 'px';
    quadro.style.transform = zoom === 1 ? '' : 'scale(' + zoom + ')';
    if (caixa) {
      caixa.style.width = Math.ceil(largura * zoom) + 'px';
      caixa.style.height = Math.ceil(altura * zoom) + 'px';
    }
  }

  function atualizar() {
    paginar();
    ajustar();
  }

  function definirZoom(valor) {
    zoom = Math.min(2, Math.max(0.5, valor));
    if (seletorZoom) {
      var existe = Array.prototype.some.call(seletorZoom.options, function (o) { return parseFloat(o.value) === zoom; });
      if (!existe) {
        var opcao = document.createElement('option');
        opcao.value = String(zoom);
        opcao.textContent = Math.round(zoom * 100) + '%';
        seletorZoom.appendChild(opcao);
      }
      seletorZoom.value = String(zoom);
    }
    guardarZoom(zoom);
    ajustar();
  }

  function passoDeZoom(direcao) {
    if (!seletorZoom) return;
    var valores = Array.prototype.map.call(seletorZoom.options, function (o) { return parseFloat(o.value); }).sort(function (a, b) { return a - b; });
    var proximo = direcao > 0
      ? valores.find(function (v) { return v > zoom + 0.001; })
      : valores.slice().reverse().find(function (v) { return v < zoom - 0.001; });
    if (proximo) definirZoom(proximo);
  }

  if (seletorZoom) seletorZoom.addEventListener('change', function () { definirZoom(parseFloat(seletorZoom.value)); });
  var menos = raiz.querySelector('[data-de-zoom-menos]');
  var mais = raiz.querySelector('[data-de-zoom-mais]');
  if (menos) menos.addEventListener('click', function () { passoDeZoom(-1); });
  if (mais) mais.addEventListener('click', function () { passoDeZoom(1); });

  /* ---- Ligação ------------------------------------------------------- */

  function ligar() {
    var doc = documentoDaFolha();
    if (!doc || !doc.documentElement) return;
    atualizar();
    if (observador) observador.disconnect();
    if (window.ResizeObserver) {
      // Só o tamanho acompanha o conteúdo ao vivo; repaginar mexe no DOM e
      // fica para quando a folha muda (ou o cursor sai do trecho).
      observador = new ResizeObserver(ajustar);
      observador.observe(doc.documentElement);
    }
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(atualizar);
  }

  /* ---- Histórico: painel lateral que abre e fecha ------------------------ */
  var historico = raiz.querySelector('[data-de-historico]');
  var alternadores = raiz.querySelectorAll('[data-de-alternar-historico]');
  function alternarHistorico() {
    if (!historico) return;
    historico.hidden = !historico.hidden;
    alternadores.forEach(function (botao) {
      if (botao.hasAttribute('aria-pressed')) botao.setAttribute('aria-pressed', historico.hidden ? 'false' : 'true');
    });
  }
  alternadores.forEach(function (botao) { botao.addEventListener('click', alternarHistorico); });

  zoom = lerZoomGuardado();
  definirZoom(zoom);
  quadro.addEventListener('load', ligar);
  if (quadro.contentDocument && quadro.contentDocument.readyState === 'complete' && quadro.contentDocument.body && quadro.contentDocument.body.children.length) ligar();

  return {
    atualizar: atualizar,
    ajustar: ajustar,
    escala: function () { return zoom; },
    desmontar: function () { if (observador) observador.disconnect(); observador = null; }
  };
  }

  window.DocPalcoMontar = montarPalco;
})();
