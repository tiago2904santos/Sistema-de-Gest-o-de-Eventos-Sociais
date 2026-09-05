/* Padrão de Listagem — MOBILE · composição própria (app shell + data list)
   Reaproveita ícones/dados do padrão desktop (piloto-v3-2.js), mas gera
   marcação e interações mobile-nativas: nada de tabela + scroll horizontal. */

const IC={
search:'<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
'chevron-down':'<path d="m6 9 6 6 6-6"/>',
'chevron-left':'<path d="m15 18-6-6 6-6"/>',
'chevron-right':'<path d="m9 18 6-6-6-6"/>',
'arrow-up-down':'<path d="m21 16-4 4-4-4"/><path d="M17 20V4"/><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/>',
kebab:'<circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/>',
plus:'<path d="M5 12h14"/><path d="M12 5v14"/>',
check:'<path d="M20 6 9 17l-5-5"/>',
x:'<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
eye:'<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
pencil:'<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
gavel:'<path d="m14.5 12.5-8 8a2.119 2.119 0 1 1-3-3l8-8"/><path d="m16 16 6-6"/><path d="m8 8 6-6"/><path d="m9 7 8 8"/><path d="m21 11-8-8"/>',
trash:'<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',
document:'<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
bell:'<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
info:'<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
undo:'<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
inbox:'<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11"/>',
'search-x':'<path d="m13.5 8.5-5 5"/><path d="m8.5 8.5 5 5"/><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>'};
const s=(n)=>`<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${IC[n]}</svg>`;

const STATUS={RASCUNHO:'Rascunho',AGUARDANDO_DESPACHO:'Aguardando despacho',DEVOLVIDA:'Devolvida para ajuste',DEFERIDA_EM_ANDAMENTO:'Deferida — em andamento',ATENDIDA:'Atendida',NAO_ATENDIDA:'Não atendida',CANCELADA:'Cancelada'};

const FILAS=[
{chave:'',rotulo:'Todas',total:186,grupo:0},
{chave:'despacho',rotulo:'Aguardando despacho',total:14,grupo:1,status:['AGUARDANDO_DESPACHO']},
{chave:'devolvidas',rotulo:'Devolvidas para ajuste',total:5,grupo:1,status:['DEVOLVIDA']},
{chave:'andamento',rotulo:'Deferidas',total:38,grupo:1,status:['DEFERIDA_EM_ANDAMENTO','ATENDIDA']},
{chave:'canceladas',rotulo:'Canceladas',total:9,grupo:1,status:['CANCELADA']},
{chave:'rascunhos',rotulo:'Meus rascunhos',total:3,grupo:2,status:['RASCUNHO']},
{chave:'minhas',rotulo:'Minhas',total:27,grupo:2}];

const MUNICIPIOS=['Curitiba','Londrina','Maringá','Ponta Grossa','Cascavel','Foz do Iguaçu','São José dos Pinhais','Colombo','Guarapuava','Paranaguá','Toledo','Apucarana'];
const TIPOS=['Ação social','Feira de serviços','Palestra educativa','Ciclo de palestras','Mutirão de cidadania'];
const UNIDADES=['Diretoria-Geral','1ª SDP Londrina','2ª SDP Maringá','SDP Ponta Grossa','SDP Foz do Iguaçu','SDP Colombo'];
const DECISOES=['Pendente','Atender','Não atender','Evento cancelado'];

const ORDENS=[
{k:'data',desc:true,r:'Mais recentes primeiro'},
{k:'data',desc:false,r:'Mais antigas primeiro'},
{k:'periodo',desc:false,r:'Evento mais próximo'},
{k:'numero',desc:true,r:'Número (maior primeiro)'},
{k:'municipio',desc:false,r:'Município (A–Z)'},
{k:'status',desc:false,r:'Status (A–Z)'}];

