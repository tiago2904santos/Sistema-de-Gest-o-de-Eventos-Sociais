(() => {
  const dados = document.getElementById('oficio-modelos-texto');
  if (!dados) return;
  const modelos = JSON.parse(dados.textContent);
  Object.entries({'modelo_motivo': 'motivo', 'justificativa-modelo': 'justificativa-texto'}).forEach(([origem, destino]) => {
    const seletor = document.getElementById(`id_${origem}`);
    const texto = document.getElementById(`id_${destino}`);
    if (!seletor || !texto) return;
    seletor.addEventListener('change', () => {
      const valor = modelos[origem][seletor.value];
      if (valor !== undefined) {
        texto.value = valor;
        texto.dispatchEvent(new Event('input', {bubbles: true}));
      }
    });
  });
})();
