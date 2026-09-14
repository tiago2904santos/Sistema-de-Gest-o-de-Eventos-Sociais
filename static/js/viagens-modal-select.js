/* Menu de seleção dentro do modal de cadastro: flutua sobre o formulário em
   vez de empurrar os campos de baixo.

   Como o diálogo tem rolagem própria, um menu absoluto seria cortado nas
   bordas. Ao abrir, medimos o espaço acima e abaixo do campo dentro do
   diálogo, abrimos para o lado com mais folga e limitamos a altura da lista
   ao que cabe ali. */
(() => {
  const modal = document.querySelector("[data-cadastro-dialog].v32-cadastro-modal--larga");
  if (!modal) return;

  const FOLGA = 12;
  const ALTURA_MINIMA = 120;
  const ALTURA_MAXIMA = 240;

  function posicionar(menu) {
    const campo = menu.closest(".custom-select");
    const lista = menu.querySelector(".custom-select__lista");
    if (!campo || !lista) return;
    const area = campo.getBoundingClientRect();
    const caixa = modal.getBoundingClientRect();
    const abaixo = caixa.bottom - area.bottom - FOLGA;
    const acima = area.top - caixa.top - FOLGA;
    const paraCima = abaixo < ALTURA_MINIMA && acima > abaixo;
    menu.classList.toggle("custom-select__menu--acima", paraCima);
    const disponivel = Math.max(ALTURA_MINIMA, Math.min(ALTURA_MAXIMA, paraCima ? acima : abaixo));
    // O menu tem 6px de padding em cima e embaixo; a lista é quem rola.
    lista.style.maxHeight = `${disponivel - 12}px`;
  }

  // O componente do DS apenas alterna `hidden`; é esse o momento de medir.
  new MutationObserver((mudancas) => {
    mudancas.forEach((mudanca) => {
      const menu = mudanca.target;
      if (menu.matches && menu.matches("[data-custom-select-menu]") && !menu.hidden) {
        posicionar(menu);
      }
    });
  }).observe(modal, { attributes: true, attributeFilter: ["hidden"], subtree: true });
})();
