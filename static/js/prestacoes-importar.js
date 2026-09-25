/* Prestações — importar o processo do eProtocolo (pages/viagens_prestacoes/_importar_dialogo.html).

   - `[data-importar-processo]` (botão do topo e item do ⋮ de cada ofício) abre o
     modal; `data-url` troca o endereço (a prestação do ofício já escolhida) e
     `data-titulo` diz de qual ofício é.
   - `[data-importar-soltar]` (o cartão da lista): arrastar um arquivo por cima
     mostra a faixa "Solte para importar"; soltar envia na hora. Soltado sobre o
     bloco de um ofício (`[data-importar-url]`), vai para a prestação dele.
   - Um arquivo: POST comum (a resposta é a tela de resultado ou de conferência).
   - Vários (ex.: os comprovantes baixados do WhatsApp): um fetch por arquivo,
     em sequência — cada um vai para a sua prestação — e o andamento aparece
     no próprio modal (`[data-importar-lote]`), com o link de cada resultado. */
(function () {
  "use strict";

  var dialogo = document.querySelector("[data-importar-dialogo]");
  if (!dialogo || typeof dialogo.showModal !== "function") return;

  var form = dialogo.querySelector("[data-importar-form]");
  var campo = dialogo.querySelector("[data-importar-arquivo]");
  var rotulo = dialogo.querySelector("[data-importar-rotulo]");
  var quadro = dialogo.querySelector("[data-importar-quadro]");
  var erro = dialogo.querySelector("[data-importar-erro]");
  var enviar = dialogo.querySelector("[data-importar-enviar]");
  var texto = dialogo.querySelector("[data-importar-texto]");
  var urlPadrao = form.getAttribute("data-url-padrao") || form.action;
  var lote = dialogo.querySelector("[data-importar-lote]");
  var loteResumo = dialogo.querySelector("[data-importar-lote-resumo]");
  var loteLista = dialogo.querySelector("[data-importar-lote-lista]");
  var emLote = false;
  var VAZIO = rotulo.textContent;
  var ACAO = enviar.textContent;

  function aceito(arquivo) {
    return /\.(pdf|png|jpe?g)$/i.test(arquivo.name) || /^(application\/pdf|image\/(png|jpeg))$/.test(arquivo.type);
  }

  function mostrarErro(mensagem) {
    erro.textContent = mensagem || "";
    erro.hidden = !mensagem;
  }

  function atualizar() {
    var arquivos = Array.prototype.slice.call(campo.files || []);
    mostrarErro("");
    quadro.classList.toggle("an-arquivo--escolhido", arquivos.length > 0);
    if (!arquivos.length) rotulo.textContent = VAZIO;
    else if (arquivos.length === 1) rotulo.textContent = arquivos[0].name;
    else rotulo.textContent = arquivos.length + " arquivos: " + arquivos.map(function (a) { return a.name; }).join(", ");
    var recusados = arquivos.filter(function (a) { return !aceito(a); });
    var ok = arquivos.length > 0 && !recusados.length;
    if (recusados.length) {
      mostrarErro((recusados.length === 1 ? "Este arquivo não é PDF, PNG nem JPG: " : "Estes arquivos não são PDF, PNG nem JPG: ") +
        recusados.map(function (a) { return a.name; }).join(", ") + ".");
    }
    enviar.disabled = !ok || emLote;
    enviar.textContent = arquivos.length > 1 ? "Importar " + arquivos.length + " arquivos" : ACAO;
    return ok;
  }

  /* ---------- vários arquivos: um por vez, cada um para a sua prestação ---------- */
  var ROTULOS = {
    aplicada: ["Importado", "st--atendido"],
    analisada: ["Conferir", "st--pendente"],
    repetido: ["Já enviado", "st--neutro"],
    erro: ["Não entrou", "st--cancelado"]
  };

  function linhaDoLote(nome) {
    var li = document.createElement("li");
    li.className = "pc-lote__item";
    var arquivo = document.createElement("span");
    arquivo.className = "pc-lote__arquivo";
    arquivo.textContent = nome;
    var selo = document.createElement("span");
    selo.className = "st st--neutro";
    selo.textContent = "Na fila";
    var detalhe = document.createElement("span");
    detalhe.className = "pc-lote__detalhe";
    li.appendChild(arquivo);
    li.appendChild(selo);
    li.appendChild(detalhe);
    loteLista.appendChild(li);
    return { li: li, selo: selo, detalhe: detalhe };
  }

  function marcarLinha(linha, situacao, texto, url) {
    var par = ROTULOS[situacao] || ROTULOS.erro;
    linha.selo.className = "st " + par[1];
    linha.selo.textContent = par[0];
    linha.detalhe.textContent = texto || "";
    if (url) {
      var link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = situacao === "analisada" ? "Conferir" : "Ver";
      linha.detalhe.appendChild(document.createTextNode(" "));
      linha.detalhe.appendChild(link);
    }
  }

  function enviarUm(arquivo) {
    var dados = new FormData(form);
    dados.set("arquivo", arquivo, arquivo.name);
    return fetch(form.action, {
      method: "POST",
      body: dados,
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" }
    }).then(function (resposta) {
      return resposta.json().catch(function () { return { ok: false, error: "Resposta inesperada do servidor (" + resposta.status + ")." }; });
    }).catch(function () {
      return { ok: false, error: "Sem conexão com o servidor." };
    });
  }

  function importarVarios(arquivos) {
    emLote = true;
    lote.hidden = false;
    loteLista.textContent = "";
    enviar.disabled = true;
    campo.disabled = true;
    var contagem = { aplicada: 0, analisada: 0, repetido: 0, erro: 0 };
    var linhas = arquivos.map(function (a) { return linhaDoLote(a.name); });
    var feito = 0;

    function resumir(fim) {
      var partes = [];
      if (contagem.aplicada) partes.push(contagem.aplicada + " importado" + (contagem.aplicada > 1 ? "s" : ""));
      if (contagem.analisada) partes.push(contagem.analisada + " para conferir");
      if (contagem.repetido) partes.push(contagem.repetido + " já enviado" + (contagem.repetido > 1 ? "s" : ""));
      if (contagem.erro) partes.push(contagem.erro + " não entr" + (contagem.erro > 1 ? "aram" : "ou"));
      loteResumo.textContent = (fim ? "Pronto: " : "Lendo " + (feito + 1) + " de " + arquivos.length + "… ") + partes.join(" · ");
    }

    var fila = Promise.resolve();
    arquivos.forEach(function (arquivo, i) {
      fila = fila.then(function () {
        resumir(false);
        linhas[i].selo.textContent = "Lendo…";
        return enviarUm(arquivo).then(function (r) {
          var situacao = r.ok ? (r.situacao || "analisada") : "erro";
          if (!(situacao in contagem)) situacao = "analisada";
          contagem[situacao] += 1;
          var texto = r.ok ? (r.destino ? "→ " + r.destino : "") : (r.error || r.message || "Não foi possível ler.");
          if (r.ok && situacao === "analisada" && !r.destino) texto = "prestação não identificada";
          marcarLinha(linhas[i], situacao, texto, r.ok ? r.url : "");
          feito += 1;
        });
      });
    });
    return fila.then(function () {
      resumir(true);
      emLote = false;
      campo.disabled = false;
      enviar.textContent = "Fechar e atualizar a lista";
      enviar.disabled = false;
      enviar.setAttribute("data-importar-recarregar", "");
    });
  }

  function fecharMenu(origem) {
    var corpo = origem && origem.closest && origem.closest("[data-menu-corpo]");
    if (!corpo) return;
    corpo.hidden = true;
    var gatilho = corpo.parentElement && corpo.parentElement.querySelector("[data-menu-gatilho]");
    if (gatilho) gatilho.setAttribute("aria-expanded", "false");
  }

  function abrir(url, titulo) {
    if (emLote) { if (!dialogo.open) dialogo.showModal(); return; }
    form.reset();
    lote.hidden = true;
    loteLista.textContent = "";
    enviar.removeAttribute("data-importar-recarregar");
    form.action = url || urlPadrao;
    if (texto) {
      // `data-texto-registro` é o texto de cada lista (Prestações, Ofícios, Termos), com {titulo}.
      var modelo = texto.getAttribute("data-texto-registro") ||
        "Envie o PDF inteiro do processo do {titulo}. Os documentos entram na prestação dele: ofício, despachos, relatórios técnicos, diário de bordo e comprovantes.";
      texto.textContent = titulo ? modelo.replace("{titulo}", titulo) : texto.getAttribute("data-texto-padrao");
    }
    enviar.textContent = ACAO;
    atualizar();
    if (!dialogo.open) dialogo.showModal();
  }

  function enviando() {
    enviar.disabled = true;
    enviar.textContent = "Importando… pode levar alguns segundos";
  }

  document.addEventListener("click", function (evento) {
    var gatilho = evento.target.closest && evento.target.closest("[data-importar-processo]");
    if (!gatilho) return;
    evento.preventDefault();
    fecharMenu(gatilho);
    abrir(gatilho.getAttribute("data-url"), gatilho.getAttribute("data-titulo"));
  });

  campo.addEventListener("change", atualizar);
  dialogo.querySelectorAll("[data-importar-fechar]").forEach(function (botao) {
    botao.addEventListener("click", function () { dialogo.close(); });
  });
  dialogo.addEventListener("click", function (evento) {
    if (evento.target === dialogo) dialogo.close();
  });
  form.addEventListener("submit", function (evento) {
    if (enviar.hasAttribute("data-importar-recarregar")) {
      evento.preventDefault();
      window.location.reload();
      return;
    }
    if (!atualizar()) { evento.preventDefault(); return; }
    var arquivos = Array.prototype.slice.call(campo.files || []);
    if (arquivos.length > 1) {
      evento.preventDefault();
      importarVarios(arquivos);
      return;
    }
    enviando();
  });

  /* ---------- soltar o arquivo ---------- */
  function temArquivo(evento) {
    var tipos = evento.dataTransfer && evento.dataTransfer.types;
    return !!tipos && Array.prototype.indexOf.call(tipos, "Files") !== -1;
  }

  function soltarEm(alvo, arquivos, url, titulo) {
    abrir(url, titulo);
    try {
      campo.files = arquivos;
    } catch (e) {
      mostrarErro("Não deu para usar o arquivo arrastado: escolha pelo botão.");
      return;
    }
    if (!atualizar()) return;
    if (arquivos.length > 1) {
      importarVarios(Array.prototype.slice.call(arquivos));
      return;
    }
    enviando();
    form.submit();
  }

  // O modal também recebe o arquivo arrastado sobre ele.
  dialogo.addEventListener("dragover", function (evento) {
    if (!temArquivo(evento)) return;
    evento.preventDefault();
    quadro.classList.add("is-arrastando");
  });
  dialogo.addEventListener("dragleave", function () { quadro.classList.remove("is-arrastando"); });
  dialogo.addEventListener("drop", function (evento) {
    if (!temArquivo(evento)) return;
    evento.preventDefault();
    quadro.classList.remove("is-arrastando");
    try { campo.files = evento.dataTransfer.files; } catch (e) { return; }
    atualizar();
  });

  document.querySelectorAll("[data-importar-soltar]").forEach(function (area) {
    var faixa = area.querySelector("[data-importar-faixa]");
    var profundidade = 0;

    function marcar(ligado, bloco) {
      area.classList.toggle("is-soltando", ligado);
      if (faixa) faixa.hidden = !ligado;
      area.querySelectorAll("[data-importar-url].is-alvo").forEach(function (b) { b.classList.remove("is-alvo"); });
      if (ligado && bloco) bloco.classList.add("is-alvo");
    }

    area.addEventListener("dragenter", function (evento) {
      if (!temArquivo(evento)) return;
      evento.preventDefault();
      profundidade += 1;
      marcar(true, evento.target.closest("[data-importar-url]"));
    });
    area.addEventListener("dragover", function (evento) {
      if (!temArquivo(evento)) return;
      evento.preventDefault();
      evento.dataTransfer.dropEffect = "copy";
      marcar(true, evento.target.closest("[data-importar-url]"));
    });
    area.addEventListener("dragleave", function () {
      profundidade = Math.max(0, profundidade - 1);
      if (!profundidade) marcar(false);
    });
    area.addEventListener("drop", function (evento) {
      if (!temArquivo(evento)) return;
      evento.preventDefault();
      profundidade = 0;
      var bloco = evento.target.closest("[data-importar-url]");
      marcar(false);
      soltarEm(area, evento.dataTransfer.files,
        bloco ? bloco.getAttribute("data-importar-url") : area.getAttribute("data-url"),
        bloco ? bloco.getAttribute("data-importar-titulo") : "");
    });
  });
})();
