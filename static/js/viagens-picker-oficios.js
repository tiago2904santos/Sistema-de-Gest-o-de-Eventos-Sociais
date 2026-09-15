/**
 * Seletor de ofícios com busca no servidor — o `api_buscar_oficios` da origem.
 *
 * O servidor devolve até 30 resultados por vez; quem digita algo que casa com
 * mais do que isso refina o termo em vez de rolar. Cada ofício escolhido vira
 * uma linha com um campo oculto. Em `data-picker-unico`, escolher outro
 * substitui o anterior (cadastro de termo); sem ele, acumula (justificativas).
 *
 * Marcação esperada dentro de `[data-picker-oficios]`:
 *   [data-picker-busca]      input de busca
 *   [data-picker-resultados] lista de resultados
 *   [data-picker-escolhidos] <ul> dos escolhidos (linhas com data-id e o hidden)
 *   data-url-busca, data-limite, data-nome (nome do campo oculto), data-picker-unico
 */
(function () {
  "use strict";

  document.querySelectorAll("[data-picker-oficios]").forEach(function (picker) {
    var busca = picker.querySelector("[data-picker-busca]");
    var resultados = picker.querySelector("[data-picker-resultados]");
    var escolhidos = picker.querySelector("[data-picker-escolhidos]");
    if (!busca || !resultados || !escolhidos) return;
    var urlBusca = picker.getAttribute("data-url-busca");
    var limite = parseInt(picker.getAttribute("data-limite"), 10) || 30;
    var nomeCampo = picker.getAttribute("data-nome");
    var unico = picker.hasAttribute("data-picker-unico");
    var temporizador = null;
    var ultimoTermo = null;

    function ids() {
      return Array.prototype.map.call(escolhidos.querySelectorAll("li"), function (li) { return li.dataset.id; });
    }

    function fecharMenu() {
      resultados.hidden = true;
      resultados.innerHTML = "";
      busca.setAttribute("aria-expanded", "false");
    }

    function avisar() {
      picker.dispatchEvent(new CustomEvent("picker:mudou", { bubbles: true, detail: { ids: ids() } }));
    }

    function adicionar(item) {
      if (ids().indexOf(String(item.id)) !== -1) return;
      if (unico) escolhidos.innerHTML = "";
      var li = document.createElement("li");
      li.className = "multi-pick__escolhido";
      li.dataset.id = item.id;
      var oculto = document.createElement("input");
      oculto.type = "hidden";
      oculto.name = nomeCampo;
      oculto.value = item.id;
      var texto = document.createElement("span");
      texto.textContent = item.main;
      if (item.meta) {
        var meta = document.createElement("small");
        meta.textContent = item.meta;
        texto.appendChild(meta);
      }
      var remover = document.createElement("button");
      remover.type = "button";
      remover.className = "multi-pick__remover";
      remover.setAttribute("aria-label", "Remover " + item.main);
      remover.setAttribute("data-picker-remover", "");
      remover.textContent = "×";
      li.appendChild(oculto);
      li.appendChild(texto);
      li.appendChild(remover);
      escolhidos.appendChild(li);
      picker.classList.remove("is-invalid");
      avisar();
    }

    function mensagem(texto) {
      var p = document.createElement("p");
      p.className = "custom-select__vazio";
      p.textContent = texto;
      resultados.appendChild(p);
    }

    function renderizar(dados) {
      resultados.innerHTML = "";
      var itens = (dados.results || []).filter(function (item) { return ids().indexOf(String(item.id)) === -1; });
      if (!itens.length) mensagem("Nenhum ofício encontrado.");
      itens.forEach(function (item) {
        var botao = document.createElement("button");
        botao.type = "button";
        botao.className = "custom-select__opcao jt-opcao";
        botao.setAttribute("role", "option");
        var span = document.createElement("span");
        span.textContent = item.main;
        if (item.meta) {
          var meta = document.createElement("small");
          meta.textContent = item.meta;
          span.appendChild(meta);
        }
        botao.appendChild(span);
        botao.addEventListener("click", function () {
          adicionar(item);
          busca.value = "";
          fecharMenu();
          busca.focus();
        });
        resultados.appendChild(botao);
      });
      if (dados.truncado) mensagem("Mais de " + limite + " ofícios casam com a busca. Refine o termo.");
      resultados.hidden = false;
      busca.setAttribute("aria-expanded", "true");
    }

    function buscar() {
      var termo = busca.value.trim();
      if (termo === ultimoTermo) return;
      ultimoTermo = termo;
      fetch(urlBusca + "?q=" + encodeURIComponent(termo), { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(renderizar)
        .catch(function () {
          resultados.innerHTML = "";
          mensagem("Não foi possível buscar os ofícios agora.");
          resultados.hidden = false;
        });
    }

    busca.addEventListener("input", function () {
      clearTimeout(temporizador);
      temporizador = setTimeout(buscar, 250);
    });
    busca.addEventListener("focus", function () { ultimoTermo = null; buscar(); });
    busca.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape") fecharMenu();
      if (evento.key === "Enter") {
        evento.preventDefault();
        var primeiro = resultados.querySelector(".jt-opcao");
        if (primeiro) primeiro.click();
      }
    });
    document.addEventListener("click", function (evento) {
      if (!picker.contains(evento.target)) fecharMenu();
    });
    escolhidos.addEventListener("click", function (evento) {
      var botao = evento.target.closest("[data-picker-remover]");
      if (!botao) return;
      botao.closest("li").remove();
      avisar();
      busca.focus();
    });
  });
})();
