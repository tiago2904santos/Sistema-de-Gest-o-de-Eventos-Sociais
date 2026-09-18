/**
 * Cadastro da ordem de serviço — o `ordens-servico-form.js` da origem na
 * pele da casa: os ofícios marcados copiam datas, equipe, motivo e destino
 * para a tela; o modelo de motivo preenche o texto; na necessidade que pede
 * funções (caminhão, micro-ônibus e cerimonial) cada servidor escolhido ganha
 * o seletor na própria linha, e a função vira `funcao_servidor_<id>` no envio; e o botão principal diz se a
 * OS está completa. Tudo sem recarregar nem rolar a página. Sem autosave.
 *
 * As listas de ofícios e servidores são o `multi-pick.js`; os destinos, o
 * componente do termo com o `destinos-arraste.js`.
 */
(function () {
  "use strict";

  var form = document.querySelector("[data-os-form]");
  if (!form) return;

  var FUNCOES = { CONDUCAO: "Condução", TECNICO: "Técnico", APOIO: "Apoio", COORDENACAO: "Coordenação", PREPARACAO: "Preparação" };
  var FUNCOES_POR_TIPO = {
    CAMINHAO: ["CONDUCAO", "TECNICO", "APOIO"],
    MICROONIBUS: ["CONDUCAO", "TECNICO", "APOIO"],
    CERIMONIAL_ANTECIPADO: ["COORDENACAO", "APOIO", "PREPARACAO"]
  };
  var PAINEL_POR_TIPO = {
    CAMINHAO: { titulo: "Função no caminhão", aria: "Função dos servidores no caminhão" },
    MICROONIBUS: { titulo: "Função no micro-ônibus", aria: "Função dos servidores no micro-ônibus" },
    CERIMONIAL_ANTECIPADO: { titulo: "Função no cerimonial", aria: "Função dos servidores no cerimonial" }
  };

  function lerJson(id) {
    var script = document.getElementById(id);
    if (!script) return {};
    try {
      var lido = JSON.parse(script.textContent || "{}");
      return lido && typeof lido === "object" ? lido : {};
    } catch (erro) {
      return {};
    }
  }

  function disparar(elemento, tipo) {
    elemento.dispatchEvent(new Event(tipo, { bubbles: true }));
  }

  /* ---- multi-pick: ler e marcar sem mexer no componente ------------------- */

  function opcoesDe(nome) {
    return Array.prototype.slice.call(form.querySelectorAll('[data-multi-opcao] input[name="' + nome + '"]'));
  }

  // Serve ao multi-pick (servidores) e à lista de escolha (ofícios).
  function marcados(nome) {
    return Array.prototype.slice.call(form.querySelectorAll('input[name="' + nome + '"]:checked'));
  }

  // Marca as caixas e pede ao multi-pick que refaça a lista de escolhidos: um
  // `input` na busca faz a sincronização (e abre o menu), e o Escape fecha —
  // sem focar nada, para a página não rolar até o campo.
  function marcarNoMultiPick(nome, ids) {
    var mudou = false;
    opcoesDe(nome).forEach(function (caixa) {
      if (ids.indexOf(caixa.value) !== -1 && !caixa.checked) {
        caixa.checked = true;
        mudou = true;
      }
    });
    if (!mudou) return;
    var busca = document.getElementById("id_" + nome + "_busca");
    var campo = busca && busca.closest("[data-multi-pick]");
    if (!busca || !campo) return;
    disparar(busca, "input");
    campo.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  }

  /* ---- 1. Ofícios vinculados: copiar para a tela ------------------------- */

  var resumos = lerJson("os-oficios-resumo");

  function definirData(nome, iso) {
    var campo = form.querySelector('input[name="' + nome + '"]');
    if (!campo || !iso || campo.value === iso) return;
    campo.value = iso;
    disparar(campo, "change");
  }

  function definirDestinoPrincipal(estadoId, cidadeId) {
    var linha = form.querySelector("[data-destinos] [data-destino-linha]");
    if (!linha) return;
    var estado = linha.querySelector(".destino-row__estado select");
    var cidade = linha.querySelector(".destino-row__campo select");
    if (!estado || !cidade) return;
    // Só preenche o que está em branco: o destino digitado à mão vale mais.
    if (estado.value || cidade.value) return;
    estado.value = String(estadoId || "");
    disparar(estado, "change");
    if (cidadeId) {
      cidade.value = String(cidadeId);
      disparar(cidade, "change");
    }
  }

  function aplicarOficios() {
    var escolhidos = marcados("oficios").map(function (caixa) { return resumos[caixa.value]; }).filter(Boolean);
    if (!escolhidos.length) {
      atualizarRotulo();
      return;
    }
    var inicios = escolhidos.map(function (r) { return r.data_inicio; }).filter(Boolean).sort();
    var fins = escolhidos.map(function (r) { return r.data_fim; }).filter(Boolean).sort();
    if (inicios.length) definirData("data_evento_inicio", inicios[0]);
    if (fins.length) definirData("data_evento_fim", fins[fins.length - 1]);

    var servidores = [];
    escolhidos.forEach(function (r) {
      (r.servidor_ids || []).forEach(function (id) {
        if (servidores.indexOf(String(id)) === -1) servidores.push(String(id));
      });
    });
    marcarNoMultiPick("servidores", servidores);

    // O motivo não sobrescreve o que já foi digitado.
    var motivo = form.querySelector('textarea[name="motivo"]');
    if (motivo && !motivo.value.trim()) {
      var primeiro = escolhidos.filter(function (r) { return (r.motivo || "").trim(); })[0];
      if (primeiro) {
        motivo.value = primeiro.motivo;
        disparar(motivo, "input");
      }
    }

    var comDestino = escolhidos.filter(function (r) { return r.cidade_id; })[0];
    if (comDestino) definirDestinoPrincipal(comDestino.estado_id, comDestino.cidade_id);

    sincronizarFuncoes();
    atualizarRotulo();
  }

  form.addEventListener("change", function (evento) {
    if (evento.target.name === "oficios") aplicarOficios();
  });

  // Interruptor dos ofícios, no molde do termo: o `data-expande` do app.js
  // abre e fecha o painel; desligar desmarca os ofícios, senão eles seguiriam
  // no envio com o painel fechado.
  var toggleOficios = form.querySelector("[data-oficio-toggle]");
  if (toggleOficios) {
    toggleOficios.addEventListener("click", function () {
      window.setTimeout(function () {
        var ligado = toggleOficios.getAttribute("aria-expanded") === "true";
        toggleOficios.classList.toggle("interruptor--ligado", ligado);
        var rotulo = toggleOficios.querySelector(".interruptor__rotulo");
        if (rotulo) rotulo.textContent = ligado ? "Vinculada a ofícios" : "Sem ofício vinculado";
        if (ligado) return;
        var desmarcou = false;
        marcados("oficios").forEach(function (caixa) { caixa.checked = false; desmarcou = true; });
        if (desmarcou) disparar(form.querySelector('input[name="oficios"]'), "change");
      }, 0);
    });
  }

  /* ---- 2. Modelo de motivo → texto ---------------------------------------- */

  var modelos = lerJson("os-modelos-texto");
  var seletorModelo = document.getElementById("id_modelo_motivo");
  var textoMotivo = document.getElementById("id_motivo");
  if (seletorModelo && textoMotivo) {
    seletorModelo.addEventListener("change", function () {
      var texto = (modelos[seletorModelo.value] || "").trim();
      if (!texto) return;
      textoMotivo.value = texto;
      disparar(textoMotivo, "input");
      textoMotivo.focus({ preventScroll: true });
    });
  }

  /* ---- 3. Necessidade e função de cada servidor ------------------------- */

  var funcoes = lerJson("os-funcoes-servidores");
  var equipe = form.querySelector("[data-os-equipe]");
  var escolhidos = equipe && equipe.querySelector("[data-multi-escolhidos]");
  var entradas = form.querySelector("[data-os-funcoes-inputs]");

  function tipoEscolhido() {
    var marcado = form.querySelector('input[name="tipo_necessidade"]:checked');
    return marcado ? marcado.value : "";
  }

  function funcoesDoTipo() {
    return FUNCOES_POR_TIPO[tipoEscolhido()] || [];
  }

  function marcarCartaoDeTipo() {
    form.querySelectorAll(".os-tipo").forEach(function (cartao) {
      var radio = cartao.querySelector('input[name="tipo_necessidade"]');
      cartao.classList.toggle("is-escolhido", !!radio && radio.checked);
    });
  }

  // A linha do escolhido é do multi-pick, que a refaz a cada mudança; aqui
  // ela só ganha o crachá e, quando o tipo pede, o seletor da função.
  function decorarLinha(linha, modos, copia) {
    var id = linha.dataset.valor;
    if (!id) return;
    if (!linha.querySelector(".of-av")) {
      var avatar = document.createElement("span");
      avatar.className = "of-av";
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = linha.dataset.iniciais || "—";
      linha.insertBefore(avatar, linha.firstChild);
    }
    var grupo = linha.querySelector("[data-os-funcoes-seg]");
    // O grupo é reaproveitado enquanto as funções forem as mesmas: é o que
    // deixa o realce deslizar de uma função para a outra.
    if (grupo && grupo.dataset.modos !== modos.join(" ")) {
      grupo.remove();
      grupo = null;
    }
    linha.classList.toggle("os-escolhido--funcao", modos.length > 0);
    if (!modos.length) return;
    var novo = !grupo;
    if (novo) {
      grupo = document.createElement("div");
      grupo.className = "os-func-seg sem-anim";
      grupo.setAttribute("role", "group");
      grupo.setAttribute("aria-label", (copia ? copia.aria : "Função") + " — " + (linha.querySelector("span:not(.of-av)") || linha).firstChild.textContent);
      grupo.dataset.osFuncoesSeg = "";
      grupo.dataset.modos = modos.join(" ");
      modos.forEach(function (modo) {
        var botao = document.createElement("button");
        botao.type = "button";
        botao.dataset.osFuncao = modo;
        botao.dataset.osServidor = id;
        botao.textContent = FUNCOES[modo];
        grupo.appendChild(botao);
      });
      linha.insertBefore(grupo, linha.querySelector(".multi-pick__remover"));
    }
    var escolhido = null;
    grupo.querySelectorAll("[data-os-funcao]").forEach(function (botao) {
      var ativo = funcoes[id] === botao.dataset.osFuncao;
      botao.setAttribute("aria-pressed", ativo ? "true" : "false");
      if (ativo) escolhido = botao;
    });
    if (escolhido) {
      grupo.style.setProperty("--x", escolhido.offsetLeft + "px");
      grupo.style.setProperty("--w", escolhido.offsetWidth + "px");
    }
    grupo.classList.toggle("tem-escolha", !!escolhido);
    // Grupo recém-criado já nasce no lugar; só as trocas seguintes animam.
    if (novo) window.requestAnimationFrame(function () { grupo.classList.remove("sem-anim"); });
  }

  var decorando = false;
  function decorar() {
    if (!escolhidos || decorando) return;
    decorando = true;
    var modos = funcoesDoTipo();
    var copia = PAINEL_POR_TIPO[tipoEscolhido()];
    equipe.classList.toggle("os-equipe--funcoes", modos.length > 0);
    escolhidos.querySelectorAll(".multi-pick__escolhido").forEach(function (linha) { decorarLinha(linha, modos, copia); });
    decorando = false;
  }

  function montarEntradas() {
    if (!entradas) return;
    entradas.textContent = "";
    if (!funcoesDoTipo().length) return;
    marcados("servidores").forEach(function (caixa) {
      var funcao = funcoes[caixa.value];
      if (!funcao) return;
      var oculto = document.createElement("input");
      oculto.type = "hidden";
      oculto.name = "funcao_servidor_" + caixa.value;
      oculto.value = funcao;
      entradas.appendChild(oculto);
    });
  }

  function sincronizarFuncoes() {
    marcarCartaoDeTipo();
    var modos = funcoesDoTipo();
    // Função de servidor que saiu da equipe, ou que não existe neste tipo, cai.
    var ids = marcados("servidores").map(function (caixa) { return caixa.value; });
    Object.keys(funcoes).forEach(function (id) {
      if (ids.indexOf(id) === -1 || (modos.length && modos.indexOf(funcoes[id]) === -1)) delete funcoes[id];
    });
    decorar();
    montarEntradas();
  }

  // O multi-pick refaz as linhas ao buscar, marcar e remover: redecora sempre.
  if (escolhidos && window.MutationObserver) {
    new MutationObserver(function () { if (!decorando) sincronizarFuncoes(); }).observe(escolhidos, { childList: true });
  }

  form.addEventListener("change", function (evento) {
    if (evento.target.name === "tipo_necessidade") {
      sincronizarFuncoes();
      atualizarRotulo();
    }
    if (evento.target.name === "servidores") window.setTimeout(sincronizarFuncoes, 0);
  });
  form.addEventListener("click", function (evento) {
    var remover = evento.target.closest("[data-os-equipe] .multi-pick__remover");
    if (remover) window.setTimeout(function () { sincronizarFuncoes(); atualizarRotulo(); }, 0);
    // Clicar numa função a aplica ao servidor da linha; clicar de novo a tira.
    var botao = evento.target.closest("[data-os-funcao]");
    if (!botao) return;
    var id = botao.dataset.osServidor;
    if (funcoes[id] === botao.dataset.osFuncao) delete funcoes[id];
    else funcoes[id] = botao.dataset.osFuncao;
    sincronizarFuncoes();
  });

  /* ---- 4. Rótulo do botão principal -------------------------------------- */

  function osCompleta() {
    var inicio = form.querySelector('input[name="data_evento_inicio"]');
    var fim = form.querySelector('input[name="data_evento_fim"]');
    var primeira = form.querySelector("[data-destinos] [data-destino-linha] .destino-row__campo select");
    var motivo = form.querySelector('textarea[name="motivo"]');
    return !!(inicio && inicio.value) && !!(fim && fim.value)
      && !!(primeira && primeira.value)
      && marcados("servidores").length > 0
      && !!tipoEscolhido()
      && !!(motivo && motivo.value.trim());
  }

  function atualizarRotulo() {
    var rotulo = osCompleta() ? "Finalizar Ordem de Serviço" : "Salvar como rascunho";
    document.querySelectorAll("[data-os-enviar]").forEach(function (botao) {
      if (botao.textContent !== rotulo) botao.textContent = rotulo;
    });
  }

  var agendado = null;
  function agendarRotulo() {
    window.clearTimeout(agendado);
    agendado = window.setTimeout(atualizarRotulo, 150);
  }
  form.addEventListener("input", agendarRotulo);
  form.addEventListener("change", agendarRotulo);
  form.addEventListener("click", function (evento) {
    if (evento.target.closest(".multi-pick__remover, [data-destino-remover]")) agendarRotulo();
  });

  /* ---- 5. Destinos: "+" insere abaixo, lixeira remove, alça reordena ------ */

  (function () {
    var lista = form.querySelector("[data-destinos]");
    var modelo = form.querySelector("[data-destino-modelo]");
    var quantidade = form.querySelector('input[name="quantidade_destinos"]');
    if (!lista || !modelo || !quantidade) return;
    // Índice novo nunca repete os que o servidor já usou: o envio renumera tudo.
    var proximo = Number(quantidade.value);
    if (!(proximo >= 0)) proximo = 0;

    function linhas() {
      return Array.prototype.slice.call(lista.querySelectorAll("[data-destino-linha]"));
    }

    function selectsDe(linha) {
      return {
        estado: linha.querySelector(".destino-row__estado select"),
        cidade: linha.querySelector(".destino-row__campo select")
      };
    }

    function atualizarEstado() {
      var unica = linhas().length <= 1;
      linhas().forEach(function (linha) { linha.classList.toggle("destino-row--unica", unica); });
    }

    function criarLinha(depoisDe) {
      var indice = proximo;
      proximo += 1;
      var apoio = document.createElement("div");
      apoio.innerHTML = modelo.innerHTML.replace(/__n__/g, String(indice)).trim();
      var linha = apoio.firstElementChild;
      if (!linha) return;
      if (depoisDe) lista.insertBefore(linha, depoisDe.nextSibling);
      else lista.appendChild(linha);
      if (window.DS && window.DS.aprimorar) window.DS.aprimorar(linha);
      atualizarEstado();
      var campo = linha.querySelector("[data-custom-select-trigger]");
      if (campo) campo.focus({ preventScroll: true });
    }

    function limpar(linha) {
      var campos = selectsDe(linha);
      [campos.estado, campos.cidade].forEach(function (select) {
        if (!select || !select.value) return;
        select.value = "";
        disparar(select, "change");
      });
    }

    lista.addEventListener("click", function (evento) {
      var adicionar = evento.target.closest("[data-destino-adicionar]");
      if (adicionar) { criarLinha(adicionar.closest("[data-destino-linha]")); return; }
      var remover = evento.target.closest("[data-destino-remover]");
      if (!remover) return;
      var linha = remover.closest("[data-destino-linha]");
      // A última linha esvazia em vez de sumir: a OS sempre tem onde pôr o destino.
      if (linhas().length <= 1) { limpar(linha); return; }
      linha.remove();
      atualizarEstado();
      agendarRotulo();
    });

    if (window.DS && window.DS.arrastarDestinos) window.DS.arrastarDestinos(lista, function () {});

    // A nomeação final sai daqui: a primeira linha é o destino da OS e as
    // outras viram `extra_*_0..n-1`, na ordem da tela.
    form.addEventListener("submit", function () {
      var atuais = linhas();
      atuais.forEach(function (linha, posicao) {
        var campos = selectsDe(linha);
        if (campos.estado) campos.estado.name = posicao === 0 ? "destino_estado" : "extra_estado_" + (posicao - 1);
        if (campos.cidade) campos.cidade.name = posicao === 0 ? "destino_cidade" : "extra_cidade_" + (posicao - 1);
      });
      quantidade.value = String(Math.max(0, atuais.length - 1));
    });

    atualizarEstado();
  })();

  /* ---- arranque ----------------------------------------------------------- */

  sincronizarFuncoes();
  atualizarRotulo();
})();