const L=[
{id:216,mun:'Curitiba',tipo:'Ciclo de palestras',ini:'18/09/2026',fim:'19/09/2026',sol:'Cel. Marcos A. Ribeiro',un:'Diretoria-Geral',data:'30/08/2026',st:'AGUARDANDO_DESPACHO'},
{id:215,mun:'Londrina',tipo:'Ação social',ini:'12/09/2026',fim:'12/09/2026',sol:'Del. Ana Paula Moreira',un:'1ª SDP Londrina',data:'29/08/2026',st:'AGUARDANDO_DESPACHO'},
{id:214,mun:'Ponta Grossa',tipo:'Feira de serviços',ini:'26/09/2026',fim:'27/09/2026',sol:'Inv. Rafael Kwiatkowski',un:'SDP Ponta Grossa',data:'28/08/2026',st:'DEFERIDA_EM_ANDAMENTO'},
{id:213,mun:'Maringá',tipo:'Palestra educativa',ini:'05/09/2026',fim:'05/09/2026',sol:'Esc. Juliana Ferraz',un:'2ª SDP Maringá',data:'27/08/2026',st:'DEVOLVIDA'},
{id:212,mun:'Foz do Iguaçu',tipo:'Ação social',ini:'20/08/2026',fim:'21/08/2026',sol:'Del. Carlos E. Nunes',un:'SDP Foz do Iguaçu',data:'25/08/2026',st:'ATENDIDA'},
{id:211,mun:'Cascavel',tipo:'Mutirão de cidadania',ini:'28/09/2026',fim:'02/10/2026',sol:'Cel. Marcos A. Ribeiro',un:'Diretoria-Geral',data:'24/08/2026',st:'DEFERIDA_EM_ANDAMENTO'},
{id:210,mun:'São José dos Pinhais',tipo:'Feira de serviços',ini:'',fim:'',sol:'Insp. Fernanda Lopes',un:'SDP São José dos Pinhais',data:'22/08/2026',st:'RASCUNHO'},
{id:209,mun:'Guarapuava',tipo:'Palestra educativa',ini:'14/08/2026',fim:'14/08/2026',sol:'Esc. Bruno Tavares',un:'SDP Guarapuava',data:'20/08/2026',st:'NAO_ATENDIDA'},
{id:208,mun:'Paranaguá',tipo:'Ação social',ini:'09/09/2026',fim:'09/09/2026',sol:'Del. Ana Paula Moreira',un:'SDP Paranaguá',data:'19/08/2026',st:'CANCELADA'},
{id:207,mun:'Colombo',tipo:'Ciclo de palestras',ini:'22/09/2026',fim:'24/09/2026',sol:'Inv. Rafael Kwiatkowski',un:'SDP Colombo',data:'18/08/2026',st:'DEFERIDA_EM_ANDAMENTO'},
{id:206,mun:'Toledo',tipo:'Mutirão de cidadania',ini:'11/08/2026',fim:'12/08/2026',sol:'Esc. Juliana Ferraz',un:'SDP Toledo',data:'15/08/2026',st:'ATENDIDA'},
{id:205,mun:'Apucarana',tipo:'Feira de serviços',ini:'',fim:'',sol:'Insp. Fernanda Lopes',un:'SDP Apucarana',data:'14/08/2026',st:'RASCUNHO'}];

const acao=(st)=>st==='AGUARDANDO_DESPACHO'?{r:'Despachar',i:'gavel'}
 :st==='DEFERIDA_EM_ANDAMENTO'?{r:'Confirmar',i:'check'}
 :(st==='RASCUNHO'||st==='DEVOLVIDA')?{r:'Continuar',i:'pencil'}:null;

const est={fila:'',ordem:'data',desc:true,sel:null,cenario:'normal',
  f:{status:'',municipio:'',tipo:'',inicio:'',fim:'',unidade:'',decisao:''},
  sheetFiltros:false,sheetOrdenar:false,navAberta:false,forcarPressed:null,forcarMenu:null};

