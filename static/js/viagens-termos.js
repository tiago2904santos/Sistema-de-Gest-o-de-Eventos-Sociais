/**
 * Cadastro do termo: o interruptor do ofício, as linhas de destino e a ordem
 * das viaturas. As listas de ofício e viatura são o `lista-escolha.js`; os
 * servidores, o seletor múltiplo do `multi-pick.js`.
 */

/**
 * Interruptor "vincular a um ofício" — mesmo molde do bate-volta do roteiro.
 * O `data-expande` do app.js abre e fecha o painel; aqui ficam o rótulo e o
 * efeito de desligar: o ofício escolhido sai junto, senão o campo oculto
 * continuaria indo no POST e o termo seguiria vinculado sem o painel aparecer.
 */
(function () {
  "use strict";

  var toggle = document.querySelector("[data-oficio-toggle]");
  var painel = document.getElementById("oficio-painel");
  if (!toggle || !painel) return;
  var rotulo = toggle.querySelector(".interruptor__rotulo");
  var busca = painel.querySelector("#id_oficio_busca");

  toggle.addEventListener("click", function () {
    // O app.js troca o aria-expanded no mesmo clique; o setTimeout lê o valor já trocado.
    setTimeout(function () {
      var ligado = toggle.getAttribute("aria-expanded") === "true";
      toggle.classList.toggle("interruptor--ligado", ligado);
      if (rotulo) rotulo.textContent = ligado ? "Vinculado a um ofício" : "Sem ofício vinculado";
      if (ligado) {
        if (busca) busca.focus();
        return;
      }
      // Desligado, o termo é avulso: a escolha sai junto com o painel — é a
      // única forma de desmarcar, já que um rádio marcado não desmarca sozinho.
      var marcado = painel.querySelector('input[name="oficio"]:checked');
      if (marcado) {
        marcado.checked = false;
        marcado.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }, 0);
  });
})();

/**
 * Destinos no componente do editor de roteiro: "+" insere a linha abaixo, a
 * lixeira remove e a alça reordena (o `destinos-arraste.js`).
 *
 * A lista é uma só e a posição é que decide o campo: a primeira linha é o
 * destino do termo (`destino_estado`/`destino_cidade`) e as seguintes são os
 * adicionais (`extra_estado_<i>`/`extra_cidade_<i>`, que o form do servidor
 * cria a partir de `quantidade_destinos`). Renomear a cada mexida obrigaria a
 * refazer `name`, `id` e a cascata de um select já aprimorado, então a
 * nomeação sai de uma vez no envio, na ordem em que as linhas ficaram.
 */
(function () {
  "use strict";

  var form = document.getElementById("form-termo");
  if (!form) return;
  var lista = form.querySelector("[data-destinos]");
  var modelo = form.querySelector("[data-destino-modelo]");
  var quantidade = form.querySelector('input[name="quantidade_destinos"]');
  if (!lista || !modelo || !quantidade) return;
  // Índice novo nunca repete os que o servidor já usou nesta renderização.
  // Só precisa ser único enquanto a tela vive: o envio renumera tudo.
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

  // Com uma linha só a alça e a lixeira somem, como no editor de roteiro.
  function atualizarEstado() {
    var unica = linhas().length <= 1;
    linhas().forEach(function (linha) {
      linha.classList.toggle("destino-row--unica", unica);
    });
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
    if (campo) campo.focus();
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
    // O termo precisa de um destino: a última linha esvazia em vez de sumir.
    if (linhas().length <= 1) { limpar(linha); return; }
    linha.remove();
    atualizarEstado();
  });

  if (window.DS && window.DS.arrastarDestinos) window.DS.arrastarDestinos(lista, function () {});

  // A nomeação final sai daqui: a primeira linha é o destino do termo e as
  // outras viram `extra_*_0..n-1`, na ordem da tela.
  form.addEventListener("submit", function () {
    var atuais = linhas();
    atuais.forEach(function (linha, posicao) {
      var campos = selectsDe(linha);
      if (campos.estado) campos.estado.name = posicao === 0 ? "destino_estado" : "extra_estado_" + (posicao - 1);
      if (campos.cidade) campos.cidade.name = posicao === 0 ? "destino_cidade" : "extra_cidade_" + (posicao - 1);
    });
    quantidade.value = String(Math.max(1, atuais.length - 1));
  });

  atualizarEstado();
})();

