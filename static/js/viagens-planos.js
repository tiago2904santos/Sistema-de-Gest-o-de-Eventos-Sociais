/**
 * Página do plano de trabalho — os comportamentos do wizard do Gerenciador de
 * Viagens, sem autosave: "Outro programa" revela o campo, os coordenadores
 * trocam entre servidor e nome manual, os três textos padrão se reescrevem
 * enquanto estão no automático, as linhas de efetivo (+/−), o cálculo ao
 * vivo das diárias, o filtro/preset/limpar das atividades com a prévia de
 * metas e recursos, os destinos do termo e a prévia do documento.
 */
(function () {
  "use strict";

  var raiz = document.querySelector("[data-pt-form]");
  var form = document.getElementById("form-plano");
  if (!raiz || !form) return;

  function lerJson(id, padrao) {
    var el = document.getElementById(id);
    if (!el) return padrao;
    try { return JSON.parse(el.textContent || ""); } catch (e) { return padrao; }
  }

  function disparar(el, nome) {
    if (el) el.dispatchEvent(new Event(nome, { bubbles: true }));
  }

  // Muda o valor de um select aprimorado: o app.js ouve o "change" do nativo.
  function definirSelect(select, valor) {
    if (!select) return;
    var texto = String(valor || "");
    if (texto && !Array.prototype.some.call(select.options, function (o) { return o.value === texto; })) {
      var opcao = document.createElement("option");
      opcao.value = texto;
      opcao.textContent = texto;
      select.appendChild(opcao);
    }
    if (select.value === texto) return;
    select.value = texto;
    disparar(select, "change");
  }

  /* ── Programa: "Outro" revela o campo ───────────────────────────── */

  var programa = form.querySelector('select[name="programa"]');
  var outros = form.querySelector("[data-pt-programa-outros]");
  var outroValor = raiz.getAttribute("data-programa-outro") || "__outro__";
  function aplicarPrograma() {
    if (!programa || !outros) return;
    var eOutro = programa.value === outroValor;
    outros.hidden = !eOutro;
    var entrada = outros.querySelector('input[name="programa_outros"]');
    if (entrada && !eOutro) entrada.value = "";
  }
  if (programa) programa.addEventListener("change", aplicarPrograma);
  aplicarPrograma();

  /* ── Textos padrão ao vivo ──────────────────────────────────────── */

  var MENORES = { de: 1, da: 1, do: 1, das: 1, dos: 1, e: 1, a: 1, o: 1, no: 1, na: 1, em: 1, "à": 1 };

  function titulo(valor) {
    return String(valor || "").toLowerCase().split(/\s+/).map(function (palavra, i) {
      if (!palavra) return palavra;
      if (i > 0 && MENORES[palavra]) return palavra;
      return palavra.charAt(0).toUpperCase() + palavra.slice(1);
    }).join(" ");
  }

  function municipioAtual() {
    var rotulos = [];
    form.querySelectorAll("[data-destino-linha]").forEach(function (linha) {
      var estado = linha.querySelector(".destino-row__estado select");
      var cidade = linha.querySelector(".destino-row__campo select");
      if (!cidade || !cidade.value) return;
      var nome = cidade.options[cidade.selectedIndex] ? cidade.options[cidade.selectedIndex].text.trim() : "";
      if (!nome) return;
      var uf = "";
      if (estado && estado.options[estado.selectedIndex]) uf = (estado.options[estado.selectedIndex].text.split("—")[0] || "").trim().toUpperCase();
      var rotulo = titulo(nome) + (uf ? "/" + uf : "");
      if (rotulos.indexOf(rotulo) < 0) rotulos.push(rotulo);
    });
    return rotulos.length ? rotulos.join(", ") : "________";
  }

  function programaAtual() {
    if (!programa) return "________";
    if (programa.value === outroValor) {
      var entrada = form.querySelector('input[name="programa_outros"]');
      var cru = entrada ? entrada.value.trim() : "";
      return cru ? titulo(cru) : "________";
    }
    if (!programa.value) return "________";
    var opcao = programa.options[programa.selectedIndex];
    return opcao ? titulo(opcao.text.trim()) : "________";
  }

  function termosGenero(genero) {
    var f = genero === "FEMININO";
    return {
      designado: f ? "designada" : "designado",
      artigo: f ? "a" : "o",
      coordenador_administrativo: f ? "Coordenadora Administrativa" : "Coordenador Administrativo",
      coordenador_operacional: f ? "Coordenadora Operacional do Evento" : "Coordenador Operacional do Evento"
    };
  }

  function dadosCoordenador(papel) {
    var painel = form.querySelector('[data-pt-coordenador="' + papel + '"]');
    if (!painel) return { nome: "", cargo: "", genero: "MASCULINO" };
    var manual = painel.querySelector('input[name="coordenador_' + papel + '_modo"]:checked');
    var genero = painel.querySelector('select[name="coordenador_' + papel + '_genero"]');
    var cargo = painel.querySelector('select[name="coordenador_' + papel + '_cargo_manual"]');
    var dados = { nome: "", cargo: (cargo && cargo.value) || "", genero: (genero && genero.value) || "MASCULINO" };
    if (manual && manual.value === "MANUAL") {
      var entrada = painel.querySelector('input[name="coordenador_' + papel + '_nome_manual"]');
      dados.nome = entrada ? entrada.value.trim() : "";
      return dados;
    }
    var escolha = painel.querySelector('select[name="coordenador_' + papel + '"]');
    var opcao = escolha && escolha.value ? escolha.selectedOptions[0] : null;
    if (opcao) {
      dados.nome = opcao.textContent.trim();
      dados.cargo = opcao.getAttribute("data-cargo") || dados.cargo;
    }
    return dados;
  }

  function textoCoordenador(modelo, dados, papel) {
    var termos = termosGenero(dados.genero);
    var chave = papel === "adm" ? "coordenador_administrativo" : "coordenador_operacional";
    return String(modelo || "")
      .replace(/\{cargo_nome\}/g, [titulo(dados.cargo), titulo(dados.nome)].filter(Boolean).join(" "))
      .replace(/\{designado\}/g, termos.designado)
      .replace(/\{artigo\}/g, termos.artigo)
      .replace(/\{coordenador_administrativo\}/g, termos.coordenador_administrativo)
      .replace(/\{coordenador_operacional\}/g, termos[chave]);
  }

  var modelos = lerJson("pt-textos-padrao", {});
  var programatico = false;
  var textos = [
    { nome: "contextualizacao", flag: "contextualizacao" },
    { nome: "coordenacao", flag: "coordenacao" },
    { nome: "consideracao_final", flag: "consideracao_final" }
  ];
  // Os três textos são gerados e têm comprimento variável: em quatro linhas
  // fixas a contextualização fica com o fim escondido e a linha de baixo
  // cortada ao meio. A caixa passa a acompanhar o conteúdo, até um teto para
  // um texto longo colado à mão não empurrar o resto da página para fora.
  var ALTURA_MAXIMA_TEXTO = 520;

  function ajustarAltura(area) {
    if (!area) return;
    area.style.height = "auto";
    var necessaria = Math.min(area.scrollHeight, ALTURA_MAXIMA_TEXTO);
    area.style.height = necessaria + "px";
    area.style.overflowY = area.scrollHeight > ALTURA_MAXIMA_TEXTO ? "auto" : "hidden";
  }

  textos.forEach(function (t) {
    t.area = form.querySelector('textarea[name="' + t.nome + '"]');
    t.sinal = form.querySelector('[data-pt-texto-auto="' + t.flag + '"]');
    if (t.area) {
      t.area.addEventListener("input", function () {
        // Editar à mão desliga o automático daquele texto.
        if (!programatico && t.sinal) t.sinal.value = "0";
        ajustarAltura(t.area);
      });
      ajustarAltura(t.area);
    }
  });

  function coordenacaoAtual() {
    var paragrafos = [];
    var adm = dadosCoordenador("adm");
    if (adm.nome) paragrafos.push(textoCoordenador(modelos.coordenacao_adm, adm, "adm"));
    var op = dadosCoordenador("op");
    if (op.nome) paragrafos.push(textoCoordenador(modelos.coordenacao_op, op, "op"));
    return paragrafos.join("\n\n");
  }

  function regenerarTextos() {
    var municipio = municipioAtual();
    var prog = programaAtual();
    textos.forEach(function (t) {
      if (!t.area || !t.sinal || t.sinal.value !== "1") return;
      var valor;
      if (t.nome === "coordenacao") valor = coordenacaoAtual();
      else {
        var modelo = modelos[t.nome] || "";
        if (!modelo) return;
        valor = modelo.replace(/\{municipio\}/g, municipio).replace(/\{programa\}/g, prog);
      }
      programatico = true;
      t.area.value = valor;
      programatico = false;
      ajustarAltura(t.area);
    });
  }

  form.addEventListener("change", function (evento) {
    var alvo = evento.target;
    if (!alvo || !alvo.name) return;
    if (alvo.name === "programa" || alvo.name === "programa_outros" || /^(destino|extra)_/.test(alvo.name) || /^coordenador_(adm|op)/.test(alvo.name)) regenerarTextos();
  });
  form.addEventListener("input", function (evento) {
    var alvo = evento.target;
    if (alvo && (alvo.name === "programa_outros" || /^coordenador_(adm|op)_nome_manual$/.test(alvo.name))) regenerarTextos();
  });

  /* ── Coordenadores: servidor ↔ manual, cargo preenchido pelo servidor ── */

  form.querySelectorAll("[data-pt-coordenador]").forEach(function (painel) {
    var papel = painel.getAttribute("data-pt-coordenador");
    var blocoServidor = painel.querySelector("[data-pt-coordenador-servidor]");
    var blocoManual = painel.querySelector("[data-pt-coordenador-manual]");
    var cargo = painel.querySelector('select[name="coordenador_' + papel + '_cargo_manual"]');

    function aplicarModo() {
      var manual = painel.querySelector('input[name="coordenador_' + papel + '_modo"]:checked');
      var eManual = Boolean(manual && manual.value === "MANUAL");
      if (blocoServidor) blocoServidor.hidden = eManual;
      if (blocoManual) blocoManual.hidden = !eManual;
      if (eManual) {
        // Em manual o servidor sai da escolha, senão continuaria indo no POST.
        definirSelect(painel.querySelector('select[name="coordenador_' + papel + '"]'), "");
        var entrada = blocoManual && blocoManual.querySelector("input");
        if (entrada) entrada.focus();
      }
    }
    painel.addEventListener("change", function (evento) {
      var alvo = evento.target;
      if (alvo.name === "coordenador_" + papel + "_modo") { aplicarModo(); return; }
      // Escolher um servidor traz o cargo dele; desfazer a escolha limpa o cargo.
      if (alvo.name === "coordenador_" + papel) {
        var opcao = alvo.value ? alvo.selectedOptions[0] : null;
        definirSelect(cargo, (opcao && opcao.getAttribute("data-cargo")) || "");
      }
    });
    aplicarModo();
  });

  /* ── Destinos (o mecanismo do termo) ────────────────────────────── */

  (function () {
    var lista = form.querySelector("[data-destinos]");
    var modelo = form.querySelector("[data-destino-modelo]");
    var quantidade = form.querySelector('input[name="quantidade_destinos"]');
    if (!lista || !modelo || !quantidade) return;
    var proximo = Number(quantidade.value);
    if (!(proximo >= 0)) proximo = 0;

    function linhas() { return Array.prototype.slice.call(lista.querySelectorAll("[data-destino-linha]")); }
    function selectsDe(linha) {
      return { estado: linha.querySelector(".destino-row__estado select"), cidade: linha.querySelector(".destino-row__campo select") };
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
      if (campo) campo.focus();
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
      if (linhas().length <= 1) { limpar(linha); return; }
      linha.remove();
      atualizarEstado();
      regenerarTextos();
    });
    if (window.DS && window.DS.arrastarDestinos) window.DS.arrastarDestinos(lista, regenerarTextos);
    // A nomeação final sai no envio: a primeira linha é o destino do plano, as outras `extra_*_i`.
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

  /* ── Efetivo: linhas + cálculo ao vivo das diárias ─────────────── */

  var secaoDiarias = form.querySelector("[data-pt-efetivo-diarias]");
  var temporizador = null;

  function linhasEfetivo() {
    return Array.prototype.slice.call(form.querySelectorAll("[data-pt-efetivo-linha]")).filter(function (linha) {
      var apagar = linha.querySelector("[data-pt-efetivo-apagar]");
      return !linha.hidden && !(apagar && apagar.checked);
    });
  }

  function totalEfetivo() {
    var total = 0;
    linhasEfetivo().forEach(function (linha) {
      var cargo = linha.querySelector('select[name$="-cargo"]');
      var qtd = linha.querySelector('input[name$="-quantidade"]');
      if (!cargo || !cargo.value) return;
      var n = parseInt((qtd && qtd.value) || "0", 10);
      if (!isNaN(n) && n > 0) total += n;
    });
    return total;
  }

  function atualizarLinhasEfetivo() {
    var visiveis = linhasEfetivo();
    visiveis.forEach(function (linha, i) {
      linha.classList.toggle("pt-efetivo-linha--sem-rotulos", i > 0);
      linha.querySelectorAll(".form-label").forEach(function (rotulo) { rotulo.classList.toggle("sr-only", i > 0); });
      linha.classList.toggle("pt-efetivo-linha--unica", visiveis.length <= 1);
    });
  }

  (function () {
    var lista = form.querySelector("[data-pt-efetivo-linhas]");
    var modelo = form.querySelector("[data-pt-efetivo-modelo]");
    var total = form.querySelector('input[name="efetivo-TOTAL_FORMS"]');
    if (!lista || !modelo || !total) return;

    function adicionar(depoisDe) {
      var indice = parseInt(total.value || "0", 10);
      var apoio = document.createElement("div");
      apoio.innerHTML = modelo.innerHTML.replace(/__prefix__/g, String(indice)).trim();
      var linha = apoio.firstElementChild;
      if (!linha) return;
      if (depoisDe) lista.insertBefore(linha, depoisDe.nextSibling);
      else lista.appendChild(linha);
      total.value = String(indice + 1);
      if (window.DS && window.DS.aprimorar) window.DS.aprimorar(linha);
      atualizarLinhasEfetivo();
      agendarCalculo();
      var campo = linha.querySelector("[data-custom-select-trigger]");
      if (campo) campo.focus();
    }

    lista.addEventListener("click", function (evento) {
      var mais = evento.target.closest("[data-pt-efetivo-adicionar]");
      if (mais) { adicionar(mais.closest("[data-pt-efetivo-linha]")); return; }
      var menos = evento.target.closest("[data-pt-efetivo-remover]");
      if (!menos) return;
      var linha = menos.closest("[data-pt-efetivo-linha]");
      if (linhasEfetivo().length <= 1) return;
      // Marca DELETE e esconde: arrancar do DOM deixaria TOTAL_FORMS maior que os prefixos enviados.
      var apagar = linha.querySelector("[data-pt-efetivo-apagar]");
      if (apagar) { apagar.checked = true; linha.hidden = true; } else linha.remove();
      atualizarLinhasEfetivo();
      agendarCalculo();
    });
    lista.addEventListener("change", agendarCalculo);
    lista.addEventListener("input", function (evento) {
      if (evento.target && /-quantidade$/.test(evento.target.name || "")) agendarCalculo();
    });
    atualizarLinhasEfetivo();
  })();

  function valorCampo(nome) {
    var campo = form.querySelector('[name="' + nome + '"]');
    return campo ? campo.value : "";
  }

  function escrever(seletor, valor) {
    var el = form.querySelector(seletor);
    if (el) el.textContent = valor;
  }

  function limparResultado() {
    ["[data-pt-resultado-total]", "[data-pt-resultado-total-extenso]", "[data-pt-resultado-unitario]",
      "[data-pt-resultado-unitario-extenso]", "[data-pt-resultado-composicao]", "[data-pt-resultado-efetivo]"]
      .forEach(function (s) { escrever(s, "—"); });
  }

  function calcular() {
    var url = raiz.getAttribute("data-url-calcular");
    if (!url || !secaoDiarias) return;
    var csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
    var erros = form.querySelector("[data-pt-diarias-erros]");
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf ? csrf.value : "", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify({
        saida_sede_data: valorCampo("saida_sede_data"),
        saida_sede_hora: valorCampo("saida_sede_hora"),
        chegada_sede_data: valorCampo("chegada_sede_data"),
        chegada_sede_hora: valorCampo("chegada_sede_hora"),
        // O destino vai junto: numa página só, a prévia roda antes de gravar.
        destino_cidade: valorCampo("destino_cidade"),
        total_efetivo: totalEfetivo()
      })
    }).then(function (r) { return r.json(); }).then(function (dados) {
      if (!dados || !dados.ok) {
        limparResultado();
        if (erros) {
          var lista = (dados && dados.erros) || [];
          erros.textContent = lista.join(" ");
          erros.hidden = !lista.length;
        }
        return;
      }
      if (erros) { erros.textContent = ""; erros.hidden = true; }
      escrever("[data-pt-resultado-composicao]", dados.composicao || "—");
      escrever("[data-pt-resultado-efetivo]", String(dados.quantidade_servidores) + " servidor(es)");
      escrever("[data-pt-resultado-unitario]", "R$ " + dados.valor_unitario_display);
      escrever("[data-pt-resultado-unitario-extenso]", dados.valor_unitario_extenso || "—");
      escrever("[data-pt-resultado-total]", "R$ " + dados.valor_total_display);
      escrever("[data-pt-resultado-total-extenso]", dados.valor_total_extenso || "—");
    }).catch(function () { /* silencioso: o cálculo definitivo é o do salvar */ });
  }

  function agendarCalculo() {
    if (temporizador) window.clearTimeout(temporizador);
    temporizador = window.setTimeout(calcular, 350);
  }

  ["saida_sede_data", "saida_sede_hora", "chegada_sede_data", "chegada_sede_hora"].forEach(function (nome) {
    var campo = form.querySelector('[name="' + nome + '"]');
    if (campo) campo.addEventListener("change", agendarCalculo);
  });

  /* ── Atividades: filtro, preset, limpar e prévia de metas/recursos ── */

  (function () {
    var secao = form.querySelector("[data-pt-atividades]");
    if (!secao) return;
    var catalogo = {};
    lerJson("pt-atividades-data", []).forEach(function (item) { if (item && item.codigo) catalogo[item.codigo] = item; });
    var presets = {};
    lerJson("pt-presets-data", []).forEach(function (item) { if (item && item.id != null) presets[String(item.id)] = item; });
    var caixas = Array.prototype.slice.call(secao.querySelectorAll("[data-pt-atividade-caixa]"));
    var cartoes = Array.prototype.slice.call(secao.querySelectorAll("[data-pt-atividade]"));
    var busca = secao.querySelector("[data-pt-atividade-busca]");
    var limpar = secao.querySelector("[data-pt-atividade-limpar]");
    var preset = secao.querySelector('select[name="pt_atividade_preset"]');
    var vazio = secao.querySelector("[data-pt-atividade-vazio]");

    function renderizar(listaEl, vazioEl, totalEl, valores) {
      if (totalEl) totalEl.textContent = String(valores.length);
      if (listaEl) {
        listaEl.innerHTML = "";
        valores.forEach(function (texto) {
          var li = document.createElement("li");
          li.textContent = texto;
          listaEl.appendChild(li);
        });
      }
      if (vazioEl) vazioEl.hidden = valores.length > 0;
    }

    function atualizar() {
      var metas = [], recursos = [];
      caixas.forEach(function (caixa) {
        var cartao = caixa.closest("[data-pt-atividade]");
        if (cartao) cartao.classList.toggle("is-selected", caixa.checked);
        if (!caixa.checked) return;
        var item = catalogo[caixa.value];
        if (!item) return;
        var meta = (item.meta || "").trim();
        var recurso = (item.recurso || "").trim();
        if (meta && metas.indexOf(meta) < 0) metas.push(meta);
        if (recurso && recursos.indexOf(recurso) < 0) recursos.push(recurso);
      });
      renderizar(secao.querySelector("[data-pt-metas-lista]"), secao.querySelector("[data-pt-metas-vazio]"), secao.querySelector("[data-pt-metas-total]"), metas);
      renderizar(secao.querySelector("[data-pt-recursos-lista]"), secao.querySelector("[data-pt-recursos-vazio]"), secao.querySelector("[data-pt-recursos-total]"), recursos);
    }

    function aplicarCodigos(codigos) {
      var quer = {};
      (codigos || []).forEach(function (c) { quer[String(c)] = true; });
      caixas.forEach(function (caixa) { caixa.checked = Boolean(quer[caixa.value]); });
      atualizar();
    }

    caixas.forEach(function (caixa) { caixa.addEventListener("change", atualizar); });

    if (limpar) limpar.addEventListener("click", function () {
      caixas.forEach(function (caixa) { caixa.checked = false; });
      atualizar();
      definirSelect(preset, "");
    });

    if (preset) {
      var anterior = preset.value || "";
      preset.addEventListener("change", function () {
        var id = (preset.value || "").trim();
        if (!id) { anterior = ""; return; }
        var escolhido = presets[id];
        if (!escolhido) return;
        var jaMarcou = caixas.some(function (c) { return c.checked; });
        if (jaMarcou && !window.confirm("Aplicar o preset “" + (escolhido.nome || "") + "” vai substituir a seleção atual. Continuar?")) {
          definirSelect(preset, anterior);
          return;
        }
        aplicarCodigos(escolhido.codigos || []);
        anterior = id;
      });
    }

    if (busca) busca.addEventListener("input", function () {
      var termo = (busca.value || "").trim().toLowerCase();
      var algum = false;
      cartoes.forEach(function (cartao) {
        var casa = !termo || (cartao.getAttribute("data-filtro") || "").indexOf(termo) >= 0;
        cartao.hidden = !casa;
        if (casa) algum = true;
      });
      if (vazio) vazio.hidden = algum;
    });

    atualizar();
  })();

  /* ── Remover evento: confirmação em duas etapas, como os menus da lista ── */

  form.addEventListener("click", function (evento) {
    var botao = evento.target.closest("[data-pt-evento-remover]");
    if (!botao) return;
    if (botao.classList.contains("is-armado")) return;
    evento.preventDefault();
    botao.classList.add("is-armado");
    botao.setAttribute("title", botao.getAttribute("data-confirmar") || "Confirmar?");
    window.setTimeout(function () { botao.classList.remove("is-armado"); botao.setAttribute("title", "Remover evento"); }, 4000);
  });

  /* ── Prévia do documento: o PDF só é pedido quando o cartão abre ── */

  document.querySelectorAll("[data-ofc-doc]").forEach(function (cartao) {
    function carregar() {
      if (!cartao.open) return;
      var quadro = cartao.querySelector(":scope > .ofc-doc__corpo > iframe[data-src]");
      if (quadro && !quadro.getAttribute("src")) quadro.setAttribute("src", quadro.getAttribute("data-src"));
    }
    cartao.addEventListener("toggle", carregar);
    carregar();
    var acoes = cartao.querySelector(":scope > summary .ofc-doc__acoes");
    if (acoes) acoes.addEventListener("click", function (evento) {
      if (evento.target.closest("[data-menu-gatilho]")) evento.preventDefault();
    });
  });
})();
