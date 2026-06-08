/* ===== 有機肥業務客戶管理 — 本機儲存，資料不外傳 ===== */
'use strict';

// ---------- 儲存 ----------
const LS = {
  get(k, d){ try{ return JSON.parse(localStorage.getItem(k)) ?? d; }catch(e){ return d; } },
  set(k, v){ localStorage.setItem(k, JSON.stringify(v)); }
};
// 名單庫種子（來自 prospects.js，唯讀），使用者狀態存在 overlay
const SEED = window.SEED_DATA || [];
let overlay = LS.get('crm_overlay', {});      // { prospectId: {freq,last,next,note,inter:[],hidden} }
let customers = LS.get('crm_customers', []);   // 我的客戶（含敏感欄位）
const saveOverlay = () => LS.set('crm_overlay', overlay);
const saveCust = () => LS.set('crm_customers', customers);

const CATS = ['農會','合作社','肥料行','有機農戶','競爭對手','驗證機構','友善團體','有機促進區'];
const CUST_TYPES = ['農會','合作社','經銷商','直接農民','其他'];

// 產品報價用：9 項正式品名、性狀、重量、含運、票期
const PRODUCTS = ['碩成508','碩成1號+','碩成2號','碩成2號+','碩成生技1號','碩成果美肥','碩成基肥1號','碩成基肥2號','碩成基肥2號+'];
const FORMS = ['粒狀','粉狀'];          // 性狀
const WEIGHTS = ['20','25','500','1000']; // 規格公斤（粒狀固定20，粉狀多規格）
const FREIGHTS = ['含運','不含運'];
const CHECK_PERIODS = ['現金','月結5天','月結15天','月結30天','月結45天','月結60天'];

// 區域（依台灣由北到南排序）
const REGION_ORDER = '基隆 臺北 新北 桃園 新竹 苗栗 臺中 彰化 南投 雲林 嘉義 臺南 高雄 屏東 宜蘭 花蓮 臺東 澎湖 金門 連江'.split(' ');
const normR = s => (s||'').replace(/台/g,'臺');
function regionsSorted(){
  const set=[...new Set(SEED.map(p=>p.region).filter(Boolean))];
  return set.sort((a,b)=>{
    const ia=REGION_ORDER.findIndex(x=>normR(a).includes(x));
    const ib=REGION_ORDER.findIndex(x=>normR(b).includes(x));
    return (ia<0?99:ia)-(ib<0?99:ib) || a.localeCompare(b);
  });
}
function district(addr){
  if(!addr) return '';
  let s=String(addr).replace(/^[0-9０-９]+\s*/,'');
  // 先去掉縣市前綴，避免「縣/市」字混進鄉鎮名（例：新竹縣竹北市→竹北市）
  const ci=s.indexOf('縣');
  if(ci>=0){ s=s.slice(ci+1); }
  else { const mi=s.indexOf('市'); if(mi>=0) s=s.slice(mi+1); }
  // 取開頭的鄉鎮市區（最多3字＋區/鄉/鎮/市）
  const m=s.match(/^[一-龥]{1,3}?[區鄉鎮市]/);
  if(m) return m[0];
  // 後備：全字串掃描，優先取以區/鄉/鎮結尾者
  const all=s.match(/[一-龥]{1,3}[區鄉鎮市]/g);
  if(all) return all.find(x=>/[區鄉鎮]$/.test(x))||all[0];
  return '';
}
// 既有客戶 / 陌生目標客戶：名單中已轉成「我的客戶」者視為既有
const TYPE2CHAN = {'經銷商':'肥料行','直接農民':'有機農戶','農會':'農會','合作社':'合作社','其他':'其他'};
function existingProspectIds(){ const s=new Set(); customers.forEach(c=>{ if(c.fromProspect) s.add(c.fromProspect); }); return s; }

// 客戶分級：A~D 對應拜訪頻率（每週 / 每月 / 每季 / 每年）
const GRADES = ['A','B','C','D'];
const GRADE_FREQ = {A:7, B:30, C:90, D:365};
const GRADE_LABEL = {A:'每週', B:'每月', C:'每季', D:'每年'};
const gradeText = g => g ? `${g}級・${GRADE_LABEL[g]}` : '';

// ---------- 工具 ----------
const $ = s => document.querySelector(s);
const esc = s => (s==null?'':String(s)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const todayStr = () => new Date().toISOString().slice(0,10);
function addDays(dstr, n){ const d=new Date(dstr); d.setDate(d.getDate()+n); return d.toISOString().slice(0,10); }
function daysBetween(a, b){ return Math.round((new Date(b)-new Date(a))/86400000); }
function colorFor(name){ const c=['#43a047','#1e88e5','#8e24aa','#00897b','#fb8c00','#5e35b1','#d81b60','#3949ab']; let h=0; for(const ch of (name||'')) h=(h*31+ch.charCodeAt(0))>>>0; return c[h%c.length]; }
let toastT;
function toast(msg){ const t=$('#toast'); t.textContent=msg; t.classList.add('show'); clearTimeout(toastT); toastT=setTimeout(()=>t.classList.remove('show'),1900); }
function telLink(p){ const n=(p||'').split('/')[0].replace(/[^\d+]/g,''); return n.length>=6?`<a href="tel:${n}">${esc(p)}</a>`:esc(p)||'—'; }
function mapLink(a){ return a?`<a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(a)}" target="_blank">${esc(a)} 🗺️</a>`:'—'; }

// ---------- 拜訪狀態計算 ----------
function dueInfo(o){
  if(!o || !o.next) return null;
  const d = daysBetween(todayStr(), o.next); // 距下次拜訪天數
  if(d < 0) return {cls:'pill-over', txt:`逾期${-d}天`, sort:d};
  if(d === 0) return {cls:'pill-due', txt:'今天', sort:0};
  if(d <= 7) return {cls:'pill-due', txt:`${d}天後`, sort:d};
  return {cls:'pill-ok', txt:`${d}天後`, sort:d};
}

// ---------- 導覽 ----------
let tab = 'home';
let pFilter = {status:'', cat:'', region:'', q:''};      // 名單篩選
let pLimit = 60;
function go(t){
  tab = t; pLimit = 60;
  document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('on', b.dataset.tab===t));
  $('#title').textContent = {home:'戰情總覽',map:'戰情地圖',prospects:'目標名單',route:'智慧拜訪規劃',customers:'我的客戶',settings:'設定 / 備份'}[t];
  $('#fab').style.display = (t==='customers') ? 'block' : 'none';
  window.scrollTo(0,0);
  render();
}
function onFab(){ if(tab==='customers') editCustomer(null); }

// ---------- 渲染分派 ----------
function render(){ ({home:renderHome,map:renderMap,prospects:renderProspects,route:renderRoute,customers:renderCustomers,settings:renderSettings}[tab])(); }

// ========== 掌握度統計（以名單為母體：開發=成交既有、接觸=拜訪過） ==========
function isContacted(id){ const o=overlay[id]; return !!(o && (o.last || (o.inter&&o.inter.length))); }
function computeCoverage(){
  const exIds=existingProspectIds();
  const region={}; let total=0, dev=0, con=0;
  SEED.forEach(p=>{
    const r=p.region||'其他';
    const e=exIds.has(p.id);
    const c=e||isContacted(p.id);
    const rr=region[r]=region[r]||{total:0,dev:0,con:0};
    rr.total++; total++;
    if(e){ rr.dev++; dev++; }
    if(c){ rr.con++; con++; }
  });
  return {region,total,dev,con};
}
// 掌握度進度條（開發率：開發數/名單數）
function covBarRow(name,total,dev,onclickFn){
  const r=total?dev/total:0, col=penColor(total,dev);
  return `<div class="mrow" onclick="${onclickFn()}">
    <div class="mname">${esc(name)}</div>
    <div class="mbar"><i style="width:${Math.round(r*100)}%;background:${col}"></i></div>
    <div class="mnum">開發${dev}/${total}・${Math.round(r*100)}%</div></div>`;
}
// 名單多但還沒開發的鄉鎮（gap=名單−客戶 最大者優先）
function weakestTowns(st, limit){
  if(!window.TW_MAP) return [];
  const arr=[];
  window.TW_MAP.towns.forEach((t,i)=>{ const k=townKey(t), lead=st.lead[k]||0, cust=st.cust[k]||0; if(lead>0) arr.push({i,c:t.c,t:t.t,lead,cust,gap:lead-cust}); });
  arr.sort((a,b)=>b.gap-a.gap || b.lead-a.lead);
  return arr.slice(0,limit);
}
// 從儀表板跳到地圖並聚焦
function gotoMapCounty(region){
  go('map');
  if(window.TW_MAP){
    const core=countyCore(region);
    const key=Object.keys(window.TW_MAP.counties).find(k=>countyCore(k)===core);
    if(key) mapSelectCounty(key);
  }
}
function gotoMapTown(i){ go('map'); mapTapTown(i); }