/**
 * Viaturas na ordem de quem vai viajar: a viatura vinculada a um servidor
 * escolhido sobe ao topo; depois vêm as da lotação desses servidores; o resto
 * segue na ordem de placa que veio do servidor.
 *
 * A conta é toda no navegador, pelos `data-unidade`/`data-motoristas` das
 * linhas, porque a ordem muda a cada servidor marcado ou desmarcado.
 */
(function () {
  "use strict";

  var form = document.getElementById("form-termo");
  if (!form) return;
  var lista = form.querySelector('[data-lista-escolha="viatura"]');
  if (!lista) return;

  // A ordem que veio do servidor é o desempate: sem ela, viaturas do mesmo
  // peso trocariam de lugar a cada recálculo.
  var ordemBase = {};
  Array.prototype.slice.call(lista.querySelectorAll("[data-lista-item]")).forEach(function (linha, i) {
    ordemBase[linha.getAttribute("data-lista-item")] = i;
  });

  function escolhidos() {
    var ids = [];
    var unidades = [];
    form.querySelectorAll('[data-multi-opcao] input[name="servidores"]:checked').forEach(function (caixa) {
      ids.push(caixa.value);
      var unidade = caixa.closest("[data-multi-opcao]").getAttribute("data-unidade");
      if (unidade && unidades.indexOf(unidade) === -1) unidades.push(unidade);
    });
    return { ids: ids, unidades: unidades };
  }

  // 0 é a viatura de um dos escolhidos, 1 é a da lotação deles, 2 é o resto.
  function peso(linha, alvo) {
    var motoristas = (linha.getAttribute("data-motoristas") || "").split(" ").filter(Boolean);
    if (motoristas.some(function (id) { return alvo.ids.indexOf(id) !== -1; })) return 0;
    var unidade = linha.getAttribute("data-unidade") || "";
    if (unidade && alvo.unidades.indexOf(unidade) !== -1) return 1;
    return 2;
  }

  function reordenar() {
    var alvo = escolhidos();
    var linhas = Array.prototype.slice.call(lista.querySelectorAll("[data-lista-item]"));
    var ordenadas = linhas.slice().sort(function (a, b) {
      var pa = peso(a, alvo);
      var pb = peso(b, alvo);
      if (pa !== pb) return pa - pb;
      return ordemBase[a.getAttribute("data-lista-item")] - ordemBase[b.getAttribute("data-lista-item")];
    });
    if (!ordenadas.some(function (linha, i) { return linha !== linhas[i]; })) return;
    ordenadas.forEach(function (linha) { lista.appendChild(linha); });
  }

  // A busca de viatura fica sempre à vista. A lista só aparece quando há o que
  // mostrar: servidor escolhido (as sugestões), viatura já marcada (a escolha
  // não parece perdida) ou algo digitado na busca (o filtro). Fora disso, o
  // cartão de espera ocupa o lugar dela.
  var campoBusca = form.querySelector('[data-lista-campo="viatura"]');
  var buscaViatura = campoBusca && campoBusca.querySelector(".busca");
  var entradaBusca = form.querySelector('[data-lista-busca="viatura"]');
  var espera = form.querySelector('[data-lista-aguardando="viatura"]');
  if (buscaViatura) buscaViatura.hidden = false;

  function atualizarEspera() {
    if (!espera) return;
    var temServidor = Boolean(form.querySelector('[data-multi-opcao] input[name="servidores"]:checked'));
    var temViatura = Boolean(lista.querySelector('input[name="viatura"]:checked'));
    var temBusca = Boolean(entradaBusca && entradaBusca.value.trim());
    var aguardar = !temServidor && !temViatura && !temBusca;
    espera.hidden = !aguardar;
    lista.hidden = aguardar;
  }

  form.addEventListener("change", function (evento) {
    if (evento.target.name === "servidores") reordenar();
    if (evento.target.name === "servidores" || evento.target.name === "viatura") atualizarEspera();
  });
  if (entradaBusca) entradaBusca.addEventListener("input", atualizarEspera);
  reordenar();
  atualizarEspera();
})();
