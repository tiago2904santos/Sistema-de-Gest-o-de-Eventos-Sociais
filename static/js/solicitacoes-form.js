/*
 * Tela da solicitação de evento: ajudas que só preenchem com um clique.
 *
 * - Sugestão do tipo de evento: ao escolher o tipo, mostra os serviços, as
 *   equipes (com a quantidade) e o solicitante que costumam acompanhá-lo;
 *   "Usar sugestão" marca e preenche só o que está vazio, sem desmarcar nada.
 * - Textos prontos do despacho da DG: o botão acrescenta o texto à
 *   observação (que continua editável).
 */
(function () {
  "use strict";

  function disparar(campo) {
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function el(tag, classe, texto) {
    var elemento = document.createElement(tag);
    if (classe) elemento.className = classe;
    if (texto) elemento.textContent = texto;
    return elemento;
  }

  var formulario = document.getElementById("form-solicitacao");

  function campo(nome) {
    return formulario ? formulario.querySelector('[name="' + nome + '"]') : null;
  }

  function marcavel(nome, valor) {
    return formulario.querySelector('input[name="' + nome + '"][value="' + valor + '"]');
  }

  // Um campo de texto ou select vazio e livre recebe o valor sugerido.
  function vazioELivre(elemento) {
    return elemento && !elemento.disabled && !elemento.readOnly && !String(elemento.value || "").trim();
  }

  function temOpcao(select, valor) {
    return Array.prototype.some.call(select.options, function (o) {
      return o.value === String(valor) && !o.disabled;
    });
  }

  // ------------------------------------------------------------------
  // Sugestão do tipo de evento
  // ------------------------------------------------------------------
  var caixa = document.querySelector("[data-sugestao-tipo]");
  var tipo = campo("tipo_evento");

  if (formulario && caixa && tipo && !tipo.disabled) {
    var pedido = 0;
    var dispensado = "";

    // O que a sugestão ainda acrescentaria à tela, passo a passo.
    function passos(sugestao) {
      var lista = [];
      sugestao.servicos.forEach(function (s) {
        var caixaServico = marcavel("servicos", s.id);
        if (caixaServico && !caixaServico.checked && !caixaServico.disabled) {
          lista.push(function () { caixaServico.checked = true; disparar(caixaServico); });
        }
      });
      sugestao.equipes.forEach(function (e) {
        var caixaEquipe = marcavel("equipes", e.id);
        if (!caixaEquipe || caixaEquipe.disabled) return;
        var quantidade = document.getElementById("id_quantidade_equipe_" + e.id);
        var faltaMarcar = !caixaEquipe.checked;
        var faltaQuantidade = e.quantidade && quantidade && !quantidade.value;
        if (faltaMarcar || faltaQuantidade) {
          lista.push(function () {
            if (!caixaEquipe.checked) { caixaEquipe.checked = true; disparar(caixaEquipe); }
            if (e.quantidade && quantidade && !quantidade.value) {
              quantidade.disabled = false;
              quantidade.value = e.quantidade;
              disparar(quantidade);
            }
          });
        }
      });
      var pessoa = sugestao.solicitante;
      if (pessoa) {
        [["solicitante_nome", pessoa.nome], ["solicitante_cargo_unidade", pessoa.cargo]].forEach(function (par) {
          var alvo = campo(par[0]);
          if (par[1] && vazioELivre(alvo)) {
            lista.push(function () { alvo.value = par[1]; disparar(alvo); });
          }
        });
        var orgao = campo("orgao_responsavel");
        if (pessoa.orgao && vazioELivre(orgao) && temOpcao(orgao, pessoa.orgao.id)) {
          lista.push(function () { orgao.value = String(pessoa.orgao.id); disparar(orgao); });
        }
      }
      return lista;
    }

    function linha(rotulo, texto) {
      var p = el("p", "sol-sugestao__linha");
      p.appendChild(el("b", "", rotulo + ": "));
      p.appendChild(document.createTextNode(texto));
      return p;
    }

    function mostrar(sugestao) {
      caixa.textContent = "";
      var aplicar = passos(sugestao);
      if (!aplicar.length || dispensado === tipo.value) {
        caixa.hidden = true;
        return;
      }
      var corpo = el("div", "aviso__corpo");
      corpo.appendChild(el("b", "", "Sugestão para " + sugestao.tipo));
      if (sugestao.origem.length) {
        corpo.appendChild(el("p", "sol-sugestao__origem", "Com base em " + sugestao.origem.join(" e ") + "."));
      }
      if (sugestao.servicos.length) {
        corpo.appendChild(linha("Serviços", sugestao.servicos.map(function (s) { return s.nome; }).join(", ")));
      }
      if (sugestao.equipes.length) {
        corpo.appendChild(linha("Equipes", sugestao.equipes.map(function (e) {
          return e.quantidade ? e.nome + " (" + e.quantidade + ")" : e.nome;
        }).join(", ")));
      }
      var pessoa = sugestao.solicitante;
      if (pessoa) {
        var partes = [pessoa.nome, pessoa.cargo, pessoa.orgao && pessoa.orgao.nome].filter(Boolean);
        if (partes.length) corpo.appendChild(linha("Solicitante", partes.join(" — ")));
      }
      var acoes = el("div", "sol-sugestao__acoes");
      var usar = el("button", "btn-primaria btn--compacto", "Usar sugestão");
      usar.type = "button";
      var fechar = el("button", "btn--secundaria btn--compacto", "Dispensar");
      fechar.type = "button";
      acoes.appendChild(usar);
      acoes.appendChild(fechar);
      corpo.appendChild(el("p", "sol-sugestao__nota", "Marca e preenche só o que está vazio; nada do que você escolheu é desfeito."));
      corpo.appendChild(acoes);
      var texto = el("div", "aviso__txt");
      texto.appendChild(corpo);
      caixa.appendChild(texto);
      caixa.hidden = false;

      usar.addEventListener("click", function () {
        passos(sugestao).forEach(function (passo) { passo(); });
        caixa.textContent = "";
        var feito = el("div", "aviso__txt");
        feito.appendChild(el("div", "aviso__corpo", "Sugestão aplicada. Confira e ajuste o que precisar."));
        caixa.appendChild(feito);
      });
      fechar.addEventListener("click", function () {
        dispensado = tipo.value;
        caixa.hidden = true;
      });
    }

    function buscar() {
      var valor = tipo.value;
      var numero = ++pedido;
      caixa.hidden = true;
      if (!valor) return;
      fetch(caixa.getAttribute("data-url") + "?tipo=" + encodeURIComponent(valor), {
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      })
        .then(function (resposta) { return resposta.ok ? resposta.json() : null; })
        .then(function (sugestao) {
          if (sugestao && numero === pedido && tipo.value === valor) mostrar(sugestao);
        })
        .catch(function () { /* sugestão é ajuda: sem ela, a tela segue igual */ });
    }

    tipo.addEventListener("change", buscar);
    if (tipo.value) buscar();
  }

  // ------------------------------------------------------------------
  // Textos prontos do despacho
  // ------------------------------------------------------------------
  document.querySelectorAll("[data-texto-pronto]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      var alvo = document.getElementById(botao.getAttribute("data-texto-alvo"));
      if (!alvo) return;
      var texto = botao.getAttribute("data-texto-pronto");
      var atual = alvo.value.trim();
      if (atual.indexOf(texto) !== -1) return;
      alvo.value = atual ? atual + "\n" + texto : texto;
      disparar(alvo);
      alvo.focus();
    });
  });
})();
