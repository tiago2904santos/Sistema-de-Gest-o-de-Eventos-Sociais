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

// A busca não deve enviar ao perder foco: Enter e Buscar continuam enviando.
(function () {
  "use strict";
  document.querySelectorAll('.v32-barra[data-auto-enviar] input[type="search"]').forEach(function (campo) {
    campo.addEventListener("change", function (evento) { evento.stopPropagation(); });
  });
})();

// Seletor múltiplo: mantém select/name/valores do Django e seleção com Ctrl,
// Shift e teclado, expondo o mesmo menu de opções no vocabulário V3.2.
(function () {
  "use strict";
  document.querySelectorAll("[data-v32-multiple]").forEach(function (wrapper) {
    var native = wrapper.querySelector("select");
    var trigger = wrapper.querySelector("[data-multiple-trigger]");
    var menu = wrapper.querySelector("[data-multiple-menu]");
    var items = [].slice.call(wrapper.querySelectorAll("[data-multiple-option]"));
    var search = wrapper.querySelector("[data-multiple-search]");
    var anchor = 0;
    if (!native || !trigger || !menu) return;
    function update() {
      var labels = [];
      items.forEach(function (item, index) {
        var selected = native.options[index].selected;
        item.setAttribute("aria-selected", String(selected));
        item.classList.toggle("is-selected", selected);
        if (selected) labels.push(native.options[index].text);
      });
      wrapper.querySelector("[data-multiple-value]").textContent = labels.length ? labels.join(", ") : "Selecione...";
      trigger.classList.toggle("has-value", !!labels.length);
    }
    function close() {
      menu.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
      wrapper.classList.remove("is-open");
    }
    function choose(index, event) {
      if (native.disabled) return;
      var toggle = event.ctrlKey || event.metaKey || event.pointerType === "touch";
      if (event.shiftKey) {
        [].forEach.call(native.options, function (option, i) {
          if (!toggle) option.selected = false;
          if (i >= Math.min(anchor, index) && i <= Math.max(anchor, index)) option.selected = true;
        });
      } else {
        var selected = native.options[index].selected;
        if (!toggle) [].forEach.call(native.options, function (option) { option.selected = false; });
        native.options[index].selected = toggle ? !selected : true;
        anchor = index;
      }
      native.dispatchEvent(new Event("change", { bubbles: true }));
    }
    trigger.addEventListener("click", function () {
      if (!menu.hidden) { close(); return; }
      menu.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      wrapper.classList.add("is-open");
      var first = items.find(function (item) { return item.getAttribute("aria-selected") === "true"; }) || items[0];
      if (first) first.focus();
    });
    if (search) {
      search.addEventListener("input", function () {
        var term = search.value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
        items.forEach(function (item) {
          item.hidden = !item.textContent.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().includes(term);
        });
      });
      search.addEventListener("change", function (event) { event.stopPropagation(); });
      search.addEventListener("keydown", function (event) {
        if (event.key === "Enter") event.preventDefault();
        if (event.key === "ArrowDown") {
          event.preventDefault();
          var firstVisible = items.find(function (item) { return !item.hidden; });
          if (firstVisible) firstVisible.focus();
        }
      });
    }
    items.forEach(function (item, index) {
      item.addEventListener("click", function (event) { choose(index, event); });
      item.addEventListener("keydown", function (event) {
        var next;
        if (event.key === "ArrowDown") next = Math.min(items.length - 1, index + 1);
        if (event.key === "ArrowUp") next = Math.max(0, index - 1);
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = items.length - 1;
        if (next !== undefined) {
          var direction = next >= index ? 1 : -1;
          while (items[next] && items[next].hidden) next += direction;
          if (!items[next]) return;
          event.preventDefault(); items[next].focus();
          if (!(event.ctrlKey || event.metaKey) || event.shiftKey) choose(next, event);
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
          event.preventDefault();
          [].forEach.call(native.options, function (option) { option.selected = true; });
          native.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
    });
    wrapper.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { close(); trigger.focus(); }
      if (event.key === "Tab") close();
    });
    document.addEventListener("click", function (event) { if (!wrapper.contains(event.target)) close(); });
    native.addEventListener("change", update);
    if (native.form) native.form.addEventListener("reset", function () { window.setTimeout(update, 0); });
    wrapper.classList.add("is-enhanced");
    native.tabIndex = -1;
    update();
  });
})();

// Coffee Break: saldo informativo do lote, sem alterar a validação no servidor.
// Mostra o saldo do lote escolhido ao lado da quantidade — os dados vêm
    // renderizados no atributo data-saldos; a validação real é no backend.
    (function () {
      var campoSaldo = document.querySelector("[data-saldo-lote]");
      var seletorLote = document.getElementById("id_lote");
      if (!campoSaldo || !seletorLote) return;
      var saldos = {};
      (campoSaldo.dataset.saldos || "").split(";").forEach(function (par) {
        var partes = par.split(":");
        if (partes.length === 2) saldos[partes[0]] = partes[1];
      });
      function atualizar() {
        var info = saldos[seletorLote.value];
        campoSaldo.value = info
          ? info.split("/")[0] + " de " + info.split("/")[1] + " unidades"
          : "—";
      }
      seletorLote.addEventListener("change", atualizar);
      atualizar();
    })();

// Demandas ASCOM: opções de responsável conforme os setores, preservadas.
(function () {
      var responsavel = document.getElementById("id_responsavel_atendimento");
      var setores = document.querySelectorAll('input[name="setores"]');
      if (!responsavel || !setores.length) return;
      var custom = responsavel.closest("[data-custom-select]");
      function atualizarResponsaveis() {
        var ativos = Array.prototype.filter.call(setores, function (item) {
          return item.checked;
        }).map(function (item) { return item.value; });
        responsavel.querySelectorAll("option[data-related-values]").forEach(function (opcao) {
          var relacionados = (opcao.getAttribute("data-related-values") || "").split(",");
          var elegivel = relacionados.some(function (id) { return ativos.indexOf(id) !== -1; });
          opcao.disabled = !elegivel;
          opcao.hidden = !elegivel;
          if (!elegivel && opcao.selected) responsavel.value = "";
        });
        if (custom) {
          custom.querySelectorAll("[data-related-values][data-value]").forEach(function (opcao) {
            var relacionados = (opcao.getAttribute("data-related-values") || "").split(",");
            opcao.hidden = !relacionados.some(function (id) { return ativos.indexOf(id) !== -1; });
          });
        }
        responsavel.dispatchEvent(new Event("change", { bubbles: true }));
      }
      setores.forEach(function (setor) { setor.addEventListener("change", atualizarResponsaveis); });
      atualizarResponsaveis();
    })();
