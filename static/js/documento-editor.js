/* Editor documental da prévia A4 (documentos/editor/embutido.html), no desenho
   de um editor de texto, embutido no fim do formulário de cada documento.

   A folha vive num iframe da mesma origem; os trechos que nascem de um campo
   real levam `data-doc-campo`. Trechos de texto se escrevem na própria folha
   (contenteditable). Os demais — escolha, data, alternância, busca de
   servidores — abrem num balão junto ao trecho clicado: HTML que a API
   devolve, montado com os componentes globais. Tudo grava por PATCH (JSON,
   com o token CSRF e a versão que foi lida); texto tem uma espera curta de
   digitação e grava ao sair do trecho, escolhas gravam na hora. A resposta da
   gravação já traz a folha remontada: troca-se o conteúdo dela no lugar, sem
   recarregar o iframe. 409 avisa que outra pessoa mexeu e pede para
   recarregar.

   Por cima disso, o que um editor de texto tem: o estado da gravação na barra
   de título ("Salvando…", "Tudo salvo"), desfazer/refazer do documento (cada
   gravação vira um passo, que se desfaz regravando o valor anterior) e o modo
   que mostra os pontos onde se pode inserir quebra de página. As páginas e o
   zoom são do palco (`viagens-documento.js`).

   Um editor por vez: `DocEditorMontar(raiz, palco)` liga o editor do `.de-app`
   dado e devolve `desmontar`, que tira os ouvintes da página e o balão. O
   balão vai para o <body>: o editor mora dentro do <form> do cadastro, e o
   balão é um formulário. */
