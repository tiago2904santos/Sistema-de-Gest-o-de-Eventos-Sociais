/* Modal "Baixar documentos" (components/v32/dialogo_baixar.html).

   Um botão com `data-baixar-documentos` abre o modal com os documentos do
   termo (JSON em `data-itens`), todos marcados. "Um PDF só" só vale para PDF
   com mais de um marcado. O envio é um POST comum que devolve o arquivo. */
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
  // O arquivo chega como download e a página fica; o modal fecha sozinho.
  form.addEventListener('submit', function (evento) {
    if (marcados() === 0) { evento.preventDefault(); return; }
    setTimeout(function () { dialogo.close(); }, 150);
  });
})();
