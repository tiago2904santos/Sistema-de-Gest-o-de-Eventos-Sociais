/**
 * Rascunho que se salva sozinho — ofício, ordem de serviço e plano (m050).
 *
 * O mesmo contrato do autosave de servidor que a casa já usa
 * (`data-autosave-url`, `data-autosave-model`, `data-autosave-id`,
 * `[data-autosave-estado]` e o payload de `core.autosave`), com uma
 * diferença: aqui vai o formulário INTEIRO em `fields` (listas nos campos
 * múltiplos), porque o servidor passa tudo pelo mesmo Form do "Salvar" — a
 * validação é a mesma e nada é gravado campo a campo. O padrão de envio é o
 * do editor de roteiro: espera alguns segundos depois da última alteração,
 * um envio por vez, e o indicador "Salvo às 14:32".
 *
 * Antes do retrato, o evento `autosave:preparar` deixa os scripts da tela
 * nomearem o que só nomeavam no envio (as linhas de destino arrastáveis).
 * Sem JS, ou com o autosave recusado, o botão "Salvar" continua valendo.
 */
(function () {
  "use strict";

  var ESPERA = 2500;

  function csrf(form) {
    var campo = form.querySelector('input[name="csrfmiddlewaretoken"]') || document.querySelector('input[name="csrfmiddlewaretoken"]');
    return campo ? campo.value : "";
  }

  function retrato(form) {
    var campos = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.disabled || el.name === "csrfmiddlewaretoken") return;
      var tipo = (el.type || "").toLowerCase();
      if (tipo === "file" || tipo === "submit" || tipo === "button" || tipo === "reset") return;
      if ((tipo === "checkbox" || tipo === "radio") && !el.checked) return;
      var valores = [];
      if (el.tagName === "SELECT" && el.multiple) {
        Array.prototype.forEach.call(el.options, function (o) { if (o.selected) valores.push(o.value); });
      } else {
        valores.push(tipo === "checkbox" ? (el.value || "on") : el.value);
      }
      valores.forEach(function (v) {
        if (Object.prototype.hasOwnProperty.call(campos, el.name)) {
          if (!Array.isArray(campos[el.name])) campos[el.name] = [campos[el.name]];
          campos[el.name].push(v);
        } else {
          campos[el.name] = v;
        }
      });
    });
    return campos;
  }

  document.querySelectorAll("form[data-autosave-rascunho][data-autosave-url]").forEach(function (form) {
    var url = form.getAttribute("data-autosave-url");
    var estado = document.querySelector('[data-autosave-estado][data-autosave-de="' + form.id + '"]') || form.querySelector("[data-autosave-estado]");
    var sujos = {};
    var temporizador = null;
    var enviando = false;
    var enviandoForm = false;

    function mostrar(texto, classe) {
      if (!estado) return;
      estado.textContent = texto;
      estado.className = "autosave-estado" + (classe ? " autosave-estado--" + classe : "");
    }

    function enviar() {
      var nomes = Object.keys(sujos);
      if (!nomes.length || enviandoForm) return;
      if (enviando) { agendar(); return; }
      enviando = true;
      sujos = {};
      form.dispatchEvent(new CustomEvent("autosave:preparar"));
      mostrar("Salvando…", "andamento");
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf(form), "X-Requested-With": "XMLHttpRequest"},
        body: JSON.stringify({
          model: form.getAttribute("data-autosave-model") || "",
          object_id: form.getAttribute("data-autosave-id") || "",
          form_id: form.id || "",
          dirty_fields: nomes,
          fields: retrato(form),
          snapshots: {}
        })
      }).then(function (r) { return r.json().then(function (d) { return {ok: r.ok && d.ok, dados: d}; }); })
        .then(function (res) {
          if (res.ok) {
            var hora = (res.dados.saved_at_display || "").split(" ")[1] || "";
            mostrar(hora ? "Rascunho salvo às " + hora : "Rascunho salvo", "ok");
          } else {
            var erros = res.dados && res.dados.errors ? Object.keys(res.dados.errors).map(function (k) { return [].concat(res.dados.errors[k]).join(" "); }).join(" ") : "";
            mostrar(((res.dados && res.dados.message) || "Rascunho não salvo.") + (erros ? " " + erros : ""), "erro");
          }
        })
        .catch(function () { mostrar("Sem conexão: o rascunho será salvo na próxima alteração.", "erro"); })
        .finally(function () { enviando = false; });
    }

    function agendar() {
      clearTimeout(temporizador);
      temporizador = setTimeout(enviar, ESPERA);
    }

    function marcar(e) {
      var el = e.target;
      if (!el || !el.name || el.name === "csrfmiddlewaretoken" || el.type === "file") return;
      sujos[el.name] = true;
      agendar();
    }

    form.addEventListener("input", marcar);
    form.addEventListener("change", marcar);
    // Botões de remover linha, arrastar destino etc. mexem no formulário sem "change".
    form.addEventListener("autosave:alterado", function () { sujos.__tela__ = true; agendar(); });
    // O envio normal vale mais que o rascunho pendente.
    form.addEventListener("submit", function () { enviandoForm = true; clearTimeout(temporizador); });
  });
})();
