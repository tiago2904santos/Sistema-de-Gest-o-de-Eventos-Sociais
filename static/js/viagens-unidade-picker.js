/* Lotação dos cadastros de Viagens: componente DS com pesquisa e teclado do GV. */
(() => {
  "use strict";
  document.querySelectorAll("[data-unidade-picker]").forEach(root => {
    if (root.classList.contains("is-enhanced")) return;
    const native = root.querySelector(".custom-select__native");
    const search = root.querySelector("[data-custom-select-search]");
    const menu = root.querySelector("[data-custom-select-menu]");
    const clear = root.querySelector("[data-unidade-limpar]");
    const empty = root.querySelector("[data-custom-select-empty]");
    const options = [...root.querySelectorAll(".custom-select__opcao")];
    const normalize = text => String(text || "").normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR").trim();
    let query = "";
    let active = -1;
    const label = option => [...native.options].find(item => item.value === option.dataset.value)?.text || "";
    const visible = () => options.filter(option => !option.hidden);
    const close = () => {
      menu.hidden = true;
      root.classList.remove("is-open");
      search.setAttribute("aria-expanded", "false");
      search.removeAttribute("aria-activedescendant");
    };
    const render = () => {
      const term = normalize(query);
      options.forEach(option => {
        const text = label(option) + " " + (option.querySelector("small")?.textContent || "");
        option.hidden = !term || !normalize(text).includes(term);
        option.setAttribute("aria-selected", String(native.value === option.dataset.value));
        option.classList.toggle("is-selected", native.value === option.dataset.value);
      });
      const results = visible();
      active = Math.min(active, results.length - 1);
      options.forEach(option => option.classList.toggle("is-active", option === results[active]));
      empty.hidden = !query || results.length > 0;
      clear.hidden = !search.value || native.disabled;
      if (!menu.hidden && results[active]) search.setAttribute("aria-activedescendant", results[active].id);
      else search.removeAttribute("aria-activedescendant");
    };
    const open = () => {
      if (!query || native.disabled) { close(); return; }
      menu.hidden = false;
      root.classList.add("is-open");
      search.setAttribute("aria-expanded", "true");
      render();
    };
    const sync = () => {
      search.value = native.value ? native.options[native.selectedIndex]?.text || "" : "";
      root.classList.toggle("has-value", Boolean(native.value));
      render();
    };
    const change = () => {
      native.dispatchEvent(new Event("input", {bubbles: true}));
      native.dispatchEvent(new Event("change", {bubbles: true}));
    };
    const select = option => {
      if (!option || native.disabled) return;
      native.value = option.dataset.value;
      query = "";
      active = -1;
      change();
      close();
      search.focus();
    };
    options.forEach((option, index) => {
      option.id = native.id + "_unidade_" + index;
      option.addEventListener("mousedown", event => event.preventDefault());
      option.addEventListener("click", () => select(option));
    });
    search.addEventListener("input", () => {
      query = search.value;
      active = 0;
      render();
      open();
    });
    search.addEventListener("focus", open);
    search.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        select(visible()[Math.max(active, 0)]);
      } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        active = event.key === "ArrowDown" ? Math.min(active + 1, visible().length - 1) : Math.max(active - 1, 0);
        open();
      } else if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    });
    clear.addEventListener("mousedown", event => event.preventDefault());
    clear.addEventListener("click", () => {
      native.value = "";
      query = "";
      active = -1;
      change();
      close();
      search.focus();
    });
    document.addEventListener("click", event => { if (!root.contains(event.target)) close(); });
    native.addEventListener("change", sync);
    native.addEventListener("focus", () => search.focus());
    root.classList.add("is-enhanced");
    native.tabIndex = -1;
    native.setAttribute("aria-hidden", "true");
    search.disabled = native.disabled;
    sync();
  });
})();
