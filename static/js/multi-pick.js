/**
 * Combobox de escolha múltipla com busca — o seletor de motoristas do cadastro
 * de viatura. Digita-se no próprio campo para filtrar; cada escolhido sai da
 * lista e vira uma linha abaixo, com × para remover.
 *
 * Saiu do `viagens-cadastros.js` para servir também o cadastro de termo, que
 * usa o mesmo componente para os servidores.
 *
 * Marcação esperada: `components/v32/multi_pick.html`.
 * Uso: DS.ligarEscolhaMultipla(raiz). Cada campo é ligado uma única vez.
 */
(function () {
  "use strict";

  function semAcentos(valor) {
    return String(valor || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR");
  }

  function pendentes(raiz, seletor) {
    return Array.prototype.filter.call(raiz.querySelectorAll(seletor), function (elemento) {
      if (elemento.dataset.multiPickLigado) return false;
      elemento.dataset.multiPickLigado = "1";
      return true;
    });
  }

  function ligarEscolhaMultipla(raiz) {
    pendentes(raiz, "[data-multi-pick]").forEach(function (campo) {
      var busca = campo.querySelector("[data-multi-busca]");
      var menu = campo.querySelector("[data-multi-menu]");
      var vazio = campo.querySelector("[data-multi-vazio]");
      var escolhidos = campo.parentNode.querySelector("[data-multi-escolhidos]");
      var opcoes = Array.prototype.slice.call(campo.querySelectorAll("[data-multi-opcao]"));
      var ativa = null;

      opcoes.forEach(function (opcao, indice) {
        if (!opcao.id) opcao.id = (busca.id || "multi") + "_opcao_" + indice;
      });

      function visiveis() {
        return opcoes.filter(function (opcao) { return !opcao.hidden; });
      }

      // Opção destacada: é a que o Enter escolhe.
      function destacar(opcao, semRolar) {
        if (ativa) ativa.classList.remove("is-active");
        ativa = opcao || null;
        if (ativa) {
          ativa.classList.add("is-active");
          busca.setAttribute("aria-activedescendant", ativa.id);
          // Pelo mouse a opção já está à vista; rolar ali faria a lista "fugir".
          if (!semRolar) ativa.scrollIntoView({ block: "nearest" });
        } else {
          busca.removeAttribute("aria-activedescendant");
        }
      }

      function linhaEscolhida(opcao) {
        var item = document.createElement("li");
        item.className = "multi-pick__escolhido";
        var texto = document.createElement("span");
        texto.textContent = opcao.dataset.nome;
        if (opcao.dataset.detalhes) {
          var detalhe = document.createElement("small");
          detalhe.textContent = opcao.dataset.detalhes;
          texto.appendChild(detalhe);
        }
        var remover = document.createElement("button");
        remover.type = "button";
        remover.className = "multi-pick__remover";
        remover.setAttribute("aria-label", "Remover " + opcao.dataset.nome);
        remover.textContent = "×";
        remover.addEventListener("click", function () {
          opcao.querySelector("input").checked = false;
          sincronizar();
          busca.focus();
        });
        item.appendChild(texto);
        item.appendChild(remover);
        return item;
      }

      // Escolhido sai da lista e vira linha abaixo do campo; o filtro roda
      // sobre o que sobrou.
      function sincronizar() {
        var termo = semAcentos(busca.value).trim();
        var disponiveis = 0;
        escolhidos.textContent = "";
        opcoes.forEach(function (opcao) {
          var marcado = opcao.querySelector("input").checked;
          var casa = !termo || semAcentos(opcao.dataset.busca).indexOf(termo) !== -1;
          opcao.hidden = marcado || !casa;
          if (marcado) escolhidos.appendChild(linhaEscolhida(opcao));
          else if (casa) disponiveis += 1;
        });
        if (vazio) vazio.hidden = disponiveis !== 0;
        // Digitando, a primeira opção que casa já fica pronta para o Enter.
        destacar(termo ? visiveis()[0] : null);
      }

      function abrir() {
        menu.hidden = false;
        campo.classList.add("is-open");
        busca.setAttribute("aria-expanded", "true");
      }

      function fechar() {
        menu.hidden = true;
        campo.classList.remove("is-open");
        busca.setAttribute("aria-expanded", "false");
        destacar(null);
      }

      campo.classList.add("is-enhanced");
      busca.addEventListener("focus", abrir);
      busca.addEventListener("click", abrir);
      busca.addEventListener("input", function () {
        abrir();
        sincronizar();
      });
      opcoes.forEach(function (opcao) {
        opcao.addEventListener("mousemove", function () {
          if (ativa !== opcao) destacar(opcao, true);
        });
        opcao.addEventListener("click", function () {
          // O clique marca a caixa; limpar a busca devolve a lista inteira.
          window.setTimeout(function () {
            busca.value = "";
            sincronizar();
            busca.focus();
          }, 0);
        });
      });
      busca.addEventListener("keydown", function (evento) {
        if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
          evento.preventDefault();
          abrir();
          var lista = visiveis();
          if (!lista.length) return;
          var indice = lista.indexOf(ativa);
          if (evento.key === "ArrowDown") indice = indice < lista.length - 1 ? indice + 1 : 0;
          else indice = indice > 0 ? indice - 1 : lista.length - 1;
          destacar(lista[indice]);
        } else if (evento.key === "Enter" && !menu.hidden) {
          // Com a lista aberta o Enter escolhe; nunca envia o formulário.
          evento.preventDefault();
          if (ativa && !ativa.hidden) ativa.click();
        }
      });
      campo.addEventListener("keydown", function (evento) {
        if (evento.key === "Escape" && !menu.hidden) {
          evento.stopPropagation();
          fechar();
        }
      });
      document.addEventListener("click", function (evento) {
        if (!menu.hidden && !campo.contains(evento.target)) fechar();
      });
      fechar();
      sincronizar();
    });
  }

  window.DS = window.DS || {};
  window.DS.ligarEscolhaMultipla = ligarEscolhaMultipla;

  ligarEscolhaMultipla(document);
  document.addEventListener("ds:aprimorar", function (evento) {
    ligarEscolhaMultipla((evento.detail && evento.detail.raiz) || document);
  });
})();
