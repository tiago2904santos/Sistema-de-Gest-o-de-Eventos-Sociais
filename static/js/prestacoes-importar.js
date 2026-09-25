/* Prestações — importar o processo do eProtocolo (pages/viagens_prestacoes/_importar_dialogo.html).

   - `[data-importar-processo]` (botão do topo e item do ⋮ de cada ofício) abre o
     modal; `data-url` troca o endereço (a prestação do ofício já escolhida) e
     `data-titulo` diz de qual ofício é.
   - `[data-importar-soltar]` (o cartão da lista): arrastar um arquivo por cima
     mostra a faixa "Solte para importar"; soltar envia na hora. Soltado sobre o
     bloco de um ofício (`[data-importar-url]`), vai para a prestação dele.
   - O envio é um POST comum: a resposta é a tela de resultado ou de conferência. */
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
    var arquivo = campo.files && campo.files[0];
    mostrarErro("");
    quadro.classList.toggle("an-arquivo--escolhido", !!arquivo);
    rotulo.textContent = arquivo ? arquivo.name : VAZIO;
    var ok = !!arquivo && aceito(arquivo);
    if (arquivo && !ok) mostrarErro("Escolha o PDF do processo (ou uma imagem PNG ou JPG).");
    enviar.disabled = !ok;
    return ok;
  }

  function fecharMenu(origem) {
    var corpo = origem && origem.closest && origem.closest("[data-menu-corpo]");
    if (!corpo) return;
    corpo.hidden = true;
    var gatilho = corpo.parentElement && corpo.parentElement.querySelector("[data-menu-gatilho]");
    if (gatilho) gatilho.setAttribute("aria-expanded", "false");
  }

  function abrir(url, titulo) {
    form.reset();
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
    if (!atualizar()) { evento.preventDefault(); return; }
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
