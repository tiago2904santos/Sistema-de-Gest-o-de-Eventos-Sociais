/* Prestações — revisar o pacote final página por página (m099).
   (pages/viagens_prestacoes/pacote_revisar.html)

   O servidor manda o pacote na ordem oficial (`data-pdf-url`) e o estado de
   partida (`#pacote-estado`): os documentos, com a página em que cada um começa
   no PDF, e a lista de páginas [documento, página, giro, oculta] na ordem do
   ajuste gravado (ou na oficial). A tela desenha uma miniatura por página com o
   pdf.js vendorizado; arrastar (ou ‹ ›) muda a ordem, ↻ soma 90° ao giro e
   "Ocultar" tira a página do pacote. O campo oculto `paginas` leva a lista ao
   salvar — é o servidor quem confere e aplica (services.validar_ajuste_do_pacote). */
(function () {
  "use strict";

  var form = document.querySelector("[data-pacote-revisar]");
  var fonte = document.getElementById("pacote-estado");
  if (!form || !fonte) return;
  var grade = form.querySelector("[data-pacote-grade]");
  var campo = form.querySelector("[data-pacote-paginas]");
  var estado = JSON.parse(fonte.textContent);
  var documentos = {};
  estado.documentos.forEach(function (d) { documentos[d.parte] = d; });
  var paginas = estado.paginas.map(function (p) { return {parte: p[0], pagina: p[1], giro: p[2] || 0, oculta: !!p[3]}; });

  var pdf = null;
  if (typeof pdfjsLib !== "undefined") {
    pdfjsLib.GlobalWorkerOptions.workerSrc = form.getAttribute("data-worker-src");
    pdf = pdfjsLib.getDocument({url: form.getAttribute("data-pdf-url"), withCredentials: true}).promise;
  }

  function gravar() {
    campo.value = JSON.stringify(paginas.map(function (p) { return [p.parte, p.pagina, p.giro, p.oculta]; }));
  }

  function desenhar(item) {
    var canvas = item.figura.querySelector("canvas");
    if (!pdf) return Promise.resolve();
    if (canvas._tarefa) canvas._tarefa.cancel();
    return pdf.then(function (documento) {
      return documento.getPage(documentos[item.parte].inicio + item.pagina + 1);
    }).then(function (pag) {
      var rotacao = ((pag.rotate || 0) + item.giro) % 360;
      var largura = 132;
      var base = pag.getViewport({scale: 1, rotation: rotacao});
      var densidade = window.devicePixelRatio || 1;
      var vista = pag.getViewport({scale: (largura / base.width) * densidade, rotation: rotacao});
      canvas.width = Math.floor(vista.width);
      canvas.height = Math.floor(vista.height);
      canvas.style.width = largura + "px";
      canvas.style.height = Math.floor(vista.height / densidade) + "px";
      canvas._tarefa = pag.render({canvasContext: canvas.getContext("2d"), viewport: vista});
      return canvas._tarefa.promise;
    }).catch(function (erro) {
      if (erro && erro.name === "RenderingCancelledException") return;
      item.figura.classList.add("pc-pacote__pag--falhou");
    });
  }

  function botao(texto, rotulo, acao) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "pc-pacote__btn";
    b.textContent = texto;
    b.setAttribute("aria-label", rotulo);
    b.title = rotulo;
    b.setAttribute("data-acao", acao);
    return b;
  }

  // Uma figura por página, criada uma vez; reordenar só move os nós.
  paginas.forEach(function (item) {
    var figura = document.createElement("figure");
    figura.className = "pc-pacote__pag";
    figura.draggable = true;
    var legenda = document.createElement("figcaption");
    legenda.textContent = documentos[item.parte].rotulo + " · p. " + (item.pagina + 1);
    var acoes = document.createElement("div");
    acoes.className = "pc-pacote__acoes";
    acoes.appendChild(botao("‹", "Mover para antes", "antes"));
    acoes.appendChild(botao("↻", "Girar 90°", "girar"));
    acoes.appendChild(botao("Ocultar", "Ocultar do pacote", "ocultar"));
    acoes.appendChild(botao("›", "Mover para depois", "depois"));
    figura.appendChild(document.createElement("canvas"));
    figura.appendChild(legenda);
    figura.appendChild(acoes);
    figura._item = item;
    item.figura = figura;
  });

  function montar() {
    grade.textContent = "";
    var anterior = null;
    paginas.forEach(function (item, i) {
      if (item.parte !== anterior) {
        var titulo = document.createElement("div");
        titulo.className = "pc-pacote__doc";
        titulo.textContent = documentos[item.parte].rotulo;
        grade.appendChild(titulo);
        anterior = item.parte;
      }
      item.figura.classList.toggle("is-oculta", item.oculta);
      var ocultar = item.figura.querySelector('[data-acao="ocultar"]');
      ocultar.textContent = item.oculta ? "Mostrar" : "Ocultar";
      ocultar.setAttribute("aria-pressed", item.oculta ? "true" : "false");
      item.figura.querySelector('[data-acao="antes"]').disabled = i === 0;
      item.figura.querySelector('[data-acao="depois"]').disabled = i === paginas.length - 1;
      item.figura.setAttribute("aria-label", "Página " + (i + 1) + " do pacote" + (item.oculta ? " (oculta)" : ""));
      grade.appendChild(item.figura);
    });
    gravar();
  }

  function mover(de, para) {
    if (para < 0 || para >= paginas.length || de === para) return;
    var item = paginas.splice(de, 1)[0];
    paginas.splice(para, 0, item);
    montar();
    item.figura.querySelector("button").focus();
  }

  grade.addEventListener("click", function (evento) {
    var b = evento.target.closest("[data-acao]");
    if (!b) return;
    var item = b.closest(".pc-pacote__pag")._item;
    var i = paginas.indexOf(item);
    var acao = b.getAttribute("data-acao");
    if (acao === "antes") mover(i, i - 1);
    else if (acao === "depois") mover(i, i + 1);
    else if (acao === "girar") { item.giro = (item.giro + 90) % 360; desenhar(item); gravar(); }
    else if (acao === "ocultar") { item.oculta = !item.oculta; montar(); }
  });

  var arrastado = null;
  grade.addEventListener("dragstart", function (evento) {
    var figura = evento.target.closest && evento.target.closest(".pc-pacote__pag");
    if (!figura) return;
    arrastado = figura._item;
    figura.classList.add("is-arrastando");
    evento.dataTransfer.effectAllowed = "move";
    try { evento.dataTransfer.setData("text/plain", ""); } catch (e) { /* Firefox exige algum dado */ }
  });
  grade.addEventListener("dragover", function (evento) {
    if (arrastado) evento.preventDefault();
  });
  grade.addEventListener("drop", function (evento) {
    var figura = evento.target.closest && evento.target.closest(".pc-pacote__pag");
    if (!arrastado || !figura) return;
    evento.preventDefault();
    mover(paginas.indexOf(arrastado), paginas.indexOf(figura._item));
  });
  grade.addEventListener("dragend", function () {
    if (arrastado) arrastado.figura.classList.remove("is-arrastando");
    arrastado = null;
  });

  montar();
  // Uma miniatura de cada vez: o pacote pode ter dezenas de páginas.
  var fila = Promise.resolve();
  paginas.forEach(function (item) { fila = fila.then(function () { return desenhar(item); }); });
})();
