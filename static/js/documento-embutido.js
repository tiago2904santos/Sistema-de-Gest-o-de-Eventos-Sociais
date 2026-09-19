/* O editor de documento no fim dos formulários (visualizador inline).

   Cada documento do cadastro tem um lugar `[data-de-embutir="<url>"]`, em
   geral dentro de um cartão <details>. Abrir o cartão busca o editor daquele
   documento (HTML de `documentos:editor_embutido`) e o liga: palco
   (`viagens-documento.js`) e edição (`documento-editor.js`). Um editor por
   vez: abrir outro cartão fecha o anterior e desmonta o editor dele. Lugar
   fora de cartão abre sozinho.

   O endereço com `#<id do cartão>` (o atalho das listas) abre aquele cartão.
   O PDF para imprimir sai por um formulário montado no <body>
   (`data-de-pdf`): o editor mora dentro do formulário do cadastro. */
(function () {
  'use strict';

  if (window.DocEmbutido) return;

  var atual = null;

  function desmontar() {
    if (!atual) return;
    if (atual.editor) atual.editor.desmontar();
    if (atual.palco) atual.palco.desmontar();
    atual.alvo.innerHTML = '';
    atual = null;
  }

  function carregar(alvo) {
    if (atual && atual.alvo === alvo) return;
    desmontar();
    var instancia = { alvo: alvo, palco: null, editor: null };
    atual = instancia;
    alvo.innerHTML = '<p class="de-carregando">Carregando o documento…</p>';
    fetch(alvo.getAttribute('data-de-embutir'), { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
      .then(function (html) {
        if (atual !== instancia) return;  // outro cartão foi aberto no meio do caminho
        alvo.innerHTML = html;
        var raiz = alvo.querySelector('.de-app');
        if (!raiz) return;
        if (window.DocPalcoMontar) instancia.palco = window.DocPalcoMontar(raiz);
        if (window.DocEditorMontar) instancia.editor = window.DocEditorMontar(raiz, instancia.palco);
      })
      .catch(function (codigo) {
        if (atual !== instancia) return;
        alvo.innerHTML = '<p class="de-carregando">' + (codigo === 403 ? 'Sem permissão para ver este documento.' : 'Não foi possível abrir o documento.') + '</p>';
      });
  }

  function cartaoDe(alvo) { return alvo.closest('details'); }

  function ligar(alvo) {
    if (alvo.hasAttribute('data-de-ligado')) return;
    alvo.setAttribute('data-de-ligado', '');
    var cartao = cartaoDe(alvo);
    if (!cartao) { carregar(alvo); return; }
    cartao.addEventListener('toggle', function () {
      if (cartao.open) {
        // Um editor por vez: os outros cartões com editor fecham.
        document.querySelectorAll('[data-de-embutir]').forEach(function (outro) {
          var outroCartao = cartaoDe(outro);
          if (outro !== alvo && outroCartao && outroCartao.open) outroCartao.open = false;
        });
        carregar(alvo);
      } else if (atual && atual.alvo === alvo) {
        desmontar();
      }
    });
    if (cartao.open) carregar(alvo);
  }

  function abrirPeloEndereco() {
    var id = decodeURIComponent((window.location.hash || '').slice(1));
    if (!id) return;
    var cartao = document.getElementById(id);
    if (!cartao || cartao.tagName !== 'DETAILS') return;
    // Cartão dentro de outro (os termos do ofício): abre o de fora também.
    for (var pai = cartao.parentElement; pai; pai = pai.parentElement) {
      if (pai.tagName === 'DETAILS') pai.open = true;
    }
    cartao.open = true;
    setTimeout(function () { cartao.scrollIntoView({ block: 'start' }); }, 50);
  }

  // Menu "Campos" do editor: chega depois da carga da página, então tem o
  // próprio abre-e-fecha.
  document.addEventListener('click', function (evento) {
    var gatilho = evento.target.closest('[data-de-menu-gatilho]');
    document.querySelectorAll('[data-de-menu-corpo]').forEach(function (corpo) {
      var dono = corpo.closest('[data-de-menu]');
      if (gatilho && dono && dono.contains(gatilho)) {
        corpo.hidden = !corpo.hidden;
        gatilho.setAttribute('aria-expanded', corpo.hidden ? 'false' : 'true');
      } else if (!corpo.hidden) {
        corpo.hidden = true;
        var g = dono && dono.querySelector('[data-de-menu-gatilho]');
        if (g) g.setAttribute('aria-expanded', 'false');
      }
    });

    var botao = evento.target.closest('[data-de-pdf]');
    if (!botao) return;
    evento.preventDefault();
    var form = document.createElement('form');
    form.method = 'post';
    form.action = botao.getAttribute('data-de-pdf');
    if (botao.getAttribute('data-de-alvo')) form.target = botao.getAttribute('data-de-alvo');
    var token = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (token) {
      var campo = document.createElement('input');
      campo.type = 'hidden';
      campo.name = 'csrfmiddlewaretoken';
      campo.value = token.value;
      form.appendChild(campo);
    }
    document.body.appendChild(form);
    form.submit();
    form.remove();
  });

  function iniciar() {
    document.querySelectorAll('[data-de-embutir]').forEach(ligar);
    abrirPeloEndereco();
  }

  window.addEventListener('hashchange', abrirPeloEndereco);
  window.DocEmbutido = { ligar: ligar, iniciar: iniciar };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
