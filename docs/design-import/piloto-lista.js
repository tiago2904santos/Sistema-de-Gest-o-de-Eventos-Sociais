/* Página-piloto — Solicitações de Eventos Sociais (lista)
   Componentes globais renderizados a partir de dados. Nada de estilo local. */

const IC = {
  search:'<path d="M7.2 12.4a5.2 5.2 0 1 0 0-10.4 5.2 5.2 0 0 0 0 10.4ZM11 11l3 3"/>',
  filter:'<path d="M2.5 4h11M4.5 8h7M6.5 12h3"/>',
  chevD:'<path d="M4 6.5 8 10.5l4-4"/>',
  chevR:'<path d="M6 3.5 10.5 8 6 12.5"/>',
  chevL:'<path d="M10 3.5 5.5 8 10 12.5"/>',
  up:'<path d="M8 12.5V3.5M4.5 7 8 3.5 11.5 7"/>',
  down:'<path d="M8 3.5v9M4.5 9 8 12.5 11.5 9"/>',
  sort:'<path d="M5 6.5 7.5 4l2.5 2.5M5 9.5 7.5 12l2.5-2.5"/>',
  kebab:'<circle cx="8" cy="3.2" r="1.15"/><circle cx="8" cy="8" r="1.15"/><circle cx="8" cy="12.8" r="1.15"/>',
  plus:'<path d="M8 3.5v9M3.5 8h9"/>',
  download:'<path d="M8 2.5v7.5M5 7.5 8 10.5l3-3M3 13h10"/>',
  columns:'<path d="M2.5 3h11v10h-11zM6.2 3v10M9.8 3v10"/>',
  gavel:'<path d="M3 13h6M9.5 2.5 13 6M11.2 4.2 5.5 9.9M8 6.7l1.3 1.3"/>',
  check:'<path d="M3 8.5 6.2 11.7 13 4.9"/>',
  pencil:'<path d="M11.5 2.8 13.2 4.5 5.7 12H4v-1.7z"/>',
  eye:'<path d="M1.8 8S4 4 8 4s6.2 4 6.2 4S12 12 8 12 1.8 8 1.8 8Z"/><circle cx="8" cy="8" r="1.7"/>',
  trash:'<path d="M3 4.5h10M6 4.5V3h4v1.5M4.3 4.5l.6 8.5h6.2l.6-8.5"/>',
  x:'<path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/>',
  cal:'<path d="M2.5 4h11v9.5h-11zM2.5 7h11M5.5 2.5v2M10.5 2.5v2"/>',
  doc:'<path d="M4 2h5l3 3v9H4zM9 2v3h3"/>',
  bell:'<path d="M4 7a4 4 0 0 1 8 0v3l1.2 2H2.8L4 10z"/><path d="M6.6 12.8a1.5 1.5 0 0 0 2.8 0"/>',
  grid:'<path d="M2.5 2.5h5v5h-5zM8.5 2.5h5v5h-5zM2.5 8.5h5v5h-5zM8.5 8.5h5v5h-5"/>',
  help:'<circle cx="8" cy="8" r="6"/><path d="M6.4 6.2A1.7 1.7 0 0 1 9.6 7c0 1.1-1.6 1.3-1.6 2.4M8 11.6v.01"/>',
  info:'<circle cx="8" cy="8" r="6"/><path d="M8 7.3v4M8 4.9v.01"/>',
  alert:'<path d="M8 2.6 14 13H2z"/><path d="M8 6.4v3.1M8 11.3v.01"/>',
  inbox:'<path d="M2.5 8.5 4 3h8l1.5 5.5v4.5h-11zM2.5 8.5h3l.8 1.7h3.4l.8-1.7h3"/>'
};
const svg = (n, cls) => `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"${cls?` class="${cls}"`:''} aria-hidden="true">${IC[n]}</svg>`;

const STATUS = {
  RASCUNHO:'Rascunho', AGUARDANDO_DESPACHO:'Aguardando despacho', DEVOLVIDA:'Devolvida para ajuste',
  DEFERIDA_EM_ANDAMENTO:'Deferida — em andamento', ATENDIDA:'Atendida', NAO_ATENDIDA:'Não atendida', CANCELADA:'Cancelada'
};

