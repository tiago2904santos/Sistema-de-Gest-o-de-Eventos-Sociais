(function () {
  "use strict";

  var dialog = document.querySelector("[data-servidor-dialog]");
  if (dialog) {
    var excluirForm = dialog.querySelector("[data-servidor-delete-form]");
    document.querySelectorAll("[data-servidor-excluir]").forEach(function (botao) {
      botao.addEventListener("click", function (event) {
        if (typeof dialog.showModal !== "function") return;
        event.preventDefault();
        excluirForm.action = botao.dataset.deleteUrl;
        dialog.querySelector("[data-servidor-nome]").textContent = botao.dataset.nome;
        dialog.showModal();
      });
    });
    dialog.querySelector("[data-servidor-fechar]").addEventListener("click", function () {
      dialog.close();
    });
  }

  var form = document.querySelector("[data-servidor-form]");
  if (!form) return;
  form.querySelector("[data-servidor-erros]")?.focus();
  var chave = "viagens:servidor:retorno:" + window.location.pathname;
  var nomes = ["nome", "cargo", "cpf", "rg", "telefone", "unidade"];
  try {
    var salvo = window.sessionStorage.getItem(chave);
    window.sessionStorage.removeItem(chave);
    if (salvo && !form.querySelector('[role="alert"]')) {
      var rascunho = JSON.parse(salvo);
      nomes.forEach(function (nome) {
        var campo = form.elements.namedItem(nome);
        if (campo && typeof rascunho[nome] === "string") {
          campo.value = rascunho[nome];
          campo.dispatchEvent(new Event("change", { bubbles: true }));
          campo.dispatchEvent(new Event("input", { bubbles: true }));
        }
      });
    }
  } catch (err) { /* O formulário continua utilizável sem armazenamento local. */ }

  form.querySelectorAll("[data-servidor-gerenciar]").forEach(function (link) {
    link.addEventListener("click", function () {
      var dados = {};
      nomes.forEach(function (nome) { dados[nome] = form.elements.namedItem(nome).value; });
      try { window.sessionStorage.setItem(chave, JSON.stringify(dados)); } catch (err) { /* Sem armazenamento disponível. */ }
    });
  });
})();
