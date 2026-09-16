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
  var aviso = dialogo.querySelector('[data-anexar-aviso]');
  var nome = dialogo.querySelector('[data-anexar-nome]');
  var proximo = dialogo.querySelector('[data-anexar-next]');
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

  function abrir(link) {
    form.reset();
    form.action = link.getAttribute('href');
    proximo.value = window.location.pathname + window.location.search;
    nome.textContent = link.getAttribute('data-anexar-nome') || 'este documento';
    var atual = link.getAttribute('data-anexar-atual') === '1';
    aviso.hidden = !atual;
    remover.hidden = !atual;
    atualizar();
    // Um menu suspenso aberto por trás não deve ficar aberto.
    var menu = link.closest('details[open]');
    if (menu) menu.removeAttribute('open');
    dialogo.showModal();
  }

  document.addEventListener('click', function (evento) {
    var link = evento.target.closest && evento.target.closest('a[data-anexar-assinado]');
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
