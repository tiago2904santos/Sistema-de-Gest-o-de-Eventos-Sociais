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

  var seletoresAbertos = [];

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

  document.addEventListener("pointerdown", function (event) {
    seletoresAbertos.forEach(function (instancia) {
      if (!instancia.wrapper.contains(event.target)) fecharSeletor(instancia, false);
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
  }

  formulario.addEventListener("input", atualizarAcompanhamento);
  formulario.addEventListener("change", atualizarAcompanhamento);
  atualizarAcompanhamento();
})();