// ========== 首頁（戰情儀表板） ==========
function renderHome(){
  // 待拜訪：合併我的客戶 + 名單 overlay
  const tasks = [];
  customers.forEach(c=>{ const di=dueInfo(c); if(di&&di.sort<=7) tasks.push({kind:'cust',ref:c,di,name:c.name,sub:c.type}); });
  Object.entries(overlay).forEach(([id,o])=>{ const di=dueInfo(o); if(di&&di.sort<=7){ const p=SEED.find(x=>x.id===id); if(p) tasks.push({kind:'prosp',ref:p,o,di,name:p.name,sub:p.category+(p.region?' · '+p.region:'')}); } });
  tasks.sort((a,b)=>a.di.sort-b.di.sort);
  const overdue = tasks.filter(t=>t.di.sort<0).length;
  const todayN = tasks.filter(t=>t.di.sort===0).length;

  const cov=computeCoverage();
  const pct=(a,b)=>b?Math.round(a/b*100):0;

  // ── 責任區掌握度 KPI ──
  let h = `<div class="sec-title"><span class="bar"></span>責任區掌握度</div>`;
  h += `<div class="stat-grid">
    <div class="stat cust"><div class="n">${pct(cov.dev,cov.total)}%</div><div class="l">開發率（成交）<br>${cov.dev} / ${cov.total} 家</div></div>
    <div class="stat prosp"><div class="n">${pct(cov.con,cov.total)}%</div><div class="l">接觸率（拜訪過）<br>${cov.con} / ${cov.total} 家</div></div>
    <div class="stat over"><div class="n">${overdue}</div><div class="l">逾期未拜訪</div></div>
    <div class="stat due"><div class="n">${todayN}</div><div class="l">今天要拜訪</div></div>
  </div>`;

  // ── 各縣市掌握度（依未開發多寡排序）──
  const regs=Object.entries(cov.region).filter(([,v])=>v.total>0)
    .sort((a,b)=>(b[1].total-b[1].dev)-(a[1].total-a[1].dev));
  if(regs.length){
    h += `<div class="sec-title"><span class="bar"></span>各縣市掌握度（未開發多者在前）</div><div class="card">`;
    h += regs.slice(0,12).map(([name,v])=>covBarRow(name,v.total,v.dev,()=>`gotoMapCounty('${esc(name)}')`)).join('');
    h += `</div>`;
  }

  // ── 最該開發的鄉鎮 ──
  if(window.TW_MAP){
    const st=computeTownStats();
    const weak=weakestTowns(st,8);
    if(weak.length){
      h += `<div class="sec-title"><span class="bar"></span>最該開發的鄉鎮 TOP ${weak.length}</div>
        <div class="tagline" style="margin:-4px 2px 8px">名單多但還沒開發的，優先攻。點一下看地圖。</div><div class="card">`;
      h += weak.map(w=>mapBarRow(`${w.c} ${w.t}`,w.lead,w.cust,()=>`gotoMapTown(${w.i})`)).join('');
      h += `</div>`;
    }
  }

  h += `<div class="sec-title"><span class="bar"></span>本週待拜訪</div>`;
  if(!tasks.length){
    h += `<div class="card empty"><div class="big">📭</div>目前沒有排定的拜訪。<br>到「名單」或「我的客戶」設定拜訪頻率即可自動排程。</div>`;
  } else {
    h += `<div class="card">` + tasks.slice(0,30).map(t=>itemRow({
      name:t.name, sub:t.sub, cat:(t.kind==='cust'?t.ref.type:t.ref.category),
      pill:`<span class="badge ${t.di.cls}">${t.di.txt}</span>`,
      onclick: t.kind==='cust'?`viewCustomer('${t.ref.id}')`:`viewProspect('${t.ref.id}')`
    })).join('') + `</div>`;
  }

  // 待跟進事項（拜訪後留下的後續事項）
  const fups=[];
  customers.forEach(c=>(c.follow||[]).forEach(f=>{ if(!f.done) fups.push({name:c.name,sub:c.type,kind:'cust',id:c.id,f}); }));
  Object.entries(overlay).forEach(([id,o])=>{ (o.follow||[]).forEach(f=>{ if(!f.done){ const p=SEED.find(x=>x.id===id); if(p) fups.push({name:p.name,sub:p.category,kind:'prosp',id,f}); } }); });
  fups.sort((a,b)=>((a.f.due||'9999').localeCompare(b.f.due||'9999')));
  h += `<div class="sec-title"><span class="bar"></span>待跟進事項${fups.length?`（${fups.length}）`:''}</div>`;
  if(!fups.length){
    h += `<div class="card empty"><div class="big">✅</div>沒有待辦的跟進事項。<br>拜訪後在客戶頁記下「後續跟進」就會出現在這裡。</div>`;
  } else {
    h += `<div class="card">` + fups.slice(0,30).map(u=>{
      const od=u.f.due&&u.f.due<todayStr();
      const pill=u.f.due?`<span class="badge ${od?'pill-over':'pill-ok'}">${od?'逾期 ':''}${esc(u.f.due)}</span>`:'';
      return itemRow({ name:u.f.text, sub:`${u.name}・${u.sub}`, pill,
        onclick: u.kind==='cust'?`viewCustomer('${u.id}')`:`viewProspect('${u.id}')` });
    }).join('') + `</div>`;
  }
  $('#view').innerHTML = h;
}

function itemRow({name,sub,cat,pill,onclick}){
  const ini=(name||'?').trim().charAt(0);
  return `<div class="item" onclick="${onclick}">
    <div class="avatar" style="background:${colorFor(name)}">${esc(ini)}</div>
    <div class="body"><div class="nm">${esc(name)}</div><div class="sub">${esc(sub||'')}</div></div>
    <div class="meta">${pill||(cat?`<span class="badge b-${cat}">${cat}</span>`:'')}</div>
  </div>`;
}

// ========== 戰情地圖 ==========
let mapState = {countyName:'', town:-1};   // countyName: 地圖縣市名(全島='')；town: 選取鄉鎮 index
function countyCore(s){ s=normR(s); return REGION_ORDER.find(x=>s.includes(x))||''; }
// 以官方鄉鎮名清單做權威比對（避免「平鎮區→平鎮」「台西/臺西」等誤判）
function townsByCore(){
  if(window._tbc) return window._tbc;
  const m={};
  window.TW_MAP.towns.forEach(t=>{ const core=countyCore(t.c); (m[core]=m[core]||[]).push({raw:t.t, n:normR(t.t)}); });
  Object.values(m).forEach(arr=>arr.sort((a,b)=>b.n.length-a.n.length)); // 長名優先
  window._tbc=m; return m;
}
function matchTown(addr, core){
  if(!addr||!core) return '';
  const list=townsByCore()[core]; if(!list) return '';
  const a=normR(addr);
  for(const t of list){ if(a.includes(t.n)) return t.raw; }
  return '';
}
// 計算各鄉鎮的「名單數 / 客戶數」（key = 縣市核心|官方鄉鎮名）
function computeTownStats(){
  const lead={}, cust={};
  SEED.forEach(p=>{ const core=countyCore(p.region)||countyCore(p.address); const tn=matchTown(p.address,core)||matchTown(p.region,core); if(core&&tn){ const k=core+'|'+tn; lead[k]=(lead[k]||0)+1; } });
  customers.forEach(c=>{ const core=countyCore(c.address); const tn=matchTown(c.address,core); if(core&&tn){ const k=core+'|'+tn; cust[k]=(cust[k]||0)+1; } });
  return {lead,cust};
}
function townKey(t){ return countyCore(t.c)+'|'+t.t; }
// 滲透色：灰=無資料、橘=有名單未開發、綠由淺到深=滲透越高
function penColor(lead,cust){
  if(!lead && !cust) return '#eceff1';
  if(cust<=0) return '#ffd9a8';
  const rate=lead?Math.min(1,cust/lead):1;
  if(rate<0.34) return '#a5d6a7';
  if(rate<0.67) return '#52b265';
  return '#2e7d32';
}
function renderMap(){
  if(!window.TW_MAP){ $('#view').innerHTML='<div class="card empty"><div class="big">🗺️</div>地圖資料載入失敗。</div>'; return; }
  const M=window.TW_MAP, st=computeTownStats();
  // viewBox：全島或縮放到選定縣市
  let vb=M.viewBox;
  if(mapState.countyName && M.counties[mapState.countyName]){
    const b=M.counties[mapState.countyName], pad=Math.max(b[2],b[3])*0.08;
    vb=`${b[0]-pad} ${b[1]-pad} ${b[2]+pad*2} ${b[3]+pad*2}`;
  }
  // 縣市下拉
  const cNames=Object.keys(M.counties).sort((a,b)=>REGION_ORDER.findIndex(x=>normR(a).includes(x))-REGION_ORDER.findIndex(x=>normR(b).includes(x)));
  let h=`<div class="card" style="padding:12px 13px">
    <div class="field" style="margin:0"><label>聚焦區域</label>
    <select onchange="mapSelectCounty(this.value)">
      <option value="" ${!mapState.countyName?'selected':''}>🌏 全台灣</option>
      ${cNames.map(n=>`<option value="${esc(n)}" ${mapState.countyName===n?'selected':''}>${esc(n)}</option>`).join('')}
    </select></div></div>`;
  // 選取鄉鎮資訊卡
  if(mapState.town>=0 && M.towns[mapState.town]){
    const t=M.towns[mapState.town], k=townKey(t), lead=st.lead[k]||0, cu=st.cust[k]||0;
    const rate=lead?Math.round(Math.min(1,cu/lead)*100):(cu?100:0);
    h+=`<div class="minfo"><div class="mt">${esc(t.c)} ${esc(t.t)}</div>
      <div class="mstat"><div>名單<br><b>${lead}</b></div><div>我的客戶<br><b style="color:var(--green)">${cu}</b></div><div>滲透率<br><b>${rate}%</b></div></div></div>`;
  }
  // SVG 地圖
  let paths='';
  M.towns.forEach((t,i)=>{
    const k=townKey(t);
    const col=penColor(st.lead[k]||0,st.cust[k]||0);
    paths+=`<path class="tw-town${i===mapState.town?' sel':''}" d="${t.d}" fill="${col}" onclick="mapTapTown(${i})"></path>`;
  });
  h+=`<div class="mapwrap"><svg viewBox="${vb}" preserveAspectRatio="xMidYMid meet">${paths}</svg></div>`;
  // 圖例
  h+=`<div class="maplegend">
    <span><i style="background:#ffd9a8"></i>有名單未開發</span>
    <span><i style="background:#a5d6a7"></i>滲透 ~33%</span>
    <span><i style="background:#52b265"></i>~66%</span>
    <span><i style="background:#2e7d32"></i>67%以上</span>
    <span><i style="background:#eceff1"></i>無名單</span></div>`;
  // 明細表：全島→各縣市滾算；選定縣市→該縣市各鄉鎮
  if(!mapState.countyName){
    const roll={};
    M.towns.forEach(t=>{ const k=townKey(t); const r=roll[t.c]=roll[t.c]||{lead:0,cust:0}; r.lead+=st.lead[k]||0; r.cust+=st.cust[k]||0; });
    const rows=cNames.map(n=>({name:n,...roll[n]})).filter(r=>r.lead||r.cust);
    h+=`<div class="sec-title"><span class="bar"></span>各縣市滲透概況</div><div class="card">`+
      rows.sort((a,b)=>(b.lead-b.cust)-(a.lead-a.cust)).map(r=>mapBarRow(r.name,r.lead,r.cust,()=>`mapSelectCounty('${esc(r.name)}')`)).join('')+`</div>`;
  } else {
    const towns=M.towns.map((t,i)=>({i,t})).filter(o=>o.t.c===mapState.countyName);
    const rows=towns.map(o=>{ const k=townKey(o.t); return {i:o.i,name:o.t.t,lead:st.lead[k]||0,cust:st.cust[k]||0}; }).filter(r=>r.lead||r.cust);
    h+=`<div class="sec-title"><span class="bar"></span>${esc(mapState.countyName)} 各鄉鎮（依未開發排序）</div><div class="card">`+
      (rows.length?rows.sort((a,b)=>(b.lead-b.cust)-(a.lead-a.cust)).map(r=>mapBarRow(r.name,r.lead,r.cust,()=>`mapTapTown(${r.i})`)).join(''):`<div class="tagline">此區尚無名單資料。</div>`)+`</div>`;
  }
  $('#view').innerHTML=h;
}
function mapBarRow(name,lead,cust,onclickFn){
  const rate=lead?Math.min(1,cust/lead):(cust?1:0);
  const col=penColor(lead,cust);
  return `<div class="mrow" onclick="${onclickFn()}">
    <div class="mname">${esc(name)}</div>
    <div class="mbar"><i style="width:${Math.round(rate*100)}%;background:${col}"></i></div>
    <div class="mnum">客${cust}/名單${lead}・${Math.round(rate*100)}%</div></div>`;
}
function mapSelectCounty(n){ mapState.countyName=n; mapState.town=-1; renderMap(); window.scrollTo(0,0); }
function mapTapTown(i){
  const t=window.TW_MAP.towns[i]; mapState.town=i;
  if(t && mapState.countyName!==t.c) mapState.countyName=t.c;   // 點鄉鎮自動聚焦其縣市
  renderMap(); window.scrollTo(0,0);
}

