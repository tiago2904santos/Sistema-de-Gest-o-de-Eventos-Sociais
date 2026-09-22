/*
 * Realce deslizante das etapas e das abas dos documentos (`.vg-trilho`): um
 * grafite só, posto sob o item ativo por --x/--y/--w/--h. Na primeira pintura
 * ele nasce no lugar (`sem-anim`); nas trocas, desliza. Na etapa, o clique
 * move o realce e segue para a página logo depois, para o movimento aparecer.
 */
(function () {
  "use strict";

  function ativoDe(trilho) {
    // A etapa atual pode ser um link (painel da viagem) ou um texto
    // (acompanhamento da solicitação, que não navega).
    return trilho.querySelector("input:checked + span") || trilho.querySelector(".is-atual > a, .is-atual > .vg-stepper__passo");
  }

  function posicionar(trilho, alvo) {
    alvo = alvo || ativoDe(trilho);
    trilho.classList.toggle("tem-realce", !!alvo);
    if (!alvo) return;
    var caixa = trilho.getBoundingClientRect();
    var r = alvo.getBoundingClientRect();
    trilho.style.setProperty("--x", (r.left - caixa.left) + "px");
    trilho.style.setProperty("--y", (r.top - caixa.top) + "px");
    trilho.style.setProperty("--w", r.width + "px");
    trilho.style.setProperty("--h", r.height + "px");
  }

  document.querySelectorAll("[data-vg-trilho]").forEach(function (trilho) {
    posicionar(trilho);
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () { trilho.classList.remove("sem-anim"); });
    });

    trilho.addEventListener("change", function () { posicionar(trilho); });

    trilho.addEventListener("click", function (evento) {
      var link = evento.target.closest(".vg-stepper__passo");
      // Etapa que não navega (a solicitação usa <span>) não tem para onde ir.
      if (!link || !link.href || evento.defaultPrevented || evento.button !== 0 || evento.metaKey || evento.ctrlKey || evento.shiftKey || evento.altKey) return;
      var item = link.parentElement;
      if (item.classList.contains("is-atual")) return;
      evento.preventDefault();
      var atual = trilho.querySelector(".is-atual");
      if (atual) atual.classList.remove("is-atual");
      item.classList.add("is-atual");
      posicionar(trilho, link);
      window.setTimeout(function () { window.location.href = link.href; }, 220);
    });

    // A grade muda de colunas com a largura: o realce acompanha sem animar.
    var espera = null;
    window.addEventListener("resize", function () {
      trilho.classList.add("sem-anim");
      posicionar(trilho);
      window.clearTimeout(espera);
      espera = window.setTimeout(function () { trilho.classList.remove("sem-anim"); }, 100);
    });
  });
})();

/* Etapa 4: diálogo de anexar documentos de solicitação (aberto pelo menu "Novo"). */
(function () {
  "use strict";

  var dialogo = document.querySelector("[data-vg-anexar-dialogo]");
  if (!dialogo) return;
  var arquivo = dialogo.querySelector("[data-vg-anexar-arquivo]");
  var rotulo = dialogo.querySelector("[data-vg-anexar-rotulo]");
  var enviar = dialogo.querySelector("[data-vg-anexar-enviar]");

  function atualizar() {
    var nomes = Array.prototype.map.call(arquivo.files || [], function (f) { return f.name; });
    rotulo.textContent = nomes.length ? nomes.join(", ") : "Nenhum arquivo escolhido";
    enviar.disabled = !nomes.length;
  }

  document.addEventListener("click", function (evento) {
    if (evento.target.closest("[data-vg-anexar-abrir]")) {
      arquivo.value = "";
      atualizar();
      dialogo.showModal();
    }
  });
  dialogo.querySelector("[data-vg-anexar-fechar]").addEventListener("click", function () { dialogo.close(); });
  arquivo.addEventListener("change", atualizar);
})();
