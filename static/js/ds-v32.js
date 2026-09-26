/**
 * Comportamentos próprios das páginas no Design System V3.2.
 * Complementa o app.js (menus, filtros, validação) sem substituí-lo.
 */
/**
 * Componente global upload_anexos: seleção por clique ou arrastar, lista
 * acumulada e envio pelo formulário associado quando configurado.
 */
(function () {
  "use strict";

  function tamanhoLegivel(bytes) {
    if (bytes >= 1048576) {
      return (bytes / 1048576).toFixed(1).replace(".", ",") + " MB";
    }
    return Math.max(1, Math.round(bytes / 1024)) + " KB";
  }

  document.querySelectorAll("[data-upload-anexos]").forEach(function (bloco) {
    var input = bloco.querySelector('input[type="file"]');
    var lista = bloco.querySelector(".upload-anexos__lista");
    var vazio = bloco.querySelector(".upload-anexos__vazio");
    var erro = bloco.querySelector("[data-upload-erro]");
    if (!input || !lista) return;

    // Em inputs múltiplos, cada "Escolher arquivos" SOMA à seleção anterior
    // (o navegador sozinho substituiria a lista inteira).
    var acumulados = [];

    function sincronizarInput() {
      var dt = new DataTransfer();
      acumulados.forEach(function (arquivo) {
        dt.items.add(arquivo);
      });
      input.files = dt.files;
    }

    function removerArquivo(indice) {
      acumulados.splice(indice, 1);
      sincronizarInput();
      render();
    }

    function aoSelecionar() {
      if (erro) erro.hidden = true;
      var novos = Array.prototype.slice.call(input.files);
      if (!input.multiple) {
        acumulados = novos;
      } else {
        novos.forEach(function (novo) {
          var repetido = acumulados.some(function (existente) {
            return (
              existente.name === novo.name &&
              existente.size === novo.size &&
              existente.lastModified === novo.lastModified
            );
          });
          if (!repetido) acumulados.push(novo);
        });
        sincronizarInput();
      }
      render();
      if (input.files.length && input.form && input.hasAttribute("data-anexo-enviar-ao-selecionar")) {
        input.form.requestSubmit();
      }
    }

    function render() {
      lista.innerHTML = "";
      var arquivos = acumulados;
      if (vazio) vazio.hidden = arquivos.length > 0;
      arquivos.forEach(function (arquivo, indice) {
        var item = document.createElement("li");
        item.className = "upload-anexos__item";

        var nome = document.createElement("span");
        nome.className = "upload-anexos__nome";
        nome.textContent = arquivo.name;

        var meta = document.createElement("span");
        meta.className = "upload-anexos__meta";
        meta.textContent = tamanhoLegivel(arquivo.size);

        var remover = document.createElement("button");
        remover.type = "button";
        remover.className = "upload-anexos__remover";
        remover.setAttribute("aria-label", "Remover " + arquivo.name);
        remover.textContent = "×";
        remover.addEventListener("click", function () {
          removerArquivo(indice);
        });

        item.appendChild(nome);
        item.appendChild(meta);
        item.appendChild(remover);
        lista.appendChild(item);
      });
    }

    // Arrastar e soltar na área tracejada soma à seleção, como o input.
    var zona = bloco.querySelector("[data-upload-dropzone]");
    if (zona) {
      ["dragenter", "dragover"].forEach(function (evento) {
        zona.addEventListener(evento, function (e) {
          e.preventDefault();
          zona.classList.add("is-arrastando");
        });
      });
      ["dragleave", "drop"].forEach(function (evento) {
        zona.addEventListener(evento, function (e) {
          e.preventDefault();
          zona.classList.remove("is-arrastando");
        });
      });
      zona.addEventListener("drop", function (e) {
        var soltos = e.dataTransfer && e.dataTransfer.files;
        if (!soltos || !soltos.length) return;
        if (!input.multiple && soltos.length > 1) {
          if (erro) {
            erro.textContent = "Selecione um arquivo por vez.";
            erro.hidden = false;
          }
          return;
        }
        var dt = new DataTransfer();
        Array.prototype.forEach.call(soltos, function (arquivo) {
          dt.items.add(arquivo);
        });
        input.files = dt.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
    }

    input.addEventListener("change", aoSelecionar);
    render();
  });
})();

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
// Cadastros de apoio: criar e editar na listagem, com validação do mesmo ModelForm.
(function () {
  "use strict";
  var modal = document.querySelector("[data-cadastro-dialog]");
  if (!modal) return;
  var origem = null;
  var requisicao = null;
  var salvando = false;

  function preparar(html) {
    if (typeof html === "string") modal.innerHTML = html;
    if (window.DS && window.DS.aprimorar) window.DS.aprimorar(modal);
    if (!modal.open) modal.showModal();
    var foco = modal.querySelector("[data-resumo-erros], input:not([type=hidden]), textarea, select");
    if (foco) foco.focus();
  }
  function fechar() {
    if (salvando) return;
    if (requisicao) requisicao.abort();
    modal.close();
  }
  modal.addEventListener("close", function () {
    if (!origem || !origem.isConnected) return;
    // Link dentro de um menu de linha já fechado: o foco volta ao botão do menu.
    var menu = origem.closest("[data-menu]");
    var gatilho = menu && menu.querySelector("[data-menu-gatilho]");
    (gatilho || origem).focus();
  });
  modal.addEventListener("cancel", function (evento) {
    // Escape recolhe primeiro o combobox aberto; a segunda tecla fecha o modal.
    if (salvando || modal.querySelector(".custom-select.is-open")) evento.preventDefault();
  });
  modal.addEventListener("keydown", function (evento) {
    var aberto = modal.querySelector(".custom-select.is-open");
    if (evento.key === "Escape" && aberto) {
      evento.preventDefault();
      var gatilho = aberto.querySelector("button.custom-select__trigger");
      if (gatilho) gatilho.click();
    }
  });
  modal.addEventListener("click", function (evento) {
    if (evento.target.closest("[data-cadastro-fechar]")) fechar();
  });
  document.querySelectorAll("[data-cadastro-modal]").forEach(function (link) {
    link.addEventListener("click", function (evento) {
      if (evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey || evento.button) return;
      evento.preventDefault();
      origem = link;
      if (requisicao) requisicao.abort();
      requisicao = new AbortController();
      preparar('<header class="mo__topo"><h2 id="cadastro-modal-titulo">Carregando cadastro…</h2><button type="button" class="mo__fechar" data-cadastro-fechar aria-label="Fechar cadastro">×</button></header><div class="mo__corpo" role="status">Aguarde…</div>');
      fetch(link.href, { headers: { "X-Cadastro-Modal": "1" }, signal: requisicao.signal })
        .then(function (resposta) {
          if (!resposta.ok || resposta.redirected) throw new Error("acesso");
          return resposta.text();
        })
        .then(preparar)
        .catch(function (erro) {
          if (erro.name !== "AbortError") window.location.assign(link.href);
        });
    });
  });
  modal.addEventListener("submit", function (evento) {
    var form = evento.target.closest("[data-cadastro-form]");
    if (!form) return;
    evento.preventDefault();
    if (salvando) return;
    salvando = true;
    var dados = new FormData(form);
    form.setAttribute("aria-busy", "true");
    form.querySelectorAll("button").forEach(function (botao) { botao.disabled = true; });
    fetch(form.action, { method: "POST", body: dados, headers: { "X-Cadastro-Modal": "1" } })
      .then(function (resposta) {
        if (!resposta.ok || resposta.redirected) throw new Error("Não foi possível salvar. Verifique sua conexão e tente novamente.");
        if ((resposta.headers.get("Content-Type") || "").indexOf("application/json") !== -1) {
          return resposta.json().then(function (resultado) {
            if (!resultado.ok) throw new Error("Não foi possível salvar.");
            window.location.reload();
          });
        }
        return resposta.text().then(preparar);
      })
      .catch(function (erro) {
        var falha = form.querySelector("[data-cadastro-falha]");
        if (falha) { falha.textContent = erro.message; falha.hidden = false; }
      })
      .finally(function () {
        salvando = false;
        form.removeAttribute("aria-busy");
        form.querySelectorAll("button").forEach(function (botao) { botao.disabled = false; });
      });
  });
  if (modal.hasAttribute("data-cadastro-inicial")) {
    preparar();
    var endereco = new URL(window.location.href);
    endereco.pathname = modal.getAttribute("data-cadastro-lista");
    endereco.searchParams.delete("novo");
    endereco.searchParams.delete("editar");
    window.history.replaceState(null, "", endereco);
  }
})();