// ========== 名單 ==========
function renderProspects(){
  const exIds = existingProspectIds();
  const statusOf = p => exIds.has(p.id) ? 'existing' : 'cold';
  const nEx = SEED.reduce((a,p)=>a+(statusOf(p)==='existing'?1:0),0);
  const inStatus = p => !pFilter.status || statusOf(p)===pFilter.status;
  // 通路筆數依目前「客戶狀態」動態計算
  const counts = {}; let total=0;
  SEED.forEach(p=>{ if(inStatus(p)){ counts[p.category]=(counts[p.category]||0)+1; total++; } });

  let h = `<div class="search"><input id="psearch" placeholder="🔍 搜尋名稱 / 地址 / 電話" value="${esc(pFilter.q)}" oninput="onPSearch(this.value)"></div>`;
  h += `<div class="rowsel"><span class="rowsel-l">狀態</span><div class="chips">
        <button class="chip ${pFilter.status===''?'on':''}" onclick="setPStatus('')">全部 ${SEED.length}</button>
        <button class="chip ${pFilter.status==='cold'?'on':''}" onclick="setPStatus('cold')">陌生目標客戶 ${SEED.length-nEx}</button>
        <button class="chip ${pFilter.status==='existing'?'on':''}" onclick="setPStatus('existing')">既有客戶 ${nEx}</button></div></div>`;
  h += `<div class="rowsel"><span class="rowsel-l">通路</span><div class="chips"><button class="chip ${pFilter.cat===''?'on':''}" onclick="setPCat('')">全部 ${total}</button>`;
  CATS.forEach(c=>{ if(counts[c]) h+=`<button class="chip ${pFilter.cat===c?'on':''}" onclick="setPCat('${c}')">${c} ${counts[c]}</button>`; });
  h += `</div></div>`;
  h += `<div class="rowsel"><span class="rowsel-l">區域</span><select class="regsel" onchange="setPRegion(this.value)">
        <option value="">全部區域</option>
        ${regionsSorted().map(r=>`<option value="${esc(r)}" ${pFilter.region===r?'selected':''}>${esc(r)}</option>`).join('')}
        </select></div>`;

  const q = pFilter.q.trim();
  const res = SEED.filter(p=>{
    if(!inStatus(p)) return false;
    if(pFilter.cat && p.category!==pFilter.cat) return false;
    if(pFilter.region && p.region!==pFilter.region) return false;
    if(q){ const blob=(p.name+p.address+p.phone+p.contact+p.region); if(!blob.includes(q)) return false; }
    return true;
  });
  h += `<div class="count">符合 ${res.length} 筆${res.length>pLimit?`（顯示前 ${pLimit} 筆，可搜尋縮小範圍）`:''}</div>`;
  h += `<div class="card">`;
  if(!res.length){ h+=`<div class="empty"><div class="big">🔍</div>找不到符合的名單</div>`; }
  else {
    h += res.slice(0,pLimit).map(p=>{
      const o=overlay[p.id]; const di=dueInfo(o); const ex=statusOf(p)==='existing';
      const tag = ex?`<span class="badge b-農會">既有</span>`:'';
      const pill = di?`<span class="badge ${di.cls}">${di.txt}</span>${tag}`:`<span class="badge b-${p.category}">${p.category}</span>${tag}`;
      return itemRow({name:p.name, sub:[p.region,p.address].filter(Boolean).join(' · '), pill, onclick:`viewProspect('${p.id}')`});
    }).join('');
  }
  h += `</div>`;
  if(res.length>pLimit) h+=`<div class="more" onclick="pLimit+=60;render()">顯示更多 ▼</div>`;
  $('#view').innerHTML = h;
  const inp=$('#psearch'); if(inp&&pFilter._focus){ inp.focus(); inp.setSelectionRange(inp.value.length,inp.value.length); pFilter._focus=false; }
}
function onPSearch(v){ pFilter.q=v; pFilter._focus=true; pLimit=60; renderProspects(); }
function setPStatus(s){ pFilter.status=s; pFilter.cat=''; pLimit=60; renderProspects(); }
function setPCat(c){ pFilter.cat=c; pLimit=60; renderProspects(); }
function setPRegion(r){ pFilter.region=r; pLimit=60; renderProspects(); }

function custByProspect(id){ return customers.find(c=>c.fromProspect===id); }
function viewProspect(id){
  const p=SEED.find(x=>x.id===id); if(!p) return;
  const o=overlay[id]||{}; const di=dueInfo(o);
  const exCust=custByProspect(id);
  let h='';
  h+=`<div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px">
      <span class="badge b-${p.category}">${p.category}</span>
      ${p.region?`<span class="badge b-其他">${esc(p.region)}</span>`:''}
      ${exCust?`<span class="badge b-合作社">✅ 已是我的客戶</span>`:''}
      ${di?`<span class="badge ${di.cls}">下次：${di.txt}</span>`:''}</div>`;
  if(exCust) h+=`<div class="info">這個目標客戶已轉成「我的客戶」，名單統計已自動從「陌生」改記為「既有」。拜訪排程請到客戶資料管理。</div>`;
  h+=`<div class="card">`;
  h+=drow('地址', mapLink(p.address));
  h+=drow('電話', telLink(p.phone));
  if(p.contact) h+=drow('聯絡人', esc(p.contact));
  if(p.crop) h+=drow('作物/種類', esc(p.crop));
  if(p.cert) h+=drow('驗證機構', esc(p.cert));
  if(p.area) h+=drow('面積(公頃)', esc(p.area));
  if(p.price) h+=drow('參考價格', esc(p.price));
  if(p.brand) h+=drow('使用品牌', esc(p.brand));
  if(p.ingredient) h+=drow('原料', esc(p.ingredient));
  if(p.spec) h+=drow('規格', esc(p.spec));
  if(p.notes) h+=drow('備註', esc(p.notes));
  h+=`</div>`;

  // 拜訪管理
  h+=`<div class="sec-title"><span class="bar"></span>拜訪管理</div><div class="card">`;
  h+=`<div class="field"><label>拜訪頻率（天）— 設定後自動排下次拜訪</label>
      <input type="number" id="p-freq" min="1" placeholder="例如 30" value="${o.freq||''}"></div>`;
  h+=`<div class="field-2">
      <div class="field"><label>上次拜訪日</label><input type="date" id="p-last" value="${o.last||''}"></div>
      <div class="field"><label>下次拜訪日</label><input type="date" id="p-next" value="${o.next||''}"></div></div>`;
  h+=`<div class="btn-row"><button class="btn btn-out" onclick="visitForm('prosp','${id}')">📍 記錄拜訪</button>
      <button class="btn btn-gray" onclick="saveProspectSchedule('${id}')">儲存排程</button></div>`;
  h+=`</div>`;

  // 後續跟進
  h+=followBlock('prosp', id, o.follow);

  // 互動紀錄
  h+=interactionBlock(o.inter, `addProspectInter('${id}')`);

  if(exCust){
    h+=`<div class="btn-row"><button class="btn btn-pri" onclick="closeModal();viewCustomer('${exCust.id}')">👤 查看 / 編輯客戶資料</button></div>`;
  } else {
    h+=`<div class="btn-row"><button class="btn btn-pri" onclick="convertToCustomer('${id}')">⭐ 轉為我的客戶（+1 既有 / −1 陌生）</button></div>`;
  }
  openModal(p.name, h);
}

function drow(k,v){ return `<div class="drow"><div class="k">${k}</div><div class="v">${v||'—'}</div></div>`; }

function interactionBlock(inter, addFn){
  inter = inter||[];
  let h=`<div class="sec-title"><span class="bar"></span>互動紀錄 (${inter.length})</div><div class="card">`;
  h+=`<div class="btn-row" style="margin-top:0"><button class="btn btn-out" onclick="${addFn}">＋ 新增紀錄</button></div>`;
  if(inter.length){
    h+=`<div class="timeline" style="margin-top:12px">`;
    [...inter].reverse().forEach(it=>{
      h+=`<div class="tl"><div class="tl-h"><span>${esc(it.type||'紀錄')}</span><span>${esc(it.date)}</span></div><div class="tl-c">${esc(it.content)}</div></div>`;
    });
    h+=`</div>`;
  } else { h+=`<div class="tagline" style="margin-top:10px">尚無紀錄</div>`; }
  h+=`</div>`; return h;
}

// ---------- 拜訪紀錄 + 後續跟進（目標客戶與既有客戶共用） ----------
function getHolder(kind,id){ return kind==='cust' ? findCust(id) : (overlay[id]=overlay[id]||{}); }
function saveHolder(kind){ kind==='cust'?saveCust():saveOverlay(); }
function reopenDetail(kind,id){ kind==='cust'?viewCustomer(id):viewProspect(id); }
// 點「記錄拜訪」：一次記下內容＋後續跟進，並自動往後排下次拜訪
function visitForm(kind,id){
  let h=`<div class="field"><label>拜訪日期</label><input type="date" id="v-date" value="${todayStr()}"></div>`;
  h+=`<div class="field"><label>拜訪結果 / 內容</label><textarea id="v-content" placeholder="談了什麼、對方反應、結果…"></textarea></div>`;
  h+=`<div class="field"><label>後續跟進事項（選填）</label><input id="v-follow" placeholder="例如：下週二送試用樣品 / 補報價單"></div>`;
  h+=`<div class="field"><label>跟進期限（選填）</label><input type="date" id="v-due"></div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" id="v-save">儲存拜訪</button></div>`;
  openModal('記錄拜訪', h);
  $('#v-save').onclick=()=>{
    const date=$('#v-date').value||todayStr();
    const content=$('#v-content').value.trim()||'完成拜訪';
    const hd=getHolder(kind,id); if(!hd){ toast('找不到資料'); return; }
    hd.inter=hd.inter||[]; hd.inter.push({date,type:'拜訪',content});
    hd.last=date; if(hd.freq) hd.next=addDays(date,hd.freq);
    const ft=$('#v-follow').value.trim();
    if(ft){ hd.follow=hd.follow||[]; hd.follow.push({id:'F'+Date.now(),text:ft,due:$('#v-due').value||'',done:false,created:date}); }
    saveHolder(kind); toast(ft?'已記錄拜訪並建立跟進':'已記錄拜訪'); reopenDetail(kind,id); render();
  };
}
function addFollow(kind,id){
  let h=`<div class="field"><label>跟進事項</label><input id="nf-text" placeholder="例如：下週二送樣品"></div>`;
  h+=`<div class="field"><label>跟進期限（選填）</label><input type="date" id="nf-due"></div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" id="nf-save">新增</button></div>`;
  openModal('新增跟進事項', h);
  $('#nf-save').onclick=()=>{ const t=$('#nf-text').value.trim(); if(!t){toast('請填寫事項');return;}
    const hd=getHolder(kind,id); hd.follow=hd.follow||[]; hd.follow.push({id:'F'+Date.now(),text:t,due:$('#nf-due').value||'',done:false,created:todayStr()});
    saveHolder(kind); toast('已新增跟進'); reopenDetail(kind,id); render(); };
}
function toggleFollow(kind,id,fid){ const hd=getHolder(kind,id); const f=(hd.follow||[]).find(x=>x.id===fid); if(f){ f.done=!f.done; f.doneDate=f.done?todayStr():''; saveHolder(kind); reopenDetail(kind,id); render(); } }
function delFollow(kind,id,fid){ const hd=getHolder(kind,id); hd.follow=(hd.follow||[]).filter(x=>x.id!==fid); saveHolder(kind); reopenDetail(kind,id); render(); }
function followBlock(kind,id,follows){
  follows=follows||[];
  const open=follows.filter(f=>!f.done).length;
  let h=`<div class="sec-title"><span class="bar"></span>後續跟進 (${open} 待辦)</div><div class="card">`;
  h+=`<div class="btn-row" style="margin-top:0"><button class="btn btn-out" onclick="addFollow('${kind}','${id}')">＋ 新增跟進事項</button></div>`;
  if(follows.length){
    const sorted=[...follows].sort((a,b)=>(a.done-b.done)||((a.due||'9999').localeCompare(b.due||'9999')));
    h+=`<div style="margin-top:8px">`;
    sorted.forEach(f=>{
      const od=!f.done&&f.due&&f.due<todayStr();
      h+=`<div class="fitem ${f.done?'done':''}">
        <input type="checkbox" ${f.done?'checked':''} onclick="toggleFollow('${kind}','${id}','${f.id}')">
        <div class="ftext"><div>${esc(f.text)}</div>${f.due?`<div class="fdue ${od?'over':''}">📅 ${esc(f.due)}${od?'・逾期':''}</div>`:''}</div>
        <button class="fdel" onclick="delFollow('${kind}','${id}','${f.id}')">✕</button></div>`;
    });
    h+=`</div>`;
  } else { h+=`<div class="tagline" style="margin-top:10px">尚無跟進事項，拜訪後可在這裡記下一步。</div>`; }
  h+=`</div>`; return h;
}

