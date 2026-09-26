/**
 * Triagem do e-mail na página inicial (components/v32/triagem_email.html).
 *
 * A pessoa solta o e-mail (ou o processo do eProtocolo em PDF) ou cola o
 * texto. O endpoint `core:triagem_ler` (POST) responde
 *   {token, resumo: {assunto, remetente, enviado_em, quando, quem, avisos},
 *    candidatos: [{modulo, rotulo, confianca, sinais, url}], sugerido, decidir}
 * e aqui:
 *
 * - com `decidir`, a página vai direto para a tela nova do módulo sugerido
 *   (`url`, com ?email_origem=<token>): lá a faixa "Preencher com um e-mail"
 *   lê o e-mail sozinha e oferece os outros módulos;
 * - sem, mostra o resumo do e-mail e um botão por módulo candidato (o
 *   sugerido em destaque) para a pessoa escolher.
 *
 * O conteúdo do e-mail nunca entra como HTML: tudo vai por textContent.
 */
(function () {
  "use strict";

  var EXTENSOES = [".eml", ".msg", ".pdf", ".txt"];

  // O celular entrega o arquivo como uma referência que às vezes expira antes
  // do envio (Drive, Gmail, "Recentes") — o fetch morre com "Failed to fetch".
  // Ler o conteúdo já, na hora da escolha, e mandar a cópia evita isso; se
  // nem a leitura der, a mensagem explica o que fazer.
  var MSG_LEITURA = "Não consegui abrir o arquivo no aparelho. Salve-o no telefone (pasta Downloads) e escolha de novo pelo app Arquivos — ou use o computador.";
  var MSG_REDE = "A conexão caiu no envio do arquivo. Confira a internet e tente de novo; se continuar, salve o arquivo no aparelho e escolha de novo.";
  function copiaDe(arquivo) {
    if (!arquivo.arrayBuffer) return Promise.resolve(arquivo);
    return arquivo.arrayBuffer().then(function (conteudo) {
      return new File([conteudo], arquivo.name || "arquivo", { type: arquivo.type || "application/octet-stream" });
    });
  }
  function mensagemDeFalha(falha) {
    if (falha && falha.name === "TypeError") return MSG_REDE;
    return falha && falha.message ? falha.message : "Não foi possível ler o e-mail.";
  }

  function el(tag, classe, texto) {
    var elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto !== undefined && texto !== null) elemento.textContent = texto;
    return elemento;
  }

  // Pelo nome; sem extensão (o celular às vezes manda "document"), pelo tipo.
  var TIPOS = { "application/pdf": ".pdf", "message/rfc822": ".eml", "text/plain": ".txt", "application/vnd.ms-outlook": ".msg" };
  function extensaoDe(arquivo) {
    var nome = (arquivo.name || "").toLowerCase();
    var ponto = nome.lastIndexOf(".");
    if (ponto !== -1 && ponto < nome.length - 1) return nome.slice(ponto);
    return TIPOS[(arquivo.type || "").toLowerCase()] || "";
  }

  function iniciar(bloco) {
    var url = bloco.getAttribute("data-url");
    if (!url) return;
    var maximo = parseInt(bloco.getAttribute("data-max-bytes"), 10) || 0;
    var entrada = bloco.querySelector("[data-tri-arquivo]");
    var botaoColar = bloco.querySelector("[data-tri-colar]");
    var painelTexto = bloco.querySelector("[data-tri-texto]");
    var campoTexto = bloco.querySelector("[data-tri-texto-campo]");
    var botaoLerTexto = bloco.querySelector("[data-tri-ler-texto]");
    var estado = bloco.querySelector("[data-tri-estado]");
    var erro = bloco.querySelector("[data-tri-erro]");
    var resultado = bloco.querySelector("[data-tri-resultado]");

    function csrf() {
      var campo = bloco.querySelector('input[name="csrfmiddlewaretoken"]');
      return campo ? campo.value : "";
    }

    function anunciar(texto) { estado.textContent = texto; }

    function mostrarErro(texto) {
      erro.textContent = texto;
      erro.hidden = !texto;
    }

    function ocupado(sim) {
      bloco.classList.toggle("is-lendo", sim);
      bloco.setAttribute("aria-busy", sim ? "true" : "false");
      [entrada, botaoColar, botaoLerTexto].forEach(function (b) { if (b) b.disabled = sim; });
    }

    function descrever(resumo) {
      var partes = [];
      if (resumo.remetente) partes.push("De " + resumo.remetente);
      if (resumo.enviado_em) partes.push("em " + resumo.enviado_em);
      var texto = partes.join(" ");
      if (resumo.assunto) texto += (texto ? ": " : "") + "“" + resumo.assunto + "”";
      if (resumo.quando) texto += " — evento em " + resumo.quando;
      return texto || "E-mail lido.";
    }

    function mostrar(dados) {
      resultado.textContent = "";
      var candidatos = dados.candidatos || [];
      var titulo = el("p", "tri__titulo");
      if (dados.sugerido) {
        var sugerido = candidatos.filter(function (c) { return c.modulo === dados.sugerido; })[0];
        titulo.appendChild(document.createTextNode("Parece um pedido de "));
        titulo.appendChild(el("b", "", sugerido ? sugerido.rotulo : dados.sugerido));
        titulo.appendChild(document.createTextNode(", mas não tenho certeza. Onde registrar?"));
      } else {
        titulo.appendChild(el("b", "", "Não consegui dizer de que módulo é este pedido."));
        titulo.appendChild(document.createTextNode(" Escolha onde registrar:"));
      }
      resultado.appendChild(titulo);
      resultado.appendChild(el("p", "tri__resumo", descrever(dados.resumo || {})));

      var avisos = (dados.resumo && dados.resumo.avisos) || [];
      if (avisos.length) {
        var lista = el("ul", "tri__avisos");
        lista.setAttribute("aria-label", "Avisos da leitura do e-mail");
        avisos.forEach(function (a) { lista.appendChild(el("li", "tri__aviso", a)); });
        resultado.appendChild(lista);
      }

      var opcoes = el("ul", "tri__opcoes");
      candidatos.forEach(function (c) {
        var li = el("li");
        var link = el("a", "tri__opcao" + (c.modulo === dados.sugerido ? " tri__opcao--sugerida" : ""));
        link.href = c.url;
        link.appendChild(el("span", "", c.rotulo));
        var detalhe = c.sinais && c.sinais.length ? c.sinais.slice(0, 3).join(", ") : "sem sinais no texto";
        if (c.confianca) detalhe = Math.round(c.confianca * 100) + "% · " + detalhe;
        link.appendChild(el("small", "", detalhe));
        li.appendChild(link);
        opcoes.appendChild(li);
      });
      resultado.appendChild(opcoes);
      resultado.hidden = false;
      anunciar("");
    }

    function enviar(corpo) {
      mostrarErro("");
      resultado.hidden = true;
      ocupado(true);
      anunciar("Lendo o e-mail…");
      fetch(url, {
        method: "POST",
        body: corpo,
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest" }
      })
        .then(function (resposta) {
          var tipo = resposta.headers.get("Content-Type") || "";
          if (tipo.indexOf("application/json") === -1) {
            throw new Error(
              resposta.redirected ? "Sua sessão expirou. Entre de novo e solte o e-mail outra vez." :
              resposta.status === 413 ? "O arquivo é grande demais para enviar." :
              "Não foi possível ler o e-mail agora (erro " + resposta.status + ")."
            );
          }
          return resposta.json().then(function (dados) {
            if (!resposta.ok) throw new Error(dados.erro || "Não foi possível ler o e-mail.");
            return dados;
          });
        })
        .then(function (dados) {
          var candidatos = dados.candidatos || [];
          var sugerido = candidatos.filter(function (c) { return c.modulo === dados.sugerido; })[0];
          if (dados.decidir && sugerido && sugerido.url) {
            anunciar("Parece um pedido de " + sugerido.rotulo + ": abrindo a tela já preenchida…");
            window.location.assign(sugerido.url);
            return;
          }
          if (!candidatos.length) {
            throw new Error("Você não tem acesso a nenhum módulo que registre pedidos por e-mail.");
          }
          mostrar(dados);
          if (painelTexto && !painelTexto.hidden) alternarTexto(false);
        })
        .catch(function (falha) {
          anunciar("");
          mostrarErro(mensagemDeFalha(falha));
        })
        .then(function () { ocupado(false); });
    }

    function lerArquivo(arquivo) {
      if (!arquivo) return;
      if (EXTENSOES.indexOf(extensaoDe(arquivo)) === -1) {
        mostrarErro("Envie o e-mail em .eml, .msg, .pdf ou .txt — ou cole o texto.");
        return;
      }
      if (maximo && arquivo.size > maximo) {
        mostrarErro("O arquivo passa do limite de " + Math.round(maximo / 1048576) + " MB.");
        return;
      }
      ocupado(true);
      anunciar("Abrindo o arquivo…");
      copiaDe(arquivo).then(function (copia) {
        var dados = new FormData();
        dados.append("arquivo", copia, copia.name);
        enviar(dados);
      }, function () {
        ocupado(false);
        anunciar("");
        mostrarErro(MSG_LEITURA);
      });
    }

    function lerTexto() {
      var texto = campoTexto ? campoTexto.value.trim() : "";
      if (!texto) {
        mostrarErro("Cole o texto do e-mail antes de ler.");
        if (campoTexto) campoTexto.focus();
        return;
      }
      var dados = new FormData();
      dados.append("texto", texto);
      enviar(dados);
    }

    function alternarTexto(abrir) {
      if (!painelTexto || !botaoColar) return;
      painelTexto.hidden = !abrir;
      botaoColar.setAttribute("aria-expanded", abrir ? "true" : "false");
      if (abrir && campoTexto) campoTexto.focus();
    }

    if (entrada) {
      entrada.addEventListener("change", function () {
        lerArquivo(entrada.files && entrada.files[0]);
        entrada.value = "";
      });
    }
    if (botaoColar) botaoColar.addEventListener("click", function () { alternarTexto(painelTexto.hidden); });
    if (botaoLerTexto) botaoLerTexto.addEventListener("click", lerTexto);
    if (campoTexto) {
      campoTexto.addEventListener("keydown", function (evento) {
        if (evento.key === "Enter" && (evento.ctrlKey || evento.metaKey)) {
          evento.preventDefault();
          lerTexto();
        }
      });
    }

    function temArquivos(evento) {
      var tipos = evento.dataTransfer && evento.dataTransfer.types;
      return Boolean(tipos) && Array.prototype.indexOf.call(tipos, "Files") !== -1;
    }
    var profundidade = 0;
    bloco.addEventListener("dragenter", function (evento) {
      if (!temArquivos(evento)) return;
      evento.preventDefault();
      profundidade += 1;
      bloco.classList.add("is-arrastando");
    });
    bloco.addEventListener("dragover", function (evento) {
      if (!temArquivos(evento)) return;
      evento.preventDefault();
      evento.dataTransfer.dropEffect = "copy";
    });
    bloco.addEventListener("dragleave", function (evento) {
      if (!temArquivos(evento)) return;
      profundidade = Math.max(0, profundidade - 1);
      if (!profundidade) bloco.classList.remove("is-arrastando");
    });
    bloco.addEventListener("drop", function (evento) {
      if (!temArquivos(evento)) return;
      evento.preventDefault();
      profundidade = 0;
      bloco.classList.remove("is-arrastando");
      var arquivos = evento.dataTransfer && evento.dataTransfer.files;
      if (arquivos && arquivos.length > 1) {
        mostrarErro("Solte um e-mail por vez.");
        return;
      }
      lerArquivo(arquivos && arquivos[0]);
    });
  }

  document.querySelectorAll("[data-triagem-email]").forEach(iniciar);
})();