// Filas conforme solicitacoes/views.py :: FILAS (contagens de exemplo)
const FILAS = [
  {chave:'', rotulo:'Todas', total:186},
  {chave:'despacho', rotulo:'Aguardando despacho', total:14},
  {chave:'devolvidas', rotulo:'Devolvidas para ajuste', total:5},
  {chave:'andamento', rotulo:'Deferidas', total:38},
  {chave:'canceladas', rotulo:'Canceladas', total:9},
  {chave:'rascunhos', rotulo:'Meus rascunhos', total:3},
  {chave:'minhas', rotulo:'Minhas', total:27}
];

// Colunas ordenáveis conforme views.py :: ORDENACOES / _colunas_ordenaveis
const COLUNAS = [
  {chave:'numero', rotulo:'Nº', fixa:true},
  {chave:'status', rotulo:'Status', fixa:true},
  {chave:'tipo', rotulo:'Tipo de evento'},
  {chave:'municipio', rotulo:'Município'},
  {chave:'periodo', rotulo:'Período do evento'},
  {chave:'solicitante', rotulo:'Solicitante'},
  {chave:'data', rotulo:'Data da solicitação'}
];

const D = (s) => { const [d,m,a] = s.split('/'); return new Date(+a, +m-1, +d); };
const LINHAS = [
  {id:216, municipio:'Curitiba', tipo:'Ciclo de palestras', inicio:'18/09/2026', fim:'19/09/2026', solicitante:'Cel. Marcos A. Ribeiro', unidade:'Diretoria-Geral', data:'30/08/2026', status:'AGUARDANDO_DESPACHO'},
  {id:215, municipio:'Londrina', tipo:'Ação social', inicio:'12/09/2026', fim:'12/09/2026', solicitante:'Del. Ana Paula Moreira', unidade:'1ª SDP Londrina', data:'29/08/2026', status:'AGUARDANDO_DESPACHO'},
  {id:214, municipio:'Ponta Grossa', tipo:'Feira de serviços', inicio:'26/09/2026', fim:'27/09/2026', solicitante:'Inv. Rafael Kwiatkowski', unidade:'SDP Ponta Grossa', data:'28/08/2026', status:'DEFERIDA_EM_ANDAMENTO'},
  {id:213, municipio:'Maringá', tipo:'Palestra educativa', inicio:'05/09/2026', fim:'05/09/2026', solicitante:'Esc. Juliana Ferraz', unidade:'2ª SDP Maringá', data:'27/08/2026', status:'DEVOLVIDA'},
  {id:212, municipio:'Foz do Iguaçu', tipo:'Ação social', inicio:'20/08/2026', fim:'21/08/2026', solicitante:'Del. Carlos E. Nunes', unidade:'SDP Foz do Iguaçu', data:'25/08/2026', status:'ATENDIDA'},
  {id:211, municipio:'Cascavel', tipo:'Mutirão de cidadania', inicio:'03/10/2026', fim:'04/10/2026', solicitante:'Cel. Marcos A. Ribeiro', unidade:'Diretoria-Geral', data:'24/08/2026', status:'DEFERIDA_EM_ANDAMENTO'},
  {id:210, municipio:'São José dos Pinhais', tipo:'Feira de serviços', inicio:'', fim:'', solicitante:'Insp. Fernanda Lopes', unidade:'SDP São José dos Pinhais', data:'22/08/2026', status:'RASCUNHO'},
  {id:209, municipio:'Guarapuava', tipo:'Palestra educativa', inicio:'14/08/2026', fim:'14/08/2026', solicitante:'Esc. Bruno Tavares', unidade:'SDP Guarapuava', data:'20/08/2026', status:'NAO_ATENDIDA'},
  {id:208, municipio:'Paranaguá', tipo:'Ação social', inicio:'09/09/2026', fim:'09/09/2026', solicitante:'Del. Ana Paula Moreira', unidade:'SDP Paranaguá', data:'19/08/2026', status:'CANCELADA'},
  {id:207, municipio:'Colombo', tipo:'Ciclo de palestras', inicio:'22/09/2026', fim:'24/09/2026', solicitante:'Inv. Rafael Kwiatkowski', unidade:'SDP Colombo', data:'18/08/2026', status:'DEFERIDA_EM_ANDAMENTO'},
  {id:206, municipio:'Toledo', tipo:'Mutirão de cidadania', inicio:'11/08/2026', fim:'12/08/2026', solicitante:'Esc. Juliana Ferraz', unidade:'SDP Toledo', data:'15/08/2026', status:'ATENDIDA'},
  {id:205, municipio:'Apucarana', tipo:'Feira de serviços', inicio:'', fim:'', solicitante:'Insp. Fernanda Lopes', unidade:'SDP Apucarana', data:'14/08/2026', status:'RASCUNHO'}
];

