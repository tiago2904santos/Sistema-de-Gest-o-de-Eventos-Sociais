/* Modelo de um tipo de documento (m057): os textos do modelo editados direto
   na folha montada (templates/documentos/editor/modelo.html).

   Cada texto do modelo é um trecho [data-mod-bloco] editável; os campos
   automáticos são etiquetas [data-mod-campo] que não se editam por dentro.
   Ao salvar, cada trecho alterado vira texto de novo — a etiqueta volta a ser
   `{campo}`, a quebra de linha `\n` — e vai ao servidor, que recusa campo que
   o texto não aceita. Nada sai daqui para serviço externo. */
(function () {
  'use strict';

  var raiz = document.querySelector('[data-mdl]');
  if (!raiz || raiz.dataset.mdlLigado) return;
  raiz.dataset.mdlLigado = '1';

  var quadro = raiz.querySelector('[data-mdl-folha]');
  var infoEl = document.getElementById('mdl-blocos');
  var info = infoEl ? JSON.parse(infoEl.textContent) : {};
  var estado = raiz.getAttribute('data-mdl-estado') || '';
  var salvo = raiz.querySelector('[data-mdl-salvo-texto]');
  var gravar = raiz.querySelector('[data-mdl-gravar]');
  var inserir = raiz.querySelector('[data-mdl-inserir]');
  var focoTexto = raiz.querySelector('[data-mdl-foco-texto]');
  var botaoPadrao = raiz.querySelector('[data-mdl-padrao]');
  var formPadrao = raiz.querySelector('[data-mdl-form-padrao]');
  var erro = raiz.querySelector('[data-mdl-erro]');
  var erroTexto = raiz.querySelector('[data-mdl-erro-texto]');
  var tokenCsrf = document.querySelector('input[name="csrfmiddlewaretoken"]');
  var inicial = {};
  var atual = null;
  var faixa = null;  // a última seleção dentro do trecho em foco
  var alterado = false;

  function doc() { return quadro && quadro.contentDocument; }

  function trechos() {
    var lista = Array.prototype.slice.call(raiz.querySelectorAll('[data-mod-bloco]'));
    var d = doc();
    if (d) lista = Array.prototype.slice.call(d.querySelectorAll('[data-mod-bloco]')).concat(lista);
    return lista;
  }

  function doBloco(chave) {
    return trechos().filter(function (el) { return el.getAttribute('data-mod-bloco') === chave; });
  }

  // ---- Texto <-> trecho ------------------------------------------------------
  function serializar(no) {
    var saida = '';
    Array.prototype.forEach.call(no.childNodes, function (filho) {
      if (filho.nodeType === 3) {
        saida += filho.nodeValue.replace(/ /g, ' ').replace(/[​-‍﻿]/g, '');
      } else if (filho.nodeType === 1) {
        var campo = filho.getAttribute('data-mod-campo');
        if (campo) saida += '{' + campo + '}';
        else if (filho.tagName === 'BR') saida += '\n';
        else if (filho.classList.contains('mod-indicador')) return;
        else if (/^(DIV|P)$/.test(filho.tagName)) {
          // Parágrafo que o navegador criou no Enter: vira quebra de linha.
          if (saida && saida.slice(-1) !== '\n') saida += '\n';
          saida += serializar(filho);
        } else saida += serializar(filho);
      }
    });
    return saida;
  }

  function normalizar(texto) {
    return texto.split('\n').map(function (l) { return l.replace(/\s+$/, ''); }).join('\n').trim();
  }

  function textoDo(chave) {
    var el = doBloco(chave)[0];
    return el ? normalizar(serializar(el)) : null;
  }

  function mudados() {
    var saida = {};
    Object.keys(inicial).forEach(function (chave) {
      var texto = textoDo(chave);
      if (texto !== null && texto !== inicial[chave]) saida[chave] = texto;
    });
    return saida;
  }

  function marcar(texto, tipo) {
    if (!salvo) return;
    salvo.textContent = texto;
    salvo.parentNode.setAttribute('data-estado', tipo || '');
  }

  function recemSalvo() {
    try {
      var chave = 'modelo-salvo:' + window.location.pathname;
      var quando = Number(window.sessionStorage.getItem(chave));
      window.sessionStorage.removeItem(chave);
      if (quando && Date.now() - quando < 60000) {
        var h = new Date(quando);
        return 'Salvo às ' + ('0' + h.getHours()).slice(-2) + ':' + ('0' + h.getMinutes()).slice(-2);
      }
    } catch (e) { /* sem storage */ }
    return '';
  }
  var avisoSalvo = recemSalvo();
  if (avisoSalvo) marcar(avisoSalvo, 'ok');

  function atualizarSituacao() {
    var n = Object.keys(mudados()).length;
    alterado = n > 0;
    if (!n && avisoSalvo) { marcar(avisoSalvo, 'ok'); return; }
    if (n) avisoSalvo = '';
    marcar(n ? (n === 1 ? '1 texto alterado, não salvo' : n + ' textos alterados, não salvos') : 'Sem alterações', n ? 'andamento' : '');
  }

  function mostrarErro(texto, recarregar) {
    if (!erro) { window.alert(texto); return; }
    erroTexto.textContent = texto;
    if (recarregar) {
      var botao = document.createElement('button');
      botao.type = 'button';
      botao.className = 'btn--secundaria';
      botao.textContent = 'Recarregar a página';
      botao.style.marginLeft = '8px';
      botao.addEventListener('click', function () { alterado = false; window.location.reload(); });
      erroTexto.appendChild(botao);
    }
    erro.hidden = false;
    erro.scrollIntoView({ block: 'nearest' });
  }

  // ---- Foco e barra de ferramentas ------------------------------------------
  function trechoDe(no) {
    while (no && no.nodeType !== 1) no = no.parentNode;
    return no && no.closest ? no.closest('[data-mod-bloco]') : null;
  }

  function focar(el) {
    atual = el;
    var chave = el && el.getAttribute('data-mod-bloco');
    var dados = chave ? info[chave] || {} : null;
    if (inserir) {
      inserir.innerHTML = '';
      var primeira = document.createElement('option');
      primeira.value = '';
      var campos = dados ? dados.campos || [] : [];
      primeira.textContent = !dados ? 'Inserir campo' : (campos.length ? 'Inserir campo' : 'Este texto não tem campos');
      inserir.appendChild(primeira);
      campos.forEach(function (c) {
        var opcao = document.createElement('option');
        opcao.value = c.chave;
        opcao.textContent = c.nome + ' — ' + c.rotulo;
        inserir.appendChild(opcao);
      });
      inserir.disabled = !campos.length;
    }
    if (focoTexto) {
      focoTexto.innerHTML = '';
      if (!dados) {
        focoTexto.textContent = 'Clique num texto do modelo (contorno azul) para editar.';
      } else {
        var b = document.createElement('b');
        b.textContent = dados.rotulo;
        focoTexto.appendChild(b);
        focoTexto.appendChild(document.createTextNode(
          dados.alterado ? ' · personalizado' + (dados.quando ? ' em ' + dados.quando : '') + (dados.quem ? ' por ' + dados.quem : '') : ' · padrão do sistema'));
      }
      focoTexto.title = focoTexto.textContent;
    }
    if (botaoPadrao) botaoPadrao.hidden = !(dados && dados.alterado);
  }

  function guardarSelecao(d) {
    var sel = d.getSelection();
    if (!sel || !sel.rangeCount) return;
    var faixaAtual = sel.getRangeAt(0);
    var el = trechoDe(faixaAtual.startContainer);
    if (el) { faixa = faixaAtual.cloneRange(); if (el !== atual) focar(el); }
  }

  function inserirCampo(chave) {
    var el = atual;
    if (!el) return;
    var dados = info[el.getAttribute('data-mod-bloco')] || {};
    var campo = (dados.campos || []).filter(function (c) { return c.chave === chave; })[0];
    if (!campo) return;
    var d = el.ownerDocument;
    var etiqueta = d.createElement('span');
    etiqueta.className = 'mod-chip' + (campo.negrito ? ' mod-chip--negrito' : '');
    etiqueta.setAttribute('contenteditable', 'false');
    etiqueta.setAttribute('data-mod-campo', campo.chave);
    etiqueta.title = campo.rotulo;
    etiqueta.textContent = campo.nome;
    var r = faixa && el.contains(faixa.startContainer) && el.contains(faixa.endContainer) ? faixa : null;
    if (!r) { r = d.createRange(); r.selectNodeContents(el); r.collapse(false); }
    r.deleteContents();
    r.insertNode(etiqueta);
    r.setStartAfter(etiqueta);
    r.collapse(true);
    el.focus();
    var sel = d.getSelection();
    sel.removeAllRanges();
    sel.addRange(r);
    faixa = r.cloneRange();
    aoEditar(el);
  }

  if (inserir) {
    inserir.addEventListener('change', function () {
      if (inserir.value) inserirCampo(inserir.value);
      inserir.value = '';
    });
  }

  raiz.querySelectorAll('[data-mdl-cmd]').forEach(function (botao) {
    botao.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
    botao.addEventListener('click', function () {
      var d = atual ? atual.ownerDocument : doc();
      if (!d) return;
      d.execCommand(botao.getAttribute('data-mdl-cmd'), false, null);
      if (atual) aoEditar(atual);
    });
  });

  // ---- Voltar ao padrão -------------------------------------------------------
  function voltarAoPadrao(chave) {
    var dados = info[chave];
    if (!dados || !dados.alterado || !formPadrao) return;
    var aviso = '“' + dados.rotulo + '” volta ao texto padrão do sistema, para os próximos documentos.';
    if (alterado) aviso += '\n\nAs alterações ainda não salvas nesta tela se perdem.';
    if (!window.confirm(aviso)) return;
    alterado = false;
    formPadrao.querySelector('[name="padrao"]').value = chave;
    formPadrao.submit();
  }

  if (botaoPadrao) {
    botaoPadrao.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
    botaoPadrao.addEventListener('click', function () { if (atual) voltarAoPadrao(atual.getAttribute('data-mod-bloco')); });
  }

  // O indicador de texto personalizado, ao lado de cada trecho da folha.
  function posicionarIndicadores() {
    var d = doc();
    if (!d || !d.body) return;
    Array.prototype.forEach.call(d.querySelectorAll('.mod-indicador'), function (b) { b.parentNode.removeChild(b); });
    var janela = d.defaultView;
    var corpo = d.body;
    var posicionado = janela.getComputedStyle(corpo).position !== 'static';
    var base = posicionado ? corpo.getBoundingClientRect() : { left: -janela.scrollX, top: -janela.scrollY };
    var vistos = {};
    Array.prototype.forEach.call(d.querySelectorAll('[data-mod-bloco][data-mod-alterado]'), function (el) {
      var chave = el.getAttribute('data-mod-bloco');
      if (vistos[chave]) return;
      vistos[chave] = true;
      // Na margem do parágrafo: o bloco pode começar no meio da linha
      // (depois de um dado), e o indicador não pode cobrir o texto.
      var linha = el.getClientRects()[0] || el.getBoundingClientRect();
      var paragrafo = el.closest('p, div, td, th, li, h1, h2, h3, h4') || el;
      var caixa = { left: paragrafo.getBoundingClientRect().left, top: linha.top, height: linha.height };
      var botao = d.createElement('button');
      botao.type = 'button';
      botao.className = 'mod-indicador';
      botao.setAttribute('contenteditable', 'false');
      var rotulo = (info[chave] || {}).rotulo || chave;
      botao.title = '“' + rotulo + '” está personalizado. Clique para voltar ao padrão do sistema.';
      botao.setAttribute('aria-label', botao.title);
      botao.style.left = Math.max(caixa.left - base.left - 20, 0) + 'px';
      botao.style.top = (caixa.top - base.top + Math.max((caixa.height - 16) / 2, 0)) + 'px';
      botao.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
      botao.addEventListener('click', function () { voltarAoPadrao(chave); });
      corpo.appendChild(botao);
    });
  }

  // ---- A folha ----------------------------------------------------------------
  function ajustarAltura() {
    var d = doc();
    if (!d || !d.documentElement) return;
    quadro.style.height = Math.max(d.documentElement.scrollHeight, 400) + 'px';
  }

  function aoEditar(el) {
    // O mesmo texto em mais de um lugar da folha acompanha o que se escreve.
    var chave = el.getAttribute('data-mod-bloco');
    doBloco(chave).forEach(function (outro) { if (outro !== el) outro.innerHTML = el.innerHTML; });
    if (erro) erro.hidden = true;
    atualizarSituacao();
    ajustarAltura();
    posicionarIndicadores();
  }

  function ligarDocumento(d) {
    d.addEventListener('input', function (ev) {
      var el = trechoDe(ev.target);
      if (el) aoEditar(el);
    });
    d.addEventListener('focusin', function (ev) {
      var el = trechoDe(ev.target);
      if (el) focar(el);
    });
    d.addEventListener('selectionchange', function () { guardarSelecao(d); });
    d.addEventListener('keydown', function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') {
        ev.preventDefault();
        salvar();
        return;
      }
      if (ev.key === 'Enter' && trechoDe(ev.target)) {
        // Quebra de linha dentro do texto (o modelo é texto com quebras).
        ev.preventDefault();
        if (!d.execCommand('insertLineBreak')) d.execCommand('insertHTML', false, '<br>');
      }
    });
    // Colar e arrastar: só o texto, sem o estilo de outro programa.
    d.addEventListener('paste', function (ev) {
      if (!trechoDe(ev.target)) return;
      ev.preventDefault();
      var texto = ev.clipboardData ? ev.clipboardData.getData('text/plain') : '';
      if (texto) d.execCommand('insertText', false, texto);
    });
    d.addEventListener('drop', function (ev) { if (trechoDe(ev.target)) ev.preventDefault(); });
  }

  function lerInicial() {
    trechos().forEach(function (el) {
      var chave = el.getAttribute('data-mod-bloco');
      if (!(chave in inicial)) inicial[chave] = normalizar(serializar(el));
    });
  }

  var folhaLigada = false;
  function ligarFolha() {
    var d = doc();
    if (!d || folhaLigada || !d.body) return;
    folhaLigada = true;
    try { d.execCommand('styleWithCSS', false, false); } catch (e) { /* navegador sem o comando */ }
    ligarDocumento(d);
    lerInicial();
    ajustarAltura();
    posicionarIndicadores();
    // As imagens (brasão) mudam a altura depois de carregar.
    Array.prototype.forEach.call(d.images, function (img) {
      img.addEventListener('load', function () { ajustarAltura(); posicionarIndicadores(); });
    });
  }

  ligarDocumento(document);
  lerInicial();
  if (quadro) {
    quadro.addEventListener('load', ligarFolha);
    if (quadro.contentDocument && quadro.contentDocument.readyState === 'complete' && quadro.contentDocument.body &&
        quadro.contentDocument.querySelector('[data-mod-bloco]')) ligarFolha();
    window.addEventListener('resize', function () { ajustarAltura(); posicionarIndicadores(); });
  }

  // ---- Gravar ---------------------------------------------------------------
  function salvar() {
    var blocos = mudados();
    if (!Object.keys(blocos).length) { marcar('Nada mudou no modelo.'); return; }
    if (gravar) gravar.disabled = true;
    marcar('Salvando…', 'andamento');
    fetch(raiz.getAttribute('data-mdl-salvar'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': tokenCsrf ? tokenCsrf.value : '',
      },
      body: JSON.stringify({ estado: estado, blocos: blocos }),
    }).then(function (resposta) {
      return resposta.json().catch(function () { return { ok: false }; });
    }).then(function (dados) {
      if (gravar) gravar.disabled = false;
      if (!dados.ok) {
        marcar(dados.conflito ? 'Alterado por outra pessoa' : 'Não foi possível salvar', 'erro');
        mostrarErro(dados.mensagem || 'Não foi possível salvar.', dados.conflito);
        return;
      }
      estado = String(dados.estado || '');
      alterado = false;
      // Recarrega para a folha, os indicadores e o histórico mostrarem o que foi gravado.
      try { window.sessionStorage.setItem('modelo-salvo:' + window.location.pathname, String(Date.now())); } catch (e) { /* sem storage */ }
      window.location.reload();
    }).catch(function () {
      if (gravar) gravar.disabled = false;
      marcar('Sem conexão: nada foi salvo.', 'erro');
    });
  }

  if (gravar) gravar.addEventListener('click', salvar);

  window.addEventListener('beforeunload', function (ev) {
    if (alterado) { ev.preventDefault(); ev.returnValue = ''; }
  });
  raiz.querySelectorAll('[data-mdl-form]').forEach(function (form) {
    form.addEventListener('submit', function (ev) {
      if (alterado && !window.confirm('As alterações ainda não salvas nesta tela se perdem. Continuar?')) { ev.preventDefault(); return; }
      alterado = false;
    });
  });
})();
