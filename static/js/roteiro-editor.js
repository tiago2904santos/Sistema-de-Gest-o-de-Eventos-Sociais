/*
 * Editor de roteiro (módulo Viagens).
 *
 * - a SEDE e os DESTINOS (linhas reordenáveis) definem o percurso;
 * - os TRECHOS são gerados a partir deles, um por linha da tabela: origem e
 *   destino em leitura, saída na própria linha e o resto em "Ver detalhes"
 *   (chegada, tempo adicional em passos de 15min, distância, remover);
 * - o RETORNO é o último deslocamento até a sede (sentido=RETORNO);
 * - "Calcular rota" pergunta ao servidor (OpenRouteService) e preenche as
 *   métricas, os tempos de viagem, as distâncias e o desenho no mapa;
 * - a PRÉVIA das diárias envia o formulário como está, sem gravar;
 * - o painel lateral (resumo e etapas) é derivado do estado da tela.
 *
 * Linhas nunca saem do DOM: remover esvazia e esconde (o servidor ignora
 * slots em branco) ou marca o DELETE do formset, com desfazer.
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
  var listaDestinos = editor.querySelector("[data-destinos]");
  var modeloDestino = editor.querySelector("[data-destino-modelo]");
  var totalDestinos = editor.querySelector('input[name="destinos-TOTAL_FORMS"]');
  var sede = editor.querySelector('select[name="origem_municipio"]');
  var servidoresInput = editor.querySelector('input[name="quantidade_servidores"]');

  // Rótulo de qualquer município pelo id — o select da sede lista todos.
  var rotulos = {};
  if (sede) {
    Array.prototype.forEach.call(sede.options, function (opcao) {
      if (opcao.value) rotulos[opcao.value] = opcao.text;
    });
  }

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
    var h = Math.floor(minutos / 60);
    var m = minutos % 60;
    if (h && m) return h + "h" + String(m).padStart(2, "0") + "min";
    if (h) return h + "h";
    return m + "min";
  }

  function km(valor) {
    return String(valor).replace(".", ",") + " km";
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

  function renumerarDestinos() {
    destinosVisiveis().forEach(function (linha, indice) {
      var ordem = linha.querySelector("[data-destino-ordem]");
      if (ordem) ordem.value = String(indice + 1);
    });
  }

  function criarLinhaDestino(depoisDe) {
    var slot = linhasDestino().find(function (linha) {
      return linha.hidden && !selectDaLinha(linha).value &&
        !linha.querySelector('input[name$="-DELETE"]');
    });
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
    var caixa = linha.querySelector('input[name$="-DELETE"]');
    var select = selectDaLinha(linha);
    if (caixa) caixa.checked = true;
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

  function linhaDeErros(linha) {
    var proxima = linha.nextElementSibling;
    return proxima && proxima.hasAttribute("data-trecho-erros") ? proxima : null;
  }

  function campoDe(linha, sufixo) {
    return linha.querySelector('[name$="-' + sufixo + '"]');
  }

  function caixaExclusao(linha) {
    return campoDe(linha, "DELETE");
  }

  function criarTrecho() {
    var slot = linhasTrecho().find(function (linha) {
      return linha.hidden && !caixaExclusao(linha) &&
        !campoDe(linha, "origem_municipio").value;
    });
    if (slot) {
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
      if (campo.value === "") return;
      campo.value = "";
      campo.dispatchEvent(new Event("change", { bubbles: true }));
    });
    linha.removeAttribute("data-viagem-min");
  }

  function esconderTrecho(linha) {
    // O percurso é derivado dos destinos: trecho que sai de cena é o que
    // perdeu o destino que o gerava. Já gravado, some pelo DELETE do
    // formset; novo, volta a ser um slot em branco.
    var caixa = caixaExclusao(linha);
    if (caixa) caixa.checked = true;
    else limparTrecho(linha);
    linha.hidden = true;
    var erros = linhaDeErros(linha);
    if (erros) erros.hidden = true;
  }

  function atualizarLinha(linha) {
    var origem = rotulos[campoDe(linha, "origem_municipio").value] || "";
    var destino = rotulos[campoDe(linha, "destino_municipio").value] || "";
    var rotuloOrigem = linha.querySelector("[data-trecho-origem-rotulo]");
    var rotuloDestino = linha.querySelector("[data-trecho-destino-rotulo]");
    if (rotuloOrigem) rotuloOrigem.textContent = origem || "—";
    if (rotuloDestino) rotuloDestino.textContent = destino || "—";

    var distancia = campoDe(linha, "distancia_km").value;
    var rotuloKm = linha.querySelector("[data-trecho-km-rotulo]");
    if (rotuloKm) rotuloKm.textContent = distancia ? km(distancia) : "—";
  }

  function adicionalDe(linha) {
    return Number(linha.getAttribute("data-adicional-min") || "") || 0;
  }

  function atualizarTempos(linha) {
    var viagem = Number(linha.getAttribute("data-viagem-min") || "") || null;
    var adicional = adicionalDe(linha);
    var viagemRotulo = linha.querySelector("[data-trecho-tempo-viagem]");
    var adicionalRotulo = linha.querySelector("[data-trecho-adicional-rotulo]");
    var totalRotulo = linha.querySelector("[data-trecho-tempo-total]");
    var duracaoMin = campoDe(linha, "duracao_min");

    // O tempo total é o da rota mais a espera informada à mão; é ele que
    // define a chegada e, por ela, a conta das diárias.
    var total = viagem === null ? (adicional || null) : viagem + adicional;

    if (viagemRotulo) viagemRotulo.textContent = viagem === null ? "—" : hhmmDe(viagem);
    if (adicionalRotulo) adicionalRotulo.textContent = hhmmDe(adicional);
    if (totalRotulo) totalRotulo.textContent = total === null ? "—" : hhmmDe(total);
    if (duracaoMin) duracaoMin.value = total === null ? "" : String(total);

    // A chegada não é digitada: é a saída mais o tempo total, gravada em
    // campos ocultos — é dela que o motor calcula as diárias — e mostrada na
    // última coluna, para quem monta o percurso ver onde o trecho termina.
    var dataSaida = campoDe(linha, "saida_data");
    var horaSaida = campoDe(linha, "saida_hora");
    var chegadaRotulo = linha.querySelector("[data-trecho-chegada-rotulo]");
    var textoChegada = "—";
    if (total !== null && dataSaida && dataSaida.value && horaSaida && horaSaida.value) {
      var saida = new Date(dataSaida.value + "T" + horaSaida.value);
      if (!Number.isNaN(saida.getTime())) {
        var chegada = new Date(saida.getTime() + total * 60000);
        var horaChegada = hhmmDe(chegada.getHours() * 60 + chegada.getMinutes());
        definirCampo(campoDe(linha, "chegada_data"), isoDe(chegada));
        definirCampo(campoDe(linha, "chegada_hora"), horaChegada);
        textoChegada = new Intl.DateTimeFormat("pt-BR").format(chegada) + " " + horaChegada;
      }
    }
    if (chegadaRotulo) chegadaRotulo.textContent = textoChegada;
  }

  function ajustarAdicional(linha, passo) {
    // Nunca negativo: descontar espera que não houve encurtaria a viagem.
    var novo = Math.max(0, adicionalDe(linha) + passo);
    linha.setAttribute("data-adicional-min", String(novo));
    atualizarTempos(linha);
    agendarPrevia();
  }

  function aplicarPerna(linha, origem, destino, sentido) {
    definirCampo(campoDe(linha, "origem_municipio"), origem);
    definirCampo(campoDe(linha, "destino_municipio"), destino);
    var campoSentido = campoDe(linha, "sentido");
    if (campoSentido) campoSentido.value = sentido;
    linha.setAttribute("data-sentido", sentido);
    linha.classList.toggle("trecho-linha--retorno", sentido === "RETORNO");
    atualizarLinha(linha);
  }

  function renumerarTrechos() {
    var ativos = trechosVisiveis();
    var numeroIda = 0;
    ativos.forEach(function (linha, indice) {
      var eRetorno = linha.getAttribute("data-sentido") === "RETORNO";
      var numero = linha.querySelector("[data-trecho-numero]");
      if (numero) {
        if (eRetorno) numero.textContent = "Retorno";
        else { numeroIda += 1; numero.textContent = "Trecho " + numeroIda; }
      }
      var ordem = linha.querySelector("[data-trecho-ordem]");
      var caixa = caixaExclusao(linha);
      if (ordem && !(caixa && caixa.checked)) ordem.value = String(indice + 1);
    });
    if (avisoVazio) avisoVazio.hidden = ativos.length > 0;
    if (tabelaTrechos) tabelaTrechos.hidden = ativos.length === 0;
    sincronizarCalendarioDeDatas();
    atualizarPainelLateral();
  }

  var percursoManual = false;

  function sincronizarTrechos() {
    if (percursoManual) { atualizarPainelLateral(); return; }
    var origemSede = sede ? sede.value : "";
    var paradas = destinosVisiveis()
      .map(function (linha) { return selectDaLinha(linha).value; })
      .filter(Boolean);

    var pernas = [];
    var anterior = origemSede;
    paradas.forEach(function (parada) {
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
    if (paradas.length && origemSede) {
      if (!retorno) retorno = criarTrecho();
      if (retorno) {
        aplicarPerna(retorno, paradas[paradas.length - 1], origemSede, "RETORNO");
        var erros = linhaDeErros(retorno);
        corpoTrechos.appendChild(retorno);
        if (erros) corpoTrechos.appendChild(erros);
      }
    } else if (retorno) {
      esconderTrecho(retorno);
    }
    renumerarTrechos();
    agendarPrevia();
  }

  // O calendário do cabeçalho pede uma data por trecho: dois destinos são
  // três trechos (sede→1, 1→2, 2→sede), logo três datas. O máximo acompanha
  // o percurso, e as datas entram na ordem em que foram escolhidas.
  // A página tem dois calendários múltiplos (datas de saída e bate-volta):
  // este é o do cabeçalho dos Trechos, pelo id do componente.
  var calendarioDatas = editor.querySelector("#datas-trechos[data-custom-date-multi]");

  function sincronizarCalendarioDeDatas() {
    if (!calendarioDatas) return;
    var total = trechosVisiveis().filter(function (linha) {
      var caixa = caixaExclusao(linha);
      return !(caixa && caixa.checked);
    }).length;
    calendarioDatas.setAttribute("data-max", String(Math.max(1, total)));
    calendarioDatas.setAttribute(
      "data-dica",
      total
        ? "Escolha " + total + (total === 1 ? " data" : " datas") +
          " — uma por trecho, na ordem do percurso."
        : "Defina a sede e os destinos para gerar os trechos."
    );
    var gatilho = calendarioDatas.querySelector("[data-custom-date-multi-trigger]");
    if (gatilho) gatilho.disabled = total === 0;
  }

  function aplicarDatasDeSaida(datas) {
    var ativos = trechosVisiveis().filter(function (linha) {
      var caixa = caixaExclusao(linha);
      return !(caixa && caixa.checked);
    });
    datas.forEach(function (iso, indice) {
      var linha = ativos[indice];
      if (!linha) return;
      definirCampo(campoDe(linha, "saida_data"), iso);
      atualizarTempos(linha);
    });
    atualizarPainelLateral();
    agendarPrevia();
  }

  if (calendarioDatas) {
    calendarioDatas.addEventListener("ds:datas-multi", function (evento) {
      aplicarDatasDeSaida(evento.detail.datas);
    });
  }

  // ------------------------------------------------------------------
  // Rota e mapa
  // ------------------------------------------------------------------

  var urlRota = editor.getAttribute("data-url-rota");
  var mapaElemento = editor.querySelector("[data-mapa]");
  var mapa = null;
  var camadaRota = null;

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
    return mapa;
  }

  function pontosDoPercurso() {
    var ids = [];
    trechosVisiveis().forEach(function (linha) {
      var caixa = caixaExclusao(linha);
      if (caixa && caixa.checked) return;
      var origem = campoDe(linha, "origem_municipio").value;
      var destino = campoDe(linha, "destino_municipio").value;
      if (origem && (!ids.length || ids[ids.length - 1] !== origem)) ids.push(origem);
      if (destino) ids.push(destino);
    });
    return ids;
  }

  function escreverTexto(seletor, texto) {
    var alvo = editor.querySelector(seletor);
    if (alvo) alvo.textContent = texto;
  }

  var rotaCalculada = null;

  function aplicarRota(dados) {
    var erro = editor.querySelector("[data-rota-erro]");
    if (!dados.ok) {
      if (erro) { erro.textContent = dados.motivo; erro.hidden = false; }
      return;
    }
    if (erro) erro.hidden = true;
    rotaCalculada = dados;

    var segmentos = dados.segmentos || [];
    var idaKm = 0;
    var idaMin = 0;
    segmentos.forEach(function (segmento, indice) {
      if (indice < segmentos.length - 1) {
        idaKm += segmento.distancia_km;
        idaMin += segmento.duracao_min;
      }
    });
    escreverTexto("[data-rota-distancia-total]", km(dados.distancia_total_km));
    escreverTexto("[data-rota-tempo-total]", humano(dados.duracao_total_min));
    escreverTexto("[data-rota-distancia-ida]", km(Math.round(idaKm * 100) / 100));
    escreverTexto("[data-rota-tempo-ida]", humano(idaMin));

    var ativos = trechosVisiveis().filter(function (linha) {
      var caixa = caixaExclusao(linha);
      return !(caixa && caixa.checked);
    });
    segmentos.forEach(function (segmento, indice) {
      var linha = ativos[indice];
      if (!linha) return;
      definirCampo(campoDe(linha, "distancia_km"), String(segmento.distancia_km));
      linha.setAttribute("data-viagem-min", String(segmento.duracao_min));
      atualizarLinha(linha);
      atualizarTempos(linha);
    });

    var leaflet = garantirMapa();
    if (leaflet) {
      if (camadaRota) camadaRota.remove();
      camadaRota = window.L.layerGroup().addTo(leaflet);
      (dados.pontos || []).forEach(function (ponto) {
        window.L.marker([ponto.lat, ponto.lng])
          .addTo(camadaRota)
          .bindTooltip(ponto.nome.toUpperCase() + "/" + ponto.uf,
                       { permanent: true, direction: "top" });
      });
      if (dados.geometria && dados.geometria.coordinates) {
        var linha = dados.geometria.coordinates.map(function (par) { return [par[1], par[0]]; });
        window.L.polyline(linha, { weight: 4 }).addTo(camadaRota);
        leaflet.fitBounds(window.L.polyline(linha).getBounds(), { padding: [24, 24] });
      }
      var enquadrar = editor.querySelector("[data-rota-enquadrar]");
      if (enquadrar) enquadrar.disabled = false;
    }
    var rotuloBotao = editor.querySelector("[data-rota-calcular-rotulo]");
    if (rotuloBotao) rotuloBotao.textContent = "Recalcular rota";
    atualizarPainelLateral();
  }

  function calcularRota() {
    if (!urlRota || !window.fetch) return;
    var erro = editor.querySelector("[data-rota-erro]");
    var ids = pontosDoPercurso();
    if (ids.length < 2) {
      if (erro) {
        erro.textContent = "Defina a sede e ao menos um destino para calcular a rota.";
        erro.hidden = false;
      }
      return;
    }
    var corpo = new FormData();
    var csrf = editor.querySelector('input[name="csrfmiddlewaretoken"]');
    if (csrf) corpo.append("csrfmiddlewaretoken", csrf.value);
    ids.forEach(function (id) { corpo.append("municipios", id); });
    fetch(urlRota, { method: "POST", body: corpo, headers: { "X-Requested-With": "fetch" } })
      .then(function (resposta) { return resposta.ok ? resposta.json() : null; })
      .then(function (dados) { if (dados) aplicarRota(dados); })
      .catch(function () {
        if (erro) {
          erro.textContent = "Não foi possível falar com o servidor de rotas.";
          erro.hidden = false;
        }
      });
  }

  // ------------------------------------------------------------------
  // Bate-volta diário
  // ------------------------------------------------------------------

  function valorBv(nome) {
    var campo = editor.querySelector('[name="bv_' + nome + '"]');
    return campo ? campo.value : "";
  }

  // Os campos de data da ida e da volta são gatilhos do mesmo calendário: as
  // duas datas escolhidas nele entram na ordem — a primeira na ida, a segunda
  // na volta. Uma data só serve para ida e volta no mesmo dia.
  var painelDatasBv = editor.querySelector(".bate-volta__sentidos[data-custom-date-multi]");

  function rotuloDataBr(iso) {
    var partes = String(iso || "").split("-");
    return partes.length === 3 ? partes[2] + "/" + partes[1] + "/" + partes[0] : "dd/mm/aaaa";
  }

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

  function gerarBateVolta() {
    var erro = editor.querySelector("[data-bate-volta-erro]");
    var painel = editor.querySelector("[data-bate-volta]");
    if (!painel || painel.hidden) return;

    function falhar(mensagem) {
      erro.textContent = mensagem;
      erro.hidden = false;
    }
    function aguardar() {
      // Preenchimento em curso não é erro: a tela só espera em silêncio.
      erro.hidden = true;
      limparTrechosDoBateVolta();
      renumerarTrechos();
    }
    erro.hidden = true;

    var destino = (destinosVisiveis()
      .map(function (linha) { return selectDaLinha(linha).value; })
      .filter(Boolean))[0];
    var idaData = valorBv("ida_data");
    var voltaData = valorBv("volta_data");
    var idaSaida = minutosDe(valorBv("ida_saida"));
    var idaTempo = minutosDe(valorBv("ida_tempo"));
    var voltaSaida = minutosDe(valorBv("volta_saida"));
    var voltaTempo = minutosDe(valorBv("volta_tempo"));

    var incompleto = !sede || !sede.value || !destino || !idaData || !voltaData ||
      [idaSaida, idaTempo, voltaSaida, voltaTempo].some(function (v) { return v === null; });
    if (incompleto) return aguardar();

    var dataIda = new Date(idaData + "T00:00");
    var dataVolta = new Date(voltaData + "T00:00");
    if (Number.isNaN(dataIda.getTime()) || Number.isNaN(dataVolta.getTime())) return aguardar();
    if (dataVolta < dataIda) {
      limparTrechosDoBateVolta();
      renumerarTrechos();
      return falhar("A data da volta não pode ser anterior à da ida.");
    }

    limparTrechosDoBateVolta();
    limparTrechosDerivados();
    percursoManual = true;

    var ida = criarTrecho();
    if (ida) {
      ida.setAttribute("data-bv", "");
      aplicarPerna(ida, sede.value, destino, "IDA");
      definirCampo(campoDe(ida, "saida_data"), idaData);
      definirCampo(campoDe(ida, "saida_hora"), hhmmDe(idaSaida));
      definirCampo(campoDe(ida, "chegada_data"), idaData);
      definirCampo(campoDe(ida, "chegada_hora"), hhmmDe(idaSaida + idaTempo));
      ida.setAttribute("data-viagem-min", String(idaTempo));
      atualizarTempos(ida);
    }
    var volta = criarTrecho();
    if (volta) {
      volta.setAttribute("data-bv", "");
      aplicarPerna(volta, destino, sede.value, "RETORNO");
      definirCampo(campoDe(volta, "saida_data"), voltaData);
      definirCampo(campoDe(volta, "saida_hora"), hhmmDe(voltaSaida));
      definirCampo(campoDe(volta, "chegada_data"), voltaData);
      definirCampo(campoDe(volta, "chegada_hora"), hhmmDe(voltaSaida + voltaTempo));
      volta.setAttribute("data-viagem-min", String(voltaTempo));
      atualizarTempos(volta);
    }
    renumerarTrechos();
    agendarPrevia();
  }

  var bateVoltaAgendado = null;

  function agendarBateVolta() {
    if (bateVoltaAgendado) clearTimeout(bateVoltaAgendado);
    bateVoltaAgendado = setTimeout(gerarBateVolta, 400);
  }

  // ------------------------------------------------------------------
  // Prévia das diárias
  // ------------------------------------------------------------------

  // Repetir um roteiro salvo: busca a sede e os destinos dele e refaz o
  // percurso nesta tela. É cópia — o roteiro novo não fica preso ao antigo.
  var seletorBase = editor.querySelector('select[name="roteiro_base"]');

  function aplicarRoteiroBase(dados) {
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
    percursoManual = false;
    sincronizarTrechos();
    agendarPrevia();
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

  var urlPrevia = editor.getAttribute("data-url-previa");
  var previaAgendada = null;
  var tipoDestino = "";

  function aplicarPrevia(dados) {
    var chip = editor.querySelector("[data-diarias-chip]");
    if (dados.ok) {
      escreverTexto("[data-diarias-valor]", "R$ " + dados.totais.total_valor);
      escreverTexto("[data-diarias-extenso]", dados.totais.valor_extenso || "—");
      escreverTexto("[data-diarias-tipo]", dados.totais.tipo_destino || "—");
      escreverTexto("[data-diarias-composicao]", dados.totais.resumo_diarias || "—");
      tipoDestino = dados.totais.tipo_destino || "";
      if (chip) {
        var servidores = dados.totais.quantidade_servidores;
        chip.textContent = "Cálculo atualizado (" + servidores +
          (servidores === 1 ? " servidor)" : " servidores)");
        chip.hidden = false;
      }
    } else {
      tipoDestino = "";
      if (chip) chip.hidden = true;
    }
    atualizarPainelLateral();
  }

  function pedirPrevia() {
    if (!urlPrevia || !window.fetch || !formulario) return;
    fetch(urlPrevia, {
      method: "POST",
      body: new FormData(formulario),
      headers: { "X-Requested-With": "fetch" },
    })
      .then(function (resposta) { return resposta.ok ? resposta.json() : null; })
      .then(function (dados) { if (dados) aplicarPrevia(dados); })
      .catch(function () { /* prévia é conveniência: falha de rede não interrompe a edição */ });
  }

  function agendarPrevia() {
    if (!urlPrevia) return;
    if (previaAgendada) clearTimeout(previaAgendada);
    previaAgendada = setTimeout(pedirPrevia, 700);
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
    var paradas = destinosVisiveis()
      .map(function (linha) { return selectDaLinha(linha).value; })
      .filter(Boolean);
    var trechos = trechosVisiveis().filter(function (linha) {
      var caixa = caixaExclusao(linha);
      return !(caixa && caixa.checked);
    });
    var temSede = Boolean(sede && sede.value);

    escreverTexto("[data-resumo-sede]", temSede ? rotulos[sede.value] : "—");
    escreverTexto("[data-resumo-destinos]", String(paradas.length));
    escreverTexto("[data-resumo-trechos]", String(trechos.length));
    escreverTexto("[data-resumo-distancia]",
      rotaCalculada ? km(rotaCalculada.distancia_total_km) : "—");
    escreverTexto("[data-resumo-tempo]",
      rotaCalculada ? humano(rotaCalculada.duracao_total_min) : "—");
    escreverTexto("[data-resumo-tipo]", tipoDestino || "—");
    escreverTexto("[data-resumo-servidores]",
      (servidoresInput && servidoresInput.value) || "1");

    var origemPronta = temSede && paradas.length > 0;
    var trechosComData = trechos.length > 0 && trechos.every(function (linha) {
      var data = campoDe(linha, "saida_data");
      var hora = campoDe(linha, "saida_hora");
      return data && data.value && hora && hora.value;
    });
    var valor = editor.querySelector("[data-diarias-valor]");
    var temDiarias = Boolean(valor && valor.textContent.trim() !== "—");

    definirEtapa(1, "Em preenchimento", origemPronta);
    definirEtapa(2, origemPronta ? "Em preenchimento" : "Pendente", Boolean(rotaCalculada));
    definirEtapa(3, trechos.length ? "Em preenchimento" : "Pendente", trechosComData);
    definirEtapa(4, trechosComData ? "Em preenchimento" : "Pendente", temDiarias);
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
    var enquadrar = evento.target.closest("[data-rota-enquadrar]");
    if (enquadrar && mapa && camadaRota) {
      var limites = window.L.featureGroup(camadaRota.getLayers()).getBounds();
      if (limites.isValid()) mapa.fitBounds(limites, { padding: [24, 24] });
      return;
    }
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
        if (aberto) {
          gerarBateVolta();
        } else {
          limparTrechosDoBateVolta();
          renumerarTrechos();
          percursoManual = false;
          sincronizarTrechos();
        }
      }, 0);
    }
  });

  editor.addEventListener("change", function (evento) {
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
      sincronizarTrechos();
      agendarBateVolta();
      return;
    }
    var linhaDestino = evento.target.closest("[data-destino]");
    if (linhaDestino) {
      percursoManual = false;
      sincronizarTrechos();
      agendarBateVolta();
      return;
    }

    var linha = evento.target.closest("[data-trecho]");
    if (linha) {
      if (/saida_(data|hora)$/.test(evento.target.name || "")) atualizarTempos(linha);
      atualizarLinha(linha);
    }
    atualizarPainelLateral();
    agendarPrevia();
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

  derivarEstado(sede, editor.querySelector('select[name="origem_estado"]'));
  linhasDestino().forEach(function (linha) {
    derivarEstado(selectDaLinha(linha), linha.querySelector('select[name$="-estado"]'));
  });

  trechosVisiveis().forEach(function (linha) {
    var duracao = campoDe(linha, "duracao_min");
    if (duracao && duracao.value) linha.setAttribute("data-viagem-min", duracao.value);
    var sentido = campoDe(linha, "sentido");
    linha.classList.toggle("trecho-linha--retorno",
      Boolean(sentido && sentido.value === "RETORNO"));
    atualizarLinha(linha);
    if (duracao && duracao.value) {
      var totalRotulo = linha.querySelector("[data-trecho-tempo-total]");
      if (totalRotulo) totalRotulo.textContent = hhmmDe(Number(duracao.value));
    }
  });
  if (trechosVisiveis().length) percursoManual = true;
  if (!destinosVisiveis().length) criarLinhaDestino();
  renumerarDestinos();
  renumerarTrechos();
  garantirMapa();
  agendarPrevia();
})();