// Regras de ação preservadas de pages/solicitacoes/lista.html (linha.acoes.*)
function acoes(s){
  const st = s.status;
  const primaria = st==='AGUARDANDO_DESPACHO' ? {rot:'Despachar', ic:'gavel'}
    : st==='DEFERIDA_EM_ANDAMENTO' ? {rot:'Confirmar', ic:'check'}
    : (st==='RASCUNHO'||st==='DEVOLVIDA') ? {rot:'Continuar', ic:'pencil'}
    : {rot:'Detalhes', ic:'eye'};
  return {primaria, editar: st==='RASCUNHO'||st==='DEVOLVIDA', excluir: st==='RASCUNHO'};
}

const st = {
  viewport:'desktop', dados:'dados', avancados:false, aplicados:false, densidade:'padrao',
  ordem:'data', desc:true, fila:'', selecionada:null,
  colunas: Object.fromEntries(COLUNAS.map(c=>[c.chave,true]))
};

const periodo = (l) => !l.inicio ? '<span class="texto-fraco">—</span>' : (l.fim && l.fim!==l.inicio ? `${l.inicio} <span class="texto-suave">a</span> ${l.fim}` : l.inicio);

function ordenadas(){
  const k = st.ordem, dir = st.desc ? -1 : 1;
  const val = l => k==='numero' ? l.id : k==='periodo' ? (l.inicio?D(l.inicio).getTime():0) : k==='data' ? D(l.data).getTime()
    : k==='status' ? STATUS[l.status] : k==='tipo' ? l.tipo : k==='solicitante' ? l.solicitante : l.municipio;
  return [...LINHAS].sort((a,b)=>{const x=val(a),y=val(b);return (typeof x==='number'? x-y : String(x).localeCompare(String(y),'pt-BR'))*dir});
}

function cabecalho(){
  return COLUNAS.filter(c=>st.colunas[c.chave]).map(c=>{
    const ativa = st.ordem===c.chave;
    const ic = ativa ? (st.desc?'down':'up') : 'sort';
    return `<th data-col="${c.chave}"${ativa?` aria-sort="${st.desc?'descending':'ascending'}"`:''}${c.chave==='numero'?' style="width:1%"':''}>
      <button class="ordenar" data-ordenar="${c.chave}" title="Ordenar por ${c.rotulo}">${c.rotulo}${svg(ic)}</button></th>`;
  }).join('');
}

function linha(l){
  const a = acoes(l), sel = st.selecionada===l.id;
  const cel = {
    numero:`<td class="col-num" data-rot="Nº" data-cartao="meta" data-col="numero"><a href="#detalhe-${l.id}">#${l.id}</a></td>`,
    municipio:`<td class="celula-forte celula-nowrap" data-rot="Município" data-col="municipio"><span>${l.municipio}</span></td>`,
    tipo:`<td class="celula-forte celula-nowrap" data-rot="Tipo de evento" data-cartao="titulo" data-col="tipo">${l.tipo}</td>`,
    periodo:`<td class="num celula-nowrap" data-rot="Período" data-col="periodo"><span>${periodo(l)}</span></td>`,
    solicitante:`<td data-rot="Solicitante" data-col="solicitante"><span class="celula-2linhas">${l.solicitante}<small>${l.unidade}</small></span></td>`,
    data:`<td class="num texto-suave" data-rot="Data da solicitação" data-col="data"><span>${l.data}</span></td>`,
    status:`<td data-rot="Status" data-cartao="meta" data-col="status"><span class="badge badge--${l.status.toLowerCase()}">${STATUS[l.status]}</span></td>`
  };
  const corpo = COLUNAS.filter(c=>st.colunas[c.chave]).map(c=>cel[c.chave]).join('');
  return `<tr data-id="${l.id}"${sel?' aria-selected="true"':''} tabindex="0">
    ${corpo}
    <td class="td-acoes" data-cartao="acoes">
      <div class="linha-acoes">
        <a class="btn btn--secundaria btn--sm linha-acao" href="#acao-${l.id}">${svg(a.primaria.ic)}${a.primaria.rot}</a>
        <div class="dropdown linha-acao">
          <button class="icon-btn icon-btn--sm" data-kebab="${l.id}" aria-haspopup="true" aria-expanded="false" aria-label="Mais ações da solicitação #${l.id}">${svg('kebab')}</button>
          <div class="dropdown__corpo" hidden data-kebab-corpo="${l.id}">
            <div class="dropdown__titulo">Solicitação #${l.id}</div>
            <a class="dropdown__item" href="#detalhe-${l.id}">${svg('eye')}Detalhes</a>
            ${a.editar?`<a class="dropdown__item" href="#editar-${l.id}">${svg('pencil')}Editar</a>`:''}
            <a class="dropdown__item" href="#historico-${l.id}">${svg('doc')}Histórico</a>
            ${a.excluir?`<div class="dropdown__sep"></div><button class="dropdown__item dropdown__item--perigo">${svg('trash')}Excluir</button>`:''}
          </div>
        </div>
      </div>
    </td>
    <td class="td-abrir" data-cartao="abrir">${svg('chevR')}</td></tr>`;
}