const ROTULOS={status:'Status',municipio:'Município',tipo:'Tipo de evento',inicio:'Eventos a partir de',fim:'Eventos até',unidade:'Unidade solicitante',decisao:'Decisão da DG'};
const nAtivos=()=>Object.values(est.f).filter(Boolean).length;
const D=(x)=>{const[d,m,a]=x.split('/');return new Date(+a,+m-1,+d)};

function per(l){
  if(!l.ini) return '—';
  if(!l.fim||l.fim===l.ini) return l.ini;
  return `${l.ini} – ${l.fim}`;
}
function filtradas(){
  const fila=FILAS.find(f=>f.chave===est.fila);
  return L.filter(l=>{
    if(fila&&fila.status&&!fila.status.includes(l.st)) return false;
    if(est.f.status&&STATUS[l.st]!==est.f.status) return false;
    if(est.f.municipio&&l.mun!==est.f.municipio) return false;
    if(est.f.tipo&&l.tipo!==est.f.tipo) return false;
    if(est.f.unidade&&l.un!==est.f.unidade) return false;
    if(est.f.inicio&&(!l.ini||D(l.ini)<new Date(est.f.inicio))) return false;
    if(est.f.fim&&(!l.ini||D(l.ini)>new Date(est.f.fim))) return false;
    return true;
  });
}
function ordenadas(rows){
  const k=est.ordem,dir=est.desc?-1:1;
  const v=l=>k==='numero'?l.id:k==='periodo'?(l.ini?D(l.ini).getTime():0):k==='data'?D(l.data).getTime()
    :k==='status'?STATUS[l.st]:k==='tipo'?l.tipo:l.mun;
  return [...rows].sort((a,b)=>{const x=v(a),y=v(b);return(typeof x==='number'?x-y:String(x).localeCompare(String(y),'pt-BR'))*dir});
}

