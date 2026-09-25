/* Prestações — conferência da importação do processo (pages/viagens_prestacoes/importacao.html).

   - Miniatura da 1ª página de cada documento, pelo pdf.js vendorizado
     (static/vendor/pdfjs), já com o /Rotate que vai ser gravado: o que se vê é
     o que entra na prestação.
   - ↺ ↻ (`[data-imp-girar]`) somam ±90° ao giro do documento (campo oculto
     `doc-N-giro`) e redesenham a miniatura.
   - Clique na miniatura (`[data-imp-ampliar]`): abre o visualizador grande
     (`[data-imp-zoom]`) com todas as páginas do documento, zoom + −, e ‹ ›
     entre as páginas — no giro que vai ser gravado — para conferir se é o
     tipo e a prestação certos.
   - O destino escolhido mostra só os campos dele (`[data-imp-quando]`):
     servidor para RT e comprovante; valor, data e operação para comprovante. */
(function () {
  "use strict";

  var raiz = document.querySelector("[data-importacao]");
  if (!raiz) return;

  function giroDe(doc) {
    var campo = doc.querySelector("[data-imp-giro]");
    return campo ? (parseInt(campo.value || "0", 10) || 0) : 0;
  }

  /* ---------- campos conforme o destino ---------- */
  function mostrarCampos(doc) {
    var select = doc.querySelector("[data-imp-destino] select");
    if (!select) return;
    doc.querySelectorAll("[data-imp-quando]").forEach(function (campo) {
      var quando = (campo.getAttribute("data-imp-quando") || "").split(" ");
      campo.hidden = quando.indexOf(select.value) === -1;
    });
    doc.classList.toggle("pc-imp__doc--fora", select.value === "ignorar");
  }

  raiz.querySelectorAll("[data-imp-doc]").forEach(function (doc) {
    var select = doc.querySelector("[data-imp-destino] select");
    if (select) select.addEventListener("change", function () { mostrarCampos(doc); });
    mostrarCampos(doc);
  });

  /* ---------- miniaturas ---------- */
  var pdf = null;
  if (typeof pdfjsLib !== "undefined") {
    pdfjsLib.GlobalWorkerOptions.workerSrc = raiz.getAttribute("data-worker-src");
    pdf = pdfjsLib.getDocument({ url: raiz.getAttribute("data-pdf-url"), withCredentials: true }).promise;
  }

  function desenhar(doc) {
    var canvas = doc.querySelector("[data-imp-canvas]");
    if (!canvas || !pdf) return Promise.resolve();
    var pagina = parseInt(canvas.getAttribute("data-pagina") || "0", 10);
    var rotacao = (((parseInt(canvas.getAttribute("data-rotacao") || "0", 10) + giroDe(doc)) % 360) + 360) % 360;
    if (canvas._tarefa) canvas._tarefa.cancel();
    return pdf.then(function (documento) {
      return documento.getPage(pagina + 1);
    }).then(function (pag) {
      var largura = canvas.parentElement ? Math.max(96, Math.min(canvas.parentElement.clientWidth || 132, 180)) : 132;
      var base = pag.getViewport({ scale: 1, rotation: rotacao });
      var densidade = window.devicePixelRatio || 1;
      var vista = pag.getViewport({ scale: (largura / base.width) * densidade, rotation: rotacao });
      canvas.width = Math.floor(vista.width);
      canvas.height = Math.floor(vista.height);
      canvas.style.width = largura + "px";
      canvas.style.height = Math.floor(vista.height / densidade) + "px";
      canvas._tarefa = pag.render({ canvasContext: canvas.getContext("2d"), viewport: vista });
      return canvas._tarefa.promise;
    }).catch(function (erro) {
      if (erro && erro.name === "RenderingCancelledException") return;
      canvas.classList.add("pc-imp__mini--falhou");
    });
  }

  // Uma de cada vez, na ordem: o processo pode ter dezenas de documentos.
  var fila = Promise.resolve();
  raiz.querySelectorAll("[data-imp-doc]").forEach(function (doc) {
    fila = fila.then(function () { return desenhar(doc); });
  });

  raiz.addEventListener("click", function (evento) {
    var botao = evento.target.closest && evento.target.closest("[data-imp-girar]");
    if (!botao) return;
    var doc = botao.closest("[data-imp-doc]");
    var campo = doc && doc.querySelector("[data-imp-giro]");
    if (!campo || campo.disabled) return;
    var passo = parseInt(botao.getAttribute("data-imp-girar"), 10) || 0;
    campo.value = String((((giroDe(doc) + passo) % 360) + 360) % 360);
    doc.classList.add("pc-imp__doc--girado");
    desenhar(doc);
  });

  /* ---------- visualizador ampliado ---------- */
  var zoom = document.querySelector("[data-imp-zoom]");
  if (zoom && typeof zoom.showModal === "function") {
    var zCanvas = zoom.querySelector("[data-imp-zoom-canvas]");
    var zArea = zoom.querySelector("[data-imp-zoom-area]");
    var zTitulo = zoom.querySelector("[data-imp-zoom-titulo]");
    var zPagina = zoom.querySelector("[data-imp-zoom-pagina]");
    var zEscala = zoom.querySelector("[data-imp-zoom-escala-rotulo]");
    var estado = { doc: null, paginas: [], i: 0, fator: 1 };
    var FATORES = [0.5, 0.75, 1, 1.5, 2, 3, 4];

    function desenharAmpliado() {
      if (!pdf || !estado.doc) return;
      var pagina = estado.paginas[estado.i];
      var canvasMini = estado.doc.querySelector("[data-imp-canvas]");
      var base = parseInt((canvasMini && canvasMini.getAttribute("data-rotacao")) || "0", 10);
      var rotacao = (((base + giroDe(estado.doc)) % 360) + 360) % 360;
      zPagina.textContent = estado.paginas.length > 1 ? "Página " + (estado.i + 1) + " de " + estado.paginas.length : "";
      zEscala.textContent = Math.round(estado.fator * 100) + "%";
      zoom.querySelectorAll("[data-imp-zoom-ir]").forEach(function (b) {
        var passo = parseInt(b.getAttribute("data-imp-zoom-ir"), 10);
        b.disabled = estado.i + passo < 0 || estado.i + passo >= estado.paginas.length;
        b.hidden = estado.paginas.length < 2;
      });
      if (zCanvas._tarefa) zCanvas._tarefa.cancel();
      pdf.then(function (documento) {
        return documento.getPage(pagina + 1);
      }).then(function (pag) {
        var visual = pag.getViewport({ scale: 1, rotation: rotacao });
        var cabe = Math.max(320, (zArea.clientWidth || window.innerWidth) - 32) / visual.width;
        var escala = cabe * estado.fator;
        var densidade = window.devicePixelRatio || 1;
        var vista = pag.getViewport({ scale: escala * densidade, rotation: rotacao });
        zCanvas.width = Math.floor(vista.width);
        zCanvas.height = Math.floor(vista.height);
        zCanvas.style.width = Math.floor(vista.width / densidade) + "px";
        zCanvas.style.height = Math.floor(vista.height / densidade) + "px";
        zCanvas._tarefa = pag.render({ canvasContext: zCanvas.getContext("2d"), viewport: vista });
        return zCanvas._tarefa.promise;
      }).catch(function (erro) {
        if (erro && erro.name === "RenderingCancelledException") return;
      });
    }

    raiz.addEventListener("click", function (evento) {
      var botao = evento.target.closest && evento.target.closest("[data-imp-ampliar]");
      if (!botao) return;
      estado.doc = botao.closest("[data-imp-doc]");
      estado.paginas = (botao.getAttribute("data-paginas") || "0").split(",").map(function (n) { return parseInt(n, 10) || 0; });
      estado.i = 0;
      estado.fator = 1;
      zTitulo.textContent = botao.getAttribute("data-titulo") || "";
      zoom.showModal();
      zArea.scrollTop = 0;
      desenharAmpliado();
    });

    zoom.addEventListener("click", function (evento) {
      if (evento.target === zoom) { zoom.close(); return; }
      var alvo = evento.target.closest && evento.target.closest("button");
      if (!alvo) return;
      if (alvo.hasAttribute("data-imp-zoom-fechar")) { zoom.close(); return; }
      if (alvo.hasAttribute("data-imp-zoom-ir")) {
        estado.i = Math.max(0, Math.min(estado.paginas.length - 1, estado.i + parseInt(alvo.getAttribute("data-imp-zoom-ir"), 10)));
        zArea.scrollTop = 0;
        desenharAmpliado();
      }
      if (alvo.hasAttribute("data-imp-zoom-escala")) {
        var atual = FATORES.indexOf(estado.fator);
        var prox = Math.max(0, Math.min(FATORES.length - 1, atual + parseInt(alvo.getAttribute("data-imp-zoom-escala"), 10)));
        estado.fator = FATORES[prox];
        desenharAmpliado();
      }
    });

    zoom.addEventListener("keydown", function (evento) {
      var mapa = { "+": ["escala", 1], "=": ["escala", 1], "-": ["escala", -1], "ArrowRight": ["ir", 1], "ArrowLeft": ["ir", -1] };
      var acao = mapa[evento.key];
      if (!acao) return;
      var botao = zoom.querySelector("[data-imp-zoom-" + acao[0] + '="' + acao[1] + '"]');
      if (botao && !botao.disabled) { evento.preventDefault(); botao.click(); }
    });
  }
})();
