/**
 * Viagens — a lista e a etapa 1 do painel.
 *
 * - na lista, "Cancelar viagem" abre o campo do motivo dentro do menu, sem
 *   fechá-lo (o motivo é obrigatório, como na origem);
 * - na etapa 1, escolher um modelo de motivo preenche o texto;
 * - as linhas de destino seguem o mecanismo do termo: "+" insere abaixo, a
 *   lixeira remove, a alça reordena (destinos-arraste.js) e a nomeação dos
 *   campos sai no envio, na ordem em que as linhas ficaram;
 * - o alternador de "Documentos vinculados" mostra o seletor da aba
 *   escolhida e esconde os outros quatro.
 * Nada aqui recarrega nem rola a página sozinho.
 */

/* Lista: o item "Cancelar viagem" abre o motivo sem fechar o menu. */
(function () {
  "use strict";

  document.querySelectorAll("[data-vg-cancelar]").forEach(function (botao) {
    // O app.js fecha o menu ao clicar num item; este só abre o campo.
    botao.addEventListener("click", function (evento) {
      evento.stopPropagation();
      var alvo = document.querySelector(botao.getAttribute("data-expande"));
      if (!alvo || alvo.hidden) return;
      var campo = alvo.querySelector('input[name="motivo"]');
      if (campo) campo.focus();
    });
  });
})();

/* Etapa 1: modelo de motivo → texto. */
(function () {
  "use strict";

  var form = document.getElementById("form-viagem");
  if (!form) return;
  var no = document.getElementById("viagem-modelos-texto");
  var modelos = {};
  try { modelos = no ? JSON.parse(no.textContent) : {}; } catch (erro) { modelos = {}; }
  var seletor = document.getElementById("id_modelo_motivo");
  var texto = document.getElementById("id_motivo");
  if (!seletor || !texto) return;
  seletor.addEventListener("change", function () {
    var valor = modelos[seletor.value];
    if (valor !== undefined) {
      texto.value = valor;
      texto.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
})();

/* Etapa 1: destinos no componente do termo. */
(function () {
  "use strict";

  var form = document.getElementById("form-viagem");
  if (!form) return;
  var lista = form.querySelector("[data-destinos]");
  var modelo = form.querySelector("[data-destino-modelo]");
  var quantidade = form.querySelector('input[name="quantidade_destinos"]');
  if (!lista || !modelo || !quantidade) return;
  // Índice novo nunca repete os que o servidor já usou; o envio renumera tudo.
  var proximo = Number(quantidade.value);
  if (!(proximo >= 0)) proximo = 0;

  function linhas() {
    return Array.prototype.slice.call(lista.querySelectorAll("[data-destino-linha]"));
  }

  function selectsDe(linha) {
    return {
      estado: linha.querySelector(".destino-row__estado select"),
      cidade: linha.querySelector(".destino-row__campo select")
    };
  }

  function atualizarEstado() {
    var unica = linhas().length <= 1;
    linhas().forEach(function (linha) { linha.classList.toggle("destino-row--unica", unica); });
  }

  function criarLinha(depoisDe) {
    var indice = proximo;
    proximo += 1;
    var apoio = document.createElement("div");
    apoio.innerHTML = modelo.innerHTML.replace(/__n__/g, String(indice)).trim();
    var linha = apoio.firstElementChild;
    if (!linha) return;
    if (depoisDe) lista.insertBefore(linha, depoisDe.nextSibling);
    else lista.appendChild(linha);
    if (window.DS && window.DS.aprimorar) window.DS.aprimorar(linha);
    atualizarEstado();
    var campo = linha.querySelector("[data-custom-select-trigger]");
    if (campo) campo.focus({ preventScroll: true });
  }

  function limpar(linha) {
    var campos = selectsDe(linha);
    [campos.estado, campos.cidade].forEach(function (select) {
      if (!select || !select.value) return;
      select.value = "";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  lista.addEventListener("click", function (evento) {
    var adicionar = evento.target.closest("[data-destino-adicionar]");
    if (adicionar) { criarLinha(adicionar.closest("[data-destino-linha]")); return; }
    var remover = evento.target.closest("[data-destino-remover]");
    if (!remover) return;
    var linha = remover.closest("[data-destino-linha]");
    // A primeira linha é o destino principal: a última esvazia em vez de sumir.
    if (linhas().length <= 1) { limpar(linha); return; }
    linha.remove();
    atualizarEstado();
  });

  if (window.DS && window.DS.arrastarDestinos) window.DS.arrastarDestinos(lista, function () {});

  // A primeira linha é o destino principal; as outras viram extra_*_0..n-1.
  form.addEventListener("submit", function () {
    var atuais = linhas();
    atuais.forEach(function (linha, posicao) {
      var campos = selectsDe(linha);
      if (campos.estado) campos.estado.name = posicao === 0 ? "destino_estado" : "extra_estado_" + (posicao - 1);
      if (campos.cidade) campos.cidade.name = posicao === 0 ? "destino_municipio" : "extra_cidade_" + (posicao - 1);
    });
    quantidade.value = String(Math.max(0, atuais.length - 1));
  });

  atualizarEstado();
})();

/* Etapa 1: alternador dos documentos vinculados. */
(function () {
  "use strict";

  var raiz = document.querySelector("[data-vg-docs]");
  if (!raiz) return;
  var abas = Array.prototype.slice.call(raiz.querySelectorAll("[data-vg-aba]"));
  var paineis = Array.prototype.slice.call(raiz.querySelectorAll("[data-vg-painel]"));

  function mostrar(chave) {
    paineis.forEach(function (painel) {
      painel.hidden = painel.getAttribute("data-vg-painel") !== chave;
    });
  }

  abas.forEach(function (aba) {
    aba.addEventListener("change", function () {
      if (aba.checked) mostrar(aba.value);
    });
  });
  var marcada = abas.find(function (aba) { return aba.checked; }) || abas[0];
  if (marcada) mostrar(marcada.value);
})();
