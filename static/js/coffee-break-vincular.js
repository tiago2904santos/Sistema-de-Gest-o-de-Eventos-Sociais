/* Coffee Break — etapa 2: "Vincular outra OS" no cabeçalho do cartão abre a
   lista de escolha das OS do mesmo lote (como a dos palestrantes). Marcar ou
   desmarcar já vincula (sem salvar a etapa); ao vincular, a tela volta com o
   modal de anexo da nota daquela OS aberto. */
(function () {
  "use strict";
  var botao = document.querySelector("[data-cb-vincular-abrir]");
  var painel = document.querySelector("[data-cb-vincular]");

  // Voltou de um vínculo novo: abre o anexo da nota da OS que entrou.
  var endereco = new URL(window.location.href);
  var anexar = endereco.searchParams.get("anexar");
  if (anexar) {
    endereco.searchParams.delete("anexar");
    window.history.replaceState(null, "", endereco);
    var link = document.querySelector('[data-anexar-os="' + anexar + '"]');
    if (link) setTimeout(function () { link.click(); }, 150);
  }

  if (!botao || !painel) return;
  function abrir(sim) {
    painel.hidden = !sim;
    botao.setAttribute("aria-expanded", sim ? "true" : "false");
    if (sim) {
      var busca = painel.querySelector("[data-lista-busca]");
      if (busca) busca.focus();
    }
  }
  botao.addEventListener("click", function () { abrir(painel.hidden); });

  var estado = painel.querySelector("[data-cb-vincular-estado]");
  var token = document.querySelector('input[name="csrfmiddlewaretoken"]');
  var enviando = false;
  painel.addEventListener("change", function (evento) {
    var caixa = evento.target;
    if (caixa.name !== "vinculadas" || enviando) return;
    enviando = true;
    if (estado) estado.textContent = "Vinculando…";
    var dados = new FormData();
    painel.querySelectorAll('input[name="vinculadas"]:checked').forEach(function (c) { dados.append("vinculadas", c.value); });
    fetch(painel.getAttribute("data-cb-vincular-url"), {
      method: "POST", body: dados, credentials: "same-origin",
      headers: { "X-CSRFToken": token ? token.value : "", "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok && d.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.d.mensagem || "Não foi possível vincular.");
        var destino = new URL(window.location.href);
        if (caixa.checked) destino.searchParams.set("anexar", caixa.value);
        window.location.assign(destino.toString());
      })
      .catch(function (erro) {
        enviando = false;
        caixa.checked = !caixa.checked;
        if (estado) estado.textContent = erro.message;
      });
  });
})();
