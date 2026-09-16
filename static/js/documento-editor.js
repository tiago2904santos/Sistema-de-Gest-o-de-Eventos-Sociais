/* Editor documental da prévia A4 (viagens_oficios/documento.html).

   A folha vive num iframe da mesma origem; os trechos que nascem de um campo
   real levam `data-doc-campo`. Clicar num deles abre, ao lado da folha, o
   painel daquele campo — HTML que a API devolve, montado com os componentes
   globais. O painel grava por PATCH (JSON, com o token CSRF e a versão que
   foi lida); texto tem espera de digitação, escolhas gravam na hora. Depois
   de gravar, a folha recarrega e o campo continua aberto. Erros do
   formulário voltam por nome e aparecem no lugar, sem redesenhar o painel;
   409 avisa que outra pessoa mexeu e pede para recarregar. */
(function () {
  'use strict';

  var editor = document.querySelector('[data-de-editor]');
  var quadro = document.getElementById('dc-folha');
  if (!editor || !quadro) return;

  var painel = editor.querySelector('[data-de-painel]');
  var vazio = editor.querySelector('[data-de-vazio]');
  // Três espécies de trecho editável, cada uma com a sua rota: campo (nasce
  // de um campo real), bloco (parágrafo do modelo) e quebra (ponto de quebra).
  var urls = {
    campo: editor.getAttribute('data-de-url'),
    bloco: editor.getAttribute('data-de-url-bloco'),
    quebra: editor.getAttribute('data-de-url-quebra')
  };
  var versao = editor.getAttribute('data-de-versao') || '';
  var tokenCsrf = document.querySelector('input[name="csrfmiddlewaretoken"]');
  var ESPERA_DIGITACAO = 900;

  var chaveAberta = null;
  var especieAberta = 'campo';
  var temporizador = null;
  var enviando = false;
  var reenviar = false;

  function url(especie, chave) { return (urls[especie] || '').replace('CHAVE', encodeURIComponent(chave)); }
  function documentoDaFolha() { return quadro.contentDocument; }
  function cabecalhos(comCorpo) {
    var h = { 'X-CSRFToken': tokenCsrf ? tokenCsrf.value : '', 'X-Requested-With': 'XMLHttpRequest' };
    if (comCorpo) h['Content-Type'] = 'application/json';
    return h;
  }

  function marcar(chave, especie) {
    var doc = documentoDaFolha();
    if (!doc) return;
    doc.querySelectorAll('.doc-editavel--ativo').forEach(function (el) { el.classList.remove('doc-editavel--ativo'); });
    if (!chave) return;
    var atributo = especie === 'bloco' ? 'data-doc-bloco' : 'data-doc-campo';
    doc.querySelectorAll('[' + atributo + '="' + chave + '"]').forEach(function (el) { el.classList.add('doc-editavel--ativo'); });
  }

  function status(texto, classe) {
    var el = painel.querySelector('[data-de-status]');
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

  function salvar(form) {
    if (enviando) { reenviar = true; return; }
    clearTimeout(temporizador);
    enviando = true;
    status('Salvando…', 'andamento');
    fetch(form.getAttribute('action'), {
      method: 'PATCH',
      credentials: 'same-origin',
      headers: cabecalhos(true),
      body: JSON.stringify({ versao: versao, valores: valoresDe(form) })
    }).then(function (resposta) {
      return resposta.json().then(function (dados) { return { codigo: resposta.status, dados: dados }; }, function () { return { codigo: resposta.status, dados: {} }; });
    }).then(function (res) {
      enviando = false;
      if (res.codigo === 200) {
        versao = res.dados.versao || versao;
        limparErros();
        status(res.dados.avisos && res.dados.avisos.length ? 'Salvo. O ofício ainda tem pendências em outros campos.' : 'Salvo', 'ok');
        recarregarFolha();
        // Um bloco que acabou de ganhar (ou perder) override troca de painel:
        // aparece ou some o "Restaurar". Reabre sem mexer no texto digitado.
        if (form.getAttribute('data-de-especie') === 'bloco' && !temporizador) reabrirSeMudouEstado(form, res.dados.editado);
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
    });
  }

  function restaurar(form) {
    status('Restaurando…', 'andamento');
    fetch(form.getAttribute('action'), { method: 'DELETE', credentials: 'same-origin', headers: cabecalhos(false) })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function () { recarregarFolha(); abrir(chaveAberta, 'bloco'); })
      .catch(function () { status('Não foi possível restaurar.', 'erro'); });
  }

  function alternarQuebra(chave, ativa) {
    fetch(url('quebra', chave), { method: 'PATCH', credentials: 'same-origin', headers: cabecalhos(true), body: JSON.stringify({ ativa: ativa }) })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function () { recarregarFolha(); })
      .catch(function () { window.alert('Não foi possível alterar a quebra de página.'); });
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
      status('Digitando…');
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
    painel.querySelectorAll('[data-de-fechar]').forEach(function (botao) { botao.addEventListener('click', fechar); });
    var botaoRestaurar = form.querySelector('[data-de-restaurar]');
    if (botaoRestaurar) botaoRestaurar.addEventListener('click', function () { restaurar(form); });
  }

  function montar(html) {
    painel.innerHTML = html;
    painel.hidden = false;
    if (vazio) vazio.hidden = true;
    if (window.DS && window.DS.aprimorar) window.DS.aprimorar(painel);
    ligarPainel();
  }

  function abrir(chave, especie, depois) {
    especie = especie || 'campo';
    chaveAberta = chave;
    especieAberta = especie;
    marcar(chave, especie);
    fetch(url(especie, chave), { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (dados) {
        if (dados.versao !== undefined) versao = dados.versao;
        montar(dados.fragmento);
        if (depois) depois();
        var primeiro = painel.querySelector('textarea, input[type="text"]:not([data-multi-busca]), select');
        if (primeiro && !primeiro.closest('.custom-select')) primeiro.focus();
      })
      .catch(function () { montar('<p class="form-erro">Não foi possível abrir este trecho.</p>'); });
  }

  function fechar() {
    clearTimeout(temporizador);
    temporizador = null;
    chaveAberta = null;
    marcar(null);
    painel.hidden = true;
    painel.innerHTML = '';
    if (vazio) vazio.hidden = false;
  }

  // O que foi clicado (ou acionado pelo teclado) na folha: campo, bloco ou
  // ponto de quebra. Devolve false quando não é nada editável.
  function acionar(alvoInicial) {
    if (!alvoInicial || !alvoInicial.closest) return false;
    var quebra = alvoInicial.closest('[data-doc-quebra]');
    if (quebra) {
      alternarQuebra(quebra.getAttribute('data-doc-quebra'), !quebra.hasAttribute('data-doc-quebra-ativa'));
      return true;
    }
    var bloco = alvoInicial.closest('[data-doc-bloco]');
    if (bloco) { abrir(bloco.getAttribute('data-doc-bloco'), 'bloco'); return true; }
    var campo = alvoInicial.closest('[data-doc-campo]');
    if (campo) { abrir(campo.getAttribute('data-doc-campo'), 'campo'); return true; }
    return false;
  }

  function ligarFolha() {
    var doc = documentoDaFolha();
    if (!doc) return;
    doc.addEventListener('click', function (evento) {
      if (acionar(evento.target)) evento.preventDefault();
    });
    doc.addEventListener('keydown', function (evento) {
      if (evento.key !== 'Enter' && evento.key !== ' ') return;
      if (acionar(evento.target)) evento.preventDefault();
    });
    marcar(chaveAberta, especieAberta);
  }

  quadro.addEventListener('load', ligarFolha);
  if (quadro.contentDocument && quadro.contentDocument.readyState === 'complete' && quadro.contentDocument.body && quadro.contentDocument.body.children.length) ligarFolha();

  if (vazio) vazio.addEventListener('click', function (evento) {
    var chip = evento.target.closest('[data-de-abrir]');
    if (chip) abrir(chip.getAttribute('data-de-abrir'), chip.getAttribute('data-de-especie') || 'campo');
  });
  document.addEventListener('keydown', function (evento) {
    if (evento.key === 'Escape' && chaveAberta) fechar();
  });
})();