const CHIPS = [
  {k:'status', r:'Status', v:'Aguardando despacho'},
  {k:'municipio', r:'Município', v:'Curitiba'},
  {k:'inicio', r:'Eventos a partir de', v:'01/09/2026'}
];

function render(){
  const total = st.dados==='dados' ? (st.aplicados ? 14 : 186) : 0;
  const linhas = st.dados==='dados' ? ordenadas().slice(0, st.aplicados?4:12) : [];
  const nAplic = st.aplicados ? CHIPS.length : 0;
  const app = document.querySelector('#app-conteudo');

  const filtros = `
  <div class="filter-bar">
    <div class="campo search filter-bar__busca">
      ${svg('search')}
      <input class="controle" type="search" id="q" placeholder="Buscar por nº, solicitante, local ou município" value="${st.aplicados?'':''}" aria-label="Buscar solicitações">
    </div>
    <div class="filter-bar__sep" aria-hidden="true"></div>
    <select class="controle controle--filtro filter-bar__sel" aria-label="Status" ${st.aplicados?'':'data-vazio'} style="width:auto">
      ${st.aplicados?'<option>Aguardando despacho</option>':'<option>Todos os status</option>'}
      ${Object.values(STATUS).map(s=>`<option>${s}</option>`).join('')}
    </select>
    <select class="controle controle--filtro filter-bar__sel" aria-label="Município" ${st.aplicados?'':'data-vazio'} style="width:auto">
      ${st.aplicados?'<option>Curitiba</option>':'<option>Todos os municípios</option>'}
      <option>Londrina</option><option>Maringá</option><option>Ponta Grossa</option>
    </select>
    <select class="controle controle--filtro filter-bar__sel" aria-label="Tipo de evento" data-vazio style="width:auto">
      <option>Todos os tipos</option><option>Ação social</option><option>Feira de serviços</option><option>Palestra educativa</option><option>Ciclo de palestras</option><option>Mutirão de cidadania</option>
    </select>
    <button class="btn btn--secundaria filter-toggle" data-toggle-avancados aria-expanded="${st.avancados}" aria-controls="filtros-avancados">
      ${svg('filter')}Filtros avançados${nAplic?`<span class="filter-toggle__n">${nAplic}</span>`:''}${svg('chevD')}
    </button>
    ${nAplic?`<button class="btn btn--discreta" data-limpar>Limpar filtros</button>`:''}
  </div>
  <div class="filter-panel" id="filtros-avancados"${st.avancados?'':' hidden'}>
    <div class="filter-panel__grid">
      <label class="campo"><span class="campo__label">Eventos a partir de</span><input class="controle" type="date" value="${st.aplicados?'2026-09-01':''}"></label>
      <label class="campo"><span class="campo__label">Eventos até</span><input class="controle" type="date"></label>
      <label class="campo"><span class="campo__label">Data da solicitação — de</span><input class="controle" type="date"></label>
      <label class="campo"><span class="campo__label">Data da solicitação — até</span><input class="controle" type="date"></label>
      <label class="campo"><span class="campo__label">Unidade solicitante</span><select class="controle"><option>Todas as unidades</option><option>Diretoria-Geral</option><option>1ª SDP Londrina</option><option>SDP Ponta Grossa</option></select></label>
      <label class="campo"><span class="campo__label">Decisão da DG</span><select class="controle"><option>Todas</option><option>Pendente</option><option>Atender</option><option>Não atender</option><option>Evento cancelado</option></select></label>
    </div>
    <div class="filter-panel__pe">
      <span class="filter-panel__dica">Os filtros são aplicados automaticamente ao alterar cada campo.</span>
      <div class="action-bar">
        <button class="btn btn--discreta" data-limpar>Limpar tudo</button>
        <button class="btn btn--secundaria" data-toggle-avancados>Recolher</button>
      </div>
    </div>
  </div>
  ${nAplic?`<div class="chips"><span class="texto-suave">Filtros ativos:</span>
    ${CHIPS.map(c=>`<span class="chip"><span>${c.r}:</span><b>${c.v}</b><button aria-label="Remover filtro ${c.r}" data-limpar-chip="${c.k}">${svg('x')}</button></span>`).join('')}
  </div>`:''}`;

  const vazio = st.aplicados || st.dados==='sem-resultado'
    ? `<div class="empty"><div class="empty__icone">${svg('search')}</div>
       <h3>Nenhuma solicitação corresponde aos filtros</h3>
       <p>Não há registros para <b>Aguardando despacho</b> em <b>Curitiba</b> a partir de 01/09/2026. Remova um filtro para ampliar o resultado.</p>
       <div class="empty__acoes"><button class="btn btn--secundaria" data-limpar>Limpar filtros</button><button class="btn btn--discreta" data-toggle-avancados>Revisar filtros avançados</button></div></div>`
    : `<div class="empty"><div class="empty__icone">${svg('inbox')}</div>
       <h3>Nenhuma solicitação registrada</h3>
       <p>Quando uma solicitação de evento social for registrada, ela aparecerá aqui com o status do fluxo e o histórico de despacho.</p>
       <div class="empty__acoes"><a class="btn btn--primaria" href="#nova">${svg('plus')}Nova solicitação</a></div></div>`;

  const tabela = linhas.length ? `
    <div class="tabela-scroll">
      <table class="tabela${st.densidade==='conforto'?' tabela--conforto':''}">
        <thead><tr>${cabecalho()}<th style="width:1%"><span class="sr-only">Ações</span></th><th style="width:1%"><span class="sr-only">Abrir</span></th></tr></thead>
        <tbody>${linhas.map(linha).join('')}</tbody>
      </table>
    </div>
    <div class="paginacao">
      <span class="paginacao__info">Mostrando <b>1–${linhas.length}</b> de ${total} solicitações</span>
      <nav class="paginacao__nav" aria-label="Paginação">
        <button class="paginacao__passo" aria-disabled="true">${svg('chevL')}Anterior</button>
        <button class="paginacao__n" aria-current="page">1</button>
        ${total>50?`<button class="paginacao__n">2</button><button class="paginacao__n">3</button><button class="paginacao__n">4</button><span class="paginacao__elipse">…</span><button class="paginacao__n">16</button>`:''}
        <button class="paginacao__passo"${total>50?'':' aria-disabled="true"'}>Próxima${svg('chevR')}</button>
      </nav>
      <label class="paginacao__tam">Por página <select><option>12</option><option>25</option><option>50</option></select></label>
    </div>` : vazio;

  const filaAtiva = st.aplicados ? 'despacho' : st.fila;

  app.innerHTML = `
  <nav class="breadcrumb"><a href="#">Início</a>${svg('chevR')}<a href="#">Eventos Sociais</a>${svg('chevR')}<span>Solicitações</span></nav>
  <header class="page-header">
    <div class="page-header__t">
      <div class="eyebrow eyebrow--acento">Eventos Sociais</div>
      <h1>Solicitações de Eventos Sociais</h1>
      <p class="page-header__sub">Acompanhe e gerencie as solicitações registradas${st.dados==='dados'?` · <b>14</b> aguardando despacho`:''}</p>
    </div>
    <div class="action-bar">
      <div class="dropdown">
        <button class="btn btn--secundaria" data-menu="colunas" aria-haspopup="true" aria-expanded="false">${svg('columns')}Colunas${svg('chevD')}</button>
        <div class="dropdown__corpo" hidden data-menu-corpo="colunas">
          <div class="dropdown__titulo">Colunas visíveis</div>
          ${COLUNAS.filter(c=>!c.fixa).map(c=>`<label class="check" style="padding:5px 12px"><input type="checkbox" data-coluna="${c.chave}"${st.colunas[c.chave]?' checked':''}>${c.rotulo}</label>`).join('')}
        </div>
      </div>
      <a class="btn btn--secundaria" href="#exportar">${svg('download')}Exportar CSV</a>
      <a class="btn btn--primaria" href="#nova">${svg('plus')}Nova solicitação</a>
    </div>
  </header>
  <div style="height:var(--s-5)"></div>
  <div class="tabs" role="tablist">
    ${FILAS.map(f=>`<button class="tab" role="tab" data-fila="${f.chave}" aria-selected="${filaAtiva===f.chave}">${f.rotulo}<span class="tab__n">${f.chave==='despacho'&&st.aplicados?14:f.total}</span></button>`).join('')}
  </div>
  ${filtros}
  ${linhas.length?`<div class="tabela-topo">
    <span class="tabela-topo__cont"><b>${total}</b> solicitaç${total===1?'ão':'ões'}${nAplic?' com os filtros aplicados':''}</span>
    <span class="tabela-topo__cont">Ordenado por <b>${COLUNAS.find(c=>c.chave===st.ordem).rotulo}</b> ${st.desc?'(mais recente primeiro)':'(crescente)'}</span>
  </div>`:''}
  ${tabela}`;
}

