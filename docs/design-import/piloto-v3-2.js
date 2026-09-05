/* V3.2 — Solicitações de Eventos Sociais (lista) · desktop, estado com dados
   Ícones: desenhos do Lucide copiados de templates/components/icon.html
   (mesmos nomes usados por pages/solicitacoes/lista.html). */

const IC={
search:'<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
filter:'<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
'chevron-down':'<path d="m6 9 6 6 6-6"/>',
'chevron-left':'<path d="m15 18-6-6 6-6"/>',
'chevron-right':'<path d="m9 18 6-6-6-6"/>',
'arrow-up':'<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
'arrow-down':'<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
ordenar:'<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>',
kebab:'<circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/>',
columns:'<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="M15 3v18"/>',
download:'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
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
calendar:'<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
undo:'<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
landmark:'<path d="M10 18v-7"/><path d="M11.12 2.198a2 2 0 0 1 1.76.006l7.866 3.847c.476.233.31.949-.22.949H3.474c-.53 0-.695-.716-.22-.949z"/><path d="M14 18v-7"/><path d="M18 18v-7"/><path d="M3 22h18"/><path d="M6 18v-7"/>'};
const s=(n)=>`<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${IC[n]}</svg>`;

const STATUS={RASCUNHO:'Rascunho',AGUARDANDO_DESPACHO:'Aguardando despacho',DEVOLVIDA:'Devolvida para ajuste',DEFERIDA_EM_ANDAMENTO:'Deferida — em andamento',ATENDIDA:'Atendida',NAO_ATENDIDA:'Não atendida',CANCELADA:'Cancelada'};

/* Filas conforme solicitacoes/views.py :: FILAS */
const FILAS=[
{chave:'',rotulo:'Todas',total:186,grupo:0},
{chave:'despacho',rotulo:'Aguardando despacho',total:14,grupo:1,destaque:true,status:['AGUARDANDO_DESPACHO']},
{chave:'devolvidas',rotulo:'Devolvidas para ajuste',total:5,grupo:1,status:['DEVOLVIDA']},
{chave:'andamento',rotulo:'Deferidas',total:38,grupo:1,status:['DEFERIDA_EM_ANDAMENTO','ATENDIDA']},
{chave:'canceladas',rotulo:'Canceladas',total:9,grupo:1,status:['CANCELADA']},
{chave:'rascunhos',rotulo:'Meus rascunhos',total:3,grupo:2,status:['RASCUNHO']},
{chave:'minhas',rotulo:'Minhas',total:27,grupo:2}];

/* Colunas ordenáveis conforme views.py :: ORDENACOES */
const COLUNAS=[
{k:'numero',r:'Nº',fixa:true,cls:'c-id'},
{k:'status',r:'Status',fixa:true,cls:'c-status'},
{k:'tipo',r:'Tipo de evento',cls:'c-tipo'},
{k:'municipio',r:'Município',cls:'c-mun'},
{k:'periodo',r:'Período do evento',cls:'c-per'},
{k:'solicitante',r:'Solicitante',cls:'c-sol'},
{k:'data',r:'Data da solicitação',cls:'c-data'}];

const ORDENS=[
{k:'data',desc:true,r:'Mais recentes primeiro'},
{k:'data',desc:false,r:'Mais antigas primeiro'},
{k:'periodo',desc:false,r:'Evento mais próximo'},
{k:'numero',desc:true,r:'Número (maior primeiro)'},
{k:'municipio',desc:false,r:'Município (A–Z)'},
{k:'status',desc:false,r:'Status (A–Z)'}];

const MUNICIPIOS=['Curitiba','Londrina','Maringá','Ponta Grossa','Cascavel','Foz do Iguaçu','São José dos Pinhais','Colombo','Guarapuava','Paranaguá','Toledo','Apucarana'];
const TIPOS=['Ação social','Feira de serviços','Palestra educativa','Ciclo de palestras','Mutirão de cidadania'];
const UNIDADES=['Diretoria-Geral','1ª SDP Londrina','2ª SDP Maringá','SDP Ponta Grossa','SDP Foz do Iguaçu','SDP Colombo'];
const DECISOES=['Pendente','Atender','Não atender','Evento cancelado'];

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

/* Ação de workflow por estado — regras de pages/solicitacoes/lista.html.
   Estados terminais não recebem botão: a linha inteira abre os detalhes. */
const acao=(st)=>st==='AGUARDANDO_DESPACHO'?{r:'Despachar',i:'gavel'}
 :st==='DEFERIDA_EM_ANDAMENTO'?{r:'Confirmar',i:'check'}
 :(st==='RASCUNHO'||st==='DEVOLVIDA')?{r:'Continuar',i:'pencil'}:null;

