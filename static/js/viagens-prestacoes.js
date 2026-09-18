/**
 * Prestações de contas — Meta 6.
 *
 * - `[data-autosave]`: grava sozinho o que muda num formulário (número da
 *   solicitação e período das diárias no cartão; km e abastecimento do diário;
 *   texto e custeio do relatório técnico). O payload é o de `core.autosave`:
 *   {model, object_id, form_id, dirty_fields, fields}. O formulário continua
 *   funcionando sem JS: o submit comum grava pelo caminho normal.
 * - `[data-anexar-cartao]`: escolher o arquivo no menu do cartão já envia.
 * - `[data-excluir-anexo]` e `[data-anexar-multiplos]`: etapa Documentos.
 * - `#dmv-oficios-source`: preenche a troca de motorista/viatura a partir de
 *   outro ofício.
 * - `#rt-modelos`: aplica o modelo de texto escolhido ao campo do relatório.
 */
(function () {
  "use strict";

  function csrf(form) {
    var campo = (form || document).querySelector('input[name="csrfmiddlewaretoken"]') || document.querySelector('input[name="csrfmiddlewaretoken"]');
    return campo ? campo.value : "";
  }

  /* ---------- autosave ---------- */
  document.querySelectorAll("[data-autosave]").forEach(function (form) {
    var url = form.getAttribute("data-autosave-url");
    if (!url) return;
    var estado = form.querySelector("[data-autosave-estado]");
    var sujos = {};
    var temporizador = null;
    var enviando = false;

    function mostrar(texto, classe) {
      if (!estado) return;
      estado.textContent = texto;
      estado.className = "pc-autosave" + (classe ? " pc-autosave--" + classe : "");
    }

    function valorDe(campo) {
      if (campo.type === "checkbox") return campo.checked ? campo.value || "on" : "";
      if (campo.type === "radio") {
        var marcado = form.querySelector('input[name="' + campo.name + '"]:checked');
        return marcado ? marcado.value : "";
      }
      return campo.value;
    }

    function enviar() {
      var nomes = Object.keys(sujos);
      if (!nomes.length || enviando) return;
      enviando = true;
      var campos = {};
      nomes.forEach(function (n) { campos[n] = sujos[n]; });
      sujos = {};
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
          fields: campos,
          snapshots: {}
        })
      }).then(function (r) { return r.json().then(function (d) { return {ok: r.ok && d.ok, dados: d}; }); })
        .then(function (res) {
          if (res.ok) {
            mostrar("Salvo", "ok");
            form.dispatchEvent(new CustomEvent("autosave:salvo", {bubbles: true, detail: res.dados}));
          } else {
            var erros = res.dados && res.dados.errors ? Object.values(res.dados.errors).flat().join(" ") : "";
            mostrar((res.dados && res.dados.message) || erros || "Não foi possível salvar.", "erro");
          }
        })
        .catch(function () { mostrar("Sem conexão: tente de novo.", "erro"); })
        .finally(function () {
          enviando = false;
          if (Object.keys(sujos).length) enviar();
        });
    }

    function agendar(campo, atraso) {
      if (!campo.name || campo.name === "csrfmiddlewaretoken" || campo.type === "hidden" || campo.type === "file" || campo.type === "submit") return;
      sujos[campo.name] = valorDe(campo);
      clearTimeout(temporizador);
      temporizador = setTimeout(enviar, atraso);
    }

    form.addEventListener("input", function (e) { agendar(e.target, 700); });
    form.addEventListener("change", function (e) { agendar(e.target, 150); });
    form.addEventListener("submit", function (e) {
      // Com JS, o submit do cartão só confirma o que o autosave já gravou.
      if (form.hasAttribute("data-autosave-so-ajax")) { e.preventDefault(); clearTimeout(temporizador); enviar(); }
    });
  });

  /* ---------- anexar direto do cartão ---------- */
  document.querySelectorAll("[data-anexar-cartao] input[type=file]").forEach(function (campo) {
    campo.addEventListener("change", function () {
      if (!campo.files.length) return;
      var form = campo.closest("form");
      var fd = new FormData(form);
      fetch(form.action, {method: "POST", body: fd, credentials: "same-origin", headers: {"X-Requested-With": "XMLHttpRequest"}})
        .then(function (r) { return r.json().catch(function () { return {ok: r.ok}; }).then(function (d) { return {ok: r.ok && d.ok !== false, dados: d}; }); })
        .then(function (res) {
          if (res.ok) { window.location.reload(); return; }
          window.alert((res.dados && res.dados.error) || "Não foi possível anexar o arquivo.");
          campo.value = "";
        })
        .catch(function () { window.alert("Não foi possível anexar o arquivo."); campo.value = ""; });
    });
  });

  /* ---------- etapa Documentos ---------- */
  document.querySelectorAll("[data-excluir-anexo]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var button = form.querySelector("button");
      button.disabled = true;
      fetch(form.action, {method: "POST", body: new FormData(form), headers: {"X-Requested-With": "XMLHttpRequest"}})
        .then(function (r) { return r.json().then(function (d) { if (!r.ok || !d.ok) throw new Error("Não foi possível remover o anexo."); }); })
        .then(function () { window.location.reload(); })
        .catch(function (error) { button.disabled = false; window.alert(error.message); });
    });
  });

  document.querySelectorAll("[data-anexar-multiplos]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var button = form.querySelector("button[type=submit]");
      button.disabled = true;
      fetch(form.action, {method: "POST", body: new FormData(form), headers: {"X-Requested-With": "XMLHttpRequest"}})
        .then(function (r) { return r.json().then(function (d) { return {ok: r.ok && d.ok, dados: d}; }); })
        .then(function (res) {
          if (res.ok) { window.location.reload(); return; }
          var d = res.dados || {};
          throw new Error(Object.values(d.errors || {}).flat().join(" ") || d.message || "Não foi possível anexar os arquivos.");
        })
        .catch(function (error) { button.disabled = false; window.alert(error.message); });
    });
  });

  document.querySelectorAll("[data-arquivo-nome]").forEach(function (campo) {
    campo.addEventListener("change", function () {
      var alvo = document.getElementById(campo.getAttribute("data-arquivo-nome"));
      if (!alvo) return;
      var nomes = Array.prototype.map.call(campo.files, function (f) { return f.name; });
      alvo.textContent = nomes.length ? nomes.join(", ") : "";
    });
  });

  /* ---------- modelos de texto do RT ---------- */
  var fonte = document.getElementById("rt-modelos");
  if (fonte) {
    var modelos = JSON.parse(fonte.textContent);
    document.querySelectorAll('select[name^="modelo_"]').forEach(function (select) {
      select.addEventListener("change", function () {
        var campo = select.name.slice(7);
        var texto = document.querySelector('[name="' + campo + '"]');
        if (texto && modelos[select.value] !== undefined) {
          texto.value = modelos[select.value];
          texto.dispatchEvent(new Event("input", {bubbles: true}));
        }
      });
    });
  }

  /* ---------- custeio: "Outro" abre o campo de texto ---------- */
  document.querySelectorAll("[data-rt-outro]").forEach(function (bloco) {
    var nome = bloco.getAttribute("data-rt-outro");
    var select = bloco.querySelector("select");
    var caixa = bloco.querySelector('[data-rt-outro-campo="' + nome + '"]');
    if (!select || !caixa) return;
    function atualizar() { caixa.hidden = select.value !== "__outro__"; }
    select.addEventListener("change", atualizar);
    atualizar();
  });

  /* ---------- motorista/viatura: modos ---------- */
  document.querySelectorAll("[data-modo-grupo]").forEach(function (grupo) {
    var nome = grupo.getAttribute("data-modo-grupo");
    function atualizar() {
      var select = grupo.querySelector('select[name="' + nome + '"]');
      var marcado = grupo.querySelector('input[name="' + nome + '"]:checked');
      var valor = select ? select.value : (marcado ? marcado.value : "");
      grupo.querySelectorAll("[data-modo-quando]").forEach(function (bloco) {
        bloco.hidden = bloco.getAttribute("data-modo-quando") !== valor;
      });
      grupo.querySelectorAll("[data-modo-opcao]").forEach(function (opcao) {
        opcao.classList.toggle("is-ativa", opcao.getAttribute("data-modo-opcao") === valor);
      });
    }
    grupo.addEventListener("change", atualizar);
    atualizar();
  });

  (function () {
    var data = document.getElementById("dmv-oficios-source");
    var selector = document.getElementById("id_dmv_oficio");
    if (!data || !selector) return;
    var oficios = JSON.parse(data.textContent);
    var preencher = function (name, value) {
      var radios = document.querySelectorAll('input[type=radio][name="' + name + '"]');
      if (radios.length) {
        radios.forEach(function (r) { r.checked = r.value === (value || ""); });
        if (radios[0]) radios[0].dispatchEvent(new Event("change", {bubbles: true}));
        return;
      }
      var field = document.getElementById("id_" + name);
      if (field) { field.value = value || ""; field.dispatchEvent(new Event("change", {bubbles: true})); }
    };
    selector.addEventListener("change", function () {
      var oficio = oficios.find(function (o) { return String(o.id) === selector.value; });
      if (!oficio) return;
      preencher("motorista_modo", "OUTRO_OFICIO");
      preencher("motorista_manual_nome", oficio.motorista_nome);
      preencher("motorista_manual_cpf", oficio.motorista_cpf);
      preencher("motorista_oficio_referencia", oficio.numero_ano);
      preencher("motorista_protocolo_ref", oficio.protocolo);
      preencher("viatura_modo", oficio.viatura.modo);
      preencher("viatura", oficio.viatura.id);
      ["modelo", "placa", "tipo", "combustivel"].forEach(function (campo) { preencher("viatura_manual_" + campo, oficio.viatura[campo]); });
    });
  })();

})();

/* Diário: "Trocar motorista / viatura" abre o modal em vez da página (o link segue valendo sem JS). */
(function () {
  "use strict";

  document.addEventListener("click", function (evento) {
    var link = evento.target.closest("[data-pc-modal]");
    if (link) {
      var dialogo = document.getElementById(link.getAttribute("data-pc-modal"));
      if (!dialogo || evento.ctrlKey || evento.metaKey || evento.shiftKey) return;
      evento.preventDefault();
      var corpo = link.closest("[data-menu-corpo]");
      if (corpo) {
        corpo.hidden = true;
        var gatilho = corpo.parentElement && corpo.parentElement.querySelector("[data-menu-gatilho]");
        if (gatilho) gatilho.setAttribute("aria-expanded", "false");
      }
      dialogo.showModal();
      return;
    }
    var fechar = evento.target.closest("[data-pc-fechar]");
    if (fechar) fechar.closest("dialog").close();
  });

  // O envio do modal voltou com erro: a tela abre com ele aberto.
  document.querySelectorAll("dialog[data-abrir]").forEach(function (dialogo) { dialogo.showModal(); });
})();
