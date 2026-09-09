/* Visualizador de PDF com caixa arrastável — o miolo de "posicione isto no documento".
 *
 * Duas telas fazem exatamente isso: a assinatura eletrônica, onde o signatário arrasta a
 * própria assinatura, e o ajuste do carimbo, onde o operador arrasta o número de
 * solicitação sobre o ofício do eProtocolo. O que elas compartilham é tudo menos O QUE se
 * arrasta: renderizar a página em canvas, navegar entre páginas, redesenhar quando a
 * janela muda de largura, e mover/redimensionar uma caixa presa ao palco.
 *
 * A saída é sempre a mesma: FRAÇÕES da página com origem no topo-esquerdo, que é o que
 * `documentos/services/pdf_overlay.py` espera do outro lado. Converter cedo, num lugar só,
 * é o que evita o sinal trocado no eixo Y aparecer em cada tela nova.
 *
 * Depende do `pdfjsLib` já carregado pela página (vendorizado em `static/vendor/pdfjs/`).
 */
(function () {
  "use strict";

  window.CV = window.CV || {};

  function limitar(valor, minimo, maximo) {
    return Math.min(maximo, Math.max(minimo, valor));
  }

  function ponteiro(evento) {
    var toque = evento.touches ? evento.touches[0] : evento;
    return { x: toque.clientX, y: toque.clientY };
  }

  /* Renderiza o PDF e navega entre as páginas.
   *
   * `onPagina` recebe o índice em BASE ZERO — o mesmo que vai para o servidor e para o
   * pypdf. O rótulo na tela é que soma 1; quem guarda o número nunca vê a versão humana.
   */
  function visualizador(opcoes) {
    var canvas = opcoes.canvas;
    var stage = opcoes.stage;
    var viewer = opcoes.viewer;
    if (!canvas || !stage || !viewer) return null;

    var documento = null;
    var pagina = 1;
    var total = 1;
    var quadroDeRedesenho = null;

    function desenhar(numero) {
      if (!documento) return;
      documento.getPage(numero).then(function (page) {
        var dpr = window.devicePixelRatio || 1;
        var largura = viewer.clientWidth || 320;
        var base = page.getViewport({ scale: 1 });
        var vp = page.getViewport({ scale: largura / base.width });
        canvas.width = Math.floor(vp.width * dpr);
        canvas.height = Math.floor(vp.height * dpr);
        canvas.style.width = vp.width + "px";
        canvas.style.height = vp.height + "px";
        stage.style.width = vp.width + "px";
        stage.style.height = vp.height + "px";
        var ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        page.render({ canvasContext: ctx, viewport: vp });
        pagina = numero;
        if (opcoes.pageLabel) opcoes.pageLabel.textContent = numero + " / " + total;
        if (opcoes.btnPrev) opcoes.btnPrev.disabled = numero <= 1;
        if (opcoes.btnNext) opcoes.btnNext.disabled = numero >= total;
        if (typeof opcoes.onPagina === "function") opcoes.onPagina(numero - 1, total);
      });
    }

    function carregar() {
      if (typeof pdfjsLib === "undefined") return;
      if (opcoes.workerSrc) pdfjsLib.GlobalWorkerOptions.workerSrc = opcoes.workerSrc;
      pdfjsLib
        .getDocument({ url: opcoes.url, withCredentials: true })
        .promise.then(function (doc) {
          documento = doc;
          total = doc.numPages;
          desenhar(1);
        })
        .catch(function () {
          if (typeof opcoes.onErro === "function") opcoes.onErro();
        });
    }

    if (opcoes.btnPrev) {
      opcoes.btnPrev.addEventListener("click", function () {
        if (pagina > 1) desenhar(pagina - 1);
      });
    }
    if (opcoes.btnNext) {
      opcoes.btnNext.addEventListener("click", function () {
        if (pagina < total) desenhar(pagina + 1);
      });
    }
    /* Redesenhar no `resize` é obrigatório, e não enfeite: a escala vem da largura do
     * contêiner, então sem isto a página fica na resolução antiga e a caixa arrastada
     * aponta para outro ponto do documento. */
    window.addEventListener("resize", function () {
      if (quadroDeRedesenho !== null) window.cancelAnimationFrame(quadroDeRedesenho);
      quadroDeRedesenho = window.requestAnimationFrame(function () {
        quadroDeRedesenho = null;
        if (documento) desenhar(pagina);
      });
    });

    carregar();

    return {
      irPara: function (numero) { desenhar(numero); },
      pagina: function () { return pagina; },
      total: function () { return total; },
      redesenhar: function () { desenhar(pagina); },
    };
  }

  /* Move e redimensiona uma caixa dentro do palco.
   *
   * `aspecto` (largura/altura) é mantido no redimensionamento: a assinatura não pode
   * distorcer, e o número precisa que a altura acompanhe a largura porque é dela que sai
   * o corpo da fonte.
   */
  function caixaArrastavel(opcoes) {
    var caixa = opcoes.caixa;
    var alca = opcoes.alca;
    var stage = opcoes.stage;
    if (!caixa || !stage) return null;

    var aspecto = opcoes.aspecto || 4;
    var larguraMinima = opcoes.larguraMinima || 40;
    var modo = null;
    var inicio = null;

    /* `silencioso` existe para o posicionamento PROGRAMÁTICO não avisar mudança.
     *
     * Sem ele, colocar a caixa onde o servidor mandou disparava `onMudou`, que grava a
     * posição de volta a partir do tamanho ATUAL do palco. Enquanto o PDF ainda não
     * terminou de render, o palco mede quase nada — e a gravação devolvia frações perto
     * de zero, que a próxima passada lia como posição verdadeira e encolhia de novo.
     * Duas voltas e a caixa tinha 2px de altura no canto superior esquerdo.
     *
     * Só o arraste do usuário grava. É ele quem tem opinião sobre onde a coisa vai. */
    function posicionar(esquerda, topo, largura, altura, silencioso) {
      var sw = stage.clientWidth;
      var sh = stage.clientHeight;
      esquerda = limitar(esquerda, 0, Math.max(0, sw - largura));
      topo = limitar(topo, 0, Math.max(0, sh - altura));
      caixa.style.left = esquerda + "px";
      caixa.style.top = topo + "px";
      caixa.style.width = largura + "px";
      caixa.style.height = altura + "px";
      if (!silencioso && typeof opcoes.onMudou === "function") opcoes.onMudou(fracoes());
    }

    function fracoes() {
      var sw = stage.clientWidth || 1;
      var sh = stage.clientHeight || 1;
      return {
        x: limitar(caixa.offsetLeft / sw, 0, 1),
        y: limitar(caixa.offsetTop / sh, 0, 1),
        largura: limitar(caixa.offsetWidth / sw, 0, 1),
        altura: limitar(caixa.offsetHeight / sh, 0, 1),
      };
    }

    function aoDescer(evento, qual) {
      if (caixa.hidden) return;
      evento.preventDefault();
      modo = qual;
      var p = ponteiro(evento);
      inicio = {
        px: p.x,
        py: p.y,
        esquerda: caixa.offsetLeft,
        topo: caixa.offsetTop,
        largura: caixa.offsetWidth,
        altura: caixa.offsetHeight,
      };
    }

    function aoMover(evento) {
      if (!modo) return;
      evento.preventDefault();
      var p = ponteiro(evento);
      var dx = p.x - inicio.px;
      var dy = p.y - inicio.py;
      if (modo === "mover") {
        posicionar(inicio.esquerda + dx, inicio.topo + dy, inicio.largura, inicio.altura);
      } else {
        var largura = limitar(inicio.largura + dx, larguraMinima, stage.clientWidth);
        posicionar(inicio.esquerda, inicio.topo, largura, largura / aspecto);
      }
    }

    function aoSubir() { modo = null; inicio = null; }

    caixa.addEventListener("mousedown", function (e) {
      if (alca && e.target === alca) return;
      aoDescer(e, "mover");
    });
    caixa.addEventListener("touchstart", function (e) {
      if (alca && e.target === alca) return;
      aoDescer(e, "mover");
    }, { passive: false });
    if (alca) {
      alca.addEventListener("mousedown", function (e) { aoDescer(e, "redimensionar"); });
      alca.addEventListener("touchstart", function (e) { aoDescer(e, "redimensionar"); }, { passive: false });
    }
    window.addEventListener("mousemove", aoMover);
    window.addEventListener("touchmove", aoMover, { passive: false });
    window.addEventListener("mouseup", aoSubir);
    window.addEventListener("touchend", aoSubir);

    return {
      posicionar: posicionar,
      fracoes: fracoes,
      definirAspecto: function (valor) { if (valor) aspecto = valor; },
      aspecto: function () { return aspecto; },
    };
  }

  window.CV.pdfPlace = {
    visualizador: visualizador,
    caixaArrastavel: caixaArrastavel,
    limitar: limitar,
  };
}());
