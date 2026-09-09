/* Ajustar onde cada número de solicitação é carimbado no ofício assinado.
 *
 * O visualizador de PDF e o arraste vêm de `components/pdf-place.js`, os mesmos da tela
 * pública de assinatura. O que é desta tela: uma caixa POR SERVIDOR (a assinatura tem
 * uma só), a troca de página escondendo as caixas que não são daquela folha, e o corpo
 * da fonte saindo da altura da caixa.
 *
 * Os campos ocultos guardam frações da página com origem no topo-esquerdo — a mesma
 * convenção de `documentos/services/pdf_overlay.py`, que desenha do outro lado.
 */
(function () {
  "use strict";

  var form = document.querySelector("[data-pdf-place]");
  if (!form || !window.CV || !window.CV.pdfPlace) return;

  var stage = document.getElementById("carimbo-stage");
  var canvas = document.getElementById("carimbo-canvas");
  var viewer = document.getElementById("carimbo-viewer");
  var hint = document.getElementById("carimbo-hint");

  var caixas = Array.prototype.slice.call(
    form.querySelectorAll("[data-pdf-place-box]")
  );
  if (!caixas.length) return;

  var paginaAtual = 0;

  function campo(psPk, nome) {
    return form.querySelector(
      '[data-pdf-place-field="' + nome + '"][data-ps="' + psPk + '"]'
    );
  }

  function lerNumero(valor, padrao) {
    var n = parseFloat(valor);
    return isNaN(n) ? padrao : n;
  }

  /* Escreve a posição da caixa nos campos ocultos.
   *
   * `tamanho` é a ALTURA da caixa em fração — o servidor a multiplica pela altura da
   * página para achar o corpo da fonte. Guardar em pixels quebraria em qualquer tela de
   * largura diferente da que ajustou.
   */
  function gravar(caixa, fracoes) {
    var ps = caixa.dataset.ps;
    campo(ps, "x").value = fracoes.x.toFixed(5);
    campo(ps, "y").value = fracoes.y.toFixed(5);
    campo(ps, "tamanho").value = fracoes.altura.toFixed(5);
    campo(ps, "pagina").value = String(caixa.dataset.pagina || 0);
  }

  function ajustarCorpo(caixa) {
    // O texto dentro da caixa tem de sair do tamanho que vai para o PDF, senão o
    // operador posiciona olhando um número e recebe outro.
    caixa.style.fontSize = caixa.offsetHeight + "px";
  }

  var controles = caixas.map(function (caixa) {
    var ps = caixa.dataset.ps;
    var alca = caixa.querySelector("[data-pdf-place-handle]");
    var texto = caixa.querySelector("[data-pdf-place-text]");

    var arrastavel = window.CV.pdfPlace.caixaArrastavel({
      caixa: caixa,
      alca: alca,
      stage: stage,
      // O aspecto nasce do texto e é recalculado quando a caixa é posicionada: um
      // número de 4 dígitos e um de 10 não ocupam a mesma largura no mesmo corpo.
      aspecto: 6,
      larguraMinima: 24,
      onMudou: function (fracoes) {
        ajustarCorpo(caixa);
        gravar(caixa, fracoes);
      },
    });

    caixa.addEventListener("mousedown", function () {
      caixas.forEach(function (outra) {
        outra.classList.toggle("pdf-place__box--ativa", outra === caixa);
      });
    });

    return { ps: ps, caixa: caixa, texto: texto, arrastavel: arrastavel };
  });

  /* Coloca cada caixa onde o servidor mandou, e só as da página atual ficam visíveis. */
  function posicionarTodas() {
    var sw = stage.clientWidth;
    var sh = stage.clientHeight;
    /* Palco sem medida ainda: o PDF não terminou de render. Posicionar agora colocaria
     * tudo em cima do canto superior esquerdo — e como as frações saem de uma divisão
     * pela altura do palco, o resultado seria uma caixa de 2px. Tenta no próximo quadro. */
    if (!sw || !sh) {
      window.requestAnimationFrame(posicionarTodas);
      return;
    }
    controles.forEach(function (ctrl) {
      var pagina = parseInt(ctrl.caixa.dataset.pagina || "0", 10) || 0;
      var daPagina = pagina === paginaAtual;
      ctrl.caixa.hidden = !daPagina;
      if (!daPagina) return;

      var altura = lerNumero(campo(ctrl.ps, "tamanho").value, 0.012) * sh;
      // Mede o texto no corpo real para a caixa nascer do tamanho dele, em vez de um
      // retângulo arbitrário que o operador teria de acertar na mão.
      ctrl.caixa.style.fontSize = altura + "px";
      var largura = Math.max(24, ctrl.texto.offsetWidth + 4);
      ctrl.arrastavel.definirAspecto(largura / Math.max(1, altura));
      ctrl.arrastavel.posicionar(
        lerNumero(campo(ctrl.ps, "x").value, 0.75) * sw,
        lerNumero(campo(ctrl.ps, "y").value, 0.35) * sh,
        largura,
        altura,
        true
      );
      ajustarCorpo(ctrl.caixa);
    });
  }

  window.CV.pdfPlace.visualizador({
    url: form.dataset.pdfUrl,
    workerSrc: form.dataset.workerSrc,
    canvas: canvas,
    stage: stage,
    viewer: viewer,
    pageLabel: document.getElementById("carimbo-page-label"),
    btnPrev: document.getElementById("carimbo-prev"),
    btnNext: document.getElementById("carimbo-next"),
    onPagina: function (indice) {
      paginaAtual = indice;
      posicionarTodas();
    },
    onErro: function () {
      if (hint) {
        hint.textContent =
          "Não foi possível carregar o ofício. Recarregue a página.";
      }
    },
  });

  /* "Ir para a caixa" traz o número para a página que está aberta.
   *
   * Sem isto, um número que ficou na página 3 é invisível e o operador não tem como
   * saber que ele existe — some da tela e nada explica por quê.
   */
  controles.forEach(function (ctrl) {
    var botao = document.getElementById("ir-" + ctrl.ps);
    if (!botao) return;
    botao.addEventListener("click", function (evento) {
      evento.preventDefault();
      ctrl.caixa.dataset.pagina = String(paginaAtual);
      campo(ctrl.ps, "pagina").value = String(paginaAtual);
      posicionarTodas();
      ctrl.caixa.classList.add("pdf-place__box--ativa");
    });
  });
}());
