/**
 * Preencher com um e-mail (components/v32/preencher_por_email.html).
 *
 * A pessoa solta o arquivo do e-mail (.eml, .msg, PDF impresso ou .txt) ou
 * cola o texto. O endpoint do módulo (`data-url`, POST) lê e devolve
 *   {campos: {nome: {valor, exibir, confianca, trecho, rotulo}},
 *    avisos: [...], duplicados: [{titulo, url}],
 *    mensagem: {assunto, remetente, enviado_em},
 *    arquivo: {token, nome, anexos}}
 * e aqui:
 *
 * - só se preenchem campos vazios — ou, nos listados em
 *   `data-substituir-padrao`, os que ainda têm o valor que a tela trouxe
 *   (data de hoje, estado PR) e ninguém mexeu. O campo é achado por
 *   `form.elements[nome]`, que inclui os de fora do <form> com `form=`;
 * - na ordem que as dependências pedem: estado antes do município (trocar o
 *   estado limpa o município), tipo do evento antes do solicitante (Paraná
 *   em Ação sobrescreve o solicitante), canal antes do protocolo, unidade
 *   móvel antes da designada;
 * - cada campo recebe `input` e `change` com bubbles: máscaras, selects
 *   aprimorados, cascatas, calendários, o rascunho automático e a prévia da
 *   OS acompanham;
 * - o que foi preenchido fica marcado (.is-sugerido, com o trecho de onde
 *   saiu no title) até a pessoa mexer no campo;
 * - sugestão fraca (confiança "B") e valor diferente num campo já
 *   preenchido viram "Outras sugestões", com o botão "Usar";
 * - o token do e-mail vai no campo oculto `email_origem`, para o módulo
 *   anexar o original e registrar no histórico ao salvar. Ele fica também no
 *   sessionStorage da aba até o envio do formulário: se a página recarregar
 *   (e o rascunho automático devolver os campos), o vínculo volta junto — com
 *   o botão "Não ligar este e-mail" para quem não quiser.
 *
 * O preenchimento só acontece por ação da pessoa, depois do carregamento:
 * o rascunho automático (app.js) já restaurou o que tinha — e o que ele
 * restaurou conta como preenchido, não é sobrescrito.
 *
 * Com `data-anexos` (o id do seletor de anexos do formulário), a faixa também
 * recebe os anexos: soltar vários arquivos lê o e-mail (ou, sem e-mail, o
 * primeiro PDF) e manda o resto — ofício, fotos, documentos — para a lista de
 * anexos, que vai junto ao salvar. PDF que não se lê como e-mail vira anexo.
 *
 * O conteúdo do e-mail nunca entra como HTML: tudo vai por textContent.
 */
