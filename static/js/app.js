/**
 * JS leve do Sistema de Gestão de Eventos Sociais.
 * Sem frameworks — apenas melhorias progressivas.
 */
(function () {
  "use strict";

  // Fecha alertas automaticamente após 6 segundos.
  document.querySelectorAll(".alerta").forEach(function (alerta) {
    if (alerta.matches("[data-resumo-erros]")) return;
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
    instancia.opcoes.forEach(function (opcao) { opcao.classList.remove("is-active"); });
    if (instancia.busca) {
      instancia.busca.removeAttribute("aria-activedescendant");
      var selecionada = instancia.nativo.options[instancia.nativo.selectedIndex];
      instancia.busca.value = instancia.nativo.value && selecionada ? selecionada.text : "";
      instancia.opcoes.forEach(function (opcao) {
        opcao.hidden = opcao.hasAttribute("data-filtered-out");
      });
      if (instancia.mensagemVazia) instancia.mensagemVazia.hidden = true;
    }
    if (devolverFoco) instancia.trigger.focus();
  }

  function fecharOutrosSeletores(excecao) {
    seletoresAbertos.forEach(function (instancia) {
      if (instancia !== excecao) fecharSeletor(instancia, false);
    });
  }

  // Função nomeada (e não um forEach anônimo) para que DS.aprimorar consiga
  // ligar selects inseridos dinamicamente; o is-enhanced impede religação.
  function aprimorarSelect(wrapper) {
    if (wrapper.classList.contains("is-enhanced")) return;
    var nativo = wrapper.querySelector(".custom-select__native");
    var trigger = wrapper.querySelector("[data-custom-select-trigger]");
    var valor = wrapper.querySelector(".custom-select__valor");
    var menu = wrapper.querySelector("[data-custom-select-menu]");
    var busca = wrapper.querySelector("[data-custom-select-search]");
    var mensagemVazia = wrapper.querySelector("[data-custom-select-empty]");
    var opcoes = Array.prototype.slice.call(wrapper.querySelectorAll(".custom-select__opcao"));
    if (!nativo || !trigger || !menu || (!busca && !valor)) return;

    var instancia = {
      wrapper: wrapper,
      nativo: nativo,
      trigger: trigger,
      menu: menu,
      opcoes: opcoes,
      busca: busca,
      mensagemVazia: mensagemVazia,
      aberto: false
    };
    seletoresAbertos.push(instancia);
    wrapper.classList.add("is-enhanced");
    menu.classList.add("is-navegavel");
    nativo.tabIndex = -1;
    nativo.setAttribute("aria-hidden", "true");
    trigger.disabled = nativo.disabled;

    // Botão para limpar a escolha, nos campos de formulário (os filtros das
    // listas têm o próprio "Limpar"). Só aparece quando há valor escolhido.
    var limpar = null;
    var temOpcaoVazia = Array.prototype.some.call(nativo.options, function (opcao) { return opcao.value === ""; });
    if (temOpcaoVazia && wrapper.closest(".form-campo") && !wrapper.closest(".fc--combo")) {
      limpar = document.createElement("button");
      limpar.type = "button";
      limpar.className = "custom-select__limpar";
      limpar.setAttribute("aria-label", "Limpar seleção");
      limpar.title = "Limpar seleção";
      limpar.hidden = true;
      menu.parentNode.insertBefore(limpar, menu);

      // Com o ×, a opção vazia ("Selecione...") sai da lista: parecia uma escolha
      // marcada. O select nativo mantém a opção vazia; limpar é pelo botão e o
      // texto continua no campo quando nada está escolhido.
      opcoes.forEach(function (opcao) {
        if (opcao.getAttribute("data-value") === "") opcao.remove();
      });
      opcoes = opcoes.filter(function (opcao) { return opcao.isConnected; });
      instancia.opcoes = opcoes;
    }

    // Quem reordena as opções por fora (as viaturas, no cadastro de termo)
    // chama isto: as setas andam por esta lista, não pela ordem do DOM.
    instancia.relerOpcoes = function () {
      opcoes = Array.prototype.slice.call(wrapper.querySelectorAll(".custom-select__opcao"));
      instancia.opcoes = opcoes;
    };

    function mostrarLimpar(visivel) {
      if (!limpar) return;
      limpar.hidden = !visivel;
      wrapper.classList.toggle("tem-limpar", visivel);
    }

    function opcaoAtual() {
      return nativo.options[nativo.selectedIndex];
    }

    function sincronizar() {
      var selecionada = opcaoAtual();
      if (busca) busca.value = nativo.value && selecionada ? selecionada.text : "";
      else valor.textContent = selecionada ? selecionada.text : "Selecione...";
      trigger.classList.toggle("has-value", Boolean(nativo.value));
      mostrarLimpar(Boolean(nativo.value) && !nativo.disabled);
      trigger.removeAttribute("aria-invalid");
      wrapper.classList.remove("is-invalid");
      opcoes.forEach(function (opcao) {
        var ativa = opcao.getAttribute("data-value") === nativo.value;
        opcao.setAttribute("aria-selected", ativa ? "true" : "false");
        opcao.classList.toggle("is-selected", ativa);
      });
    }

    function normalizarTexto(texto) {
      return String(texto || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLocaleLowerCase("pt-BR")
        .trim();
    }

    function opcoesVisiveis() {
      return opcoes.filter(function (opcao) { return !opcao.hidden; });
    }

    // Um destaque só, que o teclado e o mouse movem: é a opção que o Enter
    // escolhe. Abrir destaca a opção escolhida (ou a primeira); digitar, a
    // primeira que sobrou no filtro; passar o mouse leva o destaque junto.
    var ativa = null;

    function definirAtiva(opcao, rolar) {
      if (ativa && ativa !== opcao) ativa.classList.remove("is-active");
      ativa = opcao || null;
      if (!ativa) {
        if (busca) busca.removeAttribute("aria-activedescendant");
        return;
      }
      ativa.classList.add("is-active");
      if (busca) {
        if (!ativa.id) ativa.id = (nativo.id || "select") + "_opcao_" + opcoes.indexOf(ativa);
        busca.setAttribute("aria-activedescendant", ativa.id);
      }
      if (rolar && ativa.scrollIntoView) ativa.scrollIntoView({ block: "nearest" });
    }

    function ativarInicial(preferirSelecionada) {
      var visiveis = opcoesVisiveis();
      var selecionada = null;
      if (preferirSelecionada && nativo.value) {
        selecionada = visiveis.filter(function (opcao) {
          return opcao.getAttribute("data-value") === nativo.value;
        })[0] || null;
      }
      definirAtiva(selecionada || visiveis[0] || null, true);
    }

    function moverAtiva(direcao) {
      var disponiveis = opcoesVisiveis();
      if (!disponiveis.length) return;
      var indice = disponiveis.indexOf(ativa);
      if (indice < 0) indice = direcao > 0 ? 0 : disponiveis.length - 1;
      else indice = (indice + direcao + disponiveis.length) % disponiveis.length;
      definirAtiva(disponiveis[indice], true);
    }

    function filtrarOpcoes() {
      if (!busca) return opcoes;
      var termo = normalizarTexto(busca.value);
      var selecionada = opcaoAtual();
      if (nativo.value && selecionada && termo === normalizarTexto(selecionada.text)) termo = "";
      var visiveis = [];
      opcoes.forEach(function (opcao) {
        var corresponde = !opcao.hasAttribute("data-filtered-out")
          && normalizarTexto(opcao.textContent).indexOf(termo) !== -1;
        opcao.hidden = !corresponde;
        if (corresponde) visiveis.push(opcao);
      });
      if (mensagemVazia) mensagemVazia.hidden = visiveis.length > 0;
      return visiveis;
    }

    function abrirSeletor() {
      if (instancia.aberto || nativo.disabled) return;
      fecharOutrosSeletores(instancia);
      fecharOutrosCalendarios(null);
      instancia.aberto = true;
      wrapper.classList.add("is-open");
      menu.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      if (busca) {
        filtrarOpcoes();
        ativarInicial(true);
        busca.focus();
        return;
      }
      var selecionada = opcoes.find(function (opcao) {
        return opcao.getAttribute("data-value") === nativo.value;
      });
      var destino = selecionada || opcoes[0];
      if (destino) { definirAtiva(destino, true); destino.focus(); }
    }

    function selecionar(opcao) {
      nativo.value = opcao.getAttribute("data-value") || "";
      sincronizar();
      nativo.dispatchEvent(new Event("input", { bubbles: true }));
      nativo.dispatchEvent(new Event("change", { bubbles: true }));
      fecharSeletor(instancia, true);
    }

    function moverFoco(direcao) {
      var disponiveis = opcoesVisiveis();
      if (!disponiveis.length) return;
      var indice = disponiveis.indexOf(document.activeElement);
      if (indice < 0) indice = 0;
      indice = (indice + direcao + disponiveis.length) % disponiveis.length;
      if (disponiveis[indice]) disponiveis[indice].focus();
    }

    trigger.addEventListener("click", function () {
      if (busca) abrirSeletor();
      else if (instancia.aberto) fecharSeletor(instancia, true);
      else abrirSeletor();
    });

    trigger.addEventListener("keydown", function (event) {
      if (busca) {
        var disponiveis = opcoesVisiveis();
        // As setas andam com o destaque sem tirar o foco do campo: dá para
        // continuar digitando. Enter escolhe a opção destacada.
        if (event.key === "ArrowDown") {
          event.preventDefault();
          if (!instancia.aberto) abrirSeletor();
          else moverAtiva(1);
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          if (!instancia.aberto) abrirSeletor();
          else moverAtiva(-1);
        } else if (event.key === "Enter") {
          event.preventDefault();
          if (!instancia.aberto) {
            abrirSeletor();
          } else if (ativa && !ativa.hidden) {
            selecionar(ativa);
          } else if (disponiveis.length) {
            selecionar(disponiveis[0]);
          }
        } else if (event.key === "Escape") {
          event.preventDefault();
          fecharSeletor(instancia, true);
        } else if (event.key === "Tab") {
          fecharSeletor(instancia, false);
        }
      } else if (["ArrowDown", "ArrowUp", "Enter", " "].indexOf(event.key) !== -1) {
        event.preventDefault();
        abrirSeletor();
      }
    });

    if (busca) {
      busca.addEventListener("input", function () {
        var selecionada = opcaoAtual();
        if (nativo.value && (!selecionada || busca.value !== selecionada.text)) {
          nativo.value = "";
          trigger.classList.remove("has-value");
          mostrarLimpar(false);
          opcoes.forEach(function (opcao) {
            opcao.setAttribute("aria-selected", "false");
            opcao.classList.remove("is-selected");
          });
        }
        abrirSeletor();
        filtrarOpcoes();
        ativarInicial(false);
      });
    }

    opcoes.forEach(function (opcao) {
      opcao.addEventListener("click", function () { selecionar(opcao); });
      // mousemove (e não mouseenter): rolar a lista com o teclado não rouba o
      // destaque só porque uma opção passou por baixo do cursor parado.
      opcao.addEventListener("mousemove", function () {
        if (ativa === opcao) return;
        definirAtiva(opcao, false);
        if (!busca) opcao.focus({ preventScroll: true });
      });
      opcao.addEventListener("focus", function () { definirAtiva(opcao, false); });
      opcao.addEventListener("keydown", function (event) {
        if (event.key === "ArrowDown") { event.preventDefault(); moverFoco(1); }
        else if (event.key === "ArrowUp") { event.preventDefault(); moverFoco(-1); }
        else if (event.key === "Home") { var inicio = opcoesVisiveis(); event.preventDefault(); if (inicio[0]) inicio[0].focus(); }
        else if (event.key === "End") { var fim = opcoesVisiveis(); event.preventDefault(); if (fim.length) fim[fim.length - 1].focus(); }
        else if (event.key === "Escape") { event.preventDefault(); fecharSeletor(instancia, true); }
        else if (event.key === "Tab") fecharSeletor(instancia, false);
      });
    });

    if (limpar) {
      // mousedown sem padrão: o campo não perde o foco antes do clique chegar.
      limpar.addEventListener("mousedown", function (event) { event.preventDefault(); });
      limpar.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        if (!nativo.value) return;
        nativo.value = "";
        sincronizar();
        nativo.dispatchEvent(new Event("input", { bubbles: true }));
        nativo.dispatchEvent(new Event("change", { bubbles: true }));
        fecharSeletor(instancia, false);
        trigger.focus();
      });
    }

    nativo.addEventListener("change", sincronizar);
    nativo.addEventListener("focus", function () { trigger.focus(); });
    nativo.addEventListener("invalid", function () {
      wrapper.classList.add("is-invalid");
      trigger.setAttribute("aria-invalid", "true");
      trigger.focus();
    });
    sincronizar();
  }

  document.querySelectorAll("[data-custom-select]").forEach(aprimorarSelect);

  function fecharCalendario(instancia, devolverFoco) {
    if (!instancia || !instancia.aberto) return;
    instancia.aberto = false;
    instancia.wrapper.classList.remove("is-open");
    instancia.calendario.hidden = true;
    instancia.trigger.setAttribute("aria-expanded", "false");
    if (instancia.recortes) {
      devolverRecorte(instancia.recortes);
      instancia.recortes = null;
    }
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

  // Popover dentro de container que recorta (a tabela de trechos rola nos
  // dois eixos) era cortado pela metade e ainda criava barra de rolagem. Aqui
  // ele sai do fluxo do container e passa a ser posicionado pela viewport.
  function temAncestralQueRecorta(elemento) {
    var atual = elemento.parentElement;
    while (atual && atual !== document.body) {
      var estilo = getComputedStyle(atual);
      if (estilo.overflowX !== "visible" || estilo.overflowY !== "visible") return true;
      atual = atual.parentElement;
    }
    return false;
  }

  // O painel fica preso ao campo pelo CSS (absoluto); quem sai da frente é o
  // recorte: os ancestrais que o cortariam — a tabela de trechos rola nos dois
  // eixos — mostram o que transborda enquanto ele está aberto, e voltam ao
  // normal quando fecha.
  function liberarRecorte(elemento) {
    var liberados = [];
    var atual = elemento.parentElement;
    while (atual && atual !== document.body) {
      var estilo = getComputedStyle(atual);
      if (estilo.overflowX !== "visible" || estilo.overflowY !== "visible") {
        liberados.push({ elemento: atual, overflow: atual.style.overflow });
        atual.style.overflow = "visible";
      }
      atual = atual.parentElement;
    }
    return liberados;
  }

  function devolverRecorte(liberados) {
    (liberados || []).forEach(function (item) {
      if (item.overflow) item.elemento.style.overflow = item.overflow;
      else item.elemento.style.removeProperty("overflow");
    });
  }

  // Mesmo desenho do aprimorarSelect: nomeada para uso do DS.aprimorar.
  function aprimorarData(wrapper) {
    if (wrapper.classList.contains("is-enhanced")) return;
    var modoGV = wrapper.hasAttribute("data-calendar-gv");
    var display = wrapper.querySelector("[data-custom-date-display]");
    var nativo = wrapper.querySelector(".custom-date__native");
    var trigger = wrapper.querySelector("[data-custom-date-trigger]");
    var valor = wrapper.querySelector(".custom-date__valor");
    var calendario = wrapper.querySelector("[data-custom-date-calendar]");
    var tituloMes = wrapper.querySelector("[data-custom-date-month]");
    var grade = wrapper.querySelector("[data-custom-date-grid]");
    var anterior = wrapper.querySelector("[data-custom-date-prev]");
    var proximo = wrapper.querySelector("[data-custom-date-next]");
    var anoAnterior = wrapper.querySelector("[data-custom-date-prev-ano]");
    var anoProximo = wrapper.querySelector("[data-custom-date-next-ano]");
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
      if (modoGV) nomeMes = nomeMes.replace(" de ", " ");
      tituloMes.textContent = nomeMes.charAt(0).toUpperCase() + nomeMes.slice(1);
      grade.innerHTML = "";

      var primeiroDia = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth(), 1);
      var inicioGrade = new Date(
        primeiroDia.getFullYear(),
        primeiroDia.getMonth(),
        1 - ((primeiroDia.getDay() + (modoGV ? 6 : 0)) % 7)
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
        if (!modoGV) botao.setAttribute("role", "gridcell");
        botao.setAttribute("data-date", iso);
        botao.setAttribute("aria-label", new Intl.DateTimeFormat("pt-BR", {
          day: modoGV ? "2-digit" : "numeric", month: "long", year: "numeric"
        }).format(data));
        if (modoGV && iso === isoDaData(hoje)) botao.setAttribute("aria-label", botao.getAttribute("aria-label") + " (hoje)");
        botao.setAttribute(modoGV ? "aria-pressed" : "aria-selected", nativo.value === iso ? "true" : "false");
        botao.classList.toggle("is-outside", data.getMonth() !== mesVisivel.getMonth());
        botao.classList.toggle("is-today", iso === isoDaData(hoje));
        botao.classList.toggle("is-selected", nativo.value === iso);
        botao.disabled = estaIndisponivel(iso);
        grade.appendChild(botao);
      }
    }

    function sincronizar() {
      var data = dataPorIso(nativo.value);
      if (display) display.value = data ? dataFormatada(data) : "";
      else valor.textContent = data ? dataFormatada(data) : "dd/mm/aaaa";
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
      instancia.recortes = liberarRecorte(wrapper);
      if (!modoGV) focarData(nativo.value || isoDaData(hoje));
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
      if (!modoGV) focarData(isoDaData(destino));
    }

    trigger.addEventListener("click", function () {
      if (instancia.aberto) fecharCalendario(instancia, true);
      else abrirCalendario();
    });
    trigger.addEventListener("keydown", function (event) {
      if (modoGV) return;
      if (["ArrowDown", "Enter", " "].indexOf(event.key) !== -1) {
        event.preventDefault();
        abrirCalendario();
      }
    });
    anterior.addEventListener("click", function () { mudarMes(-1); });
    proximo.addEventListener("click", function () { mudarMes(1); });
    if (anoAnterior) anoAnterior.addEventListener("click", function () { mudarMes(-12); });
    if (anoProximo) anoProximo.addEventListener("click", function () { mudarMes(12); });
    limpar.addEventListener("click", function () {
      nativo.value = "";
      sincronizar();
      nativo.dispatchEvent(new Event("input", { bubbles: true }));
      nativo.dispatchEvent(new Event("change", { bubbles: true }));
      if (modoGV) {
        mesVisivel = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
        renderizar();
      } else fecharCalendario(instancia, true);
    });
    hojeBotao.addEventListener("click", function () { selecionarData(hoje); });
    grade.addEventListener("click", function (event) {
      var dia = event.target.closest("[data-date]");
      if (dia) selecionarData(dataPorIso(dia.getAttribute("data-date")));
    });
    grade.addEventListener("keydown", function (event) {
      if (modoGV) return;
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

    // Clicar fora fecha, como no seletor e no calendário de várias datas.
    // Sem isto o painel ficava aberto sobre a tela até escolher uma data.
    document.addEventListener("click", function (evento) {
      if (!instancia.aberto) return;
      // Navegar entre meses redesenha a grade: o alvo do clique já saiu do
      // DOM quando o evento chega aqui, e `contains` diria "clique fora".
      if (!evento.target.isConnected) return;
      if (!wrapper.contains(evento.target)) fecharCalendario(instancia, false);
    });

    if (display) {
      var focoDoPonteiro = false;
      display.disabled = nativo.disabled || nativo.readOnly;
      display.addEventListener("pointerdown", function () { focoDoPonteiro = true; });
      display.addEventListener("focus", function () { if (!focoDoPonteiro) abrirCalendario(); });
      display.addEventListener("click", function () { focoDoPonteiro = false; abrirCalendario(); });
      display.addEventListener("blur", function () { focoDoPonteiro = false; });
      document.addEventListener("keydown", function (event) {
        if (instancia.aberto && event.key === "Escape") {
          event.preventDefault();
          fecharCalendario(instancia, true);
        }
      });
    }
    nativo.addEventListener("change", sincronizar);
    nativo.addEventListener("focus", function () { trigger.focus(); });
    nativo.addEventListener("invalid", function () {
      wrapper.classList.add("is-invalid");
      trigger.setAttribute("aria-invalid", "true");
      trigger.focus();
    });
    sincronizar();
  }

  document.querySelectorAll("[data-custom-date]").forEach(aprimorarData);

  // Calendário de várias datas (components/date_multi.html): o gatilho é o
  // próprio botão, e a quantidade esperada vem do `data-max` do wrapper —
  // que quem usa pode mudar a qualquer momento. Ao completar o máximo, ou
  // no "Aplicar", o wrapper emite `ds:datas-multi` com as datas escolhidas.
  //
  // Com `data-sequencial`, cada clique é a PRÓXIMA data da lista: a mesma
  // pode repetir (ida e volta no mesmo dia) e não se volta no tempo — a data
  // anterior à última escolhida é ignorada. "Desfazer" tira a última. O
  // rodapé diz para qual passo a data vai (`data-passos`, lista JSON).
  function aprimorarDataMultipla(wrapper) {
    if (wrapper.classList.contains("is-enhanced")) return;
    // Vários gatilhos para um calendário só: no bate-volta, os campos de data
    // da ida e da volta abrem o mesmo, e as duas escolhas preenchem os dois.
    var gatilhos = Array.prototype.slice.call(
      wrapper.querySelectorAll("[data-custom-date-multi-trigger]")
    );
    var trigger = gatilhos[0];
    var gatilhoAtual = trigger;
    var recortes = null;
    var calendario = wrapper.querySelector("[data-custom-date-multi-calendar]");
    var grade = wrapper.querySelector("[data-custom-date-multi-grid]");
    var tituloMes = wrapper.querySelector("[data-custom-date-multi-month]");
    var contagem = wrapper.querySelector("[data-custom-date-multi-contagem]");
    var dica = wrapper.querySelector("[data-custom-date-multi-dica]");
    var contexto = wrapper.querySelector("[data-custom-date-multi-contexto]");
    var desfazer = wrapper.querySelector("[data-custom-date-multi-undo]");
    var aplicarBotao = wrapper.querySelector("[data-custom-date-multi-apply]");
    var sequencial = wrapper.hasAttribute("data-sequencial");
    if (!trigger || !calendario || !grade || !tituloMes) return;
    wrapper.classList.add("is-enhanced");

    var hoje = new Date();
    hoje = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
    var mesVisivel = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
    var escolhidas = [];
    var aberto = false;

    function maximo() {
      return Math.max(1, Number(wrapper.getAttribute("data-max") || 1));
    }

    // Datas já preenchidas no formulário, em ISO, mantidas por quem usa o
    // calendário em `data-valores`. Sem o atributo, vale a última escolha feita.
    function valoresInformados() {
      var bruto = wrapper.getAttribute("data-valores");
      if (bruto === null) return null;
      try {
        var lista = JSON.parse(bruto);
        if (!Array.isArray(lista)) return [];
        return lista.filter(function (valor) {
          return /^\d{4}-\d{2}-\d{2}$/.test(String(valor));
        }).slice(0, maximo());
      } catch (erro) {
        return [];
      }
    }

    function passos() {
      try {
        var lista = JSON.parse(wrapper.getAttribute("data-passos") || "[]");
        return Array.isArray(lista) ? lista : [];
      } catch (erro) {
        return [];
      }
    }

    // "Trecho 2 de 3 · Londrina → Maringá": qual data se está escolhendo.
    function atualizarContexto() {
      if (!contexto) return;
      var total = maximo();
      if (escolhidas.length >= total) {
        contexto.textContent = "Todas as datas escolhidas.";
        return;
      }
      var numero = escolhidas.length + 1;
      var rotulo = passos()[numero - 1] || "";
      contexto.textContent =
        "Data " + numero + " de " + total + (rotulo ? " · " + rotulo : "");
    }

    function renderizar() {
      var nomeMes = new Intl.DateTimeFormat("pt-BR", {
        month: "long", year: "numeric"
      }).format(mesVisivel);
      tituloMes.textContent = nomeMes.charAt(0).toUpperCase() + nomeMes.slice(1);
      grade.innerHTML = "";

      var primeiroDia = new Date(mesVisivel.getFullYear(), mesVisivel.getMonth(), 1);
      var inicioGrade = new Date(
        primeiroDia.getFullYear(), primeiroDia.getMonth(), 1 - primeiroDia.getDay()
      );
      var ordenadas = escolhidas.slice().sort();
      var primeira = ordenadas.length ? ordenadas[0] : null;
      var ultima = ordenadas.length ? ordenadas[ordenadas.length - 1] : null;

      for (var indice = 0; indice < 42; indice += 1) {
        var data = new Date(
          inicioGrade.getFullYear(), inicioGrade.getMonth(), inicioGrade.getDate() + indice
        );
        var iso = isoDaData(data);
        // Com repetição a mesma data pode estar duas vezes: vale a última.
        var posicao = escolhidas.lastIndexOf(iso);
        var botao = document.createElement("button");
        botao.type = "button";
        botao.className = "custom-date__dia";
        botao.textContent = String(data.getDate());
        botao.setAttribute("role", "gridcell");
        botao.setAttribute("data-date", iso);
        botao.setAttribute("aria-label", new Intl.DateTimeFormat("pt-BR", {
          day: "numeric", month: "long", year: "numeric"
        }).format(data));
        botao.setAttribute("aria-selected", posicao > -1 ? "true" : "false");
        botao.classList.toggle("is-outside", data.getMonth() !== mesVisivel.getMonth());
        botao.classList.toggle("is-today", iso === isoDaData(hoje));
        botao.classList.toggle("is-selected", posicao > -1);
        // Entre a primeira e a última escolhidas, os dias ganham a faixa
        // apagada do intervalo — o período que a viagem cobre.
        botao.classList.toggle(
          "is-in-range",
          posicao === -1 && primeira !== null && iso > primeira && iso < ultima
        );
        // A ordem da escolha é o que diz para qual trecho a data vai.
        if (posicao > -1) botao.setAttribute("data-ordem", String(posicao + 1));
        grade.appendChild(botao);
      }
      if (contagem) {
        contagem.textContent = escolhidas.length + " de " + maximo() +
          (maximo() === 1 ? " data" : " datas");
      }
      if (dica) dica.textContent = wrapper.getAttribute("data-dica") || "";
      if (desfazer) desfazer.disabled = escolhidas.length === 0;
      atualizarContexto();
    }

    function fechar(devolverFoco) {
      if (!aberto) return;
      aberto = false;
      calendario.hidden = true;
      wrapper.classList.remove("is-open");
      gatilhos.forEach(function (g) { g.setAttribute("aria-expanded", "false"); });
      devolverRecorte(recortes);
      recortes = null;
      if (devolverFoco) gatilhoAtual.focus();
    }

    function abrir() {
      if (aberto) return;
      aberto = true;
      // Reabrir mostra o que já está preenchido, nunca um calendário em branco:
      // as datas marcadas e o mês da primeira delas.
      var informados = valoresInformados();
      if (informados !== null) escolhidas = informados;
      if (escolhidas.length > maximo()) escolhidas = escolhidas.slice(0, maximo());
      if (escolhidas.length) {
        var primeiraEscolhida = dataPorIso(escolhidas[0]);
        mesVisivel = new Date(primeiraEscolhida.getFullYear(), primeiraEscolhida.getMonth(), 1);
      }
      calendario.hidden = false;
      wrapper.classList.add("is-open");
      gatilhoAtual.setAttribute("aria-expanded", "true");
      renderizar();
      // Com mais de um gatilho, o painel se muda para o invólucro do campo
      // clicado: fica preso a ele pelo CSS, como no calendário de um gatilho
      // só, e acompanha a rolagem sem recálculo.
      if (gatilhos.length > 1) {
        var casa = gatilhoAtual.parentElement;
        if (casa && calendario.parentElement !== casa) casa.appendChild(calendario);
      }
      recortes = liberarRecorte(calendario);
      var focoInicial = escolhidas.length ? escolhidas[0] : isoDaData(hoje);
      var primeiro = grade.querySelector('[data-date="' + focoInicial + '"]');
      if (primeiro) primeiro.focus();
    }

    function aplicar() {
      wrapper.dispatchEvent(new CustomEvent("ds:datas-multi", {
        bubbles: true,
        detail: { datas: escolhidas.slice() },
      }));
      fechar(true);
    }

    function alternarData(iso) {
      if (sequencial) {
        // Lista cheia (reaberta com as datas já preenchidas): o clique começa
        // uma escolha nova a partir deste dia.
        if (escolhidas.length >= maximo()) escolhidas = [];
        // Não se volta no tempo: a próxima data é a mesma ou depois.
        if (escolhidas.length && iso < escolhidas[escolhidas.length - 1]) return;
        escolhidas.push(iso);
      } else {
        var posicao = escolhidas.indexOf(iso);
        if (posicao > -1) escolhidas.splice(posicao, 1);
        else if (escolhidas.length < maximo()) escolhidas.push(iso);
        else return;  // cheio: soltar uma data antes de trocar
      }
      renderizar();
      var foco = grade.querySelector('[data-date="' + iso + '"]');
      if (foco) foco.focus();
      // Completou o que se pedia: aplica sem exigir mais um clique.
      if (escolhidas.length === maximo()) aplicar();
    }

    function mudarMes(deslocamento) {
      mesVisivel = new Date(
        mesVisivel.getFullYear(), mesVisivel.getMonth() + deslocamento, 1
      );
      renderizar();
    }

    gatilhos.forEach(function (gatilho) {
      gatilho.addEventListener("click", function () {
        if (aberto && gatilhoAtual === gatilho) { fechar(true); return; }
        if (aberto) fechar(false);
        gatilhoAtual = gatilho;
        abrir();
      });
    });
    wrapper.querySelector("[data-custom-date-multi-prev]")
      .addEventListener("click", function () { mudarMes(-1); });
    wrapper.querySelector("[data-custom-date-multi-next]")
      .addEventListener("click", function () { mudarMes(1); });
    wrapper.querySelector("[data-custom-date-multi-prev-ano]")
      .addEventListener("click", function () { mudarMes(-12); });
    wrapper.querySelector("[data-custom-date-multi-next-ano]")
      .addEventListener("click", function () { mudarMes(12); });
    wrapper.querySelector("[data-custom-date-multi-clear]")
      .addEventListener("click", function () { escolhidas = []; renderizar(); });
    if (aplicarBotao) aplicarBotao.addEventListener("click", aplicar);
    if (desfazer) {
      desfazer.addEventListener("click", function () {
        escolhidas.pop();
        renderizar();
      });
    }

    grade.addEventListener("click", function (evento) {
      var dia = evento.target.closest("[data-date]");
      if (dia) alternarData(dia.getAttribute("data-date"));
    });

    grade.addEventListener("keydown", function (evento) {
      var dia = evento.target.closest("[data-date]");
      if (!dia) return;
      var atual = dataPorIso(dia.getAttribute("data-date"));
      var deslocamento = null;
      if (evento.key === "ArrowLeft") deslocamento = -1;
      else if (evento.key === "ArrowRight") deslocamento = 1;
      else if (evento.key === "ArrowUp") deslocamento = -7;
      else if (evento.key === "ArrowDown") deslocamento = 7;
      else if (evento.key === "Escape") { evento.preventDefault(); fechar(true); return; }
      else if (evento.key === "Tab") { fechar(false); return; }
      if (deslocamento === null) return;
      evento.preventDefault();
      var destino = new Date(
        atual.getFullYear(), atual.getMonth(), atual.getDate() + deslocamento
      );
      if (destino.getMonth() !== mesVisivel.getMonth() ||
          destino.getFullYear() !== mesVisivel.getFullYear()) {
        mesVisivel = new Date(destino.getFullYear(), destino.getMonth(), 1);
        renderizar();
      }
      var alvo = grade.querySelector('[data-date="' + isoDaData(destino) + '"]');
      if (alvo) alvo.focus();
    });

    document.addEventListener("click", function (evento) {
      if (!aberto) return;
      // Escolher um dia redesenha a grade: o botão clicado sai do DOM antes
      // de o evento chegar aqui, e `contains` diria que o clique foi fora.
      if (!evento.target.isConnected) return;
      if (!wrapper.contains(evento.target)) fechar(false);
    });
  }

  document.querySelectorAll("[data-custom-date-multi]").forEach(aprimorarDataMultipla);

  // Filtro em cascata: um select mostra só as opções cujo
  // `data-parent-value` casa com o valor do select de que ele depende
  // (ex.: municípios do estado escolhido). O filho declara
  // `data-depends-on="<id do pai>"` no wrapper.
  function ligarCascata(wrapper) {
    if (wrapper.dataset.cascataLigada === "1") return;
    var alvoId = wrapper.getAttribute("data-depends-on");
    var pai = alvoId ? document.getElementById(alvoId) : null;
    var nativo = wrapper.querySelector(".custom-select__native");
    if (!pai || !nativo) return;
    wrapper.dataset.cascataLigada = "1";

    var opcoesMenu = Array.prototype.slice.call(
      wrapper.querySelectorAll(".custom-select__opcao")
    );
    var exigePai = wrapper.hasAttribute("data-depends-on-required");

    function definirDisponibilidade(disponivel) {
      nativo.disabled = !disponivel;
      var trigger = wrapper.querySelector("[data-custom-select-trigger]");
      if (trigger) trigger.disabled = !disponivel;
      wrapper.classList.toggle("is-disabled", !disponivel);
    }

    function aplicar(limparSelecao) {
      var valorPai = pai.value;
      definirDisponibilidade(!exigePai || Boolean(valorPai));
      Array.prototype.forEach.call(nativo.options, function (opcao) {
        if (!opcao.value) return;
        var dono = opcao.getAttribute("data-parent-value");
        // Sem pai escolhido, a lista inteira continua disponível.
        var visivel = exigePai ? Boolean(valorPai) && (!dono || dono === valorPai) : (!valorPai || !dono || dono === valorPai);
        opcao.hidden = !visivel;
        if (visivel) opcao.removeAttribute("data-filtered-out");
        else opcao.setAttribute("data-filtered-out", "");
      });
      opcoesMenu.forEach(function (opcao) {
        var dono = opcao.getAttribute("data-parent-value");
        var visivel = exigePai ? Boolean(valorPai) && (!dono || dono === valorPai) : (!valorPai || !dono || dono === valorPai);
        opcao.hidden = !visivel;
        if (visivel) opcao.removeAttribute("data-filtered-out");
        else opcao.setAttribute("data-filtered-out", "");
      });
      // Seleção que não pertence mais ao pai escolhido é descartada.
      var atual = nativo.options[nativo.selectedIndex];
      if (
        limparSelecao && nativo.value && atual &&
        atual.getAttribute("data-parent-value") &&
        atual.getAttribute("data-parent-value") !== valorPai
      ) {
        nativo.value = "";
        nativo.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }

    pai.addEventListener("change", function () { aplicar(true); });
    aplicar(false);
  }

  // Conteúdo inserido dinamicamente (ex.: linhas de destino do editor de
  // roteiro) pede o mesmo comportamento dos componentes já aprimorados.
  // DS.aprimorar(raiz) liga selects, datas e cascatas ainda crus na raiz.
  window.DS = window.DS || {};
  // Depois de mexer na ordem das opções de um select aprimorado.
  window.DS.relerOpcoesSelect = function (wrapper) {
    seletoresAbertos.forEach(function (instancia) {
      if (instancia.wrapper === wrapper && instancia.relerOpcoes) instancia.relerOpcoes();
    });
  };
  window.DS.aprimorar = function (raiz) {
    var alvo = raiz || document;
    alvo.querySelectorAll("[data-custom-select]").forEach(aprimorarSelect);
    alvo.querySelectorAll("[data-custom-date]").forEach(aprimorarData);
    alvo.querySelectorAll("[data-custom-date-multi]").forEach(aprimorarDataMultipla);
    alvo.querySelectorAll("[data-depends-on]").forEach(ligarCascata);
    // Scripts de módulo (máscaras e seletores dos cadastros de viagens) ligam
    // o que é deles no mesmo trecho recém-inserido.
    document.dispatchEvent(new CustomEvent("ds:aprimorar", { detail: { raiz: alvo } }));
  };

  document.querySelectorAll("[data-depends-on]").forEach(ligarCascata);

  document.querySelectorAll("[data-custom-date-range]").forEach(function (wrapper) {
    var inicio = wrapper.querySelector("[data-custom-date-range-start]");
    var fim = wrapper.querySelector("[data-custom-date-range-end]");
    // Um campo só ("de — até") ou dois, início e fim, com o mesmo calendário.
    var gatilhos = Array.prototype.slice.call(wrapper.querySelectorAll("[data-custom-date-range-trigger]"));
    var trigger = gatilhos[0];
    var valor = trigger && trigger.querySelector(".custom-date__valor");
    // Enquanto aberto pelo campo final, a próxima escolha é o fim, não um novo início.
    var alvo = null;
    var calendario = wrapper.querySelector("[data-custom-date-range-calendar]");
    var tituloMes = wrapper.querySelector("[data-custom-date-range-month]");
    var instrucao = wrapper.querySelector("[data-custom-date-range-hint]");
    var grade = wrapper.querySelector("[data-custom-date-range-grid]");
    var anterior = wrapper.querySelector("[data-custom-date-range-prev]");
    var proximo = wrapper.querySelector("[data-custom-date-range-next]");
    var anoAnterior = wrapper.querySelector("[data-custom-date-range-prev-ano]");
    var anoProximo = wrapper.querySelector("[data-custom-date-range-next-ano]");
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
    gatilhos.forEach(function (gatilho) {
      gatilho.disabled = inicio.disabled || fim.disabled || inicio.readOnly || fim.readOnly;
    });

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
      gatilhos.forEach(function (gatilho) {
        var campo = gatilho.getAttribute("data-range-campo");
        var texto = gatilho.querySelector(".custom-date__valor");
        var propria = campo === "fim" ? dataFim : dataInicio;
        if (campo) {
          texto.textContent = propria ? dataFormatada(propria) : "dd/mm/aaaa";
        } else if (dataInicio && dataFim) {
          texto.textContent = dataFormatada(dataInicio) + " — " + dataFormatada(dataFim);
        } else if (dataInicio) {
          texto.textContent = dataFormatada(dataInicio) + " — selecione o fim";
        } else {
          texto.textContent = "dd/mm/aaaa — dd/mm/aaaa";
        }
        gatilho.classList.toggle("has-value", Boolean(campo ? propria : dataInicio));
        gatilho.removeAttribute("aria-invalid");
      });
      wrapper.classList.remove("is-invalid");
      if (dataInicio) mesVisivel = new Date(dataInicio.getFullYear(), dataInicio.getMonth(), 1);
      if (instancia.aberto) renderizar();
    }

    function selecionarData(data) {
      var iso = isoDaData(data);
      if (dataEstaIndisponivel(iso)) return;

      // Aberto pelo campo final: a escolha é o fim, desde que não anteceda o início.
      if (alvo === "fim" && inicio.value && iso >= inicio.value) {
        fim.value = iso;
        sincronizar();
        dispararAlteracao(fim);
        fecharCalendario(instancia, true);
        return;
      }

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

    function abrirCalendario(gatilho) {
      if (instancia.aberto || trigger.disabled) return;
      alvo = gatilho ? gatilho.getAttribute("data-range-campo") : null;
      instancia.trigger = gatilho || trigger;
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

    gatilhos.forEach(function (gatilho) {
      gatilho.addEventListener("click", function () {
        if (instancia.aberto) fecharCalendario(instancia, true);
        else abrirCalendario(gatilho);
      });
      gatilho.addEventListener("keydown", function (event) {
        if (["ArrowDown", "Enter", " "].indexOf(event.key) !== -1) {
          event.preventDefault();
          abrirCalendario(gatilho);
        }
      });
    });
    anterior.addEventListener("click", function () { mudarMes(-1); });
    proximo.addEventListener("click", function () { mudarMes(1); });
    if (anoAnterior) anoAnterior.addEventListener("click", function () { mudarMes(-12); });
    if (anoProximo) anoProximo.addEventListener("click", function () { mudarMes(12); });
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

    function gatilhoDe(campo) {
      var nome = campo === fim ? "fim" : "inicio";
      return gatilhos.filter(function (g) { return g.getAttribute("data-range-campo") === nome; })[0] || trigger;
    }

    inicio.addEventListener("change", sincronizar);
    fim.addEventListener("change", sincronizar);
    inicio.addEventListener("focus", function () { gatilhoDe(inicio).focus(); });
    fim.addEventListener("focus", function () { gatilhoDe(fim).focus(); });
    [inicio, fim].forEach(function (campo) {
      campo.addEventListener("invalid", function () {
        wrapper.classList.add("is-invalid");
        var gatilho = gatilhoDe(campo);
        gatilho.setAttribute("aria-invalid", "true");
        gatilho.focus();
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

  // Etapas da lateral: concluída quando todos os campos da seção estão
  // preenchidos, "em preenchimento" quando parte deles está.
  function marcarEtapa(nome, feitos, total) {
    var item = document.querySelector('[data-etapa="' + nome + '"]');
    if (!item) return;
    var concluida = total > 0 && feitos >= total;
    var andamento = !concluida && feitos > 0;
    item.classList.toggle("etapa--concluida", concluida);
    item.classList.toggle("etapa--andamento", andamento);
    var texto = item.querySelector(".etapa__estado");
    if (texto) {
      texto.textContent = concluida
        ? "Concluído"
        : andamento
          ? "Em preenchimento"
          : item.hasAttribute("data-etapa-opcional")
            ? "Opcional"
            : "Pendente";
    }
  }

  function contar(condicoes) {
    return condicoes.filter(Boolean).length;
  }

  function atualizarAcompanhamento() {
    var inicio = campo("data_inicio_evento");
    var fim = campo("data_fim_evento");
    var municipio = campo("municipio");
    var estado = campo("estado");
    var quantidadeCin = campo("quantidade_cin");
    var servicos = formulario.querySelectorAll('[name="servicos"]:checked');
    var equipes = formulario.querySelectorAll('[name="equipes"]:checked');
    var nomesEquipes = Array.prototype.map.call(equipes, function (item) {
      var rotulo = item.closest("label");
      var alocacao = item.closest("[data-equipe-alocacao]");
      var quantidade = alocacao && alocacao.querySelector("[data-equipe-quantidade]");
      var nome = rotulo ? rotulo.textContent.trim() : item.value;
      return quantidade && quantidade.value ? nome + " (" + quantidade.value + ")" : nome;
    });
    var quantidadesEquipes = Array.prototype.map.call(equipes, function (item) {
      var alocacao = item.closest("[data-equipe-alocacao]");
      var quantidade = alocacao && alocacao.querySelector("[data-equipe-quantidade]");
      return quantidade ? Number(quantidade.value || 0) : 0;
    });
    var totalServidores = quantidadesEquipes.reduce(function (total, quantidade) {
      return total + quantidade;
    }, 0);

    var periodo = inicio && inicio.value ? formatarData(inicio.value) : "";
    if (fim && fim.value) periodo += " a " + formatarData(fim.value);

    definirResumo("resumo-periodo", periodo);
    definirResumo("resumo-estado", textoSelecionado("estado"));
    definirResumo("resumo-municipio", textoSelecionado("municipio"));
    definirResumo("resumo-tipo", textoSelecionado("tipo_evento"));
    definirResumo("resumo-equipes", nomesEquipes.join(", "));
    definirResumo("resumo-servidores", totalServidores || "");
    definirResumo("resumo-cin", quantidadeCin && quantidadeCin.value);

    marcarChecklist("periodo", inicio && inicio.value && fim && fim.value);
    marcarChecklist("estado", estado && estado.value);
    marcarChecklist("municipio", municipio && municipio.value);
    marcarChecklist("servicos", servicos.length);
    marcarChecklist("equipe", equipes.length);
    marcarChecklist(
      "quantidades",
      equipes.length
        && quantidadesEquipes.every(function (quantidade) { return quantidade > 0; })
        && quantidadeCin
        && quantidadeCin.value
    );

    var solicitanteNome = campo("solicitante_nome");
    var solicitanteCargo = campo("solicitante_cargo_unidade");
    var orgao = campo("orgao_responsavel");
    var quantidadesOk = Boolean(
      equipes.length
        && quantidadesEquipes.every(function (quantidade) { return quantidade > 0; })
    );
    marcarEtapa("dados", contar([
      Boolean(inicio && inicio.value && fim && fim.value),
      Boolean(estado && estado.value),
      Boolean(municipio && municipio.value),
      Boolean(textoSelecionado("tipo_evento")),
    ]), 4);
    marcarEtapa("solicitante", contar([
      Boolean(solicitanteNome && solicitanteNome.value.trim()),
      Boolean(solicitanteCargo && solicitanteCargo.value.trim()),
      Boolean(orgao && orgao.value),
    ]), 3);
    marcarEtapa("servicos", contar([servicos.length > 0]), 1);
    marcarEtapa("planejamento", contar([equipes.length > 0, quantidadesOk]), 2);
    var anexosNovos = formulario.querySelector('input[name="anexos"]');
    if (anexosNovos && anexosNovos.files.length) {
      marcarEtapa("anexos", 1, 1);
    }
  }

  formulario.querySelectorAll("[data-equipe-alocacao]").forEach(function (alocacao) {
    var checkbox = alocacao.querySelector("[data-equipe-checkbox]");
    var quantidade = alocacao.querySelector("[data-equipe-quantidade]");
    if (!checkbox || !quantidade) return;
    // A quantidade da DG fica livre mesmo com a equipe travada.
    if (quantidade.hasAttribute("data-quantidade-dg")) return;
    var bloqueadoPorPermissao = checkbox.disabled;

    function sincronizarQuantidade(focar) {
      quantidade.disabled = bloqueadoPorPermissao || !checkbox.checked;
      if (focar && checkbox.checked && !quantidade.value && !bloqueadoPorPermissao) {
        quantidade.focus();
      }
    }

    checkbox.addEventListener("change", function () { sincronizarQuantidade(true); });
    sincronizarQuantidade(false);
  });

  var dataSolicitacao = campo("data_solicitacao");
  if (dataSolicitacao && !dataSolicitacao.value) {
    var hoje = new Date();
    var deslocamento = hoje.getTimezoneOffset() * 60000;
    dataSolicitacao.value = new Date(hoje.getTime() - deslocamento).toISOString().slice(0, 10);
    dataSolicitacao.dispatchEvent(new Event("change", { bubbles: true }));
  }

  var tipoEvento = campo("tipo_evento");
  var estadoEvento = campo("estado");
  var municipioEvento = campo("municipio");
  var solicitanteNome = campo("solicitante_nome");
  var solicitanteCargoUnidade = campo("solicitante_cargo_unidade");

  function normalizarNomeEvento(valor) {
    return String(valor || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR")
      .trim();
  }

  function preencherSolicitanteParanaEmAcao() {
    if (!tipoEvento || normalizarNomeEvento(textoSelecionado("tipo_evento")) !== "parana em acao") {
      return;
    }
    if (solicitanteNome) solicitanteNome.value = "Paraná em Ação";
    if (solicitanteCargoUnidade) solicitanteCargoUnidade.value = "SEJU";
  }

  if (tipoEvento) {
    tipoEvento.addEventListener("change", preencherSolicitanteParanaEmAcao);
    preencherSolicitanteParanaEmAcao();
  }

  function filtrarMunicipiosPorEstado() {
    if (!estadoEvento || !municipioEvento) return;
    var estadoSelecionado = estadoEvento.value;
    var wrapperMunicipio = municipioEvento.closest("[data-custom-select]");
    var opcaoSelecionada = municipioEvento.options[municipioEvento.selectedIndex];

    Array.prototype.forEach.call(municipioEvento.options, function (opcao) {
      var estadoOpcao = opcao.getAttribute("data-parent-value");
      var visivel = !estadoOpcao || estadoOpcao === estadoSelecionado;
      opcao.hidden = !visivel;
      opcao.disabled = !visivel;
    });

    if (
      opcaoSelecionada
      && opcaoSelecionada.getAttribute("data-parent-value")
      && opcaoSelecionada.getAttribute("data-parent-value") !== estadoSelecionado
    ) {
      municipioEvento.value = "";
      municipioEvento.dispatchEvent(new Event("change", { bubbles: true }));
    }

    if (wrapperMunicipio) {
      wrapperMunicipio.querySelectorAll(".custom-select__opcao").forEach(function (opcao) {
        var visivel = opcao.getAttribute("data-parent-value") === estadoSelecionado;
        opcao.toggleAttribute("data-filtered-out", !visivel);
        opcao.hidden = !visivel;
      });
      var buscaMunicipio = wrapperMunicipio.querySelector("[data-custom-select-search]");
      if (buscaMunicipio && !municipioEvento.value) buscaMunicipio.value = "";
    }
  }

  if (estadoEvento && municipioEvento) {
    estadoEvento.addEventListener("change", filtrarMunicipiosPorEstado);
    filtrarMunicipiosPorEstado();
  }

  formulario.addEventListener("input", atualizarAcompanhamento);
  formulario.addEventListener("change", atualizarAcompanhamento);
  atualizarAcompanhamento();
})();

/**
 * Máscara de telefone brasileiro para campos de contato.
 * Aceita 10 dígitos (fixo) ou 11 dígitos (celular).
 */
(function () {
  "use strict";

  function formatarTelefone(valor) {
    var digitos = String(valor || "").replace(/\D/g, "").slice(0, 11);
    if (!digitos) return "";
    if (digitos.length <= 2) return "(" + digitos;

    var ddd = digitos.slice(0, 2);
    var numero = digitos.slice(2);
    if (numero.length <= 4) return "(" + ddd + ") " + numero;
    if (numero.length <= 8) {
      return "(" + ddd + ") " + numero.slice(0, 4) + "-" + numero.slice(4);
    }
    return "(" + ddd + ") " + numero.slice(0, 5) + "-" + numero.slice(5);
  }

  document.querySelectorAll("[data-mask-telefone]").forEach(function (campo) {
    function aplicarMascara() {
      campo.value = formatarTelefone(campo.value);
    }

    campo.addEventListener("input", aplicarMascara);
    aplicarMascara();
  });
})();

/**
 * Confirmação em duas etapas para ações sem volta, sem diálogo nativo do
 * navegador. Primeiro clique arma o botão; o segundo envia.
 * `data-confirmar="texto"` personaliza o rótulo armado.
 */
(function () {
  "use strict";

  var seletor = "[data-confirmar-exclusao], [data-confirmar]";
  document.querySelectorAll(seletor).forEach(function (formulario) {
    var botao = formulario.querySelector('button[type="submit"]');
    if (!botao) return;
    // Guarda a marcação inteira: itens de menu têm ícone, título e descrição.
    var conteudoOriginal = botao.innerHTML;
    var rotuloArmado = formulario.getAttribute("data-confirmar") || "Confirmar?";
    var armado = false;
    var temporizador = null;

    function desarmar() {
      armado = false;
      botao.innerHTML = conteudoOriginal;
      botao.classList.remove("is-armado");
      if (temporizador) {
        clearTimeout(temporizador);
        temporizador = null;
      }
    }

    formulario.addEventListener("submit", function (evento) {
      if (armado) return;
      evento.preventDefault();
      armado = true;
      // Item com título (<b>) troca só o título e mantém ícone e descrição.
      var titulo = botao.querySelector("b");
      if (titulo) titulo.textContent = rotuloArmado;
      else botao.textContent = rotuloArmado;
      botao.classList.add("is-armado");
      temporizador = setTimeout(desarmar, 4000);
    });

    botao.addEventListener("blur", desarmar);
  });
})();

/**
 * Campos que só existem com unidade móvel: "Qual unidade móvel" e
 * "Motorista" ficam ocultos quando a resposta é Não, e a seleção é limpa.
 * A mesma regra é garantida no servidor (SolicitacaoForm).
 */
(function () {
  "use strict";

  var formulario = document.querySelector("#form-solicitacao");
  if (!formulario) return;
  // O controle virou o interruptor do cabeçalho do cartão (uma caixa de
  // seleção); os dois formatos continuam valendo.
  var controles = formulario.querySelectorAll('input[name="unidade_movel"]');
  if (!controles.length) return;
  var selects = ["unidade_movel_designada", "motorista"]
    .map(function (nome) {
      return formulario.querySelector('select[name="' + nome + '"]');
    })
    .filter(Boolean);
  if (!selects.length) return;

  // A caixa cinza dos dois campos some inteira: vazia, ela seria só uma borda.
  var caixa = formulario.querySelector(".condicional");

  function aplicarRegra() {
    var marcado = formulario.querySelector('input[name="unidade_movel"]:checked');
    var ativo = Boolean(marcado && marcado.value === "1");
    if (caixa) caixa.hidden = !ativo;
    selects.forEach(function (select) {
      var campo = select.closest(".form-campo");
      if (campo) campo.style.display = ativo ? "" : "none";
      if (!ativo && !select.disabled && select.value) {
        select.value = "";
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  }

  controles.forEach(function (controle) {
    controle.addEventListener("change", aplicarRegra);
  });
  aplicarRegra();
})();

/**
 * Rola até a seção de trabalho da tela atual (ex.: planejamento na análise),
 * poupando o usuário de procurar o formulário no meio da página.
 */
(function () {
  "use strict";

  var alvo = document.querySelector("[data-rolar-para]");
  if (alvo) {
    window.setTimeout(function () {
      alvo.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 150);
  }
})();

/**
 * Validação com mensagem escrita em cada campo.
 * O navegador só mostra a bolha nativa no primeiro campo inválido e pinta os
 * demais de vermelho sem dizer o que falta. Aqui a validação nativa é
 * desligada e substituída: todos os campos com problema ganham um texto
 * explicativo de uma vez, e a página rola até o primeiro deles.
 */
(function () {
  "use strict";

  var MENSAGENS = {
    valueMissing: {
      SELECT: "Selecione uma opção.",
      TEXTAREA: "Preencha este campo.",
      padrao: "Preencha este campo.",
    },
    rangeUnderflow: "Informe um número maior.",
    rangeOverflow: "Informe um número menor.",
    typeMismatch: "Confira o formato do que foi digitado.",
  };

  function mensagemDe(campo) {
    var estado = campo.validity;
    if (estado.valueMissing) {
      return MENSAGENS.valueMissing[campo.tagName] || MENSAGENS.valueMissing.padrao;
    }
    var chave = ["rangeUnderflow", "rangeOverflow", "typeMismatch"].find(function (nome) {
      return estado[nome];
    });
    return (chave && MENSAGENS[chave]) || campo.validationMessage || "Valor inválido.";
  }

  function campoContainer(campo) {
    return campo.closest(".form-campo") || campo.parentElement;
  }

  function limparErro(campo) {
    var container = campoContainer(campo);
    if (!container) return;
    var erro = container.querySelector("[data-erro-cliente]");
    if (erro) {
      var descritosPor = (campo.getAttribute("aria-describedby") || "")
        .split(/\s+/)
        .filter(function (id) { return id && id !== erro.id; });
      if (descritosPor.length) campo.setAttribute("aria-describedby", descritosPor.join(" "));
      else campo.removeAttribute("aria-describedby");
      erro.remove();
    }
    campo.removeAttribute("aria-invalid");
    var wrapper = campo.closest(".custom-select, .custom-date, .form-controle-wrapper");
    if (wrapper) wrapper.classList.remove("is-invalid");
  }

  function marcarErro(campo) {
    var container = campoContainer(campo);
    if (!container) return;
    var erro = container.querySelector("[data-erro-cliente]");
    if (!erro) {
      erro = document.createElement("p");
      erro.className = "form-erro";
      erro.setAttribute("data-erro-cliente", "");
      var baseId = campo.id || campo.name || "campo";
      erro.id = baseId + "-erro-cliente";
      container.appendChild(erro);
    }
    erro.textContent = mensagemDe(campo);
    campo.setAttribute("aria-invalid", "true");
    var descritosPor = (campo.getAttribute("aria-describedby") || "")
      .split(/\s+/)
      .filter(Boolean);
    if (descritosPor.indexOf(erro.id) === -1) descritosPor.push(erro.id);
    campo.setAttribute("aria-describedby", descritosPor.join(" "));
    var wrapper = campo.closest(".custom-select, .custom-date, .form-controle-wrapper");
    if (wrapper) wrapper.classList.add("is-invalid");
  }

  document.querySelectorAll("form").forEach(function (formulario) {
    // Só campos que o formulário envia de fato: a caixa de busca dentro de um
    // combobox não tem name, é sempre válida, e apagaria a mensagem do select
    // que divide o mesmo container com ela.
    var campos = Array.prototype.filter.call(
      formulario.querySelectorAll("input, select, textarea"),
      function (campo) {
        return campo.name && campo.willValidate;
      }
    );
    if (!campos.length) return;
    // Assume a validação: sem isto o navegador interrompe antes e só a bolha
    // nativa do primeiro campo aparece.
    formulario.setAttribute("novalidate", "");

    campos.forEach(function (campo) {
      ["input", "change"].forEach(function (evento) {
        campo.addEventListener(evento, function () {
          if (campo.checkValidity()) limparErro(campo);
        });
      });
    });

    formulario.addEventListener("submit", function (evento) {
      // "Salvar rascunho" e afins passam direto, como o formnovalidate pede.
      var enviador = evento.submitter;
      if (enviador && enviador.formNoValidate) return;
      if (formulario.checkValidity()) return;

      evento.preventDefault();
      var invalidos = [];
      campos.forEach(function (campo) {
        if (campo.disabled || campo.checkValidity()) {
          limparErro(campo);
          return;
        }
        marcarErro(campo);
        invalidos.push(campo);
      });
      if (!invalidos.length) return;

      var primeiro = invalidos[0];
      var alvo = campoContainer(primeiro) || primeiro;
      alvo.scrollIntoView({ behavior: "smooth", block: "center" });
      var foco = primeiro.closest(".custom-select, .custom-date");
      var focavel = foco ? foco.querySelector("[data-custom-select-trigger], [data-custom-date-trigger]") : primeiro;
      if (focavel && focavel.focus) {
        setTimeout(function () { focavel.focus({ preventScroll: true }); }, 300);
      }
    });
  });
})();

/**
 * Linha de tabela clicável: o número já é link, mas o alvo real do usuário é
 * a linha toda. Cliques em links, botões ou seleção de texto são respeitados.
 */
(function () {
  "use strict";

  document.querySelectorAll("[data-linha-url]").forEach(function (linha) {
    var destino = linha.getAttribute("data-linha-url");

    linha.addEventListener("click", function (evento) {
      if (evento.target.closest("a, button, input, label")) return;
      if (window.getSelection && String(window.getSelection())) return;
      window.location.href = destino;
    });
  });

  var resumoErros = document.querySelector("[data-resumo-erros]");
  if (resumoErros) resumoErros.focus();
})();

/**
 * Alterna a visibilidade da senha. Digitar senha institucional às cegas é a
 * principal origem de "usuário e senha incorretos" no primeiro acesso.
 */
(function () {
  "use strict";

  var SVG_ABERTO =
    '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z"></path><circle cx="12" cy="12" r="3"></circle>';
  var SVG_FECHADO =
    '<path d="M10.6 6.2A9.9 9.9 0 0 1 12 6c6.5 0 10 6 10 6a17 17 0 0 1-3.2 3.7M6.2 7.4A17 17 0 0 0 2 12s3.5 6 10 6a9.6 9.6 0 0 0 3.9-.8"></path><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"></path><path d="M3 3l18 18"></path>';

  document.querySelectorAll("[data-alternar-senha]").forEach(function (botao) {
    var campo = botao.parentElement.querySelector('input[type="password"], input[type="text"]');
    if (!campo) return;
    var svg = botao.querySelector("svg");

    botao.addEventListener("click", function () {
      var revelando = campo.type === "password";
      campo.type = revelando ? "text" : "password";
      botao.setAttribute("aria-pressed", String(revelando));
      botao.setAttribute("aria-label", revelando ? "Ocultar senha" : "Mostrar senha");
      if (svg) svg.innerHTML = revelando ? SVG_FECHADO : SVG_ABERTO;
      campo.focus();
    });
  });
})();

/**
 * Rascunho automático do formulário de solicitação.
 * O formulário é longo e uma falha no envio custava todo o preenchimento.
 * O conteúdo fica no navegador (localStorage) enquanto a solicitação não é
 * salva, e some assim que o envio dá certo.
 */
(function () {
  "use strict";

  var chave = "rascunho:" + window.location.pathname;
  var IGNORADOS = ["csrfmiddlewaretoken", "acao"];

  // Primeiro a faxina: depois de um envio bem-sucedido a página de destino é
  // o resumo, que não tem formulário nenhum — se a limpeza dependesse dele,
  // o rascunho ficaria preso no navegador para sempre.
  try {
    var enviado = window.sessionStorage.getItem("rascunho-enviado");
    if (enviado && enviado !== chave) {
      window.localStorage.removeItem(enviado);
      window.sessionStorage.removeItem("rascunho-enviado");
    }
  } catch (erro) {
    /* Sem storage disponível não há rascunho a limpar. */
  }

  var formulario = document.getElementById("form-solicitacao");
  if (!formulario || formulario.tagName !== "FORM") return;

  function disponivel() {
    try {
      window.localStorage.setItem("__teste__", "1");
      window.localStorage.removeItem("__teste__");
      return true;
    } catch (erro) {
      return false;
    }
  }

  if (!disponivel()) return;

  function campos() {
    return Array.prototype.filter.call(
      formulario.querySelectorAll("input, select, textarea"),
      function (campo) {
        return (
          campo.name &&
          IGNORADOS.indexOf(campo.name) === -1 &&
          campo.type !== "file" &&
          campo.type !== "hidden"
        );
      }
    );
  }

  function guardar() {
    var dados = {};
    campos().forEach(function (campo) {
      if (campo.type === "checkbox" || campo.type === "radio") {
        if (!campo.checked) return;
        (dados[campo.name] = dados[campo.name] || []).push(campo.value);
      } else if (campo.value) {
        dados[campo.name] = campo.value;
      }
    });
    try {
      window.localStorage.setItem(chave, JSON.stringify(dados));
    } catch (erro) {
      /* Cota estourada: seguir sem rascunho é melhor que travar o formulário. */
    }
  }

  function restaurar() {
    var bruto = window.localStorage.getItem(chave);
    if (!bruto) return false;
    var dados;
    try {
      dados = JSON.parse(bruto);
    } catch (erro) {
      window.localStorage.removeItem(chave);
      return false;
    }
    var restaurou = false;
    campos().forEach(function (campo) {
      var salvo = dados[campo.name];
      if (salvo === undefined) return;
      if (campo.type === "checkbox" || campo.type === "radio") {
        var marcar = Array.isArray(salvo) && salvo.indexOf(campo.value) !== -1;
        if (campo.checked !== marcar) restaurou = true;
        campo.checked = marcar;
      } else if (campo.value !== salvo) {
        campo.value = salvo;
        restaurou = true;
      }
      campo.dispatchEvent(new Event("change", { bubbles: true }));
    });
    return restaurou;
  }

  function avisarRestauracao() {
    var aviso = document.createElement("div");
    aviso.className = "alerta alerta--info";
    aviso.setAttribute("role", "status");
    aviso.textContent =
      "Recuperamos o que você tinha preenchido nesta tela e não chegou a ser salvo.";
    formulario.parentNode.insertBefore(aviso, formulario);
  }

  // Só recupera em formulário novo: editar já traz os dados salvos do banco.
  var ehNovo = !formulario.querySelector('[name="acao"]') ||
    window.location.pathname.indexOf("/nova/") !== -1;
  if (ehNovo && restaurar()) avisarRestauracao();

  formulario.addEventListener("input", guardar);
  formulario.addEventListener("change", guardar);
  formulario.addEventListener("submit", function () {
    // O envio pode falhar e recarregar esta mesma página; por isso a limpeza
    // só acontece quando o navegador chega a outro endereço.
    window.sessionStorage.setItem("rascunho-enviado", chave);
  });
})();

/**
 * Menu do avatar no cabeçalho: alterar senha, acesso gestor e sair moram
 * aqui para o topo da página carregar só identidade e notificações.
 */
(function () {
  "use strict";

  document.querySelectorAll("[data-menu-usuario]").forEach(function (wrapper) {
    var gatilho = wrapper.querySelector("[data-menu-usuario-gatilho]");
    var menu = wrapper.querySelector("[data-menu-usuario-menu]");
    if (!gatilho || !menu) return;

    function fechar() {
      menu.hidden = true;
      gatilho.setAttribute("aria-expanded", "false");
    }

    gatilho.addEventListener("click", function (evento) {
      evento.stopPropagation();
      var abrir = menu.hidden;
      menu.hidden = !abrir;
      gatilho.setAttribute("aria-expanded", String(abrir));
    });

    document.addEventListener("click", function (evento) {
      if (!menu.hidden && !wrapper.contains(evento.target)) fechar();
    });

    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape" && !menu.hidden) {
        fechar();
        gatilho.focus();
      }
    });
  });
})();

/**
 * Formulário que se envia sozinho quando um campo muda (ex.: o seletor de
 * período do gráfico). O select customizado repassa o change ao nativo.
 */
(function () {
  "use strict";

  document.querySelectorAll("form[data-auto-enviar]").forEach(function (formulario) {
    formulario.addEventListener("keydown", function (evento) {
      if (evento.key === "Enter" && evento.target.matches('input[type="search"]')) {
        evento.preventDefault();
        formulario.requestSubmit();
      }
    });
    formulario.addEventListener("change", function () {
      formulario.submit();
    });
  });
})();

/**
 * Menu flutuante genérico (kebab de ações, seletor de colunas): mesmo
 * comportamento do menu do avatar, para qualquer gatilho + corpo.
 */
(function () {
  "use strict";

  // Um menu aberto por vez: abrir um fecha os demais (o clique no gatilho não
  // chega ao document, então o "clique fora" não faria isso sozinho).
  var fechamentos = [];

  document.querySelectorAll("[data-menu]").forEach(function (wrapper) {
    var gatilho = wrapper.querySelector("[data-menu-gatilho]");
    var corpo = wrapper.querySelector("[data-menu-corpo]");
    if (!gatilho || !corpo) return;

    function fechar() {
      corpo.hidden = true;
      gatilho.setAttribute("aria-expanded", "false");
    }
    fechamentos.push(fechar);

    // Abre para cima quando embaixo não cabe: ficaria cortado na janela ou
    // esticaria a página. Só sobe se houver espaço acima do gatilho.
    function posicionar(alturaAntes) {
      corpo.classList.remove("dd__c--acima");
      var margem = 12;
      var caixa = corpo.getBoundingClientRect();
      var caixaGatilho = gatilho.getBoundingClientRect();
      var cortaNaJanela = caixa.bottom + margem > window.innerHeight;
      var esticaPagina = caixa.bottom + window.scrollY > alturaAntes;
      var cabeEmCima = caixaGatilho.top - caixa.height - 6 >= margem;
      if ((cortaNaJanela || esticaPagina) && cabeEmCima) corpo.classList.add("dd__c--acima");
    }

    gatilho.addEventListener("click", function (evento) {
      evento.stopPropagation();
      var abrir = corpo.hidden;
      if (abrir) {
        fechamentos.forEach(function (outro) { if (outro !== fechar) outro(); });
      }
      // Altura da página antes de o menu aparecer: é com ela que se sabe se ele esticaria a página.
      var alturaAntes = document.documentElement.scrollHeight;
      corpo.hidden = !abrir;
      gatilho.setAttribute("aria-expanded", String(abrir));
      if (abrir) posicionar(alturaAntes);
    });

    // Escolher um item (abrir modal, excluir, enviar) também fecha o menu —
    // menos o primeiro clique de uma exclusão em duas etapas, que só arma o
    // botão: o menu fica aberto para o clique de confirmação.
    corpo.addEventListener("click", function (evento) {
      var item = evento.target.closest(".dd__i");
      if (!item) return;
      var confirmacao = item.matches('button[type="submit"]') &&
        item.closest("[data-confirmar-exclusao], [data-confirmar]");
      if (confirmacao && !item.classList.contains("is-armado")) return;
      fechar();
    });

    document.addEventListener("click", function (evento) {
      if (!corpo.hidden && !wrapper.contains(evento.target)) fechar();
    });

    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape" && !corpo.hidden) {
        fechar();
        gatilho.focus();
      }
    });
  });
})();

/**
 * Painel expansível (ex.: filtros avançados da listagem).
 */
(function () {
  "use strict";

  document.querySelectorAll("[data-expande]").forEach(function (botao) {
    var alvo = document.querySelector(botao.getAttribute("data-expande"));
    if (!alvo) return;
    // O servidor decide o estado inicial (aberto quando há data preenchida).
    alvo.hidden = botao.getAttribute("aria-expanded") !== "true";

    botao.addEventListener("click", function () {
      alvo.hidden = !alvo.hidden;
      botao.setAttribute("aria-expanded", String(!alvo.hidden));
    });
  });
})();

/**
 * Seletor de colunas da listagem, lembrado por navegador (localStorage).
 * Nº e Ações ficam sempre visíveis; o resto o usuário decide.
 */
(function () {
  "use strict";

  var tabela = document.querySelector("[data-tabela-colunas]");
  var menu = document.querySelector("[data-colunas-menu]");
  if (!tabela || !menu) return;

  var CHAVE = "lista-colunas-ocultas";

  function ocultas() {
    try {
      return JSON.parse(window.localStorage.getItem(CHAVE)) || [];
    } catch (erro) {
      return [];
    }
  }

  function guardar(lista) {
    try {
      window.localStorage.setItem(CHAVE, JSON.stringify(lista));
    } catch (erro) {
      /* Sem storage o seletor funciona só na página atual. */
    }
  }

  function aplicar() {
    var lista = ocultas();
    tabela.querySelectorAll("[data-col]").forEach(function (celula) {
      celula.classList.toggle(
        "coluna-oculta", lista.indexOf(celula.getAttribute("data-col")) !== -1
      );
    });
    menu.querySelectorAll("[data-coluna-toggle]").forEach(function (caixa) {
      caixa.checked = lista.indexOf(caixa.getAttribute("data-coluna-toggle")) === -1;
    });
  }

  menu.querySelectorAll("[data-coluna-toggle]").forEach(function (caixa) {
    caixa.addEventListener("change", function () {
      var chave = caixa.getAttribute("data-coluna-toggle");
      var lista = ocultas().filter(function (item) { return item !== chave; });
      if (!caixa.checked) lista.push(chave);
      guardar(lista);
      aplicar();
    });
  });

  aplicar();
})();

// Formulário de usuários: descreve o perfil de acesso escolhido.
(function () {
  var descricoes = document.querySelectorAll("[data-perfil-info]");
  if (!descricoes.length) return;
  var select = document.getElementById("id_perfil");
  if (!select) return;
  function atualizar() {
    descricoes.forEach(function (item) {
      item.hidden = (item.getAttribute("data-perfil-info") || "") !== select.value;
    });
  }
  select.addEventListener("change", atualizar);
  atualizar();
})();

// Alterar senha: medidor de força e requisitos marcados em tempo real.
(function () {
  var medidor = document.querySelector("[data-forca-senha]");
  var campo = document.getElementById("id_new_password1");
  if (!medidor || !campo) return;
  var texto = medidor.querySelector("[data-forca-texto]");
  var barras = medidor.querySelectorAll(".forca-senha__barra");
  var itens = document.querySelectorAll("[data-requisito]");
  var usuario = (medidor.getAttribute("data-usuario") || "").toLowerCase();
  function atualizar() {
    var valor = campo.value;
    var requisitos = {
      tamanho: valor.length >= 8,
      caixa: /[a-z]/.test(valor) && /[A-Z]/.test(valor),
      simbolos: /\d/.test(valor) || /[^A-Za-z0-9]/.test(valor),
      pessoais: valor !== "" && (!usuario || valor.toLowerCase().indexOf(usuario) === -1),
    };
    itens.forEach(function (item) {
      item.classList.toggle("is-ok", !!requisitos[item.getAttribute("data-requisito")]);
    });
    var pontos = Object.keys(requisitos).filter(function (chave) {
      return requisitos[chave];
    }).length;
    var nivel = !valor ? 0 : pontos <= 2 ? 1 : pontos === 3 ? 2 : 3;
    barras.forEach(function (barra, indice) {
      barra.classList.toggle("is-ativa", indice < nivel);
    });
    if (texto) {
      texto.textContent = ["", "Fraca", "Média", "Forte"][nivel];
      texto.setAttribute("data-nivel", String(nivel));
    }
  }
  campo.addEventListener("input", atualizar);
  atualizar();
})();

// A dica de rolagem lateral foi retirada em 14/09/2026: tabela que não cabe
// se conserta na largura, não com um aviso pedindo para arrastar.
