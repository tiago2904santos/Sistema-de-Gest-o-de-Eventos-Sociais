/*
 * Quem já pediu antes: ao digitar o nome do solicitante, lista as pessoas de
 * pedidos anteriores; um clique preenche o nome e os demais dados do último
 * pedido dela (cargo, contato, órgão; telefone e e-mail nas Palestras).
 * Nada é preenchido sem o clique, e tudo continua editável.
 *
 * Contrato: <div data-sugestao-solicitante data-url="..." data-campo-nome="...">
 * no mesmo <form> do campo de nome. A URL responde {"resultados": [{"nome",
 * "detalhe", "pedidos", "campos": {nome_do_campo: valor}}]}.
 */
(function () {
  "use strict";

  function disparar(campo) {
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function el(tag, classe, texto) {
    var elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto) elemento.textContent = texto;
    return elemento;
  }

  function definir(campo, valor) {
    if (!campo || campo.disabled || campo.readOnly) return;
    if (campo.tagName === "SELECT") {
      var existe = Array.prototype.some.call(campo.options, function (o) {
        return o.value === String(valor) && !o.disabled;
      });
      if (!existe && valor !== "") return;
    }
    campo.value = valor;
    disparar(campo);
  }

  document.querySelectorAll("[data-sugestao-solicitante]").forEach(function (caixa) {
    var formulario = caixa.closest("form");
    if (!formulario) return;
    var nome = formulario.querySelector('[name="' + caixa.getAttribute("data-campo-nome") + '"]');
    if (!nome || nome.disabled || nome.readOnly) return;

    var espera = null;
    var pedido = 0;
    var aplicado = "";

    function esconder() {
      caixa.hidden = true;
      caixa.textContent = "";
    }

    function aplicar(item) {
      aplicado = item.nome;
      definir(nome, item.nome);
      Object.keys(item.campos || {}).forEach(function (chave) {
        var campo = formulario.querySelector('[name="' + chave + '"]');
        if (item.campos[chave] !== "") definir(campo, item.campos[chave]);
      });
      esconder();
    }

    function mostrar(resultados) {
      caixa.textContent = "";
      var atual = nome.value.trim().toLocaleLowerCase("pt-BR");
      // O nome já escolhido (ou digitado igual a um só resultado) não precisa de lista.
      resultados = resultados.filter(function (item) {
        return !(item.nome.toLocaleLowerCase("pt-BR") === atual && item.nome === aplicado);
      });
      if (!resultados.length) { esconder(); return; }
      caixa.appendChild(el("p", "sugestao-solicitante__titulo", "Já pediram antes — clique para preencher com os dados do último pedido:"));
      var lista = el("ul", "sugestao-solicitante__lista");
      resultados.forEach(function (item) {
        var li = el("li");
        var botao = el("button", "sugestao-solicitante__item");
        botao.type = "button";
        botao.appendChild(el("b", "", item.nome));
        var extra = [item.detalhe, item.pedidos > 1 ? item.pedidos + " pedidos" : ""].filter(Boolean).join(" · ");
        if (extra) botao.appendChild(el("small", "", extra));
        botao.addEventListener("click", function () { aplicar(item); nome.focus(); });
        li.appendChild(botao);
        lista.appendChild(li);
      });
      caixa.appendChild(lista);
      var fechar = el("button", "sugestao-solicitante__fechar", "Fechar");
      fechar.type = "button";
      fechar.addEventListener("click", esconder);
      caixa.appendChild(fechar);
      caixa.hidden = false;
    }

    function buscar() {
      var termo = nome.value.trim();
      var numero = ++pedido;
      if (termo.length < 2 || termo === aplicado) { esconder(); return; }
      fetch(caixa.getAttribute("data-url") + "?q=" + encodeURIComponent(termo), {
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      })
        .then(function (resposta) { return resposta.ok ? resposta.json() : null; })
        .then(function (dados) {
          if (dados && numero === pedido) mostrar(dados.resultados || []);
        })
        .catch(function () { /* sugestão é ajuda: sem ela, a tela segue igual */ });
    }

    // Só reage ao que a pessoa digita (o evento sintético dos preenchimentos não é "de verdade").
    nome.addEventListener("input", function (evento) {
      if (!evento.isTrusted) return;
      clearTimeout(espera);
      espera = setTimeout(buscar, 300);
    });
    nome.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape") esconder();
    });
  });
})();