const est={ordem:'data',desc:true,fila:'',sel:null,painel:false,cenario:'normal',
  f:{status:'',municipio:'',tipo:'',inicio:'',fim:'',unidade:'',decisao:''},
  cols:Object.fromEntries(COLUNAS.map(c=>[c.k,true]))};

const ROTULOS={status:'Status',municipio:'Município',tipo:'Tipo de evento',inicio:'Eventos a partir de',fim:'Eventos até',unidade:'Unidade solicitante',decisao:'Decisão da DG'};
const ativos=()=>Object.entries(est.f).filter(([,v])=>v);
const nAvancados=()=>['inicio','fim','unidade','decisao'].filter(k=>est.f[k]).length;

const D=(x)=>{const[d,m,a]=x.split('/');return new Date(+a,+m-1,+d)};
const iso=(x)=>{const[d,m,a]=x.split('/');return `${a}-${m}-${d}`};
const brl=(x)=>x?x.split('-').reverse().join('/'):'';

/* Período compacto, mantendo o padrão numérico institucional dd/mm/aaaa */
function per(l){
  if(!l.ini) return '<span class="vazio-traco">—</span>';
  if(!l.fim||l.fim===l.ini) return l.ini;
  return `${l.ini} <em>a</em> ${l.fim}`;
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
    :k==='status'?STATUS[l.st]:k==='tipo'?l.tipo:k==='solicitante'?l.sol:l.mun;
  return [...rows].sort((a,b)=>{const x=v(a),y=v(b);return(typeof x==='number'?x-y:String(x).localeCompare(String(y),'pt-BR'))*dir});
}
const rotuloOrdem=()=>COLUNAS.find(c=>c.k===est.ordem).r;
const direcaoOrdem=()=>{
  if(est.ordem==='data') return est.desc?'mais recente primeiro':'mais antiga primeiro';
  if(est.ordem==='periodo') return est.desc?'evento mais distante':'evento mais próximo';
  if(est.ordem==='numero') return est.desc?'maior primeiro':'menor primeiro';
  return est.desc?'Z–A':'A–Z';
};

/* Filter control: rótulo + valor; ganha destaque quando há valor */
function fc(campo,padrao,opcoes){
  const v=est.f[campo];
  return `<div class="dd"><button class="fc" data-dd="f-${campo}"${v?' data-ativo':''} aria-haspopup="true" aria-expanded="false">
      <span class="fc__rot">${ROTULOS[campo]}</span>${v||padrao}${s('chevron-down')}</button>
    <div class="dd__c dd__c--esq" hidden data-dd-c="f-${campo}"><div class="dd__t">${ROTULOS[campo]}</div>
      <button class="dd__i${v?'':' dd__i--sel'}" data-filtro="${campo}:">${v?'<span class="dd__vaga"></span>':s('check')}${padrao}</button>
      ${opcoes.map(o=>`<button class="dd__i${v===o?' dd__i--sel':''}" data-filtro="${campo}:${o}">${v===o?s('check'):'<span class="dd__vaga"></span>'}${o}</button>`).join('')}
    </div></div>`;
}

