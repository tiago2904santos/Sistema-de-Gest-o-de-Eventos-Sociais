/**
 * Formulário do ofício — comportamentos do wizard da origem, numa tela só.
 *
 * - escolher um modelo preenche o texto (motivo e justificativa);
 * - viatura cadastrada ou não cadastrada: só o bloco escolhido fica visível;
 * - motorista servidor ou externo: o cartão do externo aparece no modo manual;
 * - motorista de fora da equipe (ou externo) exige ofício e protocolo de origem;
 * - o custeio por outra instituição exige a observação;
 * - o termo de autorização só pode ser marcado para quem viaja;
 * - escolher um roteiro mostra o resumo da rota.
 */
(function () {
  "use strict";

  var form = document.getElementById("form-oficio");
  if (!form) return;

  function lerJson(id) {
    var no = document.getElementById(id);
    if (!no) return {};
    try { return JSON.parse(no.textContent); } catch (erro) { return {}; }
  }

  function valorDoSelect(nome) {
    var campo = form.querySelector('[name="' + nome + '"]');
    return campo ? campo.value : "";
  }

  function marcados(nome) {
    return Array.prototype.map.call(form.querySelectorAll('input[name="' + nome + '"]:checked'), function (c) { return c.value; });
  }

  function mostrar(no, visivel) {
    if (!no) return;
    no.hidden = !visivel;
    no.querySelectorAll("input, select, textarea").forEach(function (campo) {
      // Campo escondido não é obrigatório: senão o navegador trava o envio num campo invisível.
      if (campo.dataset.obrigatorio === "1") campo.required = visivel;
    });
  }

  // 1. Modelos de texto -----------------------------------------------------
  var modelos = lerJson("oficio-modelos-texto");
  Object.entries({ "modelo_motivo": "motivo", "justificativa-modelo": "justificativa-texto" }).forEach(function (par) {
    var seletor = document.getElementById("id_" + par[0]);
    var texto = document.getElementById("id_" + par[1]);
    if (!seletor || !texto) return;
    seletor.addEventListener("change", function () {
      var valor = (modelos[par[0]] || {})[seletor.value];
      if (valor !== undefined) {
        texto.value = valor;
        texto.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
  });

  // 2. Custeio -------------------------------------------------------------
  var custeio = form.querySelector('[name="custeio"]');
  var observacaoCusteio = form.querySelector("[data-custeio-observacao]");
  function atualizarCusteio() {
    if (!custeio || !observacaoCusteio) return;
    var exige = custeio.value === "OUTRA_INSTITUICAO";
    observacaoCusteio.classList.toggle("is-exigido", exige);
    var dica = observacaoCusteio.querySelector("[data-custeio-dica]");
    if (dica) dica.hidden = !exige;
  }
  if (custeio) custeio.addEventListener("change", atualizarCusteio);

  // 3. Equipe: termo só para quem viaja -------------------------------------
  var equipe = form.querySelector("[data-equipe]");
  function atualizarEquipe() {
    if (!equipe) return;
    var viajantes = marcados("servidores");
    equipe.querySelectorAll("[data-pessoa]").forEach(function (pessoa) {
      var viaja = viajantes.indexOf(pessoa.dataset.pessoa) !== -1;
      pessoa.classList.toggle("of-membro--viaja", viaja);
      var termo = pessoa.querySelector('input[name="servidores_termo_autorizacao"]');
      if (termo) {
        termo.disabled = !viaja;
        if (!viaja) termo.checked = false;
      }
    });
    var contagem = form.querySelector("[data-equipe-contagem]");
    if (contagem) contagem.textContent = viajantes.length === 1 ? "1 viajante" : viajantes.length + " viajantes";
    atualizarMotorista();
  }
  if (equipe) {
    equipe.addEventListener("change", atualizarEquipe);
    var busca = form.querySelector("[data-equipe-busca]");
    if (busca) {
      busca.addEventListener("input", function () {
        var termo = busca.value.trim().toLowerCase();
        equipe.querySelectorAll("[data-pessoa]").forEach(function (pessoa) {
          var texto = (pessoa.dataset.busca || "").toLowerCase();
          pessoa.hidden = termo !== "" && texto.indexOf(termo) === -1 && !pessoa.querySelector('input[name="servidores"]').checked;
        });
      });
    }
  }

  // 4. Transporte: viatura cadastrada ou não cadastrada -----------------------
  var blocoCadastrada = form.querySelector("[data-viatura-cadastrada]");
  var blocoManual = form.querySelector("[data-viatura-manual]");
  function atualizarViatura() {
    var modo = form.querySelector('input[name="viatura_modo"]:checked');
    var manual = modo && modo.value === "manual";
    mostrar(blocoCadastrada, !manual);
    mostrar(blocoManual, manual);
    if (manual) {
      var viatura = form.querySelector('select[name="viatura"]');
      if (viatura && viatura.value) {
        viatura.value = "";
        viatura.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  }
  form.querySelectorAll('input[name="viatura_modo"]').forEach(function (r) { r.addEventListener("change", atualizarViatura); });

  // 5. Motorista: servidor ou externo, e a referência de origem ----------------
  var blocoServidor = form.querySelector("[data-motorista-servidor]");
  var blocoManualMotorista = form.querySelector("[data-motorista-manual]");
  var blocoReferencia = form.querySelector("[data-motorista-referencia]");
  var motoristaModo = form.querySelector('[name="motorista_modo"]');
  function atualizarMotorista() {
    var manual = motoristaModo && motoristaModo.value === "MANUAL";
    mostrar(blocoServidor, !manual);
    mostrar(blocoManualMotorista, manual);
    var motorista = valorDoSelect("motorista");
    var foraDaEquipe = !manual && motorista !== "" && marcados("servidores").indexOf(motorista) === -1;
    mostrar(blocoReferencia, manual || foraDaEquipe);
    var aviso = form.querySelector("[data-motorista-aviso]");
    if (aviso) aviso.hidden = !foraDaEquipe;
  }
  if (motoristaModo) motoristaModo.addEventListener("change", atualizarMotorista);
  var motoristaSelect = form.querySelector('select[name="motorista"]');
  if (motoristaSelect) motoristaSelect.addEventListener("change", atualizarMotorista);

  // 6. Roteiro: resumo da rota escolhida --------------------------------------
  var resumos = lerJson("oficio-resumos-roteiros");
  var roteiro = form.querySelector('select[name="roteiro"]');
  var painelRoteiro = form.querySelector("[data-roteiro-resumo]");
  var vazioRoteiro = form.querySelector("[data-roteiro-vazio]");
  function atualizarRoteiro() {
    if (!roteiro || !painelRoteiro) return;
    var dados = resumos[roteiro.value];
    painelRoteiro.hidden = !dados;
    if (vazioRoteiro) vazioRoteiro.hidden = Boolean(dados);
    if (!dados) return;
    painelRoteiro.querySelectorAll("[data-roteiro-campo]").forEach(function (no) {
      var chave = no.dataset.roteiroCampo;
      var valor = dados[chave];
      if (Array.isArray(valor)) valor = valor.length ? valor.join(", ") : "—";
      no.textContent = valor === "" || valor === undefined ? "—" : valor;
    });
    var abrir = painelRoteiro.querySelector("[data-roteiro-abrir]");
    if (abrir) abrir.href = dados.url_editar;
  }
  if (roteiro) roteiro.addEventListener("change", atualizarRoteiro);

  // 7. Lateral: rolar até a etapa -------------------------------------------
  document.querySelectorAll("[data-ir]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      var alvo = document.querySelector(botao.getAttribute("data-ir"));
      if (alvo) alvo.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  atualizarCusteio();
  atualizarEquipe();
  atualizarViatura();
  atualizarMotorista();
  atualizarRoteiro();
})();
