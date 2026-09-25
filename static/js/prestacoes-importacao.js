/* Prestações — conferência da importação do processo (pages/viagens_prestacoes/importacao.html).

   - Miniatura da 1ª página de cada documento, pelo pdf.js vendorizado
     (static/vendor/pdfjs), já com o /Rotate que vai ser gravado: o que se vê é
     o que entra na prestação.
   - ↺ ↻ (`[data-imp-girar]`) somam ±90° ao giro do documento (campo oculto
     `doc-N-giro`) e redesenham a miniatura.
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
})();
