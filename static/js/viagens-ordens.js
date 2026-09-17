/**
 * Cadastro da ordem de serviço — o `ordens-servico-form.js` da origem na
 * pele da casa: os ofícios marcados copiam datas, equipe, motivo e destino
 * para a tela; o modelo de motivo preenche o texto; a necessidade escolhida
 * mostra o painel de funções (só caminhão, micro-ônibus e cerimonial); cada
 * função vira `funcao_servidor_<id>` no envio; e o botão principal diz se a
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

  function marcados(nome) {
    return opcoesDe(nome).filter(function (caixa) { return caixa.checked; });
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
  // O "×" do escolhido desmarca sem disparar `change`: ouve-se o clique.
  form.addEventListener("click", function (evento) {
    var remover = evento.target.closest("[data-os-oficios] .multi-pick__remover");
    if (remover) window.setTimeout(aplicarOficios, 0);
  });

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

  /* ---- 3. Necessidade e painel de funções -------------------------------- */

  var funcoes = lerJson("os-funcoes-servidores");
  var painel = form.querySelector("[data-os-funcoes]");
  var tituloPainel = painel && painel.querySelector("[data-os-funcoes-titulo]");
  var segmentos = painel && painel.querySelector("[data-os-funcoes-seg]");
  var cartoes = painel && painel.querySelector("[data-os-funcoes-cartoes]");
  var entradas = form.querySelector("[data-os-funcoes-inputs]");
  var funcaoAtiva = "";

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

  function montarSegmentos() {
    if (!segmentos) return;
    var modos = funcoesDoTipo();
    if (modos.indexOf(funcaoAtiva) === -1) funcaoAtiva = modos[0] || "";
    segmentos.textContent = "";
    modos.forEach(function (modo) {
      var botao = document.createElement("button");
      botao.type = "button";
      botao.dataset.osFuncao = modo;
      botao.setAttribute("aria-pressed", modo === funcaoAtiva ? "true" : "false");
      botao.textContent = FUNCOES[modo];
      segmentos.appendChild(botao);
    });
  }

  function cartaoDoServidor(caixa) {
    var opcao = caixa.closest("[data-multi-opcao]");
    var id = caixa.value;
    var funcao = funcoes[id] || "";
    var cartao = document.createElement("div");
    cartao.className = "of-membro ofc-pessoa os-func-cartao";
    cartao.dataset.osServidor = id;
    cartao.setAttribute("role", "button");
    cartao.tabIndex = 0;
    cartao.title = "Clique para definir a função";
    cartao.classList.toggle("is-atribuido", !!funcao);
    cartao.classList.toggle("is-ativa", !!funcao && funcao === funcaoAtiva);
    cartao.setAttribute("aria-pressed", funcao === funcaoAtiva ? "true" : "false");
    var avatar = document.createElement("span");
    avatar.className = "of-av";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = opcao.dataset.iniciais || "—";
    var texto = document.createElement("span");
    texto.className = "of-pessoa__txt";
    var nome = document.createElement("span");
    nome.className = "of-pessoa__nome";
    nome.textContent = opcao.dataset.nome || "";
    var selo = document.createElement("span");
    selo.className = "st os-func-selo" + (funcao ? "" : " os-func-selo--vazio");
    selo.textContent = funcao ? FUNCOES[funcao] : "Sem função - texto padrão";
    nome.appendChild(selo);
    texto.appendChild(nome);
    if (opcao.dataset.detalhes) {
      var desc = document.createElement("span");
      desc.className = "of-pessoa__desc";
      desc.textContent = opcao.dataset.detalhes;
      texto.appendChild(desc);
    }
    cartao.appendChild(avatar);
    cartao.appendChild(texto);
    return cartao;
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
    if (!painel) return;
    var modos = funcoesDoTipo();
    var copia = PAINEL_POR_TIPO[tipoEscolhido()];
    painel.hidden = !modos.length;
    if (copia) {
      if (tituloPainel) tituloPainel.textContent = copia.titulo;
      if (segmentos) segmentos.setAttribute("aria-label", copia.aria);
    }
    // Função de servidor que saiu da equipe, ou que não existe neste tipo, cai.
    var equipe = marcados("servidores").map(function (caixa) { return caixa.value; });
    Object.keys(funcoes).forEach(function (id) {
      if (equipe.indexOf(id) === -1 || (modos.length && modos.indexOf(funcoes[id]) === -1)) delete funcoes[id];
    });
    montarSegmentos();
    if (cartoes) {
      cartoes.textContent = "";
      if (modos.length) {
        marcados("servidores").forEach(function (caixa) { cartoes.appendChild(cartaoDoServidor(caixa)); });
      }
    }
    montarEntradas();
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
  });

  if (painel) {
    painel.addEventListener("click", function (evento) {
      var botao = evento.target.closest("[data-os-funcao]");
      if (botao) {
        funcaoAtiva = botao.dataset.osFuncao;
        sincronizarFuncoes();
        return;
      }
      var cartao = evento.target.closest("[data-os-servidor]");
      if (!cartao) return;
      atribuir(cartao.dataset.osServidor);
    });
    painel.addEventListener("keydown", function (evento) {
      if (evento.key !== "Enter" && evento.key !== " ") return;
      var cartao = evento.target.closest("[data-os-servidor]");
      if (!cartao) return;
      evento.preventDefault();
      atribuir(cartao.dataset.osServidor);
    });
  }

  // Clicar no cartão aplica a função ativa; clicar de novo a tira.
  function atribuir(id) {
    if (!funcaoAtiva) return;
    if (funcoes[id] === funcaoAtiva) delete funcoes[id];
    else funcoes[id] = funcaoAtiva;
    sincronizarFuncoes();
  }

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