(function () {
  'use strict';

  function montarEditor(raiz, palcoDoEditor) {
  var editor = raiz.matches('[data-de-editor]') ? raiz : null;
  var quadro = raiz.querySelector('.dc-folha');
  if (!editor || !quadro) return null;

  // Ouvintes na página (document/window), tirados ao desmontar.
  var ouvintes = [];
  function ouvir(alvo, tipo, funcao) { alvo.addEventListener(tipo, funcao); ouvintes.push([alvo, tipo, funcao]); }

  var painel = editor.querySelector('[data-de-painel]');
  if (painel) document.body.appendChild(painel);
  // Três espécies de trecho editável, cada uma com a sua rota: campo (nasce
  // de um campo real), bloco (parágrafo do modelo) e quebra (ponto de quebra).
  var urls = {
    campo: editor.getAttribute('data-de-url'),
    bloco: editor.getAttribute('data-de-url-bloco'),
    quebra: editor.getAttribute('data-de-url-quebra')
  };
  var versao = editor.getAttribute('data-de-versao') || '';
  /* Origens do registro principal do documento (o ofício, o termo, a ordem de
     serviço...): usam a versão da página. As demais guardam a própria. */
  var principais = (editor.getAttribute('data-de-principais') || 'oficio marcacao').split(' ');
  var tokenCsrf = document.querySelector('input[name="csrfmiddlewaretoken"]');
  var salvo = raiz.querySelector('[data-de-salvo]');
  var salvoTexto = raiz.querySelector('[data-de-salvo-texto]');
  /* Espera de digitação antes de gravar. Curta porque gravar já não recarrega
     a folha: o documento se atualiza no lugar, então errar para menos custa
     pouco. Sair do campo grava na hora, sem esperar o relógio. */
  var ESPERA_DIGITACAO = 400;

  var chaveAberta = null;
  var especieAberta = 'campo';
  var objetoAberto = '';
  var origemAberta = '';
  var temporizador = null;
  var enviando = false;
  var reenviar = false;

  /* Trecho de um registro entre vários (a linha de um servidor) leva o id
     dele: vai na URL, e é parte do endereço do trecho na folha. */
  function url(especie, chave, objeto) {
    var base = (urls[especie] || '').replace('CHAVE', encodeURIComponent(chave));
    if (!objeto) return base;
    // A URL pode já trazer a variante do documento (?v=): o id vai junto.
    return base + (base.indexOf('?') < 0 ? '?' : '&') + 'objeto=' + encodeURIComponent(objeto);
  }

  /* Versões. Cada origem tem a sua: o ofício (e os marcadores dele) usa a
     versão da página; o cadastro de um servidor, a prestação e a configuração
     guardam a própria, lida quando o trecho é aberto ou gravado pela primeira
     vez. O controle de concorrência compara com a do registro que muda. */
  var versoes = {};
  function daOficio(origem) { return !origem || principais.indexOf(origem) >= 0; }
  function chaveDeVersao(chave, objeto) { return chave + ':' + (objeto || ''); }
  function guardarVersao(origem, chave, objeto, valor) {
    if (valor === undefined || valor === null) return;
    if (daOficio(origem)) versao = valor || versao;
    else versoes[chaveDeVersao(chave, objeto)] = valor;
  }
  /* Avisa a página que um campo foi gravado pelo documento: o formulário em
     volta (o do cadastro) acompanha os valores e a versão nova, para salvar
     depois sem desfazer o que se editou na folha. */
  function avisarGravado(origem, valores, novaVersao) {
    editor.dispatchEvent(new CustomEvent('documento:gravado', {
      bubbles: true, detail: { origem: origem, valores: valores || {}, versao: novaVersao }
    }));
  }
  function versaoPara(origem, chave, objeto) {
    if (daOficio(origem)) return Promise.resolve(versao);
    var k = chaveDeVersao(chave, objeto);
    if (versoes[k] !== undefined) return Promise.resolve(versoes[k]);
    return fetch(url('campo', chave, objeto), { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (dados) { versoes[k] = dados.versao; return dados.versao; })
      .catch(function () { return undefined; });
  }
  function documentoDaFolha() { return quadro.contentDocument; }
  function palco() { return palcoDoEditor || null; }
  function cabecalhos(comCorpo) {
    var h = { 'X-CSRFToken': tokenCsrf ? tokenCsrf.value : '', 'X-Requested-With': 'XMLHttpRequest' };
    if (comCorpo) h['Content-Type'] = 'application/json';
    return h;
  }

  function atributoDa(especie) { return especie === 'bloco' ? 'data-doc-bloco' : especie === 'quebra' ? 'data-doc-quebra' : 'data-doc-campo'; }
  function seletorDo(chave, especie, objeto) {
    var seletor = '[' + atributoDa(especie) + '="' + chave + '"]';
    return objeto ? seletor + '[data-doc-objeto="' + objeto + '"]' : seletor;
  }
  function trechoNaFolha(chave, especie, objeto) {
    var doc = documentoDaFolha();
    return doc && chave ? doc.querySelector(seletorDo(chave, especie, objeto)) : null;
  }

  function marcar(chave, especie, objeto) {
    var doc = documentoDaFolha();
    if (!doc) return;
    doc.querySelectorAll('.doc-editavel--ativo').forEach(function (el) { el.classList.remove('doc-editavel--ativo'); });
    if (!chave) return;
    doc.querySelectorAll(seletorDo(chave, especie, objeto)).forEach(function (el) { el.classList.add('doc-editavel--ativo'); });
  }

  /* ---- Estado da gravação ---------------------------------------------
     Na barra de título, sempre; no balão, quando há um aberto. */
  function indicar(texto, classe) {
    if (!salvo) return;
    salvo.setAttribute('data-estado', classe || 'andamento');
    if (salvoTexto) salvoTexto.textContent = classe === 'ok' ? 'Tudo salvo' : (texto || 'Tudo salvo');
  }

  function status(texto, classe) {
    indicar(texto, classe);
    var el = painel ? painel.querySelector('[data-de-status]') : null;
    if (!el) return;
    el.textContent = texto || '';
    el.className = 'de-status' + (classe ? ' de-status--' + classe : '');
  }

  function limparErros() {
    painel.querySelectorAll('.de-erro').forEach(function (el) { el.remove(); });
    painel.querySelectorAll('.is-invalid').forEach(function (el) { el.classList.remove('is-invalid'); });
    var gerais = painel.querySelector('[data-de-erros]');
    if (gerais) gerais.innerHTML = '';
  }

  function mostrarErros(porNome, gerais) {
    limparErros();
    Object.keys(porNome || {}).forEach(function (nome) {
      var controle = painel.querySelector('[name="' + nome + '"]');
      var campo = controle && controle.closest('.form-campo');
      if (!campo) return;
      var wrapper = campo.querySelector('.form-controle-wrapper') || controle;
      wrapper.classList.add('is-invalid');
      porNome[nome].forEach(function (mensagem) {
        var p = document.createElement('p');
        p.className = 'form-erro de-erro';
        p.textContent = mensagem;
        campo.appendChild(p);
      });
    });
    var caixa = painel.querySelector('[data-de-erros]');
    if (caixa) (gerais || []).forEach(function (mensagem) {
      var p = document.createElement('p');
      p.className = 'form-erro de-erro';
      p.textContent = mensagem;
      caixa.appendChild(p);
    });
  }

  // Partes que só fazem sentido com certo valor de outra parte
  // (data-de-quando="custeio=OUTRA_INSTITUICAO").
  function condicionais(form) {
    form.querySelectorAll('[data-de-quando]').forEach(function (parte) {
      var regra = parte.getAttribute('data-de-quando').split('=');
      var controle = form.querySelector('[name="' + regra[0] + '"]');
      parte.hidden = !controle || controle.value !== regra[1];
    });
  }

  function valoresDe(form) {
    var dados = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.tagName === 'BUTTON' || el.name === 'csrfmiddlewaretoken') return;
      if (el.type === 'checkbox') {
        // Interruptor (value="on") é booleano; caixas com valor próprio são
        // uma escolha múltipla e viram lista.
        if (el.value === 'on') { dados[el.name] = el.checked; return; }
        dados[el.name] = dados[el.name] || [];
        if (el.checked) dados[el.name].push(el.value);
        return;
      }
      if (el.type === 'radio') { if (el.checked) dados[el.name] = el.value; return; }
      dados[el.name] = el.value;
    });
    return dados;
  }

  function recarregarFolha() {
    try { quadro.contentWindow.location.reload(); } catch (e) { quadro.src = quadro.src; }
  }

  /* A folha já vem remontada na resposta da gravação: troca-se só o conteúdo
     do <body>, sem recarregar o iframe. Isso evita a ida ao servidor e o
     piscar da página, mantém o <head> (o CSS não é rebuscado, não há salto de
     estilo) e preserva os handlers de clique, que vivem no documento e não
     nos elementos. Depois, o palco repagina. Sem a folha na resposta,
     recarrega como antes. */
  function aplicarFolha(html) {
    var doc = documentoDaFolha();
    if (!doc || !doc.body || !html) { recarregarFolha(); return; }
    var nova;
    try { nova = new DOMParser().parseFromString(html, 'text/html'); } catch (e) { recarregarFolha(); return; }
    if (!nova || !nova.body) { recarregarFolha(); return; }
    doc.body.className = nova.body.className;
    doc.body.innerHTML = nova.body.innerHTML;
    marcar(chaveAberta, especieAberta, objetoAberto);
    if (palco()) palco().atualizar();
    posicionar();
  }

  /* ---- Desfazer e refazer ------------------------------------------------
     Cada gravação bem-sucedida vira um passo: o que o trecho (ou o campo do
     balão) tinha antes e o que ficou. Gravações seguidas do mesmo trecho,
     sem sair dele, formam um passo só — desfazer volta ao texto de antes de
     começar a escrever, não letra a letra. Desfazer regrava o valor anterior
     pelo mesmo caminho da edição (mesma validação, mesma trilha de auditoria). */

  var passosDesfazer = [];
  var passosRefazer = [];
  var botaoDesfazer = raiz.querySelector('[data-de-desfazer]');
  var botaoRefazer = raiz.querySelector('[data-de-refazer]');
  var sessoes = 0;
  var sessaoPainel = null;

  function atualizarBotoes() {
    if (botaoDesfazer) botaoDesfazer.disabled = !passosDesfazer.length;
    if (botaoRefazer) botaoRefazer.disabled = !passosRefazer.length;
  }

  function iguais(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function registrar(passo) {
    if (iguais(passo.antes, passo.depois)) return;
    var topo = passosDesfazer[passosDesfazer.length - 1];
    if (topo && passo.sessao && topo.sessao === passo.sessao) {
      topo.depois = passo.depois;
      if (iguais(topo.antes, topo.depois)) passosDesfazer.pop();
    } else {
      passosDesfazer.push(passo);
      if (passosDesfazer.length > 50) passosDesfazer.shift();
    }
    passosRefazer = [];
    atualizarBotoes();
  }

  function regravar(passo, valores) {
    status('Salvando…', 'andamento');
    if (passo.especie === 'quebra') {
      return fetch(url('quebra', passo.chave), { method: 'PATCH', credentials: 'same-origin', headers: cabecalhos(true), body: JSON.stringify({ ativa: valores.ativa }) })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
        .then(function (dados) { aplicarFolha(dados && dados.folha); status('Salvo', 'ok'); return true; })
        .catch(function () { status('Não foi possível desfazer.', 'erro'); return false; });
    }
    if (passo.especie === 'bloco') delete versaoDeBloco[passo.chave];
    var pedirVersao = passo.especie === 'bloco' ? versaoDoBloco(passo.chave) : versaoPara(passo.origem, passo.chave, passo.objeto);
    return pedirVersao.then(function (versaoAtual) {
      return fetch(url(passo.especie, passo.chave, passo.objeto), {
        method: 'PATCH', credentials: 'same-origin', headers: cabecalhos(true),
        body: JSON.stringify({ versao: versaoAtual, valores: valores })
      });
    }).then(function (resposta) {
      return resposta.json().then(function (dados) { return { codigo: resposta.status, dados: dados }; },
                                  function () { return { codigo: resposta.status, dados: {} }; });
    }).then(function (res) {
      if (res.codigo !== 200) {
        status(res.codigo === 409 ? (res.dados.mensagem || 'O documento mudou em outro lugar.') : 'Não foi possível desfazer.', 'erro');
        return false;
      }
      if (passo.especie === 'bloco') versaoDeBloco[passo.chave] = res.dados.versao;
      else { guardarVersao(passo.origem, passo.chave, passo.objeto, res.dados.versao); avisarGravado(passo.origem, valores, res.dados.versao); }
      aplicarFolha(res.dados.folha);
      status('Salvo', 'ok');
      // O balão aberto no mesmo campo mostraria o valor velho: reabre.
      if (chaveAberta === passo.chave && objetoAberto === (passo.objeto || '')) abrir(passo.chave, especieAberta, null, false, objetoAberto, origemAberta);
      return true;
    }).catch(function () { status('Não foi possível desfazer.', 'erro'); return false; });
  }

  function desfazer() {
    var passo = passosDesfazer.pop();
    atualizarBotoes();
    if (!passo) return;
    regravar(passo, passo.antes).then(function (ok) {
      if (ok) passosRefazer.push(passo); else passosDesfazer.push(passo);
      atualizarBotoes();
    });
  }

  function refazer() {
    var passo = passosRefazer.pop();
    atualizarBotoes();
    if (!passo) return;
    regravar(passo, passo.depois).then(function (ok) {
      if (ok) passosDesfazer.push(passo); else passosRefazer.push(passo);
      atualizarBotoes();
    });
  }

  if (botaoDesfazer) botaoDesfazer.addEventListener('click', desfazer);
  if (botaoRefazer) botaoRefazer.addEventListener('click', refazer);

  // Ctrl+Z / Ctrl+Y desfazem o documento quando o cursor não está num texto
  // (dentro de um texto, o navegador desfaz a digitação, como sempre).
  function atalhoDesfazer(evento) {
    if (!(evento.ctrlKey || evento.metaKey)) return false;
    var alvo = evento.target;
    if (alvo && (alvo.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(alvo.tagName))) return false;
    var tecla = (evento.key || '').toLowerCase();
    if (tecla === 'z' && !evento.shiftKey) { evento.preventDefault(); desfazer(); return true; }
    if (tecla === 'y' || (tecla === 'z' && evento.shiftKey)) { evento.preventDefault(); refazer(); return true; }
    return false;
  }
  ouvir(document, 'keydown', atalhoDesfazer);

  /* ---- Digitar na própria folha -------------------------------------
     Trechos de texto saem da folha como `contenteditable`: escreve-se neles
     como num editor de texto. O que se digita já está na tela, então gravar
     não remonta a folha — remontar tiraria o cursor do lugar. A folha da
     resposta só é aplicada quando a edição veio de um controle (escolha,
     alternância, seleção), que muda partes do documento que não estão sob o
     cursor. */

  var temporizadorTexto = null;
  var digitando = null;        // elemento sendo escrito agora
  var versaoDeBloco = {};      // versão por bloco, para o controle de concorrência
  var sessaoDoTrecho = new WeakMap();

  function alvoDigitavel(el) { return el && el.closest ? el.closest('[data-doc-digitavel]') : null; }

  function textoDoTrecho(el) {
    // <br> e <div> viram quebra de linha; o resto é o texto como está na tela.
    var caixa = document.createElement('div');
    caixa.innerHTML = el.innerHTML.replace(/<br\s*\/?>/gi, '\n').replace(/<\/div>/gi, '\n')
      // Parágrafos (o texto da justificativa, a contextualização do plano)
      // viram linha em branco entre eles, como o texto é guardado.
      .replace(/<\/p>\s*(?=<p)/gi, '\n\n');
    return (caixa.textContent || '').replace(/ /g, ' ').replace(/\n+$/, '');
  }

  function enderecoDoTrecho(el) {
    if (el.hasAttribute('data-doc-bloco')) {
      return { especie: 'bloco', chave: el.getAttribute('data-doc-bloco') };
    }
    return {
      especie: 'campo', chave: el.getAttribute('data-doc-campo'), parte: el.getAttribute('data-doc-parte'),
      objeto: el.getAttribute('data-doc-objeto') || '', origem: el.getAttribute('data-doc-origem') || 'oficio'
    };
  }

  function valoresDoTrecho(onde, texto) {
    var valores = {};
    if (onde.especie === 'bloco') valores.conteudo = texto;
    else valores[onde.parte] = texto;
    return valores;
  }

  function marcarEstado(el, texto, classe) {
    el.setAttribute('data-doc-estado', classe || '');
    indicar(texto, classe);
  }

  // O bloco guarda a versão do override, não a do objeto: busca-se uma vez,
  // ao entrar no trecho, e depois a resposta da gravação a mantém em dia.
  function versaoDoBloco(chave) {
    if (versaoDeBloco[chave] !== undefined) return Promise.resolve(versaoDeBloco[chave]);
    return fetch(url('bloco', chave), { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (dados) { versaoDeBloco[chave] = dados.versao; return dados.versao; })
      .catch(function () { return undefined; });
  }

  function gravarTrecho(el) {
    var onde = enderecoDoTrecho(el);
    var texto = textoDoTrecho(el);
    var valores = valoresDoTrecho(onde, texto);
    var sessao = sessaoDoTrecho.get(el);
    var pedirVersao = onde.especie === 'bloco' ? versaoDoBloco(onde.chave) : versaoPara(onde.origem, onde.chave, onde.objeto);
    marcarEstado(el, 'Salvando…', 'andamento');
    return pedirVersao.then(function (versaoAtual) {
      return fetch(url(onde.especie, onde.chave, onde.objeto), {
        method: 'PATCH', credentials: 'same-origin', headers: cabecalhos(true),
        body: JSON.stringify({ versao: versaoAtual, valores: valores })
      });
    }).then(function (resposta) {
      return resposta.json().then(function (dados) { return { codigo: resposta.status, dados: dados }; },
                                  function () { return { codigo: resposta.status, dados: {} }; });
    }).then(function (res) {
      if (res.codigo === 200) {
        if (onde.especie === 'bloco') versaoDeBloco[onde.chave] = res.dados.versao;
        else { guardarVersao(onde.origem, onde.chave, onde.objeto, res.dados.versao); avisarGravado(onde.origem, valores, res.dados.versao); }
        marcarEstado(el, 'Salvo', 'ok');
        if (sessao) registrar({ especie: onde.especie, chave: onde.chave, objeto: onde.objeto, origem: onde.origem, antes: sessao.antes, depois: valores, sessao: sessao.id });
        // O domínio pode normalizar o que foi gravado (o motivo vai para caixa
        // de título, o protocolo ganha máscara). Só se ajusta o texto na tela
        // quando ninguém está com o cursor ali — mexer sob o cursor o perderia.
        if (el !== digitando) conciliarTrecho(el, onde, res.dados.folha);
      } else if (res.codigo === 409) {
        marcarEstado(el, res.dados.mensagem || 'O documento mudou em outro lugar.', 'erro');
        oferecerRecarga();
      } else {
        var erros = res.dados.erros && res.dados.erros[onde.parte];
        marcarEstado(el, (erros && erros[0]) || res.dados.mensagem || 'Não foi possível salvar este trecho.', 'erro');
      }
    }).catch(function () { marcarEstado(el, 'Não foi possível salvar este trecho.', 'erro'); });
  }

  // Traz da folha recém-montada o texto canônico deste mesmo trecho.
  function conciliarTrecho(el, onde, folha) {
    if (!folha) return;
    var nova;
    try { nova = new DOMParser().parseFromString(folha, 'text/html'); } catch (e) { return; }
    var equivalente = nova && nova.querySelector(seletorDo(onde.chave, onde.especie, onde.objeto));
    if (equivalente && equivalente.innerHTML !== el.innerHTML) el.innerHTML = equivalente.innerHTML;
  }

  function ligarDigitacao(doc) {
    // Entrar num trecho abre uma sessão de escrita: o que ele tinha agora é o
    // "antes" do passo que o desfazer vai restaurar.
    doc.addEventListener('focusin', function (evento) {
      var el = alvoDigitavel(evento.target);
      if (!el) return;
      if (chaveAberta) fechar();
      sessaoDoTrecho.set(el, { id: ++sessoes, antes: valoresDoTrecho(enderecoDoTrecho(el), textoDoTrecho(el)) });
    });
    doc.addEventListener('input', function (evento) {
      var el = alvoDigitavel(evento.target);
      if (!el) return;
      digitando = el;
      marcarEstado(el, 'Alterações não salvas…', 'andamento');
      clearTimeout(temporizadorTexto);
      temporizadorTexto = setTimeout(function () { temporizadorTexto = null; gravarTrecho(el); }, ESPERA_DIGITACAO);
    });
    // Sair do trecho grava na hora o que ainda não foi — e, se o cursor saiu
    // da escrita, repagina (o texto pode ter crescido além da página).
    doc.addEventListener('focusout', function (evento) {
      var el = alvoDigitavel(evento.target);
      if (!el) return;
      if (digitando === el) digitando = null;
      setTimeout(function () { if (!alvoDigitavel(doc.activeElement) && palco()) palco().atualizar(); }, 0);
      if (!temporizadorTexto) return;
      clearTimeout(temporizadorTexto);
      temporizadorTexto = null;
      gravarTrecho(el);
    });
    doc.addEventListener('keydown', function (evento) {
      var el = alvoDigitavel(evento.target);
      if (!el) { atalhoDesfazer(evento); return; }
      // Num trecho de uma linha, Enter encerra a edição em vez de quebrar.
      if (evento.key === 'Enter' && el.getAttribute('data-doc-digitavel') !== 'varias') {
        evento.preventDefault();
        el.blur();
      }
    });
    // Colar entra como texto puro, mesmo onde plaintext-only não vale.
    doc.addEventListener('paste', function (evento) {
      var el = alvoDigitavel(evento.target);
      if (!el || !evento.clipboardData) return;
      evento.preventDefault();
      var texto = evento.clipboardData.getData('text/plain');
      if (doc.defaultView && doc.defaultView.getSelection) {
        var selecao = doc.defaultView.getSelection();
        if (selecao && selecao.rangeCount) {
          var faixa = selecao.getRangeAt(0);
          faixa.deleteContents();
          faixa.insertNode(doc.createTextNode(texto));
          selecao.collapseToEnd();
        }
      }
      el.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }

  /* ---- Balão do campo ---------------------------------------------------- */

  function salvar(form) {
    if (enviando) { reenviar = true; return; }
    clearTimeout(temporizador);
    enviando = true;
    status('Salvando…', 'andamento');
    var valores = valoresDe(form);
    var especie = form.getAttribute('data-de-especie') === 'bloco' ? 'bloco' : 'campo';
    var origem = form.getAttribute('data-de-origem') || 'oficio';
    var objeto = form.getAttribute('data-de-objeto') || '';
    var chave = chaveAberta;
    var sessao = sessaoPainel;
    var versaoAtual = especie === 'bloco' ? Promise.resolve(versao) : versaoPara(origem, chave, objeto);
    versaoAtual.then(function (v) {
      return fetch(form.getAttribute('action'), {
        method: 'PATCH',
        credentials: 'same-origin',
        headers: cabecalhos(true),
        body: JSON.stringify({ versao: v, valores: valores })
      });
    }).then(function (resposta) {
      return resposta.json().then(function (dados) { return { codigo: resposta.status, dados: dados }; }, function () { return { codigo: resposta.status, dados: {} }; });
    }).then(function (res) {
      enviando = false;
      if (res.codigo === 200) {
        if (especie === 'bloco') versao = res.dados.versao || versao;
        else { guardarVersao(origem, chave, objeto, res.dados.versao); avisarGravado(origem, valores, res.dados.versao); }
        limparErros();
        status(res.dados.avisos && res.dados.avisos.length ? 'Salvo. O ofício ainda tem pendências em outros campos.' : 'Salvo', 'ok');
        if (sessao) registrar({ especie: especie, chave: chave, objeto: objeto, origem: origem, antes: sessao.antes, depois: valores, sessao: sessao.id });
        aplicarFolha(res.dados.folha);
        // Um bloco que acabou de ganhar (ou perder) override troca de painel:
        // aparece ou some o "Restaurar". Reabre sem mexer no texto digitado.
        if (especie === 'bloco' && !temporizador) reabrirSeMudouEstado(form, res.dados.editado);
      } else if (res.codigo === 409) {
        status(res.dados.mensagem || 'O documento mudou em outro lugar.', 'erro');
        oferecerRecarga();
      } else if (res.codigo === 400 && res.dados.erros) {
        mostrarErros(res.dados.erros, res.dados.outros_erros);
        status('Corrija o campo para salvar.', 'erro');
      } else if (res.codigo === 403) {
        status('Você não pode editar este documento.', 'erro');
      } else {
        status(res.dados.mensagem || 'Não foi possível salvar.', 'erro');
      }
      if (reenviar) { reenviar = false; salvar(form); }
    }).catch(function () {
      enviando = false;
      status('Sem conexão. Tente de novo.', 'erro');
    });
  }

  function reabrirSeMudouEstado(form, editado) {
    var tinhaRestaurar = !!form.querySelector('[data-de-restaurar]');
    if (tinhaRestaurar === !!editado) return;
    var texto = form.querySelector('textarea');
    var valor = texto ? texto.value : null;
    abrir(chaveAberta, 'bloco', function () {
      var novo = painel.querySelector('textarea');
      if (novo && valor !== null) novo.value = valor;
      status('Salvo', 'ok');
    }, true);
  }

  function restaurar(form) {
    status('Restaurando…', 'andamento');
    fetch(form.getAttribute('action'), { method: 'DELETE', credentials: 'same-origin', headers: cabecalhos(false) })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (dados) { aplicarFolha(dados && dados.folha); abrir(chaveAberta, 'bloco'); status('Salvo', 'ok'); })
      .catch(function () { status('Não foi possível restaurar.', 'erro'); });
  }

  function alternarQuebra(chave, ativa) {
    status('Salvando…', 'andamento');
    fetch(url('quebra', chave), { method: 'PATCH', credentials: 'same-origin', headers: cabecalhos(true), body: JSON.stringify({ ativa: ativa }) })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (dados) {
        registrar({ especie: 'quebra', chave: chave, antes: { ativa: !ativa }, depois: { ativa: ativa } });
        aplicarFolha(dados && dados.folha);
        status('Salvo', 'ok');
      })
      .catch(function () { status('Não foi possível alterar a quebra de página.', 'erro'); });
  }

  function oferecerRecarga() {
    var rodape = painel.querySelector('.de-campo__rodape');
    if (!rodape || rodape.querySelector('[data-de-recarregar]')) return;
    var botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'btn--secundaria';
    botao.setAttribute('data-de-recarregar', '');
    botao.textContent = 'Recarregar';
    botao.addEventListener('click', function () { window.location.reload(); });
    rodape.insertBefore(botao, rodape.querySelector('[type="submit"]'));
  }

  function ligarPainel() {
    var form = painel.querySelector('[data-de-form]');
    if (!form) return;
    condicionais(form);
    form.addEventListener('submit', function (evento) { evento.preventDefault(); salvar(form); });
    form.addEventListener('input', function (evento) {
      var alvo = evento.target;
      if (!alvo.matches('textarea, input[type="text"], input[type="search"]')) return;
      if (alvo.closest('[data-multi-pick]')) return;  // a busca do multi-pick não é valor
      clearTimeout(temporizador);
      status('Alterações não salvas…', 'andamento');
      temporizador = setTimeout(function () { temporizador = null; salvar(form); }, ESPERA_DIGITACAO);
    });
    form.addEventListener('change', function (evento) {
      var alvo = evento.target;
      condicionais(form);
      if (alvo.matches('textarea, input[type="text"], input[type="search"]')) {
        if (alvo.closest('[data-multi-pick]')) return;
        clearTimeout(temporizador);
      }
      salvar(form);
    });
    // Sair do campo com gravação pendente grava na hora: quem terminou de
    // escrever e foi para outro lugar não espera o relógio.
    form.addEventListener('focusout', function (evento) {
      if (!temporizador) return;
      if (!evento.target.matches('textarea, input[type="text"], input[type="search"]')) return;
      if (evento.target.closest('[data-multi-pick]')) return;
      clearTimeout(temporizador);
      temporizador = null;
      salvar(form);
    });
    painel.querySelectorAll('[data-de-fechar]').forEach(function (botao) { botao.addEventListener('click', fechar); });
    var botaoRestaurar = form.querySelector('[data-de-restaurar]');
    if (botaoRestaurar) botaoRestaurar.addEventListener('click', function () { restaurar(form); });
  }

  /* O balão fica logo abaixo do trecho na folha (coordenadas do iframe,
     escaladas pelo zoom), dentro da largura da janela. Sem o trecho à vista
     (campo aberto pelo menu), fica no alto da folha. */
  function posicionar() {
    if (!painel || painel.hidden) return;
    var escala = palco() ? palco().escala() : 1;
    var quadroRect = quadro.getBoundingClientRect();
    var trecho = trechoNaFolha(chaveAberta, especieAberta, objetoAberto);
    var x, y;
    if (trecho) {
      var r = trecho.getBoundingClientRect();
      x = quadroRect.left + r.left * escala;
      y = quadroRect.top + r.bottom * escala + 8;
    } else {
      x = quadroRect.left + quadroRect.width / 2 - painel.offsetWidth / 2;
      y = Math.max(quadroRect.top, 120) + 16;
    }
    var largura = painel.offsetWidth;
    var limite = document.documentElement.clientWidth - largura - 12;
    x = Math.max(12, Math.min(x, limite));
    painel.style.left = (x + window.scrollX) + 'px';
    painel.style.top = (y + window.scrollY) + 'px';
  }

  // Traz o trecho para o meio da tela antes de abrir o balão (campo escolhido
  // no menu "Campos" pode estar fora de vista).
  function trazerParaVista(trecho) {
    if (!trecho) return;
    var escala = palco() ? palco().escala() : 1;
    var r = trecho.getBoundingClientRect();
    var topoNaTela = quadro.getBoundingClientRect().top + r.top * escala;
    if (topoNaTela < 130 || topoNaTela > window.innerHeight - 200) {
      window.scrollTo({ top: window.scrollY + topoNaTela - window.innerHeight / 3 });
    }
  }

  function montar(html, manterSessao) {
    painel.innerHTML = html;
    painel.hidden = false;
    if (window.DS && window.DS.aprimorar) window.DS.aprimorar(painel);
    ligarPainel();
    var form = painel.querySelector('[data-de-form]');
    if (form && !manterSessao) sessaoPainel = { id: ++sessoes, antes: valoresDe(form) };
    posicionar();
  }

  function abrir(chave, especie, depois, manterSessao, objeto, origem) {
    especie = especie || 'campo';
    chaveAberta = chave;
    especieAberta = especie;
    objetoAberto = objeto || '';
    origemAberta = origem || 'oficio';
    marcar(chave, especie, objetoAberto);
    fetch(url(especie, chave, objetoAberto), { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (dados) {
        if (dados.versao !== undefined) {
          if (especie === 'bloco') versao = dados.versao;
          else guardarVersao(origemAberta, chave, objetoAberto, dados.versao);
        }
        montar(dados.fragmento, manterSessao);
        if (depois) depois();
        var primeiro = painel.querySelector('textarea, input[type="text"]:not([data-multi-busca]), select');
        if (primeiro && !primeiro.closest('.custom-select')) primeiro.focus({ preventScroll: true });
      })
      .catch(function (codigo) {
        // 404: o dado não existe onde deveria (servidor ainda sem prestação de
        // contas, por exemplo); 403: é da gestão.
        var mensagem = codigo === 404 ? 'Este dado ainda não existe no sistema para ser alterado aqui (por exemplo, o servidor ainda não tem prestação de contas neste ofício).'
          : codigo === 403 ? 'Só a gestão pode alterar este dado.' : 'Não foi possível abrir este trecho.';
        montar('<p class="de-campo__ajuda">' + mensagem + '</p>');
      });
  }

  function fechar() {
    clearTimeout(temporizador);
    temporizador = null;
    objetoAberto = '';
    origemAberta = '';
    chaveAberta = null;
    sessaoPainel = null;
    marcar(null);
    if (!painel) return;
    painel.hidden = true;
    painel.innerHTML = '';
  }

  // O que foi clicado (ou acionado pelo teclado) na folha: campo, bloco ou
  // ponto de quebra. Devolve false quando não é nada editável.
  function acionar(alvoInicial) {
    if (!alvoInicial || !alvoInicial.closest) return false;
    // Trecho que se digita: o clique põe o cursor no texto, e não abre balão.
    if (alvoDigitavel(alvoInicial)) return false;
    var quebra = alvoInicial.closest('[data-doc-quebra]');
    if (quebra) {
      alternarQuebra(quebra.getAttribute('data-doc-quebra'), !quebra.hasAttribute('data-doc-quebra-ativa'));
      return true;
    }
    var bloco = alvoInicial.closest('[data-doc-bloco]');
    if (bloco) { abrir(bloco.getAttribute('data-doc-bloco'), 'bloco'); return true; }
    var campo = alvoInicial.closest('[data-doc-campo]');
    if (campo) {
      abrir(campo.getAttribute('data-doc-campo'), 'campo', null, false,
            campo.getAttribute('data-doc-objeto') || '', campo.getAttribute('data-doc-origem') || 'oficio');
      return true;
    }
    return false;
  }

  /* ---- Pontos de quebra à vista ------------------------------------------
     A classe fica no <html> da folha, que não é trocado quando a folha se
     atualiza no lugar. */
  var botaoQuebras = raiz.querySelector('[data-de-alternar-quebras]');
  function aplicarModoQuebras() {
    var doc = documentoDaFolha();
    var ligado = botaoQuebras && botaoQuebras.getAttribute('aria-pressed') === 'true';
    if (doc && doc.documentElement) doc.documentElement.classList.toggle('mostrar-quebras', !!ligado);
  }
  if (botaoQuebras) botaoQuebras.addEventListener('click', function () {
    var ligado = botaoQuebras.getAttribute('aria-pressed') !== 'true';
    botaoQuebras.setAttribute('aria-pressed', ligado ? 'true' : 'false');
    aplicarModoQuebras();
  });

  function ligarFolha() {
    var doc = documentoDaFolha();
    if (!doc) return;
    doc.addEventListener('click', function (evento) {
      if (acionar(evento.target)) { evento.preventDefault(); return; }
      // Clicar fora de um trecho, na folha, fecha o balão — como no Docs.
      if (chaveAberta && !alvoDigitavel(evento.target)) fechar();
    });
    doc.addEventListener('keydown', function (evento) {
      if (evento.key === 'Escape' && chaveAberta) { fechar(); return; }
      if (evento.key !== 'Enter' && evento.key !== ' ') return;
      if (acionar(evento.target)) evento.preventDefault();
    });
    ligarDigitacao(doc);
    marcar(chaveAberta, especieAberta, objetoAberto);
    aplicarModoQuebras();
  }

  quadro.addEventListener('load', ligarFolha);
  if (quadro.contentDocument && quadro.contentDocument.readyState === 'complete' && quadro.contentDocument.body && quadro.contentDocument.body.children.length) ligarFolha();

  // Menu "Campos": abre o balão do campo junto ao trecho dele na folha.
  ouvir(document, 'click', function (evento) {
    var item = evento.target.closest('[data-de-abrir]');
    if (!item || !raiz.contains(item)) return;
    var chave = item.getAttribute('data-de-abrir');
    var especie = item.getAttribute('data-de-especie') || 'campo';
    trazerParaVista(trechoNaFolha(chave, especie));
    abrir(chave, especie, null, false, "", item.getAttribute("data-de-origem") || "oficio");
  });

  // Clicar fora do balão (e fora de um menu) fecha; Escape também.
  ouvir(document, 'mousedown', function (evento) {
    if (!chaveAberta || !painel || painel.hidden) return;
    var alvo = evento.target;
    if (painel.contains(alvo) || alvo.closest('[data-de-abrir], [data-menu], [data-de-menu], [data-de-desfazer], [data-de-refazer]')) return;
    fechar();
  });
  ouvir(document, 'keydown', function (evento) {
    if (evento.key === 'Escape' && chaveAberta) fechar();
  });
  ouvir(window, 'resize', posicionar);
  ouvir(window, 'scroll', posicionar);
  raiz.querySelectorAll('[data-de-zoom], [data-de-zoom-menos], [data-de-zoom-mais]').forEach(function (el) {
    el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'click', function () { setTimeout(posicionar, 0); });
  });

  return {
    desmontar: function () {
      fechar();
      ouvintes.forEach(function (o) { o[0].removeEventListener(o[1], o[2]); });
      ouvintes = [];
      if (painel && painel.parentNode) painel.parentNode.removeChild(painel);
    }
  };
  }

  window.DocEditorMontar = montarEditor;
})();
