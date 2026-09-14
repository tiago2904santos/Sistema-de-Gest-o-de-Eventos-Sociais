/* Confirmação de exclusão dos cadastros de viagens: o diálogo recebe o nome
   e a URL do registro escolhido na linha. */
(() => {
  const dialog = document.querySelector("[data-catalogo-dialog]");
  if (!dialog || typeof dialog.showModal !== "function") return;
  document.querySelectorAll("[data-catalogo-excluir]").forEach(botao => {
    botao.addEventListener("click", event => {
      event.preventDefault();
      dialog.querySelector("[data-catalogo-nome]").textContent = botao.dataset.nome;
      dialog.querySelector("[data-catalogo-delete-form]").action = botao.dataset.deleteUrl;
      dialog.showModal();
    });
  });
  dialog.querySelector("[data-catalogo-fechar]").addEventListener("click", () => dialog.close());
})();