function saveProspectSchedule(id){
  const o = overlay[id]||{};
  o.freq = $('#p-freq').value ? +$('#p-freq').value : null;
  o.last = $('#p-last').value || o.last;
  o.next = $('#p-next').value || (o.last&&o.freq?addDays(o.last,o.freq):o.next);
  overlay[id]=o; saveOverlay(); toast('已儲存排程'); viewProspect(id); render();
}
function logProspectVisit(id){
  const o = overlay[id]||{}; const t=todayStr();
  o.last=t; if(o.freq) o.next=addDays(t,o.freq);
  o.inter=o.inter||[]; o.inter.push({date:t,type:'拜訪',content:'完成拜訪'});
  overlay[id]=o; saveOverlay(); toast('已記錄今日拜訪'); viewProspect(id);
}
function addProspectInter(id){
  interForm(it=>{ const o=overlay[id]||{}; o.inter=o.inter||[]; o.inter.push(it); overlay[id]=o; saveOverlay(); toast('已新增紀錄'); viewProspect(id); });
}

function convertToCustomer(id){
  const p=SEED.find(x=>x.id===id); if(!p) return;
  const o=overlay[id]||{};
  const typeMap={'農會':'農會','合作社':'合作社','肥料行':'經銷商','有機農戶':'直接農民'};
  const c = {
    id:'C'+Date.now(), name:p.name, type:typeMap[p.category]||'其他',
    phone:p.phone, address:p.address, contact:p.contact||'',
    idno:'', birth:'', taxid:'', terms:'', checkPeriod:'', truck:'', deliveryTime:'',
    currentFert:p.brand||'', price:p.price||'', conditions:'', grade:'',
    freq:o.freq||null, last:o.last||'', next:o.next||'', notes:p.notes||'',
    inter:o.inter?[...o.inter]:[], fromProspect:id
  };
  closeModal();
  editCustomer(c, true);
}

// ========== 我的客戶 ==========
let cFilter={q:'', grade:''};
function renderCustomers(){
  let h=`<div class="info">🔒 這一頁的資料（含身分證、統編、出生年月日）只儲存在你這台裝置的瀏覽器，不會上傳。請定期到「設定」備份。</div>`;
  h+=`<div class="search"><input placeholder="🔍 搜尋我的客戶" value="${esc(cFilter.q)}" oninput="cFilter.q=this.value;renderCustomers()"></div>`;
  const gc={}; customers.forEach(c=>{ gc[c.grade||'']=(gc[c.grade||'']||0)+1; });
  h+=`<div class="rowsel"><span class="rowsel-l">分級</span><div class="chips">
      <button class="chip ${cFilter.grade===''?'on':''}" onclick="setCGrade('')">全部 ${customers.length}</button>
      ${GRADES.map(g=>`<button class="chip ${cFilter.grade===g?'on':''}" onclick="setCGrade('${g}')">${g}・${GRADE_LABEL[g]} ${gc[g]||0}</button>`).join('')}
      <button class="chip ${cFilter.grade==='none'?'on':''}" onclick="setCGrade('none')">未分級 ${gc['']||0}</button></div></div>`;
  const q=cFilter.q.trim();
  const res=customers.filter(c=>{
    if(cFilter.grade==='none'){ if(c.grade) return false; }
    else if(cFilter.grade){ if(c.grade!==cFilter.grade) return false; }
    return !q||(c.name+c.phone+c.address+(c.contact||'')).includes(q);
  });
  h+=`<div class="count">共 ${customers.length} 位客戶${cFilter.grade?`，符合 ${res.length} 位`:''}</div><div class="card">`;
  if(!res.length){ h+=`<div class="empty"><div class="big">👤</div>${customers.length?'找不到符合的客戶':'還沒有客戶。<br>點右下角 ＋ 新增，或到名單「轉為我的客戶」。'}</div>`; }
  else res.forEach(c=>{ const di=dueInfo(c);
    const gtag=c.grade?`<span class="badge grade-${c.grade}">${c.grade}</span>`:'';
    const pill=(di?`<span class="badge ${di.cls}">${di.txt}</span>`:`<span class="badge b-${c.type}">${c.type}</span>`)+gtag;
    h+=itemRow({name:c.name,sub:[c.phone,c.address].filter(Boolean).join(' · '),pill,onclick:`viewCustomer('${c.id}')`}); });
  h+=`</div>`;
  $('#view').innerHTML=h;
}
function setCGrade(g){ cFilter.grade=g; renderCustomers(); }

function viewCustomer(id){
  const c=customers.find(x=>x.id===id); if(!c) return;
  const di=dueInfo(c);
  let h=`<div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px">
      <span class="badge b-${c.type}">${c.type}</span>
      ${c.grade?`<span class="badge grade-${c.grade}">${esc(gradeText(c.grade))}</span>`:''}
      ${di?`<span class="badge ${di.cls}">下次：${di.txt}</span>`:''}</div>`;
  h+=`<div class="card">`;
  if(c.sysno)h+=drow('系統編號',esc(c.sysno));
  h+=drow('電話',telLink(c.phone));
  h+=drow('通訊地址',mapLink(c.address));
  if(c.contact)h+=drow('聯絡人',esc(c.contact));
  if(c.filedDate)h+=drow('建檔日期',esc(c.filedDate));
  if(c.taxid)h+=drow('統一編號',esc(c.taxid));
  if(c.idno)h+=drow('身分證字號',esc(c.idno));
  if(c.birth)h+=drow('出生年月日',esc(c.birth));
  if(c.regAddress)h+=drow('戶籍地址',mapLink(c.regAddress));
  h+=`</div>`;
  if(c.products&&c.products.length){
    h+=`<div class="sec-title"><span class="bar"></span>產品報價</div><div class="card">`;
    c.products.forEach(p=>h+=drow(esc(p.name), esc(prodText(p))));
    h+=`</div>`;
  }
  h+=`<div class="sec-title"><span class="bar"></span>交易 / 配送</div><div class="card">`;
  if(c.terms)h+=drow('交易條件',esc(c.terms));
  if(c.checkPeriod)h+=drow('票期',esc(c.checkPeriod));
  if(c.price)h+=drow('價格',esc(c.price));
  if(c.conditions)h+=drow('其他條件',esc(c.conditions));
  if(c.currentFert)h+=drow('目前用肥',esc(c.currentFert));
  if(c.truck)h+=drow('運送車輛',esc(c.truck));
  if(c.deliveryTime)h+=drow('送貨時間',esc(c.deliveryTime));
  if(!(c.terms||c.checkPeriod||c.price||c.conditions||c.currentFert||c.truck||c.deliveryTime))h+=`<div class="tagline">尚未填寫</div>`;
  h+=`</div>`;
  if(c.notes){ h+=`<div class="sec-title"><span class="bar"></span>備註</div><div class="card">${esc(c.notes)}</div>`; }

  h+=`<div class="sec-title"><span class="bar"></span>拜訪管理</div><div class="card">`;
  h+=`<div class="field"><label>客戶分級（決定拜訪頻率）</label><select id="c-grade" onchange="if(this.value)document.getElementById('c-freq').value={A:7,B:30,C:90,D:365}[this.value]">
      <option value="" ${!c.grade?'selected':''}>未分級</option>
      ${GRADES.map(g=>`<option value="${g}" ${c.grade===g?'selected':''}>${g} 級・${GRADE_LABEL[g]}拜訪</option>`).join('')}
      </select></div>`;
  h+=`<div class="field-2"><div class="field"><label>拜訪頻率(天)</label><input type="number" id="c-freq" value="${c.freq||''}" min="1"></div>
      <div class="field"><label>下次拜訪日</label><input type="date" id="c-next" value="${c.next||''}"></div></div>`;
  h+=`<div class="btn-row"><button class="btn btn-out" onclick="visitForm('cust','${id}')">📍 記錄拜訪</button>
      <button class="btn btn-gray" onclick="saveCustSchedule('${id}')">儲存排程</button></div></div>`;

  h+=followBlock('cust', id, c.follow);

  h+=interactionBlock(c.inter, `addCustInter('${id}')`);

  h+=`<div class="btn-row"><button class="btn btn-pri" onclick="editCustomer(findCust('${id}'))">✏️ 編輯</button>
      <button class="btn btn-red" onclick="delCustomer('${id}')">刪除</button></div>`;
  openModal(c.name, h);
}
function findCust(id){ return customers.find(x=>x.id===id); }

function saveCustSchedule(id){ const c=findCust(id); c.grade=$('#c-grade').value; c.freq=$('#c-freq').value?+$('#c-freq').value:(c.grade?GRADE_FREQ[c.grade]:null); c.next=$('#c-next').value||(c.freq?addDays(c.last||todayStr(),c.freq):c.next); saveCust(); toast('已儲存'); viewCustomer(id); render(); }
function logCustVisit(id){ const c=findCust(id); const t=todayStr(); c.last=t; if(c.freq)c.next=addDays(t,c.freq); c.inter=c.inter||[]; c.inter.push({date:t,type:'拜訪',content:'完成拜訪'}); saveCust(); toast('已記錄拜訪'); viewCustomer(id); }
function addCustInter(id){ interForm(it=>{ const c=findCust(id); c.inter=c.inter||[]; c.inter.push(it); saveCust(); toast('已新增'); viewCustomer(id); }); }
function delCustomer(id){ if(!confirm('確定刪除這位客戶？此動作無法復原。'))return; customers=customers.filter(c=>c.id!==id); saveCust(); closeModal(); toast('已刪除'); render(); }

function field(label,id,val,type='text',req=false,ph=''){ return `<div class="field"><label>${label}${req?' <span class="req">*</span>':''}</label><input type="${type}" id="${id}" value="${esc(val||'')}" placeholder="${esc(ph)}"></div>`; }

