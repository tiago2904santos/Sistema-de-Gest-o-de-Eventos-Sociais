/*
 * Editor de roteiro (módulo Viagens).
 *
 * - a SEDE e os DESTINOS (linhas reordenáveis) definem o percurso;
 * - os TRECHOS são gerados a partir deles, um por linha da tabela: origem e
 *   destino em leitura, saída na própria linha, tempo adicional em passos de
 *   15min; a chegada é composta (saída + viagem + adicional);
 * - cada trecho recém-gerado é ESTIMADO pelo servidor (distância e tempo de
 *   viagem), sem precisar calcular a rota inteira;
 * - o RETORNO é o último deslocamento até a sede (sentido=RETORNO);
 * - o BATE-VOLTA diário gera, para cada dia do período, uma ida e uma volta;
 * - "Calcular rota" pergunta ao servidor (OpenRouteService), preenche as
 *   métricas, os tempos, as distâncias e o desenho no mapa, e guarda a rota
 *   em campos ocultos para ela ser gravada com o roteiro; mudar o percurso
 *   depois disso marca a rota como desatualizada;
 * - a PRÉVIA das diárias envia o formulário como está, sem gravar;
 * - o RASCUNHO é gravado sozinho um segundo depois da última mudança;
 * - o painel lateral (resumo e etapas) é derivado do estado da tela.
 *
 * Linhas nunca saem do DOM: remover esvazia e esconde (o servidor ignora
 * slots em branco) ou marca o DELETE do formset quando a linha já tem id.
 */
