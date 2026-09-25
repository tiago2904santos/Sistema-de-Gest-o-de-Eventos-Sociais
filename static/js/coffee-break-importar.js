/* Coffee Break — importar o processo de pagamento (pages/coffee_break/_importar_processo.html).

   - `[data-cb-importar]` (botão da lista, item do ⋮, botão da etapa 3) abre o
     modal; `data-solicitacao` diz de qual solicitação ele foi aberto (a âncora
     da identificação) e `data-titulo` aparece no texto.
   - `[data-cb-importar-soltar]` (o cartão da lista, a faixa da etapa 3):
     arrastar um arquivo por cima acende a área; soltar envia na hora (com a
     `data-solicitacao` da área, se houver).
   - O envio é um POST comum: a resposta é a tela de resultado ou de conferência. */
(function () {
  "use strict";

  var dialogo = document.querySelector("[data-cb-importar-dialogo]");
  if (!dialogo || typeof dialogo.showModal !== "function") return;

  var form = dialogo.querySelector("[data-cb-importar-form]");
  var campo = dialogo.querySelector("[data-cb-importar-arquivo]");
  var ancora = dialogo.querySelector("[data-cb-importar-solicitacao]");
  var rotulo = dialogo.querySelector("[data-cb-importar-rotulo]");
  var quadro = dialogo.querySelector("[data-cb-importar-quadro]");
  var erro = dialogo.querySelector("[data-cb-importar-erro]");
  var enviar = dialogo.querySelector("[data-cb-importar-enviar]");
  var texto = dialogo.querySelector("[data-cb-importar-texto]");
  var VAZIO = rotulo.textContent;
  var ACAO = enviar.textContent;

  function ehPdf(arquivo) {
    return /\.pdf$/i.test(arquivo.name) || arquivo.type === "application/pdf";
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
    var ok = !!arquivo && ehPdf(arquivo);
    if (arquivo && !ok) mostrarErro("Escolha o PDF do processo (o arquivo que o eProtocolo gera).");
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

  function abrir(solicitacao, titulo) {
    form.reset();
    ancora.value = solicitacao || "";
    texto.textContent = titulo
      ? "Envie o PDF inteiro do processo de pagamento da " + titulo + ", baixado do eProtocolo. O protocolo de pagamento é gravado e a nota fiscal que faltar é anexada — também nas outras OS do mesmo pagamento."
      : texto.getAttribute("data-texto-padrao");
    enviar.textContent = ACAO;
    atualizar();
    if (!dialogo.open) dialogo.showModal();
  }

  function enviando() {
    enviar.disabled = true;
    enviar.textContent = "Lendo o processo… pode levar alguns segundos";
  }

  document.addEventListener("click", function (evento) {
    var gatilho = evento.target.closest && evento.target.closest("[data-cb-importar]");
    if (!gatilho) return;
    evento.preventDefault();
    fecharMenu(gatilho);
    abrir(gatilho.getAttribute("data-solicitacao"), gatilho.getAttribute("data-titulo"));
  });

  campo.addEventListener("change", atualizar);
  dialogo.querySelectorAll("[data-cb-importar-fechar]").forEach(function (botao) {
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

  // O próprio modal também recebe o arquivo arrastado.
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

  document.querySelectorAll("[data-cb-importar-soltar]").forEach(function (area) {
    var faixa = area.querySelector("[data-cb-importar-faixa]");
    var profundidade = 0;

    function marcar(ligado) {
      area.classList.toggle("is-soltando", ligado);
      if (faixa) faixa.hidden = !ligado;
    }

    area.addEventListener("dragenter", function (evento) {
      if (!temArquivo(evento)) return;
      evento.preventDefault();
      profundidade += 1;
      marcar(true);
    });
    area.addEventListener("dragover", function (evento) {
      if (!temArquivo(evento)) return;
      evento.preventDefault();
      evento.dataTransfer.dropEffect = "copy";
      marcar(true);
    });
    area.addEventListener("dragleave", function () {
      profundidade = Math.max(0, profundidade - 1);
      if (!profundidade) marcar(false);
    });
    area.addEventListener("drop", function (evento) {
      if (!temArquivo(evento)) return;
      evento.preventDefault();
      profundidade = 0;
      marcar(false);
      abrir(area.getAttribute("data-solicitacao"), area.getAttribute("data-titulo"));
      try {
        campo.files = evento.dataTransfer.files;
      } catch (e) {
        mostrarErro("Não deu para usar o arquivo arrastado: escolha pelo botão.");
        return;
      }
      if (!atualizar()) return;
      enviando();
      form.submit();
    });
  });
})();
