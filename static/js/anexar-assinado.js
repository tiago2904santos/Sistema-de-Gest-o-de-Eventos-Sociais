/* Modal "Anexar documento assinado" (components/v32/dialogo_assinado.html).

   Liga, por delegação, todo link com `data-anexar-assinado`: o clique abre o
   modal em vez de navegar. O formulário posta no endereço do link e leva a
   página atual em `next`, para a view voltar para cá. O botão de envio só
   habilita com um PDF escolhido. */
(function () {
  'use strict';

  var dialogo = document.querySelector('[data-anexar-dialogo]');
  if (!dialogo || typeof dialogo.showModal !== 'function') return;

  var form = dialogo.querySelector('[data-anexar-form]');
  var campo = dialogo.querySelector('[data-anexar-arquivo]');
  var rotulo = dialogo.querySelector('[data-anexar-rotulo]');
  var quadro = dialogo.querySelector('[data-anexar-quadro]');
  var limpar = dialogo.querySelector('[data-anexar-limpar]');
  var erro = dialogo.querySelector('[data-anexar-erro]');
  var enviar = dialogo.querySelector('[data-anexar-enviar]');
  var remover = dialogo.querySelector('[data-anexar-remover]');
  var nome = dialogo.querySelector('[data-anexar-nome]');
  var proximo = dialogo.querySelector('[data-anexar-next]');
  var alvos = dialogo.querySelector('[data-anexar-alvos]');
  var alvosLista = dialogo.querySelector('[data-anexar-alvos-lista]');
  var VAZIO = 'Nenhum documento escolhido';

  function mostrarErro(texto) {
    erro.textContent = texto || '';
    erro.hidden = !texto;
  }

  function atualizar() {
    var arquivo = campo.files && campo.files[0];
    mostrarErro('');
    if (!arquivo) {
      rotulo.textContent = VAZIO;
      quadro.classList.remove('an-arquivo--escolhido');
      limpar.hidden = true;
      enviar.disabled = true;
      return;
    }
    rotulo.textContent = arquivo.name;
    quadro.classList.add('an-arquivo--escolhido');
    limpar.hidden = false;
    var pdf = /\.pdf$/i.test(arquivo.name) || arquivo.type === 'application/pdf';
    if (!pdf) mostrarErro('Escolha um arquivo PDF.');
    enviar.disabled = !pdf;
  }

  // Aponta o formulário para um documento: endereço, nome e se dá para remover o assinado.
  function escolher(alvo) {
    form.action = alvo.url;
    nome.textContent = alvo.nome || 'este documento';
    remover.hidden = !alvo.atual;
  }

  // Várias opções: um seletor, com a primeira disponível marcada.
  function montarAlvos(opcoes) {
    alvosLista.innerHTML = '';
    alvos.hidden = opcoes.length < 2;
    alvosLista.style.setProperty('--colunas', String(Math.min(opcoes.length, 3)));
    var marcada = false;
    opcoes.forEach(function (opcao, i) {
      var rotulo = document.createElement('label');
      var radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'anexar_alvo';
      radio.value = String(i);
      radio.disabled = !opcao.url;
      var texto = document.createElement('span');
      texto.textContent = opcao.nome;
      texto.title = opcao.nome;
      if (!opcao.url) {
        rotulo.classList.add('bx-seg__op--off');
        rotulo.title = 'Gere o PDF deste termo primeiro';
      }
      if (opcao.url && !marcada) { radio.checked = true; marcada = true; escolher(opcao); }
      radio.addEventListener('change', function () { escolher(opcao); });
      rotulo.appendChild(radio);
      rotulo.appendChild(texto);
      alvosLista.appendChild(rotulo);
    });
  }

  function abrir(link) {
    form.reset();
    proximo.value = window.location.pathname + window.location.search;
    var opcoes = null;
    try { opcoes = JSON.parse(link.getAttribute('data-anexar-opcoes') || 'null'); } catch (e) { opcoes = null; }
    if (opcoes && opcoes.length) {
      montarAlvos(opcoes);
    } else {
      alvos.hidden = true;
      alvosLista.innerHTML = '';
      escolher({
        url: link.getAttribute('href'),
        nome: link.getAttribute('data-anexar-nome'),
        atual: link.getAttribute('data-anexar-atual') === '1'
      });
    }
    atualizar();
    var corpo = link.closest('[data-menu-corpo]');
    if (corpo) {
      corpo.hidden = true;
      var gatilho = corpo.parentElement && corpo.parentElement.querySelector('[data-menu-gatilho]');
      if (gatilho) gatilho.setAttribute('aria-expanded', 'false');
    }
    // Um menu suspenso aberto por trás não deve ficar aberto.
    var menu = link.closest('details[open]');
    if (menu) menu.removeAttribute('open');
    dialogo.showModal();
  }

  document.addEventListener('click', function (evento) {
    var link = evento.target.closest && evento.target.closest('[data-anexar-assinado]');
    if (!link || evento.defaultPrevented || evento.button !== 0 || evento.ctrlKey || evento.metaKey || evento.shiftKey) return;
    evento.preventDefault();
    abrir(link);
  });

  campo.addEventListener('change', atualizar);
  limpar.addEventListener('click', function () {
    campo.value = '';
    atualizar();
  });
  dialogo.querySelectorAll('[data-anexar-fechar]').forEach(function (botao) {
    botao.addEventListener('click', function () { dialogo.close(); });
  });
  // Clique no véu fecha.
  dialogo.addEventListener('click', function (evento) {
    if (evento.target === dialogo) dialogo.close();
  });
  form.addEventListener('submit', function (evento) {
    var botao = evento.submitter;
    if (botao === remover) {
      if (!window.confirm('Remover a versão assinada? O PDF gerado volta a valer.')) evento.preventDefault();
      return;
    }
    if (enviar.disabled) { evento.preventDefault(); return; }
    enviar.disabled = true;
    enviar.textContent = 'Enviando…';
  });
})();
