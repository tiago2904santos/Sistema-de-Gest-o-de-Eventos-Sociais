/**
 * Comportamentos próprios das páginas no Design System V3.2.
 * Complementa o app.js (menus, filtros, validação, anexos) sem substituí-lo.
 */
(function () {
  "use strict";

  // Stepper numérico das equipes: − / + ajustam o input e avisam o formulário
  // (o resumo lateral e a validação escutam "input").
  document.querySelectorAll("[data-stepper]").forEach(function (stepper) {
    var input = stepper.querySelector("input");
    var menos = stepper.querySelector("[data-stepper-menos]");
    var mais = stepper.querySelector("[data-stepper-mais]");
    if (!input || !menos || !mais) return;

    function definir(valor) {
      if (input.disabled) return;
      var minimo = Number(input.min || 0);
      input.value = Math.max(minimo, valor);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    menos.addEventListener("click", function () { definir((Number(input.value) || 0) - 1); });
    mais.addEventListener("click", function () { definir((Number(input.value) || 0) + 1); });
  });

  // Etapas da lateral rolam até a seção correspondente.
  document.querySelectorAll("[data-ir]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      var alvo = document.querySelector(botao.getAttribute("data-ir"));
      if (alvo) alvo.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  // O formulário de filtros envia a cada "change". O campo de busca do combobox
  // dispara change ao perder o foco, o que enviaria a lista no meio da escolha:
  // o evento dele para aqui. Quem envia é o change do <select> por trás.
  document.querySelectorAll("form[data-auto-enviar] [data-custom-select-search]").forEach(function (busca) {
    busca.addEventListener("change", function (evento) { evento.stopPropagation(); });
  });

  // Lateral flutuante: gruda na janela enquanto a página rola, mas só quando
  // cabe inteira — nunca ganha barra de rolagem própria nem esconde o fim.
  // Fora disso (janela baixa ou layout empilhado) volta a rolar com a página.
  var laterais = [].slice.call(document.querySelectorAll(".sticky"));
  function ajustarLaterais() {
    laterais.forEach(function (lateral) {
      var pai = lateral.parentElement;
      lateral.classList.add("pode-flutuar");
      var empilhada = pai && lateral.offsetWidth > pai.offsetWidth * 0.7;
      var alta = lateral.offsetHeight + 40 > window.innerHeight;
      if (empilhada || alta) lateral.classList.remove("pode-flutuar");
    });
  }
  if (laterais.length) {
    ajustarLaterais();
    var pendente;
    window.addEventListener("resize", function () {
      window.clearTimeout(pendente);
      pendente = window.setTimeout(ajustarLaterais, 150);
    });
    // O conteúdo muda de altura (anexos, erros, etapas): remede quando isso ocorre.
    if (window.ResizeObserver) {
      var observador = new ResizeObserver(function () { ajustarLaterais(); });
      laterais.forEach(function (lateral) {
        [].slice.call(lateral.children).forEach(function (filho) { observador.observe(filho); });
      });
    }
  }

  // Bottom sheets (mobile): Filtros e Ordenar abrem sobre um véu; Escape,
  // o véu e o botão de fechar recolhem.
  var veu = document.querySelector(".m-veu");
  function fecharSheets() {
    document.querySelectorAll(".m-sheet").forEach(function (sheet) { sheet.hidden = true; });
    if (veu) veu.hidden = true;
    document.body.classList.remove("m-sheet-aberto");
    document.querySelectorAll("[data-abrir-sheet]").forEach(function (botao) { botao.setAttribute("aria-expanded", "false"); });
  }
  document.querySelectorAll("[data-abrir-sheet]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      var alvo = document.querySelector(botao.getAttribute("data-abrir-sheet"));
      if (!alvo) return;
      fecharSheets();
      alvo.hidden = false;
      if (veu) veu.hidden = false;
      document.body.classList.add("m-sheet-aberto");
      botao.setAttribute("aria-expanded", "true");
      var foco = alvo.querySelector("select, input, a, button");
      if (foco) foco.focus();
    });
  });
  document.querySelectorAll("[data-fechar-sheet]").forEach(function (el) { el.addEventListener("click", fecharSheets); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") fecharSheets(); });

  // Ao voltar de uma decisão com erro, a página abre já na seção do despacho.
  if (window.location.hash === "#despacho-dg") {
    var despacho = document.getElementById("despacho-dg");
    if (despacho) window.setTimeout(function () { despacho.scrollIntoView({ block: "start" }); }, 50);
  }
})();
