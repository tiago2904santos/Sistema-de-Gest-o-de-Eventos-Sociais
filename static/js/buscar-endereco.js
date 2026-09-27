/*
 * Buscador de endereço dos campos Endereço/Bairro/CEP (components/endereco_campos.html).
 *
 * A pessoa digita rua, bairro, lugar ou CEP; depois de 300 ms parado (e ao
 * menos 3 letras), o servidor responde com sugestões (core:buscar_endereco —
 * do cadastro, do ViaCEP e do mapa). Escolher uma preenche endereço, bairro,
 * CEP e, se a tela tiver, estado e município (e o nome do local, se vazio).
 * O número não se perde: vale o que veio na busca, senão o que já estava no
 * campo Endereço, senão o do endereço já cadastrado.
 *
 * Combobox ARIA: ↑/↓ andam na lista, Enter escolhe, Esc fecha. Enter nunca
 * envia o formulário a partir deste campo. Sem resposta do servidor, a tela
 * segue igual — a busca é só ajuda.
 */
(function () {
  "use strict";

  var ESPERA_MS = 300;
  var MINIMO = 3;
  var FONTES = { cadastro: "Já usado", cep: "CEP", mapa: "Mapa" };
  // Número no fim da busca ("Rua X, 500" ou "Rua X 500"), fora rodovias ("BR 376").
  var NUMERO_FINAL = /^(.*?[A-Za-zÀ-ÿ].*?)(?:\s*,\s*|\s+)(\d{1,5}[A-Za-z]?|s\/?n)\s*$/i;
  var RODOVIA = /\b[A-Z]{2}\s*-?\s*$/;
  // Número do campo Endereço: o que vem depois da primeira vírgula ("123, sala 2").
  var NUMERO_GRAVADO = /^[^,]+?\s*,\s*((?:\d|s\/?n\b|km\b).*)$/i;

  function el(tag, classe, texto) {
    var elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto) elemento.textContent = texto;
    return elemento;
  }

  function disparar(campo) {
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function editavel(campo) {
    return campo && !campo.disabled && !campo.readOnly;
  }

  function definir(campo, valor) {
    if (!editavel(campo) || !valor || campo.value === valor) return;
    campo.value = valor;
    disparar(campo);
  }

  function escolherOpcao(select, valor) {
    if (!editavel(select) || !valor) return false;
    valor = String(valor);
    var existe = Array.prototype.some.call(select.options, function (o) { return o.value === valor; });
    if (!existe) return false;
    if (select.value !== valor) {
      select.value = valor;
      disparar(select);
    }
    return true;
  }

  function numeroDaBusca(texto) {
    var achado = NUMERO_FINAL.exec((texto || "").trim());
    if (!achado || RODOVIA.test(achado[1])) return "";
    return achado[2];
  }

  function numeroDoCampo(texto) {
    var achado = NUMERO_GRAVADO.exec((texto || "").trim());
    return achado ? achado[1].trim() : "";
  }

  document.querySelectorAll("[data-buscar-endereco]").forEach(function (caixa, indice) {
    var campo = caixa.querySelector("[data-be-campo]");
    var menu = caixa.querySelector("[data-be-menu]");
    var lista = caixa.querySelector("[data-be-lista]");
    var aviso = caixa.querySelector("[data-be-aviso]");
    var estado = caixa.querySelector("[data-be-estado]");
    var url = caixa.getAttribute("data-url");
    if (!campo || !menu || !lista || !url) return;
    var raiz = caixa.closest("form") || document;
    var textoAjuda = estado ? estado.textContent : "";

    function achar(nome) {
      return raiz.querySelector('[name="' + nome + '"]');
    }

    var espera = null;
    var pedido = 0;
    var itens = [];
    var ativo = -1;

    function informar(texto) {
      if (estado) estado.textContent = texto || textoAjuda;
    }

    function fechar() {
      menu.hidden = true;
      campo.setAttribute("aria-expanded", "false");
      campo.removeAttribute("aria-activedescendant");
      ativo = -1;
    }

    function abrir() {
      menu.hidden = false;
      campo.setAttribute("aria-expanded", "true");
    }

    function destacar(novo) {
      var opcoes = lista.querySelectorAll('[role="option"]');
      if (!opcoes.length) return;
      ativo = (novo + opcoes.length) % opcoes.length;
      opcoes.forEach(function (opcao, i) {
        var marcado = i === ativo;
        opcao.classList.toggle("is-active", marcado);
        opcao.setAttribute("aria-selected", marcado ? "true" : "false");
        if (marcado) {
          campo.setAttribute("aria-activedescendant", opcao.id);
          if (opcao.scrollIntoView) opcao.scrollIntoView({ block: "nearest" });
        }
      });
    }

    function mostrarAviso(texto) {
      if (!aviso) return;
      aviso.textContent = texto || "";
      aviso.hidden = !texto;
    }

    function mostrar(dados) {
      itens = dados.resultados || [];
      lista.textContent = "";
      ativo = -1;
      itens.forEach(function (item, i) {
        var opcao = el("div", "custom-select__opcao");
        opcao.id = "id_endereco_busca_opcao_" + indice + "_" + i;
        opcao.setAttribute("role", "option");
        opcao.setAttribute("aria-selected", "false");
        var texto = el("span", "endereco-busca__texto");
        texto.appendChild(el("b", "", item.rotulo));
        if (item.detalhe) texto.appendChild(el("small", "", item.detalhe));
        opcao.appendChild(texto);
        opcao.appendChild(el("span", "endereco-busca__fonte", FONTES[item.fonte] || ""));
        // mousedown (e não click): o campo não perde o foco antes da escolha.
        opcao.addEventListener("mousedown", function (evento) {
          evento.preventDefault();
          aplicar(item);
        });
        opcao.addEventListener("mousemove", function () { if (ativo !== i) destacar(i); });
        lista.appendChild(opcao);
      });
      var avisos = (dados.avisos || []).slice();
      if (!itens.length) avisos.unshift("Nenhum endereço encontrado. Confira a grafia ou escolha o município antes.");
      mostrarAviso(avisos.join(" "));
      abrir();
      informar(itens.length ? (itens.length === 1 ? "1 sugestão." : itens.length + " sugestões.") + " Use ↑ e ↓ e Enter para escolher." : avisos.join(" "));
    }

    function aplicar(item) {
      fechar();
      var endereco = achar("endereco");
      var numero = numeroDaBusca(campo.value) || numeroDoCampo(endereco ? endereco.value : "") || item.numero || "";
      if (item.logradouro) definir(endereco, item.logradouro + (numero ? ", " + numero : ""));
      definir(achar("bairro"), item.bairro);
      definir(achar("cep"), item.cep);
      // Estado antes do município: trocar o estado limpa o município da cascata.
      if (item.municipio_id) {
        var select = achar("municipio");
        var selectEstado = achar("estado");
        if (select && selectEstado && item.estado_id) escolherOpcao(selectEstado, item.estado_id);
        if (select) escolherOpcao(select, item.municipio_id);
      }
      // O nome do lugar só entra se o campo "Local" ainda está vazio.
      if (item.local) {
        ["local_evento", "local_entrega", "local"].some(function (nome) {
          var local = achar(nome);
          if (!local || local.tagName === "SELECT") return false;
          if (!local.value.trim()) definir(local, item.local);
          return true;
        });
      }
      campo.value = "";
      informar(item.logradouro && !numero ? "Endereço preenchido — complete o número no campo Endereço." : "Endereço preenchido — confira os campos abaixo.");
      if (endereco && item.logradouro && !numero && editavel(endereco)) {
        endereco.focus();
        var fim = endereco.value.length;
        try { endereco.setSelectionRange(fim, fim); } catch (erro) { /* campo sem seleção */ }
      }
    }

    function buscar() {
      var termo = campo.value.trim();
      var numeroPedido = ++pedido;
      if (termo.replace(/[^0-9A-Za-zÀ-ÿ]/g, "").length < MINIMO) { fechar(); informar(""); return; }
      var parametros = new URLSearchParams({ q: termo });
      var municipio = achar("municipio");
      var estadoSelect = achar("estado");
      if (municipio && municipio.value) parametros.set("municipio", municipio.value);
      if (estadoSelect && estadoSelect.value) parametros.set("uf", estadoSelect.value);
      informar("Buscando…");
      fetch(url + "?" + parametros.toString(), {
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      })
        .then(function (resposta) { return resposta.ok ? resposta.json() : null; })
        .then(function (dados) {
          if (numeroPedido !== pedido) return;
          if (!dados) { informar("Não foi possível buscar agora. Preencha os campos à mão."); return; }
          mostrar(dados);
        })
        .catch(function () {
          if (numeroPedido === pedido) informar("Não foi possível buscar agora. Preencha os campos à mão.");
        });
    }

    campo.addEventListener("input", function () {
      clearTimeout(espera);
      espera = setTimeout(buscar, ESPERA_MS);
    });

    campo.addEventListener("keydown", function (evento) {
      var aberto = !menu.hidden && itens.length;
      if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
        evento.preventDefault();
        if (!aberto) { if (itens.length) abrir(); else return; }
        destacar(ativo === -1 ? (evento.key === "ArrowDown" ? 0 : -1) : ativo + (evento.key === "ArrowDown" ? 1 : -1));
      } else if (evento.key === "Enter") {
        // Enter aqui nunca envia o formulário.
        evento.preventDefault();
        if (aberto && ativo >= 0) aplicar(itens[ativo]);
        else if (aberto && itens.length === 1) aplicar(itens[0]);
        else { clearTimeout(espera); buscar(); }
      } else if (evento.key === "Escape") {
        if (!menu.hidden) { evento.preventDefault(); evento.stopPropagation(); fechar(); }
      }
    });

    campo.addEventListener("blur", function () { setTimeout(fechar, 120); });
    campo.addEventListener("focus", function () {
      if (itens.length && campo.value.trim().length >= MINIMO) abrir();
    });
  });
})();