// ---------- 產品報價（多筆）----------
function productRowHTML(p){
  p=p||{};
  const sel=(arr,v,extra='')=>arr.map(x=>`<option ${x===v?'selected':''}>${x}</option>`).join('');
  return `<div class="prow">
    <select class="pp-name"><option value="">產品…</option>${PRODUCTS.map(x=>`<option ${x===p.name?'selected':''}>${esc(x)}</option>`).join('')}</select>
    <div class="prow-2">
      <select class="pp-form">${sel(FORMS,p.form||'粒狀')}</select>
      <select class="pp-weight">${sel(WEIGHTS,p.weight||'20')}</select>
      <input class="pp-price" type="number" inputmode="decimal" placeholder="單價" value="${esc(p.price||'')}">
      <select class="pp-freight">${sel(FREIGHTS,p.freight||'含運')}</select>
      <button type="button" class="prow-del" onclick="this.closest('.prow').remove()">✕</button>
    </div></div>`;
}
function addProductRow(){ const c=document.getElementById('prod-rows'); if(c) c.insertAdjacentHTML('beforeend', productRowHTML()); }
function readProducts(){
  return [...document.querySelectorAll('#prod-rows .prow')].map(el=>({
    name:el.querySelector('.pp-name').value,
    form:el.querySelector('.pp-form').value,
    weight:el.querySelector('.pp-weight').value,
    price:el.querySelector('.pp-price').value.trim(),
    freight:el.querySelector('.pp-freight').value
  })).filter(p=>p.name);
}
function prodText(p){ return `${p.form}${p.weight}kg・$${p.price||'—'}・${p.freight}`; }

// ---------- 票期下拉（現金 / 月結N天 / 手動）----------
function checkPeriodHTML(v){
  const known=CHECK_PERIODS.includes(v);
  const isCustom=v && !known;
  return `<div class="field"><label>票期</label>
    <select id="f-checksel" onchange="onCheckSel()">
      <option value="" ${!v?'selected':''}>未設定</option>
      ${CHECK_PERIODS.map(x=>`<option ${x===v?'selected':''}>${esc(x)}</option>`).join('')}
      <option value="__other" ${isCustom?'selected':''}>其他（手動輸入）</option>
    </select>
    <input id="f-checktext" placeholder="自訂票期，例如 月結90天" value="${isCustom?esc(v):''}" style="margin-top:6px;display:${isCustom?'block':'none'}"></div>`;
}
function onCheckSel(){ const s=$('#f-checksel').value, t=$('#f-checktext'); t.style.display=(s==='__other')?'block':'none'; if(s!=='__other') t.value=''; }
function readCheckPeriod(){ const s=$('#f-checksel').value; return s==='__other' ? $('#f-checktext').value.trim() : (s||''); }

function editCustomer(c, isNew){
  c = c || {id:'C'+Date.now(), type:'直接農民', inter:[]};
  const isAdd = isNew || !customers.some(x=>x.id===c.id);
  let h=`<fieldset class="fset"><legend>基本資料</legend>`;
  h+=field('名稱','f-name',c.name,'text',true,'客戶名稱');
  h+=`<div class="field"><label>客戶類型</label><select id="f-type">${CUST_TYPES.map(t=>`<option ${c.type===t?'selected':''}>${t}</option>`).join('')}</select></div>`;
  h+=field('系統編號','f-sysno',c.sysno,'text',false,'內部系統編號');
  h+=field('電話','f-phone',c.phone,'tel');
  h+=field('聯絡人','f-contact',c.contact);
  h+=field('通訊地址','f-address',c.address);
  h+=field('建檔日期','f-filedDate',c.filedDate,'date');
  h+=`</fieldset>`;
  h+=`<fieldset class="fset sens"><legend>🔒 稅務 / 法務（敏感，僅存本機）</legend>`;
  h+=field('統一編號','f-taxid',c.taxid);
  h+=field('身分證字號','f-idno',c.idno);
  h+=field('出生年月日','f-birth',c.birth,'date');
  h+=field('戶籍地址','f-regAddress',c.regAddress);
  h+=`</fieldset>`;
  h+=`<fieldset class="fset"><legend>產品報價（可多筆）</legend>
    <div id="prod-rows">${(c.products||[]).map(productRowHTML).join('')}</div>
    <div class="more" style="margin-top:8px" onclick="addProductRow()">＋ 新增產品報價</div></fieldset>`;
  h+=`<fieldset class="fset"><legend>交易條件</legend>`;
  h+=field('交易條件','f-terms',c.terms,'text',false,'例如 貨到付款');
  h+=checkPeriodHTML(c.checkPeriod);
  h+=field('其他條件','f-conditions',c.conditions);
  h+=field('目前使用肥料','f-currentFert',c.currentFert);
  h+=`</fieldset>`;
  h+=`<fieldset class="fset"><legend>物流配送</legend>`;
  h+=field('運送車輛大小','f-truck',c.truck,'text',false,'例如 3.5噸 / 小貨車');
  h+=field('送貨時間','f-deliveryTime',c.deliveryTime,'text',false,'例如 週二上午');
  h+=`</fieldset>`;
  h+=`<fieldset class="fset"><legend>客戶分級 / 拜訪</legend>`;
  h+=`<div class="field"><label>客戶分級（決定拜訪頻率）</label><select id="f-grade" onchange="onGradeChange()">
      <option value="" ${!c.grade?'selected':''}>未分級</option>
      ${GRADES.map(g=>`<option value="${g}" ${c.grade===g?'selected':''}>${g} 級・${GRADE_LABEL[g]}拜訪</option>`).join('')}
      </select></div>`;
  h+=field('拜訪頻率（天）','f-freq',c.freq,'number',false,'分級後自動帶入，可微調');
  h+=`<div class="field"><label>備註</label><textarea id="f-notes">${esc(c.notes||'')}</textarea></div>`;
  h+=`</fieldset>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" onclick='saveCustomer(${JSON.stringify(c.id)},${isAdd})'>💾 儲存</button></div>`;
  openModal(isAdd?'新增客戶':'編輯客戶', h);
  window._draft=c;
}
function onGradeChange(){ const g=$('#f-grade').value; if(g) $('#f-freq').value=GRADE_FREQ[g]; }
function saveCustomer(id, isAdd){
  const name=$('#f-name').value.trim(); if(!name){ toast('請填寫名稱'); return; }
  const base = isAdd ? (window._draft||{id,inter:[]}) : findCust(id);
  const g=i=>$('#'+i).value.trim();
  Object.assign(base,{ id, name, type:$('#f-type').value, sysno:g('f-sysno'), phone:g('f-phone'), contact:g('f-contact'),
    address:g('f-address'), filedDate:g('f-filedDate'), taxid:g('f-taxid'), idno:g('f-idno'), birth:g('f-birth'),
    regAddress:g('f-regAddress'), terms:g('f-terms'), checkPeriod:readCheckPeriod(), conditions:g('f-conditions'),
    currentFert:g('f-currentFert'), truck:g('f-truck'), deliveryTime:g('f-deliveryTime'),
    grade:$('#f-grade').value, notes:g('f-notes'), products:readProducts() });
  const freq=$('#f-freq').value; base.freq=freq?+freq:(base.grade?GRADE_FREQ[base.grade]:null);
  if(base.freq && !base.next) base.next = addDays(todayStr(), base.freq);
  base.inter = base.inter||[];
  if(isAdd) customers.push(base);
  saveCust(); closeModal(); toast('已儲存'); go('customers');
}

// ---------- 互動紀錄表單 ----------
function interForm(cb){
  const types=['拜訪','電話','報價','成交','其他'];
  let h=`<div class="field"><label>日期</label><input type="date" id="i-date" value="${todayStr()}"></div>`;
  h+=`<div class="field"><label>類型</label><select id="i-type">${types.map(t=>`<option>${t}</option>`).join('')}</select></div>`;
  h+=`<div class="field"><label>內容</label><textarea id="i-content" placeholder="談了什麼、結果、下一步…"></textarea></div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" id="i-save">儲存紀錄</button></div>`;
  openModal('新增互動紀錄', h);
  $('#i-save').onclick=()=>{ const content=$('#i-content').value.trim(); if(!content){toast('請填寫內容');return;} cb({date:$('#i-date').value,type:$('#i-type').value,content}); };
}

