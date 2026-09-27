/* Modal "Baixar documentos" (components/v32/dialogo_baixar.html).

   Um botão com `data-baixar-documentos` abre o modal com os documentos do
   termo (JSON em `data-itens`), todos marcados. "Um PDF só" só vale para PDF
   com mais de um marcado.

   O envio é um POST por fetch (m122): a janela fica em "Gerando documentos…"
   com o botão desabilitado até o arquivo chegar, e só então o download
   começa e ela fecha — a conversão pode levar segundos, e antes a janela
   fechava na hora, sem retorno, e a pessoa clicava de novo. Se o servidor
   redirecionar (erro com aviso na página), a página vai para lá. Formato,
   versão e saída escolhidos ficam guardados no navegador (localStorage) e
   voltam na próxima abertura. */
(function () {
  'use strict';

  var dialogo = document.querySelector('[data-baixar-dialogo]');
  if (!dialogo || typeof dialogo.showModal !== 'function') return;

  var form = dialogo.querySelector('[data-baixar-form]');
  var lista = dialogo.querySelector('[data-baixar-lista]');
  var sub = dialogo.querySelector('[data-baixar-sub]');
  var todos = dialogo.querySelector('[data-baixar-todos]');
  var enviar = dialogo.querySelector('[data-baixar-enviar]');
  var proximo = dialogo.querySelector('[data-baixar-next]');
  var unico = form.querySelector('input[name="saida"][value="unico"]');
  var separados = form.querySelector('input[name="saida"][value="separados"]');
  var grupoVersao = dialogo.querySelector('[data-baixar-versao]');

  var CHAVE_ESCOLHAS = 'baixar-documentos:escolhas';
  var enviando = false;

  function lerEscolhas() {
    try { return JSON.parse(window.localStorage.getItem(CHAVE_ESCOLHAS) || '{}') || {}; } catch (e) { return {}; }
  }
  function guardarEscolhas() {
    var escolhas = {};
    ['formato', 'versao', 'saida'].forEach(function (nome) {
      var marcado = form.querySelector('input[name="' + nome + '"]:checked');
      if (marcado) escolhas[nome] = marcado.value;
    });
    try { window.localStorage.setItem(CHAVE_ESCOLHAS, JSON.stringify(escolhas)); } catch (e) { /* sem armazenamento: vale só nesta visita */ }
  }
  function restaurarEscolhas() {
    var escolhas = lerEscolhas();
    ['formato', 'versao', 'saida'].forEach(function (nome) {
      var opcao = escolhas[nome] && form.querySelector('input[name="' + nome + '"][value="' + escolhas[nome] + '"]');
      if (opcao && !opcao.disabled) opcao.checked = true;
    });
  }

  function marcados() {
    return lista.querySelectorAll('input[name="itens"]:checked').length;
  }

  function formato() {
    return form.querySelector('input[name="formato"]:checked').value;
  }

  // Há assinado entre os marcados? Só então a escolha de versão faz sentido.
  function assinadosMarcados() {
    return lista.querySelectorAll('input[name="itens"][data-assinado]:checked').length;
  }

  function atualizar() {
    var n = marcados();
    var total = lista.querySelectorAll('input[name="itens"]').length;
    var pdf = formato() === 'pdf';
    grupoVersao.hidden = !pdf || assinadosMarcados() === 0;
    unico.disabled = !pdf || n < 2;
    unico.closest('label').classList.toggle('bx-seg__op--off', unico.disabled);
    if (unico.disabled && unico.checked) separados.checked = true;
    enviar.disabled = n === 0;
    todos.textContent = n === total ? 'Desmarcar todos' : 'Marcar todos';
  }

  function linha(item) {
    var rotulo = document.createElement('label');
    rotulo.className = 'bx-item';
    var caixa = document.createElement('input');
    caixa.type = 'checkbox';
    caixa.name = 'itens';
    caixa.value = item.valor;
    caixa.checked = true;
    caixa.className = 'sr-only';
    if (item.assinado) caixa.setAttribute('data-assinado', '');
    var marca = document.createElement('span');
    marca.className = 'bx-item__marca';
    marca.setAttribute('aria-hidden', 'true');
    var texto = document.createElement('span');
    texto.className = 'bx-item__txt';
    var nome = document.createElement('b');
    nome.textContent = item.nome;
    texto.appendChild(nome);
    if (item.detalhe) {
      var detalhe = document.createElement('small');
      detalhe.textContent = item.detalhe;
      texto.appendChild(detalhe);
    }
    rotulo.appendChild(caixa);
    rotulo.appendChild(marca);
    rotulo.appendChild(texto);
    if (item.estado) {
      var estado = document.createElement('span');
      estado.className = 'bx-item__estado';
      estado.textContent = item.estado;
      rotulo.appendChild(estado);
    }
    return rotulo;
  }

  function abrir(botao) {
    var itens = [];
    try { itens = JSON.parse(botao.getAttribute('data-itens') || '[]'); } catch (e) { itens = []; }
    form.reset();
    form.action = botao.getAttribute('data-url');
    proximo.value = window.location.pathname + window.location.search;
    sub.textContent = botao.getAttribute('data-titulo') || '';
    // Só PDF (Coffee Break): sem a escolha de formato.
    var soPdf = botao.hasAttribute('data-baixar-so-pdf');
    var grupoFormato = form.querySelector('input[name="formato"]').closest('fieldset');
    if (grupoFormato) grupoFormato.hidden = soPdf;
    if (soPdf) form.querySelector('input[name="formato"][value="pdf"]').checked = true;
    lista.innerHTML = '';
    itens.forEach(function (item) { lista.appendChild(linha(item)); });
    if (!soPdf) restaurarEscolhas();
    gerando(false);
    var menu = botao.closest('[data-menu-corpo]');
    if (menu) {
      menu.hidden = true;
      var gatilho = menu.parentElement && menu.parentElement.querySelector('[data-menu-gatilho]');
      if (gatilho) gatilho.setAttribute('aria-expanded', 'false');
    }
    atualizar();
    dialogo.showModal();
  }

  document.addEventListener('click', function (evento) {
    var botao = evento.target.closest && evento.target.closest('[data-baixar-documentos]');
    if (!botao) return;
    evento.preventDefault();
    abrir(botao);
  });

  form.addEventListener('change', atualizar);
  todos.addEventListener('click', function () {
    var marcar = marcados() !== lista.querySelectorAll('input[name="itens"]').length;
    lista.querySelectorAll('input[name="itens"]').forEach(function (caixa) { caixa.checked = marcar; });
    atualizar();
  });
  dialogo.querySelectorAll('[data-baixar-fechar]').forEach(function (botao) {
    botao.addEventListener('click', function () { dialogo.close(); });
  });
  dialogo.addEventListener('click', function (evento) {
    if (evento.target === dialogo) dialogo.close();
  });
  form.addEventListener('change', guardarEscolhas);

  /* ---- Envio com retorno visual (m122) ---------------------------------- */
  var rotuloEnviar = enviar.innerHTML;
  var aviso = dialogo.querySelector('[data-baixar-aviso]');
  var erro = dialogo.querySelector('[data-baixar-erro]');
  function gerando(ligado) {
    enviando = ligado;
    enviar.disabled = ligado || marcados() === 0;
    enviar.setAttribute('aria-busy', ligado ? 'true' : 'false');
    enviar.innerHTML = ligado ? '<span class="bx-espera" aria-hidden="true"></span>Gerando documentos…' : rotuloEnviar;
    if (aviso) aviso.hidden = !ligado;
    if (ligado && erro) erro.hidden = true;
  }

  function nomeDoArquivo(resposta) {
    var cabecalho = resposta.headers.get('Content-Disposition') || '';
    var utf8 = /filename\*=UTF-8''([^;]+)/i.exec(cabecalho);
    if (utf8) { try { return decodeURIComponent(utf8[1]); } catch (e) { /* segue para o nome simples */ } }
    var simples = /filename="?([^";]+)"?/i.exec(cabecalho);
    return simples ? simples[1] : 'documentos';
  }

  function baixarBlob(blob, nome) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
  }

  function falhou(mensagem) {
    gerando(false);
    if (erro) { erro.textContent = mensagem; erro.hidden = false; }
    else window.alert(mensagem);
  }

  // O arquivo chega pelo fetch e vira download; a janela espera por ele.
  form.addEventListener('submit', function (evento) {
    evento.preventDefault();
    if (enviando || marcados() === 0) return;
    if (!window.fetch || !window.URL || !URL.createObjectURL) { form.submit(); setTimeout(function () { dialogo.close(); }, 150); return; }
    guardarEscolhas();
    gerando(true);
    fetch(form.action, { method: 'POST', credentials: 'same-origin', body: new FormData(form), headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (resposta) {
        // Redirecionou: é um aviso do servidor (erro, permissão) na página de volta.
        if (resposta.redirected) { window.location.href = resposta.url; return null; }
        if (!resposta.ok) return Promise.reject(resposta.status);
        if (!/attachment|inline/i.test(resposta.headers.get('Content-Disposition') || '')) { window.location.href = resposta.url; return null; }
        return resposta.blob().then(function (blob) { baixarBlob(blob, nomeDoArquivo(resposta)); return true; });
      })
      .then(function (baixou) {
        if (baixou === null) return;
        gerando(false);
        dialogo.close();
      })
      .catch(function (codigo) {
        falhou(codigo === 403 ? 'Você não tem permissão para baixar estes documentos.' : 'Não foi possível gerar os documentos. Tente de novo.');
      });
  });
})();
