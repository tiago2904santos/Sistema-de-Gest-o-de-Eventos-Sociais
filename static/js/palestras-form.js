// Formulário de palestras: temas em cartões, palestrantes recomendados pelo
// tema e o protocolo que só aparece quando o pedido veio por protocolo.
(function () {
  "use strict";

  // 1. Temas ----------------------------------------------------------------
  // Cartões marcáveis como as atividades do plano de trabalho: marcar acende
  // o cartão, a busca filtra pelo nome e "Limpar seleção" desmarca tudo.
  var temas = document.querySelector("[data-pal-temas]");
  var cartoes = temas ? Array.prototype.slice.call(temas.querySelectorAll("[data-pal-tema]")) : [];
  var total = temas && temas.querySelector("[data-pal-temas-total]");
  var limpar = temas && temas.querySelector("[data-pal-tema-limpar]");
  var busca = temas && temas.querySelector("[data-pal-tema-busca]");
  var vazio = temas && temas.querySelector("[data-pal-tema-vazio]");

  function semAcento(texto) {
    return (texto || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  function marcados() {
    return cartoes.filter(function (c) { return c.querySelector("input").checked; });
  }

  function atualizarTemas() {
    cartoes.forEach(function (c) { c.classList.toggle("is-selected", c.querySelector("input").checked); });
    var n = marcados().length;
    if (total) total.textContent = n;
    if (limpar) limpar.disabled = !n;
    recomendar();
  }

  cartoes.forEach(function (c) { c.querySelector("input").addEventListener("change", atualizarTemas); });
  if (limpar) {
    limpar.addEventListener("click", function () {
      cartoes.forEach(function (c) { c.querySelector("input").checked = false; });
      atualizarTemas();
    });
  }
  if (busca) {
    busca.addEventListener("input", function () {
      var termo = semAcento(busca.value.trim());
      var visiveis = 0;
      cartoes.forEach(function (c) {
        var mostra = !termo || c.getAttribute("data-filtro").indexOf(termo) !== -1 || c.querySelector("input").checked;
        c.hidden = !mostra;
        if (mostra) visiveis += 1;
      });
      if (vazio) vazio.hidden = visiveis > 0;
    });
  }

  // 2. Recomendação de palestrante -------------------------------------------
  // O "Tema de abordagem" do palestrante é texto livre ("Bullyng /
  // Cyberbullyng"), então a comparação é por palavra: as palavras de quatro
  // letras ou mais do tema escolhido, pelo começo (cinco letras), contra as
  // do palestrante — "bullying" encontra "bullyng". Quem casa sobe na lista
  // com o selo "Recomendado".
  var VAZIAS = ["para", "como", "sobre", "contra", "entre", "outros", "outras", "consequencias", "prevencao", "combate", "enfrentamento", "identificar", "importancia"];
  var lista = document.querySelector('[data-lista-escolha="palestrantes"]');
  var buscaPalestrante = document.querySelector('[data-lista-busca="palestrantes"]');
  var aguardando = document.querySelector('[data-lista-aguardando="palestrantes"]');
  var semResultado = document.querySelector('[data-lista-sem-resultado="palestrantes"]');
  var recomendadosAtuais = [];
  var dica = document.querySelector("[data-pal-recomendacao]");
  var linhas = lista ? Array.prototype.slice.call(lista.querySelectorAll("[data-lista-item]")) : [];
  var ordemOriginal = linhas.slice();

  function raizes(texto) {
    return semAcento(texto).split(/[^a-z0-9]+/).filter(function (p) {
      return p.length >= 4 && VAZIAS.indexOf(p) === -1;
    }).map(function (p) { return p.slice(0, 5); });
  }

  function recomendar() {
    if (!lista) return;
    var procuradas = [];
    marcados().forEach(function (c) { procuradas = procuradas.concat(raizes(c.getAttribute("data-filtro"))); });
    var recomendados = [];
    linhas.forEach(function (linha) {
      var doPalestrante = raizes(linha.getAttribute("data-tema"));
      var casa = procuradas.length && doPalestrante.some(function (r) { return procuradas.indexOf(r) !== -1; });
      var nome = linha.querySelector(".of-pessoa__nome");
      var selo = nome && nome.querySelector("[data-pal-recomendado]");
      if (casa && !selo && nome) {
        selo = document.createElement("span");
        selo.className = "st st--atendido lista-escolha__chip";
        selo.setAttribute("data-pal-recomendado", "");
        selo.textContent = "Recomendado";
        nome.appendChild(selo);
      } else if (!casa && selo) {
        selo.remove();
      }
      if (casa) recomendados.push(linha);
    });
    // Recomendados primeiro, na ordem alfabética; depois os demais.
    var resto = ordemOriginal.filter(function (l) { return recomendados.indexOf(l) === -1; });
    recomendados.concat(resto).forEach(function (l) { lista.appendChild(l); });
    recomendadosAtuais = recomendados;
    filtrarPalestrantes();
    if (dica) {
      dica.hidden = !procuradas.length;
      dica.textContent = recomendados.length
        ? recomendados.length + (recomendados.length === 1 ? " recomendado" : " recomendados") + " para o tema"
        : "Nenhum palestrante cadastrado com esse tema";
    }
  }

  // Sem busca, a lista mostra só os recomendados pelo tema e os já marcados.
  // Com busca, qualquer palestrante que case com o texto — para quando a
  // ASCOM precisa de alguém fora da recomendação.
  function filtrarPalestrantes() {
    if (!lista) return;
    var termo = buscaPalestrante ? semAcento(buscaPalestrante.value.trim()) : "";
    var visiveis = 0;
    linhas.forEach(function (linha) {
      var marcado = linha.querySelector("input").checked;
      var mostra = marcado || (termo
        ? semAcento(linha.getAttribute("data-busca")).indexOf(termo) !== -1
        : recomendadosAtuais.indexOf(linha) !== -1);
      linha.hidden = !mostra;
      if (mostra) visiveis += 1;
    });
    lista.hidden = visiveis === 0;
    if (semResultado) semResultado.hidden = !(termo && visiveis === 0);
    if (aguardando) {
      aguardando.hidden = !(!termo && visiveis === 0);
      var texto = aguardando.querySelector("span");
      if (texto) {
        texto.textContent = marcados().length
          ? "Nenhum palestrante recomendado para o tema escolhido — busque pelo nome."
          : "Escolha um tema acima para ver os palestrantes recomendados — ou busque pelo nome.";
      }
    }
  }

  if (buscaPalestrante) {
    // Roda depois do filtro genérico da lista de escolha e manda na visibilidade.
    buscaPalestrante.addEventListener("input", filtrarPalestrantes);
  }
  if (lista) {
    // Desmarcar um palestrante fora da recomendação o tira da vista.
    lista.addEventListener("change", filtrarPalestrantes);
  }

  // 3. Canal e protocolo ------------------------------------------------------
  // O número do protocolo só aparece quando o canal é Protocolo, já com a
  // máscara do e-Protocolo (00.000.000-0), a mesma dos ofícios.
  var canal = document.getElementById("id_canal_solicitacao");
  var caixaProtocolo = document.querySelector("[data-pal-protocolo]");
  var protocolo = document.getElementById("id_protocolo");

  function mascaraProtocolo(valor) {
    var d = (valor || "").replace(/\D/g, "").slice(0, 9);
    var s = d.slice(0, 2);
    if (d.length > 2) s += "." + d.slice(2, 5);
    if (d.length > 5) s += "." + d.slice(5, 8);
    if (d.length > 8) s += "-" + d.slice(8);
    return s;
  }

  function atualizarCanal(evento) {
    if (!canal || !caixaProtocolo) return;
    var ehProtocolo = canal.value === "PROTOCOLO";
    caixaProtocolo.hidden = !ehProtocolo;
    caixaProtocolo.closest(".pal-canal").classList.toggle("pal-canal--protocolo", ehProtocolo);
    // Escolheu Protocolo agora: o cursor já vai para o número. A lista
    // aprimorada devolve o foco ao próprio gatilho logo depois, por isso a espera.
    if (evento && ehProtocolo && protocolo) setTimeout(function () { protocolo.focus(); }, 0);
  }

  if (protocolo) {
    protocolo.value = mascaraProtocolo(protocolo.value);
    protocolo.addEventListener("input", function () { protocolo.value = mascaraProtocolo(protocolo.value); });
  }
  if (canal) {
    canal.addEventListener("change", atualizarCanal);
    atualizarCanal(null);
  }

  recomendar();
})();