(function () {
  "use strict";

  var PRIMEIROS = ["estado", "tipo_evento", "canal_solicitacao", "unidade_movel", "evento"];
  var EXTENSOES = [".eml", ".msg", ".pdf", ".txt"];
  var EMAILS = [".eml", ".msg", ".txt"];

  // Pelo nome; sem extensão (o celular às vezes manda "document"), pelo tipo.
  var TIPOS = { "application/pdf": ".pdf", "message/rfc822": ".eml", "text/plain": ".txt", "application/vnd.ms-outlook": ".msg" };
  function extensaoDe(arquivo) {
    var nome = (arquivo.name || "").toLowerCase();
    var ponto = nome.lastIndexOf(".");
    if (ponto !== -1 && ponto < nome.length - 1) return nome.slice(ponto);
    return TIPOS[(arquivo.type || "").toLowerCase()] || "";
  }

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

  function plural(n, um, varios) {
    return n + " " + (n === 1 ? um : varios);
  }

  function ordenar(nomes) {
    return nomes
      .map(function (nome, i) {
        var p = PRIMEIROS.indexOf(nome);
        return { nome: nome, i: i, p: p === -1 ? PRIMEIROS.length : p };
      })
      .sort(function (a, b) { return a.p - b.p || a.i - b.i; })
      .map(function (x) { return x.nome; });
  }

  function marcavel(campo) {
    return campo.type === "checkbox" || campo.type === "radio";
  }

  function disparar(campo) {
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function iniciar(bloco) {
    var form = document.getElementById(bloco.getAttribute("data-formulario"));
    var url = bloco.getAttribute("data-url");
    if (!form || !url) return;
    var substituiveis = (bloco.getAttribute("data-substituir-padrao") || "").split(/\s+/).filter(Boolean);
    var anexaOriginal = bloco.hasAttribute("data-anexa-original");
    var registro = bloco.getAttribute("data-registro") || "registro";
    var maximo = parseInt(bloco.getAttribute("data-max-bytes"), 10) || 0;

    var entrada = bloco.querySelector("[data-pe-arquivo]");
    var botaoColar = bloco.querySelector("[data-pe-colar]");
    var painelTexto = bloco.querySelector("[data-pe-texto]");
    var campoTexto = bloco.querySelector("[data-pe-texto-campo]");
    var botaoLerTexto = bloco.querySelector("[data-pe-ler-texto]");
    var estado = bloco.querySelector("[data-pe-estado]");
    var erro = bloco.querySelector("[data-pe-erro]");
    var resultado = bloco.querySelector("[data-pe-resultado]");
    var vinculo = bloco.querySelector("[data-pe-vinculo]");
    var vinculoTexto = bloco.querySelector("[data-pe-vinculo-texto]");
    var botaoDesligar = bloco.querySelector("[data-pe-desligar]");
    var CHAVE = "preencher-email:" + window.location.pathname + "#" + form.id;
    var seletorAnexos = bloco.getAttribute("data-anexos") ? document.getElementById(bloco.getAttribute("data-anexos")) : null;
    var avisoAnexados = bloco.querySelector("[data-pe-anexados]");

    var aplicando = false;
    var marcados = [];
    var desfazer = [];

    // ------------------------------------------------------------------
    // Campos do formulário
    // ------------------------------------------------------------------

    function camposDe(nome) {
      var alvo = form.elements.namedItem(nome);
      if (!alvo) return [];
      var lista = alvo.tagName ? [alvo] : Array.prototype.slice.call(alvo);
      lista = lista.filter(function (c) { return c.name === nome; });
      var visiveis = lista.filter(function (c) { return c.type !== "hidden"; });
      return visiveis.length ? visiveis : lista;
    }

    function bloqueado(campos) {
      return campos.some(function (c) { return c.disabled || c.readOnly; });
    }

    function livre(campos, nome) {
      var campo = campos[0];
      var padrao = substituiveis.indexOf(nome) !== -1;
      if (marcavel(campo)) {
        if (!campos.some(function (c) { return c.checked; })) return true;
        return padrao && campos.every(function (c) { return c.checked === c.defaultChecked; });
      }
      if (campo.tagName === "SELECT") {
        if (!campo.value) return true;
        var opcao = campo.options[campo.selectedIndex];
        return padrao && Boolean(opcao && opcao.defaultSelected);
      }
      if (!String(campo.value).trim()) return true;
      return padrao && campo.value === campo.defaultValue;
    }

    function valorAtual(campos) {
      if (marcavel(campos[0])) {
        return campos.filter(function (c) { return c.checked; }).map(function (c) { return c.value; });
      }
      return campos[0].value;
    }

    function mesmoValor(campos, valor) {
      var atual = valorAtual(campos);
      if (Array.isArray(atual)) {
        var desejado = (Array.isArray(valor) ? valor : [valor]).map(String).sort();
        return atual.slice().sort().join("|") === desejado.join("|");
      }
      return String(atual) === (Array.isArray(valor) ? valor.join(", ") : String(valor));
    }

    function guardarParaDesfazer(campos) {
      desfazer.push({
        campos: campos,
        valores: campos.map(function (c) { return marcavel(c) ? c.checked : c.value; })
      });
    }

    function definir(campos, valor) {
      var campo = campos[0];
      if (marcavel(campo)) {
        var valores = (Array.isArray(valor) ? valor : [valor]).map(String);
        var unico = campos.length === 1 && campo.type === "checkbox" && !Array.isArray(valor);
        var algum = false;
        campos.forEach(function (c) {
          var marcar = unico
            ? valores[0] === "1" || valores[0] === "true" || valores[0] === c.value
            : valores.indexOf(c.value) !== -1;
          if (c.checked !== marcar) {
            c.checked = marcar;
            disparar(c);
          }
          algum = algum || marcar;
        });
        return algum;
      }
      var texto = Array.isArray(valor) ? valor.join(", ") : String(valor);
      if (campo.tagName === "SELECT") {
        var existe = Array.prototype.some.call(campo.options, function (o) {
          return o.value === texto && !o.disabled;
        });
        if (!existe) return false;
        campo.value = texto;
      } else {
        if (campo.maxLength > 0 && texto.length > campo.maxLength) texto = texto.slice(0, campo.maxLength);
        campo.value = texto;
        if (campo.value !== texto) return false; // data ou número que o campo recusou
      }
      disparar(campo);
      return true;
    }

    // ------------------------------------------------------------------
    // Marca de "preenchido pelo e-mail"
    // ------------------------------------------------------------------

    function caixaDe(campo) {
      if (marcavel(campo)) return campo.closest(".cartao-escolha, .interruptor, label") || campo;
      return campo.closest(".form-controle-wrapper") || campo;
    }

    function focavelDe(campo) {
      var caixa = caixaDe(campo);
      if (campo.hasAttribute("data-custom-date-range-start")) {
        return caixa.querySelector('[data-range-campo="inicio"]') || caixa.querySelector("[data-custom-date-range-trigger]") || campo;
      }
      if (campo.hasAttribute("data-custom-date-range-end")) {
        return caixa.querySelector('[data-range-campo="fim"]') || caixa.querySelector("[data-custom-date-range-trigger]") || campo;
      }
      return caixa.querySelector("[data-custom-select-trigger], [data-custom-date-trigger]") || campo;
    }

    function marcar(campos, sugestao) {
      var alvos = marcavel(campos[0]) ? campos.filter(function (c) { return c.checked; }) : [campos[0]];
      alvos.forEach(function (campo) {
        var caixa = caixaDe(campo);
        if (!caixa.hasAttribute("data-pe-title")) caixa.setAttribute("data-pe-title", caixa.getAttribute("title") || "");
        caixa.classList.add("is-sugerido");
        caixa.title = "Preenchido pelo e-mail" + (sugestao.trecho ? ": “" + sugestao.trecho + "”" : "") + " — confira.";
        focavelDe(campo).setAttribute("aria-description", "Preenchido pelo e-mail; confira.");
        if (marcados.indexOf(caixa) === -1) marcados.push(caixa);
      });
    }

    function desmarcar(caixa) {
      if (!caixa.classList.contains("is-sugerido")) return;
      caixa.classList.remove("is-sugerido");
      var antigo = caixa.getAttribute("data-pe-title");
      if (antigo) caixa.title = antigo;
      else caixa.removeAttribute("title");
      caixa.removeAttribute("data-pe-title");
      caixa.querySelectorAll("[aria-description]").forEach(function (f) { f.removeAttribute("aria-description"); });
      if (caixa.hasAttribute("aria-description")) caixa.removeAttribute("aria-description");
      marcados = marcados.filter(function (m) { return m !== caixa; });
    }

    // Mexeu no campo: a pessoa conferiu, a marca sai.
    function aoMexer(evento) {
      if (aplicando || !marcados.length) return;
      var alvo = evento.target;
      if (!alvo || !alvo.closest) return;
      if (alvo.form !== form && !form.contains(alvo)) return;
      var caixa = alvo.closest(".is-sugerido");
      if (caixa) desmarcar(caixa);
    }
    document.addEventListener("input", aoMexer, true);
    document.addEventListener("change", aoMexer, true);

    // ------------------------------------------------------------------
    // Aplicar as sugestões
    // ------------------------------------------------------------------

    function aplicar(campos) {
      var preenchidos = [];
      var outras = [];
      var recusados = [];
      marcados.slice().forEach(desmarcar);
      desfazer = [];
      aplicando = true;
      try {
        ordenar(Object.keys(campos)).forEach(function (nome) {
          var sugestao = campos[nome];
          var alvos = camposDe(nome);
          if (!alvos.length || bloqueado(alvos)) return;
          var item = { nome: nome, sugestao: sugestao, campos: alvos };
          if (sugestao.confianca === "B") {
            if (!mesmoValor(alvos, sugestao.valor)) outras.push(item);
            return;
          }
          if (!livre(alvos, nome)) {
            if (!mesmoValor(alvos, sugestao.valor)) outras.push(item);
            return;
          }
          guardarParaDesfazer(alvos);
          if (definir(alvos, sugestao.valor)) {
            marcar(alvos, sugestao);
            preenchidos.push(item);
          } else {
            desfazer.pop();
            recusados.push(item);
          }
        });
      } finally {
        aplicando = false;
      }
      return { preenchidos: preenchidos, outras: outras, recusados: recusados };
    }

    function usar(item, botao) {
      guardarParaDesfazer(item.campos);
      aplicando = true;
      var ok;
      try {
        ok = definir(item.campos, item.sugestao.valor);
      } finally {
        aplicando = false;
      }
      if (ok) {
        marcar(item.campos, item.sugestao);
        var linha = botao.closest("li");
        if (linha) {
          linha.textContent = "";
          linha.appendChild(el("span", "pe__chip-feito", rotulo(item) + ": " + item.sugestao.exibir + " — aplicado"));
        }
        anunciar(rotulo(item) + " preenchido com " + item.sugestao.exibir + ".", true);
      } else {
        desfazer.pop();
        anunciar("Não deu para usar esta sugestão: a opção não está na lista do campo.", true);
      }
    }

    function desfazerTudo() {
      aplicando = true;
      try {
        desfazer.slice().reverse().forEach(function (passo) {
          passo.campos.forEach(function (campo, i) {
            var anterior = passo.valores[i];
            if (marcavel(campo)) {
              if (campo.checked !== anterior) { campo.checked = anterior; disparar(campo); }
            } else if (campo.value !== anterior) {
              campo.value = anterior;
              disparar(campo);
            }
          });
        });
      } finally {
        aplicando = false;
      }
      desfazer = [];
      marcados.slice().forEach(desmarcar);
      var token = campoToken(false);
      if (token) token.value = "";
      esquecer();
      if (vinculo) vinculo.hidden = true;
      resultado.hidden = true;
      resultado.textContent = "";
      anunciar("Preenchimento desfeito. Os campos voltaram ao que eram.");
    }

    // ------------------------------------------------------------------
    // Resumo
    // ------------------------------------------------------------------

    // O rótulo que a pessoa vê na tela; na falta, o do formulário (servidor).
    function rotulo(item) {
      var campo = item.campos[0];
      var fonte = campo.id && document.querySelector('label[for="' + campo.id + '"]');
      if (!fonte && campo.closest("fieldset")) fonte = campo.closest("fieldset").querySelector("legend");
      // Grupo de caixas sem <fieldset> (temas, palestrantes): o rótulo do
      // grupo; o <label> de uma caixa só vale quando ela é o campo inteiro.
      var grupo = !fonte && marcavel(campo) && item.campos.length > 1 && campo.closest("[role=group][aria-label]");
      if (grupo) return grupo.getAttribute("aria-label");
      if (!fonte && marcavel(campo) && item.campos.length === 1) fonte = campo.closest("label");
      var texto = fonte ? fonte.textContent.replace(/\*/g, "").replace(/\s+/g, " ").trim() : "";
      return texto || item.sugestao.rotulo || item.nome;
    }

    function focar(item) {
      var alvo = item.campos.filter(function (c) { return !marcavel(c) || c.checked; })[0] || item.campos[0];
      var focavel = focavelDe(alvo);
      if (focavel.scrollIntoView) focavel.scrollIntoView({ block: "center", behavior: "smooth" });
      focavel.focus({ preventScroll: true });
    }

    // `estado` é a região viva: com o resumo aberto, ela só fala ao leitor de
    // tela (o resumo já mostra o mesmo texto).
    function anunciar(texto, soLeitor) {
      estado.classList.toggle("sr-only", Boolean(soLeitor));
      estado.textContent = texto;
    }

    function mostrarErro(texto) {
      erro.textContent = texto;
      erro.hidden = !texto;
    }

    function campoToken(criar) {
      var campo = form.elements.namedItem("email_origem");
      if (!campo && criar) {
        campo = document.createElement("input");
        campo.type = "hidden";
        campo.name = "email_origem";
        form.appendChild(campo);
      }
      return campo && campo.tagName ? campo : null;
    }

    // Vínculo com o e-mail lido: guardado na aba até o formulário ser enviado.
    function lembrar(dados) {
      try { window.sessionStorage.setItem(CHAVE, JSON.stringify(dados)); } catch (e) { /* sem storage: só a tela atual */ }
    }
    function esquecer() {
      try { window.sessionStorage.removeItem(CHAVE); } catch (e) { /* nada a limpar */ }
    }
    function lembrado() {
      try { return JSON.parse(window.sessionStorage.getItem(CHAVE) || "null"); } catch (e) { return null; }
    }

    function mostrarVinculo(assunto) {
      if (!vinculo || !vinculoTexto) return;
      vinculoTexto.textContent = "O e-mail “" + assunto + "” continua ligado a esta " + registro + ": ao salvar, " +
        (anexaOriginal ? "ele fica anexado e " : "") + "o histórico registra de onde ela veio.";
      vinculo.hidden = false;
    }

    function desligar() {
      var token = campoToken(false);
      if (token) token.value = "";
      esquecer();
      if (vinculo) vinculo.hidden = true;
      anunciar("O e-mail não fica mais ligado a esta " + registro + ".");
    }

    function descreverOrigem(dados) {
      var m = dados.mensagem || {};
      var partes = [];
      if (m.remetente) partes.push("E-mail de " + m.remetente);
      else partes.push("E-mail");
      if (m.enviado_em) partes[0] += " (" + m.enviado_em + ")";
      var texto = partes[0] + (m.assunto ? ": “" + m.assunto + "”." : ".");
      var arquivo = dados.arquivo || {};
      // PDF que não é e-mail (o ofício): sem remetente nem assunto, vale o nome do arquivo.
      var soArquivo = !m.remetente && !m.assunto && arquivo.nome;
      if (soArquivo) texto = "Arquivo “" + arquivo.nome + "”.";
      if (arquivo.token) {
        if (anexaOriginal) {
          var nomesAnexos = arquivo.anexos || [];
          var anexos = nomesAnexos.length;
          texto += " Ao salvar, " + (soArquivo ? "ele" : "o e-mail") + (anexos ? " e " + plural(anexos, "anexo dele", "anexos dele") +
            " (" + nomesAnexos.join(", ") + ")" : "") +
            " fica" + (anexos ? "m" : "") + " anexado" + (anexos ? "s" : "") + " à " + registro +
            " e o histórico registra de onde ela veio.";
        } else {
          texto += " Ao salvar, o histórico registra que a " + registro + " veio deste e-mail.";
        }
      }
      return texto;
    }

    function mostrar(dados, efeito) {
      resultado.textContent = "";
      var n = efeito.preenchidos.length;

      var titulo = el("p", "pe__resumo-titulo");
      if (n) {
        titulo.appendChild(el("b", "", plural(n, "campo preenchido", "campos preenchidos")));
        titulo.appendChild(document.createTextNode(" — confira os destacados."));
      } else {
        titulo.appendChild(el("b", "", "Nenhum campo vazio foi preenchido"));
        titulo.appendChild(document.createTextNode(efeito.outras.length ? " — veja as sugestões abaixo." : " — o e-mail não trouxe dados para esta tela."));
      }
      resultado.appendChild(titulo);
      resultado.appendChild(el("p", "pe__origem", descreverOrigem(dados)));

      // Veio da triagem da página inicial: os outros módulos a um clique.
      var outros = dados.outros_modulos || [];
      if (outros.length) {
        var troca = el("p", "pe__outros");
        troca.appendChild(document.createTextNode("Não é uma " + registro + "? Abrir este e-mail como: "));
        outros.forEach(function (o, i) {
          if (i) troca.appendChild(document.createTextNode(" · "));
          var link = el("a", "pe__outro", o.rotulo);
          link.href = o.url;
          troca.appendChild(link);
        });
        resultado.appendChild(troca);
      }

      var avisos = (dados.avisos || []).slice();
      efeito.recusados.forEach(function (item) {
        avisos.push(rotulo(item) + ": “" + item.sugestao.exibir + "” não está entre as opções do campo; escolha à mão.");
      });
      if (avisos.length || (dados.duplicados || []).length) {
        var listaAvisos = el("ul", "pe__avisos");
        listaAvisos.setAttribute("aria-label", "Avisos da leitura do e-mail");
        (dados.duplicados || []).forEach(function (d) {
          var li = el("li", "pe__aviso pe__aviso--duplicado");
          li.appendChild(document.createTextNode("Este e-mail já deu origem a "));
          var link = el("a", "", d.titulo);
          link.href = d.url;
          li.appendChild(link);
          li.appendChild(document.createTextNode(". Confira antes de salvar outra."));
          listaAvisos.appendChild(li);
        });
        avisos.forEach(function (texto) { listaAvisos.appendChild(el("li", "pe__aviso", texto)); });
        resultado.appendChild(listaAvisos);
      }

      if (efeito.outras.length) {
        var bloco = el("div", "pe__sugestoes");
        bloco.appendChild(el("p", "pe__subtitulo", "Outras sugestões do e-mail (não preenchidas):"));
        var lista = el("ul", "pe__chips");
        efeito.outras.forEach(function (item) {
          var li = el("li", "pe__chip");
          var texto = el("span", "pe__chip-texto");
          texto.appendChild(el("span", "pe__chip-rotulo", rotulo(item) + ": "));
          texto.appendChild(el("b", "", item.sugestao.exibir));
          if (item.sugestao.trecho) texto.title = "Do e-mail: “" + item.sugestao.trecho + "”";
          li.appendChild(texto);
          var botao = el("button", "pe__usar", "Usar");
          botao.type = "button";
          botao.setAttribute("aria-label", "Usar " + item.sugestao.exibir + " em " + rotulo(item));
          botao.addEventListener("click", function () { usar(item, botao); });
          li.appendChild(botao);
          lista.appendChild(li);
        });
        bloco.appendChild(lista);
        resultado.appendChild(bloco);
      }

      if (n) {
        var detalhes = el("details", "pe__lista");
        detalhes.appendChild(el("summary", "", "Ver o que foi preenchido"));
        var listaCampos = el("ul");
        efeito.preenchidos.forEach(function (item) {
          var li = el("li");
          var ir = el("button", "pe__ir", rotulo(item));
          ir.type = "button";
          ir.addEventListener("click", function () { focar(item); });
          li.appendChild(ir);
          li.appendChild(el("span", "", ": " + item.sugestao.exibir));
          listaCampos.appendChild(li);
        });
        detalhes.appendChild(listaCampos);
        resultado.appendChild(detalhes);

        var acoes = el("div", "pe__acoes");
        var botaoDesfazer = el("button", "btn--secundaria pe__desfazer", "Desfazer o preenchimento");
        botaoDesfazer.type = "button";
        botaoDesfazer.addEventListener("click", desfazerTudo);
        acoes.appendChild(botaoDesfazer);
        resultado.appendChild(acoes);
      }
      resultado.hidden = false;

      anunciar(
        (n ? plural(n, "campo preenchido", "campos preenchidos") + " — confira os destacados." : "Nenhum campo vazio foi preenchido.") +
        (avisos.length ? " " + plural(avisos.length, "aviso", "avisos") + "." : ""),
        true
      );
    }

    // ------------------------------------------------------------------
    // Envio ao servidor
    // ------------------------------------------------------------------

    function ocupado(sim) {
      bloco.classList.toggle("is-lendo", sim);
      bloco.setAttribute("aria-busy", sim ? "true" : "false");
      [entrada, botaoColar, botaoLerTexto].forEach(function (b) { if (b) b.disabled = sim; });
    }

    function csrf() {
      var campo = form.querySelector('input[name="csrfmiddlewaretoken"]');
      return campo ? campo.value : "";
    }

    function enviar(corpo, seNaoLer) {
      mostrarErro("");
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
              resposta.redirected ? "Sua sessão expirou. Entre de novo e leia o e-mail outra vez." :
              resposta.status === 403 ? "Você não tem acesso a este módulo." :
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
          var efeito = aplicar(dados.campos || {});
          var token = dados.arquivo && dados.arquivo.token;
          if (token) {
            campoToken(true).value = token;
            lembrar({ token: token, assunto: (dados.mensagem && dados.mensagem.assunto) || dados.arquivo.nome });
          }
          if (vinculo) vinculo.hidden = true;
          mostrar(dados, efeito);
          if (painelTexto && !painelTexto.hidden) alternarTexto(false);
        })
        .catch(function (falha) {
          anunciar("");
          if (seNaoLer && seNaoLer()) return;
          mostrarErro(mensagemDeFalha(falha));
        })
        .then(function () { ocupado(false); });
    }

    function lerArquivo(arquivo, seNaoLer) {
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
        enviar(dados, seNaoLer);
      }, function () {
        ocupado(false);
        anunciar("");
        mostrarErro(MSG_LEITURA);
      });
    }

    // ------------------------------------------------------------------
    // Anexos: o que não é o e-mail vai para o seletor de anexos do formulário
    // ------------------------------------------------------------------

    function aceitoComoAnexo(arquivo) {
      var aceitos = (seletorAnexos.getAttribute("accept") || "").toLowerCase().split(",")
        .map(function (t) { return t.trim(); }).filter(Boolean);
      return !aceitos.length || aceitos.indexOf(extensaoDe(arquivo)) !== -1;
    }

    var lote = { aceitos: [], recusados: [] };

    function anexar(arquivos) {
      if (!seletorAnexos || !arquivos.length) return;
      var novos = arquivos.filter(aceitoComoAnexo);
      lote.aceitos = lote.aceitos.concat(novos);
      lote.recusados = lote.recusados.concat(arquivos.filter(function (a) { return !aceitoComoAnexo(a); }));
      var aceitos = lote.aceitos;
      var recusados = lote.recusados;
      if (novos.length) {
        // O seletor soma o que chega no "change" à lista que já tinha.
        var dt = new DataTransfer();
        novos.forEach(function (a) { dt.items.add(a); });
        seletorAnexos.files = dt.files;
        seletorAnexos.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (avisoAnexados) {
        var partes = [];
        if (aceitos.length) {
          partes.push(plural(aceitos.length, "arquivo foi para", "arquivos foram para") + " os anexos e vai" +
            (aceitos.length > 1 ? "o" : "") + " junto ao salvar: " +
            aceitos.map(function (a) { return a.name; }).join(", ") + ".");
        }
        if (recusados.length) {
          partes.push("Não entra" + (recusados.length > 1 ? "m" : "") + " como anexo (tipo não aceito): " +
            recusados.map(function (a) { return a.name; }).join(", ") + ".");
        }
        avisoAnexados.textContent = partes.join(" ");
        avisoAnexados.hidden = !partes.length;
      }
      if (aceitos.length) anunciar(plural(aceitos.length, "arquivo anexado", "arquivos anexados") + ".");
    }

    function receber(lista) {
      var arquivos = Array.prototype.slice.call(lista || []);
      if (!arquivos.length) return;
      lote = { aceitos: [], recusados: [] };
      if (!seletorAnexos) {
        if (arquivos.length > 1) {
          mostrarErro("Solte um e-mail por vez.");
          return;
        }
        lerArquivo(arquivos[0]);
        return;
      }
      // O e-mail é lido; sem e-mail, o primeiro PDF (e-mail impresso ou ofício).
      var ler = arquivos.filter(function (a) { return EMAILS.indexOf(extensaoDe(a)) !== -1; })[0] ||
        arquivos.filter(function (a) { return extensaoDe(a) === ".pdf"; })[0];
      var resto = arquivos.filter(function (a) { return a !== ler; });
      if (!ler) {
        mostrarErro("");
        anexar(resto);
        return;
      }
      var pdf = extensaoDe(ler) === ".pdf";
      if (maximo && ler.size > maximo) {
        resto.unshift(ler);
        mostrarErro("");
        anexar(resto);
        return;
      }
      anexar(resto);
      lerArquivo(ler, pdf ? function () {
        // PDF que não é e-mail (um ofício escaneado, por exemplo): só anexa.
        anexar([ler]);
        return true;
      } : null);
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

    // Veio da triagem da página inicial (?email_origem=): lê o e-mail sozinha.
    var tokenAuto = bloco.getAttribute("data-pe-auto");
    if (tokenAuto) {
      var dadosAuto = new FormData();
      dadosAuto.append("token", tokenAuto);
      enviar(dadosAuto);
      if (window.history && window.history.replaceState) {
        // O token sai da URL: recarregar a página não lê de novo por cima do que a pessoa digitou.
        try { window.history.replaceState(null, "", window.location.pathname); } catch (e) { /* sem histórico */ }
      }
    }

    // Página recarregada: o vínculo volta (o servidor confere se o e-mail ainda vale).
    var tokenDaTela = campoToken(false);
    if (!tokenAuto && (!tokenDaTela || !tokenDaTela.value)) {
      var salvo = lembrado();
      if (salvo && salvo.token) {
        campoToken(true).value = salvo.token;
        mostrarVinculo(salvo.assunto || "lido antes");
      }
    }
    if (botaoDesligar) botaoDesligar.addEventListener("click", desligar);
    form.addEventListener("submit", esquecer);

    if (entrada) {
      entrada.addEventListener("change", function () {
        receber(entrada.files);
        entrada.value = ""; // o mesmo arquivo pode ser escolhido de novo
      });
    }
    if (botaoColar) {
      botaoColar.addEventListener("click", function () { alternarTexto(painelTexto.hidden); });
    }
    if (botaoLerTexto) botaoLerTexto.addEventListener("click", lerTexto);
    if (campoTexto) {
      campoTexto.addEventListener("keydown", function (evento) {
        if (evento.key === "Enter" && (evento.ctrlKey || evento.metaKey)) {
          evento.preventDefault();
          lerTexto();
        }
      });
    }

    // Arrastar e soltar em qualquer ponto da faixa. Só arquivo: texto
    // arrastado para a caixa de colar segue o comportamento normal.
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
      receber(evento.dataTransfer && evento.dataTransfer.files);
    });
  }

  document.querySelectorAll("[data-preencher-email]").forEach(iniciar);
})();
