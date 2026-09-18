/*
 * Nome com sugestões (components/v32/nome_sugerido.html): texto livre que
 * sugere os cadastrados, no menu dos outros seletores.
 *
 * Digitar filtra sem ligar para acento e caixa; setas andam pela lista, Enter
 * escolhe a destacada e Esc fecha. Escolher preenche o nome e dispara
 * `ds:nome-sugerido` no campo, com os `data-*` da opção em `detail` — quem
 * precisa de mais (o cargo de um servidor, por exemplo) ouve esse evento.
 * Nada obriga a escolher: o nome digitado vale como está.
 */
(function () {
  "use strict";

  function semAcento(texto) {
    return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  }

  function ligar(raiz) {
    if (raiz.hasAttribute("data-nome-sugerido-ligado")) return;
    raiz.setAttribute("data-nome-sugerido-ligado", "1");
    var campo = raiz.querySelector("[data-nome-sugerido-campo]");
    var menu = raiz.querySelector("[data-nome-sugerido-menu]");
    var vazio = raiz.querySelector("[data-nome-sugerido-vazio]");
    var opcoes = Array.prototype.slice.call(raiz.querySelectorAll("[data-nome-sugerido-opcao]"));
    if (!campo || !menu) return;
    var ativa = null;

    function visiveis() { return opcoes.filter(function (o) { return !o.hidden; }); }

    function destacar(opcao) {
      if (ativa) ativa.classList.remove("is-active");
      ativa = opcao || null;
      if (ativa) {
        ativa.classList.add("is-active");
        ativa.scrollIntoView({ block: "nearest" });
        campo.setAttribute("aria-activedescendant", ativa.id || "");
      } else {
        campo.removeAttribute("aria-activedescendant");
      }
    }

    function filtrar() {
      var termo = semAcento(campo.value);
      opcoes.forEach(function (o) {
        o.hidden = Boolean(termo) && semAcento(o.getAttribute("data-busca")).indexOf(termo) === -1;
        o.setAttribute("aria-selected", semAcento(o.getAttribute("data-valor")) === termo ? "true" : "false");
      });
      var algum = visiveis().length > 0;
      if (vazio) vazio.hidden = algum || !termo;
      destacar(null);
    }

    function abrir() {
      if (!opcoes.length) return;
      filtrar();
      menu.hidden = false;
      raiz.classList.add("is-open");
      campo.setAttribute("aria-expanded", "true");
    }

    function fechar() {
      menu.hidden = true;
      raiz.classList.remove("is-open");
      campo.setAttribute("aria-expanded", "false");
      destacar(null);
    }

    function escolher(opcao) {
      campo.value = opcao.getAttribute("data-valor");
      fechar();
      var dados = {};
      Array.prototype.forEach.call(opcao.attributes, function (a) {
        if (a.name.indexOf("data-") === 0) dados[a.name.slice(5)] = a.value;
      });
      campo.dispatchEvent(new CustomEvent("ds:nome-sugerido", { bubbles: true, detail: dados }));
      campo.dispatchEvent(new Event("change", { bubbles: true }));
    }

    opcoes.forEach(function (opcao, indice) {
      opcao.id = campo.id + "_opcao_" + indice;
      // O mousedown não tira o foco do campo: a escolha acontece sem piscar.
      opcao.addEventListener("mousedown", function (evento) { evento.preventDefault(); });
      opcao.addEventListener("click", function () { escolher(opcao); });
      opcao.addEventListener("mousemove", function () { if (ativa !== opcao) destacar(opcao); });
    });

    campo.addEventListener("focus", abrir);
    campo.addEventListener("click", abrir);
    campo.addEventListener("input", function () { if (menu.hidden) abrir(); else filtrar(); });
    campo.addEventListener("keydown", function (evento) {
      var lista = visiveis();
      if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
        evento.preventDefault();
        if (menu.hidden) abrir();
        lista = visiveis();
        if (!lista.length) return;
        var i = lista.indexOf(ativa);
        i = evento.key === "ArrowDown" ? (i + 1) % lista.length : (i <= 0 ? lista.length - 1 : i - 1);
        destacar(lista[i]);
      } else if (evento.key === "Enter" && !menu.hidden && ativa && !ativa.hidden) {
        // Enter com uma sugestão destacada escolhe; sem destaque, segue o formulário.
        evento.preventDefault();
        escolher(ativa);
      } else if (evento.key === "Escape" && !menu.hidden) {
        evento.preventDefault();
        fechar();
      } else if (evento.key === "Tab") {
        fechar();
      }
    });
    document.addEventListener("click", function (evento) {
      if (!menu.hidden && !raiz.contains(evento.target)) fechar();
    });
  }

  function ligarTodos(escopo) {
    (escopo || document).querySelectorAll("[data-nome-sugerido]").forEach(ligar);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { ligarTodos(); });
  else ligarTodos();
})();
