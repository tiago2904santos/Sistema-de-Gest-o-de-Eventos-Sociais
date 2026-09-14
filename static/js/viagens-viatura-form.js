/* Seleção de motoristas e retorno dos cadastros sem perder a viatura em edição. */
(() => {
  const form = document.querySelector("[data-viatura-form]");
  if (!form) return;
  const root = form.querySelector("[data-viatura-pessoas]");
  const search = root.querySelector('[name="busca_motoristas"]');
  const menu = root.querySelector("[data-pessoas-opcoes]");
  const clear = root.querySelector("[data-pessoas-limpar]");
  const options = [...root.querySelectorAll("[data-pessoa-opcao]")];
  const cards = [...root.querySelectorAll("[data-pessoa-cartao]")];
  const normalize = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR").trim();
  let active = -1;
  search.setAttribute("role", "combobox");
  search.setAttribute("aria-autocomplete", "list");
  search.setAttribute("aria-controls", menu.id);
  search.setAttribute("aria-expanded", "false");
  const close = () => {
    menu.hidden = true;
    search.setAttribute("aria-expanded", "false");
    search.removeAttribute("aria-activedescendant");
    options.forEach(option => option.classList.remove("is-active"));
  };
  const highlight = () => {
    const visible = options.filter(option => !option.hidden);
    active = Math.min(active, visible.length - 1);
    options.forEach(option => option.classList.toggle("is-active", option === visible[active]));
    if (!menu.hidden && visible[active]) search.setAttribute("aria-activedescendant", visible[active].id);
    else search.removeAttribute("aria-activedescendant");
  };
  const filter = () => {
    const query = normalize(search.value);
    let count = 0;
    options.forEach(option => {
      option.classList.remove("is-active");
      option.hidden = !query || option.getAttribute("aria-selected") === "true" || !option.dataset.busca.includes(query);
      if (!option.hidden) count++;
    });
    menu.hidden = !query;
    clear.hidden = !query;
    root.querySelector("[data-pessoas-sem-resultado]").hidden = count > 0;
    search.setAttribute("aria-expanded", String(Boolean(query)));
    highlight();
  };
  const sync = () => {
    options.forEach(option => {
      const card = cards.find(item => item.dataset.pessoaCartao === option.dataset.pessoaOpcao);
      option.setAttribute("aria-selected", String(!card.querySelector("input").disabled));
      card.hidden = card.querySelector("input").disabled;
    });
    root.querySelector("[data-pessoas-vazio]").hidden = cards.some(card => !card.hidden);
  };
  const select = id => {
    const card = cards.find(item => item.dataset.pessoaCartao === id);
    card.querySelector("input").disabled = false;
    sync();
    search.value = "";
    active = -1;
    clear.hidden = true;
    close();
    search.focus();
  };
  options.forEach(option => option.addEventListener("click", () => select(option.dataset.pessoaOpcao)));
  root.querySelectorAll("[data-pessoa-remover]").forEach(button => button.addEventListener("click", () => {
    cards.find(card => card.dataset.pessoaCartao === button.dataset.pessoaRemover).querySelector("input").disabled = true;
    sync(); filter(); search.focus();
  }));
  search.addEventListener("input", () => { active = 0; filter(); });
  search.addEventListener("focus", filter);
  clear.addEventListener("mousedown", event => event.preventDefault());
  clear.addEventListener("click", () => { search.value = ""; active = -1; filter(); search.focus(); });
  search.addEventListener("keydown", event => {
    const visible = options.filter(option => !option.hidden);
    if (event.key === "Escape") { event.preventDefault(); close(); }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      // O GV reabre com as setas e mantém o cursor nos limites da lista.
      active = event.key === "ArrowDown" ? Math.min(active + 1, visible.length - 1) : Math.max(active - 1, 0);
      filter();
      visible[active]?.scrollIntoView({block:"nearest"});
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (visible.length) select(visible[Math.max(0, active)].dataset.pessoaOpcao);
    }
  });
  document.addEventListener("click", event => { if (!root.contains(event.target)) close(); });
  const key = "viagens:viatura:retorno:" + window.location.pathname;
  const names = ["placa", "modelo", "tipo", "combustivel", "unidade"];
  try {
    const raw = sessionStorage.getItem(key);
    sessionStorage.removeItem(key);
    if (raw && !form.querySelector('[role="alert"]')) {
      const draft = JSON.parse(raw);
      names.forEach(name => {
        if (typeof draft[name] !== "string") return;
        const input = form.elements.namedItem(name);
        input.value = draft[name];
        input.dispatchEvent(new Event("change", {bubbles:true}));
        input.dispatchEvent(new Event("input", {bubbles:true}));
      });
      if (Array.isArray(draft.motoristas)) cards.forEach(card => {
        card.querySelector("input").disabled = !draft.motoristas.includes(card.dataset.pessoaCartao);
      });
    }
  } catch (_) { /* A gravação normal permanece disponível sem sessionStorage. */ }
  sync();
  form.querySelectorAll("[data-viatura-gerenciar]").forEach(link => link.addEventListener("click", () => {
    const draft = Object.fromEntries(names.map(name => [name, form.elements.namedItem(name).value]));
    draft.motoristas = cards.filter(card => !card.querySelector("input").disabled).map(card => card.dataset.pessoaCartao);
    try { sessionStorage.setItem(key, JSON.stringify(draft)); } catch (_) {}
  }));
  // A pesquisa do seletor não faz parte do cadastro enviado ao servidor.
  form.addEventListener("submit", () => { search.disabled = true; });
  form.querySelector("[data-viatura-erros]")?.focus();
})();
