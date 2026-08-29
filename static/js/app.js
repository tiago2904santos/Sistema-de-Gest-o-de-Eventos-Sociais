/**
 * JS leve do Sistema de Gestão de Eventos Sociais.
 * Sem frameworks — apenas melhorias progressivas.
 */
(function () {
  "use strict";

  // Fecha alertas automaticamente após 6 segundos.
  document.querySelectorAll(".alerta").forEach(function (alerta) {
    setTimeout(function () {
      alerta.style.transition = "opacity 0.4s ease";
      alerta.style.opacity = "0";
      setTimeout(function () {
        alerta.remove();
      }, 400);
    }, 6000);
  });

  var formulario = document.querySelector("#form-solicitacao");
  if (!formulario) return;

  var regioesPorMunicipio = {
    Curitiba: "Curitiba e RM",
    Londrina: "Norte",
    Maringá: "Noroeste",
    Cascavel: "Oeste",
    "Ponta Grossa": "Campos Gerais"
  };

  var meses = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
  ];

  function campo(nome) {
    return formulario.querySelector('[name="' + nome + '"]');
  }

  function textoSelecionado(nome) {
    var elemento = campo(nome);
    if (!elemento || !elemento.value) return "—";
    return elemento.options ? elemento.options[elemento.selectedIndex].text : elemento.value;
  }

  function formatarData(valor) {
    if (!valor) return "";
    var partes = valor.split("-");
    return partes.length === 3 ? partes[2] + "/" + partes[1] + "/" + partes[0] : valor;
  }

  function definirResumo(id, valor) {
    var elemento = document.getElementById(id);
    if (elemento) elemento.textContent = valor || "—";
  }

  function marcarChecklist(nome, completo) {
    var item = document.querySelector('[data-check="' + nome + '"]');
    if (item) item.classList.toggle("is-complete", Boolean(completo));
  }

  function atualizarAcompanhamento() {
    var inicio = campo("data_inicio_evento");
    var fim = campo("data_fim_evento");
    var municipio = campo("municipio");
    var quantidadeServidores = campo("quantidade_servidores");
    var quantidadeCin = campo("quantidade_cin");
    var contato = campo("contato");
    var servicos = formulario.querySelectorAll('[name="servicos"]:checked');
    var equipes = formulario.querySelectorAll('[name="equipes"]:checked');
    var nomesEquipes = Array.prototype.map.call(equipes, function (item) { return item.value; });

    var periodo = inicio && inicio.value ? formatarData(inicio.value) : "";
    if (fim && fim.value) periodo += " a " + formatarData(fim.value);

    definirResumo("resumo-periodo", periodo);
    definirResumo("resumo-municipio", textoSelecionado("municipio"));
    definirResumo("resumo-tipo", textoSelecionado("tipo_evento"));
    definirResumo("resumo-equipes", nomesEquipes.join(", "));
    definirResumo("resumo-servidores", quantidadeServidores && quantidadeServidores.value);
    definirResumo("resumo-cin", quantidadeCin && quantidadeCin.value);

    var regiao = document.getElementById("id_regiao");
    if (regiao && municipio) regiao.value = regioesPorMunicipio[municipio.value] || "";

    var mes = document.getElementById("id_mes_evento");
    if (mes) {
      mes.value = inicio && inicio.value ? meses[Number(inicio.value.split("-")[1]) - 1] : "";
    }

    marcarChecklist("contato", contato && contato.value.trim());
    marcarChecklist("periodo", inicio && inicio.value && fim && fim.value);
    marcarChecklist("municipio", municipio && municipio.value);
    marcarChecklist("servicos", servicos.length);
    marcarChecklist("equipe", equipes.length);
    marcarChecklist(
      "quantidades",
      quantidadeServidores && quantidadeServidores.value && quantidadeCin && quantidadeCin.value
    );
  }

  var dataSolicitacao = campo("data_solicitacao");
  if (dataSolicitacao && !dataSolicitacao.value) {
    var hoje = new Date();
    var deslocamento = hoje.getTimezoneOffset() * 60000;
    dataSolicitacao.value = new Date(hoje.getTime() - deslocamento).toISOString().slice(0, 10);
  }

  formulario.addEventListener("input", atualizarAcompanhamento);
  formulario.addEventListener("change", atualizarAcompanhamento);
  atualizarAcompanhamento();
})();
