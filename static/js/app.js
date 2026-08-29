/**
 * JS leve do Sistema de Gestão de Eventos Sociais.
 * Sem frameworks — apenas melhorias progressivas.
 */
(function () {
  "use strict";

  // Fecha alertas automaticamente após 6 segundos.
  document.querySelectorAll(".alerta").forEach(function (alerta) {
    setTimeout(function () {
      alerta.style.transition = "opacity 0.4s ease";
      alerta.style.opacity = "0";
      setTimeout(function () {
        alerta.remove();
      }, 400);
    }, 6000);
  });

  var sidebarAcompanhamento = document.querySelector(".solicitacao-sidebar");
  var rodapeAplicacao = document.querySelector(".app-shell__footer");
  var ajusteSidebarPendente = false;
  var topoDocumentoSidebar = null;

  function medirPosicaoSidebar() {
    if (!sidebarAcompanhamento) return;
    var retangulo = sidebarAcompanhamento.getBoundingClientRect();
    topoDocumentoSidebar = retangulo.top + window.scrollY;
    sidebarAcompanhamento.style.setProperty("--sidebar-left", retangulo.left + "px");
    sidebarAcompanhamento.style.setProperty("--sidebar-width", retangulo.width + "px");
  }

  function ajustarAlturaSidebar() {
    ajusteSidebarPendente = false;
    if (!sidebarAcompanhamento) return;
    if (window.innerWidth <= 980) {
      sidebarAcompanhamento.classList.remove("is-stuck");
      sidebarAcompanhamento.style.removeProperty("--sidebar-footer-shift");
      topoDocumentoSidebar = null;
      return;
    }
    if (topoDocumentoSidebar === null) medirPosicaoSidebar();
    var encostouNoTopo = window.scrollY >= topoDocumentoSidebar - 14;
    sidebarAcompanhamento.classList.toggle("is-stuck", encostouNoTopo);
    var deslocamentoRodape = 0;
    if (encostouNoTopo && rodapeAplicacao) {
      var topoRodape = rodapeAplicacao.getBoundingClientRect().top;
      var baseSidebar = 14 + sidebarAcompanhamento.offsetHeight;
      deslocamentoRodape = Math.min(0, topoRodape - 10 - baseSidebar);
    }
    sidebarAcompanhamento.style.setProperty("--sidebar-footer-shift", deslocamentoRodape + "px");
  }

  function agendarAjusteSidebar() {
    if (ajusteSidebarPendente) return;
    ajusteSidebarPendente = true;
    window.requestAnimationFrame(ajustarAlturaSidebar);
  }

  if (sidebarAcompanhamento) {
    medirPosicaoSidebar();
    ajustarAlturaSidebar();
    window.addEventListener("scroll", agendarAjusteSidebar, { passive: true });
    window.addEventListener("resize", function () {
      sidebarAcompanhamento.classList.remove("is-stuck");
      sidebarAcompanhamento.style.removeProperty("--sidebar-footer-shift");
      topoDocumentoSidebar = null;
      agendarAjusteSidebar();
    });
  }

  var seletoresAbertos = [];
  var calendariosAbertos = [];

  function fecharSeletor(instancia, devolverFoco) {
    if (!instancia || !instancia.aberto) return;
    instancia.aberto = false;
    instancia.wrapper.classList.remove("is-open");
    instancia.menu.hidden = true;
    instancia.trigger.setAttribute("aria-expanded", "false");
    if (devolverFoco) instancia.trigger.focus();
  }

  function fecharOutrosSeletores(excecao) {
    seletoresAbertos.forEach(function (instancia) {
      if (instancia !== excecao) fecharSeletor(instancia, false);
    });
  }

  document.querySelectorAll("[data-custom-select]").forEach(function (wrapper) {
    var nativo = wrapper.querySelector(".custom-select__native");
    var trigger = wrapper.querySelector("[data-custom-select-trigger]");
    var valor = wrapper.querySelector(".custom-select__valor");
    var menu = wrapper.querySelector("[data-custom-select-menu]");
    var opcoes = Array.prototype.slice.call(wrapper.querySelectorAll(".custom-select__opcao"));
    if (!nativo || !trigger || !valor || !menu) return;

    var instancia = {
      wrapper: wrapper,
      nativo: nativo,
      trigger: trigger,
      menu: menu,
      opcoes: opcoes,
      aberto: false
    };
    seletoresAbertos.push(instancia);
    wrapper.classList.add("is-enhanced");
    nativo.tabIndex = -1;
    nativo.setAttribute("aria-hidden", "true");
    trigger.disabled = nativo.disabled;

    function opcaoAtual() {
      return nativo.options[nativo.selectedIndex];
    }

    function sincronizar() {
      var selecionada = opcaoAtual();
      valor.textContent = selecionada ? selecionada.text : "Selecione...";
      trigger.classList.toggle("has-value", Boolean(nativo.value));
      trigger.removeAttribute("aria-invalid");
      wrapper.classList.remove("is-invalid");
      opcoes.forEach(function (opcao) {
        var ativa = opcao.getAttribute("data-value") === nativo.value;
        opcao.setAttribute("aria-selected", ativa ? "true" : "false");
        opcao.classList.toggle("is-selected", ativa);
      });
    }

    function abrirSeletor() {
      if (instancia.aberto || nativo.disabled) return;
      fecharOutrosSeletores(instancia);
      fecharOutrosCalendarios(null);
      instancia.aberto = true;
      wrapper.classList.add("is-open");
      menu.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      var selecionada = opcoes.find(function (opcao) {
        return opcao.getAttribute("data-value") === nativo.value;
      });
      var destino = selecionada || opcoes[0];
      if (destino) destino.focus();
    }

    function selecionar(opcao) {
      nativo.value = opcao.getAttribute("data-value") || "";
      sincronizar();
      nativo.dispatchEvent(new Event("input", { bubbles: true }));
      nativo.dispatchEvent(new Event("change", { bubbles: true }));
      fecharSeletor(instancia, true);
    }

    function moverFoco(direcao) {
      if (!opcoes.length) return;
      var indice = opcoes.indexOf(document.activeElement);
      if (indice < 0) indice = 0;
      indice = (indice + direcao + opcoes.length) % opcoes.length;
      if (opcoes[indice]) opcoes[indice].focus();
    }

    trigger.addEventListener("click", function () {
      if (instancia.aberto) fecharSeletor(instancia, true);
      else abrirSeletor();
    });

    trigger.addEventListener("keydown", function (event) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].indexOf(event.key) !== -1) {
        event.preventDefault();
        abrirSeletor();
      }
    });

    opcoes.forEach(function (opcao) {
      opcao.addEventListener("click", function () { selecionar(opcao); });
      opcao.addEventListener("keydown", function (event) {
        if (event.key === "ArrowDown") { event.preventDefault(); moverFoco(1); }
        else if (event.key === "ArrowUp") { event.preventDefault(); moverFoco(-1); }
        else if (event.key === "Home") { event.preventDefault(); if (opcoes[0]) opcoes[0].focus(); }
        else if (event.key === "End") { event.preventDefault(); if (opcoes.length) opcoes[opcoes.length - 1].focus(); }
        else if (event.key === "Escape") { event.preventDefault(); fecharSeletor(instancia, true); }
        else if (event.key === "Tab") fecharSeletor(instancia, false);
      });
    });

    nativo.addEventListener("change", sincronizar);
    nativo.addEventListener("focus", function () { trigger.focus(); });
    nativo.addEventListener("invalid", function () {
      wrapper.classList.add("is-invalid");
      trigger.setAttribute("aria-invalid", "true");
      trigger.focus();
    });
    sincronizar();
  });

  function fecharCalendario(instancia, devolverFoco) {
    if (!instancia || !instancia.aberto) return;
    instancia.aberto = false;
    instancia.wrapper.classList.remove("is-open");
    instancia.calendario.hidden = true;
    instancia.trigger.setAttribute("aria-expanded", "false");
    if (devolverFoco) instancia.trigger.focus();
  }

  function fecharOutrosCalendarios(excecao) {
    calendariosAbertos.forEach(function (instancia) {
      if (instancia !== excecao) fecharCalendario(instancia, false);
    });
  }

  function dataPorIso(valor) {
    var partes = String(valor || "").split("-");
    if (partes.length !== 3) return null;
    var data = new Date(Number(partes[0]), Number(partes[1]) - 1, Number(partes[2]));
    return Number.isNaN(data.getTime()) ? null : data;
  }

  function isoDaData(data) {
    var ano = data.getFullYear();
    var mes = String(data.getMonth() + 1).padStart(2, "0");
    var dia = String(data.getDate()).padStart(2, "0");
    return ano + "-" + mes + "-" + dia;
  }

  function dataFormatada(data) {
    return new Intl.DateTimeFormat("pt-BR").format(data);
  }

  document.querySelectorAll("[data-custom-date]").forEach(function (wrapper) {
    var nativo = wrapper.querySelector(".custom-date__native");
    var trigger = wrapper.querySelector("[data-custom-date-trigger]");
    var valor = wrapper.querySelector(".custom-date__valor");
    var calendario = wrapper.querySelector("[data-custom-date-calendar]");
    var tituloMes = wrapper.querySelector("[data-custom-date-month]");
    var grade = wrapper.querySelector("[data-custom-date-grid]");
    var anterior = wrapper.querySelector("[data-custom-date-prev]");
    var proximo = wrapper.querySelector("[data-custom-date-next]");
    var limpar = wrapper.querySelector("[data-custom-date-clear]");
    var hojeBotao = wrapper.querySelector("[data-custom-date-today]");
    if (!nativo || !trigger || !valor || !calendario || !grade) return;

    var hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    var selecionadaInicial = dataPorIso(nativo.value);
    var mesVisivel = selecionadaInicial || hoje;
    mesVisivel = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth(), 1);

    var instancia = {
      wrapper: wrapper,
      trigger: trigger,
      calendario: calendario,
      aberto: false
    };
    calendariosAbertos.push(instancia);
    wrapper.classList.add("is-enhanced");
    nativo.tabIndex = -1;
    nativo.setAttribute("aria-hidden", "true");
    trigger.disabled = nativo.disabled || nativo.readOnly;

    function estaIndisponivel(iso) {
      return Boolean((nativo.min && iso < nativo.min) || (nativo.max && iso > nativo.max));
    }

    function focarData(iso) {
      var alvo = grade.querySelector('[data-date="' + iso + '"]');
      if (alvo && !alvo.disabled) alvo.focus();
    }

    function renderizar() {
      var nomeMes = new Intl.DateTimeFormat("pt-BR", {
        month: "long",
        year: "numeric"
      }).format(mesVisivel);
      tituloMes.textContent = nomeMes.charAt(0).toUpperCase() + nomeMes.slice(1);
      grade.innerHTML = "";

      var primeiroDia = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth(), 1);
      var inicioGrade = new Date(
        primeiroDia.getFullYear(),
        primeiroDia.getMonth(),
        1 - primeiroDia.getDay()
      );

      for (var indice = 0; indice < 42; indice += 1) {
        var data = new Date(
          inicioGrade.getFullYear(),
          inicioGrade.getMonth(),
          inicioGrade.getDate() + indice
        );
        var iso = isoDaData(data);
        var botao = document.createElement("button");
        botao.type = "button";
        botao.className = "custom-date__dia";
        botao.textContent = String(data.getDate());
        botao.setAttribute("role", "gridcell");
        botao.setAttribute("data-date", iso);
        botao.setAttribute("aria-label", new Intl.DateTimeFormat("pt-BR", {
          day: "numeric", month: "long", year: "numeric"
        }).format(data));
        botao.setAttribute("aria-selected", nativo.value === iso ? "true" : "false");
        botao.classList.toggle("is-outside", data.getMonth() !== mesVisivel.getMonth());
        botao.classList.toggle("is-today", iso === isoDaData(hoje));
        botao.classList.toggle("is-selected", nativo.value === iso);
        botao.disabled = estaIndisponivel(iso);
        grade.appendChild(botao);
      }
    }

    function sincronizar() {
      var data = dataPorIso(nativo.value);
      valor.textContent = data ? dataFormatada(data) : "dd/mm/aaaa";
      trigger.classList.toggle("has-value", Boolean(data));
      trigger.removeAttribute("aria-invalid");
      wrapper.classList.remove("is-invalid");
      if (data) mesVisivel = new Date(data.getFullYear(), data.getMonth(), 1);
      if (instancia.aberto) renderizar();
    }

    function selecionarData(data) {
      var iso = isoDaData(data);
      if (estaIndisponivel(iso)) return;
      nativo.value = iso;
      sincronizar();
      nativo.dispatchEvent(new Event("input", { bubbles: true }));
      nativo.dispatchEvent(new Event("change", { bubbles: true }));
      fecharCalendario(instancia, true);
    }

    function abrirCalendario() {
      if (instancia.aberto || nativo.disabled || nativo.readOnly) return;
      fecharOutrosSeletores(null);
      fecharOutrosCalendarios(instancia);
      instancia.aberto = true;
      wrapper.classList.add("is-open");
      calendario.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      renderizar();
      focarData(nativo.value || isoDaData(hoje));
    }

    function mudarMes(deslocamento) {
      mesVisivel = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth() + deslocamento, 1);
      renderizar();
      var diaPreferido = dataPorIso(nativo.value) || hoje;
      var ultimoDia = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth() + 1, 0).getDate();
      var destino = new Date(
        mesVisivel.getFullYear(),
        mesVisivel.getMonth(),
        Math.min(diaPreferido.getDate(), ultimoDia)
      );
      focarData(isoDaData(destino));
    }

    trigger.addEventListener("click", function () {
      if (instancia.aberto) fecharCalendario(instancia, true);
      else abrirCalendario();
    });
    trigger.addEventListener("keydown", function (event) {
      if (["ArrowDown", "Enter", " "].indexOf(event.key) !== -1) {
        event.preventDefault();
        abrirCalendario();
      }
    });
    anterior.addEventListener("click", function () { mudarMes(-1); });
    proximo.addEventListener("click", function () { mudarMes(1); });
    limpar.addEventListener("click", function () {
      nativo.value = "";
      sincronizar();
      nativo.dispatchEvent(new Event("input", { bubbles: true }));
      nativo.dispatchEvent(new Event("change", { bubbles: true }));
      fecharCalendario(instancia, true);
    });
    hojeBotao.addEventListener("click", function () { selecionarData(hoje); });
    grade.addEventListener("click", function (event) {
      var dia = event.target.closest("[data-date]");
      if (dia) selecionarData(dataPorIso(dia.getAttribute("data-date")));
    });
    grade.addEventListener("keydown", function (event) {
      var dia = event.target.closest("[data-date]");
      if (!dia) return;
      var atual = dataPorIso(dia.getAttribute("data-date"));
      var deslocamento = null;
      if (event.key === "ArrowLeft") deslocamento = -1;
      else if (event.key === "ArrowRight") deslocamento = 1;
      else if (event.key === "ArrowUp") deslocamento = -7;
      else if (event.key === "ArrowDown") deslocamento = 7;
      else if (event.key === "Home") deslocamento = -atual.getDay();
      else if (event.key === "End") deslocamento = 6 - atual.getDay();
      else if (event.key === "PageUp") { event.preventDefault(); mudarMes(-1); return; }
      else if (event.key === "PageDown") { event.preventDefault(); mudarMes(1); return; }
      else if (event.key === "Escape") { event.preventDefault(); fecharCalendario(instancia, true); return; }
      else if (event.key === "Tab") { fecharCalendario(instancia, false); return; }
      if (deslocamento === null) return;
      event.preventDefault();
      var destino = new Date(atual.getFullYear(), atual.getMonth(), atual.getDate() + deslocamento);
      if (destino.getMonth() !== mesVisivel.getMonth() || destino.getFullYear() !== mesVisivel.getFullYear()) {
        mesVisivel = new Date(destino.getFullYear(), destino.getMonth(), 1);
        renderizar();
      }
      focarData(isoDaData(destino));
    });

    nativo.addEventListener("change", sincronizar);
    nativo.addEventListener("focus", function () { trigger.focus(); });
    nativo.addEventListener("invalid", function () {
      wrapper.classList.add("is-invalid");
      trigger.setAttribute("aria-invalid", "true");
      trigger.focus();
    });
    sincronizar();
  });

  document.querySelectorAll("[data-custom-date-range]").forEach(function (wrapper) {
    var inicio = wrapper.querySelector("[data-custom-date-range-start]");
    var fim = wrapper.querySelector("[data-custom-date-range-end]");
    var trigger = wrapper.querySelector("[data-custom-date-range-trigger]");
    var valor = wrapper.querySelector(".custom-date__valor");
    var calendario = wrapper.querySelector("[data-custom-date-range-calendar]");
    var tituloMes = wrapper.querySelector("[data-custom-date-range-month]");
    var instrucao = wrapper.querySelector("[data-custom-date-range-hint]");
    var grade = wrapper.querySelector("[data-custom-date-range-grid]");
    var anterior = wrapper.querySelector("[data-custom-date-range-prev]");
    var proximo = wrapper.querySelector("[data-custom-date-range-next]");
    var limpar = wrapper.querySelector("[data-custom-date-range-clear]");
    var hojeBotao = wrapper.querySelector("[data-custom-date-range-today]");
    if (!inicio || !fim || !trigger || !valor || !calendario || !grade) return;

    var hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    var dataInicial = dataPorIso(inicio.value);
    var mesVisivel = dataInicial || hoje;
    mesVisivel = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth(), 1);

    var instancia = {
      wrapper: wrapper,
      trigger: trigger,
      calendario: calendario,
      aberto: false
    };
    calendariosAbertos.push(instancia);
    wrapper.classList.add("is-enhanced");
    inicio.tabIndex = -1;
    fim.tabIndex = -1;
    inicio.setAttribute("aria-hidden", "true");
    fim.setAttribute("aria-hidden", "true");
    trigger.disabled = inicio.disabled || fim.disabled || inicio.readOnly || fim.readOnly;

    function dataEstaIndisponivel(iso) {
      var minimo = inicio.min || fim.min;
      var maximo = fim.max || inicio.max;
      return Boolean((minimo && iso < minimo) || (maximo && iso > maximo));
    }

    function focarData(iso) {
      var alvo = grade.querySelector('[data-date="' + iso + '"]');
      if (alvo && !alvo.disabled) alvo.focus();
    }

    function renderizar() {
      var nomeMes = new Intl.DateTimeFormat("pt-BR", {
        month: "long",
        year: "numeric"
      }).format(mesVisivel);
      tituloMes.textContent = nomeMes.charAt(0).toUpperCase() + nomeMes.slice(1);
      instrucao.textContent = inicio.value && !fim.value
        ? "Agora selecione a data final"
        : "Selecione a data inicial";
      grade.innerHTML = "";

      var primeiroDia = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth(), 1);
      var inicioGrade = new Date(
        primeiroDia.getFullYear(),
        primeiroDia.getMonth(),
        1 - primeiroDia.getDay()
      );

      for (var indice = 0; indice < 42; indice += 1) {
        var data = new Date(
          inicioGrade.getFullYear(),
          inicioGrade.getMonth(),
          inicioGrade.getDate() + indice
        );
        var iso = isoDaData(data);
        var dentroDoIntervalo = Boolean(inicio.value && fim.value && iso > inicio.value && iso < fim.value);
        var botao = document.createElement("button");
        botao.type = "button";
        botao.className = "custom-date__dia";
        botao.textContent = String(data.getDate());
        botao.setAttribute("role", "gridcell");
        botao.setAttribute("data-date", iso);
        botao.setAttribute("aria-label", new Intl.DateTimeFormat("pt-BR", {
          day: "numeric", month: "long", year: "numeric"
        }).format(data));
        botao.setAttribute(
          "aria-selected",
          inicio.value === iso || fim.value === iso ? "true" : "false"
        );
        botao.classList.toggle("is-outside", data.getMonth() !== mesVisivel.getMonth());
        botao.classList.toggle("is-today", iso === isoDaData(hoje));
        botao.classList.toggle("is-in-range", dentroDoIntervalo);
        botao.classList.toggle("is-range-start", inicio.value === iso);
        botao.classList.toggle("is-range-end", fim.value === iso);
        botao.disabled = dataEstaIndisponivel(iso);
        grade.appendChild(botao);
      }
    }

    function dispararAlteracao(campo) {
      campo.dispatchEvent(new Event("input", { bubbles: true }));
      campo.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function sincronizar() {
      var dataInicio = dataPorIso(inicio.value);
      var dataFim = dataPorIso(fim.value);
      if (dataInicio && dataFim) {
        valor.textContent = dataFormatada(dataInicio) + " — " + dataFormatada(dataFim);
      } else if (dataInicio) {
        valor.textContent = dataFormatada(dataInicio) + " — selecione o fim";
      } else {
        valor.textContent = "dd/mm/aaaa — dd/mm/aaaa";
      }
      trigger.classList.toggle("has-value", Boolean(dataInicio));
      trigger.removeAttribute("aria-invalid");
      wrapper.classList.remove("is-invalid");
      if (dataInicio) mesVisivel = new Date(dataInicio.getFullYear(), dataInicio.getMonth(), 1);
      if (instancia.aberto) renderizar();
    }

    function selecionarData(data) {
      var iso = isoDaData(data);
      if (dataEstaIndisponivel(iso)) return;

      if (!inicio.value || fim.value) {
        inicio.value = iso;
        fim.value = "";
        sincronizar();
        dispararAlteracao(inicio);
        dispararAlteracao(fim);
        renderizar();
        focarData(iso);
        return;
      }

      if (iso < inicio.value) {
        inicio.value = iso;
        fim.value = "";
        sincronizar();
        dispararAlteracao(inicio);
        dispararAlteracao(fim);
        renderizar();
        focarData(iso);
        return;
      }

      fim.value = iso;
      sincronizar();
      dispararAlteracao(fim);
      fecharCalendario(instancia, true);
    }

    function abrirCalendario() {
      if (instancia.aberto || trigger.disabled) return;
      fecharOutrosSeletores(null);
      fecharOutrosCalendarios(instancia);
      instancia.aberto = true;
      wrapper.classList.add("is-open");
      calendario.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      renderizar();
      focarData(fim.value || inicio.value || isoDaData(hoje));
    }

    function mudarMes(deslocamento) {
      mesVisivel = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth() + deslocamento, 1);
      renderizar();
      var preferida = dataPorIso(fim.value || inicio.value) || hoje;
      var ultimoDia = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth() + 1, 0).getDate();
      var destino = new Date(
        mesVisivel.getFullYear(),
        mesVisivel.getMonth(),
        Math.min(preferida.getDate(), ultimoDia)
      );
      focarData(isoDaData(destino));
    }

    trigger.addEventListener("click", function () {
      if (instancia.aberto) fecharCalendario(instancia, true);
      else abrirCalendario();
    });
    trigger.addEventListener("keydown", function (event) {
      if (["ArrowDown", "Enter", " "].indexOf(event.key) !== -1) {
        event.preventDefault();
        abrirCalendario();
      }
    });
    anterior.addEventListener("click", function () { mudarMes(-1); });
    proximo.addEventListener("click", function () { mudarMes(1); });
    limpar.addEventListener("click", function () {
      inicio.value = "";
      fim.value = "";
      sincronizar();
      dispararAlteracao(inicio);
      dispararAlteracao(fim);
      fecharCalendario(instancia, true);
    });
    hojeBotao.addEventListener("click", function () {
      var isoHoje = isoDaData(hoje);
      inicio.value = isoHoje;
      fim.value = isoHoje;
      sincronizar();
      dispararAlteracao(inicio);
      dispararAlteracao(fim);
      fecharCalendario(instancia, true);
    });
    grade.addEventListener("click", function (event) {
      var dia = event.target.closest("[data-date]");
      if (dia) selecionarData(dataPorIso(dia.getAttribute("data-date")));
    });
    grade.addEventListener("keydown", function (event) {
      var dia = event.target.closest("[data-date]");
      if (!dia) return;
      var atual = dataPorIso(dia.getAttribute("data-date"));
      var deslocamento = null;
      if (event.key === "ArrowLeft") deslocamento = -1;
      else if (event.key === "ArrowRight") deslocamento = 1;
      else if (event.key === "ArrowUp") deslocamento = -7;
      else if (event.key === "ArrowDown") deslocamento = 7;
      else if (event.key === "Home") deslocamento = -atual.getDay();
      else if (event.key === "End") deslocamento = 6 - atual.getDay();
      else if (event.key === "PageUp") { event.preventDefault(); mudarMes(-1); return; }
      else if (event.key === "PageDown") { event.preventDefault(); mudarMes(1); return; }
      else if (event.key === "Escape") { event.preventDefault(); fecharCalendario(instancia, true); return; }
      else if (event.key === "Tab") { fecharCalendario(instancia, false); return; }
      if (deslocamento === null) return;
      event.preventDefault();
      var destino = new Date(atual.getFullYear(), atual.getMonth(), atual.getDate() + deslocamento);
      if (destino.getMonth() !== mesVisivel.getMonth() || destino.getFullYear() !== mesVisivel.getFullYear()) {
        mesVisivel = new Date(destino.getFullYear(), destino.getMonth(), 1);
        renderizar();
      }
      focarData(isoDaData(destino));
    });

    inicio.addEventListener("change", sincronizar);
    fim.addEventListener("change", sincronizar);
    inicio.addEventListener("focus", function () { trigger.focus(); });
    fim.addEventListener("focus", function () { trigger.focus(); });
    [inicio, fim].forEach(function (campo) {
      campo.addEventListener("invalid", function () {
        wrapper.classList.add("is-invalid");
        trigger.setAttribute("aria-invalid", "true");
        trigger.focus();
      });
    });
    sincronizar();
  });

  document.addEventListener("pointerdown", function (event) {
    seletoresAbertos.forEach(function (instancia) {
      if (!instancia.wrapper.contains(event.target)) fecharSeletor(instancia, false);
    });
    calendariosAbertos.forEach(function (instancia) {
      if (!instancia.wrapper.contains(event.target)) fecharCalendario(instancia, false);
    });
  });

  var formulario = document.querySelector("#form-solicitacao");
  if (!formulario) return;

  function campo(nome) {
    return formulario.querySelector('[name="' + nome + '"]');
  }

  function textoSelecionado(nome) {
    var elemento = campo(nome);
    if (!elemento || !elemento.value) return "—";
    return elemento.options ? elemento.options[elemento.selectedIndex].text : elemento.value;
  }

  function formatarData(valor) {
    if (!valor) return "";
    var partes = valor.split("-");
    return partes.length === 3 ? partes[2] + "/" + partes[1] + "/" + partes[0] : valor;
  }

  function definirResumo(id, valor) {
    var elemento = document.getElementById(id);
    if (elemento) elemento.textContent = valor || "—";
  }

  function marcarChecklist(nome, completo) {
    var item = document.querySelector('[data-check="' + nome + '"]');
    if (item) item.classList.toggle("is-complete", Boolean(completo));
  }

  function atualizarAcompanhamento() {
    var inicio = campo("data_inicio_evento");
    var fim = campo("data_fim_evento");
    var municipio = campo("municipio");
    var quantidadeServidores = campo("quantidade_servidores");
    var quantidadeCin = campo("quantidade_cin");
    var contato = campo("contato");
    var servicos = formulario.querySelectorAll('[name="servicos"]:checked');
    var equipes = formulario.querySelectorAll('[name="equipes"]:checked');
    var nomesEquipes = Array.prototype.map.call(equipes, function (item) { return item.value; });

    var periodo = inicio && inicio.value ? formatarData(inicio.value) : "";
    if (fim && fim.value) periodo += " a " + formatarData(fim.value);

    definirResumo("resumo-periodo", periodo);
    definirResumo("resumo-municipio", textoSelecionado("municipio"));
    definirResumo("resumo-tipo", textoSelecionado("tipo_evento"));
    definirResumo("resumo-equipes", nomesEquipes.join(", "));
    definirResumo("resumo-servidores", quantidadeServidores && quantidadeServidores.value);
    definirResumo("resumo-cin", quantidadeCin && quantidadeCin.value);

    marcarChecklist("contato", contato && contato.value.trim());
    marcarChecklist("periodo", inicio && inicio.value && fim && fim.value);
    marcarChecklist("municipio", municipio && municipio.value);
    marcarChecklist("servicos", servicos.length);
    marcarChecklist("equipe", equipes.length);
    marcarChecklist(
      "quantidades",
      quantidadeServidores && quantidadeServidores.value && quantidadeCin && quantidadeCin.value
    );
  }

  var dataSolicitacao = campo("data_solicitacao");
  if (dataSolicitacao && !dataSolicitacao.value) {
    var hoje = new Date();
    var deslocamento = hoje.getTimezoneOffset() * 60000;
    dataSolicitacao.value = new Date(hoje.getTime() - deslocamento).toISOString().slice(0, 10);
    dataSolicitacao.dispatchEvent(new Event("change", { bubbles: true }));
  }

  formulario.addEventListener("input", atualizarAcompanhamento);
  formulario.addEventListener("change", atualizarAcompanhamento);
  atualizarAcompanhamento();
})();