/* --- interações ---------------------------------------------------------- */
function fecharMenus(exceto){
  document.querySelectorAll('[data-kebab-corpo],[data-menu-corpo]').forEach(c=>{
    if(c!==exceto){c.hidden=true;const g=c.previousElementSibling;if(g&&g.hasAttribute('aria-expanded'))g.setAttribute('aria-expanded','false');}
  });
}

document.addEventListener('click', e=>{
  const t = e.target;
  const q = (s)=>t.closest(s);
  if(q('[data-toggle-avancados]')){st.avancados=!st.avancados;render();return}
  if(q('[data-limpar]')||q('[data-limpar-chip]')){st.aplicados=false;sincronizarPainel();render();return}
  const ord = q('[data-ordenar]');
  if(ord){const k=ord.dataset.ordenar; if(st.ordem===k){st.desc=!st.desc}else{st.ordem=k;st.desc=(k==='data'||k==='numero'||k==='periodo')} render();return}
  const fila = q('[data-fila]');
  if(fila){st.fila=fila.dataset.fila;if(st.fila!=='despacho')st.aplicados=false;sincronizarPainel();render();return}
  const kebab = q('[data-kebab]');
  if(kebab){const c=kebab.parentElement.querySelector('[data-kebab-corpo]');const abrir=c.hidden;fecharMenus();c.hidden=!abrir;kebab.setAttribute('aria-expanded',String(abrir));e.preventDefault();return}
  const menu = q('[data-menu]');
  if(menu){const c=menu.parentElement.querySelector('[data-menu-corpo]');const abrir=c.hidden;fecharMenus();c.hidden=!abrir;menu.setAttribute('aria-expanded',String(abrir));return}
  if(q('[data-coluna]')){const cb=q('[data-coluna]');st.colunas[cb.dataset.coluna]=cb.checked;render();
    const c=document.querySelector('[data-menu-corpo="colunas"]');if(c){c.hidden=false;document.querySelector('[data-menu="colunas"]').setAttribute('aria-expanded','true')}return}
  if(q('.dropdown__corpo')) return;
  fecharMenus();
  const tr = q('tbody tr');
  if(tr && !q('a.btn') && !q('.icon-btn')){st.selecionada = st.selecionada===+tr.dataset.id ? null : +tr.dataset.id; render()}
});
document.addEventListener('keydown', e=>{ if(e.key==='Escape') fecharMenus(); });

/* --- painel de revisão --------------------------------------------------- */
function sincronizarPainel(){
  document.querySelectorAll('[data-set]').forEach(b=>{
    const [k,v] = b.dataset.set.split(':');
    const val = k==='avancados'||k==='aplicados' ? String(st[k]) : st[k];
    b.setAttribute('aria-pressed', String(val===v));
  });
}
document.addEventListener('click', e=>{
  const b = e.target.closest('[data-set]'); if(!b) return;
  const [k,v] = b.dataset.set.split(':');
  st[k] = (v==='true') ? true : (v==='false') ? false : v;
  if(k==='aplicados' && st[k]) st.dados='dados';
  if(k==='dados' && v!=='dados') st.aplicados=false;
  if(k==='viewport') document.body.dataset.viewport = v;
  sincronizarPainel(); render();
});

document.body.dataset.viewport = 'desktop';
sincronizarPainel();
render();
