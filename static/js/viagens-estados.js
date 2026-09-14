/* O editor do Estado ocupa os mesmos três campos da inclusão rápida. */
(() => {
  const form = document.querySelector('[data-catalogo-form]');
  const toggle = document.querySelector('[data-catalogo-toggle]');
  if (!form || !toggle) return;
  const criarUrl = form.action;
  const campos = [form.elements.nome, form.elements.sigla, form.elements.codigo_ibge];
  const preenchido = () => campos.filter(campo => campo.required).every(campo => campo.value.trim());
  const atualizar = () => {
    toggle.querySelector('[data-catalogo-rotulo]').textContent = preenchido() ? 'Salvar estado' : 'Cadastrar estado';
    toggle.classList.toggle('is-filled', preenchido());
  };
  toggle.addEventListener('click', () => {
    if (form.hidden) {
      form.hidden = false;
      toggle.setAttribute('aria-expanded', 'true');
    } else if (preenchido()) {
      form.requestSubmit();
    } else {
      form.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      form.action = criarUrl;
      campos.forEach(campo => { campo.value = ''; });
      atualizar();
    }
  });
  form.addEventListener('input', atualizar);
  form.querySelector('[data-catalogo-erros]')?.focus();
  document.querySelectorAll('[data-estado-editar]').forEach(button => {
    button.addEventListener('click', () => {
      form.action = button.dataset.estadoEditar;
      form.elements.nome.value = button.dataset.nome;
      form.elements.sigla.value = button.dataset.sigla;
      form.elements.codigo_ibge.value = button.dataset.codigo;
      form.hidden = false;
      toggle.hidden = false;
      toggle.setAttribute('aria-expanded', 'true');
      toggle.querySelector('[data-catalogo-rotulo]').textContent = 'Cadastrar estado';
      form.elements.nome.focus();
    });
  });
})();
