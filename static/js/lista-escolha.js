/**
 * Lista de escolha única com busca — a marcação de `components/v32/lista_escolha.html`.
 *
 * A linha inteira é o rótulo do rádio, então clicar em qualquer ponto escolhe;
 * clicar na linha já escolhida desfaz, que um rádio sozinho não desmarca. A
 * busca olha o `data-busca` da linha, que carrega também o que ela não mostra,
 * e a escolhida nunca some do filtro: sumir daria a impressão de ter perdido o
 * vínculo.
 */
(function () {
  "use strict";

  function ligar(lista) {
    if (lista.dataset.listaLigada) return;
    lista.dataset.listaLigada = "1";
    var nome = lista.getAttribute("data-lista-escolha");
    var busca = document.querySelector('[data-lista-busca="' + nome + '"]');

    function linhas() {
      return Array.prototype.slice.call(lista.querySelectorAll("[data-lista-item]"));
    }

    function radioDe(linha) {
      return linha.querySelector('input[name="' + nome + '"]');
    }

    function destacar() {
      linhas().forEach(function (linha) {
        linha.classList.toggle("of-membro--viaja", radioDe(linha).checked);
      });
    }

    lista.addEventListener("click", function (evento) {
      var linha = evento.target.closest("[data-lista-item]");
      if (!linha) return;
      var radio = radioDe(linha);
      // O clique que o rótulo repassa ao próprio rádio já foi tratado aqui.
      if (evento.target === radio) return;
      // Caixa (escolha múltipla) já alterna sozinha; marcar é o comportamento
      // normal do rótulo e não precisa de ajuda.
      if (radio.type === "checkbox" || !radio.checked) return;
      evento.preventDefault();
      radio.checked = false;
      radio.dispatchEvent(new Event("change", { bubbles: true }));
    });

    lista.addEventListener("change", destacar);
    // Quem desmarca de fora (um interruptor, por exemplo) dispara o mesmo change.
    document.addEventListener("change", function (evento) {
      if (evento.target.name === nome) destacar();
    });

    // Busca sem resultado: a lista vazia vira uma borda solta; no lugar dela, a mensagem.
    var semResultado = document.querySelector('[data-lista-sem-resultado="' + nome + '"]');

    if (busca) {
      busca.addEventListener("input", function () {
        var termo = busca.value.trim().toLowerCase();
        var visiveis = 0;
        linhas().forEach(function (linha) {
          var texto = (linha.dataset.busca || "").toLowerCase();
          linha.hidden = termo !== "" && texto.indexOf(termo) === -1 && !radioDe(linha).checked;
          if (!linha.hidden) visiveis += 1;
        });
        var nada = termo !== "" && visiveis === 0 && linhas().length > 0;
        lista.hidden = nada;
        if (semResultado) semResultado.hidden = !nada;
      });
    }

    destacar();
  }

  function ligarTodas(raiz) {
    (raiz || document).querySelectorAll("[data-lista-escolha]").forEach(ligar);
  }

  window.DS = window.DS || {};
  window.DS.ligarListasDeEscolha = ligarTodas;

  ligarTodas(document);
  document.addEventListener("ds:aprimorar", function (evento) {
    ligarTodas((evento.detail && evento.detail.raiz) || document);
  });
})();
