/**
 * "Gerar documentos" da viagem (m064): o contador de equipe ao vivo.
 *
 * Soma, sem repetir ninguém, quem já está nos ofícios da viagem
 * (`data-ja-em-oficios`), quem foi escolhido nas equipes desta tela e os
 * motoristas (que entram na equipe do seu ofício), e compara com a meta da
 * DG (`data-meta`). Sem JS a tela funciona igual: o texto só não se atualiza.
 */
(function () {
  "use strict";

  var form = document.querySelector("[data-gerar-documentos]");
  if (!form) return;
  var saida = form.querySelector("[data-gerar-contador]");
  var meta = parseInt(form.getAttribute("data-meta") || "0", 10) || 0;
  var existentes = (form.getAttribute("data-ja-em-oficios") || "").split(",").filter(Boolean);

  function plural(n, um, varios) { return n === 1 ? um : varios; }

  function atualizar() {
    var todos = {};
    existentes.forEach(function (pk) { todos[pk] = true; });
    var novos = {};
    form.querySelectorAll('input[type="checkbox"][name$="-servidores"]:checked').forEach(function (c) { novos[c.value] = true; });
    form.querySelectorAll('input[name$="-motorista"]:checked').forEach(function (s) { if (s.value) novos[s.value] = true; });
    Object.keys(novos).forEach(function (pk) { todos[pk] = true; });
    var total = Object.keys(todos).length;
    var aqui = Object.keys(novos).filter(function (pk) { return existentes.indexOf(pk) === -1; }).length;
    var texto = total + " " + plural(total, "servidor", "servidores") + " na viagem (" + aqui + " nesta tela)";
    if (meta) {
      var faltam = Math.max(meta - total, 0);
      texto += faltam
        ? " — faltam " + faltam + " para os " + meta + " designados pela DG."
        : " — a meta de " + meta + " designados pela DG está batida.";
      saida.classList.toggle("vg-gerar__contador--falta", faltam > 0);
    } else {
      texto += ". A DG não fixou quantidade.";
    }
    saida.textContent = texto;
  }

  // Viaturas de cada ofício: as sugeridas sobem para o topo da lista, com o
  // chip do porquê ("Unidade ASCOM" da equipe/motorista, "Motorista: FULANO").
  function nomeDaLinha(linha) {
    var nome = linha && linha.querySelector(".of-pessoa__nome");
    if (!nome) return "";
    var texto = "";
    nome.childNodes.forEach(function (n) { if (n.nodeType === 3) texto += n.textContent; });
    return (texto || nome.textContent).trim();
  }

  function chip(texto) {
    var c = document.createElement("span");
    c.className = "st st--atendido lista-escolha__chip";
    c.setAttribute("data-gerar-sugestao", "");
    c.textContent = texto;
    return c;
  }

  var ordens = {};
  function sugerirViaturas(bloco) {
    var lista = bloco.querySelector('[data-lista-escolha$="-viatura"]');
    if (!lista) return;
    var chave = lista.getAttribute("data-lista-escolha");
    if (!ordens[chave]) ordens[chave] = Array.prototype.slice.call(lista.querySelectorAll("[data-lista-item]"));
    var unidades = {};
    bloco.querySelectorAll('input[name$="-servidores"]:checked').forEach(function (c) {
      var l = c.closest("[data-lista-item]");
      if (l && l.getAttribute("data-unidade")) unidades[l.getAttribute("data-unidade")] = true;
    });
    var marcado = bloco.querySelector('input[name$="-motorista"]:checked');
    var linhaMotorista = marcado && marcado.closest("[data-lista-item]");
    if (linhaMotorista && linhaMotorista.getAttribute("data-unidade")) unidades[linhaMotorista.getAttribute("data-unidade")] = true;
    var nomeMotorista = nomeDaLinha(linhaMotorista);
    var sugeridas = [], demais = [];
    ordens[chave].forEach(function (l) {
      l.querySelectorAll("[data-gerar-sugestao]").forEach(function (c) { c.remove(); });
      var chips = [];
      if (unidades[l.getAttribute("data-unidade")]) chips.push("Unidade " + (l.getAttribute("data-sigla") || "da equipe"));
      if (marcado && (l.getAttribute("data-motoristas") || "").split(" ").indexOf(marcado.value) !== -1) {
        chips.push("Motorista: " + (nomeMotorista || "escolhido"));
      }
      var nome = l.querySelector(".of-pessoa__nome");
      if (nome) chips.forEach(function (t) { nome.appendChild(chip(t)); });
      (chips.length || l.querySelector(".lista-escolha__chip") ? sugeridas : demais).push(l);
    });
    sugeridas.concat(demais).forEach(function (l) { l.parentNode.appendChild(l); });
  }

  function sugerirTodas() {
    form.querySelectorAll("[data-gerar-oficio]").forEach(sugerirViaturas);
  }

  form.addEventListener("change", function (evento) {
    atualizar();
    var bloco = evento.target.closest("[data-gerar-oficio]");
    if (bloco && !/-viatura$/.test(evento.target.name || "")) sugerirViaturas(bloco);
  });
  atualizar();
  sugerirTodas();
})();