function render(){
  const rows=est.cenario==='vazio'?[]:ordenadas(filtradas());
  const filtrando=ativos().length>0;
  const fila=FILAS.find(f=>f.chave===est.fila);
  const total=filtrando?rows.length:(fila?fila.total:186);

  const bandaCabeca=`
  <div class="cabeca">
    <div class="cabeca__esq">
      <div class="kicker">Eventos Sociais</div>
      <h1>Solicitações</h1>
      <p class="cabeca__sub">Acompanhe e gerencie as solicitações registradas no módulo.</p>
    </div>
    <div class="cabeca__dir">
      <div class="ind">
        <button class="ind__i" data-fila="">
          <span class="ind__ic ind__ic--n">${s('users')}</span>
          <span class="ind__v"><b>186</b><span>Total de solicitações</span></span>
        </button>
        <button class="ind__i" data-fila="despacho">
          <span class="ind__ic ind__ic--a">${s('document')}</span>
          <span class="ind__v"><b>14</b><span>Aguardando despacho</span></span>
        </button>
        <button class="ind__i" data-fila="devolvidas">
          <span class="ind__ic ind__ic--d">${s('undo')}</span>
          <span class="ind__v"><b>5</b><span>Devolvidas para ajuste</span></span>
        </button>
      </div>
      <button class="btn-primaria">${s('plus')}Nova solicitação</button>
    </div>
  </div>`;

  const bandaFilas=`
  <div class="filas" role="tablist" aria-label="Filas de trabalho">
    ${FILAS.map((f,i)=>`${i>0&&f.grupo!==FILAS[i-1].grupo?'<span class="filas__sep" aria-hidden="true"></span>':''}
      <button class="fila${f.destaque?' fila--destaque':''}" role="tab" data-fila="${f.chave}"${est.fila===f.chave?' aria-current="page" aria-selected="true"':' aria-selected="false"'}>
        ${f.rotulo}<span class="fila__n">${f.total}</span></button>`).join('')}
  </div>`;

  const bandaBarra=`
  <div class="barra__esq">
    <div class="busca">${s('search')}<input type="search" placeholder="Buscar por nº, solicitante, local ou município" aria-label="Buscar solicitações"></div>
    <span class="risco-b" aria-hidden="true"></span>
    ${fc('status','Todos',Object.values(STATUS))}
    <button class="fc" data-dd="f-tipo" aria-haspopup="true" aria-expanded="false">
      <span class="fc__rot">Tipo de evento</span>Todos${s('chevron-down')}
    </button>
    ${fc('municipio','Todos',MUNICIPIOS.slice(0,8))}
    <div class="dd">
      <button class="fc" data-painel aria-expanded="${est.painel}" aria-controls="filtros-avancados">
        ${s('filter')}Filtros${nAvancados()?`<span class="fc__n">${nAvancados()}</span>`:''}${s('chevron-down')}
      </button>
    </div>
  </div>
  <div class="fpanel" id="filtros-avancados"${est.painel?'':' hidden'}>
    <div class="fpanel__grid">
      <label class="campo"><span class="campo__label">Eventos a partir de</span><input class="ctrl" type="date" data-av="inicio" value="${est.f.inicio}"></label>
      <label class="campo"><span class="campo__label">Eventos até</span><input class="ctrl" type="date" data-av="fim" value="${est.f.fim}"></label>
      <label class="campo"><span class="campo__label">Unidade solicitante</span><select class="ctrl" data-av="unidade"><option value="">Todas as unidades</option>${UNIDADES.map(u=>`<option${est.f.unidade===u?' selected':''}>${u}</option>`).join('')}</select></label>
      <label class="campo"><span class="campo__label">Decisão da DG</span><select class="ctrl" data-av="decisao"><option value="">Todas</option>${DECISOES.map(d=>`<option${est.f.decisao===d?' selected':''}>${d}</option>`).join('')}</select></label>
      <div class="fpanel__ferr">
      <div class="dd"><button class="fc fc--ferramenta" data-dd="colunas" aria-haspopup="true" aria-expanded="false">${s('columns')}Colunas</button>
        <div class="dd__c" hidden data-dd-c="colunas"><div class="dd__t">Colunas visíveis</div>
          ${COLUNAS.filter(c=>!c.fixa).map(c=>`<label class="dd__check"><input type="checkbox" data-col="${c.k}"${est.cols[c.k]?' checked':''}>${c.r}</label>`).join('')}</div></div>
      <button class="fc fc--ferramenta" title="Exportar a listagem filtrada em CSV">${s('download')}Exportar</button>
      </div>
    </div>
  </div>`;

  const tabela=rows.length?`<div class="painel"><div class="dt-w"><table class="dt">
    <thead><tr>
      ${COLUNAS.filter(c=>est.cols[c.k]).map(c=>{const at=est.ordem===c.k;
        return `<th class="${c.cls}"${at?` aria-sort="${est.desc?'descending':'ascending'}"`:''}><button class="dt__ord" data-ordenar="${c.k}">${c.r}${s(at?(est.desc?'arrow-down':'arrow-up'):'ordenar')}</button></th>`}).join('')}
      <th class="c-acoes"><span class="sr-only">Ações</span></th>
    </tr></thead>
    <tbody>
      ${rows.map(l=>{const a=acao(l.st),sel=est.sel===l.id;
        const cel={
          numero:`<td class="c-id"><i>#</i>${l.id}</td>`,
          status:`<td class="c-status"><span class="st st--${l.st.toLowerCase()}">${STATUS[l.st]}</span></td>`,
          tipo:`<td class="c-tipo">${l.tipo}</td>`,
          municipio:`<td class="c-mun">${l.mun}</td>`,
          periodo:`<td class="c-per">${per(l)}</td>`,
          solicitante:`<td class="c-sol"><b>${l.sol}</b><small>${l.un}</small></td>`,
          data:`<td class="c-data">${l.data}</td>`};
        return `<tr data-id="${l.id}"${sel?' aria-selected="true"':''} tabindex="0">
          ${COLUNAS.filter(c=>est.cols[c.k]).map(c=>cel[c.k]).join('')}
          <td class="c-acoes"><div class="acoes">
            ${a?`<button class="acao-linha">${s(a.i)}${a.r}</button>`:''}
            <button class="ib-linha" aria-label="Abrir solicitação #${l.id}">${s('chevron-right')}</button>
            <div class="dd"><button class="ib-linha" data-dd="k${l.id}" aria-haspopup="true" aria-expanded="false" aria-label="Mais ações da solicitação #${l.id}">${s('kebab')}</button>
              <div class="dd__c" hidden data-dd-c="k${l.id}"><div class="dd__t">Solicitação #${l.id}</div>
                <button class="dd__i">${s('eye')}Detalhes</button>
                ${(l.st==='RASCUNHO'||l.st==='DEVOLVIDA')?`<button class="dd__i">${s('pencil')}Editar</button>`:''}
                <button class="dd__i">${s('document')}Histórico</button>
                ${l.st==='RASCUNHO'?`<div class="dd__s"></div><button class="dd__i dd__i--perigo">${s('trash')}Excluir</button>`:''}
              </div></div>
          </div></td></tr>`}).join('')}
    </tbody>
  </table></div>
  <div class="pag">
    <span>Mostrando <b>1–${rows.length}</b> de <b>${total}</b> solicitações</span>
    <nav class="pag__nav" aria-label="Paginação">
      <button class="pag__passo" aria-disabled="true">${s('chevron-left')}Anterior</button>
      <button class="pag__n" aria-current="page">1</button>
      ${total>50?'<button class="pag__n">2</button><button class="pag__n">3</button><button class="pag__n">4</button><span class="pag__el">…</span><button class="pag__n">16</button>':''}
      <button class="pag__passo"${total>50?'':' aria-disabled="true"'}>Próxima${s('chevron-right')}</button>
    </nav>
    <label class="pag__tam">Por página <select><option>12</option><option>25</option><option>50</option></select></label>
  </div></div>`
  :est.cenario==='vazio'?`<div class="semres"><p class="semres__t">Nenhuma solicitação registrada nesta fila ainda.</p>
      <button class="btn-primaria" style="margin:0 auto">${s('plus')}Nova solicitação</button></div>`
  :`<div class="semres"><p class="semres__t">Nenhuma solicitação corresponde aos filtros aplicados.</p>
      <button class="btn btn--secundaria" data-limpar>Limpar filtros</button></div>`;

  document.querySelector('#folha').innerHTML=bandaCabeca+bandaFilas+bandaBarra+tabela;
}

function fechar(x){document.querySelectorAll('[data-dd-c]').forEach(c=>{if(c!==x){c.hidden=true;const g=document.querySelector(`[data-dd="${c.dataset.ddC}"]`);if(g)g.setAttribute('aria-expanded','false')}})}

document.addEventListener('click',e=>{
  const q=x=>e.target.closest(x);
  const f=q('[data-filtro]');
  if(f){const i=f.dataset.filtro.indexOf(':');est.f[f.dataset.filtro.slice(0,i)]=f.dataset.filtro.slice(i+1);fechar();render();return}
  const rm=q('[data-remover]');
  if(rm){est.f[rm.dataset.remover]='';render();return}
  if(q('[data-limpar]')){Object.keys(est.f).forEach(k=>est.f[k]='');render();return}
  if(q('[data-painel]')){est.painel=!est.painel;render();return}
  const g=q('[data-dd]');
  if(g){const c=document.querySelector(`[data-dd-c="${g.dataset.dd}"]`);const abrir=c.hidden;fechar();c.hidden=!abrir;g.setAttribute('aria-expanded',String(abrir));e.preventDefault();return}
  const o=q('[data-ordem]');
  if(o){const[k,d]=o.dataset.ordem.split(':');est.ordem=k;est.desc=d==='true';fechar();render();return}
  const th=q('[data-ordenar]');
  if(th){const k=th.dataset.ordenar;if(est.ordem===k){est.desc=!est.desc}else{est.ordem=k;est.desc=(k==='data'||k==='numero')}render();return}
  const fila=q('[data-fila]');
  if(fila){est.fila=fila.dataset.fila;render();return}
  const cb=q('[data-col]');
  if(cb){est.cols[cb.dataset.col]=cb.checked;render();const c=document.querySelector('[data-dd-c="colunas"]');c.hidden=false;document.querySelector('[data-dd="colunas"]').setAttribute('aria-expanded','true');return}
  if(q('.dd__c')||q('.busca')||q('.fpanel')) return;
  fechar();
  const tr=q('tbody tr');
  if(tr&&!q('.btn')&&!q('.ib')&&!q('.ib-linha')&&!q('.acao-linha')){est.sel=est.sel===+tr.dataset.id?null:+tr.dataset.id;render()}
});
document.addEventListener('change',e=>{
  const av=e.target.closest('[data-av]');
  if(av){est.f[av.dataset.av]=av.value;render();const p=document.querySelector('.fpanel');if(p)p.hidden=!est.painel}
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')fechar()});
render();