(function () {
  "use strict";

  var editor = document.querySelector("[data-roteiro-editor]");
  if (!editor) return;

  var formulario = editor.querySelector("form");
  var corpoTrechos = editor.querySelector("[data-trechos] tbody");
  var avisoVazio = editor.querySelector("[data-trechos-vazio]");
  var tabelaTrechos = editor.querySelector("[data-trechos-tabela]");
  var modeloTrecho = editor.querySelector("[data-trecho-modelo]");
  var totalTrechos = editor.querySelector('input[name="trechos-TOTAL_FORMS"]');
  var iniciaisTrechos = editor.querySelector('input[name="trechos-INITIAL_FORMS"]');
  var listaDestinos = editor.querySelector("[data-destinos]");
  var modeloDestino = editor.querySelector("[data-destino-modelo]");
  var totalDestinos = editor.querySelector('input[name="destinos-TOTAL_FORMS"]');
  var iniciaisDestinos = editor.querySelector('input[name="destinos-INITIAL_FORMS"]');
  var sede = editor.querySelector('select[name="origem_municipio"]');
  var servidoresInput = editor.querySelector('input[name="quantidade_servidores"]');

  var urlPrevia = editor.getAttribute("data-url-previa");
  var urlRota = editor.getAttribute("data-url-rota");
  var urlEstimar = editor.getAttribute("data-url-estimar");
  var urlAutosave = editor.getAttribute("data-url-autosave");
  var autosaveLigado = editor.getAttribute("data-autosave") === "1";

  // Rótulo de qualquer município pelo id — o select da sede lista todos.
  var rotulos = {};
  if (sede) {
    Array.prototype.forEach.call(sede.options, function (opcao) {
      if (opcao.value) rotulos[opcao.value] = opcao.text;
    });
  }

  // Enquanto um estado inteiro é aplicado (roteiro base, datas em sequência),
  // os ouvintes de mudança ficam mudos: cada campo tocado disparava uma
  // sincronização, e a última desfazia as anteriores.
  var aplicandoEstado = false;

  function slice(colecao) { return Array.prototype.slice.call(colecao); }

  function minutosDe(hhmm) {
    var partes = String(hhmm || "").split(":");
    if (partes.length < 2) return null;
    var minutos = Number(partes[0]) * 60 + Number(partes[1]);
    return Number.isNaN(minutos) ? null : minutos;
  }

  function hhmmDe(minutos) {
    if (minutos === null || minutos === undefined || minutos < 0) return "";
    var h = Math.floor(minutos / 60);
    var m = minutos % 60;
    return String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0");
  }

  function humano(minutos) {
    if (minutos === null || minutos === undefined) return "—";
    var h = Math.floor(minutos / 60);
    var m = minutos % 60;
    if (h && m) return h + "h" + String(m).padStart(2, "0") + "min";
    if (h) return h + "h";
    return m + "min";
  }

  function km(valor) {
    if (valor === null || valor === undefined || valor === "") return "—";
    return Number(valor).toLocaleString("pt-BR", {
      minimumFractionDigits: 0, maximumFractionDigits: 2
    }) + " km";
  }

  function inteiroDe(valor) {
    var numero = Number(valor);
    return valor === "" || valor === null || valor === undefined || Number.isNaN(numero)
      ? null : numero;
  }

  function definirCampo(campo, valor) {
    if (!campo || campo.value === String(valor)) return;
    campo.value = valor;
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function isoDe(data) {
    return data.getFullYear() + "-" +
      String(data.getMonth() + 1).padStart(2, "0") + "-" +
      String(data.getDate()).padStart(2, "0");
  }

  function rotuloDataBr(iso) {
    var partes = String(iso || "").split("-");
    return partes.length === 3 ? partes[2] + "/" + partes[1] + "/" + partes[0] : "dd/mm/aaaa";
  }

  function escreverTexto(seletor, texto) {
    var alvo = editor.querySelector(seletor);
    if (alvo) alvo.textContent = texto;
  }

  function mostrarErro(seletor, mensagem) {
    var alvo = editor.querySelector(seletor);
    if (!alvo) return;
    if (mensagem) { alvo.textContent = mensagem; alvo.hidden = false; }
    else { alvo.textContent = ""; alvo.hidden = true; }
  }

  function tokenCsrf() {
    var campo = editor.querySelector('input[name="csrfmiddlewaretoken"]');
    return campo ? campo.value : "";
  }

  function postar(url, corpo) {
    if (!url || !window.fetch) return Promise.reject(new Error("sem fetch"));
    if (!(corpo instanceof FormData)) {
      var dados = new FormData();
      Object.keys(corpo || {}).forEach(function (chave) {
        var valor = corpo[chave];
        if (Array.isArray(valor)) valor.forEach(function (v) { dados.append(chave, v); });
        else dados.append(chave, valor);
      });
      corpo = dados;
    }
    if (!corpo.has("csrfmiddlewaretoken")) corpo.append("csrfmiddlewaretoken", tokenCsrf());
    return fetch(url, {
      method: "POST", body: corpo, headers: { "X-Requested-With": "fetch" }
    }).then(function (resposta) {
      if (!resposta.ok) throw new Error("HTTP " + resposta.status);
      return resposta.json();
    });
  }

  // Campo `id` do formset: com valor, a linha já existe no banco.
  function campoId(linha) { return linha.querySelector('input[name$="-id"]'); }
  function gravada(linha) { var id = campoId(linha); return Boolean(id && id.value); }
  function caixaExclusao(linha) { return linha.querySelector('input[name$="-DELETE"]'); }
  function indiceDe(linha) {
    var id = campoId(linha);
    var partes = id ? id.name.split("-") : [];
    return partes.length >= 3 ? Number(partes[1]) : -1;
  }

  // ------------------------------------------------------------------
  // Destinos
  // ------------------------------------------------------------------

  function linhasDestino() { return slice(editor.querySelectorAll("[data-destino]")); }

  function destinosVisiveis() {
    return linhasDestino().filter(function (linha) { return !linha.hidden; });
  }

  function selectDaLinha(linha) {
    return linha.querySelector('select[name$="-municipio"]');
  }

  function paradas() {
    return destinosVisiveis()
      .map(function (linha) { return selectDaLinha(linha).value; })
      .filter(Boolean);
  }

  function renumerarDestinos() {
    destinosVisiveis().forEach(function (linha, indice) {
      var ordem = linha.querySelector("[data-destino-ordem]");
      if (ordem) ordem.value = String(indice + 1);
    });
    // Com uma linha só não há o que remover: o botão some, como no editor
    // de referência.
    var unica = destinosVisiveis().length <= 1;
    linhasDestino().forEach(function (linha) {
      linha.classList.toggle("destino-row--unica", unica);
    });
    atualizarPercursoPrevia();
  }

  // "Sede › A › B" no subtítulo dos destinos, assim que houver algum.
  function atualizarPercursoPrevia() {
    var previa = editor.querySelector("[data-percurso-previa]");
    if (!previa) return;
    var nomes = paradas().map(function (id) { return rotulos[id] || "?"; });
    if (!nomes.length) {
      previa.textContent = previa.getAttribute("data-texto-padrao") || "";
      previa.classList.remove("percurso-previa");
      return;
    }
    var origem = sede && sede.value ? rotulos[sede.value] : "Sede";
    previa.textContent = [origem].concat(nomes).join(" › ");
    previa.classList.add("percurso-previa");
  }

  function slotDeDestino() {
    var iniciais = iniciaisDestinos ? Number(iniciaisDestinos.value) : 0;
    return linhasDestino().find(function (linha) {
      // Slot na faixa "inicial" do formset o servidor trata como linha
      // gravada (e a pula se estiver vazia): reaproveitá-lo perderia o
      // destino na gravação.
      return linha.hidden && !gravada(linha) && !selectDaLinha(linha).value &&
        indiceDe(linha) >= iniciais;
    });
  }

  function criarLinhaDestino(depoisDe) {
    var slot = slotDeDestino();
    if (!slot) {
      if (!modeloDestino || !totalDestinos) return null;
      var indice = Number(totalDestinos.value);
      listaDestinos.insertAdjacentHTML(
        "beforeend", modeloDestino.innerHTML.replace(/__prefix__/g, String(indice))
      );
      totalDestinos.value = String(indice + 1);
      slot = listaDestinos.lastElementChild;
      if (window.DS && window.DS.aprimorar) window.DS.aprimorar(slot);
    }
    var caixa = caixaExclusao(slot);
    if (caixa) caixa.checked = false;
    slot.hidden = false;
    // O "+" da linha insere logo abaixo dela; sem origem, vai para o fim.
    if (depoisDe && depoisDe !== slot) {
      listaDestinos.insertBefore(slot, depoisDe.nextSibling);
    } else {
      listaDestinos.appendChild(slot);
    }
    renumerarDestinos();
    return slot;
  }

  function removerLinhaDestino(linha) {
    var select = selectDaLinha(linha);
    if (destinosVisiveis().length <= 1) {
      // A última linha não some: só esvazia, para sempre haver onde escolher.
      if (select && select.value) definirCampo(select, "");
      return;
    }
    var caixa = caixaExclusao(linha);
    if (caixa) caixa.checked = gravada(linha);
    if (select && select.value) {
      select.value = "";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    linha.hidden = true;
    renumerarDestinos();
    sincronizarTrechos();
  }

  // Arrastar para reordenar, pela alça. A mecânica é a do editor de
  // referência: ponteiro (não o drag-and-drop do HTML5, que não anima), com
  // limiar de 8px antes de começar; a linha na mão apaga e a vizinha abre
  // espaço para onde ela vai cair — o vão que se alarga já diz o lugar, sem
  // precisar desenhar fio nenhum.
  var LIMIAR_ARRASTE = 8;
  var arraste = null;

  function limparAlvosDeSoltura() {
    linhasDestino().forEach(function (linha) {
      linha.classList.remove("is-drop-target", "is-drop-before", "is-drop-after");
    });
  }

  function alvoDeSoltura(arrastada, y) {
    var alvo = null;
    var menorDistancia = Infinity;
    destinosVisiveis().forEach(function (linha) {
      if (linha === arrastada) return;
      var caixa = linha.getBoundingClientRect();
      var centro = caixa.top + caixa.height / 2;
      var distancia = Math.abs(y - centro);
      if (distancia < menorDistancia) {
        menorDistancia = distancia;
        alvo = { linha: linha, depois: y >= centro };
      }
    });
    return alvo;
  }

  function marcarAlvo(alvo) {
    limparAlvosDeSoltura();
    if (!alvo) return;
    alvo.linha.classList.add("is-drop-target");
    alvo.linha.classList.add(alvo.depois ? "is-drop-after" : "is-drop-before");
  }

  function encerrarArraste() {
    if (arraste && arraste.linha) arraste.linha.classList.remove("is-dragging");
    arraste = null;
    document.body.classList.remove("is-arrastando-destino");
    limparAlvosDeSoltura();
    document.removeEventListener("pointermove", aoMoverPonteiro);
    document.removeEventListener("pointerup", aoSoltarPonteiro);
    document.removeEventListener("pointercancel", encerrarArraste);
  }

  function aoMoverPonteiro(evento) {
    if (!arraste) return;
    var dx = evento.clientX - arraste.x;
    var dy = evento.clientY - arraste.y;
    if (!arraste.ativo) {
      if (Math.sqrt(dx * dx + dy * dy) < LIMIAR_ARRASTE) return;
      arraste.ativo = true;
      arraste.linha.classList.add("is-dragging");
      document.body.classList.add("is-arrastando-destino");
    }
    evento.preventDefault();
    arraste.alvo = alvoDeSoltura(arraste.linha, evento.clientY);
    marcarAlvo(arraste.alvo);
  }

  function aoSoltarPonteiro(evento) {
    if (!arraste) return;
    if (!arraste.ativo) { encerrarArraste(); return; }
    evento.preventDefault();
    var alvo = arraste.alvo || alvoDeSoltura(arraste.linha, evento.clientY);
    var arrastada = arraste.linha;
    encerrarArraste();
    if (!alvo || alvo.linha === arrastada) return;
    var referencia = alvo.depois ? alvo.linha.nextSibling : alvo.linha;
    if (referencia === arrastada) return;
    listaDestinos.insertBefore(arrastada, referencia);
    renumerarDestinos();
    percursoManual = false;
    sincronizarTrechos();
  }

  editor.addEventListener("pointerdown", function (evento) {
    if (evento.button !== 0) return;
    // Com um destino só não há o que reordenar.
    if (destinosVisiveis().length <= 1) return;
    if (!evento.target.closest("[data-destino-alca]")) return;
    var linha = evento.target.closest("[data-destino]");
    if (!linha) return;
    encerrarArraste();
    arraste = { linha: linha, x: evento.clientX, y: evento.clientY, alvo: null, ativo: false };
    document.addEventListener("pointermove", aoMoverPonteiro);
    document.addEventListener("pointerup", aoSoltarPonteiro);
    document.addEventListener("pointercancel", encerrarArraste);
  });

  // ------------------------------------------------------------------
  // Trechos
  // ------------------------------------------------------------------

  function linhasTrecho() { return slice(editor.querySelectorAll("[data-trecho]")); }

  function trechosVisiveis() {
    return linhasTrecho().filter(function (linha) { return !linha.hidden; });
  }

  // Os trechos que valem: visíveis e não marcados para exclusão.
  function trechosAtivos() {
    return trechosVisiveis().filter(function (linha) {
      var caixa = caixaExclusao(linha);
      return !(caixa && caixa.checked);
    });
  }

  function linhaDeErros(linha) {
    var proxima = linha.nextElementSibling;
    return proxima && proxima.hasAttribute("data-trecho-erros") ? proxima : null;
  }

  function campoDe(linha, sufixo) {
    return linha.querySelector('[name$="-' + sufixo + '"]');
  }

  function valorDe(linha, sufixo) {
    var campo = campoDe(linha, sufixo);
    return campo ? campo.value : "";
  }

  function slotDeTrecho() {
    var iniciais = iniciaisTrechos ? Number(iniciaisTrechos.value) : 0;
    return linhasTrecho().find(function (linha) {
      return linha.hidden && !gravada(linha) && !valorDe(linha, "origem_municipio") &&
        indiceDe(linha) >= iniciais;
    });
  }

  function criarTrecho() {
    var slot = slotDeTrecho();
    if (slot) {
      var caixa = caixaExclusao(slot);
      if (caixa) caixa.checked = false;
      slot.hidden = false;
      return slot;
    }
    if (!modeloTrecho || !totalTrechos) return null;
    var indice = Number(totalTrechos.value);
    var html = modeloTrecho.innerHTML.replace(/__prefix__/g, String(indice));
    // O molde vem embrulhado num <table><tbody> porque <tr> solto não
    // sobrevive ao parser; aqui as duas linhas voltam para a tabela real.
    var molde = document.createElement("template");
    molde.innerHTML = html.trim();
    var linhas = slice(molde.content.querySelectorAll("tr"));
    linhas.forEach(function (linha) { corpoTrechos.appendChild(linha); });
    totalTrechos.value = String(indice + 1);
    if (window.DS && window.DS.aprimorar) window.DS.aprimorar(linhas[0].parentNode);
    return linhas[0];
  }

  function limparTrecho(linha) {
    slice(linha.querySelectorAll("input")).forEach(function (campo) {
      if (campo.hasAttribute("data-trecho-ordem")) return;
      if (campo.name && campo.name.slice(-3) === "-id") return;
      if (campo.type === "checkbox") { campo.checked = false; return; }
      var padrao = campo.hasAttribute("data-trecho-adicional-min") ? "0" : "";
      if (campo.value === padrao) return;
      campo.value = padrao;
      campo.dispatchEvent(new Event("change", { bubbles: true }));
    });
    linha.removeAttribute("data-adicional-manual");
    linha.removeAttribute("data-bv");
  }

  function esconderTrecho(linha) {
    // O percurso é derivado dos destinos: trecho que sai de cena é o que
    // perdeu o destino que o gerava. Já gravado, some pelo DELETE do
    // formset; novo, volta a ser um slot em branco.
    var caixa = caixaExclusao(linha);
    if (gravada(linha)) { if (caixa) caixa.checked = true; }
    else limparTrecho(linha);
    linha.hidden = true;
    var erros = linhaDeErros(linha);
    if (erros) erros.hidden = true;
  }

  function escreverEm(linha, seletor, texto) {
    var alvo = linha.querySelector(seletor);
    if (alvo) alvo.textContent = texto;
  }

  function atualizarLinha(linha) {
    var origem = rotulos[valorDe(linha, "origem_municipio")] || "";
    var destino = rotulos[valorDe(linha, "destino_municipio")] || "";
    escreverEm(linha, "[data-trecho-origem-rotulo]", origem || "—");
    escreverEm(linha, "[data-trecho-destino-rotulo]", destino || "—");
    var tag = linha.querySelector("[data-trecho-tag]");
    if (tag) tag.hidden = linha.getAttribute("data-sentido") !== "RETORNO";
  }

  function viagemDe(linha) { return inteiroDe(valorDe(linha, "tempo_viagem_min")); }
  function adicionalDe(linha) { return inteiroDe(valorDe(linha, "tempo_adicional_min")) || 0; }

  function definirViagem(linha, minutos, distanciaKm, fonte) {
    definirCampo(campoDe(linha, "tempo_viagem_min"), minutos === null ? "" : String(minutos));
    if (distanciaKm !== undefined) {
      definirCampo(campoDe(linha, "distancia_km"),
        distanciaKm === null ? "" : String(distanciaKm));
    }
    if (fonte !== undefined) definirCampo(campoDe(linha, "rota_fonte"), fonte || "");
  }

  function definirAdicional(linha, minutos, manual) {
    definirCampo(campoDe(linha, "tempo_adicional_min"), String(Math.max(0, minutos || 0)));
    if (manual) linha.setAttribute("data-adicional-manual", "1");
  }

  function atualizarTempos(linha) {
    var viagem = viagemDe(linha);
    var adicional = adicionalDe(linha);
    var duracaoMin = campoDe(linha, "duracao_min");

    // O tempo total é o da rota mais a espera informada à mão; é ele que
    // define a chegada e, por ela, a conta das diárias.
    var total = viagem === null ? (adicional || null) : viagem + adicional;

    escreverEm(linha, "[data-trecho-adicional-rotulo]", hhmmDe(adicional));
    escreverEm(linha, "[data-trecho-tempo-total]", total === null ? "—" : hhmmDe(total));
    escreverEm(linha, "[data-trecho-viagem-nota]",
      viagem === null ? "" : "viagem " + hhmmDe(viagem));
    if (duracaoMin) definirCampo(duracaoMin, total === null ? "" : String(total));

    // A chegada não é digitada: é a saída mais o tempo total, gravada em
    // campos ocultos — é dela que o motor calcula as diárias — e mostrada na
    // última coluna, para quem monta o percurso ver onde o trecho termina.
    var dataSaida = valorDe(linha, "saida_data");
    var horaSaida = valorDe(linha, "saida_hora");
    var textoChegada = "—";
    if (total !== null && dataSaida && horaSaida) {
      var saida = new Date(dataSaida + "T" + horaSaida);
      if (!Number.isNaN(saida.getTime())) {
        var chegada = new Date(saida.getTime() + total * 60000);
        var horaChegada = hhmmDe(chegada.getHours() * 60 + chegada.getMinutes());
        definirCampo(campoDe(linha, "chegada_data"), isoDe(chegada));
        definirCampo(campoDe(linha, "chegada_hora"), horaChegada);
        textoChegada = new Intl.DateTimeFormat("pt-BR").format(chegada) + " " + horaChegada;
      }
    } else {
      definirCampo(campoDe(linha, "chegada_data"), "");
      definirCampo(campoDe(linha, "chegada_hora"), "");
    }
    escreverEm(linha, "[data-trecho-chegada-rotulo]", textoChegada);
  }

  function ajustarAdicional(linha, passo) {
    // Nunca negativo: descontar espera que não houve encurtaria a viagem.
    definirAdicional(linha, adicionalDe(linha) + passo, true);
    atualizarTempos(linha);
    atualizarPainelLateral();
    agendarPrevia();
    agendarAutosave();
  }

  function aplicarPerna(linha, origem, destino, sentido) {
    var mudou = valorDe(linha, "origem_municipio") !== String(origem) ||
      valorDe(linha, "destino_municipio") !== String(destino);
    definirCampo(campoDe(linha, "origem_municipio"), origem);
    definirCampo(campoDe(linha, "destino_municipio"), destino);
    var campoSentido = campoDe(linha, "sentido");
    if (campoSentido) campoSentido.value = sentido;
    linha.setAttribute("data-sentido", sentido);
    linha.classList.toggle("trecho-linha--retorno", sentido === "RETORNO");
    if (mudou) {
      // Outro par de cidades: a estimativa anterior não vale mais. O
      // adicional que o operador ajustou à mão fica; o sugerido cai junto.
      definirViagem(linha, null, null, "");
      if (!linha.hasAttribute("data-adicional-manual")) definirAdicional(linha, 0, false);
    }
    atualizarLinha(linha);
    atualizarTempos(linha);
  }

  function renumerarTrechos() {
    var ativos = trechosVisiveis();
    ativos.forEach(function (linha, indice) {
      var ordem = linha.querySelector("[data-trecho-ordem]");
      var caixa = caixaExclusao(linha);
      if (ordem && !(caixa && caixa.checked)) ordem.value = String(indice + 1);
    });
    if (avisoVazio) avisoVazio.hidden = ativos.length > 0;
    if (tabelaTrechos) tabelaTrechos.hidden = ativos.length === 0;
    sincronizarCalendarioDeDatas();
    atualizarPainelLateral();
  }

  // Ligado, o bate-volta (ou um roteiro já gravado com trechos próprios)
  // comanda a tabela; os destinos deixam de regerar as linhas.
  var percursoManual = false;

  function sincronizarTrechos() {
    if (percursoManual) { atualizarPainelLateral(); return; }
    var origemSede = sede ? sede.value : "";
    var pontos = paradas();

    var pernas = [];
    var anterior = origemSede;
    pontos.forEach(function (parada) {
      if (anterior) pernas.push({ origem: anterior, destino: parada });
      anterior = parada;
    });

    var idas = trechosVisiveis().filter(function (linha) {
      return linha.getAttribute("data-sentido") !== "RETORNO";
    });
    pernas.forEach(function (perna, indice) {
      var linha = idas[indice] || criarTrecho();
      if (linha) aplicarPerna(linha, perna.origem, perna.destino, "IDA");
    });
    idas.slice(pernas.length).forEach(esconderTrecho);

    var retorno = trechosVisiveis().find(function (linha) {
      return linha.getAttribute("data-sentido") === "RETORNO";
    });
    if (pontos.length && origemSede) {
      if (!retorno) retorno = criarTrecho();
      if (retorno) {
        aplicarPerna(retorno, pontos[pontos.length - 1], origemSede, "RETORNO");
        var erros = linhaDeErros(retorno);
        corpoTrechos.appendChild(retorno);
        if (erros) corpoTrechos.appendChild(erros);
      }
    } else if (retorno) {
      esconderTrecho(retorno);
    }
    renumerarTrechos();
    verificarRotaDesatualizada();
    agendarEstimativas();
    agendarPrevia();
    agendarAutosave();
  }

  // O calendário do cabeçalho pede uma data por trecho: dois destinos são
  // três trechos (sede→1, 1→2, 2→sede), logo três datas. O máximo acompanha
  // o percurso, e cada passo mostra o trecho a que a data vai.
  // A página tem dois calendários múltiplos (datas de saída e bate-volta):
  // este é o do cabeçalho dos Trechos, pelo id do componente.
  var calendarioDatas = editor.querySelector("#datas-trechos[data-custom-date-multi]");

  function sincronizarCalendarioDeDatas() {
    if (!calendarioDatas) return;
    var ativos = trechosAtivos();
    calendarioDatas.setAttribute("data-max", String(Math.max(1, ativos.length)));
    calendarioDatas.setAttribute("data-passos", JSON.stringify(ativos.map(function (linha) {
      var origem = rotulos[valorDe(linha, "origem_municipio")] || "?";
      var destino = rotulos[valorDe(linha, "destino_municipio")] || "?";
      return origem + " → " + destino;
    })));
    var gatilho = calendarioDatas.querySelector("[data-custom-date-multi-trigger]");
    if (gatilho) gatilho.disabled = ativos.length === 0;
  }

  function aplicarDatasDeSaida(datas) {
    var ativos = trechosAtivos();
    aplicandoEstado = true;
    try {
      datas.forEach(function (iso, indice) {
        var linha = ativos[indice];
        if (!linha) return;
        definirCampo(campoDe(linha, "saida_data"), iso);
        atualizarTempos(linha);
      });
    } finally {
      aplicandoEstado = false;
    }
    atualizarPainelLateral();
    agendarPrevia();
    agendarAutosave();
  }

  if (calendarioDatas) {
    calendarioDatas.addEventListener("ds:datas-multi", function (evento) {
      aplicarDatasDeSaida(evento.detail.datas);
    });
  }

  // ------------------------------------------------------------------
  // Estimativa de cada trecho (distância e tempo de viagem)
  // ------------------------------------------------------------------

  // Assim que um trecho existe, o servidor estima distância e tempo de
  // viagem dele — sem esperar o "Calcular rota". Um por vez, para não
  // disparar uma rajada na API; a falha de um não cancela os outros.
  var estimativaAgendada = null;
  var estimativasFalhas = {};

  function agendarEstimativas() {
    if (!urlEstimar) return;
    if (estimativaAgendada) clearTimeout(estimativaAgendada);
    estimativaAgendada = setTimeout(estimarTrechos, 450);
  }

  function chaveDePerna(linha) {
    return valorDe(linha, "origem_municipio") + ">" + valorDe(linha, "destino_municipio");
  }

  function aplicarEstimativa(linha, dados) {
    definirViagem(linha, dados.tempo_viagem_min, dados.distancia_km, dados.fonte || "");
    // O adicional sugerido só entra onde o operador ainda não mexeu.
    if (!linha.hasAttribute("data-adicional-manual") && !adicionalDe(linha)) {
      definirAdicional(linha, dados.tempo_adicional_sugerido_min || 0, false);
    }
    atualizarTempos(linha);
  }

  function estimarTrechos() {
    estimativaAgendada = null;
    if (bateVoltaLigado()) return;
    var fila = trechosAtivos().filter(function (linha) {
      return valorDe(linha, "origem_municipio") && valorDe(linha, "destino_municipio") &&
        viagemDe(linha) === null && !estimativasFalhas[chaveDePerna(linha)];
    });
    if (!fila.length) return;
    var falhas = [];
    var motivo = "";
    fila.reduce(function (anterior, linha) {
      return anterior.then(function () {
        var perna = chaveDePerna(linha);
        return postar(urlEstimar, {
          origem: valorDe(linha, "origem_municipio"),
          destino: valorDe(linha, "destino_municipio"),
        }).then(function (dados) {
          if (!dados.ok) throw new Error(dados.motivo || "");
          // A linha pode ter mudado de par enquanto a resposta vinha.
          if (chaveDePerna(linha) !== perna || linha.hidden) return;
          aplicarEstimativa(linha, dados);
        }).catch(function (erro) {
          estimativasFalhas[perna] = true;
          falhas.push(perna);
          if (erro && erro.message && !motivo) motivo = erro.message;
        });
      });
    }, Promise.resolve()).then(function () {
      if (falhas.length) {
        var quantos = falhas.length === 1 ? "de um trecho" : "de " + falhas.length + " trechos";
        mostrarErro("[data-trechos-erro]",
          "Não foi possível estimar a distância " + quantos + ". " +
          (motivo || "Tente de novo alterando o destino."));
      } else {
        mostrarErro("[data-trechos-erro]", "");
      }
      atualizarPainelLateral();
      agendarPrevia();
      agendarAutosave();
    });
  }

  // ------------------------------------------------------------------
  // Rota e mapa
  // ------------------------------------------------------------------

  var mapaElemento = editor.querySelector("[data-mapa]");
  var mapa = null;
  var camadaRota = null;
  var limitesRota = null;
  var rotaCalculada = null;   // a última rota válida (do servidor ou gravada)
  var rotaEmVoo = false;

  var COR_LINHA = "#333333";
  var COR_HALO = "#ffffff";
  var COR_SEDE = "#bea45a";
  var COR_DESTINO = "#333333";

  function garantirMapa() {
    if (mapa || !mapaElemento || !window.L) return mapa;
    // Sem zoom pela roda: rolar a página sobre o mapa mudava a escala em
    // vez de descer a tela. O zoom continua nos botões + e −.
    mapa = window.L.map(mapaElemento, { scrollWheelZoom: false })
      .setView([-24.6, -51.5], 7);
    window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "© OpenStreetMap",
    }).addTo(mapa);
    // O Leaflet mede o container na criação; se o layout ainda estava
    // assentando, ele fica com a altura errada e sobra uma faixa cinza.
    // Remedir no quadro seguinte resolve, e o observador cobre as mudanças
    // de tamanho posteriores (janela, lateral, painel que abre).
    window.requestAnimationFrame(function () { mapa.invalidateSize(); });
    if (window.ResizeObserver) {
      new window.ResizeObserver(function () { mapa.invalidateSize(); })
        .observe(mapaElemento);
    }
    return mapa;
  }

  function pontosDoPercurso() {
    var ids = [];
    trechosAtivos().forEach(function (linha) {
      var origem = valorDe(linha, "origem_municipio");
      var destino = valorDe(linha, "destino_municipio");
      if (origem && (!ids.length || ids[ids.length - 1] !== origem)) ids.push(origem);
      if (destino) ids.push(destino);
    });
    return ids;
  }

  function focarPonto(lat, lng) {
    if (!mapa) return;
    mapa.flyTo([lat, lng], Math.max(mapa.getZoom(), 11), { duration: 0.75 });
  }

  function desenharRota(dados) {
    var leaflet = garantirMapa();
    if (!leaflet) return;
    if (camadaRota) camadaRota.remove();
    camadaRota = window.L.layerGroup().addTo(leaflet);
    limitesRota = null;

    if (dados.geometria && dados.geometria.coordinates) {
      var linha = dados.geometria.coordinates.map(function (par) { return [par[1], par[0]]; });
      // Halo claro por baixo da linha escura: a rota se destaca do mapa sem
      // brigar com as estradas desenhadas nele.
      window.L.polyline(linha, { color: COR_HALO, weight: 9, opacity: 0.85 }).addTo(camadaRota);
      window.L.polyline(linha, { color: COR_LINHA, weight: 4, opacity: 0.95 }).addTo(camadaRota);
      limitesRota = window.L.polyline(linha).getBounds();
    }

    var vistos = {};
    (dados.pontos || []).forEach(function (ponto, indice) {
      var chave = ponto.lat + "|" + ponto.lng;
      if (vistos[chave]) return;
      vistos[chave] = true;
      var eSede = indice === 0;
      var marcador = window.L.circleMarker([ponto.lat, ponto.lng], {
        radius: eSede ? 7 : 6,
        color: eSede ? COR_SEDE : COR_DESTINO,
        weight: eSede ? 3 : 2,
        fillColor: eSede ? COR_SEDE : "#ffffff",
        fillOpacity: 1,
      }).addTo(camadaRota);
      marcador.bindTooltip(ponto.nome.toUpperCase() + "/" + ponto.uf, {
        permanent: true, direction: "top", offset: [0, -10],
        className: "mapa__rotulo" + (eSede ? " mapa__rotulo--sede" : ""),
      });
      marcador.on("click", function () { focarPonto(ponto.lat, ponto.lng); });
      if (!limitesRota) limitesRota = window.L.latLngBounds([ponto.lat, ponto.lng], [ponto.lat, ponto.lng]);
      else limitesRota.extend([ponto.lat, ponto.lng]);
    });

    if (limitesRota && limitesRota.isValid()) {
      leaflet.fitBounds(limitesRota, { padding: [32, 32], maxZoom: 12 });
    }
    var enquadrar = editor.querySelector("[data-rota-enquadrar]");
    if (enquadrar) enquadrar.hidden = !(limitesRota && limitesRota.isValid());
  }

  function mostrarMetricas(dados) {
    var segmentos = dados.segmentos || [];
    var idaKm = null;
    var idaMin = null;
    if (segmentos.length > 1) {
      idaKm = 0; idaMin = 0;
      segmentos.forEach(function (segmento, indice) {
        if (indice < segmentos.length - 1) {
          idaKm += segmento.distancia_km;
          idaMin += segmento.tempo_viagem_min || segmento.duracao_min;
        }
      });
      idaKm = Math.round(idaKm * 100) / 100;
    } else if (dados.distancia_total_km !== null && dados.distancia_total_km !== undefined) {
      // Rota gravada sem os segmentos: a ida é metade do circuito.
      idaKm = Math.round(dados.distancia_total_km * 50) / 100;
      idaMin = Math.floor((dados.duracao_total_min || 0) / 2);
    }
    escreverTexto("[data-rota-distancia-total]", km(dados.distancia_total_km));
    escreverTexto("[data-rota-tempo-total]", humano(dados.duracao_total_min));
    escreverTexto("[data-rota-distancia-ida]", km(idaKm));
    escreverTexto("[data-rota-tempo-ida]", humano(idaMin));
  }

  // A rota viaja com o formulário: geometria, totais, fonte, assinatura do
  // percurso e quando foi calculada. É o que o servidor grava no roteiro.
  function guardarRotaNoFormulario(dados) {
    function campo(nome) { return editor.querySelector('[data-rota-campo="' + nome + '"]'); }
    var geometria = campo("geojson");
    if (!geometria) return;
    if (!dados) {
      ["geojson", "distancia", "duracao", "fonte", "assinatura", "calculada_em"]
        .forEach(function (nome) { var c = campo(nome); if (c) c.value = ""; });
      return;
    }
    geometria.value = dados.geometria ? JSON.stringify(dados.geometria) : "";
    campo("distancia").value = dados.distancia_total_km === null ? "" : String(dados.distancia_total_km);
    campo("duracao").value = dados.duracao_total_min === null ? "" : String(dados.duracao_total_min);
    campo("fonte").value = dados.fonte || "";
    campo("assinatura").value = dados.assinatura || "";
    campo("calculada_em").value = dados.calculada_em || "";
  }

  var ROTULOS_ROTA = {
    PENDENTE: ["Rota pendente", "status-badge--rascunho", "Pendente"],
    CALCULADA: ["Rota calculada", "status-badge--atendida", "Calculada"],
    DESATUALIZADA: ["Rota desatualizada", "status-badge--pendente", "Desatualizada — recalcule"],
  };

  function definirStatusRota(status) {
    var chip = editor.querySelector("[data-rota-status]");
    var aviso = editor.querySelector("[data-rota-desatualizada]");
    var dados = ROTULOS_ROTA[status] || ROTULOS_ROTA.PENDENTE;
    if (chip) {
      chip.textContent = dados[0];
      chip.className = "status-badge " + dados[1];
    }
    if (aviso) aviso.hidden = status !== "DESATUALIZADA";
    escreverTexto("[data-resumo-rota]", dados[2]);
    var rotuloBotao = editor.querySelector("[data-rota-calcular-rotulo]");
    if (rotuloBotao) rotuloBotao.textContent = rotaCalculada ? "Recalcular rota" : "Calcular rota";
  }

  // O percurso de agora ainda é o que a rota descreve? Comparado pelos ids
  // dos municípios, na ordem — a mesma assinatura que o servidor confere.
  function verificarRotaDesatualizada() {
    if (!rotaCalculada) { definirStatusRota("PENDENTE"); return; }
    var atual = pontosDoPercurso().join(">");
    var daRota = (rotaCalculada.ids || []).join(">");
    definirStatusRota(atual === daRota ? "CALCULADA" : "DESATUALIZADA");
  }

  function aplicarRota(dados, opcoes) {
    opcoes = opcoes || {};
    rotaCalculada = dados;
    rotaCalculada.ids = (dados.pontos || []).map(function (p) { return String(p.id); });
    mostrarMetricas(dados);
    guardarRotaNoFormulario(dados);

    // Os segmentos preenchem os trechos na ordem; ao recalcular, o adicional
    // sugerido volta por cima do que estava (é o que "recalcular" promete).
    var ativos = trechosAtivos();
    (dados.segmentos || []).forEach(function (segmento, indice) {
      var linha = ativos[indice];
      if (!linha) return;
      definirViagem(linha, segmento.tempo_viagem_min, segmento.distancia_km, dados.fonte || "");
      if (opcoes.sobrescreverAdicional || !linha.hasAttribute("data-adicional-manual")) {
        definirAdicional(linha, segmento.tempo_adicional_sugerido_min || 0, false);
        linha.removeAttribute("data-adicional-manual");
      }
      atualizarTempos(linha);
    });

    desenharRota(dados);
    verificarRotaDesatualizada();
    atualizarPainelLateral();
    agendarPrevia();
    agendarAutosave();
  }

  function mostrarCarregandoRota(ligado) {
    var carregando = editor.querySelector("[data-rota-carregando]");
    var botao = editor.querySelector("[data-rota-calcular]");
    if (carregando) carregando.hidden = !ligado;
    if (botao) botao.disabled = ligado;
  }

  function calcularRota() {
    if (!urlRota || rotaEmVoo) return;
    if (bateVoltaLigado()) {
      mostrarErro("[data-rota-erro]",
        "Desative o modo bate-volta diário para calcular a rota pelo mapa.");
      return;
    }
    var ids = pontosDoPercurso();
    if (ids.length < 2) {
      mostrarErro("[data-rota-erro]", "Defina a sede e ao menos um destino para calcular a rota.");
      return;
    }
    var recalculo = Boolean(rotaCalculada);
    mostrarErro("[data-rota-erro]", "");
    mostrarCarregandoRota(true);
    rotaEmVoo = true;
    postar(urlRota, { municipios: ids })
      .then(function (dados) {
        if (!dados.ok) { mostrarErro("[data-rota-erro]", dados.motivo); return; }
        aplicarRota(dados, { sobrescreverAdicional: recalculo });
      })
      .catch(function () {
        mostrarErro("[data-rota-erro]", "Falha de rede ao calcular a rota. Tente novamente.");
      })
      .then(function () {
        rotaEmVoo = false;
        mostrarCarregandoRota(false);
      });
  }

  function enquadrarRota() {
    if (mapa && limitesRota && limitesRota.isValid()) {
      mapa.fitBounds(limitesRota, { padding: [32, 32], maxZoom: 12 });
    }
  }

  // Roteiro reaberto com rota gravada: o mapa nasce desenhado, com os totais
  // e a situação que o servidor apurou (calculada ou desatualizada).
  function carregarRotaInicial() {
    var script = document.getElementById("rota-inicial");
    if (!script) return;
    var dados;
    try { dados = JSON.parse(script.textContent); } catch (erro) { return; }
    if (!dados || !dados.geometria) return;
    rotaCalculada = dados;
    rotaCalculada.ids = (dados.pontos || []).map(function (p) { return String(p.id); });
    mostrarMetricas(dados);
    guardarRotaNoFormulario(dados);
    desenharRota(dados);
    verificarRotaDesatualizada();
  }

  // ------------------------------------------------------------------
  // Bate-volta diário
  // ------------------------------------------------------------------

  function valorBv(nome) {
    var campo = editor.querySelector('[name="bv_' + nome + '"]');
    return campo ? campo.value : "";
  }

  function bateVoltaLigado() {
    var painel = editor.querySelector("[data-bate-volta]");
    return Boolean(painel && !painel.hidden);
  }

  // Os campos de data da ida e da volta são gatilhos do mesmo calendário: as
  // duas datas escolhidas nele entram na ordem — a primeira na ida, a segunda
  // na volta. Uma data só serve para ida e volta no mesmo dia.
  var painelDatasBv = editor.querySelector(".bate-volta__sentidos[data-custom-date-multi]");

  function mostrarDatasBv() {
    ["ida", "volta"].forEach(function (sentido) {
      var campo = editor.querySelector('[name="bv_' + sentido + '_data"]');
      var rotulo = editor.querySelector('[data-bv-rotulo="' + sentido + '"]');
      if (!campo || !rotulo) return;
      rotulo.textContent = rotuloDataBr(campo.value);
      rotulo.closest(".custom-date__trigger").classList.toggle("has-value", Boolean(campo.value));
    });
  }

  if (painelDatasBv) {
    painelDatasBv.addEventListener("ds:datas-multi", function (evento) {
      var datas = evento.detail.datas.slice().sort();
      if (!datas.length) return;
      definirCampo(editor.querySelector('[name="bv_ida_data"]'), datas[0]);
      definirCampo(editor.querySelector('[name="bv_volta_data"]'), datas[1] || datas[0]);
      mostrarDatasBv();
      agendarBateVolta();
    });
  }

  // Os trechos nascem sozinhos quando período e horários estão completos —
  // não há botão. Regerar substitui os trechos do bate-volta anteriores, em
  // vez de empilhar: cada linha gerada carrega a marca `data-bv`.
  function limparTrechosDoBateVolta() {
    linhasTrecho().forEach(function (linha) {
      if (linha.hasAttribute("data-bv")) {
        linha.removeAttribute("data-bv");
        esconderTrecho(linha);
      }
    });
  }

  // Ligado, o bate-volta É o percurso: ida e volta repetidas por dia. Os
  // trechos derivados dos destinos sairiam repetidos e sem data ao lado dos
  // gerados, então saem de cena enquanto ele comanda.
  function limparTrechosDerivados() {
    trechosVisiveis().forEach(function (linha) {
      if (!linha.hasAttribute("data-bv")) esconderTrecho(linha);
    });
  }

  function diasEntre(inicioIso, fimIso) {
    var dias = [];
    var atual = new Date(inicioIso + "T00:00");
    var fim = new Date(fimIso + "T00:00");
    if (Number.isNaN(atual.getTime()) || Number.isNaN(fim.getTime())) return dias;
    // Um teto para um dedo escorregado no calendário não gerar um ano de
    // trechos de uma vez.
    while (atual <= fim && dias.length < 62) {
      dias.push(isoDe(atual));
      atual = new Date(atual.getFullYear(), atual.getMonth(), atual.getDate() + 1);
    }
    return dias;
  }

  function gerarTrechoBv(origem, destino, sentido, data, saidaMin, tempoMin) {
    var linha = criarTrecho();
    if (!linha) return;
    linha.setAttribute("data-bv", "");
    aplicarPerna(linha, origem, destino, sentido);
    definirCampo(campoDe(linha, "saida_data"), data);
    definirCampo(campoDe(linha, "saida_hora"), hhmmDe(saidaMin));
    definirViagem(linha, tempoMin, null, "bate-volta");
    definirAdicional(linha, 0, false);
    atualizarTempos(linha);
  }

  function gerarBateVolta() {
    var painel = editor.querySelector("[data-bate-volta]");
    var resumo = editor.querySelector("[data-bate-volta-resumo]");
    if (!painel || painel.hidden) return;

    function falhar(mensagem) {
      limparTrechosDoBateVolta();
      renumerarTrechos();
      mostrarErro("[data-bate-volta-erro]", mensagem);
    }
    function aguardar() {
      // Preenchimento em curso não é erro: a tela só espera em silêncio.
      mostrarErro("[data-bate-volta-erro]", "");
      limparTrechosDoBateVolta();
      renumerarTrechos();
      if (resumo) resumo.textContent = "Preencha as datas, as saídas e o tempo de viagem: os trechos de cada dia nascem sozinhos.";
    }
    mostrarErro("[data-bate-volta-erro]", "");

    var pontos = paradas();
    if (pontos.length > 1) {
      return falhar("No modo bate-volta diário, informe exatamente um destino.");
    }
    var destino = pontos[0];
    var idaData = valorBv("ida_data");
    var voltaData = valorBv("volta_data");
    var idaSaida = minutosDe(valorBv("ida_saida"));
    var idaTempo = minutosDe(valorBv("ida_tempo"));
    var voltaSaida = minutosDe(valorBv("volta_saida"));
    var voltaTempo = minutosDe(valorBv("volta_tempo"));

    var incompleto = !sede || !sede.value || !destino || !idaData || !voltaData ||
      [idaSaida, idaTempo, voltaSaida, voltaTempo].some(function (v) { return v === null; });
    if (incompleto) return aguardar();
    if (voltaData < idaData) return falhar("A data da volta não pode ser anterior à da ida.");

    var dias = diasEntre(idaData, voltaData);
    if (!dias.length) return aguardar();

    aplicandoEstado = true;
    try {
      limparTrechosDoBateVolta();
      limparTrechosDerivados();
      percursoManual = true;
      // Cada dia do período é uma ida e uma volta; só a última volta é o
      // retorno de verdade — as outras são deslocamentos do dia.
      dias.forEach(function (dia, indice) {
        var ultimo = indice === dias.length - 1;
        gerarTrechoBv(sede.value, destino, "IDA", dia, idaSaida, idaTempo);
        gerarTrechoBv(destino, sede.value, ultimo ? "RETORNO" : "IDA", dia, voltaSaida, voltaTempo);
      });
    } finally {
      aplicandoEstado = false;
    }
    if (resumo) {
      resumo.textContent = dias.length + (dias.length === 1 ? " dia" : " dias") +
        " · " + (dias.length * 2) + " trechos gerados (ida e volta por dia).";
    }
    renumerarTrechos();
    verificarRotaDesatualizada();
    agendarPrevia();
    agendarAutosave();
  }

  var bateVoltaAgendado = null;

  function agendarBateVolta() {
    if (bateVoltaAgendado) clearTimeout(bateVoltaAgendado);
    bateVoltaAgendado = setTimeout(gerarBateVolta, 400);
  }

  function desligarBateVolta() {
    limparTrechosDoBateVolta();
    renumerarTrechos();
    percursoManual = false;
    mostrarErro("[data-bate-volta-erro]", "");
    mostrarErro("[data-rota-erro]", "");
    sincronizarTrechos();
  }

  // ------------------------------------------------------------------
  // Repetir um roteiro salvo
  // ------------------------------------------------------------------

  // Busca a sede e os destinos dele e refaz o percurso nesta tela. É cópia
  // — o roteiro novo não fica preso ao antigo.
  var seletorBase = editor.querySelector('select[name="roteiro_base"]');

  function aplicarRoteiroBase(dados) {
    aplicandoEstado = true;
    try {
      if (dados.sede) {
        var estadoSede = editor.querySelector('select[name="origem_estado"]');
        definirCampo(estadoSede, dados.sede.estado);
        definirCampo(sede, dados.sede.municipio);
      }
      // Zera os destinos atuais antes de repetir os do roteiro escolhido.
      destinosVisiveis().forEach(function (linha, indice) {
        if (indice > 0) removerLinhaDestino(linha);
      });
      var primeira = destinosVisiveis()[0];
      dados.destinos.forEach(function (destino, indice) {
        var linha = indice === 0 ? primeira : criarLinhaDestino(null);
        if (!linha) return;
        definirCampo(linha.querySelector('select[name$="-estado"]'), destino.estado);
        definirCampo(selectDaLinha(linha), destino.municipio);
      });
      if (!dados.destinos.length && primeira) {
        definirCampo(selectDaLinha(primeira), "");
      }
    } finally {
      aplicandoEstado = false;
    }
    renumerarDestinos();
    percursoManual = false;
    sincronizarTrechos();
  }

  if (seletorBase) {
    seletorBase.addEventListener("change", function () {
      var pk = seletorBase.value;
      if (!pk || !window.fetch) return;
      fetch("/viagens/roteiros/" + encodeURIComponent(pk) + "/dados/", {
        headers: { "X-Requested-With": "fetch" },
      })
        .then(function (resposta) { return resposta.ok ? resposta.json() : null; })
        .then(function (dados) { if (dados) aplicarRoteiroBase(dados); })
        .catch(function () { /* repetir é atalho: falha de rede não trava a tela */ });
    });
  }

  // ------------------------------------------------------------------
  // Prévia das diárias
  // ------------------------------------------------------------------

  var previaAgendada = null;
  var previaEmVoo = false;
  var previaRepetir = false;
  var tipoDestino = "";
  var temResultadoDiarias = false;

  var CHIPS_DIARIAS = {
    pendente: ["status-badge--rascunho", "Aguardando dados"],
    calculando: ["status-badge--em_andamento", "Calculando diárias…"],
    desatualizado: ["status-badge--pendente", "Cálculo desatualizado"],
    atualizado: ["status-badge--atendida", "Cálculo atualizado"],
    erro: ["status-badge--nao_atendida", "Falha no cálculo"],
  };

  function definirEstadoDiarias(estado, texto) {
    var chip = editor.querySelector("[data-diarias-chip]");
    var dados = CHIPS_DIARIAS[estado] || CHIPS_DIARIAS.pendente;
    if (chip) {
      chip.className = "status-badge section-card__acao " + dados[0];
      chip.textContent = texto || dados[1];
      chip.setAttribute("data-estado", estado);
    }
  }

  // Sem destino, saída e chegada em algum trecho não há o que calcular: os
  // valores voltam ao traço e o chip explica que está esperando dados.
  function dadosCompletosParaDiarias() {
    var ativos = trechosAtivos();
    return ativos.length > 0 && ativos.some(function (linha) {
      return valorDe(linha, "destino_municipio") && valorDe(linha, "saida_data") &&
        valorDe(linha, "saida_hora") && valorDe(linha, "chegada_data");
    });
  }

  function limparDiarias() {
    escreverTexto("[data-diarias-valor]", "—");
    escreverTexto("[data-diarias-extenso]", "—");
    escreverTexto("[data-diarias-tipo]", "—");
    escreverTexto("[data-diarias-composicao]", "—");
    tipoDestino = "";
    temResultadoDiarias = false;
    mostrarErro("[data-diarias-erro]", "");
    definirEstadoDiarias("pendente");
  }

  function aplicarPrevia(dados) {
    if (dados.ok) {
      escreverTexto("[data-diarias-valor]", "R$ " + dados.totais.total_valor);
      escreverTexto("[data-diarias-extenso]", dados.totais.valor_extenso || "—");
      escreverTexto("[data-diarias-tipo]", dados.totais.tipo_destino || "—");
      escreverTexto("[data-diarias-composicao]", dados.totais.resumo_diarias || "—");
      tipoDestino = dados.totais.tipo_destino || "";
      temResultadoDiarias = true;
      mostrarErro("[data-diarias-erro]", "");
      var servidores = dados.totais.quantidade_servidores;
      definirEstadoDiarias("atualizado", "Cálculo atualizado (" + servidores +
        (servidores === 1 ? " servidor)" : " servidores)"));
    } else {
      tipoDestino = "";
      temResultadoDiarias = false;
      mostrarErro("[data-diarias-erro]", dados.motivo || "Erro ao calcular as diárias.");
      definirEstadoDiarias("erro");
    }
    atualizarPainelLateral();
  }

  function pedirPrevia() {
    previaAgendada = null;
    if (!urlPrevia || !formulario) return;
    if (previaEmVoo) { previaRepetir = true; return; }
    previaEmVoo = true;
    definirEstadoDiarias("calculando");
    // A prévia só precisa dos trechos: a geometria da rota (centenas de KB)
    // fica de fora do envio.
    var dados = new FormData(formulario);
    dados.delete("rota_geojson");
    postar(urlPrevia, dados)
      .then(aplicarPrevia)
      .catch(function () {
        // Prévia é conveniência: falha de rede não interrompe a edição.
        definirEstadoDiarias("erro", "Sem resposta do servidor");
      })
      .then(function () {
        previaEmVoo = false;
        if (previaRepetir) { previaRepetir = false; agendarPrevia(); }
      });
  }

  function agendarPrevia() {
    if (!urlPrevia) return;
    if (previaAgendada) clearTimeout(previaAgendada);
    if (!dadosCompletosParaDiarias()) { limparDiarias(); atualizarPainelLateral(); return; }
    if (temResultadoDiarias) definirEstadoDiarias("desatualizado");
    previaAgendada = setTimeout(pedirPrevia, 700);
  }

  // ------------------------------------------------------------------
  // Gravação automática do rascunho
  // ------------------------------------------------------------------

  var autosaveAgendado = null;
  var autosaveEmVoo = null;   // a Promise da gravação em curso
  var autosaveRepetir = false;
  var autosaveSujo = false;

  function definirStatusAutosave(estado, texto) {
    var alvo = editor.querySelector("[data-autosave-status]");
    if (!alvo) return;
    alvo.textContent = texto;
    alvo.setAttribute("data-estado", estado);
  }

  // Só há o que gravar quando existe sede ou algum destino: um rascunho
  // vazio a cada visita à tela seria lixo no banco.
  function temConteudoParaGravar() {
    return Boolean((sede && sede.value) || paradas().length);
  }

  function agendarAutosave() {
    if (!autosaveLigado || !urlAutosave || aplicandoEstado) return;
    autosaveSujo = true;
    if (autosaveAgendado) clearTimeout(autosaveAgendado);
    autosaveAgendado = setTimeout(salvarAutomaticamente, 1000);
  }

  // Os ids que o servidor acabou de criar entram nos campos `id` das linhas:
  // a partir daí elas são editadas, não recriadas. INITIAL_FORMS acompanha —
  // é o que diz ao formset quais linhas já existem.
  function aprenderIds(ids, gravou) {
    ids = ids || {};
    gravou = gravou || {};
    var maiores = { destinos: -1, trechos: -1 };
    Object.keys(ids).forEach(function (nome) {
      var campo = formulario.querySelector('input[name="' + nome + '"]');
      if (campo) campo.value = String(ids[nome]);
    });
    slice(formulario.querySelectorAll('input[name$="-id"]')).forEach(function (campo) {
      var partes = campo.name.split("-");
      if (partes.length !== 3 || maiores[partes[0]] === undefined) return;
      // O que o servidor gravou e não devolveu foi apagado (linha marcada
      // para exclusão): o id antigo sai e a linha oculta volta a ser um slot
      // em branco — com os dados antigos ela seria gravada de novo, e com a
      // ordem repetida derrubaria o formset inteiro.
      if (campo.value && gravou[partes[0]] && !(campo.name in ids)) {
        campo.value = "";
        var linha = campo.closest("[data-trecho], [data-destino]");
        if (linha) esquecerLinha(linha);
      }
      // Linhas já gravadas antes também contam para a faixa inicial.
      if (campo.value) maiores[partes[0]] = Math.max(maiores[partes[0]], Number(partes[1]));
    });
    if (iniciaisDestinos) iniciaisDestinos.value = String(maiores.destinos + 1);
    if (iniciaisTrechos) iniciaisTrechos.value = String(maiores.trechos + 1);
  }

  function esquecerLinha(linha) {
    var caixa = caixaExclusao(linha);
    if (caixa) caixa.checked = false;
    if (!linha.hidden) return;   // visível é linha viva: será regravada
    var estava = aplicandoEstado;
    aplicandoEstado = true;
    try {
      if (linha.hasAttribute("data-trecho")) {
        limparTrecho(linha);
        atualizarLinha(linha);
      } else {
        var select = selectDaLinha(linha);
        if (select && select.value) definirCampo(select, "");
      }
    } finally {
      aplicandoEstado = estava;
    }
  }

  function dadosDoFormulario() {
    var dados = new FormData(formulario);
    dados.delete("acao");
    return dados;
  }

  function salvarAutomaticamente() {
    autosaveAgendado = null;
    if (!autosaveLigado || !urlAutosave || !formulario) return Promise.resolve();
    if (autosaveEmVoo) { autosaveRepetir = true; return autosaveEmVoo; }
    if (!autosaveSujo || !temConteudoParaGravar()) return Promise.resolve();
    autosaveSujo = false;
    definirStatusAutosave("salvando", "Salvando rascunho…");
    autosaveEmVoo = postar(urlAutosave, dadosDoFormulario())
      .then(function (dados) {
        if (!dados.ok) {
          definirStatusAutosave("erro", "Não foi possível salvar automaticamente: " + (dados.motivo || ""));
          return;
        }
        aprenderIds(dados.ids, dados.gravou);
        if (dados.criado) {
          // O roteiro passou a existir: a tela vira a edição dele, sem
          // recarregar — o próximo "Salvar" grava nele, não cria outro.
          urlAutosave = dados.url_autosave;
          formulario.setAttribute("action", dados.url_editar);
          if (window.history && window.history.replaceState) {
            window.history.replaceState({}, "", dados.url_editar);
          }
        }
        if (dados.motivo) {
          definirStatusAutosave("erro", "Rascunho salvo às " + dados.salvo_em + ", mas " + dados.motivo + ".");
        } else {
          definirStatusAutosave("salvo", "Rascunho salvo automaticamente às " + dados.salvo_em + ".");
        }
      })
      .catch(function () {
        definirStatusAutosave("erro", "Sem resposta do servidor: o rascunho não foi salvo automaticamente.");
      })
      .then(function () {
        autosaveEmVoo = null;
        if (autosaveRepetir) { autosaveRepetir = false; autosaveSujo = true; return salvarAutomaticamente(); }
        return undefined;
      });
    return autosaveEmVoo;
  }

  // "Salvar" com uma gravação automática em curso espera ela terminar: as
  // duas escrevendo o mesmo roteiro ao mesmo tempo criariam linhas em dobro.
  var submissaoLiberada = false;
  if (formulario) {
    formulario.addEventListener("submit", function (evento) {
      if (submissaoLiberada) { submissaoLiberada = false; return; }
      if (autosaveAgendado) { clearTimeout(autosaveAgendado); autosaveAgendado = null; autosaveSujo = false; }
      if (!autosaveEmVoo) return;
      evento.preventDefault();
      var botao = evento.submitter;
      var limite = new Promise(function (resolver) { setTimeout(resolver, 8000); });
      Promise.race([autosaveEmVoo, limite]).then(function () {
        submissaoLiberada = true;
        if (botao && formulario.requestSubmit) formulario.requestSubmit(botao);
        else formulario.submit();
      });
    });

    // Fechar a aba com mudança pendente: a última chance de gravar.
    window.addEventListener("beforeunload", function () {
      if (!autosaveLigado || !autosaveSujo || !temConteudoParaGravar()) return;
      if (!navigator.sendBeacon) return;
      try { navigator.sendBeacon(urlAutosave, dadosDoFormulario()); } catch (erro) { /* melhor esforço */ }
    });
  }

  // ------------------------------------------------------------------
  // Painel lateral: resumo e etapas
  // ------------------------------------------------------------------

  function definirEtapa(numero, estado, concluida) {
    var etapa = editor.querySelector('[data-etapa="' + numero + '"]');
    if (!etapa) return;
    etapa.classList.toggle("etapa-roteiro--concluida", Boolean(concluida));
    etapa.classList.toggle("etapa-roteiro--ativa", !concluida && estado === "Em preenchimento");
    var texto = etapa.querySelector("[data-etapa-estado]");
    if (texto) texto.textContent = concluida ? "Concluída" : estado;
  }

  function atualizarPainelLateral() {
    var pontos = paradas();
    var trechos = trechosAtivos();
    var temSede = Boolean(sede && sede.value);

    escreverTexto("[data-resumo-sede]", temSede ? rotulos[sede.value] : "—");
    escreverTexto("[data-resumo-destinos]", String(pontos.length));
    escreverTexto("[data-resumo-trechos]", String(trechos.length));
    escreverTexto("[data-resumo-distancia]",
      rotaCalculada ? km(rotaCalculada.distancia_total_km) : "—");
    escreverTexto("[data-resumo-tempo]",
      rotaCalculada ? humano(rotaCalculada.duracao_total_min) : "—");
    escreverTexto("[data-resumo-tipo]", tipoDestino || "—");
    escreverTexto("[data-resumo-servidores]",
      (servidoresInput && servidoresInput.value) || "1");

    var origemPronta = temSede && pontos.length > 0;
    var trechosComData = trechos.length > 0 && trechos.every(function (linha) {
      return valorDe(linha, "saida_data") && valorDe(linha, "saida_hora");
    });

    definirEtapa(1, "Em preenchimento", origemPronta);
    definirEtapa(2, origemPronta ? "Em preenchimento" : "Pendente", Boolean(rotaCalculada));
    definirEtapa(3, trechos.length ? "Em preenchimento" : "Pendente", trechosComData);
    definirEtapa(4, trechosComData ? "Em preenchimento" : "Pendente", temResultadoDiarias);
  }

  // ------------------------------------------------------------------
  // Ligações
  // ------------------------------------------------------------------

  editor.addEventListener("click", function (evento) {
    var novoDestino = evento.target.closest("[data-destino-adicionar]");
    if (novoDestino) { criarLinhaDestino(novoDestino.closest("[data-destino]")); return; }
    var removerDestino = evento.target.closest("[data-destino-remover]");
    if (removerDestino) { removerLinhaDestino(removerDestino.closest("[data-destino]")); return; }

    var menos = evento.target.closest("[data-tempo-menos]");
    if (menos) { ajustarAdicional(menos.closest("[data-trecho]"), -15); return; }
    var mais = evento.target.closest("[data-tempo-mais]");
    if (mais) { ajustarAdicional(mais.closest("[data-trecho]"), 15); return; }

    if (evento.target.closest("[data-rota-calcular]")) { calcularRota(); return; }
    if (evento.target.closest("[data-rota-enquadrar]")) { enquadrarRota(); return; }

    var toggleBv = evento.target.closest("[data-bate-volta-toggle]");
    if (toggleBv) {
      // O data-expande do app.js abre e fecha o painel; aqui o rótulo e o
      // efeito de desligar: fechado, os trechos gerados por ele saem.
      setTimeout(function () {
        var aberto = toggleBv.getAttribute("aria-expanded") === "true";
        toggleBv.classList.toggle("interruptor--ligado", aberto);
        var rotulo = toggleBv.querySelector(".interruptor__rotulo");
        if (rotulo) {
          rotulo.textContent = aberto ? "Com bate-volta diário" : "Sem bate-volta diário";
        }
        if (aberto) gerarBateVolta();
        else desligarBateVolta();
      }, 0);
    }
  });

  editor.addEventListener("change", function (evento) {
    if (aplicandoEstado) return;

    // Campos do bate-volta: geram os trechos assim que ficam completos.
    if (evento.target.closest("[data-bate-volta]")) {
      // O tempo da volta acompanha o da ida: é o mesmo percurso ao contrário.
      // Continua editável — mexer na ida apenas repõe o espelho.
      if (evento.target.name === "bv_ida_tempo") {
        definirCampo(editor.querySelector('[name="bv_volta_tempo"]'), evento.target.value);
      }
      agendarBateVolta();
      return;
    }

    if (evento.target === sede) {
      percursoManual = false;
      renumerarDestinos();
      sincronizarTrechos();
      agendarBateVolta();
      return;
    }
    var linhaDestino = evento.target.closest("[data-destino]");
    if (linhaDestino) {
      if (evento.target === selectDaLinha(linhaDestino)) {
        percursoManual = false;
        renumerarDestinos();
        sincronizarTrechos();
        agendarBateVolta();
      }
      return;
    }

    var linha = evento.target.closest("[data-trecho]");
    if (linha) {
      if (/saida_(data|hora)$/.test(evento.target.name || "")) atualizarTempos(linha);
      atualizarLinha(linha);
      atualizarPainelLateral();
      agendarPrevia();
      agendarAutosave();
      return;
    }
    // Qualquer outro campo do formulário (vínculo, etc.).
    if (formulario && formulario.contains(evento.target)) agendarAutosave();
  });

  // ------------------------------------------------------------------
  // Estado inicial
  // ------------------------------------------------------------------

  // Na edição, o estado do município já escolhido é derivado dele: sem isso
  // a cascata abriria com o filtro vazio e o campo pareceria em branco.
  function derivarEstado(selectMunicipio, selectEstado) {
    if (!selectMunicipio || !selectEstado || !selectMunicipio.value) return;
    var opcao = selectMunicipio.options[selectMunicipio.selectedIndex];
    var dono = opcao && opcao.getAttribute("data-parent-value");
    if (dono && selectEstado.value !== dono) {
      selectEstado.value = dono;
      selectEstado.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  aplicandoEstado = true;
  try {
    derivarEstado(sede, editor.querySelector('select[name="origem_estado"]'));
    linhasDestino().forEach(function (linha) {
      derivarEstado(selectDaLinha(linha), linha.querySelector('select[name$="-estado"]'));
    });

    trechosVisiveis().forEach(function (linha) {
      // Roteiro antigo, gravado só com o total: ele vira o tempo de viagem,
      // para a linha não reabrir sem tempo nenhum.
      var duracao = valorDe(linha, "duracao_min");
      if (viagemDe(linha) === null && duracao) {
        definirViagem(linha, Math.max(0, Number(duracao) - adicionalDe(linha)));
      }
      if (adicionalDe(linha)) linha.setAttribute("data-adicional-manual", "1");
      atualizarLinha(linha);
      atualizarTempos(linha);
    });
    if (trechosVisiveis().length) percursoManual = true;
    if (!destinosVisiveis().length) criarLinhaDestino();
    renumerarDestinos();
    renumerarTrechos();
    garantirMapa();
    carregarRotaInicial();
  } finally {
    aplicandoEstado = false;
  }
  verificarRotaDesatualizada();
  agendarEstimativas();
  agendarPrevia();
})();