// ========== 設定 / 備份 ==========
function renderSettings(){
  const size=((JSON.stringify(overlay).length+JSON.stringify(customers).length)/1024).toFixed(0);
  let h=`<div class="info">所有資料只存在這台裝置的瀏覽器中。換手機、清除瀏覽器資料前，請先「匯出備份」。</div>`;
  h+=`<div class="sec-title"><span class="bar"></span>資料統計</div><div class="card">`;
  h+=drow('名單庫', SEED.length+' 筆（內建）');
  h+=drow('我的客戶', customers.length+' 位');
  h+=drow('已排程名單', Object.keys(overlay).length+' 筆');
  h+=drow('本機資料量', size+' KB');
  h+=`</div>`;
  h+=`<div class="sec-title"><span class="bar"></span>備份與還原</div><div class="card">`;
  h+=`<div class="btn-row" style="margin-top:0"><button class="btn btn-pri" onclick="exportJSON()">⬇️ 匯出備份 (JSON)</button></div>`;
  h+=`<div class="btn-row"><button class="btn btn-out" onclick="exportCSV()">📊 匯出客戶 (CSV/Excel)</button></div>`;
  h+=`<div class="btn-row"><button class="btn btn-gray" onclick="document.getElementById('imp').click()">⬆️ 匯入還原 (JSON)</button></div>`;
  h+=`<input type="file" id="imp" accept="application/json,.json" style="display:none" onchange="importJSON(this)">`;
  h+=`<div class="hint" style="margin-top:8px;color:var(--muted);font-size:11px">匯入會合併客戶與排程；同名客戶會新增為另一筆。</div>`;
  h+=`</div>`;
  h+=`<div class="sec-title"><span class="bar"></span>匯入既有客戶（SAP 客戶檔）</div><div class="card">`;
  h+=`<div class="btn-row" style="margin-top:0"><button class="btn btn-pri" onclick="document.getElementById('impxls').click()">📥 匯入 SAP 客戶檔 (.xls)</button></div>`;
  h+=`<input type="file" id="impxls" accept=".xls,.csv,.txt,.tsv" style="display:none" onchange="importCustomerFile(this)">`;
  h+=`<div class="hint" style="margin-top:8px;color:var(--muted);font-size:11.5px;line-height:1.7">支援 SAP「客戶/收貨人 ZSD29」匯出的 .xls 檔。會自動帶入<b>系統編號、名稱、電話、通訊地址、戶籍地址、統編、建檔日期</b>；已存在(同系統編號或同名)只補空欄、不覆蓋。檔案在你手機<b>本機</b>讀取，不會上傳。</div>`;
  h+=`</div>`;
  h+=`<div class="sec-title"><span class="bar"></span>使用說明</div><div class="card" style="font-size:13px;line-height:1.7;color:#3a473f">
    <b>📱 加到主畫面：</b>用 Safari/Chrome 開啟後，選「分享 → 加入主畫面」，即可像 App 一樣使用（離線可用）。<br>
    <b>🎯 名單：</b>3,547 筆全國農會／合作社／肥料行／有機農戶。可搜尋、依類別篩選，設定拜訪頻率後自動排程。<br>
    <b>⭐ 開發客戶：</b>名單中點「轉為我的客戶」即可補上完整資料。<br>
    <b>🏠 首頁：</b>自動列出逾期與本週該拜訪的對象。</div>`;
  $('#view').innerHTML=h;
}
function download(name, content, type){
  const blob=new Blob([content],{type}); const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function exportJSON(){
  const data={ver:1, exported:new Date().toISOString(), customers, overlay};
  download(`客戶管理備份_${todayStr()}.json`, JSON.stringify(data), 'application/json');
  toast('已匯出備份');
}
function exportCSV(){
  const cols=[['sysno','系統編號'],['name','名稱'],['type','類型'],['grade','分級'],['phone','電話'],['contact','聯絡人'],['address','通訊地址'],['regAddress','戶籍地址'],['taxid','統編'],['idno','身分證'],['birth','生日'],['filedDate','建檔日期'],['terms','交易條件'],['checkPeriod','票期'],['products','產品報價'],['conditions','其他條件'],['currentFert','目前用肥'],['truck','運送車輛'],['deliveryTime','送貨時間'],['freq','拜訪頻率'],['next','下次拜訪'],['notes','備註']];
  const head=cols.map(c=>c[1]).join(',');
  const fmt=(c,k)=>{ if(k==='products') return (c.products||[]).map(p=>`${p.name} ${prodText(p)}`).join(' / '); return c[k]??''; };
  const rows=customers.map(c=>cols.map(([k])=>`"${String(fmt(c,k)).replace(/"/g,'""')}"`).join(','));
  download(`我的客戶_${todayStr()}.csv`, '﻿'+head+'\n'+rows.join('\n'), 'text/csv');
  toast('已匯出 CSV');
}
function importJSON(input){
  const f=input.files[0]; if(!f)return; const r=new FileReader();
  r.onload=()=>{ try{ const d=JSON.parse(r.result);
    if(Array.isArray(d.customers)){ const ids=new Set(customers.map(c=>c.id)); d.customers.forEach(c=>{ if(ids.has(c.id))c.id='C'+Date.now()+Math.random().toString(36).slice(2,5); customers.push(c); }); }
    if(d.overlay) Object.assign(overlay, d.overlay);
    saveCust(); saveOverlay(); toast('已匯入還原'); render();
  }catch(e){ alert('檔案格式錯誤，無法匯入'); } };
  r.readAsText(f); input.value='';
}

// ---------- 匯入 SAP 客戶檔（Big5 定位字元 .xls）----------
function fmtYmd(s){ s=(s||'').trim(); return /^\d{8}$/.test(s) ? s.slice(0,4)+'-'+s.slice(4,6)+'-'+s.slice(6,8) : s; }
// 解析 SAP ZSD29 匯出：主列(第1欄有系統編號)=客戶；子列(第2欄有編號)=同一客戶的戶籍地
function parseCustomerTSV(text){
  const lines=text.split(/\r\n|\n|\r/);
  const out=[]; let cur=null;
  for(const line of lines){
    if(!line) continue;
    const c=line.split('\t');
    if(c.length<7) continue;
    const code=(c[0]||'').trim(), sub=(c[1]||'').trim(), name=(c[2]||'').trim();
    const tel=(c[4]||'').trim(), addr=(c[6]||'').trim(), tax=(c[8]||'').trim(), cdate=(c[9]||'').trim();
    if(code==='客戶/收貨人' || /^客戶/.test(code)) continue; // 標題列
    if(code){
      cur={ id:'C'+Date.now().toString(36)+Math.random().toString(36).slice(2,6),
        sysno:code, name, type:'直接農民',
        phone:(tel&&tel!=='0')?tel:'', address:addr, regAddress:'', taxid:tax,
        filedDate:fmtYmd(cdate), contact:'', idno:'', birth:'', terms:'', checkPeriod:'',
        conditions:'', currentFert:'', truck:'', deliveryTime:'', grade:'', notes:'',
        freq:null, last:'', next:'', inter:[], products:[] };
      out.push(cur);
    } else if(sub && cur && addr){ // 子列＝同客戶戶籍地
      if(!cur.regAddress) cur.regAddress=addr;
      else cur.notes=(cur.notes?cur.notes+'\n':'')+'其他地址：'+addr;
    }
  }
  return out.filter(c=>c.name);
}
function importCustomerFile(input){
  const f=input.files[0]; if(!f) return;
  const r=new FileReader();
  r.onload=()=>{
    let text='';
    try{ text=new TextDecoder('big5').decode(r.result); }catch(e){ text=''; }
    // big5 解不出（出現大量替代字元）就改 utf-8
    if(!text || (text.match(/�/g)||[]).length>20){
      try{ text=new TextDecoder('utf-8').decode(r.result); }catch(e){}
    }
    let rows;
    try{ rows=parseCustomerTSV(text); }catch(e){ alert('檔案解析失敗：'+e.message); return; }
    if(!rows.length){ alert('讀不到客戶資料，請確認是 SAP ZSD29 匯出的檔案'); return; }
    const bySys=new Map(), byName=new Map();
    customers.forEach(c=>{ if(c.sysno)bySys.set(c.sysno,c); byName.set(c.name,c); });
    let add=0, upd=0;
    rows.forEach(nc=>{
      const ex=(nc.sysno&&bySys.get(nc.sysno)) || byName.get(nc.name);
      if(ex){
        ['sysno','phone','address','regAddress','taxid','filedDate'].forEach(k=>{ if(nc[k]&&!ex[k]) ex[k]=nc[k]; });
        upd++;
      } else { customers.push(nc); if(nc.sysno)bySys.set(nc.sysno,nc); byName.set(nc.name,nc); add++; }
    });
    saveCust(); render();
    alert(`✅ 匯入完成\n新增 ${add} 位、更新 ${upd} 位\n（身分證、出生年月日、票期、產品報價等請逐筆補上）`);
  };
  r.readAsArrayBuffer(f); input.value='';
}

// ========== 拜訪路線規劃 ==========
// rules: 多組條件，每組 {status, channel, grade, n}，分別挑選後合併成一條路線
let routeCfg = {region:'', home:'', start:'08:00', end:'17:00', dwell:40, nl:'', rules:[{status:'',channel:'',grade:'',n:5}], _last:''};
const ROUTE_CHANS = ['農會','合作社','肥料行','有機農戶'];
// 自然語言→組合：完全離線解析（免費、不外傳）
const CN_NUM={零:0,一:1,二:2,兩:2,三:3,四:4,五:5,六:6,七:7,八:8,九:9,十:10};
function cn2num(s){ if(/^[0-9]+$/.test(s))return +s; if(s==='十')return 10; const m=s.match(/^(.)?十(.)?$/); if(m){const t=m[1]?(CN_NUM[m[1]]||1):1; const o=m[2]?(CN_NUM[m[2]]||0):0; return t*10+o;} return CN_NUM[s]||null; }
function parseRouteText(raw){
  const s=(raw||'').replace(/[、，,+＋和跟與及\/個家]/g,' ');
  const re=/(陌生|生客|開發|既有|回訪|老客戶?)?\s*(農會|合作社|肥料行|經銷商|資材行|直接農民|有機農戶|農戶|農民)\s*([ABCDabcd])?\s*級?\s*([0-9]+|[一二兩三四五六七八九十]+)?/g;
  const out=[]; let m;
  while((m=re.exec(s))){
    if(!m[2]){ if(m.index===re.lastIndex) re.lastIndex++; continue; }
    const st=/陌生|生客|開發/.test(m[1]||'')?'cold':(/既有|回訪|老客/.test(m[1]||'')?'existing':'');
    let ch=m[2]; if(ch==='經銷商'||ch==='資材行')ch='肥料行'; if(ch==='直接農民'||ch==='農戶'||ch==='農民')ch='有機農戶';
    const g=(m[3]||'').toUpperCase();
    let n=m[4]?cn2num(m[4]):1; if(!n||n<1)n=1; n=Math.min(9,n);
    out.push({status:st, channel:ch, grade:g, n});
  }
  return out;
}
function parseNL(){
  routeCfg.region=$('#r-region').value;
  const nlEl=$('#r-nl'); routeCfg.nl=nlEl?nlEl.value:'';
  const homeEl=$('#r-home'); if(homeEl)routeCfg.home=homeEl.value.trim();
  const sEl=$('#r-start'); if(sEl)routeCfg.start=sEl.value||'08:00';
  const eEl=$('#r-end'); if(eEl)routeCfg.end=eEl.value||'17:00';
  const dEl=$('#r-dwell'); if(dEl)routeCfg.dwell=Math.max(10,+dEl.value||40);
  const rules=parseRouteText(routeCfg.nl);
  if(!rules.length){ toast('看不懂耶，照範例輸入，例如「陌生農會1 既有合作社2」'); return; }
  routeCfg.rules=rules; renderRoute(); toast(`已建立 ${rules.length} 組條件，可再微調`);
}
const ST_OPTS = [['','全部狀態'],['cold','陌生目標客戶'],['existing','既有客戶']];
function statusOpts(v){ return ST_OPTS.map(([k,l])=>`<option value="${k}" ${v===k?'selected':''}>${l}</option>`).join(''); }
function chanOpts(v){ return `<option value="" ${v===''?'selected':''}>全部通路</option>`+ROUTE_CHANS.map(c=>`<option value="${c}" ${v===c?'selected':''}>${c}</option>`).join(''); }
function gradeOpts(v){ return `<option value="" ${v===''?'selected':''}>全部分級</option>`+GRADES.map(g=>`<option value="${g}" ${v===g?'selected':''}>${g}級・${GRADE_LABEL[g]}</option>`).join(''); }
function ruleCard(r,i,canDel){
  return `<div class="rcard">
    <div class="rcard-h"><b>組合 ${i+1}</b>${canDel?`<button class="rule-del" onclick="removeRule(${i})">✕ 移除</button>`:''}</div>
    <div class="field-2">
      <div class="field"><label>客戶狀態</label><select class="rr-status">${statusOpts(r.status)}</select></div>
      <div class="field"><label>通路</label><select class="rr-channel">${chanOpts(r.channel)}</select></div></div>
    <div class="field-2">
      <div class="field"><label>分級(僅既有)</label><select class="rr-grade">${gradeOpts(r.grade)}</select></div>
      <div class="field"><label>家數</label><input class="rr-n" type="number" min="1" max="9" value="${r.n}"></div></div>
  </div>`;
}
// ---------- 模式切換：每週智慧排程 / 自訂單日路線 ----------
let routeMode = 'week';
function setRouteMode(m){ routeMode=m; renderRoute(); }
function renderRoute(){
  let h=`<div class="seg">
    <button class="seg-b ${routeMode==='week'?'on':''}" onclick="setRouteMode('week')">📅 每週智慧排程</button>
    <button class="seg-b ${routeMode==='custom'?'on':''}" onclick="setRouteMode('custom')">🗺️ 自訂單日路線</button></div>
    <div id="route-body"></div>`;
  $('#view').innerHTML=h;
  if(routeMode==='week') renderWeekRoute(); else renderCustomRoute();
}

// ========== 每週拜訪智慧排程 ==========
let weekCfg = { start:'', days:[1,2,3,4,5], maxPerDay:6, region:'', mode:'all', _last:'' };
const WD_NAME = ['日','一','二','三','四','五','六'];
function thisMonday(){ const d=new Date(); const w=d.getDay(); d.setDate(d.getDate()+(w===0?-6:1-w)); return d.toISOString().slice(0,10); }
function gradeFreq(g){ return GRADE_FREQ[g]||null; }
function syncWeek(){
  const s=$('#w-start'); if(s)weekCfg.start=s.value||weekCfg.start;
  const m=$('#w-max'); if(m)weekCfg.maxPerDay=Math.max(1,Math.min(12,+m.value||6));
  const r=$('#w-region'); if(r)weekCfg.region=r.value;
  const md=$('#w-mode'); if(md)weekCfg.mode=md.value;
}
function toggleWeekDay(wd){ syncWeek(); const i=weekCfg.days.indexOf(wd); if(i<0)weekCfg.days.push(wd); else weekCfg.days.splice(i,1); renderRoute(); }
function renderWeekRoute(){
  const regs = regionsSorted();
  if(weekCfg.region===''&&weekCfg._inited!==1){ weekCfg.region = regs.find(r=>normR(r).includes('臺南')) || ''; weekCfg._inited=1; }
  if(!weekCfg.start) weekCfg.start=thisMonday();
  let h=`<div class="info">系統自動收集「到期 / 逾期」要回訪的客戶與名單，加上依分級頻率該回訪的對象，按鄉鎮就近分配到本週各出訪日。全程本機計算、不外傳。</div>`;
  h+=`<div class="card">`;
  h+=`<div class="field"><label>本週起始日（週一）</label><input type="date" id="w-start" value="${weekCfg.start}"></div>`;
  h+=`<div class="field"><label>區域（限定責任區，留空＝全部）</label><select id="w-region"><option value="">全部區域</option>${regs.map(r=>`<option value="${esc(r)}" ${r===weekCfg.region?'selected':''}>${esc(r)}</option>`).join('')}</select></div>`;
  h+=`<div class="field"><label>出訪日（可複選）</label><div class="wdays">${[1,2,3,4,5,6,0].map(wd=>`<button type="button" class="chip ${weekCfg.days.includes(wd)?'on':''}" onclick="toggleWeekDay(${wd})">週${WD_NAME[wd]}</button>`).join('')}</div></div>`;
  h+=`<div class="field-2"><div class="field"><label>每日最多家數</label><input type="number" id="w-max" min="1" max="12" value="${weekCfg.maxPerDay}"></div>
      <div class="field"><label>排程範圍</label><select id="w-mode"><option value="all" ${weekCfg.mode==='all'?'selected':''}>到期＋依分級建議(推薦)</option><option value="due" ${weekCfg.mode==='due'?'selected':''}>只排已設下次拜訪日</option></select></div></div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" onclick="planWeek()">📅 產生本週拜訪計畫</button></div>`;
  h+=`</div><div id="week-result">${weekCfg._last||''}</div>`;
  $('#route-body').innerHTML=h;
}
// 收集本週該拜訪的對象（客戶＋有排程/分級的名單）
function collectVisitTargets(region, weekEnd, includeGrade){
  const core = region ? normR(region).replace(/[縣市]$/,'') : '';
  const exIds = existingProspectIds();
  const today = todayStr();
  const list=[];
  const push=(o, base)=>{
    let next=o.next||'';
    if(!next && includeGrade && base.grade){ const f=gradeFreq(base.grade); if(f) next = o.last? addDays(o.last,f) : today; }
    if(!next) return;
    if(next>weekEnd) return;          // 還沒到本週範圍
    const d=daysBetween(today,next);
    const reason = o.next ? (d<0?`逾期${-d}天`:(d===0?'今天到期':`${d}天後到期`))
                          : (o.last?`分級${base.grade}・約${gradeFreq(base.grade)}天回訪`:`分級${base.grade}・建議首訪`);
    list.push(Object.assign({}, base, {next, sort:d, overdue:d<0, reason}));
  };
  customers.forEach(c=>{
    if(core && !normR(c.address||'').includes(core)) return;
    push({next:c.next,last:c.last}, {kind:'cust',id:c.id,name:c.name,channel:TYPE2CHAN[c.type]||c.type||'其他',status:'existing',grade:c.grade||'',address:c.address||'',phone:c.phone||'',district:district(c.address)});
  });
  SEED.forEach(p=>{
    const o=overlay[p.id]; if(!o) return;   // 名單沒有任何排程才不掃，避免 3547 筆全進來
    if(core && !(normR(p.region||'')===normR(region) || normR(p.address||'').includes(core))) return;
    push({next:o.next,last:o.last}, {kind:'prosp',id:p.id,name:p.name,channel:p.category||'其他',status:exIds.has(p.id)?'existing':'cold',grade:o.grade||'',address:p.address||'',phone:p.phone||'',district:district(p.address)});
  });
  const seen=new Set();
  return list.filter(x=>{const k=x.name+x.address; if(seen.has(k))return false; seen.add(k); return true;});
}
function planWeek(){
  syncWeek();
  const start=weekCfg.start||thisMonday();
  const days=weekCfg.days.slice().sort((a,b)=>(a===0?7:a)-(b===0?7:b));
  const resEl=()=>$('#week-result');
  if(!days.length){ toast('請至少選一個出訪日'); return; }
  const weekEnd=addDays(start,6);
  const includeGrade=weekCfg.mode==='all';
  const targets=collectVisitTargets(weekCfg.region,weekEnd,includeGrade);
  if(!targets.length){
    weekCfg._last=`<div class="card empty"><div class="big">📭</div>本週（${start} ～ ${weekEnd}）沒有到期或建議拜訪的對象。<br>到「我的客戶」或「名單」設定分級或下次拜訪日，就會自動排入。</div>`;
    resEl().innerHTML=weekCfg._last; return;
  }
  // 依鄉鎮急迫度排序：同鄉鎮集中、急的先排
  const townUrg={};
  targets.forEach(t=>{ const k=t.district||'其他'; if(!(k in townUrg)||t.sort<townUrg[k]) townUrg[k]=t.sort; });
  targets.sort((a,b)=>{ const ua=townUrg[a.district||'其他'],ub=townUrg[b.district||'其他']; if(ua!==ub)return ua-ub; const da=a.district||'其他',db=b.district||'其他'; if(da!==db)return da.localeCompare(db,'zh-Hant'); return a.sort-b.sort; });
  const dayDates=days.map(wd=>addDays(start, wd===0?6:wd-1));
  const cap=weekCfg.maxPerDay, totalSlots=dayDates.length*cap;
  const scheduled=targets.slice(0,totalSlots), overflow=targets.slice(totalSlots);
  const buckets=dayDates.map((d,i)=>({date:d, wd:days[i], items:[]}));
  let bi=0; scheduled.forEach(t=>{ while(bi<buckets.length-1 && buckets[bi].items.length>=cap) bi++; buckets[bi].items.push(t); });
  const overdue=targets.filter(t=>t.overdue).length;

  let h=`<div class="sec-title"><span class="bar"></span>本週拜訪計畫</div><div class="card">`;
  h+=drow('期間', `${start} ～ ${weekEnd}`);
  h+=drow('總計', `${targets.length} 家（逾期 ${overdue}）｜排入 ${scheduled.length} 家／${buckets.filter(b=>b.items.length).length} 個出訪日`);
  if(overflow.length) h+=drow('順延', `${overflow.length} 家本週排不完，可增加出訪日或每日家數，否則下週優先安排`);
  h+=`</div>`;
  buckets.forEach(b=>{
    h+=`<div class="sec-title" style="margin-top:14px"><span class="bar"></span>週${WD_NAME[b.wd]}　${b.date.slice(5)}　(${b.items.length} 家)</div>`;
    if(!b.items.length){ h+=`<div class="card empty" style="padding:16px">這天暫無安排</div>`; return; }
    h+=`<div class="card" style="padding:4px 14px">`;
    b.items.forEach((x,i)=>{
      const tel=(x.phone||'').split('/')[0].replace(/[^\d+]/g,'');
      const pill=`<span class="badge ${x.overdue?'pill-over':'pill-due'}">${esc(x.reason)}</span>`;
      h+=`<div class="item" onclick="${x.kind==='cust'?`viewCustomer('${x.id}')`:`viewProspect('${x.id}')`}">
        <div class="avatar" style="background:${colorFor(x.name)}">${i+1}</div>
        <div class="body"><div class="nm">${esc(x.name)}</div>
          <div class="sub">${esc([x.district,x.address].filter(Boolean).join(' · '))}</div>
          <div class="tagline" style="margin-top:4px">${pill} <span class="badge b-${x.channel}">${esc(x.channel)}</span>${x.grade?` <span class="badge grade-${x.grade}">${x.grade}</span>`:''}${x.status==='cold'?' <span class="badge">陌生</span>':''}</div></div>
        <div class="meta">${x.address?`<a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(x.address)}" target="_blank" onclick="event.stopPropagation()">導航</a>`:''}${tel.length>=6?`<br><a href="tel:${tel}" onclick="event.stopPropagation()">電話</a>`:''}</div>
      </div>`;
    });
    h+=`</div>`;
    const addrs=b.items.filter(x=>x.address).map(x=>encodeURIComponent(x.address));
    if(addrs.length){
      const origin=weekCfg.region||'';
      const url=`https://www.google.com/maps/dir/?api=1&${origin?`origin=${encodeURIComponent(origin)}&`:''}destination=${addrs[addrs.length-1]}&travelmode=driving&waypoints=${addrs.slice(0,-1).join('%7C')}`;
      h+=`<div class="btn-row" style="margin-top:8px"><a class="btn btn-out" style="text-decoration:none" href="${url}" target="_blank">🚗 用 Google 地圖開這天路線</a></div>`;
    }
  });
  h+=`<div class="tagline" style="margin:10px 2px 0">排序原則：逾期/急迫優先、同鄉鎮集中同一天以減少往返。點任一家可進客戶頁；記錄拜訪後會自動排下次。</div>`;
  weekCfg._last=h; resEl().innerHTML=h;
  resEl().scrollIntoView({behavior:'smooth',block:'start'});
}

function renderCustomRoute(){
  const regs = regionsSorted();
  if(!routeCfg.region) routeCfg.region = regs.find(r=>normR(r).includes('臺南')) || regs[0] || '';
  if(!routeCfg.rules||!routeCfg.rules.length) routeCfg.rules=[{status:'',channel:'',grade:'',n:5}];
  let h=`<div class="info">可加多組條件(例如:陌生×肥料行 2 家 + 既有×農會 1 家),系統會分別挑選再合併排成一條順路路線。資料皆在本機計算。</div>`;
  h+=`<div class="card"><div class="field"><label>區域</label><select id="r-region">${regs.map(r=>`<option ${r===routeCfg.region?'selected':''}>${esc(r)}</option>`).join('')}</select></div></div>`;
  h+=`<div class="card">`;
  h+=`<div class="field"><label>🤖 智慧輸入（用打的，自動拆成下面的組合）</label>
      <input id="r-nl" value="${esc(routeCfg.nl)}" placeholder="例如：陌生農會1 陌生合作社2 陌生直接農民3 既有經銷商2"></div>`;
  h+=`<div class="btn-row" style="margin-top:0"><button class="btn btn-out" onclick="parseNL()">✨ 解析成組合</button></div>`;
  h+=`<div class="tagline" style="margin-top:6px">看得懂：陌生／既有・農會／合作社／肥料行(經銷商)／有機農戶(直接農民)・可加 A~D 級・數字＝家數。完全離線、不外傳。</div>`;
  h+=`</div>`;
  h+=`<div class="sec-title"><span class="bar"></span>拜訪組合</div>`;
  h+=`<div id="rules">${routeCfg.rules.map((r,i)=>ruleCard(r,i,routeCfg.rules.length>1)).join('')}</div>`;
  h+=`<div class="more" onclick="addRule()">＋ 新增一組條件</div>`;
  h+=`<div class="card">`;
  h+=`<div class="field"><label>出發 / 返回地點</label><input id="r-home" value="${esc(routeCfg.home)}" placeholder="例如 台南市東區自家地址(留空則用區域中心)"></div>`;
  h+=`<div class="field-2">
      <div class="field"><label>出門時間</label><input type="time" id="r-start" value="${routeCfg.start}"></div>
      <div class="field"><label>回家時間</label><input type="time" id="r-end" value="${routeCfg.end}"></div></div>`;
  h+=`<div class="field"><label>每家停留(分)</label><input type="number" id="r-dwell" min="10" step="5" value="${routeCfg.dwell}"></div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" onclick="planRoute()">🗺️ 產生路線</button></div>`;
  h+=`</div><div id="route-result">${routeCfg._last||''}</div>`;
  $('#route-body').innerHTML=h;
}
function readRules(){
  return [...document.querySelectorAll('#rules .rcard')].map(el=>({
    status:el.querySelector('.rr-status').value,
    channel:el.querySelector('.rr-channel').value,
    grade:el.querySelector('.rr-grade').value,
    n:Math.min(9,Math.max(1,+el.querySelector('.rr-n').value||1))
  }));
}
function syncRoute(){
  routeCfg.region=$('#r-region').value;
  const nlEl=$('#r-nl'); if(nlEl) routeCfg.nl=nlEl.value;
  routeCfg.home=$('#r-home').value.trim();
  routeCfg.start=$('#r-start').value||'08:00';
  routeCfg.end=$('#r-end').value||'17:00';
  routeCfg.dwell=Math.max(10,+$('#r-dwell').value||40);
  routeCfg.rules=readRules();
}
function addRule(){ syncRoute(); routeCfg.rules.push({status:'',channel:'',grade:'',n:1}); renderRoute(); }
function removeRule(i){ syncRoute(); routeCfg.rules.splice(i,1); if(!routeCfg.rules.length)routeCfg.rules=[{status:'',channel:'',grade:'',n:5}]; renderRoute(); }
function planRoute(){
  syncRoute();
  const core=normR(routeCfg.region).replace(/[縣市]$/,'');
  const exIds=existingProspectIds();
  let pool=[];
  customers.forEach(c=>{ if(!c.address)return; if(normR(c.address).includes(core))
    pool.push({kind:'cust',id:c.id,name:c.name,channel:TYPE2CHAN[c.type]||c.type,status:'existing',grade:c.grade||'',address:c.address,phone:c.phone,district:district(c.address),due:dueInfo(c)}); });
  SEED.forEach(p=>{ if(!p.address)return; if(normR(p.region)===normR(routeCfg.region)||normR(p.address).includes(core))
    pool.push({kind:'prosp',id:p.id,name:p.name,channel:p.category,status:exIds.has(p.id)?'existing':'cold',grade:'',address:p.address,phone:p.phone,district:district(p.address),due:dueInfo(overlay[p.id])}); });
  const dseen=new Set(); pool=pool.filter(x=>{const k=x.name+x.address; if(dseen.has(k))return false; dseen.add(k); return true;});
  const byDue=(a,b)=>((a.due?a.due.sort:999)-(b.due?b.due.sort:999));
  let pick=[]; const used=new Set();
  routeCfg.rules.forEach(r=>{
    pool.filter(x=>!used.has(x.name+x.address)
        && (!r.status||x.status===r.status)
        && (!r.channel||x.channel===r.channel)
        && (!r.grade||x.grade===r.grade))
      .sort(byDue).slice(0,r.n)
      .forEach(x=>{ used.add(x.name+x.address); pick.push(x); });
  });
  if(!pick.length){ routeCfg._last=`<div class="card empty"><div class="big">📍</div>「${esc(routeCfg.region)}」找不到符合組合條件的對象。<br>放寬條件，或換個區域再試。</div>`; $('#route-result').innerHTML=routeCfg._last; return; }
  pick.sort((a,b)=>(a.district||'').localeCompare(b.district||'','zh-Hant'));

  const n=pick.length, toMin=t=>{const[a,b]=t.split(':').map(Number);return a*60+b;};
  const fmt=m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(Math.round(m%60)).padStart(2,'0')}`;
  const s=toMin(routeCfg.start), e=toMin(routeCfg.end), lunch=60;
  const per=(e-s-lunch)/n, travel=Math.max(10,Math.round(per-routeCfg.dwell));
  let t=s, lunchDone=false;
  pick.forEach((x,i)=>{ if(!lunchDone && t>=12*60){ x._lunch=true; t+=lunch; lunchDone=true; } x.arrive=fmt(t); t+=routeCfg.dwell; x.leave=fmt(t); if(i<n-1)t+=travel; });
  const back=t+travel;
  let warn='';
  if(per<routeCfg.dwell+10) warn=`時間偏緊:${n} 家 ×(停留${routeCfg.dwell}分+車程)可能塞不進 ${routeCfg.start}–${routeCfg.end},建議減少家數或縮短停留。`;
  else if(back>e) warn=`依估算約 ${fmt(back)} 才到家,略晚於 ${routeCfg.end}。可縮短停留或少拜訪一家。`;

  let h=`<div class="sec-title"><span class="bar"></span>建議路線(${n} 家)</div>`;
  if(warn) h+=`<div class="info" style="background:var(--amber-l);color:var(--amber)">⚠️ ${esc(warn)}</div>`;
  h+=`<div class="card">`;
  h+=drow('區域', esc(routeCfg.region));
  const stMap={'':'全部',cold:'陌生',existing:'既有'};
  const ruleDesc=routeCfg.rules.map(r=>`${stMap[r.status]}・${r.channel||'全通路'}${r.grade?'・'+r.grade+'級':''} ×${r.n}`).join('　＋　');
  h+=drow('組合', esc(ruleDesc)+`（共要 ${routeCfg.rules.reduce((a,r)=>a+r.n,0)} 家，實排 ${n} 家）`);
  h+=drow('時程', `${routeCfg.start} 出發 → 預計 ${fmt(back)} 到家`);
  h+=`</div>`;
  h+=`<div class="card" style="padding:4px 14px">`;
  pick.forEach((x,i)=>{
    if(x._lunch) h+=`<div class="drow"><div class="k">🍱 午餐</div><div class="v">12:00–13:00 休息</div></div>`;
    const tel=(x.phone||'').split('/')[0].replace(/[^\d+]/g,'');
    h+=`<div class="item" style="cursor:default">
      <div class="avatar" style="background:${colorFor(x.name)}">${i+1}</div>
      <div class="body"><div class="nm">${esc(x.name)}</div>
        <div class="sub">${esc([x.district,x.address].filter(Boolean).join(' · '))}</div>
        <div class="tagline" style="margin-top:4px">🕐 ${x.arrive}–${x.leave}　<span class="badge b-${x.channel}">${esc(x.channel)}</span>${x.grade?` <span class="badge grade-${x.grade}">${x.grade}</span>`:''}</div></div>
      <div class="meta"><a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(x.address)}" target="_blank">導航</a>${tel.length>=6?`<br><a href="tel:${tel}">電話</a>`:''}</div>
    </div>`;
  });
  h+=`</div>`;
  const origin=routeCfg.home||routeCfg.region;
  const url=`https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(origin)}&travelmode=driving&waypoints=${pick.map(x=>encodeURIComponent(x.address)).join('%7C')}`;
  h+=`<div class="btn-row"><a class="btn btn-pri" style="text-decoration:none" href="${url}" target="_blank">🚗 用 Google 地圖開啟整條路線</a></div>`;
  h+=`<div class="tagline" style="margin:8px 2px 0">時間為估算(午休約60分、各站車程約${travel}分);地圖會依實際道路顯示,順序可在地圖中拖曳微調。</div>`;
  const tips=['出發前先電話確認對方在場;農會、合作社中午常有午休(約 12:00–13:30)。',
    '帶齊型錄/DM、試用樣品、報價單與名片。',
    '已成交客戶順道確認庫存、收票與票期。',
    '偏遠農戶地址可能不精準,先用導航確認位置再出發。',
    '每拜訪完立刻在 App 記一筆互動紀錄,避免回家忘記。',
    '帶足現金/油資,留意當日天氣與道路狀況。'];
  h+=`<div class="sec-title"><span class="bar"></span>注意事項</div><div class="card"><ul style="margin:0;padding-left:18px;line-height:1.9">${tips.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`;
  routeCfg._last=h; $('#route-result').innerHTML=h;
  $('#route-result').scrollIntoView({behavior:'smooth',block:'start'});
}

// ---------- modal ----------
function openModal(title, html){ $('#m-title').textContent=title; $('#m-body').innerHTML=html; $('#modal').classList.add('show'); }
function closeModal(){ $('#modal').classList.remove('show'); }
$('#modal').addEventListener('click',e=>{ if(e.target.id==='modal') closeModal(); });

// ---------- 啟動 ----------
function isInLineApp(){ return /Line\//i.test(navigator.userAgent||''); }
function appUrl(){ return location.href.split('#')[0].split('?')[0]; }
function copyAppUrl(){
  const u=appUrl();
  if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(u).then(()=>toast('已複製網址，貼到 Safari 開啟'),()=>toast(u)); }
  else toast(u);
}
function showInAppWarning(){
  if(!isInLineApp()||document.getElementById('inapp-warn')) return;
  const bar=document.createElement('div');
  bar.id='inapp-warn';
  bar.innerHTML=`⚠️ 你正在 <b>LINE 內建瀏覽器</b>開啟，這裡輸入的客戶資料 <b>不會被儲存</b>！<br>請改用手機<b>主畫面的「客戶戰情室」圖示</b>開啟（或用 Safari／Chrome）。
    <div class="wbtns"><button class="wcopy" onclick="copyAppUrl()">複製網址</button><button class="wok" onclick="document.getElementById('inapp-warn').remove()">知道了</button></div>`;
  document.body.appendChild(bar);
}
function initApp(){
  const valid=['home','map','prospects','route','customers','settings'];
  const hash=(location.hash||'').replace('#','');
  go(valid.includes(hash)?hash:'home');
  showInAppWarning();
}
window.addEventListener('hashchange',()=>{ const h=(location.hash||'').replace('#',''); const valid=['home','map','prospects','route','customers','settings']; if(valid.includes(h)) go(h); });
initApp();