function render(){
  const raiz=document.getElementById('folha-m');
  const rows=est.cenario==='vazio'?[]:ordenadas(filtradas());
  const fila=FILAS.find(f=>f.chave===est.fila);

  const cabeca=`
  <div class="m-cabeca">
    <div class="kicker">Eventos Sociais</div>
    <h1>Solicitações</h1>
    <p class="m-cabeca__sub">Acompanhe e gerencie as solicitações registradas no módulo.</p>
    <div class="m-kpis">
      <button class="m-kpi" data-fila=""><span class="m-kpi__ic" style="background:var(--n-100);color:var(--n-450)">${s('users')}</span><b>186</b><span>Total</span></button>
      <button class="m-kpi" data-fila="despacho"><span class="m-kpi__ic" style="background:var(--wn-b);color:#a8822a">${s('document')}</span><b>14</b><span>Aguardando</span></button>
      <button class="m-kpi" data-fila="devolvidas"><span class="m-kpi__ic" style="background:var(--dg-b);color:#b4483c">${s('undo')}</span><b>5</b><span>Devolvidas</span></button>
    </div>
    <button class="btn-primaria">${s('plus')}Nova solicitação</button>
  </div>`;

  const filas=`
  <div class="m-filas" role="tablist" aria-label="Filas de trabalho">
    ${FILAS.map(f=>`<button class="m-fila" role="tab" data-fila="${f.chave}"${est.fila===f.chave?' aria-current="page" aria-selected="true"':''}>${f.rotulo}<span class="m-fila__n">${f.total}</span></button>`).join('')}
  </div>`;

  const ferramentas=`
  <div class="m-ferramentas">
    <div class="m-busca">${s('search')}<input type="search" placeholder="Buscar solicitações" aria-label="Buscar solicitações"></div>
    <button class="m-bt" data-abrir="filtros">${s('inbox')}Filtros${nAtivos()?`<span class="m-bt__contagem">${nAtivos()}</span>`:''}</button>
    <button class="m-bt" data-abrir="ordenar">${s('arrow-up-down')}Ordenar</button>
  </div>`;

  let corpo;
  if(rows.length){
    corpo=`<div class="m-lista">${rows.map(l=>{
      const a=acao(l.st);
      const menuAberto=est.forcarMenu===l.id;
      return `<div class="m-item${est.forcarPressed===l.id?' pressionado':''}" data-id="${l.id}">
        <div class="m-item__topo"><span class="m-item__id"><i>#</i>${l.id}</span><span class="st st--${l.st.toLowerCase()}">${STATUS[l.st]}</span></div>
        <div class="m-item__tipo">${l.tipo}</div>
        <div class="m-item__meta">${l.mun} · ${per(l)}</div>
        <div class="m-item__sol">${l.sol}<small>${l.un} · Solicitado em ${l.data}</small></div>
        <div class="m-item__rodape">
          ${a?`<button class="acao-linha">${s(a.i)}${a.r}</button>`:'<span></span>'}
          <div class="dd"><button class="ib-linha" data-dd="km${l.id}" aria-haspopup="true" aria-expanded="${menuAberto}" aria-label="Mais ações da solicitação #${l.id}">${s('kebab')}</button>
            <div class="dd__c" ${menuAberto?'':'hidden'} data-dd-c="km${l.id}"><div class="dd__t">Solicitação #${l.id}</div>
              <button class="dd__i">${s('eye')}Detalhes</button>
              ${(l.st==='RASCUNHO'||l.st==='DEVOLVIDA')?`<button class="dd__i">${s('pencil')}Editar</button>`:''}
              <button class="dd__i">${s('document')}Histórico</button>
              ${l.st==='RASCUNHO'?`<div class="dd__s"></div><button class="dd__i dd__i--perigo">${s('trash')}Excluir</button>`:''}
            </div></div>
        </div>
      </div>`}).join('')}</div>
    <div class="m-pag">
      <button ${true?'disabled':''}>${s('chevron-left')}Anterior</button>
      <span class="m-pag__meio">Página 1 de ${Math.max(1,Math.ceil((fila?fila.total:186)/12))}</span>
      <button>Próxima${s('chevron-right')}</button>
    </div>
    <div class="m-pag__sel">Por página <select><option>12</option><option>25</option><option>50</option></select></div>`;
  } else if(est.cenario==='vazio'){
    corpo=`<div class="m-vazio"><span class="m-vazio__ic">${s('inbox')}</span><h3>Nenhuma solicitação aqui ainda</h3><p>Quando houver registros nesta fila, eles aparecerão nesta lista.</p><button class="btn-primaria">${s('plus')}Nova solicitação</button></div>`;
  } else {
    corpo=`<div class="m-vazio"><span class="m-vazio__ic">${s('search-x')}</span><h3>Nenhum resultado</h3><p>Nenhuma solicitação corresponde aos filtros aplicados.</p><button class="btn--secundaria" data-limpar>Limpar filtros</button></div>`;
  }

  raiz.innerHTML=cabeca+filas+ferramentas+corpo;

  const veu=document.getElementById('m-veu');
  const sf=document.getElementById('m-sheet-filtros');
  const so=document.getElementById('m-sheet-ordenar');
  veu.hidden=!(est.sheetFiltros||est.sheetOrdenar);
  sf.hidden=!est.sheetFiltros;
  so.hidden=!est.sheetOrdenar;
  if(est.sheetFiltros) sf.innerHTML=corpoFiltros();
  if(est.sheetOrdenar) so.innerHTML=corpoOrdenar();

  const drawer=document.getElementById('m-nav-drawer');
  drawer.hidden=!est.navAberta;
  document.getElementById('m-nav').toggleAttribute('data-aberto',est.navAberta);
}

