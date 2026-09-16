/**
 * Cadastro de ofício — os comportamentos do Gerenciador de Viagens numa página.
 *
 * - escolher um modelo preenche o texto (descrição e justificativa);
 * - custeio "Outra instituição" mostra o Nome da Instituição;
 * - protocolo com a máscara 00.000.000-0;
 * - seletores com busca: equipe (com "Definir motorista" e "Com termo"),
 *   viatura e motorista do sistema;
 * - sugestões de viatura pela unidade da equipe e do motorista;
 * - o cartão do motorista aparece com viatura escolhida e ninguém da equipe
 *   ao volante; "No sistema" / "Manual" alterna o que ele pede;
 * - "Roteiro salvo" / "Roteiro novo" mostra ou esconde a busca de roteiros;
 * - o PDF da conferência só é pedido quando o cartão abre.
 */
(function () {
  "use strict";

  var form = document.getElementById("form-oficio");
  if (!form) return;

  function lerJson(id) {
    var no = document.getElementById(id);
    if (!no) return {};
    try { return JSON.parse(no.textContent); } catch (erro) { return {}; }
  }

  function semAcento(texto) {
    return (texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  function disparar(campo) {
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // 1. Modelos de texto -----------------------------------------------------
  var modelos = lerJson("oficio-modelos-texto");
  Object.entries({ "modelo_motivo": "motivo", "justificativa-modelo": "justificativa-texto" }).forEach(function (par) {
    var seletor = document.getElementById("id_" + par[0]);
    var texto = document.getElementById("id_" + par[1]);
    if (!seletor || !texto) return;
    seletor.addEventListener("change", function () {
      var valor = (modelos[par[0]] || {})[seletor.value];
      if (valor !== undefined) {
        texto.value = valor;
        texto.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
  });

  // 2. Custeio --------------------------------------------------------------
  var custeio = form.querySelector('[name="custeio"]');
  var instituicao = form.querySelector("[data-custeio-instituicao]");
  if (custeio && instituicao) {
    custeio.addEventListener("change", function () {
      instituicao.hidden = custeio.value !== instituicao.getAttribute("data-outra");
    });
  }

  // 3. Protocolo: 00.000.000-0 ----------------------------------------------
  function mascaraProtocolo(valor) {
    var d = (valor || "").replace(/\D/g, "").slice(0, 9);
    var s = d.slice(0, 2);
    if (d.length > 2) s += "." + d.slice(2, 5);
    if (d.length > 5) s += "." + d.slice(5, 8);
    if (d.length > 8) s += "-" + d.slice(8);
    return s;
  }
  ["protocolo", "motorista_protocolo_ref"].forEach(function (nome) {
    var campo = form.querySelector('[name="' + nome + '"]');
    if (!campo) return;
    campo.placeholder = "00.000.000-0";
    campo.value = mascaraProtocolo(campo.value);
    campo.addEventListener("input", function () { campo.value = mascaraProtocolo(campo.value); });
  });

  // 4. Seletores com busca --------------------------------------------------
  // Cada `.ofc-picker` tem a busca, a lista de resultados e a lista de
  // escolhidos. Todas as linhas já vêm do servidor; escolher só mostra a
  // linha e marca o campo dela. `unico` troca a escolha anterior.
  function montarSeletor(raiz, opcoes) {
    var busca = raiz.querySelector("[data-ofc-busca]");
    var lista = raiz.querySelector("[data-ofc-resultados]");
    var semResultado = raiz.querySelector("[data-ofc-sem-resultado]");
    var escolhidos = raiz.querySelector("[data-ofc-escolhidos]");
    var vazio = escolhidos.querySelector("[data-ofc-equipe-vazia]");
    var resultados = Array.prototype.slice.call(lista.querySelectorAll(".ofc-picker__resultado"));
    var linhas = Array.prototype.slice.call(escolhidos.querySelectorAll(".ofc-pessoa"));

    function linha(valor) {
      return linhas.find(function (l) { return l.getAttribute("data-valor") === valor; });
    }
    function campo(l) { return l.querySelector('input[type="checkbox"], input[type="radio"]'); }
    function escolhido(l) { var c = campo(l); return c && c.checked; }

    function atualizarVazio() {
      if (vazio) vazio.hidden = linhas.some(escolhido);
    }

    function filtrar() {
      var termo = semAcento(busca.value.trim());
      var algum = false;
      resultados.forEach(function (r) {
        var l = linha(r.getAttribute("data-valor"));
        var ja = opcoes.unico ? false : (l && escolhido(l));
        var casa = !termo || semAcento(r.getAttribute("data-busca")).indexOf(termo) !== -1;
        r.hidden = ja || !casa;
        if (!r.hidden) algum = true;
      });
      if (semResultado) semResultado.hidden = algum;
    }

    function abrir(aberto) {
      lista.hidden = !aberto;
      busca.setAttribute("aria-expanded", aberto ? "true" : "false");
    }

    function escolher(valor) {
      var l = linha(valor);
      if (!l) return;
      if (opcoes.unico) {
        linhas.forEach(function (outra) {
          if (outra !== l) { campo(outra).checked = false; outra.hidden = true; }
        });
      }
      campo(l).checked = true;
      l.hidden = false;
      if (opcoes.aoEscolher) opcoes.aoEscolher(l);
      busca.value = "";
      abrir(false);
      atualizarVazio();
      mudou();
    }

    function remover(l) {
      campo(l).checked = false;
      l.hidden = true;
      if (opcoes.aoRemover) opcoes.aoRemover(l);
      atualizarVazio();
      mudou();
    }

    function mudou() {
      filtrar();
      raiz.dispatchEvent(new CustomEvent("ofc:mudou", { bubbles: true }));
    }

    busca.addEventListener("focus", function () { filtrar(); abrir(true); });
    busca.addEventListener("input", function () { filtrar(); abrir(true); });
    busca.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape") { abrir(false); return; }
      if (evento.key === "ArrowDown") {
        evento.preventDefault();
        var primeiro = resultados.find(function (r) { return !r.hidden; });
        if (primeiro) primeiro.focus();
      }
      if (evento.key === "Enter") {
        evento.preventDefault();
        var unico = resultados.filter(function (r) { return !r.hidden; });
        if (unico.length === 1) escolher(unico[0].getAttribute("data-valor"));
      }
    });
    resultados.forEach(function (r) {
      r.addEventListener("mousedown", function (evento) { evento.preventDefault(); });
      r.addEventListener("click", function () { escolher(r.getAttribute("data-valor")); });
      r.addEventListener("keydown", function (evento) {
        var visiveis = resultados.filter(function (x) { return !x.hidden; });
        var i = visiveis.indexOf(r);
        if (evento.key === "Enter" || evento.key === " ") { evento.preventDefault(); escolher(r.getAttribute("data-valor")); }
        else if (evento.key === "ArrowDown" && visiveis[i + 1]) { evento.preventDefault(); visiveis[i + 1].focus(); }
        else if (evento.key === "ArrowUp") { evento.preventDefault(); (visiveis[i - 1] || busca).focus(); }
        else if (evento.key === "Escape") { abrir(false); busca.focus(); }
      });
    });
    document.addEventListener("click", function (evento) {
      if (!raiz.querySelector(".ofc-picker__campo").contains(evento.target)) abrir(false);
    });
    linhas.forEach(function (l) {
      var botao = l.querySelector("[data-ofc-remover]");
      if (botao) botao.addEventListener("click", function () { remover(l); });
    });
    atualizarVazio();

    return { linhas: linhas, escolhido: escolhido, escolher: escolher, remover: remover };
  }

  // 4a. Equipe: motorista e termo em cada pessoa
  var raizEquipe = form.querySelector("[data-ofc-equipe]");
  var raizViatura = form.querySelector("[data-ofc-viatura]");
  var raizMotorista = form.querySelector("[data-ofc-motorista-sistema]");
  var cartaoMotorista = form.querySelector("[data-ofc-cartao-motorista]");
  var campoModo = form.querySelector("[data-ofc-modo]");
  var motoristaEquipe = raizEquipe ? raizEquipe.getAttribute("data-motorista") : "";

  var equipe = raizEquipe && montarSeletor(raizEquipe, {
    aoEscolher: function (l) {
      // Quem entra na equipe entra com termo, como na origem.
      definirTermo(l, true);
    },
    aoRemover: function (l) {
      definirTermo(l, false);
      if (motoristaEquipe === l.getAttribute("data-valor")) definirMotoristaEquipe("");
    },
  });
  var viatura = raizViatura && montarSeletor(raizViatura, { unico: true });
  var motorista = raizMotorista && montarSeletor(raizMotorista, { unico: true });

  function definirTermo(l, ativo) {
    var campo = l.querySelector('input[name="servidores_termo_autorizacao"]');
    var botao = l.querySelector("[data-ofc-termo]");
    if (campo) campo.checked = ativo;
    if (botao) {
      botao.setAttribute("aria-pressed", ativo ? "true" : "false");
      botao.classList.toggle("is-ativo", ativo);
      botao.textContent = ativo ? "Com termo" : "Sem termo";
    }
  }

  function campoMotorista(valor) {
    return form.querySelector('input[name="motorista"][value="' + valor + '"]');
  }

  function definirMotoristaEquipe(valor) {
    motoristaEquipe = valor;
    equipe.linhas.forEach(function (l) {
      var ativo = l.getAttribute("data-valor") === valor;
      var botao = l.querySelector("[data-ofc-motorista]");
      l.classList.toggle("ofc-pessoa--motorista", ativo);
      botao.setAttribute("aria-pressed", ativo ? "true" : "false");
      botao.textContent = ativo ? "Motorista" : "Definir motorista";
    });
    // O motorista da equipe é o mesmo campo `motorista`, no modo servidor.
    if (valor) {
      if (motorista) motorista.escolher(valor);
      if (campoModo) definirModo("SERVIDOR");
    } else if (motorista) {
      motorista.linhas.forEach(function (l) {
        if (motorista.escolhido(l)) motorista.remover(l);
      });
    }
    atualizarCartaoMotorista();
  }

  if (equipe) {
    equipe.linhas.forEach(function (l) {
      var botaoTermo = l.querySelector("[data-ofc-termo]");
      var botaoMotorista = l.querySelector("[data-ofc-motorista]");
      if (botaoTermo) botaoTermo.addEventListener("click", function () {
        definirTermo(l, botaoTermo.getAttribute("aria-pressed") !== "true");
      });
      if (botaoMotorista) botaoMotorista.addEventListener("click", function () {
        var valor = l.getAttribute("data-valor");
        definirMotoristaEquipe(motoristaEquipe === valor ? "" : valor);
      });
    });
  }

  // 4b. Cartão do motorista
  var painelServidor = form.querySelector("[data-ofc-motorista-servidor]");
  var painelManual = form.querySelector("[data-ofc-motorista-manual]");
  var opcoesModo = Array.prototype.slice.call(form.querySelectorAll("[data-ofc-modo-opcao]"));

  function definirModo(modo) {
    if (!campoModo) return;
    campoModo.value = modo;
    opcoesModo.forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-ofc-modo-opcao") === modo ? "true" : "false");
    });
    if (painelServidor) painelServidor.hidden = modo === "MANUAL";
    if (painelManual) painelManual.hidden = modo !== "MANUAL";
  }
  opcoesModo.forEach(function (b) {
    b.addEventListener("click", function () { definirModo(b.getAttribute("data-ofc-modo-opcao")); });
  });

  function temViatura() {
    return !!form.querySelector('input[name="viatura"]:checked');
  }

  function atualizarCartaoMotorista() {
    if (!cartaoMotorista) return;
    var visivel = temViatura() && !motoristaEquipe;
    cartaoMotorista.hidden = !visivel;
    // Cartão escondido com motorista da equipe: o campo segue marcado por ela.
  }

  if (raizMotorista) {
    raizMotorista.addEventListener("ofc:mudou", function () {
      // Escolher no cartão alguém que já está na equipe é defini-lo como motorista da equipe.
      var marcado = form.querySelector('input[name="motorista"]:checked');
      if (marcado && equipe) {
        var l = equipe.linhas.find(function (x) { return x.getAttribute("data-valor") === marcado.value; });
        if (l && equipe.escolhido(l) && motoristaEquipe !== marcado.value) {
          definirMotoristaEquipe(marcado.value);
        }
      }
      atualizarSugestoes();
    });
  }
  if (raizViatura) raizViatura.addEventListener("ofc:mudou", function () {
    atualizarCartaoMotorista();
    atualizarSugestoes();
  });
  if (raizEquipe) raizEquipe.addEventListener("ofc:mudou", atualizarSugestoes);

  // 5. Sugestões de viatura -------------------------------------------------
  var sugestoes = form.querySelector("[data-ofc-sugestoes]");
  var listaSugestoes = form.querySelector("[data-ofc-sugestoes-lista]");

  function atualizarSugestoes() {
    if (!sugestoes || !viatura) return;
    var unidades = new Set();
    if (equipe) equipe.linhas.forEach(function (l) {
      if (equipe.escolhido(l) && l.getAttribute("data-unidade")) unidades.add(l.getAttribute("data-unidade"));
    });
    var marcado = form.querySelector('input[name="motorista"]:checked');
    if (marcado && motorista) {
      var lm = motorista.linhas.find(function (x) { return x.getAttribute("data-valor") === marcado.value; });
      if (lm && lm.getAttribute("data-unidade")) unidades.add(lm.getAttribute("data-unidade"));
    }
    listaSugestoes.innerHTML = "";
    var atual = form.querySelector('input[name="viatura"]:checked');
    viatura.linhas.forEach(function (l) {
      if (!unidades.has(l.getAttribute("data-unidade"))) return;
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "ofc-sugestao";
      var ativo = atual && atual.value === l.getAttribute("data-valor");
      chip.setAttribute("aria-pressed", ativo ? "true" : "false");
      chip.textContent = l.getAttribute("data-rotulo");
      if (l.getAttribute("data-sigla")) {
        var sigla = document.createElement("span");
        sigla.className = "ofc-sugestao__sigla";
        sigla.textContent = l.getAttribute("data-sigla");
        chip.appendChild(sigla);
      }
      chip.addEventListener("click", function () { viatura.escolher(l.getAttribute("data-valor")); });
      listaSugestoes.appendChild(chip);
    });
    sugestoes.hidden = !listaSugestoes.children.length;
  }
  atualizarSugestoes();

  // 6. Roteiro salvo / Roteiro novo ------------------------------------------
  var fonte = document.querySelector("[data-roteiro-fonte]");
  var blocoSalvo = document.querySelector("[data-roteiro-salvo]");
  if (fonte && blocoSalvo) {
    fonte.querySelectorAll("[data-roteiro-fonte-opcao]").forEach(function (botao) {
      botao.addEventListener("click", function () {
        var salvo = botao.getAttribute("data-roteiro-fonte-opcao") === "salvo";
        fonte.querySelectorAll("[data-roteiro-fonte-opcao]").forEach(function (b) {
          b.setAttribute("aria-pressed", b === botao ? "true" : "false");
        });
        blocoSalvo.hidden = !salvo;
      });
    });
  }

  // 7. Conferência: o PDF só é pedido quando o cartão abre ---------------------
  document.querySelectorAll("[data-ofc-doc]").forEach(function (cartao) {
    cartao.addEventListener("toggle", function () {
      if (!cartao.open) return;
      var quadro = cartao.querySelector(":scope > .ofc-doc__corpo > iframe[data-src]");
      if (quadro && !quadro.getAttribute("src")) quadro.setAttribute("src", quadro.getAttribute("data-src"));
    });
    // A pasta de ações mora no título; clicar nela não abre nem fecha o cartão.
    var acoes = cartao.querySelector(":scope > summary .ofc-doc__acoes");
    if (acoes) acoes.addEventListener("click", function (evento) {
      if (evento.target.closest("[data-menu-gatilho]")) evento.preventDefault();
    });
  });
})();
