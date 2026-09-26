/* Editor completo do documento (m057): liga a barra de formatação à folha do
   iframe e grava a versão editada.

   A folha marca cada região editável com comentários (<!--ed:corpo--> ...
   <!--/ed:corpo-->); o elemento que os contém fica editável (contenteditable)
   e, ao gravar, o HTML de dentro dele vai ao servidor, que o passa pela lista
   branca antes de guardar. Nada sai daqui para serviço externo. */
(function () {
  'use strict';

  var raiz = document.querySelector('[data-dcp]');
  if (!raiz || raiz.dataset.dcpLigado) return;
  raiz.dataset.dcpLigado = '1';

  var quadro = raiz.querySelector('[data-dcp-folha]');
  var editavel = raiz.hasAttribute('data-dcp-editavel');
  var estado = raiz.getAttribute('data-dcp-estado') || '';
  var salvo = raiz.querySelector('[data-dcp-salvo-texto]');
  var gravar = raiz.querySelector('[data-dcp-gravar]');
  var alterado = false;
  var tokenCsrf = document.querySelector('input[name="csrfmiddlewaretoken"]');

  function doc() { return quadro && quadro.contentDocument; }

  function marcar(texto, erro) {
    if (!salvo) return;
    salvo.textContent = texto;
    salvo.parentNode.setAttribute('data-estado', erro ? 'erro' : (alterado ? 'andamento' : ''));
  }

  function regioes() {
    var d = doc();
    if (!d) return [];
    var achadas = [];
    var andar = d.createTreeWalker(d.body, NodeFilter.SHOW_COMMENT, null);
    var no;
    while ((no = andar.nextNode())) {
      var m = /^ed:(\w+)$/.exec(no.nodeValue.trim());
      if (m && no.parentNode) achadas.push({ nome: m[1], el: no.parentNode });
    }
    return achadas;
  }

  function ajustarAltura() {
    var d = doc();
    if (!d || !d.documentElement) return;
    quadro.style.height = Math.max(d.documentElement.scrollHeight, 400) + 'px';
  }

  function ligarFolha() {
    var d = doc();
    if (!d) return;
    ajustarAltura();
    if (!editavel) return;
    regioes().forEach(function (r) {
      r.el.setAttribute('contenteditable', 'true');
      r.el.setAttribute('data-ed-regiao', r.nome);
      r.el.setAttribute('spellcheck', 'true');
    });
    try { d.execCommand('styleWithCSS', false, false); } catch (e) { /* navegador sem o comando */ }
    d.addEventListener('input', function () {
      alterado = true;
      marcar('Alterações não salvas');
      ajustarAltura();
    });
    d.addEventListener('keydown', function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') {
        ev.preventDefault();
        salvar();
      }
    });
    // Colagem de fora: só o texto, para não trazer o estilo de outro programa.
    d.addEventListener('paste', function (ev) {
      var dados = ev.clipboardData;
      if (!dados) return;
      var html = dados.getData('text/html');
      if (!html) return;
      ev.preventDefault();
      d.execCommand('insertText', false, dados.getData('text/plain'));
    });
  }

  if (quadro) {
    quadro.addEventListener('load', ligarFolha);
    if (quadro.contentDocument && quadro.contentDocument.readyState === 'complete') ligarFolha();
    window.addEventListener('resize', ajustarAltura);
  }

  function comando(nome, valor) {
    var d = doc();
    if (!d) return;
    d.execCommand(nome, false, valor || null);
    alterado = true;
    marcar('Alterações não salvas');
    ajustarAltura();
  }

  raiz.querySelectorAll('[data-dcp-cmd]').forEach(function (botao) {
    // mousedown sem foco: a seleção na folha continua onde estava.
    botao.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
    botao.addEventListener('click', function () { comando(botao.getAttribute('data-dcp-cmd')); });
  });

  var estilo = raiz.querySelector('[data-dcp-bloco]');
  if (estilo) {
    estilo.addEventListener('change', function () {
      if (estilo.value) comando('formatBlock', '<' + estilo.value + '>');
      estilo.value = '';
    });
  }

  // ---- Tabelas --------------------------------------------------------------
  function celulaAtual() {
    var d = doc();
    var sel = d && d.getSelection();
    var no = sel && sel.anchorNode;
    while (no && no.nodeType !== 1) no = no.parentNode;
    return no && no.closest ? no.closest('td, th') : null;
  }

  function tabela(acao) {
    var d = doc();
    if (!d) return;
    if (acao === 'inserir') {
      var linhas = parseInt(window.prompt('Quantas linhas?', '3'), 10);
      var colunas = parseInt(window.prompt('Quantas colunas?', '3'), 10);
      if (!(linhas > 0 && colunas > 0 && linhas <= 50 && colunas <= 12)) return;
      var html = '<table class="doc-tabela-livre"><tbody>';
      for (var i = 0; i < linhas; i++) {
        html += '<tr>';
        for (var j = 0; j < colunas; j++) html += '<td><br></td>';
        html += '</tr>';
      }
      comando('insertHTML', html + '</tbody></table><p><br></p>');
      return;
    }
    var celula = celulaAtual();
    if (!celula) { window.alert('Ponha o cursor numa célula da tabela.'); return; }
    var linha = celula.parentNode;
    var indice = Array.prototype.indexOf.call(linha.children, celula);
    var tab = celula.closest('table');
    if (acao === 'linha') {
      var nova = linha.cloneNode(true);
      Array.prototype.forEach.call(nova.children, function (c) { c.innerHTML = '<br>'; });
      linha.parentNode.insertBefore(nova, linha.nextSibling);
    } else if (acao === 'coluna') {
      tab.querySelectorAll('tr').forEach(function (tr) {
        var ref = tr.children[indice];
        var novaCelula = d.createElement(ref ? ref.tagName.toLowerCase() : 'td');
        novaCelula.innerHTML = '<br>';
        tr.insertBefore(novaCelula, ref ? ref.nextSibling : null);
      });
    } else if (acao === 'sem-linha') {
      linha.parentNode.removeChild(linha);
      if (!tab.querySelector('tr')) tab.parentNode.removeChild(tab);
    } else if (acao === 'sem-coluna') {
      tab.querySelectorAll('tr').forEach(function (tr) {
        if (tr.children[indice]) tr.removeChild(tr.children[indice]);
      });
      if (!tab.querySelector('td, th')) tab.parentNode.removeChild(tab);
    }
    alterado = true;
    marcar('Alterações não salvas');
    ajustarAltura();
  }

  raiz.querySelectorAll('[data-dcp-tabela]').forEach(function (botao) {
    botao.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
    botao.addEventListener('click', function () { tabela(botao.getAttribute('data-dcp-tabela')); });
  });

  var quebra = raiz.querySelector('[data-dcp-quebra]');
  if (quebra) {
    quebra.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
    quebra.addEventListener('click', function () {
      // A quebra entra no cursor: o que vem depois começa em página nova
      // (`doc-quebra`, no CSS dos documentos de Viagens e do Coffee Break).
      comando('insertHTML', '<div class="doc-quebra"></div>');
    });
  }

  // ---- Gravar ---------------------------------------------------------------
  function conteudo(el) {
    var copia = el.cloneNode(true);
    copia.removeAttribute('contenteditable');
    return copia.innerHTML;
  }

  function salvar() {
    if (!editavel) return;
    var corpo = { estado: estado, regioes: {} };
    regioes().forEach(function (r) { corpo.regioes[r.nome] = conteudo(r.el); });
    if (gravar) gravar.disabled = true;
    marcar('Salvando…');
    fetch(raiz.getAttribute('data-dcp-salvar'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': tokenCsrf ? tokenCsrf.value : '',
      },
      body: JSON.stringify(corpo),
    }).then(function (resposta) {
      return resposta.json().catch(function () { return { ok: false }; });
    }).then(function (dados) {
      if (gravar) gravar.disabled = false;
      if (!dados.ok) {
        marcar(dados.mensagem || 'Não foi possível salvar.', true);
        if (dados.mensagem) window.alert(dados.mensagem);
        return;
      }
      estado = String(dados.estado);
      alterado = false;
      // Recarrega para o histórico e a folha mostrarem o que foi gravado
      // (já sanitizado).
      window.location.reload();
    }).catch(function () {
      if (gravar) gravar.disabled = false;
      marcar('Sem conexão: nada foi salvo.', true);
    });
  }

  if (gravar) gravar.addEventListener('click', salvar);

  window.addEventListener('beforeunload', function (ev) {
    if (alterado) { ev.preventDefault(); ev.returnValue = ''; }
  });
  raiz.querySelectorAll('form').forEach(function (form) {
    form.addEventListener('submit', function () { alterado = false; });
  });
})();