function corpoFiltros(){
  const campo=(k,rot,opts)=>`<label class="campo"><span class="campo__label">${rot}</span><select class="ctrl" data-f="${k}"><option value="">Todos</option>${opts.map(o=>`<option${est.f[k]===o?' selected':''}>${o}</option>`).join('')}</select></label>`;
  return `<div class="m-sheet__alca"></div>
  <div class="m-sheet__topo"><h2>Filtros${nAtivos()?` · ${nAtivos()}`:''}</h2><button class="m-sheet__fechar" data-fechar-sheet>${s('x')}</button></div>
  <div class="m-sheet__corpo">
    ${campo('status','Status',Object.values(STATUS))}
    ${campo('tipo','Tipo de evento',TIPOS)}
    ${campo('municipio','Município',MUNICIPIOS)}
    <label class="campo"><span class="campo__label">Eventos a partir de</span><input class="ctrl" type="date" data-f="inicio" value="${est.f.inicio}"></label>
    <label class="campo"><span class="campo__label">Eventos até</span><input class="ctrl" type="date" data-f="fim" value="${est.f.fim}"></label>
    ${campo('unidade','Unidade solicitante',UNIDADES)}
    ${campo('decisao','Decisão da DG',DECISOES)}
  </div>
  <div class="m-sheet__rodape"><button class="btn--secundaria" data-limpar>Limpar filtros</button><button class="btn-primaria" data-fechar-sheet>Ver resultados</button></div>`;
}
function corpoOrdenar(){
  return `<div class="m-sheet__alca"></div>
  <div class="m-sheet__topo"><h2>Ordenar por</h2><button class="m-sheet__fechar" data-fechar-sheet>${s('x')}</button></div>
  <div class="m-sheet__corpo">
    ${ORDENS.map(o=>{const at=o.k===est.ordem&&o.desc===est.desc;return `<button class="m-op" data-ordem="${o.k}:${o.desc}"${at?' aria-current="true"':''}>${o.r}${at?s('check'):''}</button>`}).join('')}
  </div>`;
}

function fecharMenus(){est.forcarMenu=null;document.querySelectorAll('[data-dd-c]').forEach(c=>{c.hidden=true;const g=document.querySelector(`[data-dd="${c.dataset.ddC}"]`);if(g)g.setAttribute('aria-expanded','false')})}

document.addEventListener('click',e=>{
  const q=x=>e.target.closest(x);
  if(q('#seletor')) return;
  if(q('#m-nav-gatilho')){est.navAberta=!est.navAberta;render();return}
  const ni=q('.m-nav__item');
  if(ni){est.navAberta=false;render();return}
  const ab=q('[data-abrir]');
  if(ab){est.sheetFiltros=ab.dataset.abrir==='filtros';est.sheetOrdenar=ab.dataset.abrir==='ordenar';render();return}
  if(q('[data-fechar-sheet]')||q('#m-veu')){est.sheetFiltros=false;est.sheetOrdenar=false;render();return}
  const fc=q('[data-f]');
  // handled on change for selects/inputs
  const rm=q('[data-limpar]');
  if(rm){Object.keys(est.f).forEach(k=>est.f[k]='');est.sheetFiltros=false;render();return}
  const oi=q('[data-ordem]');
  if(oi){const[k,d]=oi.dataset.ordem.split(':');est.ordem=k;est.desc=d==='true';est.sheetOrdenar=false;render();return}
  const fila=q('[data-fila]');
  if(fila){est.fila=fila.dataset.fila;render();return}
  const g=q('[data-dd]');
  if(g){const c=document.querySelector(`[data-dd-c="${g.dataset.dd}"]`);const abrir=c.hidden;fecharMenus();c.hidden=!abrir;g.setAttribute('aria-expanded',String(abrir));return}
  if(q('.dd__c')) return;
  fecharMenus();
  const item=q('.m-item');
  if(item&&!q('.acao-linha')&&!q('.ib-linha')){est.sel=est.sel===+item.dataset.id?null:+item.dataset.id;render()}
});
document.addEventListener('change',e=>{
  const f=e.target.closest('[data-f]');
  if(f){est.f[f.dataset.f]=f.value;render()}
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){est.sheetFiltros=false;est.sheetOrdenar=false;est.navAberta=false;render()}});

render();
