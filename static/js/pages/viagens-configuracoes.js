/* Configurações dos documentos de viagens: máscara do CEP e busca do endereço.
 *
 * Telefone e caixa alta já vêm de `js/viagens-cadastros.js`, que ignora
 * `data-mask="cep"` por não ter essa máscara. O servidor guarda só os dígitos.
 *
 * Ao completar os 8 dígitos, consulta `viagens_cadastros:api_consulta_cep`
 * (o ViaCEP é chamado pelo servidor) e preenche logradouro, bairro, cidade e
 * UF, em silêncio: só erro aparece abaixo do campo. O CEP já salvo não dispara
 * consulta no carregamento, só o que se digita. */
(function () {
  "use strict";

  var form = document.getElementById("form-configuracoes");
  var campo = document.querySelector('[data-mask="cep"]');
  if (!campo) return;

  function digitos(valor) {
    return String(valor || "").replace(/\D/g, "").slice(0, 8);
  }

  function mascaraCep(valor) {
    var d = digitos(valor);
    return d.length > 5 ? d.slice(0, 5) + "-" + d.slice(5) : d;
  }

  campo.value = mascaraCep(campo.value);

  var urlModelo = form && form.getAttribute("data-cep-url");
  if (!urlModelo) {
    campo.addEventListener("input", function () { campo.value = mascaraCep(campo.value); });
    return;
  }

  var status = document.createElement("p");
  status.className = "form-ajuda cfg-cep-status";
  status.id = "id_cep_status";
  status.setAttribute("aria-live", "polite");
  campo.closest(".form-campo").appendChild(status);
  campo.setAttribute("aria-describedby", status.id);

  var destinos = { logradouro: "id_logradouro", bairro: "id_bairro", cidade: "id_cidade_endereco", uf: "id_uf" };
  var consultado = digitos(campo.value);
  var controle = null;

  function avisar(texto, tipo) {
    status.textContent = texto;
    status.classList.toggle("cfg-cep-status--erro", tipo === "erro");
    campo.closest(".form-controle-wrapper").classList.toggle("is-invalid", tipo === "erro");
  }

  function preencher(dados) {
    Object.keys(destinos).forEach(function (chave) {
      var alvo = document.getElementById(destinos[chave]);
      if (alvo) alvo.value = String(dados[chave] || "").toLocaleUpperCase("pt-BR");
    });
    var numero = document.getElementById("id_numero");
    if (numero && !numero.value) numero.focus();
  }

  function buscar(cep) {
    if (controle) controle.abort();
    controle = new AbortController();
    avisar("");
    fetch(urlModelo.replace("00000000", cep), {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      signal: controle.signal,
    })
      .then(function (resposta) {
        return resposta.json().catch(function () { return {}; }).then(function (dados) {
          if (!resposta.ok) throw new Error(dados.erro || "Não foi possível consultar o CEP.");
          return dados;
        });
      })
      .then(function (dados) {
        preencher(dados);
        avisar("");
      })
      .catch(function (erro) {
        if (erro.name === "AbortError") return;
        avisar(erro.message + " Preencha o endereço à mão.", "erro");
      });
  }

  campo.addEventListener("input", function () {
    campo.value = mascaraCep(campo.value);
    var cep = digitos(campo.value);
    if (cep.length < 8) {
      if (controle) controle.abort();
      consultado = "";
      avisar("");
      return;
    }
    if (cep === consultado) return;
    consultado = cep;
    buscar(cep);
  });
})();
