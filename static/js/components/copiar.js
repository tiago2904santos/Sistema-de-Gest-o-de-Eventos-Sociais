/* Botões Copiar — peça comum (Coffee Break e Viagens: "Dados para o
   eProtocolo"; ver components/v32/copiaveis.html).
   `data-copiar-de="<id>"` copia o texto da caixa; `data-copiar="<texto>"`
   copia o próprio valor. O botão diz "Copiado" por um instante. Sem a API do
   navegador (HTTP sem TLS), cai para a seleção + execCommand. */
(function () {
  "use strict";

  function copiar(texto, origem) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(texto);
    }
    var campo = origem;
    var temporario = !campo;
    if (temporario) {
      campo = document.createElement("textarea");
      campo.value = texto;
      campo.setAttribute("readonly", "");
      campo.style.position = "fixed";
      campo.style.opacity = "0";
      document.body.appendChild(campo);
    }
    campo.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    if (temporario) document.body.removeChild(campo);
    return ok ? Promise.resolve() : Promise.reject(new Error("copiar"));
  }

  function confirmar(botao, texto) {
    var rotulo = botao.querySelector("[data-copiar-rotulo]");
    botao.classList.add("is-copiado");
    if (rotulo) {
      if (!botao.dataset.rotuloOriginal) botao.dataset.rotuloOriginal = rotulo.textContent;
      rotulo.textContent = texto;
    } else {
      botao.setAttribute("title", texto);
    }
    clearTimeout(botao._copiarTempo);
    botao._copiarTempo = setTimeout(function () {
      botao.classList.remove("is-copiado");
      if (rotulo) rotulo.textContent = botao.dataset.rotuloOriginal;
      else botao.setAttribute("title", "Copiar");
    }, 1800);
  }

  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest("[data-copiar-de], [data-copiar]");
    if (!botao) return;
    var origem = botao.hasAttribute("data-copiar-de")
      ? document.getElementById(botao.getAttribute("data-copiar-de"))
      : null;
    var texto = origem ? origem.value : botao.getAttribute("data-copiar");
    copiar(texto, origem).then(
      function () { confirmar(botao, "Copiado"); },
      function () {
        if (origem) origem.select();
        confirmar(botao, "Use Ctrl+C");
      }
    );
  });
})();
