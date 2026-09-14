/* Prévia da diária: campos desabilitados; o modelo deriva os valores gravados. */
(() => {
  const base = document.querySelector("[data-diaria-base]");
  if (base) {
    const campos = [[document.getElementById("id_diaria_calc_15"), 0.15], [document.getElementById("id_diaria_calc_30"), 0.30]];
    const atualizar = () => {
      const valor = parseFloat(base.value.replace(",", "."));
      campos.forEach(([campo, fator]) => {
        if (campo) campo.value = !Number.isFinite(valor) || valor <= 0 ? "" : "R$ " + (Math.round(valor * fator * 100) / 100).toFixed(2).replace(".", ",");
      });
    };
    base.addEventListener("input", atualizar);
    atualizar();
  }
  document.querySelector("[data-resumo-erros]")?.focus();
})();
