/* Campos dos cadastros de viagens: máscaras (CPF, RG, telefone, placa), caixa
   alta ao sair do campo e o seletor múltiplo com busca.

   `ligar(raiz)` é chamado no carregamento e de novo a cada modal aberto — o
   formulário chega pronto do servidor via fetch, e o DS avisa pelo evento
   `ds:aprimorar`. Cada elemento é ligado uma única vez. */
(function () {
  "use strict";

  function semAcentos(valor) {
    return String(valor || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-BR");
  }

  function somenteDigitos(valor, limite) {
    return String(valor || "").replace(/\D/g, "").slice(0, limite);
  }

  function mascaraCpf(valor) {
    var d = somenteDigitos(valor, 11);
    return d
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1-$2");
  }

  function mascaraTelefone(valor) {
    var d = somenteDigitos(valor, 11);
    if (d.length <= 10) {
      return d.replace(/^(\d{2})(\d)/, "($1) $2").replace(/(\d{4})(\d)/, "$1-$2");
    }
    return d.replace(/^(\d{2})(\d)/, "($1) $2").replace(/(\d{5})(\d)/, "$1-$2");
  }

  function mascaraRg(valor) {
    if (/[A-Za-zÀ-ÿ]/.test(valor)) return String(valor).toLocaleUpperCase("pt-BR");
    var d = somenteDigitos(valor, 9);
    return d
      .replace(/^(\d{2})(\d)/, "$1.$2")
      .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1-$2");
  }

  function mascaraPlaca(valor) {
    var placa = String(valor || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 7).toUpperCase();
    return /^[A-Z]{3}\d{1,4}$/.test(placa) && placa.length > 3
      ? placa.slice(0, 3) + "-" + placa.slice(3)
      : placa;
  }

  var mascaras = { cpf: mascaraCpf, telefone: mascaraTelefone, rg: mascaraRg, placa: mascaraPlaca };

  // Religar o mesmo campo duplicaria máscara e contagem; marca quem já foi.
  function pendentes(raiz, seletor) {
    return Array.prototype.filter.call(raiz.querySelectorAll(seletor), function (elemento) {
      if (elemento.dataset.viagensLigado) return false;
      elemento.dataset.viagensLigado = "1";
      return true;
    });
  }

  function ligarMascaras(raiz) {
    pendentes(raiz, "[data-mask]").forEach(function (campo) {
      var aplicar = mascaras[campo.getAttribute("data-mask")];
      if (!aplicar) return;
      function atualizar() { campo.value = aplicar(campo.value); }
      campo.addEventListener("input", atualizar);
      atualizar();
    });

    pendentes(raiz, "[data-uppercase='true']").forEach(function (campo) {
      campo.addEventListener("blur", function () {
        campo.value = campo.value.trim().replace(/\s+/g, " ").toLocaleUpperCase("pt-BR");
      });
    });
  }

  function ligarEscolhaMultipla(raiz) {
    pendentes(raiz, "[data-multi-pick]").forEach(function (campo) {
      var busca = campo.querySelector("[data-multi-busca]");
      var menu = campo.querySelector("[data-multi-menu]");
      var vazio = campo.querySelector("[data-multi-vazio]");
      var escolhidos = campo.parentNode.querySelector("[data-multi-escolhidos]");
      var opcoes = Array.prototype.slice.call(campo.querySelectorAll("[data-multi-opcao]"));

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
      }

      campo.classList.add("is-enhanced");
      busca.addEventListener("focus", abrir);
      busca.addEventListener("click", abrir);
      busca.addEventListener("input", function () {
        abrir();
        sincronizar();
      });
      opcoes.forEach(function (opcao) {
        opcao.addEventListener("click", function () {
          // O clique marca a caixa; limpar a busca devolve a lista inteira.
          window.setTimeout(function () {
            busca.value = "";
            sincronizar();
            busca.focus();
          }, 0);
        });
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

  function ligarPreviaDiaria(raiz) {
    pendentes(raiz, "[data-diaria-base]").forEach(function (base) {
      var quinze = raiz.querySelector("[data-diaria-15]");
      var trinta = raiz.querySelector("[data-diaria-30]");
      var dinheiro = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

      function numero(valor) {
        // O campo é numérico (ponto decimal), mas aceita vírgula digitada.
        var resultado = parseFloat(String(valor || "").trim().replace(",", "."));
        return Number.isFinite(resultado) ? resultado : 0;
      }

      function atualizar() {
        var valor = numero(base.value);
        // Os percentuais gravados saem do servidor; aqui é só a prévia.
        if (quinze) quinze.textContent = dinheiro.format(valor * 0.15);
        if (trinta) trinta.textContent = dinheiro.format(valor * 0.30);
      }

      base.addEventListener("input", atualizar);
      atualizar();
    });
  }

  function ligar(raiz) {
    ligarMascaras(raiz);
    ligarEscolhaMultipla(raiz);
    ligarPreviaDiaria(raiz);
  }

  ligar(document);
  document.addEventListener("ds:aprimorar", function (evento) {
    ligar((evento.detail && evento.detail.raiz) || document);
  });
})();
