/* Inclusão dos catálogos: o mesmo botão expande, recolhe vazio ou salva. */
(() => {
  const form = document.querySelector("[data-catalogo-form]");
  const toggle = document.querySelector("[data-catalogo-toggle]");
  if (form && toggle && !form.hasAttribute("data-estado-form")) {
    const nome = form.elements.nome;
    const label = toggle.querySelector("[data-catalogo-rotulo]");
    const atualizar = () => {
      const preenchido = !form.hidden && Boolean(nome.value.trim());
      label.textContent = preenchido ? toggle.dataset.salvar : toggle.dataset.cadastrar;
      toggle.classList.toggle("is-filled", preenchido);
    };
    toggle.addEventListener("click", () => {
      if (form.hidden) {
        form.hidden = false;
        toggle.setAttribute("aria-expanded", "true");
      } else if (nome.value.trim()) {
        form.requestSubmit();
      } else {
        form.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
        form.reset();
      }
      atualizar();
    });
    form.addEventListener("input", atualizar);
    atualizar();
    form.querySelector("[data-catalogo-erros]")?.focus();
  }
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
