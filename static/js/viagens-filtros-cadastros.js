/* As buscas de cadastros consultam todas as páginas após 1 s sem digitação.
   A marca de foco é consumida uma vez e não armazena o texto pesquisado. */
(() => {
  document.querySelectorAll("[data-cadastro-busca]").forEach(form => {
    const busca = form.querySelector('[name="q"]');
    if (!busca) return;
    const chave = "viagens:cadastro:foco:" + window.location.pathname;
    let temporizador;
    try {
      const restaurar = sessionStorage.getItem(chave) === "1";
      sessionStorage.removeItem(chave);
      if (restaurar) {
        busca.focus();
        busca.setSelectionRange(busca.value.length, busca.value.length);
      }
    } catch (_) { /* Buscar continua disponível sem armazenamento local. */ }

    busca.addEventListener("input", () => {
      clearTimeout(temporizador);
      temporizador = setTimeout(() => {
        try { sessionStorage.setItem(chave, "1"); } catch (_) { /* Sem armazenamento. */ }
        form.requestSubmit();
      }, 1000);
    });
    form.addEventListener("submit", () => clearTimeout(temporizador));
  });
})();
