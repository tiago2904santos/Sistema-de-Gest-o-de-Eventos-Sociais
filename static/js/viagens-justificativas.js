/**
 * Justificativas — inclusão rápida.
 *
 * O seletor de ofícios busca no servidor (`api/oficios/?q=`), que devolve até
 * 30 resultados por vez, como o seletor da origem. Cada ofício escolhido vira
 * uma linha com um campo oculto `oficios`; o modelo escolhido preenche o
 * texto, como no formulário do ofício.
 */
(function () {
  "use strict";

  var form = document.querySelector("[data-jt-rapida]");
  if (!form) return;

  var picker = form.querySelector("[data-jt-picker]");
  var busca = form.querySelector("[data-jt-busca]");
  var resultados = form.querySelector("[data-jt-resultados]");
  var escolhidos = form.querySelector("[data-jt-escolhidos]");
  var dica = form.querySelector("[data-jt-dica]");
  var urlBusca = form.getAttribute("data-url-busca");
  var limite = parseInt(form.getAttribute("data-limite"), 10) || 30;
  var nomeCampo = "rapida-oficios";
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

  function adicionar(item) {
    if (ids().indexOf(String(item.id)) !== -1) return;
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
    remover.setAttribute("data-jt-remover", "");
    remover.textContent = "×";
    li.appendChild(oculto);
    li.appendChild(texto);
    li.appendChild(remover);
    escolhidos.appendChild(li);
    picker.classList.remove("is-invalid");
  }

  function renderizar(dados) {
    resultados.innerHTML = "";
    var itens = (dados.results || []).filter(function (item) { return ids().indexOf(String(item.id)) === -1; });
    if (!itens.length) {
      var vazio = document.createElement("p");
      vazio.className = "custom-select__vazio";
      vazio.textContent = "Nenhum ofício encontrado.";
      resultados.appendChild(vazio);
    }
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
    if (dados.truncado) {
      var aviso = document.createElement("p");
      aviso.className = "custom-select__vazio";
      aviso.textContent = "Mais de " + limite + " ofícios casam com a busca. Refine o termo.";
      resultados.appendChild(aviso);
    }
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
        var erro = document.createElement("p");
        erro.className = "custom-select__vazio";
        erro.textContent = "Não foi possível buscar os ofícios agora.";
        resultados.appendChild(erro);
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
    var botao = evento.target.closest("[data-jt-remover]");
    if (!botao) return;
    botao.closest("li").remove();
    busca.focus();
  });

  // Modelo → texto, como no formulário do ofício.
  var modelos = {};
  try { modelos = JSON.parse(document.getElementById("oficio-modelos-texto").textContent); } catch (erro) { modelos = {}; }
  var seletor = document.getElementById("id_rapida-modelo");
  var texto = document.getElementById("id_rapida-texto");
  if (seletor && texto) {
    seletor.addEventListener("change", function () {
      var valor = (modelos["rapida-modelo"] || {})[seletor.value];
      if (valor !== undefined) {
        texto.value = valor;
        texto.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
  }

  // Abre o painel já focado na busca quando o botão do cabeçalho o expande.
  document.querySelectorAll('[data-expande="#inclusao-rapida"]').forEach(function (botao) {
    botao.addEventListener("click", function () {
      var painel = document.getElementById("inclusao-rapida");
      if (painel && !painel.hidden) setTimeout(function () { busca.focus(); }, 50);
    });
  });
})();
