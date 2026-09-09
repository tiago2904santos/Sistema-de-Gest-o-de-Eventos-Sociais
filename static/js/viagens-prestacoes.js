document.addEventListener("DOMContentLoaded", () => {
  const fonte = document.getElementById("rt-modelos");
  if (fonte) {
    const modelos = JSON.parse(fonte.textContent);
    document.querySelectorAll('select[name^="modelo_"]').forEach(select => select.addEventListener("change", () => {
      const campo = select.name.slice(7);
      const texto = document.querySelector(`[name="${campo}"]`);
      if (texto && modelos[select.value] !== undefined) texto.value = modelos[select.value];
    }));
  }
});

document.querySelectorAll('[data-excluir-anexo]').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {'X-Requested-With': 'XMLHttpRequest'}});
      if (!response.ok || !(await response.json()).ok) throw new Error('Não foi possível remover o anexo.');
      window.location.reload();
    } catch (error) { button.disabled = false; window.alert(error.message); }
  });
});

document.querySelectorAll('[data-anexar-multiplos]').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button'); button.disabled = true;
    try {
      const response = await fetch(form.action, {method:'POST', body:new FormData(form), headers:{'X-Requested-With':'XMLHttpRequest'}});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(Object.values(data.errors || {}).flat().join(' ') || data.message || 'Não foi possível anexar os arquivos.');
      window.location.reload();
    } catch(error) { button.disabled = false; window.alert(error.message); }
  });
});

(() => {
  const data = document.getElementById('dmv-oficios-source');
  const selector = document.getElementById('id_dmv_oficio');
  if (!data || !selector) return;
  const oficios = JSON.parse(data.textContent);
  const preencher = (name,value) => {
    const field=document.getElementById('id_'+name);
    if(field) {field.value=value || '';field.dispatchEvent(new Event('change',{bubbles:true}));}
  };
  selector.addEventListener('change', () => {
    const oficio=oficios.find(o=>String(o.id)===selector.value);
    if (!oficio) return;
    preencher('motorista_modo','outro');
    preencher('motorista_manual_nome',oficio.motorista_nome);
    preencher('motorista_manual_cpf',oficio.motorista_cpf);
    preencher('motorista_oficio_referencia',oficio.numero_ano);
    preencher('motorista_protocolo_ref',oficio.protocolo);
    preencher('viatura_modo',oficio.viatura.modo);
    preencher('viatura',oficio.viatura.id);
    ['modelo','placa','tipo','combustivel'].forEach(campo=>preencher('viatura_manual_'+campo,oficio.viatura[campo]));
  });
})();
