/*
 * Aviso de conflito de agenda (components/v32/avisos_conflito.html).
 *
 * Ao escolher pessoa, viatura, unidade móvel, palestrante, município ou
 * datas, pergunta ao servidor (core/conflitos.py) se o recurso já está em
 * outro compromisso no mesmo horário e atualiza o aviso amarelo. Nunca
 * impede o salvamento.
 *
 * `data-campos` liga campos do formulário a parâmetros do endpoint
 * ("servidores:servidores motorista:servidores viatura:viaturas"); os
 * pickers das telas marcam checkboxes e rádios sem sempre disparar
 * "change", então cliques também contam — a consulta só sai quando os
 * valores mudaram de fato.
 */
(function () {
  "use strict";

  function iniciar(caixa) {
    var formulario = document.getElementById(caixa.getAttribute("data-formulario"));
    var url = caixa.getAttribute("data-url");
    var lista = caixa.querySelector("[data-conflitos-lista]");
    if (!formulario || !url || !lista) return;
    var pares = (caixa.getAttribute("data-campos") || "").split(/\s+/).filter(Boolean).map(function (par) {
      var partes = par.split(":");
      return { campo: partes[0], parametro: partes[1] || partes[0] };
    });
    var fixos = caixa.getAttribute("data-fixos") || "";

    function valores(nome) {
      return Array.prototype.filter.call(formulario.elements, function (el) {
        if (el.name !== nome) return false;
        if (el.type === "checkbox" || el.type === "radio") return el.checked;
        return true;
      }).map(function (el) {
        if (el.tagName === "SELECT" && el.multiple) {
          return Array.prototype.filter.call(el.options, function (o) { return o.selected; }).map(function (o) { return o.value; });
        }
        return el.value;
      }).reduce(function (todos, v) { return todos.concat(v); }, []).filter(function (v) { return String(v || "").trim(); });
    }

    function consulta() {
      var busca = new URLSearchParams(fixos);
      pares.forEach(function (p) {
        valores(p.campo).forEach(function (v) { busca.append(p.parametro, v); });
      });
      return busca.toString();
    }

    function mostrar(conflitos) {
      lista.textContent = "";
      conflitos.forEach(function (c) {
        var item = document.createElement("li");
        var alvo = item;
        if (c.url) {
          alvo = document.createElement("a");
          alvo.href = c.url;
          item.appendChild(alvo);
        }
        alvo.textContent = c.mensagem;
        lista.appendChild(item);
      });
      caixa.hidden = !conflitos.length;
      // Vazio, a caixa nem parece aviso (a tela abre limpa).
      caixa.classList.toggle("aviso--callout", !!conflitos.length);
    }

    var ultima = consulta();
    var espera = null;
    var pedido = 0;

    function talvezConsultar() {
      clearTimeout(espera);
      espera = setTimeout(function () {
        var atual = consulta();
        if (atual === ultima) return;
        ultima = atual;
        var numero = ++pedido;
        fetch(url + "?" + atual, { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
          .then(function (r) { return r.ok ? r.json() : { conflitos: [] }; })
          .then(function (dados) { if (numero === pedido) mostrar(dados.conflitos || []); })
          .catch(function () { /* Sem resposta, fica o aviso que estava: é só aviso. */ });
      }, 350);
    }

    ["change", "input", "click"].forEach(function (tipo) {
      document.addEventListener(tipo, talvezConsultar, true);
    });
  }

  function tudo() {
    document.querySelectorAll("[data-conflitos][data-url]").forEach(iniciar);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", tudo);
  else tudo();
})();
