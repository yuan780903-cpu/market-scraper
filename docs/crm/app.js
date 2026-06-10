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
let competitors = LS.get('crm_competitors', []); // 競品報價（本機）
const saveOverlay = () => LS.set('crm_overlay', overlay);
const saveCust = () => LS.set('crm_customers', customers);
const saveComp = () => LS.set('crm_competitors', competitors);
// 臨時目標客戶（使用者手動新增，只存本機）：併入 SEED，讓名單/地圖/排路線各處自動納入
let customProspects = LS.get('crm_prospects', []);
customProspects.forEach(p=>{ if(p&&p.id&&!SEED.some(s=>s.id===p.id)) SEED.push(p); });
const saveProspects = () => LS.set('crm_prospects', customProspects);

// 戰鬥人員（戰情公仔）— 只存本機
let soldier = LS.get('crm_soldier', {name:'', region:[], branch:'army', weapon:'rifle', photo:''});
if(!Array.isArray(soldier.region)) soldier.region = [];   // region：所屬戰鬥區域(縣市，可複選)＝戰情地圖負責銷售區域
const saveSoldier = () => LS.set('crm_soldier', soldier);
function getRegions(){ if(!Array.isArray(soldier.region)) soldier.region=[]; return soldier.region; }
function toggleRegion(n){ const a=getRegions(), i=a.indexOf(n); if(i>=0)a.splice(i,1); else a.push(n); saveSoldier(); }
function clearRegions(){ soldier.region=[]; saveSoldier(); }
// 縣市清單（北到南），供地圖與設定共用
function countyNames(){ return window.TW_MAP ? Object.keys(window.TW_MAP.counties).sort((a,b)=>REGION_ORDER.findIndex(x=>normR(a).includes(x))-REGION_ORDER.findIndex(x=>normR(b).includes(x))) : []; }
const BRANCHES = {
  army:{label:'陸軍', emoji:'🪖', uni:'#586b3f', uni2:'#46552f', skin:'#ffd9b0'},
  navy:{label:'海軍', emoji:'⚓', uni:'#23436b', uni2:'#172e4d', skin:'#ffd9b0'},
  air :{label:'空軍', emoji:'✈️', uni:'#4f6f8f', uni2:'#3a5773', skin:'#ffd9b0'}
};
const WEAPONS = {
  water  :{label:'水槍',  emoji:'💦'},
  pistol :{label:'手槍',  emoji:'🔫'},
  rifle  :{label:'步槍',  emoji:'🔫'},
  mg     :{label:'機關槍',emoji:'🔥'},
  tank   :{label:'坦克車',emoji:'🛡️'},
  jet    :{label:'戰鬥機',emoji:'✈️'},
  carrier:{label:'航空母艦',emoji:'🚢'}
};
const SOLDIER_LINES = ['報告長官！士氣高昂 💪','保證達成業績目標！','衝啊！拿下這張訂單！','碩成肥料・使命必達 🫡','今天也要努力跑客戶！','敵不動我不動，敵一動我成交！','一鼓作氣，攻下這區！','嘿嘿～再摸我會害羞 😆'];

const CATS = ['農會','合作社','肥料行','有機農戶','競爭對手','驗證機構','友善團體','有機促進區'];
const CUST_TYPES = ['農會','合作社','經銷商','直接農民','其他'];

// 產品報價用：9 項正式品名、性狀、重量、含運、票期
const PRODUCTS = ['碩成508','碩成1號+','碩成2號','碩成2號+','碩成生技1號','碩成果美肥','碩成基肥1號','碩成基肥2號','碩成基肥2號+'];
const FORMS = ['粒狀','粉狀'];          // 性狀
const WEIGHTS = ['20','25','500','1000']; // 規格公斤（粒狀固定20，粉狀多規格）
const FREIGHTS = ['含運','不含運'];
const CHECK_PERIODS = ['現金','月結5天','月結15天','月結30天','月結45天','月結60天'];
// 種植 / 用肥（非經銷商通路）
const COMMON_CROPS = ['水稻','蔬菜','果樹','茶','花卉','雜糧','根莖類','菇類','檳榔','其他'];
const AREA_UNITS = ['公頃','甲','分','坪'];
const LOC_TYPES = ['住家','下貨位置','倉庫','田區','其他'];

// 區域（依台灣由北到南排序）
const REGION_ORDER = '基隆 臺北 新北 桃園 新竹 苗栗 臺中 彰化 南投 雲林 嘉義 臺南 高雄 屏東 宜蘭 花蓮 臺東 澎湖 金門 連江'.split(' ');
const normR = s => (s||'').replace(/台/g,'臺');
function regionsSorted(){
  // 只保留有效的台灣縣市（過濾掉名單裡誤填的數字、「全國」等雜訊）
  const set=[...new Set(SEED.map(p=>p.region).filter(Boolean))].filter(r=>countyCore(r));
  return set.sort((a,b)=>{
    const ia=REGION_ORDER.findIndex(x=>normR(a).includes(x));
    const ib=REGION_ORDER.findIndex(x=>normR(b).includes(x));
    return (ia<0?99:ia)-(ib<0?99:ib) || a.localeCompare(b);
  });
}
// 多選區域晶片（不選＝全部）：toggleFn 收到 regionsSorted() 的索引
function regionMultiHTML(selected, toggleFn){
  const regs=regionsSorted();
  if(!regs.length) return `<div class="hint">尚無區域資料</div>`;
  return `<div class="wdays">${regs.map((r,i)=>`<button type="button" class="chip ${selected.includes(r)?'on':''}" onclick="${toggleFn}(${i})">${esc(r)}</button>`).join('')}</div>`;
}
function toggleInArr(arr, r){ if(!r)return; const i=arr.indexOf(r); if(i<0)arr.push(r); else arr.splice(i,1); }
function toggleSmartRegion(i){ syncSmart(); toggleInArr(smartCfg.f.regions, regionsSorted()[i]); renderRoute(); }
function toggleWeekRegion(i){ syncWeek(); toggleInArr(weekCfg.regions, regionsSorted()[i]); renderRoute(); }
function toggleRouteRegion(i){ syncRoute(); toggleInArr(routeCfg.regions, regionsSorted()[i]); renderRoute(); }
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
let tab = 'map';
let pFilter = {status:'', cat:'', region:'', q:'', area:'', organic:''};      // 名單篩選
function inOrganic(p,v){ if(!v) return true; return v==='org' ? p.category==='有機農戶' : p.category!=='有機農戶'; }
// 經營面積級距（公頃）— 多為有機農戶；選了級距會排除無面積資料者
const AREA_BANDS = [
  {k:'lt1', label:'未滿1公頃', test:n=>n<1},
  {k:'1-3', label:'1–3公頃', test:n=>n>=1&&n<3},
  {k:'3-5', label:'3–5公頃', test:n=>n>=3&&n<5},
  {k:'5-10', label:'5–10公頃', test:n=>n>=5&&n<10},
  {k:'10+', label:'10公頃以上', test:n=>n>=10},
];
function areaVal(p){ const n=parseFloat(p&&p.area); return isNaN(n)?null:n; }
function inAreaBand(p,k){ if(!k) return true; const n=areaVal(p); if(n==null) return false; const b=AREA_BANDS.find(x=>x.k===k); return b?b.test(n):true; }
let pLimit = 60;
function go(t){
  tab = t; pLimit = 60;
  document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('on', b.dataset.tab===t));
  $('#title').textContent = {home:'戰情總覽',map:'戰情地圖',prospects:'目標名單',route:'智慧拜訪規劃',customers:'我的客戶',compete:'即時競品價格',report:'拜訪週報',settings:'設定 / 備份'}[t];
  $('#fab').style.display = (t==='customers') ? 'block' : 'none';
  window.scrollTo(0,0);
  render();
}
function onFab(){ if(tab==='customers') editCustomer(null); }

// ---------- 渲染分派 ----------
function render(){ ({home:renderHome,map:renderMap,prospects:renderProspects,route:renderRoute,customers:renderCustomers,compete:renderCompetitors,report:renderReport,settings:renderSettings}[tab])(); }

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
  if(window.TW_MAP){
    const core=countyCore(region);
    const key=Object.keys(window.TW_MAP.counties).find(k=>countyCore(k)===core);
    soldier.region=key?[key]:[]; saveSoldier(); mapState.town=-1;
  }
  go('map');
}
function gotoMapTown(i){ go('map'); mapTapTown(i); }

// ========== 首頁（戰情儀表板） ==========
// ---------- 軍事圖標（白色剪影 SVG）----------
const MIL_ICON = {
  radar: `<svg viewBox="0 0 32 32" fill="none" stroke="#fff" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 26h22"/><path d="M16 26v-9"/><path d="M16 17 6.5 13.5 9 7l9.5 3.5z" fill="#fff" stroke="none"/><path d="M20.5 9.5A7.5 7.5 0 0 1 25 16"/><path d="M22.5 5.5A11.5 11.5 0 0 1 29 15"/></svg>`,
  target: `<svg viewBox="0 0 32 32" fill="none" stroke="#fff" stroke-width="2.3"><circle cx="16" cy="16" r="10"/><circle cx="16" cy="16" r="4.6"/><circle cx="16" cy="16" r="1.4" fill="#fff" stroke="none"/><path d="M16 2v6M16 24v6M2 16h6M24 16h6" stroke-linecap="round"/></svg>`,
  rifle: `<svg viewBox="0 0 32 32" fill="#fff"><rect x="3" y="13" width="26" height="3" rx="1"/><rect x="6.5" y="16" width="3" height="6.5" rx="1"/><path d="M22 16l-2.2 5.5h3.2L25 16z"/><rect x="12.5" y="9.6" width="2.4" height="3.6"/><rect x="26" y="11.5" width="3" height="1.6" rx=".6"/></svg>`,
  jet: `<svg viewBox="0 0 32 32" fill="#fff"><path d="M16 2c1.1 0 1.8 1.4 2 3l.5 8.5 10.5 5.5v2.6l-10.5-2.8-.4 5.4 3 2.6v2.2l-4.6-1.7-4.6 1.7v-2.2l3-2.6-.4-5.4L3.5 21.6V19l10.5-5.5L14 5c.2-1.6.9-3 2-3z"/></svg>`,
  tank: `<svg viewBox="0 0 32 32" fill="#fff"><rect x="3" y="18" width="24" height="6" rx="3"/><circle cx="8" cy="21" r="1.3" fill="#37431d"/><circle cx="13" cy="21" r="1.3" fill="#37431d"/><circle cx="18" cy="21" r="1.3" fill="#37431d"/><circle cx="23" cy="21" r="1.3" fill="#37431d"/><rect x="6" y="12.5" width="16" height="6" rx="1.5"/><rect x="11" y="8" width="8" height="5.5" rx="1.5"/><rect x="18" y="9.6" width="12" height="2.3" rx="1"/></svg>`,
  carrier: `<svg viewBox="0 0 32 32" fill="#fff"><path d="M3 20h26l-3.5 6H7z"/><rect x="4" y="16" width="25" height="3"/><rect x="20" y="9.5" width="4.2" height="6.5"/><rect x="21.3" y="5" width="1.6" height="4.5"/><path d="M7 16l3-3h6l-1.4 3z" fill="#37431d"/></svg>`,
  gear: `<svg viewBox="0 0 32 32" fill="#fff"><path d="M14.5 2h3l.55 3.1a9 9 0 0 1 2.05.85l2.6-1.7 2.1 2.1-1.7 2.6c.36.64.64 1.32.85 2.05L29 14.5v3l-3.1.55c-.21.73-.49 1.41-.85 2.05l1.7 2.6-2.1 2.1-2.6-1.7c-.64.36-1.32.64-2.05.85L17.5 30h-3l-.55-3.1a9 9 0 0 1-2.05-.85l-2.6 1.7-2.1-2.1 1.7-2.6a9 9 0 0 1-.85-2.05L3 17.5v-3l3.1-.55c.21-.73.49-1.41.85-2.05l-1.7-2.6 2.1-2.1 2.6 1.7c.64-.36 1.32-.64 2.05-.85L14.5 2z"/><circle cx="16" cy="16" r="4" fill="#37431d"/></svg>`
};
function milIcon(k){ return MIL_ICON[k]||''; }

// ---------- 各頁「作戰單位」抬頭卡（全站統一）----------
const PAGE_META = {
  map:       {icon:'radar',   code:'RECON',  title:'戰情地圖', desc:'戰區雷達 ・ 鄉鎮滲透'},
  prospects: {icon:'target',  code:'TARGET', title:'目標名單', desc:'狙擊目標 ・ 名單篩選'},
  customers: {icon:'rifle',   code:'ALLY',   title:'現有客戶', desc:'友軍部隊 ・ 拜訪跟進'},
  compete:   {icon:'jet',     code:'BOGEY',  title:'競品價格', desc:'敵機偵蒐 ・ 市場比價'},
  route:     {icon:'tank',    code:'ARMOR',  title:'智慧拜訪規劃', desc:'裝甲行軍 ・ 智慧排程'},
  report:    {icon:'carrier', code:'SITREP', title:'拜訪週報', desc:'航艦戰報 ・ 紀要生成'},
  settings:  {icon:'gear',    code:'LOGI',   title:'設定備份', desc:'軍械補給 ・ 資料備份'}
};
function pageHeader(k){ const m=PAGE_META[k]; if(!m) return '';
  return `<div class="unit-hd"><span class="uh-ic">${milIcon(m.icon)}</span><div class="uh-t"><div class="uh-code">${m.code}</div><div class="uh-title">${esc(m.title)}</div><div class="uh-desc">${esc(m.desc)}</div></div></div>`; }
// 統一寫入 #view：非首頁自動加上單位抬頭卡，直接重繪也保留
function viewHTML(html){ $('#view').innerHTML = (tab!=='home' ? pageHeader(tab) : '') + html; }

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

  // ── 戰區掌握度 KPI ──（功能總覽改由 LINE 選單導覽，首頁只留戰情看板）
  let h = `<div class="sec-title"><span class="bar"></span>戰區掌握度</div>`;
  h += `<div class="stat-grid">
    <div class="stat cust"><div class="n">${pct(cov.dev,cov.total)}%</div><div class="l">佔領率（成交）<br>${cov.dev} / ${cov.total} 家</div></div>
    <div class="stat prosp"><div class="n">${pct(cov.con,cov.total)}%</div><div class="l">接觸率（偵蒐）<br>${cov.con} / ${cov.total} 家</div></div>
    <div class="stat over"><div class="n">${overdue}</div><div class="l">逾期未出擊</div></div>
    <div class="stat due"><div class="n">${todayN}</div><div class="l">今日任務</div></div>
  </div>`;

  // ── 作戰快報：精簡卡片，點一張只看那一張的內容 ──
  const fups=getFollowUps();
  const regs=Object.entries(cov.region).filter(([,v])=>v.total>0)
    .sort((a,b)=>(b[1].total-b[1].dev)-(a[1].total-a[1].dev));
  const weakCounty=regs.length?regs[0][0]:'';
  let weakN=0;
  if(window.TW_MAP){ weakN=weakestTowns(computeTownStats(),8).length; }

  h += `<div class="sec-title"><span class="bar"></span>作戰快報 ・ 點卡片看內容</div><div class="card">`;
  h += homeTile('rifle', '本週出擊任務', tasks.length?`${tasks.length} 個任務${overdue?`・逾期 ${overdue}`:''}`:'目前沒有排定的拜訪', 'openHomeTasks()');
  h += homeTile('target','待辦戰術跟進', fups.length?`${fups.length} 項待辦`:'沒有待辦的跟進事項', 'openHomeFollow()');
  if(regs.length) h += homeTile('radar', '各縣市戰況', `共 ${regs.length} 縣市・最待開發：${esc(weakCounty)}`, 'openHomeCounty()');
  if(weakN)       h += homeTile('tank',  '優先攻佔鄉鎮', `名單多未開發 TOP ${weakN}`, 'openHomeTown()');
  h += `</div>`;
  $('#view').innerHTML = h;
}
function homeTile(icon,title,sum,onclick){
  return `<div class="item" onclick="${onclick}">
    <div class="avatar" style="background:#5d6651;font-size:18px">${milIcon(icon)}</div>
    <div class="body"><div class="nm">${esc(title)}</div><div class="sub">${esc(sum||'')}</div></div>
    <div class="meta" style="color:var(--muted);font-size:20px">›</div></div>`;
}
// ── 首頁快報的資料來源（重算，供卡片彈窗用）──
function getDueTasks(){
  const tasks=[];
  customers.forEach(c=>{ const di=dueInfo(c); if(di&&di.sort<=7) tasks.push({kind:'cust',ref:c,di,name:c.name,sub:c.type}); });
  Object.entries(overlay).forEach(([id,o])=>{ const di=dueInfo(o); if(di&&di.sort<=7){ const p=SEED.find(x=>x.id===id); if(p) tasks.push({kind:'prosp',ref:p,o,di,name:p.name,sub:p.category+(p.region?' · '+p.region:'')}); } });
  tasks.sort((a,b)=>a.di.sort-b.di.sort);
  return tasks;
}
function getFollowUps(){
  const fups=[];
  customers.forEach(c=>(c.follow||[]).forEach(f=>{ if(!f.done) fups.push({name:c.name,sub:c.type,kind:'cust',id:c.id,f}); }));
  Object.entries(overlay).forEach(([id,o])=>{ (o.follow||[]).forEach(f=>{ if(!f.done){ const p=SEED.find(x=>x.id===id); if(p) fups.push({name:p.name,sub:p.category,kind:'prosp',id,f}); } }); });
  fups.sort((a,b)=>((a.f.due||'9999').localeCompare(b.f.due||'9999')));
  return fups;
}
function openHomeTasks(){
  const tasks=getDueTasks();
  let h = tasks.length
    ? `<div class="card">`+tasks.map(t=>itemRow({ name:t.name, sub:t.sub, cat:(t.kind==='cust'?t.ref.type:t.ref.category),
        pill:`<span class="badge ${t.di.cls}">${t.di.txt}</span>`,
        onclick: t.kind==='cust'?`viewCustomer('${t.ref.id}')`:`viewProspect('${t.ref.id}')` })).join('')+`</div>`
    : `<div class="card empty"><div class="big">📭</div>目前沒有排定的拜訪。<br>到「名單」或「我的客戶」設定拜訪頻率即可自動排程。</div>`;
  openModal('本週出擊任務', h);
}
function openHomeFollow(){
  const fups=getFollowUps();
  let h = fups.length
    ? `<div class="card">`+fups.map(u=>{ const od=u.f.due&&u.f.due<todayStr();
        const pill=u.f.due?`<span class="badge ${od?'pill-over':'pill-ok'}">${od?'逾期 ':''}${esc(u.f.due)}</span>`:'';
        return itemRow({ name:u.f.text, sub:`${u.name}・${u.sub}`, pill,
          onclick: u.kind==='cust'?`viewCustomer('${u.id}')`:`viewProspect('${u.id}')` }); }).join('')+`</div>`
    : `<div class="card empty"><div class="big">✅</div>沒有待辦的跟進事項。<br>拜訪後在客戶頁記下「後續跟進」就會出現在這裡。</div>`;
  openModal('待辦戰術跟進', h);
}
function openHomeCounty(){
  const cov=computeCoverage();
  const regs=Object.entries(cov.region).filter(([,v])=>v.total>0).sort((a,b)=>(b[1].total-b[1].dev)-(a[1].total-a[1].dev));
  let h=`<div class="tagline" style="margin:0 2px 8px">未攻佔多者在前。點一下看地圖。</div><div class="card">`;
  h+=regs.slice(0,16).map(([name,v])=>covBarRow(name,v.total,v.dev,()=>`closeModal();gotoMapCounty('${esc(name)}')`)).join('');
  h+=`</div>`;
  openModal('各縣市戰況', h);
}
function openHomeTown(){
  if(!window.TW_MAP){ openModal('優先攻佔鄉鎮','<div class="card empty"><div class="big">🗺️</div>地圖資料尚未載入。</div>'); return; }
  const weak=weakestTowns(computeTownStats(),12);
  let h=`<div class="tagline" style="margin:0 2px 8px">名單多但還沒開發的，優先攻。點一下看地圖。</div><div class="card">`;
  h+=weak.map(w=>mapBarRow(`${w.c} ${w.t}`,w.lead,w.cust,()=>`closeModal();gotoMapTown(${w.i})`)).join('');
  h+=`</div>`;
  openModal('優先攻佔鄉鎮', h);
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
let mapState = {town:-1};   // town: 選取鄉鎮 index（負責銷售區域改存 soldier.region，可跨頁連動並持久化）
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
  const lead={}, cust={}, dist={}, distNames={};
  SEED.forEach(p=>{ const core=countyCore(p.region)||countyCore(p.address); const tn=matchTown(p.address,core)||matchTown(p.region,core); if(core&&tn){ const k=core+'|'+tn; lead[k]=(lead[k]||0)+1; } });
  customers.forEach(c=>{ const core=countyCore(c.address); const tn=matchTown(c.address,core); if(core&&tn){ const k=core+'|'+tn; cust[k]=(cust[k]||0)+1; } });
  // 經銷商「經銷區域」覆蓋：縣市層級＝整個縣市所有鄉鎮；有鄉鎮＝該鄉鎮
  customers.forEach(c=>{
    if(c.inactive || c.type!=='經銷商') return;
    (c.salesRegions||[]).forEach(r=>{
      if(!r || r==='線上通路') return;
      const core=countyCore(r); if(!core) return;
      const tn=matchTown(r,core);
      const keys = tn ? [core+'|'+tn] : (townsByCore()[core]||[]).map(t=>core+'|'+t.raw);
      keys.forEach(k=>{ dist[k]=(dist[k]||0)+1; (distNames[k]=distNames[k]||new Set()).add(c.name); });
    });
  });
  return {lead,cust,dist,distNames};
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
  if(!window.TW_MAP){ viewHTML('<div class="card empty"><div class="big">🗺️</div>地圖資料載入失敗。</div>'); return; }
  const M=window.TW_MAP, st=computeTownStats();
  const sel=getRegions().filter(n=>M.counties[n]);
  // viewBox：全島或縮放到所選負責區域（聯集）
  let vb=M.viewBox;
  if(sel.length){
    let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
    sel.forEach(n=>{ const b=M.counties[n]; minX=Math.min(minX,b[0]); minY=Math.min(minY,b[1]); maxX=Math.max(maxX,b[0]+b[2]); maxY=Math.max(maxY,b[1]+b[3]); });
    const w=maxX-minX, hh=maxY-minY, pad=Math.max(w,hh)*0.08;
    vb=`${minX-pad} ${minY-pad} ${w+pad*2} ${hh+pad*2}`;
  }
  // 縣市清單（由北到南）
  const cNames=Object.keys(M.counties).sort((a,b)=>REGION_ORDER.findIndex(x=>normR(a).includes(x))-REGION_ORDER.findIndex(x=>normR(b).includes(x)));
  // 戰情公仔（負責區域由公仔設定，地圖直接套用，不再重複選擇）
  let h=soldierCardHTML();
  // 選取鄉鎮資訊卡
  if(mapState.town>=0 && M.towns[mapState.town]){
    const t=M.towns[mapState.town], k=townKey(t), lead=st.lead[k]||0, cu=st.cust[k]||0;
    const rate=lead?Math.round(Math.min(1,cu/lead)*100):(cu?100:0);
    const dn = st.distNames[k] ? [...st.distNames[k]] : [];
    h+=`<div class="minfo"><div class="mt">${esc(t.c)} ${esc(t.t)}</div>
      <div class="mstat"><div>名單<br><b>${lead}</b></div><div>我的客戶<br><b style="color:var(--green)">${cu}</b></div><div>滲透率<br><b>${rate}%</b></div></div>`+
      (dn.length?`<div style="margin-top:9px;padding-top:9px;border-top:1px solid var(--line);font-size:13px">🛡️ 已有經銷商經營：<b>${dn.map(esc).join('、')}</b></div>`:'')+`</div>`;
  }
  // SVG 地圖
  let paths='';
  M.towns.forEach((t,i)=>{
    const k=townKey(t);
    const col=penColor(st.lead[k]||0,st.cust[k]||0);
    const covered=(st.dist[k]||0)>0;
    paths+=`<path class="tw-town${i===mapState.town?' sel':''}${covered?' tw-dist':''}" d="${t.d}" fill="${col}" onclick="mapTapTown(${i})"></path>`;
  });
  h+=`<div class="mapwrap"><svg viewBox="${vb}" preserveAspectRatio="xMidYMid meet">${paths}</svg></div>`;
  // 圖例
  h+=`<div class="maplegend">
    <span><i style="background:#ffd9a8"></i>有名單未開發</span>
    <span><i style="background:#a5d6a7"></i>滲透 ~33%</span>
    <span><i style="background:#52b265"></i>~66%</span>
    <span><i style="background:#2e7d32"></i>67%以上</span>
    <span><i style="background:#eceff1"></i>無名單</span>
    <span><i style="background:#fff;border:2px solid #d4a017"></i>🛡️ 已有經銷商經營</span></div>`;
  // 明細表：未選→各縣市滾算；已選→所選縣市各鄉鎮（聯集）
  if(!sel.length){
    const roll={};
    M.towns.forEach(t=>{ const k=townKey(t); const r=roll[t.c]=roll[t.c]||{lead:0,cust:0,dist:0}; r.lead+=st.lead[k]||0; r.cust+=st.cust[k]||0; if(st.dist[k])r.dist++; });
    const rows=cNames.map(n=>({name:n,...roll[n]})).filter(r=>r.lead||r.cust||r.dist);
    h+=`<div class="sec-title"><span class="bar"></span>各縣市滲透概況<span style="font-weight:400;font-size:11.5px;color:var(--muted)">（點縣市加入負責區）</span></div><div class="card">`+
      rows.sort((a,b)=>(b.lead-b.cust)-(a.lead-a.cust)).map(r=>mapBarRow(r.name,r.lead,r.cust,()=>`mapToggleCounty('${esc(r.name)}')`,r.dist>0)).join('')+`</div>`;
  } else {
    const towns=M.towns.map((t,i)=>({i,t})).filter(o=>sel.includes(o.t.c));
    const rows=towns.map(o=>{ const k=townKey(o.t); return {i:o.i,name:`${o.t.c} ${o.t.t}`,lead:st.lead[k]||0,cust:st.cust[k]||0,dist:st.dist[k]||0}; }).filter(r=>r.lead||r.cust||r.dist);
    h+=`<div class="sec-title"><span class="bar"></span>負責區域 各鄉鎮（依未開發排序）</div><div class="card">`+
      (rows.length?rows.sort((a,b)=>(b.lead-b.cust)-(a.lead-a.cust)).map(r=>mapBarRow(r.name,r.lead,r.cust,()=>`mapTapTown(${r.i})`,r.dist>0)).join(''):`<div class="tagline">此區尚無名單資料。</div>`)+`</div>`;
  }
  viewHTML(h);
}
function mapBarRow(name,lead,cust,onclickFn,covered){
  const rate=lead?Math.min(1,cust/lead):(cust?1:0);
  const col=penColor(lead,cust);
  return `<div class="mrow" onclick="${onclickFn()}">
    <div class="mname">${esc(name)}${covered?' <span title="已有經銷商經營">🛡️</span>':''}</div>
    <div class="mbar"><i style="width:${Math.round(rate*100)}%;background:${col}"></i></div>
    <div class="mnum">客${cust}/名單${lead}・${Math.round(rate*100)}%</div></div>`;
}
function mapToggleCounty(n){ toggleRegion(n); mapState.town=-1; renderMap(); window.scrollTo(0,0); }
function mapClearCounties(){ clearRegions(); mapState.town=-1; renderMap(); window.scrollTo(0,0); }
function mapTapTown(i){ mapState.town=i; renderMap(); window.scrollTo(0,0); }

// ---------- 戰情公仔（Q版戰鬥娃娃）----------
function starPath(cx,cy,r){ let p=''; for(let i=0;i<10;i++){ const a=Math.PI/5*i-Math.PI/2, rr=i%2?r*0.45:r; p+=(i?'L':'M')+(cx+rr*Math.cos(a)).toFixed(1)+' '+(cy+rr*Math.sin(a)).toFixed(1); } return p+'Z'; }
// 帽子（依軍種）
function dollHat(s){
  const b=BRANCHES[s.branch]||BRANCHES.army;
  if(s.branch==='navy') return `
    <path d="M58 50 Q100 30 142 50 L142 56 Q100 38 58 56 Z" fill="#fff"/>
    <ellipse cx="100" cy="46" rx="42" ry="15" fill="#fff"/>
    <rect x="60" y="49" width="80" height="9" rx="4" fill="#16294a"/>
    <circle cx="100" cy="46" r="5" fill="#c0392b"/>`;
  if(s.branch==='air') return `
    <path d="M58 56 Q58 28 100 28 Q142 28 142 56 Z" fill="#3a5773"/>
    <rect x="56" y="52" width="88" height="7" rx="3" fill="#24384a"/>
    <circle cx="84" cy="55" r="9" fill="#bfe6f2" stroke="#24384a" stroke-width="3"/>
    <circle cx="116" cy="55" r="9" fill="#bfe6f2" stroke="#24384a" stroke-width="3"/>
    <path d="${starPath(100,42,7)}" fill="#ffd84d"/>`;
  // army helmet
  return `
    <path d="M60 58 Q60 24 100 24 Q140 24 140 58 Z" fill="${b.uni2}"/>
    <rect x="56" y="56" width="88" height="9" rx="4" fill="#36421f"/>
    <path d="${starPath(100,42,8)}" fill="#ffd84d"/>`;
}
// 臉（照片或卡通臉）
function dollFace(s,id){
  if(s.photo) return `
    <clipPath id="fc${id}"><circle cx="100" cy="78" r="31"/></clipPath>
    <circle cx="100" cy="78" r="34" fill="#ffd9b0"/>
    <image href="${s.photo}" x="69" y="47" width="62" height="62" preserveAspectRatio="xMidYMid slice" clip-path="url(#fc${id})"/>
    <circle cx="100" cy="78" r="31" fill="none" stroke="rgba(0,0,0,.12)" stroke-width="2"/>`;
  return `
    <circle cx="100" cy="78" r="34" fill="#ffd9b0"/>
    <ellipse cx="89" cy="78" rx="4" ry="5" fill="#3a2a1a"/><ellipse cx="111" cy="78" rx="4" ry="5" fill="#3a2a1a"/>
    <circle cx="90.5" cy="76.5" r="1.3" fill="#fff"/><circle cx="112.5" cy="76.5" r="1.3" fill="#fff"/>
    <circle cx="82" cy="88" r="5" fill="#ff9a9a" opacity=".5"/><circle cx="118" cy="88" r="5" fill="#ff9a9a" opacity=".5"/>
    <path d="M91 90 Q100 98 109 90" stroke="#b5654a" stroke-width="3" fill="none" stroke-linecap="round"/>`;
}
// 身體 + 手臂（pose: 'hold' 持武器 / 'stand' 立正）
function dollBody(s,pose){
  const b=BRANCHES[s.branch]||BRANCHES.army;
  const arms = pose==='hold'
    ? `<path d="M70 124 Q62 146 84 153" stroke="${b.uni}" stroke-width="15" fill="none" stroke-linecap="round"/>
       <path d="M130 124 Q138 146 116 153" stroke="${b.uni}" stroke-width="15" fill="none" stroke-linecap="round"/>
       <circle cx="84" cy="153" r="8" fill="${b.skin}"/><circle cx="116" cy="153" r="8" fill="${b.skin}"/>`
    : `<path d="M70 124 Q58 152 70 176" stroke="${b.uni}" stroke-width="15" fill="none" stroke-linecap="round"/>
       <path d="M130 124 Q142 152 130 176" stroke="${b.uni}" stroke-width="15" fill="none" stroke-linecap="round"/>
       <circle cx="70" cy="176" r="8" fill="${b.skin}"/><circle cx="130" cy="176" r="8" fill="${b.skin}"/>`;
  return `
    <rect x="84" y="174" width="14" height="34" rx="6" fill="${b.uni2}"/>
    <rect x="102" y="174" width="14" height="34" rx="6" fill="${b.uni2}"/>
    <ellipse cx="89" cy="210" rx="13" ry="7" fill="#2a2a2a"/><ellipse cx="111" cy="210" rx="13" ry="7" fill="#2a2a2a"/>
    <rect x="64" y="108" width="72" height="76" rx="22" fill="${b.uni}"/>
    <path d="M86 108 Q100 122 114 108" stroke="${b.uni2}" stroke-width="4" fill="none"/>
    <rect x="96" y="112" width="8" height="58" rx="3" fill="${b.uni2}" opacity=".5"/>
    ${arms}`;
}
// 手持武器
function heldWeapon(w){
  if(w==='water') return `
    <rect x="78" y="145" width="54" height="14" rx="6" fill="#ff7a3c"/>
    <rect x="92" y="131" width="30" height="15" rx="6" fill="#36c5e0"/>
    <rect x="130" y="147" width="22" height="9" rx="3" fill="#36c5e0"/>
    <rect x="86" y="157" width="11" height="16" rx="3" fill="#e85d27"/>
    <circle cx="156" cy="151" r="3.5" fill="#9fe0f0"/><circle cx="163" cy="146" r="2.5" fill="#9fe0f0"/>`;
  if(w==='pistol') return `
    <rect x="94" y="146" width="36" height="12" rx="3" fill="#3b3b42"/>
    <rect x="96" y="156" width="13" height="17" rx="3" fill="#2a2a30"/>
    <rect x="128" y="148" width="8" height="6" rx="2" fill="#1e1e24"/>`;
  if(w==='mg') return `
    <rect x="56" y="146" width="98" height="11" rx="3" fill="#33332f"/>
    <rect x="150" y="148" width="26" height="6" rx="2" fill="#222"/>
    <rect x="96" y="157" width="12" height="16" rx="3" fill="#222"/>
    <rect x="70" y="157" width="22" height="15" rx="3" fill="#4a4a44"/>
    <path d="M150 156 l9 17 M160 156 l9 17" stroke="#222" stroke-width="3" stroke-linecap="round"/>
    <path d="M92 164 q9 5 14 -1" stroke="#caa64a" stroke-width="3" fill="none"/>`;
  // rifle (default)
  return `
    <rect x="62" y="147" width="86" height="9" rx="3" fill="#4a3a2a"/>
    <rect x="148" y="149" width="18" height="5" rx="2" fill="#2a2a2a"/>
    <rect x="54" y="144" width="14" height="15" rx="4" fill="#5a4632"/>
    <rect x="100" y="156" width="11" height="14" rx="3" fill="#3a2e22"/>
    <rect x="112" y="156" width="10" height="21" rx="3" fill="#2a2a2a"/>`;
}
// 載具（坦克／戰機／航母）+ 公仔擺放
const VEHICLES = {
  tank: { doll:'translate(45,46) scale(.55)', svg:`
    <rect x="22" y="204" width="156" height="24" rx="12" fill="#2f3a22"/>
    <circle cx="44" cy="216" r="8" fill="#16190f"/><circle cx="72" cy="216" r="8" fill="#16190f"/><circle cx="100" cy="216" r="8" fill="#16190f"/><circle cx="128" cy="216" r="8" fill="#16190f"/><circle cx="156" cy="216" r="8" fill="#16190f"/>
    <rect x="34" y="178" width="132" height="32" rx="10" fill="#4f6336"/>
    <rect x="76" y="158" width="56" height="26" rx="9" fill="#5b7040"/>
    <rect x="128" y="166" width="66" height="9" rx="4" fill="#3a4a2a"/>
    <rect x="190" y="164" width="6" height="13" rx="3" fill="#2f3a22"/>`},
  jet: { doll:'translate(50,30) scale(.5)', svg:`
    <path d="M16 196 Q70 178 160 184 L190 190 Q160 198 160 198 L70 210 Q30 206 16 196 Z" fill="#aebcc7"/>
    <path d="M70 192 L42 224 L104 202 Z" fill="#8497a6"/>
    <path d="M150 186 L170 160 L176 188 Z" fill="#8497a6"/>
    <ellipse cx="126" cy="186" rx="17" ry="9" fill="#bfe6f2" stroke="#5c6b76" stroke-width="2"/>
    <circle cx="22" cy="194" r="5" fill="#5c6b76"/>`},
  carrier: { doll:'translate(50,86) scale(.5)', svg:`
    <path d="M14 198 L186 198 L168 226 L32 226 Z" fill="#5a6470"/>
    <rect x="18" y="190" width="166" height="10" rx="2" fill="#3f4750"/>
    <rect x="40" y="193" width="22" height="3" fill="#d9c24a"/><rect x="78" y="193" width="22" height="3" fill="#d9c24a"/><rect x="116" y="193" width="22" height="3" fill="#d9c24a"/>
    <rect x="146" y="166" width="24" height="26" rx="3" fill="#6b7682"/>
    <rect x="156" y="150" width="4" height="18" fill="#6b7682"/>
    <path d="M6 226 Q26 220 46 226 T86 226 T126 226 T166 226 T206 226 L206 240 L6 240 Z" fill="#7fa8c4" opacity=".7"/>`}
};
function soldierSVG(s, id){
  const w=s.weapon||'rifle';
  const veh=VEHICLES[w];
  let inner;
  if(veh){
    inner = veh.svg + `<g transform="${veh.doll}">${dollBody(s,'stand')}${dollFace(s,id)}${dollHat(s)}</g>`;
  } else {
    inner = dollBody(s,'hold') + heldWeapon(w) + dollFace(s,id) + dollHat(s);
  }
  return `<svg viewBox="0 0 200 232" preserveAspectRatio="xMidYMid meet">${inner}</svg>`;
}
function soldierWrap(s,id){
  return `<div class="doll-wrap" id="dollWrap" onclick="petSoldier()" title="點我互動">
    <div class="doll-bubble" id="dollBubble"></div>
    <div class="doll-fx" id="dollFx"></div>
    ${soldierSVG(s,id)}
  </div>`;
}
function soldierCardHTML(){
  const s=soldier, b=BRANCHES[s.branch]||BRANCHES.army, w=WEAPONS[s.weapon]||WEAPONS.rifle;
  const nm=s.name?esc(s.name):'未命名戰士';
  const regTxt=getRegions().join('、');
  return `<div class="card soldier-card" style="padding:10px 13px 12px">
    ${soldierWrap(s,'m')}
    <div class="sol-name">${nm}</div>
    <div class="sol-tags">
      <span class="sol-badge" style="background:${b.uni}">${b.emoji} ${b.label}</span>
      <span class="sol-badge wpn">${w.emoji} ${w.label}</span>
      <span class="sol-badge reg">📍 ${regTxt?esc(regTxt):'全台灣'}</span>
    </div>
    <div class="sol-hint">點公仔互動 👆 ・ <span class="sol-link" onclick="event.stopPropagation();go('settings')">⚙️ 設定戰鬥人員</span></div>
  </div>`;
}
function petSoldier(){
  const d=document.getElementById('dollWrap'); if(!d) return;
  d.classList.remove('pet'); void d.offsetWidth; d.classList.add('pet');
  const bub=document.getElementById('dollBubble');
  if(bub){ bub.textContent=SOLDIER_LINES[Math.floor(Math.random()*SOLDIER_LINES.length)]; bub.classList.remove('show'); void bub.offsetWidth; bub.classList.add('show'); }
  const fx=document.getElementById('dollFx');
  if(fx){ const base=(soldier.weapon==='water')?['💦','💧','✨']:['❤️','⭐','✨','💥'];
    for(let i=0;i<4;i++){ const sp=document.createElement('span'); sp.className='fxp'; sp.textContent=base[Math.floor(Math.random()*base.length)];
      sp.style.left=(22+Math.random()*56)+'%'; sp.style.animationDelay=(i*70)+'ms'; fx.appendChild(sp); setTimeout(()=>sp.remove(),1200); } }
}
function setSoldierBranch(b){ soldier.branch=b; saveSoldier(); renderSettings(); }
function setSoldierWeapon(w){ soldier.weapon=w; saveSoldier(); renderSettings(); }
function setSoldierCounty(n){ toggleRegion(n); renderSettings(); }
function clearSoldierCounties(){ clearRegions(); renderSettings(); }
function saveSoldierSettings(){
  const nm=document.getElementById('sol-name'); if(nm) soldier.name=nm.value.trim();
  saveSoldier(); renderSettings(); toast('已儲存戰鬥人員設定 ✅');
}
function removeSoldierPhoto(){ soldier.photo=''; saveSoldier(); renderSettings(); }
function uploadSoldierPhoto(input){
  const f=input.files[0]; if(!f) return;
  const r=new FileReader();
  r.onload=()=>{ const img=new Image(); img.onload=()=>{
    const sz=240, cv=document.createElement('canvas'); cv.width=sz; cv.height=sz; const ctx=cv.getContext('2d');
    const scale=Math.max(sz/img.width, sz/img.height), dw=img.width*scale, dh=img.height*scale;
    ctx.drawImage(img,(sz-dw)/2,(sz-dh)/2,dw,dh);
    soldier.photo=cv.toDataURL('image/jpeg',0.85); saveSoldier(); toast('已更新戰鬥人員照片'); renderSettings();
  }; img.onerror=()=>alert('圖片讀取失敗'); img.src=r.result; };
  r.readAsDataURL(f); input.value='';
}

// ========== 名單 ==========
function renderProspects(){
  const exIds = existingProspectIds();
  const statusOf = p => exIds.has(p.id) ? 'existing' : 'cold';
  const nEx = SEED.reduce((a,p)=>a+(statusOf(p)==='existing'?1:0),0);
  const nVisited = SEED.reduce((a,p)=>a+(isContacted(p.id)?1:0),0);
  const inStatus = p => !pFilter.status || (pFilter.status==='visited' ? isContacted(p.id) : statusOf(p)===pFilter.status);
  // 有機屬性筆數（依目前狀態動態）
  const nOrg = SEED.reduce((a,p)=>a+(inStatus(p)&&p.category==='有機農戶'?1:0),0);
  const nNon = SEED.reduce((a,p)=>a+(inStatus(p)&&p.category!=='有機農戶'?1:0),0);
  // 通路筆數依目前「客戶狀態」動態計算（通路選項一律完整顯示，不受有機/非有機影響）
  const counts = {}; let total=0;
  SEED.forEach(p=>{ if(inStatus(p)){ counts[p.category]=(counts[p.category]||0)+1; total++; } });

  let h = `<div class="search"><input id="psearch" placeholder="🔍 搜尋名稱 / 地址 / 電話" value="${esc(pFilter.q)}" oninput="onPSearch(this.value)"></div>`;
  h += `<div class="btn-row" style="margin:2px 0 8px;gap:6px"><button class="btn btn-pri" onclick="addCustomProspect()">＋ 新增臨時目標客戶</button><button class="btn btn-ghost" onclick="smartProspectSearch()">🔎 智慧目標客戶搜尋</button></div>`;
  h += `<div class="rowsel"><span class="rowsel-l">狀態</span><select class="regsel" onchange="setPStatus(this.value)">
        <option value="" ${pFilter.status===''?'selected':''}>全部 ${SEED.length}</option>
        <option value="cold" ${pFilter.status==='cold'?'selected':''}>陌生目標客戶 ${SEED.length-nEx}</option>
        <option value="visited" ${pFilter.status==='visited'?'selected':''}>✅ 已拜訪目標客戶 ${nVisited}</option>
        <option value="existing" ${pFilter.status==='existing'?'selected':''}>既有客戶 ${nEx}</option></select></div>`;
  h += `<div class="rowsel"><span class="rowsel-l">屬性</span><select class="regsel" onchange="setPOrganic(this.value)">
        <option value="" ${pFilter.organic===''?'selected':''}>全部 ${SEED.length}</option>
        <option value="org" ${pFilter.organic==='org'?'selected':''}>🌱 有機農戶 ${nOrg}</option>
        <option value="non" ${pFilter.organic==='non'?'selected':''}>非有機 ${nNon}</option></select></div>`;
  h += `<div class="rowsel"><span class="rowsel-l">通路</span><select class="regsel" onchange="setPCat(this.value)">
        <option value="" ${pFilter.cat===''?'selected':''}>全部 ${total}</option>
        ${CATS.filter(c=>counts[c]).map(c=>`<option value="${esc(c)}" ${pFilter.cat===c?'selected':''}>${esc(c)} ${counts[c]}</option>`).join('')}</select></div>`;
  h += `<div class="rowsel"><span class="rowsel-l">區域</span><select class="regsel" onchange="setPRegion(this.value)">
        <option value="">全部區域</option>
        ${regionsSorted().map(r=>`<option value="${esc(r)}" ${pFilter.region===r?'selected':''}>${esc(r)}</option>`).join('')}
        </select></div>`;

  // 面積級距：依目前狀態／通路／區域動態計算筆數，只在有面積資料時顯示
  const areaPool = SEED.filter(p=> inStatus(p) && inOrganic(p,pFilter.organic) && (!pFilter.cat||p.category===pFilter.cat) && (!pFilter.region||p.region===pFilter.region));
  const areaCounts={}; let areaTot=0;
  areaPool.forEach(p=>{ const n=areaVal(p); if(n!=null){ areaTot++; const b=AREA_BANDS.find(x=>x.test(n)); if(b)areaCounts[b.k]=(areaCounts[b.k]||0)+1; } });
  const effArea = areaTot>0 ? pFilter.area : '';   // 此條件下沒有面積資料就不套用，避免清空結果
  if(areaTot>0){
    h += `<div class="rowsel"><span class="rowsel-l">面積</span><select class="regsel" onchange="setPArea(this.value)">
          <option value="" ${effArea===''?'selected':''}>全部 ${areaTot}</option>
          ${AREA_BANDS.filter(b=>areaCounts[b.k]).map(b=>`<option value="${b.k}" ${effArea===b.k?'selected':''}>${b.label} ${areaCounts[b.k]}</option>`).join('')}</select></div>`;
  }

  const q = pFilter.q.trim();
  const res = SEED.filter(p=>{
    if(!inStatus(p)) return false;
    if(!inOrganic(p,pFilter.organic)) return false;
    if(pFilter.cat && p.category!==pFilter.cat) return false;
    if(pFilter.region && p.region!==pFilter.region) return false;
    if(effArea && !inAreaBand(p,effArea)) return false;
    if(q){ const blob=(p.name+p.address+p.phone+p.contact+p.region); if(!blob.includes(q)) return false; }
    return true;
  });
  h += `<div class="count">符合 ${res.length} 筆${res.length>pLimit?`（顯示前 ${pLimit} 筆，可搜尋縮小範圍）`:''}</div>`;
  h += `<div class="card">`;
  if(!res.length){ h+=`<div class="empty"><div class="big">🔍</div>找不到符合的名單</div>`; }
  else {
    h += res.slice(0,pLimit).map(p=>{
      const o=overlay[p.id]; const di=dueInfo(o); const ex=statusOf(p)==='existing';
      const tag = ex?`<span class="badge b-農會">既有</span>`:(isContacted(p.id)?`<span class="badge b-合作社">✅已拜訪</span>`:'');
      const av=areaVal(p);
      const areaTag = av!=null?`<span class="badge b-有機農戶">${av.toFixed(1)}公頃</span>`:'';
      const pill = di?`<span class="badge ${di.cls}">${di.txt}</span>${areaTag}${tag}`:`<span class="badge b-${p.category}">${p.category}</span>${areaTag}${tag}`;
      return itemRow({name:p.name, sub:[p.region,p.address].filter(Boolean).join(' · '), pill, onclick:`viewProspect('${p.id}')`});
    }).join('');
  }
  h += `</div>`;
  if(res.length>pLimit) h+=`<div class="more" onclick="pLimit+=60;render()">顯示更多 ▼</div>`;
  viewHTML(h);
  const inp=$('#psearch'); if(inp&&pFilter._focus){ inp.focus(); inp.setSelectionRange(inp.value.length,inp.value.length); pFilter._focus=false; }
}
function onPSearch(v){ pFilter.q=v; pFilter._focus=true; pLimit=60; renderProspects(); }
function setPStatus(s){ pFilter.status=s; pFilter.cat=''; pLimit=60; renderProspects(); }
function setPCat(c){
  pFilter.cat=c;
  // 選的通路與有機/非有機衝突時，自動把屬性放寬，避免 0 筆
  if(c==='有機農戶' && pFilter.organic==='non') pFilter.organic='';
  else if(c && c!=='有機農戶' && pFilter.organic==='org') pFilter.organic='';
  pLimit=60; renderProspects();
}
function setPRegion(r){ pFilter.region=r; pLimit=60; renderProspects(); }
function setPArea(k){ pFilter.area=k; pLimit=60; renderProspects(); }
function setPOrganic(v){
  pFilter.organic=v;
  // 屬性與目前通路衝突時，放寬通路（保留通路篩選始終可用）
  if(v==='org' && pFilter.cat && pFilter.cat!=='有機農戶') pFilter.cat='';
  else if(v==='non' && pFilter.cat==='有機農戶') pFilter.cat='';
  pLimit=60; renderProspects();
}

function custByProspect(id){ return customers.find(c=>c.fromProspect===id); }
function viewProspect(id){
  const p=SEED.find(x=>x.id===id); if(!p) return;
  const o=overlay[id]||{}; const di=dueInfo(o);
  const exCust=custByProspect(id);
  let h='';
  h+=`<div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px">
      <span class="badge b-${p.category}">${p.category}</span>
      ${p.region?`<span class="badge b-其他">${esc(p.region)}</span>`:''}
      ${p.custom?`<span class="badge pill-due">📌 臨時新增</span>`:''}
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
  if(p.custom){ h+=`<div class="btn-row"><button class="btn btn-out" onclick="editCustomProspect('${id}')">✏️ 編輯臨時資料</button></div>`; }
  openModal(p.name, h);
}

// ---------- 臨時目標客戶（手動新增，本機儲存，併入 SEED 後各處自動納入） ----------
function addCustomProspect(){ openCustomProspectForm(null); }
function editCustomProspect(id){ const p=SEED.find(x=>x.id===id); if(p) openCustomProspectForm(p); }
function cpLocate(){ getGeo(coord=>{ const el=$('#cp-addr'); if(el) el.value=coord; toast('已帶入目前位置座標'); }); }
function openCustomProspectForm(p){
  const isEdit=!!p; p=p||{};
  const cats=['農會','合作社','肥料行','有機農戶','驗證機構','友善團體','其他'];
  const regs=regionsSorted();
  let h=`<div class="info">把你在網路或路上看到的潛在客戶臨時加進來，會一起出現在名單、戰情地圖與排路線中。資料只存在你的手機本機。</div>`;
  h+=`<div class="card">`;
  h+=`<div class="field"><label>名稱 *</label><input id="cp-name" value="${esc(p.name||'')}" placeholder="例如 ○○農產行 / ○○農場"></div>`;
  h+=`<div class="field-2">
      <div class="field"><label>通路 / 屬性</label><select id="cp-cat">${cats.map(c=>`<option ${(p.category||'肥料行')===c?'selected':''}>${c}</option>`).join('')}</select></div>
      <div class="field"><label>區域</label><select id="cp-region"><option value="">（未填）</option>${regs.map(r=>`<option ${p.region===r?'selected':''}>${esc(r)}</option>`).join('')}</select></div></div>`;
  h+=`<div class="field"><label>地址</label><div style="display:flex;gap:6px"><input id="cp-addr" style="flex:1;min-width:0" value="${esc(p.address||'')}" placeholder="地址或座標"><button type="button" class="btn btn-out" style="white-space:nowrap;padding:0 12px" onclick="cpLocate()">📍 定位</button></div></div>`;
  h+=`<div class="field-2">
      <div class="field"><label>電話</label><input id="cp-phone" value="${esc(p.phone||'')}" placeholder="可空"></div>
      <div class="field"><label>聯絡人</label><input id="cp-contact" value="${esc(p.contact||'')}" placeholder="可空"></div></div>`;
  h+=`<div class="field-2">
      <div class="field"><label>面積(公頃)</label><input id="cp-area" type="number" inputmode="decimal" value="${esc(p.area||'')}" placeholder="可空"></div>
      <div class="field"><label>作物 / 種類</label><input id="cp-crop" value="${esc(p.crop||'')}" placeholder="可空"></div></div>`;
  h+=`<div class="field"><label>備註（來源、觀察）</label><input id="cp-notes" value="${esc(p.notes||'')}" placeholder="例如 FB 看到 / 路過 ○○路口"></div>`;
  h+=`</div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" onclick="saveCustomProspect('${isEdit?p.id:''}')">💾 儲存</button>${isEdit?`<button class="btn btn-gray" onclick="delCustomProspect('${p.id}')">🗑️ 刪除</button>`:''}</div>`;
  openModal(isEdit?'編輯臨時目標客戶':'新增臨時目標客戶', h);
}
function saveCustomProspect(id){
  const g=i=>{const el=$('#'+i);return el?el.value.trim():'';};
  const name=g('cp-name'); if(!name){ toast('請填名稱'); return; }
  const data={ category:($('#cp-cat')&&$('#cp-cat').value)||'肥料行', region:($('#cp-region')&&$('#cp-region').value)||'', name, address:g('cp-addr'), phone:g('cp-phone'), contact:g('cp-contact'), area:g('cp-area'), crop:g('cp-crop'), notes:g('cp-notes'), custom:true };
  if(id){ const cp=customProspects.find(x=>x.id===id); if(cp)Object.assign(cp,data); const s=SEED.find(x=>x.id===id); if(s)Object.assign(s,data); toast('已更新'); }
  else { id='CP'+Date.now(); const obj=Object.assign({id},data); customProspects.push(obj); SEED.push(obj); toast('已新增臨時目標客戶'); }
  saveProspects(); closeModal(); render(); viewProspect(id);
}
function delCustomProspect(id){
  if(!confirm('確定刪除這筆臨時目標客戶？此動作無法復原。')) return;
  customProspects=customProspects.filter(x=>x.id!==id);
  const i=SEED.findIndex(x=>x.id===id); if(i>=0) SEED.splice(i,1);
  if(overlay[id]){ delete overlay[id]; saveOverlay(); }
  saveProspects(); closeModal(); toast('已刪除'); render();
}

// ---------- 🔎 智慧目標客戶搜尋（找有聲量的種植農民 → 解析欄位 → 一鍵加入臨時目標客戶） ----------
// 注意：本機 App 無法自行爬網，這裡幫忙產生精準搜尋連結；找到人後把文字貼回來，前端自動解析欄位（不連網、不上傳）。
const SS_CROP_GROUPS={
  '果樹類':['芒果','鳳梨','香蕉','火龍果','芭樂','葡萄','柑橘','柳丁','茂谷柑','荔枝','龍眼','百香果','酪梨','木瓜','蓮霧','紅棗','草莓','棗子','文旦柚','椪柑','水蜜桃','梨','柿子','李子','哈密瓜','洋香瓜'],
  '雜糧':['水稻','稻米','玉米','大豆','花生','紅豆','黑豆','小麥','高粱','薏仁','地瓜','馬鈴薯','蕎麥','芝麻'],
  '蔬菜':['高麗菜','大白菜','青江菜','番茄','苦瓜','絲瓜','南瓜','茭白筍','洋蔥','大蒜','薑','蘿蔔','萵苣','菠菜','空心菜','茄子','甜椒','四季豆','金針','菇類','韭菜','芹菜','有機蔬菜'],
  '特作 / 飲料作物':['茶葉','烏龍茶','紅茶','咖啡','可可','蜂蜜']
};
const SS_CROPS=Object.values(SS_CROP_GROUPS).reduce((a,b)=>a.concat(b),[]);
function smartProspectSearch(){
  const regs=regionsSorted();
  let h=`<div class="info">找出「有話題聲量」的種植農民，加進你的臨時目標客戶。<b>App 不會自動爬網</b>（免費離線版做不到），但會幫你產生精準搜尋連結；找到人後把那段文字貼回來，前端自動幫你抓出欄位、一鍵新增。全程不上傳、只存本機。</div>`;
  h+=`<div class="sec-title"><span class="bar"></span>① 產生「聲量」搜尋連結</div><div class="card">`;
  h+=`<div class="field"><label>作物 / 農產品</label><select id="ss-crop-sel" onchange="if(this.value){document.querySelector('#ss-crop').value=this.value;}"><option value="">▼ 從清單挑選（或下方自行輸入）</option>${Object.keys(SS_CROP_GROUPS).map(g=>`<optgroup label="${g}">${SS_CROP_GROUPS[g].map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}</optgroup>`).join('')}</select><input id="ss-crop" placeholder="可自行輸入，例如 愛文芒果、有機蔬菜" style="margin-top:6px"></div>`;
  h+=`<div class="field"><label>區域（縣市，可空）</label><select id="ss-region"><option value="">全台</option>${regs.map(r=>`<option>${esc(r)}</option>`).join('')}</select></div>`;
  h+=`<div class="field"><label>聲量關鍵字（可複選）</label><div id="ss-kw" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px">${['爆紅','網紅','直播','得獎','有機','青農','產銷履歷','友善耕作','故事'].map(k=>`<label style="display:inline-flex;align-items:center;gap:5px;white-space:nowrap;flex:0 0 auto;background:var(--card2,#f1efe6);border:1px solid var(--line);border-radius:16px;padding:6px 13px;font-size:14px;line-height:1"><input type="checkbox" value="${k}" style="margin:0;width:16px;height:16px;flex:0 0 auto">${k}</label>`).join('')}</div></div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" onclick="ssBuildLinks()">🔎 產生搜尋連結</button></div>`;
  h+=`<div id="ss-links"></div>`;
  h+=`</div>`;
  h+=`<div class="sec-title"><span class="bar"></span>② 貼上資訊，自動抓欄位</div><div class="card">`;
  h+=`<div class="field"><label>把找到的農民資訊貼上來（FB 貼文／新聞／名片／Google 地圖資訊都行）</label><textarea id="ss-paste" rows="5" placeholder="貼上含 名稱 / 電話 / 地址 / 作物 的文字…"></textarea></div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" onclick="ssParse()">🪄 解析欄位</button></div>`;
  h+=`<div id="ss-parsed"></div>`;
  h+=`</div>`;
  openModal('🔎 智慧目標客戶搜尋', h);
}
function ssBuildLinks(){
  const crop=($('#ss-crop')&&$('#ss-crop').value.trim())||'';
  const region=($('#ss-region')&&$('#ss-region').value)||'';
  const kws=[...document.querySelectorAll('#ss-kw input:checked')].map(c=>c.value);
  if(!crop && !region && !kws.length){ toast('至少填作物或選關鍵字'); return; }
  const news=encodeURIComponent([crop,region,...kws,'農民'].filter(Boolean).join(' '));
  const gen=encodeURIComponent([crop,region,...kws,'農場'].filter(Boolean).join(' '));
  const fb=encodeURIComponent([crop,region,'農場'].filter(Boolean).join(' '));
  const yt=encodeURIComponent([crop,region,'農民'].filter(Boolean).join(' '));
  const map=encodeURIComponent([crop,region,'農場 果園'].filter(Boolean).join(' '));
  const links=[
    ['📰 Google 新聞（找報導 / 爆紅）',`https://www.google.com/search?tbm=nws&q=${news}`],
    ['🔍 Google 一般搜尋',`https://www.google.com/search?q=${gen}`],
    ['📘 Facebook 貼文 / 粉專',`https://www.facebook.com/search/top?q=${fb}`],
    ['▶️ YouTube（直播 / 介紹）',`https://www.youtube.com/results?search_query=${yt}`],
    ['🗺️ Google 地圖（農場 / 果園）',`https://www.google.com/maps/search/${map}`],
    ['📗 上下游新聞市集',`https://www.newsmarket.com.tw/?s=${encodeURIComponent([crop,kws[0]].filter(Boolean).join(' '))}`],
    ['🌾 農傳媒 AgriHarvest',`https://www.agriharvest.tw/?s=${encodeURIComponent([crop,kws[0]].filter(Boolean).join(' '))}`]
  ];
  let html=`<div class="tagline" style="margin:8px 0 4px">點開連結瀏覽，找到有聲量的農民後，複製那段文字貼到下方解析。</div>`;
  html+=links.map(([t,u])=>`<a class="btn btn-out" style="display:block;text-align:left;text-decoration:none;margin:4px 0" href="${u}" target="_blank" rel="noopener">${t}</a>`).join('');
  $('#ss-links').innerHTML=html;
}
function parseLead(text){
  const t=String(text||'');
  const mobile=(t.match(/09\d{2}[-\s]?\d{3}[-\s]?\d{3}/)||[])[0]||'';
  const tel=(t.match(/0\d{1,2}[-\s)]?\s?\d{3,4}[-\s]?\d{4}/)||[])[0]||'';
  const phone=(mobile||tel||'').replace(/[\s)]/g,'');
  const url=(t.match(/https?:\/\/[^\s)）」』]+/)||[])[0]||'';
  // 地址：抓「○○縣/市 ○○鄉/鎮/市/區 …」整段
  let address='';
  const cm=t.match(/((?:台|臺)?[一-龥]{1,3}[縣市][一-龥]{1,4}[區鄉鎮市][^\n，,。、；;]{0,22})/);
  if(cm){ address=cm[1].trim(); }
  else { const core=countyCore(t); if(core){ const tn=matchTown(t,core); address=core+(/[縣市]$/.test(core)?'':( /市/.test(core)?'市':'縣'))+(tn||''); } }
  const core2=countyCore(address||t);
  const am=t.match(/(\d+(?:\.\d+)?)\s*(公頃|甲|分地|分)/);
  const area=am?am[1]:'';
  const cropInput=($('#ss-crop')&&$('#ss-crop').value.trim())||'';
  const crop=cropInput||SS_CROPS.find(c=>t.includes(c))||'';
  let name=(t.match(/[一-龥]{2,10}(?:生態農場|有機農場|休閒農場|觀光果園|農場|果園|農園|農莊|果園|莊園|茶園|蜂場)/)||[])[0]||'';
  if(!name){
    const lines=t.split(/\n/).map(s=>s.trim()).filter(Boolean);
    const nm=lines.find(l=>l.length>=2&&l.length<=14&&/[一-龥]/.test(l)&&!/https?:|\d{6,}|電話|地址/.test(l));
    name=nm||(crop?crop+'農友':'');
  }
  return {name, phone, address, region:core2, area, crop, source:url};
}
function ssParse(){
  const txt=($('#ss-paste')&&$('#ss-paste').value)||'';
  if(!txt.trim()){ toast('請先貼上文字'); return; }
  const d=parseLead(txt);
  const regs=regionsSorted();
  const cats=['農會','合作社','肥料行','有機農戶','驗證機構','友善團體','其他'];
  const rcore=normR(d.region||'').replace(/[縣市]$/,'');
  let h=`<div class="tagline" style="margin:8px 0">自動抓到以下欄位，確認 / 修改後按新增（抓不到的請手動補）：</div>`;
  h+=`<div class="field"><label>名稱 *</label><input id="ssp-name" value="${esc(d.name)}"></div>`;
  h+=`<div class="field-2"><div class="field"><label>通路 / 屬性</label><select id="ssp-cat">${cats.map(c=>`<option ${c==='有機農戶'?'selected':''}>${c}</option>`).join('')}</select></div>
      <div class="field"><label>區域</label><select id="ssp-region"><option value="">（未填）</option>${regs.map(r=>`<option ${rcore&&normR(r).includes(rcore)?'selected':''}>${esc(r)}</option>`).join('')}</select></div></div>`;
  h+=`<div class="field"><label>地址</label><input id="ssp-addr" value="${esc(d.address)}"></div>`;
  h+=`<div class="field-2"><div class="field"><label>電話</label><input id="ssp-phone" value="${esc(d.phone)}"></div>
      <div class="field"><label>作物 / 種類</label><input id="ssp-crop" value="${esc(d.crop)}"></div></div>`;
  h+=`<div class="field-2"><div class="field"><label>面積(公頃)</label><input id="ssp-area" type="number" inputmode="decimal" value="${esc(d.area)}"></div>
      <div class="field"><label>聯絡人</label><input id="ssp-contact" value=""></div></div>`;
  h+=`<div class="field"><label>備註 / 聲量來源</label><input id="ssp-notes" value="${esc(d.source?('來源:'+d.source):'')}"></div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" onclick="ssAdd()">➕ 新增為臨時目標客戶</button></div>`;
  $('#ss-parsed').innerHTML=h;
}
function ssAdd(){
  const g=i=>{const e=$('#'+i);return e?e.value.trim():'';};
  const name=g('ssp-name'); if(!name){ toast('請填名稱'); return; }
  const id='CP'+Date.now();
  const obj={ id, category:($('#ssp-cat')&&$('#ssp-cat').value)||'有機農戶', region:($('#ssp-region')&&$('#ssp-region').value)||'',
    name, address:g('ssp-addr'), phone:g('ssp-phone'), contact:g('ssp-contact'),
    area:g('ssp-area'), crop:g('ssp-crop'), notes:g('ssp-notes'), custom:true };
  customProspects.push(obj); SEED.push(obj); saveProspects();
  toast('已新增臨時目標客戶：'+name);
  $('#ss-parsed').innerHTML=`<div class="info">✅ 已加入「${esc(name)}」到臨時目標客戶。可繼續貼下一位，或關閉視窗到「目標客戶」查看。</div>`;
  const pa=$('#ss-paste'); if(pa)pa.value='';
  render();
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
function reopenDetail(kind,id){ kind==='cust'?custGroup(id,'mgmt'):viewProspect(id); }
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
// 由地址取「縣市」（去掉郵遞區號後，取開頭 縣/市）
function cityOf(addr){
  if(!addr) return '';
  let s=String(addr).replace(/^[0-9０-９]+\s*/,'').trim();
  const m=s.match(/^[一-龥]{1,2}[縣市]/);
  return m?normR(m[0]):'';
}
function cityCmp(a,b){
  const ia=REGION_ORDER.findIndex(x=>normR(a).includes(x));
  const ib=REGION_ORDER.findIndex(x=>normR(b).includes(x));
  return (ia<0?99:ia)-(ib<0?99:ib)||a.localeCompare(b);
}
// 客戶分區用縣市：經銷商以「經銷區域」、直接農民以「使用肥料區域」第一筆判讀；未填則退回基本資料地址
function custCity(c){
  const regs = c.type==='經銷商' ? c.salesRegions : c.type==='直接農民' ? c.fertRegions : null;
  if(Array.isArray(regs)){ for(const r of regs){ const ci=cityOf(r); if(ci) return ci; } }
  return cityOf(c.address);
}
// 地區（縣市＋鄉鎮市區，例：台南市佳里區）；顯示用「台」
function regionFull(addr){
  const c=cityOf(addr), d=district(addr);
  if(!c&&!d) return '未填地區';
  return ((c||'')+(d||'')).replace(/臺/g,'台');
}
// 取一筆電話，以手機（09開頭）優先
function pickPhone(p){
  if(!p) return '';
  const parts=String(p).split(/[\/、,，;；\s]+/).map(x=>x.trim()).filter(Boolean);
  const mob=parts.find(x=>/^09\d{8}$/.test(x.replace(/[^\d]/g,'')));
  return mob||parts[0]||'';
}
let cFilter={q:'', grade:'', type:'', city:'', org:'', status:'active'};
// 依狀態取基底名單：使用中（隱藏停用）或 停用客戶
function custStatusBase(){ return cFilter.status==='inactive' ? customers.filter(c=>c.inactive) : customers.filter(c=>!c.inactive); }
function renderCustomers(){
  let h=`<div class="info">🔒 這一頁的資料（含身分證、統編、出生年月日）只儲存在你這台裝置的瀏覽器，不會上傳。請定期到「設定」備份。</div>`;
  // 搜尋框：只更新結果區、不重建輸入框，並避開中文（注音）組字中觸發搜尋
  h+=`<div class="search"><input id="cust-q" placeholder="🔍 搜尋我的客戶" value="${esc(cFilter.q)}" oninput="onCustSearchInput(this)" oncompositionstart="cFilter._composing=true" oncompositionend="cFilter._composing=false;onCustSearchInput(this)"></div>`;
  const base=custStatusBase();
  const activeN=customers.filter(c=>!c.inactive).length, inactiveN=customers.filter(c=>c.inactive).length;
  // 篩選下拉（改用下拉式選單，畫面不擁擠）
  const gc={}; base.forEach(c=>{ gc[c.grade||'']=(gc[c.grade||'']||0)+1; });
  const tcnt={}; base.forEach(c=>{ const t=c.type||'其他'; tcnt[t]=(tcnt[t]||0)+1; });
  const types=CUST_TYPES.filter(t=>tcnt[t]);
  const cities=[...new Set(base.map(c=>custCity(c)).filter(Boolean))].sort(cityCmp);
  const orgs=[...new Set(base.map(c=>c.org).filter(Boolean))].sort();
  h+=`<div class="field-2">
      <div class="field"><label>分級</label><select onchange="cFilter.grade=this.value;renderCustomers()">
        <option value="">全部分級（${base.length}）</option>
        ${GRADES.map(g=>`<option value="${g}" ${cFilter.grade===g?'selected':''}>${g}・${GRADE_LABEL[g]}（${gc[g]||0}）</option>`).join('')}
        <option value="none" ${cFilter.grade==='none'?'selected':''}>未分級（${gc['']||0}）</option></select></div>
      <div class="field"><label>通路</label><select onchange="cFilter.type=this.value;renderCustomers()">
        <option value="">全部通路</option>
        ${types.map(t=>`<option value="${esc(t)}" ${cFilter.type===t?'selected':''}>${esc(t)}（${tcnt[t]}）</option>`).join('')}</select></div></div>`;
  h+=`<div class="field-2">
      <div class="field"><label>地區</label><select onchange="cFilter.city=this.value;renderCustResults()">
        <option value="">全部地區</option>${cities.map(ci=>`<option value="${esc(ci)}" ${cFilter.city===ci?'selected':''}>${esc(ci)}</option>`).join('')}</select></div>
      <div class="field"><label>組織</label><select onchange="cFilter.org=this.value;renderCustResults()">
        <option value="">全部組織</option>${orgs.map(o=>`<option value="${esc(o)}" ${cFilter.org===o?'selected':''}>${esc(o)}</option>`).join('')}
        <option value="__none" ${cFilter.org==='__none'?'selected':''}>（未分組）</option></select></div></div>`;
  h+=`<div class="field"><label>狀態</label><select onchange="cFilter.status=this.value;renderCustomers()">
        <option value="active" ${cFilter.status!=='inactive'?'selected':''}>✅ 使用中（${activeN}）</option>
        <option value="inactive" ${cFilter.status==='inactive'?'selected':''}>⏸️ 停用客戶（${inactiveN}）</option></select></div>`;
  h+=`<div class="btn-row" style="margin-top:2px"><button class="btn btn-out" onclick="orgManager()">🏷️ 整理組織（批次歸戶）</button></div>`;
  h+=`<div id="cust-results"></div>`;
  viewHTML(h);
  renderCustResults();
}
function onCustSearchInput(el){ cFilter.q=el.value; if(cFilter._composing) return; renderCustResults(); }
function renderCustResults(){
  const box=document.getElementById('cust-results'); if(!box) return;
  const q=cFilter.q.trim();
  const base=custStatusBase();
  const res=base.filter(c=>{
    if(cFilter.grade==='none'){ if(c.grade) return false; }
    else if(cFilter.grade){ if(c.grade!==cFilter.grade) return false; }
    if(cFilter.type && (c.type||'其他')!==cFilter.type) return false;
    if(cFilter.city && custCity(c)!==cFilter.city) return false;
    if(cFilter.org==='__none'){ if(c.org) return false; }
    else if(cFilter.org){ if((c.org||'')!==cFilter.org) return false; }
    return !q||(c.name+c.phone+c.address+(c.contact||'')+(c.org||'')).includes(q);
  });
  const active = cFilter.grade||cFilter.type||cFilter.city||cFilter.org||q;
  let h=`<div class="count">${cFilter.status==='inactive'?`⏸️ 停用客戶 ${base.length} 位`:`共 ${base.length} 位客戶`}${active?`，符合 ${res.length} 位`:''}</div>`;
  if(!res.length){
    h+=`<div class="card"><div class="empty"><div class="big">${cFilter.status==='inactive'?'⏸️':'👤'}</div>${cFilter.status==='inactive'?'目前沒有停用的客戶。':(customers.length?'找不到符合的客戶':'還沒有客戶。<br>點右下角 ＋ 新增，或到名單「轉為我的客戶」。')}</div></div>`;
  } else {
    // 依地區分組（縣市層級），每個縣市獨立一塊
    const cityKey=c=>{ const ci=custCity(c); return ci?ci.replace(/臺/g,'台'):'未填地區'; };
    const groups={};
    res.forEach(c=>{ const d=cityKey(c); (groups[d]=groups[d]||[]).push(c); });
    const dists=Object.keys(groups).sort((a,b)=>{ if(a==='未填地區')return 1; if(b==='未填地區')return -1; return cityCmp(a,b)||a.localeCompare(b); });
    dists.forEach(d=>{
      const list=groups[d];
      h+=`<div class="sec-title"><span class="bar"></span>${esc(d)} <span style="color:var(--muted);font-weight:400;font-size:12px">${list.length} 位</span></div>`;
      // 地區內再依通路分類
      const byType={};
      list.forEach(c=>{ const t=c.type||'其他'; (byType[t]=byType[t]||[]).push(c); });
      const typeOrder=CUST_TYPES.filter(t=>byType[t]).concat(Object.keys(byType).filter(t=>!CUST_TYPES.includes(t)));
      h+=`<div class="card">`;
      typeOrder.forEach(t=>{
        h+=`<div style="display:flex;align-items:center;gap:7px;padding:7px 4px 4px;font-size:12px;color:var(--muted)"><span class="badge b-${t}">${esc(t)}</span><span>${byType[t].length} 位</span></div>`;
        byType[t].slice().sort((a,b)=>a.name.localeCompare(b.name)).forEach(c=>{
          const di=dueInfo(c);
          const gtag=c.grade?`<span class="badge grade-${c.grade}">${c.grade}</span>`:'';
          const otag=c.org?`<span class="badge" style="background:#5d6651;color:#fff">${esc(c.org)}</span>`:'';
          const itag=c.inactive?`<span class="badge" style="background:#9a9a8a;color:#fff">⏸️ 停用</span>`:'';
          const pill=(c.inactive?'':(di?`<span class="badge ${di.cls}">${di.txt}</span>`:''))+gtag+otag+itag;
          h+=itemRow({name:c.name,sub:pickPhone(c.phone)||'—',pill,onclick:`viewCustomer('${c.id}')`});
        });
      });
      h+=`</div>`;
    });
  }
  box.innerHTML=h;
}
function setCGrade(g){ cFilter.grade=g; renderCustomers(); }
function setCType(t){ cFilter.type=t; renderCustomers(); }

// ---------- 組織（批次歸戶）----------
function orgManager(){
  const orgs=[...new Set(customers.map(c=>c.org).filter(Boolean))].sort();
  const pre=(cFilter.org && cFilter.org!=='__none')?cFilter.org:'';
  let h=`<div class="field"><label>組織名稱</label><input id="org-name" list="org-dl" placeholder="例如 打貓合作社" value="${esc(pre)}"><datalist id="org-dl">${orgs.map(o=>`<option value="${esc(o)}">`).join('')}</datalist></div>`;
  h+=`<div class="search" style="margin-top:4px"><input id="org-q" placeholder="🔍 篩選客戶名稱" oninput="orgFilterList(this.value)"></div>`;
  h+=`<div class="hint" style="margin:6px 0;color:var(--muted);font-size:11.5px;line-height:1.6">勾選要歸入此組織的客戶，按下方「指派」。可重複操作，把不同客戶加進同一個組織。</div>`;
  h+=`<div id="org-list" style="max-height:46vh;overflow:auto;border:1px solid var(--line);border-radius:10px">`;
  customers.slice().sort((a,b)=>cityCmp(cityOf(a.address),cityOf(b.address))||a.name.localeCompare(b.name)).forEach(c=>{
    h+=`<label class="org-pick" data-name="${esc(c.name)}" style="display:flex;align-items:center;gap:9px;padding:9px 11px;border-bottom:1px solid var(--line)">
      <input type="checkbox" value="${c.id}" style="width:18px;height:18px;flex:none">
      <span style="flex:1;min-width:0"><b>${esc(c.name)}</b> <span style="color:var(--muted);font-size:12px">${esc(cityOf(c.address)||'')}</span>${c.org?` <span class="badge" style="background:#5d6651;color:#fff">${esc(c.org)}</span>`:''}</span></label>`;
  });
  h+=`</div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" onclick="assignOrg()">指派到組織</button></div>`;
  openModal('整理組織', h);
}
function orgFilterList(q){ q=(q||'').trim(); document.querySelectorAll('#org-list .org-pick').forEach(el=>{ el.style.display=(!q||el.dataset.name.includes(q))?'flex':'none'; }); }
function assignOrg(){
  const name=$('#org-name').value.trim(); if(!name){ toast('請輸入組織名稱'); return; }
  const ids=[...document.querySelectorAll('#org-list input:checked')].map(i=>i.value);
  if(!ids.length){ toast('請至少勾選一位客戶'); return; }
  const set=new Set(ids); let n=0;
  customers.forEach(c=>{ if(set.has(c.id)){ c.org=name; n++; } });
  saveCust(); closeModal(); toast(`已將 ${n} 位歸入「${name}」`); renderCustomers();
}

// ===== 客戶詳情：卡片選單（一張卡片 → 一頁內容）=====
const CUST_SECTIONS = [
  {key:'basic',    icon:'📋', title:'基本資料'},
  {key:'products', icon:'💰', title:'產品報價'},
  {key:'rivals',   icon:'⚔️', title:'競品肥料'},
  {key:'deal',     icon:'🚚', title:'交易 / 配送'},
  {key:'farm',     icon:'🌱', title:'種植 / 用肥'},
  {key:'visit',    icon:'📅', title:'拜訪管理'},
  {key:'follow',   icon:'🔔', title:'後續跟進'},
  {key:'inter',    icon:'💬', title:'互動紀錄'},
  {key:'notes',    icon:'📝', title:'備註'},
];
// 三大群組（卡片）：基本資料(含交易配送/種植用肥/備註)、產品相關價格(報價/競品)、拜訪管理(分級/跟進/互動)
const CUST_GROUPS = [
  {key:'profile', icon:'📋', title:'基本資料'},
  {key:'pricing', icon:'💰', title:'產品相關價格'},
  {key:'mgmt',    icon:'📅', title:'拜訪管理'},
];
function groupSummary(c,key){
  if(key==='profile'){ const parts=[regionFull(c.address)].filter(x=>x&&x!=='未填地區'); const ph=pickPhone(c.phone); if(ph)parts.push(ph); if(c.checkPeriod)parts.push('票期 '+c.checkPeriod); const rg=c.type==='經銷商'?(c.salesRegions||[]):c.type==='直接農民'?(c.fertRegions||[]):[]; if(rg.length)parts.push((c.type==='經銷商'?'經銷區 ':'肥料區 ')+rg.length); return parts.length?parts.join('・'):'點此填寫'; }
  if(key==='pricing'){ const a=[]; const np=(c.products||[]).length, nr=(c.rivals||[]).length; if(np)a.push(np+' 報價'); if(nr)a.push(nr+' 競品'); return a.length?a.join('・'):'尚未填寫'; }
  if(key==='mgmt'){ const di=dueInfo(c); const open=(c.follow||[]).filter(f=>!f.done).length; const a=[c.grade?gradeText(c.grade):'未分級']; if(di)a.push('下次 '+di.txt); if(open)a.push(open+' 待辦'); return a.join('・'); }
  return '';
}
function custSectionSummary(c,key){
  switch(key){
    case 'basic':    return [pickPhone(c.phone),regionFull(c.address)].filter(x=>x&&x!=='未填地區').join('・')||'點此填寫';
    case 'products': return (c.products&&c.products.length)?`${c.products.length} 筆報價`:'尚未填寫';
    case 'rivals':   return (c.rivals&&c.rivals.length)?`${c.rivals.length} 筆競品`:'尚未填寫';
    case 'deal':     { const parts=[]; if(c.checkPeriod)parts.push('票期：'+c.checkPeriod); if(c.creditLimit)parts.push('額度 '+c.creditLimit+' 萬'); const rg=c.type==='經銷商'?(c.salesRegions||[]):c.type==='直接農民'?(c.fertRegions||[]):[]; if(rg.length)parts.push((c.type==='經銷商'?'經銷區':'肥料區')+' '+rg.length); if(Array.isArray(c.mapLocations)&&c.mapLocations.length)parts.push('📍'+c.mapLocations.length); return parts.length?parts.join('・'):'尚未設定'; }
    case 'farm':     { const a=[]; if(c.plantArea)a.push(c.plantArea+(c.plantAreaUnit||'公頃')); if(Array.isArray(c.crops)&&c.crops.length)a.push(c.crops.slice(0,2).join('、')+(c.crops.length>2?'…':'')); if(c.fertTons)a.push(c.fertTons+'噸/年'); return a.length?a.join('・'):'尚未填寫'; }
    case 'visit':    { const di=dueInfo(c); return (c.grade?gradeText(c.grade):'未分級')+(di?`・下次 ${di.txt}`:''); }
    case 'follow':   { const n=(c.follow||[]).filter(f=>!f.done).length; return n?`${n} 項待辦`:'無待辦'; }
    case 'inter':    return (c.inter&&c.inter.length)?`${c.inter.length} 筆紀錄`:'尚無紀錄';
    case 'notes':    return c.notes?String(c.notes).slice(0,16)+(c.notes.length>16?'…':''):'無';
  }
  return '';
}
function custTile(id,key,icon,title,sum,onclick){
  return `<div class="item" onclick="${onclick}">
    <div class="avatar" style="background:#5d6651;font-size:19px">${icon}</div>
    <div class="body"><div class="nm">${esc(title)}</div><div class="sub">${esc(sum||'')}</div></div>
    <div class="meta" style="color:var(--muted);font-size:20px">›</div></div>`;
}
function viewCustomer(id){
  const c=customers.find(x=>x.id===id); if(!c) return;
  const di=dueInfo(c);
  let h=`<div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px">
      <span class="badge b-${c.type}">${c.type}</span>
      ${c.inactive?`<span class="badge" style="background:#9a9a8a;color:#fff">⏸️ 已停用</span>`:''}
      ${c.org?`<span class="badge" style="background:#5d6651;color:#fff">🏷️ ${esc(c.org)}</span>`:''}
      ${c.grade?`<span class="badge grade-${c.grade}">${esc(gradeText(c.grade))}</span>`:''}
      ${(!c.inactive&&di)?`<span class="badge ${di.cls}">下次：${di.txt}</span>`:''}</div>`;
  // 經銷 / 使用肥料區域（唯讀總覽，設定後可直接看到）
  const _rg = c.type==='經銷商'?(c.salesRegions||[]):c.type==='直接農民'?(c.fertRegions||[]):[];
  if(_rg.length){
    const _lbl = c.type==='經銷商'?'經銷區域':'使用肥料區域';
    h+=`<div class="card" style="padding:12px 14px"><div class="grp-sub" style="margin-bottom:8px;padding-bottom:6px">📍 ${_lbl}（${_rg.length}）</div>`+
       `<div style="display:flex;flex-wrap:wrap;gap:6px">`+_rg.map(r=>`<span class="reg-chip" style="cursor:default">${r==='線上通路'?'🌐':'📍'} ${esc(r)}</span>`).join('')+`</div>`+
       (c.type==='經銷商'?`<div class="hint" style="color:var(--muted);font-size:11.5px;margin-top:8px">這些區域已在「戰情地圖」標示為有經銷商經營。</div>`:'')+`</div>`;
  }
  h+=`<div class="card">`;
  CUST_GROUPS.forEach(g=>{ h+=custTile(id,g.key,g.icon,g.title,groupSummary(c,g.key),`custGroup('${id}','${g.key}')`); });
  (c.cards||[]).forEach(cd=>{ h+=custTile(id,'cd'+cd.id,'🗂️',cd.title,cd.body?String(cd.body).slice(0,16)+(cd.body.length>16?'…':''):'點此填寫',`custCustomCard('${id}','${cd.id}')`); });
  h+=`</div>`;
  h+=`<div class="btn-row" style="margin-top:2px"><button class="btn btn-pri" onclick="custFullView('${id}')">📋 客戶資料全貌（可複製）</button></div>`;
  h+=`<div class="btn-row"><button class="btn btn-out" onclick="addCustCard('${id}')">⚙️ 新增卡片</button>
      <button class="btn btn-gray" onclick="toggleInactive('${id}')">${c.inactive?'▶️ 啟用客戶':'⏸️ 停用客戶'}</button></div>`;
  h+=`<div class="btn-row"><button class="btn btn-red" onclick="delCustomer('${id}')">刪除</button></div>`;
  openModal(c.name, h);
}
function sectionTitleOf(key){ const s=CUST_SECTIONS.find(x=>x.key===key); return s?s.title:key; }
function custBackBar(id){ return `<div class="btn-row" style="margin-top:0;margin-bottom:12px"><button class="btn btn-gray" onclick="viewCustomer('${id}')">← 返回</button></div>`; }
function custSection(id,key){
  const c=findCust(id); if(!c) return;
  let h=custBackBar(id);
  if(key==='basic'){
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
    h+=`</div><div class="btn-row"><button class="btn btn-pri" onclick="editCustomer(findCust('${id}'))">✏️ 編輯基本資料</button></div>`;
  } else if(key==='products'){
    h+=`<div class="card"><div id="prod-rows">${(c.products&&c.products.length?c.products:[]).map(p=>productRowHTML(p)).join('')}</div>`;
    h+=`<button type="button" class="btn btn-out" style="margin-top:8px" onclick="addProductRow()">＋ 新增產品報價</button>`;
    h+=`<div class="btn-row" style="margin-top:8px"><button class="btn btn-pri" onclick="saveCustProducts('${id}')">💾 儲存產品報價</button></div></div>`;
  } else if(key==='rivals'){
    h+=`<div class="card"><div class="hint" style="color:var(--muted);font-size:12px;margin-bottom:8px">目前使用（銷售）的競品肥料，掌握對手價格與條件。</div>`;
    h+=`<div id="rival-rows">${(c.rivals&&c.rivals.length?c.rivals:[]).map(r=>rivalRowHTML(r)).join('')}</div>`;
    h+=`<button type="button" class="btn btn-out" style="margin-top:8px" onclick="addRivalRow()">＋ 新增競品肥料</button>`;
    h+=`<div class="btn-row" style="margin-top:8px"><button class="btn btn-pri" onclick="saveCustRivals('${id}')">💾 儲存競品肥料</button></div></div>`;
  } else if(key==='deal'){
    h+=`<div class="card">`+checkPeriodHTML(c.checkPeriod||'');
    h+=`<div class="field"><label>額度（萬元）</label><input id="c-credit" type="number" inputmode="decimal" value="${esc(c.creditLimit||'')}" placeholder="例如 50"></div>`;
    if(c.type==='經銷商') h+=regionEditorHTML('經銷區域', getSalesRegions(c), '經銷商實際銷售涵蓋的縣市／鄉鎮');
    else if(c.type==='直接農民') h+=regionEditorHTML('使用肥料區域', getFertRegions(c), '實際施肥的縣市／鄉鎮（與居住地可能不同，影響業績判讀）');
    h+=locEditorHTML(getMapLocs(c));
    if(c.terms)h+=drow('交易條件',esc(c.terms));
    if(c.price)h+=drow('價格',esc(c.price));
    if(c.conditions)h+=drow('其他條件',esc(c.conditions));
    if(c.currentFert)h+=drow('目前用肥',esc(c.currentFert));
    if(c.truck)h+=drow('運送車輛',esc(c.truck));
    if(c.deliveryTime)h+=drow('送貨時間',esc(c.deliveryTime));
    h+=`<div class="btn-row" style="margin-top:8px"><button class="btn btn-pri" onclick="saveCustDeal('${id}')">💾 儲存交易資料</button></div></div>`;
  } else if(key==='farm'){
    const crops=Array.isArray(c.crops)?c.crops:[];
    const months=Array.isArray(c.fertMonths)?c.fertMonths:[];
    const customCrops=crops.filter(x=>!COMMON_CROPS.includes(x));
    h+=`<div class="card">`;
    h+=`<div class="field-2"><div class="field"><label>種植面積</label><input id="c-area" type="number" inputmode="decimal" value="${esc(c.plantArea||'')}" placeholder="例如 2.5"></div>
        <div class="field"><label>單位</label><select id="c-areaunit">${AREA_UNITS.map(u=>`<option ${(c.plantAreaUnit||'公頃')===u?'selected':''}>${u}</option>`).join('')}</select></div></div>`;
    h+=`<div class="field"><label>每年使用肥料噸數（噸）</label><input id="c-ferttons" type="number" inputmode="decimal" value="${esc(c.fertTons||'')}" placeholder="例如 12"></div>`;
    h+=`<div class="field"><label>作物類別（可複選）</label><div class="chips chips-wrap" id="c-crops">`+
       COMMON_CROPS.map(cr=>`<button type="button" class="chip ${crops.includes(cr)?'on':''}" data-c="${esc(cr)}" onclick="this.classList.toggle('on')">${esc(cr)}</button>`).join('')+`</div>`;
    h+=`<input id="c-cropother" placeholder="其他作物（多項用、分隔）" value="${esc(customCrops.join('、'))}" style="margin-top:7px;width:100%;border:1px solid var(--line);border-radius:9px;padding:9px 10px;font-size:14px;font-family:inherit"></div>`;
    h+=`<div class="field"><label>使用肥料時機（月份・可複選）</label><div class="chips chips-wrap" id="c-months">`+
       Array.from({length:12},(_,i)=>i+1).map(m=>`<button type="button" class="chip ${months.includes(m)?'on':''}" data-m="${m}" onclick="this.classList.toggle('on')">${m}月</button>`).join('')+`</div></div>`;
    h+=`<div class="btn-row" style="margin-top:8px"><button class="btn btn-pri" onclick="saveCustFarm('${id}')">💾 儲存種植資料</button></div></div>`;
  } else if(key==='visit'){
    h+=`<div class="card"><div class="field"><label>客戶分級（決定拜訪頻率）</label><select id="c-grade" onchange="if(this.value)document.getElementById('c-freq').value={A:7,B:30,C:90,D:365}[this.value]">
        <option value="" ${!c.grade?'selected':''}>未分級</option>
        ${GRADES.map(g=>`<option value="${g}" ${c.grade===g?'selected':''}>${g} 級・${GRADE_LABEL[g]}拜訪</option>`).join('')}
        </select></div>`;
    h+=`<div class="field-2"><div class="field"><label>拜訪頻率(天)</label><input type="number" id="c-freq" value="${c.freq||''}" min="1"></div>
        <div class="field"><label>下次拜訪日</label><input type="date" id="c-next" value="${c.next||''}"></div></div>`;
    h+=`<div class="btn-row"><button class="btn btn-out" onclick="visitForm('cust','${id}')">📍 記錄拜訪</button>
        <button class="btn btn-pri" onclick="saveCustSchedule('${id}')">儲存排程</button></div></div>`;
  } else if(key==='follow'){
    h+=followBlock('cust', id, c.follow);
  } else if(key==='inter'){
    h+=interactionBlock(c.inter, `addCustInter('${id}')`);
  } else if(key==='notes'){
    h+=`<div class="card"><div class="field"><label>備註</label><textarea id="c-notes" placeholder="輸入備註…">${esc(c.notes||'')}</textarea></div>
        <div class="btn-row"><button class="btn btn-pri" onclick="saveCustNotes('${id}')">💾 儲存備註</button></div></div>`;
  }
  openModal(`${c.name}・${sectionTitleOf(key)}`, h);
}
function findCust(id){ return customers.find(x=>x.id===id); }

// ===== 三大群組編輯頁 =====
function farmFieldsHTML(c){
  const crops=Array.isArray(c.crops)?c.crops:[];
  const months=Array.isArray(c.fertMonths)?c.fertMonths:[];
  const customCrops=crops.filter(x=>!COMMON_CROPS.includes(x));
  let h=`<div class="field-2"><div class="field"><label>種植面積</label><input id="c-area" type="number" inputmode="decimal" value="${esc(c.plantArea||'')}" placeholder="例如 2.5"></div>
      <div class="field"><label>單位</label><select id="c-areaunit">${AREA_UNITS.map(u=>`<option ${(c.plantAreaUnit||'公頃')===u?'selected':''}>${u}</option>`).join('')}</select></div></div>`;
  h+=`<div class="field"><label>每年使用肥料噸數（噸）</label><input id="c-ferttons" type="number" inputmode="decimal" value="${esc(c.fertTons||'')}" placeholder="例如 12"></div>`;
  h+=`<div class="field"><label>作物類別（可複選）</label><div class="chips chips-wrap" id="c-crops">`+
     COMMON_CROPS.map(cr=>`<button type="button" class="chip ${crops.includes(cr)?'on':''}" data-c="${esc(cr)}" onclick="this.classList.toggle('on')">${esc(cr)}</button>`).join('')+`</div>`;
  h+=`<input id="c-cropother" placeholder="其他作物（多項用、分隔）" value="${esc(customCrops.join('、'))}" style="margin-top:7px;width:100%;border:1px solid var(--line);border-radius:9px;padding:9px 10px;font-size:14px;font-family:inherit"></div>`;
  h+=`<div class="field"><label>使用肥料時機（月份・可複選）</label><div class="chips chips-wrap" id="c-months">`+
     Array.from({length:12},(_,i)=>i+1).map(m=>`<button type="button" class="chip ${months.includes(m)?'on':''}" data-m="${m}" onclick="this.classList.toggle('on')">${m}月</button>`).join('')+`</div></div>`;
  return h;
}
function profileRegionBlock(c){
  if(c.type==='經銷商') return regionEditorHTML('經銷區域', getSalesRegions(c), '經銷商實際銷售涵蓋的縣市／鄉鎮');
  if(c.type==='直接農民') return regionEditorHTML('使用肥料區域', getFertRegions(c), '實際施肥的縣市／鄉鎮（與居住地可能不同，影響業績判讀）');
  return '';
}
function onProfileTypeChange(){
  const t=$('#f-type').value; const c=findCust(window._curCustId); if(!c) return;
  const rw=document.getElementById('reg-wrap');
  if(rw) rw.innerHTML = t==='經銷商'?regionEditorHTML('經銷區域',getSalesRegions(c),'經銷商實際銷售涵蓋的縣市／鄉鎮'):t==='直接農民'?regionEditorHTML('使用肥料區域',getFertRegions(c),'實際施肥的縣市／鄉鎮（與居住地可能不同，影響業績判讀）'):'';
  const fw=document.getElementById('farm-wrap'); if(fw) fw.style.display=(t==='經銷商')?'none':'';
}
function custGroup(id,key){
  const c=findCust(id); if(!c) return;
  window._curCustId=id;
  let h=custBackBar(id);
  if(key==='profile'){
    const _orgs=[...new Set(customers.map(x=>x.org).filter(Boolean))].sort();
    h+=`<div class="card"><div class="grp-sub">📋 基本資料</div>`;
    h+=field('名稱','f-name',c.name,'text',true,'客戶名稱');
    h+=`<div class="field"><label>客戶類型</label><select id="f-type" onchange="onProfileTypeChange()">${CUST_TYPES.map(t=>`<option ${c.type===t?'selected':''}>${t}</option>`).join('')}</select></div>`;
    h+=`<div class="field"><label>所屬組織</label><input id="f-org" list="f-org-dl" value="${esc(c.org||'')}" placeholder="例如 打貓合作社"><datalist id="f-org-dl">${_orgs.map(o=>`<option value="${esc(o)}">`).join('')}</datalist></div>`;
    h+=field('系統編號','f-sysno',c.sysno);
    h+=field('電話','f-phone',c.phone,'tel');
    h+=field('聯絡人','f-contact',c.contact);
    h+=field('通訊地址','f-address',c.address);
    h+=field('建檔日期','f-filedDate',c.filedDate,'date');
    h+=`</div>`;
    h+=`<div class="card sens-card"><div class="grp-sub">🔒 稅務 / 法務（敏感，僅存本機）</div>`;
    h+=field('統一編號','f-taxid',c.taxid);
    h+=field('身分證字號','f-idno',c.idno);
    h+=field('出生年月日','f-birth',c.birth,'date');
    h+=field('戶籍地址','f-regAddress',c.regAddress);
    h+=`</div>`;
    h+=`<div class="card"><div class="grp-sub">🚚 交易 / 配送</div>`;
    h+=checkPeriodHTML(c.checkPeriod||'');
    h+=field('額度（萬元）','f-creditLimit',c.creditLimit,'number',false,'例如 50');
    h+=mortgageEditorHTML(c);
    h+=`<div id="reg-wrap">`+profileRegionBlock(c)+`</div>`;
    h+=locEditorHTML(getMapLocs(c));
    h+=field('其他條件','f-conditions',c.conditions);
    h+=field('運送車輛大小','f-truck',c.truck,'text',false,'例如 3.5噸 / 小貨車');
    h+=field('送貨時間','f-deliveryTime',c.deliveryTime,'text',false,'例如 週二上午');
    h+=`</div>`;
    h+=`<div class="card" id="farm-wrap" style="${c.type==='經銷商'?'display:none':''}"><div class="grp-sub">🌱 種植 / 用肥</div>`+farmFieldsHTML(c)+`</div>`;
    h+=`<div class="card"><div class="grp-sub">📝 備註</div><div class="field"><textarea id="f-notes" placeholder="輸入備註…">${esc(c.notes||'')}</textarea></div></div>`;
    h+=`<div class="btn-row"><button class="btn btn-pri" onclick="saveCustProfile('${id}')">💾 儲存基本資料</button></div>`;
    openModal(`${c.name}・基本資料`, h);
  } else if(key==='pricing'){
    h+=`<div class="card"><div class="grp-sub">💰 產品報價</div><div id="prod-rows">${(c.products||[]).map(productRowHTML).join('')}</div>`;
    h+=`<button type="button" class="btn btn-out" style="margin-top:8px" onclick="addProductRow()">＋ 新增產品報價</button></div>`;
    h+=`<div class="card"><div class="grp-sub">⚔️ 競品肥料</div><div class="hint" style="color:var(--muted);font-size:12px;margin-bottom:8px">目前使用（銷售）的競品肥料，掌握對手價格與條件。</div><div id="rival-rows">${(c.rivals||[]).map(rivalRowHTML).join('')}</div>`;
    h+=`<button type="button" class="btn btn-out" style="margin-top:8px" onclick="addRivalRow()">＋ 新增競品肥料</button></div>`;
    h+=`<div class="btn-row"><button class="btn btn-pri" onclick="saveCustPricing('${id}')">💾 儲存產品 / 競品</button></div>`;
    openModal(`${c.name}・產品相關價格`, h);
  } else if(key==='mgmt'){
    h+=`<div class="card"><div class="grp-sub">📅 拜訪分級</div>`;
    h+=`<div class="field"><label>客戶分級（決定拜訪頻率）</label><select id="c-grade" onchange="if(this.value)document.getElementById('c-freq').value={A:7,B:30,C:90,D:365}[this.value]">
        <option value="" ${!c.grade?'selected':''}>未分級</option>
        ${GRADES.map(g=>`<option value="${g}" ${c.grade===g?'selected':''}>${g} 級・${GRADE_LABEL[g]}拜訪</option>`).join('')}
        </select></div>`;
    h+=`<div class="field-2"><div class="field"><label>拜訪頻率(天)</label><input type="number" id="c-freq" value="${c.freq||''}" min="1"></div>
        <div class="field"><label>下次拜訪日</label><input type="date" id="c-next" value="${c.next||''}"></div></div>`;
    h+=`<div class="btn-row"><button class="btn btn-out" onclick="visitForm('cust','${id}')">📍 記錄拜訪</button>
        <button class="btn btn-pri" onclick="saveCustSchedule('${id}')">儲存排程</button></div></div>`;
    h+=followBlock('cust', id, c.follow);
    h+=interactionBlock(c.inter, `addCustInter('${id}')`);
    openModal(`${c.name}・拜訪管理`, h);
  }
}
function saveCustProfile(id){
  const c=findCust(id); const g=i=>{const e=$('#'+i); return e?e.value.trim():'';};
  const name=g('f-name'); if(!name){ toast('請填寫名稱'); return; }
  const type=$('#f-type').value;
  Object.assign(c,{ name, type, org:g('f-org'), sysno:g('f-sysno'), phone:g('f-phone'), contact:g('f-contact'),
    address:g('f-address'), filedDate:g('f-filedDate'), taxid:g('f-taxid'), idno:g('f-idno'), birth:g('f-birth'), regAddress:g('f-regAddress'),
    checkPeriod:readCheckPeriod(), creditLimit:g('f-creditLimit'), conditions:g('f-conditions'),
    mortgageSet:($('#f-mortset')?$('#f-mortset').value:''), mortgageType:($('#f-morttype')?$('#f-morttype').value:''), mortgageAmount:g('f-mortamt'),
    truck:g('f-truck'), deliveryTime:g('f-deliveryTime'), notes:g('f-notes') });
  const regs=readRegionChips(); if(type==='經銷商') c.salesRegions=regs; else if(type==='直接農民') c.fertRegions=regs;
  c.mapLocations=readMapLocs();
  if(type!=='經銷商'){
    c.plantArea=g('c-area'); c.plantAreaUnit=$('#c-areaunit')?$('#c-areaunit').value:'公頃'; c.fertTons=g('c-ferttons');
    const sel=[...document.querySelectorAll('#c-crops .chip.on')].map(b=>b.dataset.c);
    const other=(g('c-cropother')||'').split(/[、,，\s]+/).map(s=>s.trim()).filter(Boolean);
    c.crops=[...new Set([...sel,...other])];
    c.fertMonths=[...document.querySelectorAll('#c-months .chip.on')].map(b=>+b.dataset.m).sort((a,b)=>a-b);
  }
  saveCust(); toast('已儲存基本資料'); render(); custGroup(id,'profile');
}
function saveCustPricing(id){ const c=findCust(id); c.products=readProducts(); c.rivals=readRivals(); saveCust(); toast('已儲存產品 / 競品'); render(); custGroup(id,'pricing'); }

// ===== 客戶資料全貌（一頁式・可複製）=====
function buildFullProfile(c){
  const secs=[];
  const b=[]; const add=(k,v)=>{ if(v!==''&&v!=null) b.push([k,v]); };
  add('名稱',c.name); add('類型',c.type); add('所屬組織',c.org); add('系統編號',c.sysno);
  add('電話',c.phone); add('聯絡人',c.contact); add('通訊地址',c.address); add('建檔日期',c.filedDate);
  add('統一編號',c.taxid); add('身分證字號',c.idno); add('出生年月日',c.birth); add('戶籍地址',c.regAddress);
  if(c.notes) b.push(['備註',c.notes]);
  secs.push({title:'基本資料', rows:b});
  const d=[]; const addd=(k,v)=>{ if(v!==''&&v!=null) d.push([k,v]); };
  addd('票期',c.checkPeriod); addd('額度（萬元）',c.creditLimit);
  const regs = c.type==='經銷商'?(c.salesRegions||[]):c.type==='直接農民'?(c.fertRegions||[]):[];
  if(regs.length) addd(c.type==='經銷商'?'經銷區域':'使用肥料區域', regs.join('、'));
  (c.mapLocations||[]).forEach((l,i)=> d.push([`位置${i+1}（${l.type}）`, l.url]));
  addd('抵押設定',mortgageSummary(c)); addd('其他條件',c.conditions);
  addd('運送車輛',c.truck); addd('送貨時間',c.deliveryTime);
  secs.push({title:'交易 / 配送', rows:d});
  if(c.type!=='經銷商'){
    const f=[];
    if(c.plantArea) f.push(['種植面積', c.plantArea+(c.plantAreaUnit||'公頃')]);
    if(Array.isArray(c.crops)&&c.crops.length) f.push(['作物類別', c.crops.join('、')]);
    if(c.fertTons) f.push(['每年用肥噸數', c.fertTons+' 噸']);
    if(Array.isArray(c.fertMonths)&&c.fertMonths.length) f.push(['使用肥料時機', c.fertMonths.map(m=>m+'月').join('、')]);
    if(f.length) secs.push({title:'種植 / 用肥', rows:f});
  }
  secs.push({title:'產品報價', rows:(c.products||[]).map((p,i)=>[`產品${i+1}`, `${p.name||''} ${prodText(p)}`.trim()])});
  secs.push({title:'競品肥料', rows:(c.rivals||[]).map((r,i)=>[`競品${i+1}`, `${r.name||''} ${rivalText(r)}${r.note?'（'+r.note+'）':''}`.trim()])});
  const m=[]; m.push(['分級', c.grade?gradeText(c.grade):'未分級']);
  if(c.freq) m.push(['拜訪頻率', c.freq+' 天']);
  if(c.next) m.push(['下次拜訪', c.next]); if(c.last) m.push(['最近拜訪', c.last]);
  (c.follow||[]).filter(f=>!f.done).forEach((f,i)=> m.push([`待辦${i+1}`, f.text+(f.due?'（'+f.due+'）':'')]));
  secs.push({title:'拜訪管理', rows:m});
  const inter=(c.inter||[]).slice(-5).reverse().map(it=>[it.date||'', `${it.type||''} ${it.content||''}`.trim()]);
  if(inter.length) secs.push({title:'互動紀錄（近5筆）', rows:inter});
  return secs;
}
function custFullText(c){
  let out=`【${c.name}】${c.type||''}${c.inactive?'（已停用）':''}\n`;
  buildFullProfile(c).forEach(s=>{ if(!s.rows.length) return; out+=`\n■ ${s.title}\n`; s.rows.forEach(([k,v])=>{ out+=(k?`${k}：`:'')+v+'\n'; }); });
  return out.trim();
}
function custFullView(id){
  const c=findCust(id); if(!c) return;
  let h=custBackBar(id);
  h+=`<div class="btn-row" style="margin-top:0;margin-bottom:6px"><button class="btn btn-pri" onclick="copyCustFull('${id}')">📋 複製全部文字</button>
      <button class="btn btn-out" onclick="exportCustPDF('${id}')">🖨️ 輸出 PDF</button></div>`;
  h+=`<div class="hint" style="color:var(--muted);font-size:11.5px;margin:0 2px 10px">「輸出 PDF」會開啟列印預覽，iPhone 可選「儲存到檔案」存成 PDF，再用 LINE/Email 傳出。</div>`;
  buildFullProfile(c).forEach(s=>{ if(!s.rows.length) return; h+=`<div class="grp-sub" style="margin:8px 0 6px 2px">${esc(s.title)}</div><div class="card">`; s.rows.forEach(([k,v])=>{ h+=drow(k||'·', esc(String(v))); }); h+=`</div>`; });
  openModal(`${c.name}・資料全貌`, h);
}
function buildCustPrintHTML(c){
  const secs=buildFullProfile(c);
  let body=`<h1>${esc(c.name)}</h1><div class="sub">${esc(c.type||'')}${c.inactive?'（已停用）':''} ｜ 碩成肥料 ｜ 列印日期 ${esc(todayStr())}</div>`;
  secs.forEach(s=>{ if(!s.rows.length) return; body+=`<h2>${esc(s.title)}</h2><table>`; s.rows.forEach(([k,v])=>{ body+=`<tr><th>${esc(k||'·')}</th><td>${esc(String(v))}</td></tr>`; }); body+=`</table>`; });
  return `<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(c.name)}_客戶資料</title>
<style>*{box-sizing:border-box}body{font-family:-apple-system,"PingFang TC","Microsoft JhengHei",system-ui,sans-serif;color:#23271c;margin:18px;font-size:13px;line-height:1.55}
h1{font-size:20px;margin:0 0 4px}.sub{color:#666;font-size:12px;margin-bottom:16px;border-bottom:2px solid #556b2f;padding-bottom:9px}
h2{font-size:14px;color:#3c4d20;margin:15px 0 6px;border-left:4px solid #556b2f;padding-left:8px}
table{width:100%;border-collapse:collapse;margin-bottom:8px}
th,td{border:1px solid #d8d8c8;padding:6px 8px;text-align:left;vertical-align:top;word-break:break-word}
th{width:32%;background:#f2f2e6;font-weight:700;color:#3c4d20;white-space:nowrap}
@page{margin:12mm}@media print{body{margin:0}}</style></head>
<body>${body}<scr`+`ipt>window.onload=function(){setTimeout(function(){try{window.focus();window.print();}catch(e){}},350);};</scr`+`ipt></body></html>`;
}
function exportCustPDF(id){
  const c=findCust(id); if(!c){ return; }
  const html=buildCustPrintHTML(c);
  const w=window.open('','_blank');
  if(w&&w.document){ w.document.open(); w.document.write(html); w.document.close(); return; }
  // 後備：用隱藏 iframe 列印（彈窗被擋時）
  let ifr=document.getElementById('pdf-frame'); if(ifr) ifr.remove();
  ifr=document.createElement('iframe'); ifr.id='pdf-frame';
  ifr.style.cssText='position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden';
  document.body.appendChild(ifr);
  const doc=ifr.contentWindow.document; doc.open(); doc.write(html); doc.close();
  setTimeout(()=>{ try{ ifr.contentWindow.focus(); ifr.contentWindow.print(); }catch(e){ toast('此瀏覽器不支援列印，請改用「複製全部文字」'); } }, 500);
}
function copyCustFull(id){ const c=findCust(id); if(!c) return; const txt=custFullText(c);
  if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(txt).then(()=>toast('已複製全部資料'),()=>fallbackCopy(txt)); } else fallbackCopy(txt); }
function fallbackCopy(txt){ const ta=document.createElement('textarea'); ta.value=txt; ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta); ta.focus(); ta.select(); try{ document.execCommand('copy'); toast('已複製全部資料'); }catch(e){ toast('複製失敗，請手動選取'); } document.body.removeChild(ta); }

// ----- 自訂卡片 -----
function addCustCard(id){
  const c=findCust(id); if(!c) return;
  let h=`<div class="field"><label>卡片名稱</label><input id="cc-title" placeholder="例如：土壤檢測、特殊備註"></div>
    <div class="field"><label>內容（選填）</label><textarea id="cc-body" placeholder="可先空白，之後再填"></textarea></div>
    <div class="btn-row"><button class="btn btn-gray" onclick="viewCustomer('${id}')">取消</button>
      <button class="btn btn-pri" id="cc-save">新增卡片</button></div>`;
  openModal('新增卡片', h);
  $('#cc-save').onclick=()=>{ const t=$('#cc-title').value.trim(); if(!t){toast('請輸入卡片名稱');return;}
    c.cards=c.cards||[]; c.cards.push({id:'K'+Date.now(),title:t,body:$('#cc-body').value.trim()});
    saveCust(); toast('已新增卡片'); viewCustomer(id); render(); };
}
function custCustomCard(id,cardId){
  const c=findCust(id); if(!c) return; const cd=(c.cards||[]).find(x=>x.id===cardId); if(!cd){ viewCustomer(id); return; }
  let h=custBackBar(id);
  h+=`<div class="card"><div class="field"><label>卡片名稱</label><input id="cc-title" value="${esc(cd.title)}"></div>
      <div class="field"><label>內容</label><textarea id="cc-body" placeholder="輸入內容…">${esc(cd.body||'')}</textarea></div>
      <div class="btn-row"><button class="btn btn-pri" onclick="saveCustomCard('${id}','${cardId}')">💾 儲存</button>
        <button class="btn btn-red" onclick="delCustomCard('${id}','${cardId}')">刪除卡片</button></div></div>`;
  openModal(`${c.name}・${cd.title}`, h);
}
function saveCustomCard(id,cardId){ const c=findCust(id); const cd=(c.cards||[]).find(x=>x.id===cardId); if(!cd)return; const t=$('#cc-title').value.trim(); if(!t){toast('請輸入卡片名稱');return;} cd.title=t; cd.body=$('#cc-body').value.trim(); saveCust(); toast('已儲存'); viewCustomer(id); render(); }
function delCustomCard(id,cardId){ if(!confirm('確定刪除這張卡片？'))return; const c=findCust(id); c.cards=(c.cards||[]).filter(x=>x.id!==cardId); saveCust(); toast('已刪除卡片'); viewCustomer(id); render(); }

function saveCustSchedule(id){ const c=findCust(id); c.grade=$('#c-grade').value; c.freq=$('#c-freq').value?+$('#c-freq').value:(c.grade?GRADE_FREQ[c.grade]:null); c.next=$('#c-next').value||(c.freq?addDays(c.last||todayStr(),c.freq):c.next); saveCust(); toast('已儲存'); render(); custGroup(id,'mgmt'); }
function saveCustProducts(id){ const c=findCust(id); c.products=readProducts(); saveCust(); toast('已儲存產品報價'); custSection(id,'products'); render(); }
function saveCustDeal(id){ const c=findCust(id); c.checkPeriod=readCheckPeriod(); const cr=$('#c-credit'); c.creditLimit=cr?cr.value.trim():(c.creditLimit||''); const regs=readRegionChips(); if(c.type==='經銷商') c.salesRegions=regs; else if(c.type==='直接農民') c.fertRegions=regs; c.mapLocations=readMapLocs(); saveCust(); toast('已儲存交易資料'); custSection(id,'deal'); render(); }
function saveCustRivals(id){ const c=findCust(id); c.rivals=readRivals(); saveCust(); toast('已儲存競品肥料'); custSection(id,'rivals'); render(); }
function saveCustFarm(id){
  const c=findCust(id);
  c.plantArea=($('#c-area').value||'').trim(); c.plantAreaUnit=$('#c-areaunit').value||'公頃';
  c.fertTons=($('#c-ferttons').value||'').trim();
  const sel=[...document.querySelectorAll('#c-crops .chip.on')].map(b=>b.dataset.c);
  const other=($('#c-cropother').value||'').split(/[、,，\s]+/).map(s=>s.trim()).filter(Boolean);
  c.crops=[...new Set([...sel, ...other])];
  c.fertMonths=[...document.querySelectorAll('#c-months .chip.on')].map(b=>+b.dataset.m).sort((a,b)=>a-b);
  saveCust(); toast('已儲存種植資料'); custSection(id,'farm'); render();
}
function toggleInactive(id){ const c=findCust(id); if(!c)return; if(!c.inactive){ if(!confirm('確定停用此客戶？資料會保留，但會標示為停用。'))return; c.inactive=true; toast('已停用客戶（資料保留）'); } else { c.inactive=false; toast('已重新啟用客戶'); } saveCust(); viewCustomer(id); render(); }
function saveCustNotes(id){ const c=findCust(id); c.notes=$('#c-notes').value.trim(); saveCust(); toast('已儲存備註'); custSection(id,'notes'); render(); }
function logCustVisit(id){ const c=findCust(id); const t=todayStr(); c.last=t; if(c.freq)c.next=addDays(t,c.freq); c.inter=c.inter||[]; c.inter.push({date:t,type:'拜訪',content:'完成拜訪'}); saveCust(); toast('已記錄拜訪'); viewCustomer(id); }
function addCustInter(id){ interForm(it=>{ const c=findCust(id); c.inter=c.inter||[]; c.inter.push(it); saveCust(); toast('已新增'); custGroup(id,'mgmt'); }); }
function delCustomer(id){ if(!confirm('確定刪除這位客戶？此動作無法復原。'))return; customers=customers.filter(c=>c.id!==id); saveCust(); closeModal(); toast('已刪除'); render(); }

function field(label,id,val,type='text',req=false,ph=''){ return `<div class="field"><label>${label}${req?' <span class="req">*</span>':''}</label><input type="${type}" id="${id}" value="${esc(val||'')}" placeholder="${esc(ph)}"></div>`; }

// ---------- 產品報價（多筆）----------
function productRowHTML(p){
  p=p||{};
  const sel=(arr,v,extra='')=>arr.map(x=>`<option ${x===v?'selected':''}>${x}</option>`).join('');
  const isCustom = p.name && !PRODUCTS.includes(p.name);
  return `<div class="prow">
    <select class="pp-name" onchange="onProdNameSel(this)">
      <option value="">產品…</option>
      ${PRODUCTS.map(x=>`<option ${x===p.name?'selected':''}>${esc(x)}</option>`).join('')}
      <option value="__other" ${isCustom?'selected':''}>＋ 其他（手動輸入新產品）</option>
    </select>
    <input class="pp-name-other" placeholder="輸入新產品名稱" value="${isCustom?esc(p.name):''}" style="margin-top:6px;display:${isCustom?'block':'none'}">
    <div class="prow-2">
      <select class="pp-form">${sel(FORMS,p.form||'粒狀')}</select>
      <select class="pp-weight">${sel(WEIGHTS,p.weight||'20')}</select>
      <input class="pp-price" type="number" inputmode="decimal" placeholder="單價" value="${esc(p.price||'')}">
      <select class="pp-freight">${sel(FREIGHTS,p.freight||'含運')}</select>
      <button type="button" class="prow-del" onclick="this.closest('.prow').remove()">✕</button>
    </div></div>`;
}
function addProductRow(){ const c=document.getElementById('prod-rows'); if(c) c.insertAdjacentHTML('beforeend', productRowHTML()); }
function onProdNameSel(s){ const t=s.closest('.prow').querySelector('.pp-name-other'); if(!t)return; const other=(s.value==='__other'); t.style.display=other?'block':'none'; if(!other)t.value=''; else t.focus(); }
function readProducts(){
  return [...document.querySelectorAll('#prod-rows .prow')].map(el=>{
    let name=el.querySelector('.pp-name').value;
    if(name==='__other'){ const t=el.querySelector('.pp-name-other'); name=t?t.value.trim():''; }
    return {
      name,
      form:el.querySelector('.pp-form').value,
      weight:el.querySelector('.pp-weight').value,
      price:el.querySelector('.pp-price').value.trim(),
      freight:el.querySelector('.pp-freight').value
    };
  }).filter(p=>p.name);
}
function prodText(p){ return `${p.form}${p.weight}kg・$${p.price||'—'}・${p.freight}`; }

// ---------- 競品肥料（多筆）----------
function rivalRowHTML(r){
  r=r||{};
  const sel=(arr,v)=>arr.map(x=>`<option ${x===v?'selected':''}>${esc(x)}</option>`).join('');
  return `<div class="prow rrow">
    <input class="rv-name" placeholder="競品產品名稱" value="${esc(r.name||'')}">
    <div class="rrow-2">
      <select class="rv-form">${sel(FORMS,r.form||'粒狀')}</select>
      <input class="rv-price" type="number" inputmode="decimal" placeholder="價格" value="${esc(r.price||'')}">
      <select class="rv-freight">${sel(FREIGHTS,r.freight||'含運')}</select>
      <button type="button" class="prow-del" onclick="this.closest('.rrow').remove()">✕</button>
    </div>
    <input class="rv-check rv-line" placeholder="票期，例如 月結30天 / 現金" value="${esc(r.checkPeriod||'')}">
    <input class="rv-note rv-line" placeholder="備註" value="${esc(r.note||'')}">
  </div>`;
}
function addRivalRow(){ const c=document.getElementById('rival-rows'); if(c) c.insertAdjacentHTML('beforeend', rivalRowHTML()); }
function readRivals(){
  return [...document.querySelectorAll('#rival-rows .rrow')].map(el=>({
    name:el.querySelector('.rv-name').value.trim(),
    form:el.querySelector('.rv-form').value,
    price:el.querySelector('.rv-price').value.trim(),
    freight:el.querySelector('.rv-freight').value,
    checkPeriod:el.querySelector('.rv-check').value.trim(),
    note:el.querySelector('.rv-note').value.trim()
  })).filter(r=>r.name);
}
function rivalText(r){ return [`${r.form||''}${r.price?'・$'+r.price:''}`, r.freight, r.checkPeriod].filter(Boolean).join('・'); }

// ---------- 區域選擇（縣市／鄉鎮・可多筆）：經銷區域 / 使用肥料區域 ----------
function getSalesRegions(c){ if(!Array.isArray(c.salesRegions)){ c.salesRegions = c.salesRegion ? [c.salesRegion] : []; } return c.salesRegions; }
function getFertRegions(c){ if(!Array.isArray(c.fertRegions)){ c.fertRegions = (c.fertLocation && countyCore(c.fertLocation)) ? [c.fertLocation] : []; } return c.fertRegions; }
function townsOfCounty(county){ if(!window.TW_MAP||!county) return []; const list=townsByCore()[countyCore(county)]||[]; return list.map(x=>x.raw).slice().sort((a,b)=>a.localeCompare(b,'zh-Hant')); }
function regionChipHTML(r){ const ic=(r==='線上通路')?'🌐':'📍'; return `<span class="reg-chip" data-r="${esc(r)}">${ic} ${esc(r)}<button type="button" onclick="this.parentNode.remove()">✕</button></span>`; }
function regionEditorHTML(label, regions, hint){
  const cn=countyNames();
  let h=`<div class="field"><label>${label}（縣市／鄉鎮・可複選）</label>`;
  if(hint) h+=`<div class="hint" style="color:var(--muted);font-size:11.5px;margin:-2px 0 6px">${hint}</div>`;
  h+=`<div id="reg-chips" style="display:flex;flex-wrap:wrap;margin-bottom:${(regions&&regions.length)?'7px':'0'}">${(regions||[]).map(regionChipHTML).join('')}</div>`;
  h+=`<div class="field-2"><div class="field" style="margin:0"><select id="reg-county" onchange="onRegCountyChange()"><option value="">選縣市…</option><option value="線上通路">🌐 線上通路</option>${cn.map(n=>`<option>${esc(n)}</option>`).join('')}</select></div>`;
  h+=`<div class="field" style="margin:0"><select id="reg-town"><option value="">全縣市（不分鄉鎮）</option></select></div></div>`;
  h+=`<button type="button" class="btn btn-out" style="margin-top:8px" onclick="addRegionChip()">＋ 新增區域</button></div>`;
  return h;
}
function onRegCountyChange(){ const c=$('#reg-county').value, t=$('#reg-town'); if(c==='線上通路'){ t.innerHTML='<option value="">（線上通路免選鄉鎮）</option>'; t.disabled=true; return; } t.disabled=false; const tw=c?townsOfCounty(c):[]; t.innerHTML='<option value="">全縣市（不分鄉鎮）</option>'+tw.map(x=>`<option>${esc(x)}</option>`).join(''); }
function addRegionChip(){ const c=$('#reg-county').value; if(!c){ toast('請先選縣市'); return; } const tw=$('#reg-town').value; const r=(c==='線上通路')?'線上通路':(tw?`${c} ${tw}`:c); const box=$('#reg-chips'); if([...box.querySelectorAll('.reg-chip')].some(el=>el.dataset.r===r)){ toast('已加入此區域'); return; } box.style.marginBottom='7px'; box.insertAdjacentHTML('beforeend', regionChipHTML(r)); $('#reg-county').value=''; const t=$('#reg-town'); t.disabled=false; t.innerHTML='<option value="">全縣市（不分鄉鎮）</option>'; }
function readRegionChips(){ const box=$('#reg-chips'); if(!box) return []; return [...box.querySelectorAll('.reg-chip')].map(el=>el.dataset.r); }

// ---------- 抵押設定（取代原「交易條件」，下拉為主）----------
const MORTGAGE_SET = ['有設定','無設定'];
const MORTGAGE_TYPE = ['動產','不動產'];
function mortgageEditorHTML(c){
  const set=c.mortgageSet||'', type=c.mortgageType||'', amt=c.mortgageAmount||'';
  let h=`<div class="field"><label>有無設定抵押</label><select id="f-mortset"><option value="" ${!set?'selected':''}>未設定</option>${MORTGAGE_SET.map(o=>`<option ${set===o?'selected':''}>${o}</option>`).join('')}</select></div>`;
  h+=`<div class="field-2"><div class="field"><label>動產 / 不動產</label><select id="f-morttype"><option value="" ${!type?'selected':''}>未選</option>${MORTGAGE_TYPE.map(o=>`<option ${type===o?'selected':''}>${o}</option>`).join('')}</select></div>`;
  h+=`<div class="field"><label>金額（萬元）</label><input id="f-mortamt" type="number" inputmode="decimal" value="${esc(amt)}" placeholder="例如 300"></div></div>`;
  return h;
}
function mortgageSummary(c){ const set=c.mortgageSet||''; if(!set) return ''; if(set==='無設定') return '無設定抵押'; const parts=[c.mortgageType, c.mortgageAmount?c.mortgageAmount+' 萬':''].filter(Boolean); return '有設定抵押'+(parts.length?'（'+parts.join('・')+'）':''); }

// ---------- 位置資訊（住家 / 下貨位置 + Google 地圖網址，可多筆）----------
// 取得目前 GPS 座標（需 HTTPS 與使用者授權；座標只用於本機帶入欄位/產生地圖連結，不外傳）
function getGeo(onOk){
  if(!navigator.geolocation){ toast('此裝置不支援定位'); return; }
  if(isInLineApp()){ toast('LINE 內建瀏覽器無法定位，請點右下「⋯」用 Safari 開啟，或手動輸入地址'); return; }
  toast('定位中…請允許位置權限');
  navigator.geolocation.getCurrentPosition(
    pos=>{ const la=pos.coords.latitude.toFixed(6), ln=pos.coords.longitude.toFixed(6); onOk(la+','+ln); },
    err=>{ toast(err && err.code===1 ? '已拒絕定位權限：請到 iPhone 設定→隱私權→定位服務→Safari 開啟，再重新整理' : '定位失敗，請稍後再試或手動輸入地址'); },
    {enableHighAccuracy:true, timeout:10000, maximumAge:0}
  );
}
function getMapLocs(c){ if(!Array.isArray(c.mapLocations)) c.mapLocations=[]; return c.mapLocations; }
function locChipHTML(l){
  const url=(l&&l.url)||''; const type=(l&&l.type)||'位置';
  const link = url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" class="loc-open">🔗 開啟</a>` : '';
  return `<div class="loc-chip" data-type="${esc(type)}" data-url="${esc(url)}">`
    + `<span class="loc-t">📍 ${esc(type)}</span>`
    + (url?`<span class="loc-u">${esc(url)}</span>`:`<span class="loc-u loc-empty">未填網址</span>`)
    + link
    + `<button type="button" class="loc-del" onclick="this.closest('.loc-chip').remove()">✕</button></div>`;
}
function locEditorHTML(locs){
  let h=`<div class="field"><label>位置資訊（住家／下貨位置・可新增多筆）</label>`;
  h+=`<div class="hint">選好類型後可按「📍 用目前定位」就地擷取座標，或貼上 Google 地圖網址，方便日後導航或分享給司機</div>`;
  h+=`<div id="loc-chips" style="display:flex;flex-direction:column;gap:6px;margin-bottom:${(locs&&locs.length)?'7px':'0'}">${(locs||[]).map(locChipHTML).join('')}</div>`;
  h+=`<div class="loc-add"><select id="loc-type">${LOC_TYPES.map(t=>`<option>${t}</option>`).join('')}</select>`
    + `<input id="loc-url" type="url" inputmode="url" placeholder="貼上 Google 地圖網址"></div>`;
  h+=`<div class="btn-row" style="margin-top:6px;gap:8px"><button type="button" class="btn btn-out" onclick="addMapLoc()">＋ 新增位置</button><button type="button" class="btn btn-out" onclick="addMapLocGeo()">📍 用目前定位</button></div>`;
  h+=`</div>`;
  return h;
}
function normLocUrl(u){ u=(u||'').trim(); if(!u) return ''; if(!/^https?:\/\//i.test(u)) u='https://'+u.replace(/^\/+/,''); return u; }
function addMapLoc(){
  const t=$('#loc-type').value; const u=normLocUrl($('#loc-url').value);
  if(!u){ toast('請貼上 Google 地圖網址'); return; }
  const box=$('#loc-chips'); if(!box) return;
  if([...box.querySelectorAll('.loc-chip')].some(el=>el.dataset.url===u)){ toast('已加入此網址'); return; }
  box.style.marginBottom='7px';
  box.insertAdjacentHTML('beforeend', locChipHTML({type:t,url:u}));
  $('#loc-url').value='';
}
function addMapLocGeo(){
  const t=($('#loc-type')&&$('#loc-type').value)||'位置';
  getGeo(coord=>{
    const u='https://www.google.com/maps/search/?api=1&query='+coord;
    const box=$('#loc-chips'); if(!box) return;
    if([...box.querySelectorAll('.loc-chip')].some(el=>el.dataset.url===u)){ toast('已加入此位置'); return; }
    box.style.marginBottom='7px';
    box.insertAdjacentHTML('beforeend', locChipHTML({type:t,url:u}));
    toast('已加入目前定位（'+coord+'）');
  });
}
function readMapLocs(){
  const box=$('#loc-chips');
  const out = box ? [...box.querySelectorAll('.loc-chip')].map(el=>({type:el.dataset.type||'位置',url:el.dataset.url||''})) : [];
  // 若使用者打了網址但忘了按「＋新增位置」，儲存時自動納入
  const ui=$('#loc-url'); const ut=$('#loc-type');
  if(ui){ const u=normLocUrl(ui.value); if(u && !out.some(l=>l.url===u)) out.push({type:(ut&&ut.value)||'位置', url:u}); }
  return out.filter(l=>l.url);
}

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
  const _orgs=[...new Set(customers.map(x=>x.org).filter(Boolean))].sort();
  h+=`<div class="field"><label>所屬組織</label><input id="f-org" list="f-org-dl" value="${esc(c.org||'')}" placeholder="例如 打貓合作社"><datalist id="f-org-dl">${_orgs.map(o=>`<option value="${esc(o)}">`).join('')}</datalist></div>`;
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
  h+=`<fieldset class="fset"><legend>競品肥料（目前使用 / 銷售・可多筆）</legend>
    <div id="rival-rows">${(c.rivals||[]).map(rivalRowHTML).join('')}</div>
    <div class="more" style="margin-top:8px" onclick="addRivalRow()">＋ 新增競品肥料</div></fieldset>`;
  h+=`<fieldset class="fset"><legend>交易條件</legend>`;
  h+=checkPeriodHTML(c.checkPeriod);
  h+=field('額度（萬元）','f-creditLimit',c.creditLimit,'number',false,'例如 50');
  h+=mortgageEditorHTML(c);
  h+=`<div class="hint" style="color:var(--muted);font-size:11.5px;margin:2px 0 6px">經銷區域（經銷商）／使用肥料區域（直接農民）請到「交易 / 配送」卡片用縣市鄉鎮下拉設定。</div>`;
  h+=field('其他條件','f-conditions',c.conditions);
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
  Object.assign(base,{ id, name, type:$('#f-type').value, org:g('f-org'), sysno:g('f-sysno'), phone:g('f-phone'), contact:g('f-contact'),
    address:g('f-address'), filedDate:g('f-filedDate'), taxid:g('f-taxid'), idno:g('f-idno'), birth:g('f-birth'),
    regAddress:g('f-regAddress'), checkPeriod:readCheckPeriod(), conditions:g('f-conditions'),
    mortgageSet:($('#f-mortset')?$('#f-mortset').value:''), mortgageType:($('#f-morttype')?$('#f-morttype').value:''), mortgageAmount:g('f-mortamt'),
    truck:g('f-truck'), deliveryTime:g('f-deliveryTime'),
    creditLimit:g('f-creditLimit'),
    grade:$('#f-grade').value, notes:g('f-notes'), products:readProducts(), rivals:readRivals() });
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
  // 戰鬥人員（戰情公仔）設定
  h+=`<div class="sec-title"><span class="bar"></span>戰鬥人員設定（戰情公仔）</div><div class="card">`;
  h+=soldierWrap(soldier,'s');
  h+=`<div class="field"><label>戰鬥人員名稱</label><input id="sol-name" type="text" value="${esc(soldier.name||'')}" placeholder="例：莊政遠 中士" oninput="soldier.name=this.value;saveSoldier()"></div>`;
  const _cN=countyNames(), _reg=getRegions();
  h+=`<div class="field"><label>所屬戰鬥區域（可複選・連動戰情地圖）</label>`;
  if(_cN.length){
    h+=`<div class="chips chips-wrap"><button class="chip ${!_reg.length?'on':''}" onclick="clearSoldierCounties()">🌏 全台灣</button>`+
      _cN.map(n=>`<button class="chip ${_reg.includes(n)?'on':''}" onclick="setSoldierCounty('${esc(n)}')">${esc(n)}</button>`).join('')+`</div>`;
    h+=`<div class="hint" style="font-size:11px;color:var(--muted)">選好的區域會自動帶到「戰情地圖」並縮放顯示。${_reg.length?'已選 '+_reg.length+' 區':''}</div>`;
  } else { h+=`<div class="hint" style="color:var(--muted)">地圖資料載入中，請稍候再設定。</div>`; }
  h+=`</div>`;
  h+=`<div class="rowsel"><span class="rowsel-l">軍種</span><div class="chips">`+
    Object.entries(BRANCHES).map(([k,v])=>`<button class="chip ${soldier.branch===k?'on':''}" onclick="setSoldierBranch('${k}')">${v.emoji} ${v.label}</button>`).join('')+`</div></div>`;
  h+=`<div class="rowsel" style="align-items:flex-start"><span class="rowsel-l">武器</span><div class="chips">`+
    Object.entries(WEAPONS).map(([k,v])=>`<button class="chip ${soldier.weapon===k?'on':''}" onclick="setSoldierWeapon('${k}')">${v.emoji} ${v.label}</button>`).join('')+`</div></div>`;
  h+=`<div class="btn-row" style="margin-top:8px"><button class="btn btn-out" onclick="document.getElementById('solphoto').click()">📷 上傳照片當公仔的臉</button></div>`;
  h+=`<input type="file" id="solphoto" accept="image/*" style="display:none" onchange="uploadSoldierPhoto(this)">`;
  if(soldier.photo) h+=`<div class="btn-row"><button class="btn btn-gray" onclick="removeSoldierPhoto()">🗑️ 移除照片（改用卡通臉）</button></div>`;
  h+=`<div class="hint" style="margin-top:7px;color:var(--muted);font-size:11px">照片會自動縮圖、只存在你本機裝置，不會上傳。點公仔可以撫摸互動 😆</div>`;
  h+=`<div class="btn-row" style="margin-top:10px"><button class="btn btn-pri" onclick="saveSoldierSettings()">💾 儲存戰鬥人員設定</button></div>`;
  h+=`</div>`;
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
  // Google 雲端硬碟備份
  const _gcid=gdriveClientId(), _glast=gdriveLast();
  h+=`<div class="sec-title"><span class="bar"></span>Google 雲端硬碟備份</div><div class="card">`;
  h+=`<div class="hint" style="color:var(--muted);font-size:11.5px;line-height:1.7;margin-top:0">把全部資料（含客戶個資）備份到<b>你自己的</b> Google 雲端硬碟。⚠️ 資料會以<b>原文</b>存到 Google，請確認帳號只有你能登入。需先做一次性設定（見下方說明）。</div>`;
  h+=`<div class="field" style="margin-top:8px"><label>Google OAuth 用戶端 ID</label><input id="gd-cid" value="${esc(_gcid)}" placeholder="xxxxx.apps.googleusercontent.com" style="font-size:12px"></div>`;
  h+=`<div class="btn-row" style="margin-top:0"><button class="btn btn-out" onclick="saveGdriveClientId(document.getElementById('gd-cid').value)">💾 儲存 ID</button></div>`;
  h+=`<label style="display:flex;align-items:center;gap:8px;margin:10px 2px 2px;font-size:13px"><input type="checkbox" ${gdriveAuto()?'checked':''} onchange="toggleGdriveAuto(this.checked)" style="width:18px;height:18px">每天自動備份（每次開App超過約20小時就自動上傳）</label>`;
  h+=`<div class="btn-row" style="margin-top:8px"><button class="btn btn-pri" onclick="gdriveBackup('')">☁️ 立即備份到雲端</button></div>`;
  h+=`<div class="btn-row"><button class="btn btn-gray" onclick="gdriveRestore()">⬇️ 從雲端還原最新備份</button></div>`;
  h+=`<div class="hint" style="margin-top:6px;color:var(--muted);font-size:11px">上次雲端備份：${_glast?esc(new Date(_glast).toLocaleString('zh-TW')):'尚未備份'}</div>`;
  h+=`<details style="margin-top:8px"><summary style="font-size:12.5px;color:#3a473f;cursor:pointer;font-weight:600">📋 一次性設定教學（換手機時也照這個做‧點開）</summary><div style="font-size:11.5px;line-height:1.9;color:#3a473f;margin-top:6px">
    <b>建議用電腦操作。</b>到 <b>Google Cloud Console</b>（console.cloud.google.com）用你的 Google 帳號登入，沿用預設的「My First Project」即可。<br>
    <b>1.</b> 點「<b>Google Auth Platform</b>」（管理類別，說明寫 OAuth 設定和憑證）→「開始使用 / Get started」。<br>
    <b>2.</b> 填：應用程式名稱 <b>碩成CRM</b>、支援信箱選自己、<b>目標對象選「外部 External」</b>、聯絡信箱填自己 → 同意 → 建立。<br>
    <b>3.</b> 左側「<b>目標對象 / Audience</b>」→ 測試使用者「+ Add users」→ 把<b>你自己的 Gmail</b> 加進去 → 儲存。<br>
    <b>4.</b> 左側「<b>用戶端 / Clients</b>」→「建立用戶端」→ 類型選「<b>網頁應用程式</b>」。<br>
    <b>5.</b> 「已授權的 JavaScript 來源」新增：<b>https://yuan780903-cpu.github.io</b> → 建立。<br>
    <b>6.</b> 複製跳出的<b>用戶端 ID</b>（結尾 .apps.googleusercontent.com），貼到上面欄位按「儲存 ID」。<br>
    <b>7.</b> 漢堡選單 ☰ →「API 和服務 → 程式庫」搜尋 <b>Google Drive API</b> 並<b>啟用</b>（沒開備份會失敗）。<br>
    （用戶端 ID 不是密碼，只存你手機本機；權限只開放本App建立的備份檔，看不到你雲端其他檔案。）</div></details>`;
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
    <b>🧭 切換功能：</b>用畫面最下方的導覽列（或 LINE 選單）切換地圖／名單／路線／客戶／競品／週報／設定。</div>`;
  viewHTML(h);
}
function download(name, content, type){
  const blob=new Blob([content],{type}); const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function backupBundle(){ return {ver:2, exported:new Date().toISOString(), customers, overlay, competitors, soldier, prospects:customProspects}; }
function exportJSON(){
  download(`客戶管理備份_${todayStr()}.json`, JSON.stringify(backupBundle()), 'application/json');
  toast('已匯出備份');
}
function exportCSV(){
  const cols=[['sysno','系統編號'],['name','名稱'],['type','類型'],['grade','分級'],['inactive','停用'],['phone','電話'],['contact','聯絡人'],['address','通訊地址'],['regAddress','戶籍地址'],['taxid','統編'],['idno','身分證'],['birth','生日'],['filedDate','建檔日期'],['checkPeriod','票期'],['creditLimit','額度(萬元)'],['mortgageSet','有無設定抵押'],['mortgageType','抵押動產/不動產'],['mortgageAmount','抵押金額(萬元)'],['fertRegions','使用肥料區域'],['salesRegions','經銷區域'],['plantArea','種植面積'],['crops','作物類別'],['fertTons','年用肥噸數'],['fertMonths','用肥月份'],['products','產品報價'],['rivals','競品肥料'],['conditions','其他條件'],['truck','運送車輛'],['deliveryTime','送貨時間'],['mapLocations','位置資訊'],['freq','拜訪頻率'],['next','下次拜訪'],['notes','備註']];
  const head=cols.map(c=>c[1]).join(',');
  const fmt=(c,k)=>{ if(k==='products') return (c.products||[]).map(p=>`${p.name} ${prodText(p)}`).join(' / '); if(k==='rivals') return (c.rivals||[]).map(r=>`${r.name} ${rivalText(r)}${r.note?'('+r.note+')':''}`).join(' / '); if(k==='salesRegions'||k==='fertRegions'||k==='crops') return (c[k]||[]).join('、'); if(k==='fertMonths') return (c.fertMonths||[]).map(m=>m+'月').join('、'); if(k==='mapLocations') return (c.mapLocations||[]).map(l=>`${l.type}:${l.url}`).join(' / '); if(k==='plantArea') return c.plantArea?c.plantArea+(c.plantAreaUnit||'公頃'):''; if(k==='inactive') return c.inactive?'停用':''; return c[k]??''; };
  const rows=customers.map(c=>cols.map(([k])=>`"${String(fmt(c,k)).replace(/"/g,'""')}"`).join(','));
  download(`我的客戶_${todayStr()}.csv`, '﻿'+head+'\n'+rows.join('\n'), 'text/csv');
  toast('已匯出 CSV');
}
function importJSON(input){
  const f=input.files[0]; if(!f)return; const r=new FileReader();
  r.onload=()=>{ try{ const d=JSON.parse(r.result);
    if(Array.isArray(d.customers)){ const ids=new Set(customers.map(c=>c.id)); d.customers.forEach(c=>{ if(ids.has(c.id))c.id='C'+Date.now()+Math.random().toString(36).slice(2,5); customers.push(c); }); }
    if(d.overlay) Object.assign(overlay, d.overlay);
    if(Array.isArray(d.competitors)){ const cids=new Set(competitors.map(c=>c.id)); d.competitors.forEach(c=>{ if(!cids.has(c.id)) competitors.push(c); }); saveComp(); }
    if(d.soldier && typeof d.soldier==='object'){ Object.assign(soldier, d.soldier); saveSoldier(); }
    if(Array.isArray(d.prospects)){ const pids=new Set(customProspects.map(p=>p.id)); d.prospects.forEach(p=>{ if(p&&p.id&&!pids.has(p.id)){ customProspects.push(p); if(!SEED.some(s=>s.id===p.id)) SEED.push(p); } }); saveProspects(); }
    saveCust(); saveOverlay(); toast('已匯入還原'); render();
  }catch(e){ alert('檔案格式錯誤，無法匯入'); } };
  r.readAsText(f); input.value='';
}

// ---------- Google 雲端硬碟備份（存到使用者自己的 Drive；drive.file 權限只看得到本App建立的檔）----------
const GDRIVE_SCOPE='https://www.googleapis.com/auth/drive.file';
let _gToken=null;   // {token, exp}
function gdriveClientId(){ return (localStorage.getItem('crm_gdrive_clientid')||'').trim(); }
function gdriveLast(){ return localStorage.getItem('crm_gdrive_last')||''; }
function gdriveAuto(){ return localStorage.getItem('crm_gdrive_auto')==='1'; }
function saveGdriveClientId(v){ localStorage.setItem('crm_gdrive_clientid',(v||'').trim()); _gToken=null; toast('已儲存用戶端 ID'); }
function toggleGdriveAuto(on){ localStorage.setItem('crm_gdrive_auto', on?'1':'0'); toast(on?'已開啟每天自動備份':'已關閉自動備份'); }
function loadGIS(){ return new Promise((res,rej)=>{ if(window.google&&google.accounts&&google.accounts.oauth2) return res(); const s=document.createElement('script'); s.src='https://accounts.google.com/gsi/client'; s.async=true; s.onload=()=>res(); s.onerror=()=>rej(new Error('無法載入 Google 登入元件，請確認網路')); document.head.appendChild(s); }); }
function getDriveToken(mode){   // mode==='silent' → 用 prompt:'none'（無彈窗，需既有授權）；否則互動授權
  return new Promise(async (resolve,reject)=>{
    const cid=gdriveClientId(); if(!cid){ reject(new Error('尚未填入 Google 用戶端 ID')); return; }
    if(_gToken && _gToken.exp>Date.now()+60000){ resolve(_gToken.token); return; }
    try{ await loadGIS(); }catch(e){ return reject(e); }
    const tc=google.accounts.oauth2.initTokenClient({
      client_id:cid, scope:GDRIVE_SCOPE,
      callback:(resp)=>{ if(resp&&resp.access_token){ _gToken={token:resp.access_token, exp:Date.now()+(resp.expires_in||3600)*1000}; resolve(resp.access_token); } else reject(new Error(resp&&resp.error?resp.error:'授權失敗')); },
      error_callback:(err)=>reject(new Error((err&&err.type)||'授權失敗或被取消'))
    });
    try{ tc.requestAccessToken({prompt: mode==='silent'?'none':''}); }catch(e){ reject(e); }
  });
}
async function driveFindFile(token,name){
  const q=encodeURIComponent(`name='${name}' and trashed=false`);
  const r=await fetch(`https://www.googleapis.com/drive/v3/files?q=${q}&spaces=drive&fields=files(id,name)&orderBy=modifiedTime desc`,{headers:{Authorization:'Bearer '+token}});
  if(!r.ok) throw new Error('Drive 查詢失敗 '+r.status);
  const j=await r.json(); return (j.files&&j.files[0])||null;
}
async function driveUpload(token,name,content,existingId){
  const boundary='crmbnd'+Date.now();
  const meta=existingId?{}:{name, mimeType:'application/json'};
  const body=`--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(meta)}\r\n--${boundary}\r\nContent-Type: application/json\r\n\r\n${content}\r\n--${boundary}--`;
  const url=existingId
    ? `https://www.googleapis.com/upload/drive/v3/files/${existingId}?uploadType=multipart&fields=id`
    : `https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id`;
  const r=await fetch(url,{method:existingId?'PATCH':'POST', headers:{Authorization:'Bearer '+token,'Content-Type':'multipart/related; boundary='+boundary}, body});
  if(!r.ok){ const t=await r.text(); throw new Error('上傳失敗 '+r.status+' '+t.slice(0,100)); }
  return r.json();
}
async function gdriveBackup(mode){
  try{
    if(mode!=='silent') toast('連結 Google 中…');
    const token=await getDriveToken(mode);
    const name=`碩成CRM備份_${todayStr()}.json`;
    const ex=await driveFindFile(token,name);
    await driveUpload(token,name,JSON.stringify(backupBundle()), ex&&ex.id);
    localStorage.setItem('crm_gdrive_last', new Date().toISOString());
    toast('✅ 已備份到 Google 雲端硬碟');
    if(tab==='settings') renderSettings();
  }catch(e){
    if(mode==='silent'){ console.log('silent backup skipped:', e.message); return; }
    toast('雲端備份失敗：'+e.message);
  }
}
async function gdriveRestore(){
  if(!confirm('將從 Google 雲端硬碟取回最新備份，並「覆蓋」這台裝置目前的客戶／排程資料。確定要還原嗎？')) return;
  try{
    toast('連結 Google 中…');
    const token=await getDriveToken('');
    const q=encodeURIComponent(`name contains '碩成CRM備份' and trashed=false`);
    const r=await fetch(`https://www.googleapis.com/drive/v3/files?q=${q}&spaces=drive&fields=files(id,name)&orderBy=modifiedTime desc`,{headers:{Authorization:'Bearer '+token}});
    if(!r.ok) throw new Error('查詢失敗 '+r.status);
    const j=await r.json(); const f=j.files&&j.files[0];
    if(!f){ toast('雲端找不到備份檔'); return; }
    const dr=await fetch(`https://www.googleapis.com/drive/v3/files/${f.id}?alt=media`,{headers:{Authorization:'Bearer '+token}});
    if(!dr.ok) throw new Error('下載失敗 '+dr.status);
    const d=await dr.json();
    if(Array.isArray(d.customers)){ customers=d.customers; saveCust(); }
    if(d.overlay&&typeof d.overlay==='object'){ overlay=d.overlay; saveOverlay(); }
    if(Array.isArray(d.competitors)){ competitors=d.competitors; saveComp(); }
    if(d.soldier&&typeof d.soldier==='object'){ Object.assign(soldier,d.soldier); saveSoldier(); }
    if(Array.isArray(d.prospects)){ customProspects=d.prospects; customProspects.forEach(p=>{ if(p&&p.id&&!SEED.some(s=>s.id===p.id)) SEED.push(p); }); saveProspects(); }
    toast('✅ 已從雲端還原'); render();
  }catch(e){ toast('還原失敗：'+e.message); }
}
function maybeAutoBackup(){
  if(!gdriveAuto()||!gdriveClientId()) return;
  const last=gdriveLast(); if(last && (Date.now()-new Date(last).getTime()) < 20*3600*1000) return;
  setTimeout(()=>gdriveBackup('silent'), 3000);   // 試無彈窗備份；iPhone Safari 可能擋，會自動略過待手動
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
        creditLimit:'', fertRegions:[], salesRegions:[], rivals:[], inactive:false,
        plantArea:'', plantAreaUnit:'公頃', crops:[], fertTons:'', fertMonths:[], mapLocations:[],
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
let routeCfg = {regions:[], home:'', start:'08:00', end:'17:00', dwell:40, nl:'', rules:[{status:'',channel:'',grade:'',n:5}], _last:''};
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
// ---------- 模式切換：智慧安排 / 每週智慧排程 / 自訂單日路線 ----------
let routeMode = 'smart';
function setRouteMode(m){ routeMode=m; renderRoute(); }
function renderRoute(){
  let h=`<div class="field" style="margin-bottom:10px"><label>排程模式</label>
    <select onchange="setRouteMode(this.value)">
      <option value="smart" ${routeMode==='smart'?'selected':''}>🧠 每日智慧安排</option>
      <option value="week" ${routeMode==='week'?'selected':''}>📅 每週排程</option>
      <option value="custom" ${routeMode==='custom'?'selected':''}>🗺️ 每日條件路線</option></select></div>
    <div id="route-body"></div>`;
  viewHTML(h);
  if(routeMode==='smart') renderSmartRoute();
  else if(routeMode==='week') renderWeekRoute();
  else renderCustomRoute();
}

// ========== 智慧客戶拜訪路線安排 ==========
// 設出發/回家位置與時間、午休，依篩選把客戶加入名單、可設約定到達時間，
// 「智慧安排」依位置就近排出最佳前後順序並穿插已約客戶。全程本機計算、不外傳。
const SMART_DWELL = 40;
const UNIT_HA = {'公頃':1,'甲':0.9699,'分':0.09699,'坪':0.0033058};
let smartCfg = {
  startLoc:'', startTime:'08:00',
  endLoc:'', endTime:'17:00',
  lunchStart:'12:00', lunchEnd:'13:00', lunchLoc:'',
  f:{ src:'', organic:'', regions:[], channel:'', area:'', grade:'' },
  picks:[],   // {key,kind,id,name,channel,grade,address,phone,district,organic,area,dwell,fixed}
  _last:'', _inited:0, _poolOpen:0
};
function custAreaHa(c){ const n=parseFloat(c.plantArea); if(isNaN(n))return null; return n*(UNIT_HA[c.plantAreaUnit||'公頃']||1); }
// 地理排序索引：縣市(由北而南)*10萬 + 鄉鎮在官方清單的序（同縣市內大致地理相鄰）
function smartGeoIdx(addr){
  const core=countyCore(addr);
  const ci = core ? REGION_ORDER.indexOf(core) : 99;
  const tn = core ? matchTown(addr,core) : '';
  let ti=9999;
  if(tn){ const tw=window.TW_MAP.towns; const idx=tw.findIndex(t=>countyCore(t.c)===core && t.t===tn); if(idx>=0)ti=idx; }
  return (ci<0?99:ci)*100000 + ti;
}
// ---- 離線距離估算（不外傳）----
// 由 map-data.js 的鄉鎮 SVG 路徑算出中心點，再以校正後的仿射轉換換成近似經緯度，
// 用 haversine 算直線距離→換算開車時間。座標(定位)地址可直接用。全程本機計算。
const GEO_LAT=[-1.892765e-5,-2.349097e-3,2.531461e+1];
const GEO_LNG=[2.571412e-3,7.081449e-6,1.194307e+2];
function smartTownCentroids(){
  if(window._tcen) return window._tcen;
  const m={};
  if(window.TW_MAP&&window.TW_MAP.towns){
    window.TW_MAP.towns.forEach(t=>{
      const nums=(t.d||'').replace(/[A-Za-z]/g,' ').trim().split(/\s+/).map(Number).filter(n=>!isNaN(n));
      let sx=0,sy=0,n=0; for(let i=0;i+1<nums.length;i+=2){ sx+=nums[i]; sy+=nums[i+1]; n++; }
      if(n){ const core=countyCore(t.c); const ll=[GEO_LAT[0]*(sx/n)+GEO_LAT[1]*(sy/n)+GEO_LAT[2], GEO_LNG[0]*(sx/n)+GEO_LNG[1]*(sy/n)+GEO_LNG[2]]; m[core+'|'+t.t]=ll; (m[core]=m[core]||[]).push(ll); }
    });
    // 縣市中心＝該縣市各鄉鎮中心平均
    Object.keys(m).forEach(k=>{ if(k.includes('|'))return; const arr=m[k]; m['#'+k]=[arr.reduce((s,p)=>s+p[0],0)/arr.length, arr.reduce((s,p)=>s+p[1],0)/arr.length]; });
  }
  window._tcen=m; return m;
}
// 從 Google 地圖網址 / 座標字串取出 [lat,lng]（純前端解析，不連網）
function parseGmaps(s){
  s=String(s||'');
  const m=s.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/)
      || s.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/)
      || s.match(/[?&](?:q|query|ll|center|destination|daddr)=(-?\d+\.\d+),\s*(-?\d+\.\d+)/)
      || s.match(/\/(-?\d+\.\d+),(-?\d+\.\d+)(?:[\/,?]|$)/);
  if(m){ const la=+m[1], ln=+m[2]; if(la>=20&&la<=27&&ln>=118&&ln<=123) return [la,ln]; }
  return null;
}
function smartLatLng(addr){
  if(!addr) return null;
  const mc=String(addr).trim().match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
  if(mc){ const la=+mc[1], ln=+mc[2]; if(la>=20&&la<=27&&ln>=118&&ln<=123) return [la,ln]; }
  const gm=parseGmaps(addr); if(gm) return gm;   // 貼上 Google 地圖網址也能精準定位
  const C=smartTownCentroids(); const core=countyCore(addr);
  if(core){
    const tn=matchTown(addr,core); if(tn&&C[core+'|'+tn]) return C[core+'|'+tn];
    return C['#'+core]||null;   // 只知縣市→用縣市中心
  }
  // 沒有縣市字樣→用鄉鎮市區名稱比對（例如「楠西7-11」→ 楠西）
  const t=smartTownByName(addr);
  if(t){ const k=countyCore(t.c)+'|'+t.t; if(C[k]) return C[k]; }
  return null;
}
function smartTownByName(addr){
  if(!window.TW_MAP||!window.TW_MAP.towns) return null;
  const s=normR(addr); let best=null,bl=0;
  window.TW_MAP.towns.forEach(t=>{
    const base=normR(t.t).replace(/[區鄉鎮市]$/,'');
    if(base.length>=2 && s.indexOf(base)>=0 && base.length>bl){ best=t; bl=base.length; }
  });
  return best;
}
function kmBetween(a,b){ const R=6371,d2r=Math.PI/180; const dla=(b[0]-a[0])*d2r,dlo=(b[1]-a[1])*d2r; const x=Math.sin(dla/2)**2+Math.cos(a[0]*d2r)*Math.cos(b[0]*d2r)*Math.sin(dlo/2)**2; return 2*R*Math.asin(Math.sqrt(x)); }
// 以「開車走高速公路為主」估速：短程市區較慢、中長程上快速道路/國道
function driveMin(km){ const rk=km*1.30; let sp; if(rk<5)sp=24; else if(rk<15)sp=38; else if(rk<35)sp=55; else if(rk<70)sp=72; else sp=88; return Math.max(7, Math.round(rk/sp*60)+3); }
// ---- 線上實際路網車程（OSRM，可選；只送鄉鎮中心座標，不送任何客戶地址/個資）----
window._osrmDur = window._osrmDur || {};
function llKey(ll){ return ll[0].toFixed(4)+','+ll[1].toFixed(4); }
function osrmLookup(a,b){ if(!a||!b)return null; const v=window._osrmDur[llKey(a)+'>'+llKey(b)]; return v==null?null:v; }
async function osrmFillTable(lls){
  // 只取唯一的鄉鎮中心座標送出（去重），不含任何地址文字
  const uniq=[], seen={};
  lls.forEach(ll=>{ if(!ll)return; const k=llKey(ll); if(!(k in seen)){ seen[k]=uniq.length; uniq.push(ll); } });
  if(uniq.length<2 || uniq.length>90) return false;
  const pts=uniq.map(c=>c[1].toFixed(5)+','+c[0].toFixed(5)).join(';');  // OSRM 是 lng,lat
  const url=`https://router.project-osrm.org/table/v1/driving/${pts}?annotations=duration`;
  let j;
  try{ const ctrl=new AbortController(); const to=setTimeout(()=>ctrl.abort(),9000);
    const r=await fetch(url,{signal:ctrl.signal}); clearTimeout(to); if(!r.ok)return false; j=await r.json();
  }catch(e){ return false; }
  if(!j||j.code!=='Ok'||!Array.isArray(j.durations)) return false;
  for(let i=0;i<uniq.length;i++) for(let k=0;k<uniq.length;k++){
    const sec=j.durations[i] && j.durations[i][k]; if(sec==null)continue;
    const min=Math.max(6, Math.round(sec/60*1.15)+2);   // 實際車程＋15%路況緩衝
    window._osrmDur[llKey(uniq[i])+'>'+llKey(uniq[k])]=min;
  }
  return true;
}
function smartTravel(a,b){
  const pa=smartLatLng(a), pb=smartLatLng(b);
  if(pa&&pb){ const od=osrmLookup(pa,pb); if(od!=null)return od; return driveMin(kmBetween(pa,pb)); }
  if(!a||!b)return 15; const ca=countyCore(a),cb=countyCore(b); if(ca&&cb&&ca!==cb)return 35; const da=district(a),db=district(b); if(da&&db&&da!==db)return 18; return 10;
}
// 兩座標間的車程（分鐘）：有 OSRM 用實際路網，否則用離線估算
function travelMinLL(a,b){ if(!a||!b)return null; const od=osrmLookup(a,b); if(od!=null)return od; return driveMin(kmBetween(a,b)); }
// 最近鄰 + 2-opt 路徑最佳化（離線/線上皆可，依出發點決定方向，消除來回繞路）
function optimizeFreeOrder(items, startLL, endLL){
  const withLL=items.filter(p=>p._ll), noLL=items.filter(p=>!p._ll);
  noLL.sort((a,b)=>smartGeoIdx(a.address)-smartGeoIdx(b.address));
  if(withLL.length<=1) return withLL.concat(noLL);
  const D=(x,y)=>travelMinLL(x,y);
  // 最近鄰建構
  const left=withLL.slice(), order=[]; let cur=startLL;
  if(!cur){ order.push(left.shift()); cur=order[0]._ll; }
  while(left.length){ let bi=0,bd=Infinity; for(let i=0;i<left.length;i++){ const d=D(cur,left[i]._ll); if(d<bd){bd=d;bi=i;} } const nx=left.splice(bi,1)[0]; order.push(nx); cur=nx._ll; }
  // 2-opt 改良（含「回到出發/回家點」的最後一段，避免結束在最遠的離群點）
  let improved=true, guard=0;
  while(improved && guard++<80){
    improved=false;
    for(let i=0;i<order.length-1;i++){
      const A = i>0 ? order[i-1]._ll : startLL; if(!A) continue;
      const B = order[i]._ll;
      for(let k=i+1;k<order.length;k++){
        const C=order[k]._ll, E=(k<order.length-1)?order[k+1]._ll:(endLL||null);
        const cur=D(A,B)+(E?D(C,E):0);
        const swp=D(A,C)+(E?D(B,E):0);
        if(swp+1e-6 < cur){ let lo=i,hi=k; while(lo<hi){ const t=order[lo];order[lo]=order[hi];order[hi]=t;lo++;hi--; } improved=true; }
      }
    }
  }
  return order.concat(noLL);
}
function smartPool(){
  const f=smartCfg.f;
  const regs=f.regions||[];
  const cores=regs.map(r=>normR(r).replace(/[縣市]$/,'')).filter(Boolean);
  const exIds=existingProspectIds();
  let pool=[];
  if(f.src!=='prosp'){
    customers.forEach(c=>{
      if(c.inactive) return;
      const chan=TYPE2CHAN[c.type]||c.type||'其他';
      pool.push({key:'c'+c.id,kind:'cust',id:c.id,name:c.name,channel:chan,status:'existing',grade:c.grade||'',address:c.address||'',phone:c.phone||'',district:district(c.address),organic:chan==='有機農戶'?'org':'non',area:custAreaHa(c)});
    });
  }
  if(f.src!=='cust'){
    SEED.forEach(p=>{
      pool.push({key:'p'+p.id,kind:'prosp',id:p.id,name:p.name,channel:p.category||'其他',status:exIds.has(p.id)?'existing':'cold',grade:(overlay[p.id]&&overlay[p.id].grade)||'',address:p.address||'',phone:p.phone||'',district:district(p.address),organic:p.category==='有機農戶'?'org':'non',area:areaVal(p),region:p.region});
    });
  }
  return pool.filter(x=>{
    if(!x.address) return false;
    if(regs.length){ const okR=regs.some(rg=>x.region&&normR(x.region)===normR(rg))||cores.some(core=>normR(x.address).includes(core)); if(!okR)return false; }
    if(f.organic && x.organic!==f.organic) return false;
    if(f.channel && x.channel!==f.channel) return false;
    if(f.grade){ if(f.grade==='none'){ if(x.grade)return false; } else if(x.grade!==f.grade)return false; }
    if(f.area){ const m=parseFloat(f.area); if(!isNaN(m)){ if(x.area==null||x.area<m)return false; } }
    return true;
  });
}
function syncSmart(){
  const g=id=>{const el=$('#'+id);return el?el.value:undefined;};
  let v;
  if((v=g('sm-startloc'))!==undefined) smartCfg.startLoc=v.trim();
  if((v=g('sm-endloc'))!==undefined) smartCfg.endLoc=v.trim();
  if((v=g('sm-start'))!==undefined) smartCfg.startTime=v||'08:00';
  if((v=g('sm-end'))!==undefined) smartCfg.endTime=v||'17:00';
  if((v=g('sm-lunch1'))!==undefined) smartCfg.lunchStart=v||'12:00';
  if((v=g('sm-lunch2'))!==undefined) smartCfg.lunchEnd=v||'13:00';
  if((v=g('sm-lunchloc'))!==undefined) smartCfg.lunchLoc=v.trim();
  // filters
  if((v=g('sm-src'))!==undefined) smartCfg.f.src=v;
  if((v=g('sm-organic'))!==undefined) smartCfg.f.organic=v;
  // 地區改為多選晶片，由 toggleSmartRegion 直接維護 smartCfg.f.regions
  if((v=g('sm-channel'))!==undefined) smartCfg.f.channel=v;
  if((v=g('sm-grade'))!==undefined) smartCfg.f.grade=v;
  if((v=g('sm-area'))!==undefined) smartCfg.f.area=v;
  // pick rows (dwell + fixed time)
  document.querySelectorAll('#route-body .pk-row').forEach(el=>{
    const k=el.dataset.k, p=smartCfg.picks.find(x=>x.key===k); if(!p)return;
    const d=el.querySelector('.pk-dwell'), fx=el.querySelector('.pk-fixed');
    if(d) p.dwell=Math.max(5,+d.value||SMART_DWELL);
    if(fx) p.fixed=fx.value||'';
    if(p.kind==='custom'){
      const nm=el.querySelector('.pk-name'), ad=el.querySelector('.pk-addr');
      if(nm) p.name=nm.value||'其他行程';
      if(ad){ p.address=ad.value.trim(); p.district=district(p.address); }
    }
  });
}
function smartAddPick(key){
  syncSmart();
  if(smartCfg.picks.some(p=>p.key===key)){ toast('已在名單中'); return; }
  const item=smartPool().find(x=>x.key===key);
  if(!item){ toast('找不到此客戶'); return; }
  smartCfg.picks.push(Object.assign({}, item, {dwell:SMART_DWELL, fixed:''}));
  renderRoute();
}
function smartAddAll(){
  syncSmart();
  const pool=smartPool(); let n=0;
  pool.slice(0,40).forEach(item=>{ if(!smartCfg.picks.some(p=>p.key===item.key)){ smartCfg.picks.push(Object.assign({}, item, {dwell:SMART_DWELL, fixed:''})); n++; } });
  toast(n?`已加入 ${n} 家`:'這些客戶都已在名單中'); renderRoute();
}
function smartLocate(fieldId){
  syncSmart();
  getGeo(coord=>{
    const el=$('#'+fieldId); if(el) el.value=coord;
    if(fieldId==='sm-startloc') smartCfg.startLoc=coord; else if(fieldId==='sm-endloc') smartCfg.endLoc=coord; else if(fieldId==='sm-lunchloc') smartCfg.lunchLoc=coord;
    toast('已帶入目前位置座標');
  });
}
// 開 Google 地圖找地點（用現有文字/座標當搜尋起點）
function smartMapPick(fieldId){
  syncSmart();
  const el=$('#'+fieldId); const q=(el&&el.value.trim())||'';
  const gm=q?smartLatLng(q):null;
  const url=gm ? `https://www.google.com/maps/search/?api=1&query=${gm[0]},${gm[1]}`
              : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q||'附近 餐廳')}`;
  window.open(url,'_blank');
  toast('在地圖找到位置後，複製座標或連結貼回欄位');
}
// 貼上 Google 地圖網址時自動轉成精準座標
function smartNormLoc(el){
  if(!el) return;
  const gm=parseGmaps(el.value);
  if(gm){ el.value=gm[0].toFixed(6)+','+gm[1].toFixed(6); toast('已從地圖網址取得座標'); }
  syncSmart();
}
function smartAddCustom(){
  syncSmart();
  smartCfg.picks.push({key:'x'+Date.now(), kind:'custom', name:'其他行程', address:'', district:'', channel:'其他', organic:'', grade:'', status:'', dwell:30, fixed:''});
  renderRoute();
}
function smartLocateCustom(key){
  syncSmart();
  getGeo(coord=>{
    const p=smartCfg.picks.find(x=>x.key===key); if(p){ p.address=coord; renderRoute(); toast('已帶入目前位置座標'); }
  });
}
function smartRemovePick(key){ syncSmart(); smartCfg.picks=smartCfg.picks.filter(p=>p.key!==key); renderRoute(); }
function smartClearPicks(){ smartCfg.picks=[]; smartCfg._last=''; renderRoute(); }
function smartTogglePool(){ syncSmart(); smartCfg._poolOpen=smartCfg._poolOpen?0:1; renderRoute(); }
function renderSmartRoute(){
  const regs=regionsSorted();
  if(!smartCfg._inited){ const tn=regs.find(r=>normR(r).includes('臺南')); smartCfg.f.regions = tn?[tn]:[]; smartCfg._inited=1; }
  const f=smartCfg.f;
  let h=`<div class="info">設好出發/回家地點與時間，用下方條件把要拜訪的客戶加入名單，再按「🧠 智慧安排」。系統會依位置排出最順的前後順序、穿插你已約好的客戶與中午休息。全程本機計算、不外傳。</div>`;
  // 出發 / 回家
  h+=`<div class="card"><div class="sec-title" style="margin-top:0"><span class="bar"></span>出發 / 回家</div>`;
  h+=`<div class="field"><label>🏁 出發位置 <span style="color:var(--red);font-weight:700">必填</span></label><div style="display:flex;gap:6px"><input id="sm-startloc" style="flex:1;min-width:0" value="${esc(smartCfg.startLoc)}" placeholder="例如 台南市東區自家地址"><button type="button" class="btn btn-out" style="white-space:nowrap;padding:0 12px" onclick="smartLocate('sm-startloc')">📍 定位</button></div></div>`;
  h+=`<div class="field"><label>🏠 回家位置（留空＝同出發）</label><div style="display:flex;gap:6px"><input id="sm-endloc" style="flex:1;min-width:0" value="${esc(smartCfg.endLoc)}" placeholder="留空則回到出發位置"><button type="button" class="btn btn-out" style="white-space:nowrap;padding:0 12px" onclick="smartLocate('sm-endloc')">📍 定位</button></div></div>`;
  h+=`<div class="field"><label>出發時間（回家時間排完路線會自動估算）</label><input type="time" id="sm-start" value="${smartCfg.startTime}"></div>`;
  h+=`<div class="field-2"><div class="field"><label>中午休息起</label><input type="time" id="sm-lunch1" value="${smartCfg.lunchStart}"></div>
      <div class="field"><label>中午休息迄</label><input type="time" id="sm-lunch2" value="${smartCfg.lunchEnd}"></div></div>`;
  h+=`<div class="field"><label>🍱 中午休息地點（可空，填了會算進前後車程）</label><div style="display:flex;gap:6px"><input id="sm-lunchloc" style="flex:1;min-width:0" value="${esc(smartCfg.lunchLoc)}" placeholder="例如 某餐廳地址，或貼地圖座標/網址" onchange="smartNormLoc(this)"><button type="button" class="btn btn-out" style="white-space:nowrap;padding:0 12px" onclick="smartLocate('sm-lunchloc')">📍 定位</button></div>
    <button type="button" class="btn btn-out" style="width:100%;margin-top:6px;font-size:12.5px" onclick="smartMapPick('sm-lunchloc')">🗺️ 用 Google 地圖選地點</button>
    <div class="hint" style="color:var(--muted);font-size:10.5px;margin-top:4px;line-height:1.6">在地圖上<b>長按</b>你要的位置會掉一根針，下方/搜尋列會出現座標 → 複製貼回上面欄位最準；也可在店家頁按「分享→複製連結」貼回來。</div></div>`;
  h+=`</div>`;
  // 篩選
  const orgOpts=[['','有機/非有機'],['org','🌱 有機'],['non','非有機']];
  h+=`<div class="card"><div class="sec-title" style="margin-top:0"><span class="bar"></span>篩選客戶</div>`;
  h+=`<div class="field-2">
      <div class="field"><label>客戶來源</label><select id="sm-src" onchange="syncSmart();renderRoute()">
        <option value="" ${f.src===''?'selected':''}>全部</option>
        <option value="cust" ${f.src==='cust'?'selected':''}>既有客戶</option>
        <option value="prosp" ${f.src==='prosp'?'selected':''}>目標客戶</option></select></div>
      <div class="field"><label>有機/非有機</label><select id="sm-organic" onchange="syncSmart();renderRoute()">${orgOpts.map(([k,l])=>`<option value="${k}" ${f.organic===k?'selected':''}>${l}</option>`).join('')}</select></div></div>`;
  h+=`<div class="field-2">
      <div class="field"><label>通路</label><select id="sm-channel" onchange="syncSmart();renderRoute()"><option value="">全部通路</option>${ROUTE_CHANS.map(c=>`<option value="${c}" ${f.channel===c?'selected':''}>${c}</option>`).join('')}</select></div>
      <div class="field"><label>等級</label><select id="sm-grade" onchange="syncSmart();renderRoute()"><option value="">全部等級</option>${GRADES.map(g=>`<option value="${g}" ${f.grade===g?'selected':''}>${g}・${GRADE_LABEL[g]}</option>`).join('')}<option value="none" ${f.grade==='none'?'selected':''}>未分級</option></select></div></div>`;
  h+=`<div class="field"><label>面積≥(公頃)</label><input id="sm-area" type="number" inputmode="decimal" value="${esc(f.area)}" placeholder="不限" oninput="smartCfg.f.area=this.value"></div>`;
  h+=`<div class="field"><label>地區（可複選，不選＝全部）</label>${regionMultiHTML(f.regions,'toggleSmartRegion')}</div>`;
  const pool=smartPool();
  const pickedKeys=new Set(smartCfg.picks.map(p=>p.key));
  h+=`<div class="btn-row" style="flex-wrap:wrap;gap:8px">
      <button class="btn btn-out" onclick="smartTogglePool()">${smartCfg._poolOpen?'▲ 收合符合清單':`🔍 顯示符合清單（${pool.length}）`}</button>
      <button class="btn btn-pri" onclick="smartAddAll()">＋ 全部加入${pool.length>40?'（前40）':''}</button></div>`;
  if(smartCfg._poolOpen){
    if(!pool.length){ h+=`<div class="card empty" style="padding:14px">沒有符合條件的客戶，放寬篩選再試。</div>`; }
    else{
      h+=`<div class="card" style="padding:4px 14px;max-height:340px;overflow:auto">`;
      pool.slice(0,80).forEach(x=>{
        const added=pickedKeys.has(x.key);
        h+=`<div class="item" style="cursor:default">
          <div class="body"><div class="nm">${esc(x.name)}</div>
            <div class="sub">${esc([x.district,x.address].filter(Boolean).join(' · '))}</div>
            <div class="tagline" style="margin-top:4px"><span class="badge b-${x.channel}">${esc(x.channel)}</span>${x.grade?` <span class="badge grade-${x.grade}">${x.grade}</span>`:''}${x.status==='cold'?' <span class="badge">陌生</span>':''}${x.organic==='org'?' 🌱':''}${x.area!=null?` <span class="badge">${x.area.toFixed(1)}ha</span>`:''}</div></div>
          <div class="meta">${added?'<span style="color:var(--muted)">已加入</span>':`<button class="btn btn-out" style="padding:4px 10px" onclick="smartAddPick('${x.key}')">＋ 加入</button>`}</div>
        </div>`;
      });
      if(pool.length>80) h+=`<div class="tagline" style="padding:8px 2px">符合 ${pool.length} 家，僅顯示前 80，請縮小篩選或直接「全部加入」。</div>`;
      h+=`</div>`;
    }
  }
  h+=`</div>`;
  // 已選名單
  h+=`<div class="sec-title"><span class="bar"></span>拜訪名單（${smartCfg.picks.length}）${smartCfg.picks.length?` <button class="rule-del" style="float:right" onclick="smartClearPicks()">✕ 全部清除</button>`:''}</div>`;
  if(!smartCfg.picks.length){
    h+=`<div class="card empty" style="padding:16px">尚未加入行程。用上面的篩選找到客戶後按「＋ 加入」。<br>也可按下方「＋ 新增其他行程」插入非客戶事項（例如 10:00 到某地址加油／開會／取貨）。<br>有約定時間者填「約定到達」，系統會固定排在該時段、其餘排在前後。</div>`;
  }else{
    h+=`<div class="card" style="padding:8px 12px">`;
    smartCfg.picks.forEach((p,i)=>{
      if(p.kind==='custom'){
        h+=`<div class="pk-row" data-k="${p.key}" style="padding:8px 0;border-bottom:1px solid var(--line);background:var(--amber-l);border-radius:8px;margin:2px 0;padding-left:8px;padding-right:8px">
          <div style="display:flex;align-items:center;gap:8px">
            <div class="avatar" style="background:#7a6a3a;width:26px;height:26px;font-size:13px">📍</div>
            <div style="flex:1;min-width:0"><div class="nm" style="font-size:13px;color:var(--amber)">其他行程（非客戶）</div></div>
            <button class="rule-del" onclick="smartRemovePick('${p.key}')">✕</button></div>
          <div class="field" style="margin:6px 0 0"><label style="font-size:11px">做什麼事</label><input class="pk-name" value="${esc(p.name||'')}" placeholder="例如 加油 / 開會 / 取貨"></div>
          <div class="field" style="margin:6px 0 0"><label style="font-size:11px">地點 / 地址</label><div style="display:flex;gap:6px"><input class="pk-addr" style="flex:1;min-width:0" value="${esc(p.address||'')}" placeholder="地址或座標（可空）"><button type="button" class="btn btn-out" style="white-space:nowrap;padding:0 10px" onclick="smartLocateCustom('${p.key}')">📍</button></div></div>
          <div class="field-2" style="margin-top:6px">
            <div class="field" style="margin:0"><label style="font-size:11px">預計時間(分)</label><input class="pk-dwell" type="number" min="5" step="5" value="${p.dwell||30}"></div>
            <div class="field" style="margin:0"><label style="font-size:11px">約定到達(可空)</label><input class="pk-fixed" type="time" value="${p.fixed||''}"></div></div>
        </div>`;
      }else{
        h+=`<div class="pk-row" data-k="${p.key}" style="padding:8px 0;border-bottom:1px solid var(--line)">
          <div style="display:flex;align-items:center;gap:8px">
            <div class="avatar" style="background:${colorFor(p.name)};width:26px;height:26px;font-size:13px">${i+1}</div>
            <div style="flex:1;min-width:0"><div class="nm" style="font-size:14px">${esc(p.name)}</div>
              <div class="sub" style="font-size:11.5px">${esc([p.district,p.channel].filter(Boolean).join(' · '))}${p.organic==='org'?' 🌱':''}</div></div>
            <button class="rule-del" onclick="smartRemovePick('${p.key}')">✕</button></div>
          <div class="field-2" style="margin-top:6px">
            <div class="field" style="margin:0"><label style="font-size:11px">預計拜訪(分)</label><input class="pk-dwell" type="number" min="5" step="5" value="${p.dwell||SMART_DWELL}"></div>
            <div class="field" style="margin:0"><label style="font-size:11px">約定到達(可空)</label><input class="pk-fixed" type="time" value="${p.fixed||''}"></div></div>
        </div>`;
      }
    });
    h+=`</div>`;
  }
  h+=`<div class="btn-row" style="gap:8px"><button class="btn btn-out" onclick="smartAddCustom()">＋ 新增其他行程</button>${smartCfg.picks.length?`<button class="btn btn-pri" onclick="smartPlan()">🧠 智慧安排路線</button>`:''}</div>`;
  h+=`<div id="smart-result">${smartCfg._last||''}</div>`;
  $('#route-body').innerHTML=h;
}
function smartPlan(){
  syncSmart();
  const picks=smartCfg.picks;
  const resEl=()=>$('#smart-result');
  if(!smartCfg.startLoc){ toast('請先填出發位置（或按 📍 定位）'); const el=$('#sm-startloc'); if(el){ el.scrollIntoView({behavior:'smooth',block:'center'}); setTimeout(()=>el.focus(),300); } return; }
  if(!picks.length){ toast('請先把客戶加入名單'); return; }
  const toMin=t=>{const[a,b]=(t||'').split(':').map(Number);return (a||0)*60+(b||0);};
  const fmt=m=>`${String(Math.floor(m/60)).padStart(2,'0')}:${String(Math.round(((m%60)+60)%60)).padStart(2,'0')}`;
  const s=toMin(smartCfg.startTime), e=toMin(smartCfg.endTime);
  const ls=toMin(smartCfg.lunchStart), le=toMin(smartCfg.lunchEnd);
  const startLoc=smartCfg.startLoc||(smartCfg.f.regions&&smartCfg.f.regions[0])||'';
  const endLoc=smartCfg.endLoc||startLoc;
  const startLL=smartLatLng(startLoc), endLL=smartLatLng(endLoc);
  const dwellOf=p=>Math.max(5,p.dwell||SMART_DWELL);
  const lunchLoc=smartCfg.lunchLoc, lunchDur=Math.max(0,le-ls);

  // 依目前可用的車程資料（離線估算 or 已載入的 OSRM 實際路網）建立行程
  function buildPlan(){
    // 自由客戶：最近鄰 + 2-opt 就近排序（取代舊的一維索引，消除來回繞路）
    const free=optimizeFreeOrder(picks.filter(p=>!p.fixed).map(p=>Object.assign({},p,{_ll:smartLatLng(p.address)})), startLL, endLL);
    const fixed=picks.filter(p=>p.fixed).map(p=>Object.assign({},p,{_at:toMin(p.fixed)})).sort((a,b)=>a._at-b._at);
    const result=[]; let lunchDone=false, prevAddr=startLoc, t=s, lateFix=false;
    const hasPrev=()=>!!(result.length||startLoc);
    const insertLunchBefore=(stopAddr)=>{
      if(lunchDone) return;
      const naive=t + (hasPrev()?smartTravel(prevAddr,stopAddr):0);
      if(naive < ls) return;
      let larr = lunchLoc ? t + (hasPrev()?smartTravel(prevAddr,lunchLoc):0) : t;
      larr=Math.max(larr,ls);
      result.push({lunch:true,arrive:fmt(larr),leave:fmt(larr+lunchDur),address:lunchLoc||''});
      t=larr+lunchDur; if(lunchLoc) prevAddr=lunchLoc;
      lunchDone=true;
    };
    let fi=0, ui=0;
    while(ui<free.length || fi<fixed.length){
      const nextFx = fi<fixed.length ? fixed[fi] : null;
      let useFixed=false;
      if(nextFx){
        if(ui>=free.length) useFixed=true;
        else if(nextFx._at <= t + smartTravel(prevAddr, nextFx.address)) useFixed=true;
        else {
          const fr=free[ui];
          const afterFree = t + (hasPrev()?smartTravel(prevAddr,fr.address):0) + dwellOf(fr) + smartTravel(fr.address, nextFx.address);
          if(afterFree > nextFx._at) useFixed=true;
        }
      }
      if(useFixed){
        const fx=fixed[fi++];
        insertLunchBefore(fx.address);
        let arr=Math.max(t + (hasPrev()?smartTravel(prevAddr,fx.address):0), fx._at);
        if(arr>fx._at) lateFix=true;
        result.push(Object.assign({},fx,{arrive:fmt(arr),leave:fmt(arr+dwellOf(fx)),_dur:dwellOf(fx),fixedMark:true}));
        t=arr+dwellOf(fx); prevAddr=fx.address;
      }else{
        const p=free[ui++];
        insertLunchBefore(p.address);
        let arr=t + (hasPrev()?smartTravel(prevAddr,p.address):0);
        result.push(Object.assign({},p,{arrive:fmt(arr),leave:fmt(arr+dwellOf(p)),_dur:dwellOf(p)}));
        t=arr+dwellOf(p); prevAddr=p.address;
      }
    }
    if(!lunchDone && ls>=s && ls<=e){
      let larr = lunchLoc ? t + (hasPrev()?smartTravel(prevAddr,lunchLoc):0) : Math.max(t,ls);
      larr=Math.max(larr,ls);
      result.push({lunch:true,arrive:fmt(larr),leave:fmt(larr+lunchDur),address:lunchLoc||''});
      t=larr+lunchDur; if(lunchLoc) prevAddr=lunchLoc;
    }
    const backTravel=smartTravel(prevAddr,endLoc);
    return {result, home:t+backTravel, lateFix};
  }

  function renderPlan(online){
  const plan=buildPlan();
  const result=plan.result, home=plan.home, lateFix=plan.lateFix;
  const stops=result.filter(x=>!x.lunch);
  let warn='';
  if(home>e) warn=`預估約 ${fmt(home)} 才到家，行程偏長。可減少家數、縮短停留或提早出發。`;
  else if(lateFix) warn=`部分約定客戶因前段時間排不下而略有延後，請現場彈性調整。`;

  let h=`<div class="sec-title"><span class="bar"></span>智慧安排結果（${stops.length} 家）`;
  h+=online ? ` <span class="badge" style="background:#2f5d34;color:#dff0e0;float:right">✅ 線上路網校正</span>` : ` <span class="badge" style="background:#5a4a2a;color:#f0e6cf;float:right">離線估算</span>`;
  h+=`</div>`;
  if(warn) h+=`<div class="info" style="background:var(--amber-l);color:var(--amber)">⚠️ ${esc(warn)}</div>`;
  h+=`<div class="card">`;
  h+=drow('出發', `${esc(startLoc||'(未填)')}　${smartCfg.startTime}`);
  h+=drow('預估回家', `🏁 ${fmt(home)} 到家　${esc(endLoc||'(同出發)')}`);
  h+=drow('中午休息', `${smartCfg.lunchStart}–${smartCfg.lunchEnd}${smartCfg.lunchLoc?'　@ '+esc(smartCfg.lunchLoc):''}`);
  h+=`</div>`;
  h+=`<div class="card" style="padding:4px 14px">`;
  let idx=0;
  result.forEach(x=>{
    if(x.lunch){ h+=`<div class="item" style="background:#f3efe2">
      <div class="avatar" style="background:#b08948">🍱</div>
      <div class="body">
        <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
          <span style="font-size:22px;font-weight:800;line-height:1.05;letter-spacing:.5px">${x.arrive}</span>
          <span style="font-size:12.5px;color:var(--muted)">中午休息</span></div>
        <div style="font-size:11.5px;color:var(--muted);margin-top:1px">時段 ${x.arrive}–${x.leave}</div>
        <div class="nm" style="margin-top:4px">🍱 中午休息</div>
        ${x.address?`<div class="sub">${esc(x.address)}</div>`:''}</div>
      <div class="meta">${x.address?`<a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(x.address)}" target="_blank" onclick="event.stopPropagation()">導航</a>`:''}</div>
    </div>`; return; }
    idx++;
    const tel=(x.phone||'').split('/')[0].replace(/[^\d+]/g,'');
    const isCustom=x.kind==='custom';
    const onclick=isCustom?'':(x.kind==='cust'?`viewCustomer('${x.id}')`:`viewProspect('${x.id}')`);
    const dwLabel=isCustom?'預計':'抵達・拜訪';
    h+=`<div class="item"${onclick?` onclick="${onclick}"`:''} style="${isCustom?'background:var(--amber-l)':''}">
      <div class="avatar" style="background:${isCustom?'#7a6a3a':colorFor(x.name)}">${idx}</div>
      <div class="body">
        <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
          <span style="font-size:22px;font-weight:800;line-height:1.05;letter-spacing:.5px">${x.arrive}</span>
          <span style="font-size:12.5px;color:var(--muted)">${dwLabel} ${x._dur} 分</span></div>
        <div style="font-size:11.5px;color:var(--muted);margin-top:1px">時段 ${x.arrive}–${x.leave}</div>
        <div class="nm" style="margin-top:4px">${isCustom?'📍 ':''}${esc(x.name)}${x.fixedMark?' <span class="badge pill-due">📌 約定</span>':''}</div>
        ${(x.district||x.address)?`<div class="sub">${esc([x.district,x.address].filter(Boolean).join(' · '))}</div>`:''}
        ${isCustom?`<div class="tagline" style="margin-top:4px"><span class="badge">其他行程</span></div>`:`<div class="tagline" style="margin-top:4px"><span class="badge b-${x.channel}">${esc(x.channel)}</span>${x.grade?` <span class="badge grade-${x.grade}">${x.grade}</span>`:''}${x.status==='cold'?' <span class="badge">陌生</span>':''}${x.organic==='org'?' 🌱':''}</div>`}</div>
      <div class="meta">${x.address?`<a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(x.address)}" target="_blank" onclick="event.stopPropagation()">導航</a>`:''}${(!isCustom&&tel.length>=6)?`<br><a href="tel:${tel}" onclick="event.stopPropagation()">電話</a>`:''}${onclick?`<br><a href="javascript:void(0)" onclick="event.stopPropagation();${onclick}">📋 拜訪管理</a>`:''}${(x.kind==='prosp'&&!custByProspect(x.id))?`<br><a href="javascript:void(0)" style="color:var(--amber)" onclick="event.stopPropagation();convertToCustomer('${x.id}')">⭐ 轉既有</a>`:''}</div>
    </div>`;
  });
  h+=`<div class="item" style="background:#eef1e6">
      <div class="avatar" style="background:#4c5a2e">🏁</div>
      <div class="body">
        <div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">
          <span style="font-size:22px;font-weight:800;line-height:1.05;letter-spacing:.5px">${fmt(home)}</span>
          <span style="font-size:12.5px;color:var(--muted)">預估回家時間</span></div>
        <div class="nm" style="margin-top:4px">🏁 回到${endLoc&&endLoc!==startLoc?'回家點':'出發地'}</div>
        ${endLoc?`<div class="sub">${esc(endLoc)}</div>`:''}</div>
      <div class="meta">${endLoc?`<a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(endLoc)}" target="_blank" onclick="event.stopPropagation()">導航</a>`:''}</div>
    </div>`;
  h+=`</div>`;
  const mapStops=stops.filter(x=>x.address);
  if(mapStops.length){
    const wp=mapStops.map(x=>encodeURIComponent(x.address)).join('%7C');
    const url=`https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(startLoc||mapStops[0].address)}&destination=${encodeURIComponent(endLoc||startLoc||mapStops[mapStops.length-1].address)}&travelmode=driving&waypoints=${wp}`;
    h+=`<div class="btn-row"><a class="btn btn-pri" style="text-decoration:none" href="${url}" target="_blank">🚗 用 Google 地圖開啟整條路線</a></div>`;
  }
  // 今日拜訪客戶清單（可一鍵記錄成拜訪管理，流入週報；目標客戶會自動建/補到「我的客戶」）
  window._routeToday = stops.filter(x=>x.kind==='cust'||x.kind==='prosp').map(x=>({kind:x.kind,id:x.id,name:x.name}));
  if(window._routeToday.length){
    h+=`<div class="btn-row" style="margin-top:4px"><button class="btn btn-out" style="border-color:#4c5a2e;color:#3a4622" onclick="routeFinishToday()">✅ 完成今日拜訪（記錄 ${window._routeToday.length} 家並寫入週報）</button></div>`;
    h+=`<div class="tagline" style="margin:2px 2px 0">按下後，今日這 ${window._routeToday.length} 家會各自新增一筆拜訪紀錄（你可逐家補內容）；目標客戶會自動寫進「我的客戶」卡片。完成後可到「拜訪週報」一鍵產生主管週報。</div>`;
  }
  h+=`<div class="tagline" style="margin:8px 2px 0">順序用「最近鄰＋2-opt」就近最佳化（自動消除來回繞路），並把你填的約定到達時間固定在該時段、其餘客戶排在前後。${online?'<b>站間車程已用線上 OSRM 實際路網校正</b>（只送鄉鎮中心座標，不含任何客戶地址/個資）。':'站間車程為離線估算（鄉鎮中心點直線距離×1.3 倍路程、依距離抓 24–88 km/h）；連上網路會自動用實際路網校正。'}實際會因路況、山路而異，僅供參考；點「用 Google 地圖開啟整條路線」可看實際時間。填了中午休息地點，會把上午最後一站→休息地點→下午第一站的車程一起算進去。</div>`;
  smartCfg._last=h; resEl().innerHTML=h;
  }
  renderPlan(false);
  resEl().scrollIntoView({behavior:'smooth',block:'start'});
  // 線上 OSRM 實際路網校正（可選；只送鄉鎮中心座標，失敗則維持離線估算）
  if(navigator.onLine!==false){
    const lls=[startLL,endLL,smartLatLng(lunchLoc)].concat(picks.map(p=>smartLatLng(p.address))).filter(Boolean);
    osrmFillTable(lls).then(ok=>{ if(ok && $('#smart-result')) renderPlan(true); }).catch(()=>{});
  }
}

// ========== 完成今日拜訪：把今日路線上的客戶一次記成拜訪、寫入週報 ==========
// 不開表單、直接把目標客戶補進「我的客戶」（個資欄位留空，可日後補）
function convertProspectSilent(id, interItem){
  const p=SEED.find(x=>x.id===id); if(!p) return null;
  const exist=custByProspect(id); if(exist) return exist;
  const o=overlay[id]||{};
  const typeMap={'農會':'農會','合作社':'合作社','肥料行':'經銷商','有機農戶':'直接農民'};
  const c={ id:'C'+Date.now()+Math.random().toString(36).slice(2,5), name:p.name, type:typeMap[p.category]||'其他',
    phone:p.phone||'', address:p.address||'', contact:p.contact||'',
    idno:'', birth:'', taxid:'', terms:'', checkPeriod:'', truck:'', deliveryTime:'',
    currentFert:p.brand||'', price:p.price||'', conditions:'', grade:(o.grade||''),
    freq:o.freq||null, last:o.last||'', next:o.next||'', notes:p.notes||'',
    inter:o.inter?[...o.inter]:[], fromProspect:id };
  if(interItem){ c.inter.push(interItem); c.last=interItem.date; if(c.freq)c.next=addDays(interItem.date,c.freq); }
  customers.push(c); return c;
}
function routeFinishToday(){
  const list=window._routeToday||[]; if(!list.length){ toast('沒有可記錄的客戶'); return; }
  let h=`<div class="info">把今日路線上的 ${list.length} 家一次記成「已拜訪」，會寫入互動紀錄並流入「拜訪週報」。<b>目標客戶會自動進入「目標客戶 ▸ ✅ 已拜訪」列表</b>；談得有意願時，再到該客戶頁或路線上按「⭐ 轉既有」轉成你的客戶。</div>`;
  h+=`<div class="field"><label>拜訪日期</label><input type="date" id="rf-date" value="${todayStr()}"></div>`;
  h+=`<div class="card" style="padding:6px 12px">`;
  list.forEach((x,i)=>{
    h+=`<div style="padding:7px 0;border-bottom:1px solid var(--line)">
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
        <input type="checkbox" class="rf-on" data-i="${i}" checked>
        <span class="nm" style="font-size:14px">${i+1}. ${esc(x.name)}${x.kind==='prosp'?' <span class="badge">目標</span>':''}</span></label>
      <input class="rf-note" data-i="${i}" placeholder="這家談了什麼／結果（可空）" style="margin-top:5px;width:100%;box-sizing:border-box">
    </div>`;
  });
  h+=`</div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" id="rf-save">✅ 確認記錄</button><button class="btn btn-gray" onclick="closeModal()">取消</button></div>`;
  openModal('完成今日拜訪', h);
  $('#rf-save').onclick=()=>{
    const date=$('#rf-date').value||todayStr();
    const ons=[...document.querySelectorAll('.rf-on')];
    const notes=[...document.querySelectorAll('.rf-note')];
    let n=0, visP=0;
    ons.forEach((cb,idx)=>{
      if(!cb.checked) return;
      const x=list[idx]; const content=(notes[idx]&&notes[idx].value.trim())||'完成拜訪';
      const it={date,type:'拜訪',content};
      if(x.kind==='cust'){
        const c=findCust(x.id); if(!c)return; c.inter=c.inter||[]; c.inter.push(it); c.last=date; if(c.freq)c.next=addDays(date,c.freq); n++;
      }else{
        const ex=custByProspect(x.id);
        if(ex){ ex.inter=ex.inter||[]; ex.inter.push(it); ex.last=date; if(ex.freq)ex.next=addDays(date,ex.freq); }
        else { const o=overlay[x.id]||{}; o.inter=o.inter||[]; o.inter.push(it); o.last=date; if(o.freq)o.next=addDays(date,o.freq); overlay[x.id]=o; visP++; } // 記成已拜訪，留在目標客戶清單
        n++;
      }
    });
    saveCust(); saveOverlay();
    closeModal();
    toast(`已記錄 ${n} 家拜訪${visP?`，${visP} 家目標客戶已進入「已拜訪」清單`:''}`);
    go('report');
  };
}

// ========== 每週拜訪智慧排程 ==========
let weekCfg = { start:'', days:[1,2,3,4,5], maxPerDay:6, regions:[], mode:'all', _last:'' };
const WD_NAME = ['日','一','二','三','四','五','六'];
function thisMonday(){ const d=new Date(); const w=d.getDay(); d.setDate(d.getDate()+(w===0?-6:1-w)); return d.toISOString().slice(0,10); }
function gradeFreq(g){ return GRADE_FREQ[g]||null; }
function syncWeek(){
  const s=$('#w-start'); if(s)weekCfg.start=s.value||weekCfg.start;
  const m=$('#w-max'); if(m)weekCfg.maxPerDay=Math.max(1,Math.min(12,+m.value||6));
  // 區域改為多選晶片，由 toggleWeekRegion 直接維護 weekCfg.regions
  const md=$('#w-mode'); if(md)weekCfg.mode=md.value;
}
function toggleWeekDay(wd){ syncWeek(); const i=weekCfg.days.indexOf(wd); if(i<0)weekCfg.days.push(wd); else weekCfg.days.splice(i,1); renderRoute(); }
function renderWeekRoute(){
  const regs = regionsSorted();
  if(weekCfg._inited!==1){ const tn=regs.find(r=>normR(r).includes('臺南')); weekCfg.regions = tn?[tn]:[]; weekCfg._inited=1; }
  if(!weekCfg.start) weekCfg.start=thisMonday();
  let h=`<div class="info">系統自動收集「到期 / 逾期」要回訪的客戶與名單，加上依分級頻率該回訪的對象，按鄉鎮就近分配到本週各出訪日。全程本機計算、不外傳。</div>`;
  h+=`<div class="card">`;
  h+=`<div class="field"><label>本週起始日（週一）</label><input type="date" id="w-start" value="${weekCfg.start}"></div>`;
  h+=`<div class="field"><label>區域（可複選・限定責任區，不選＝全部）</label>${regionMultiHTML(weekCfg.regions,'toggleWeekRegion')}</div>`;
  h+=`<div class="field"><label>出訪日（可複選）</label><div class="wdays">${[1,2,3,4,5,6,0].map(wd=>`<button type="button" class="chip ${weekCfg.days.includes(wd)?'on':''}" onclick="toggleWeekDay(${wd})">週${WD_NAME[wd]}</button>`).join('')}</div></div>`;
  h+=`<div class="field-2"><div class="field"><label>每日最多家數</label><input type="number" id="w-max" min="1" max="12" value="${weekCfg.maxPerDay}"></div>
      <div class="field"><label>排程範圍</label><select id="w-mode"><option value="all" ${weekCfg.mode==='all'?'selected':''}>到期＋依分級建議(推薦)</option><option value="due" ${weekCfg.mode==='due'?'selected':''}>只排已設下次拜訪日</option></select></div></div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" onclick="planWeek()">📅 產生本週拜訪計畫</button></div>`;
  h+=`</div><div id="week-result">${weekCfg._last||''}</div>`;
  $('#route-body').innerHTML=h;
}
// 收集本週該拜訪的對象（客戶＋有排程/分級的名單）
function collectVisitTargets(regions, weekEnd, includeGrade){
  const regs = Array.isArray(regions) ? regions : (regions?[regions]:[]);
  const cores = regs.map(r=>normR(r).replace(/[縣市]$/,'')).filter(Boolean);
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
    if(cores.length && !cores.some(core=>normR(c.address||'').includes(core))) return;
    push({next:c.next,last:c.last}, {kind:'cust',id:c.id,name:c.name,channel:TYPE2CHAN[c.type]||c.type||'其他',status:'existing',grade:c.grade||'',address:c.address||'',phone:c.phone||'',district:district(c.address)});
  });
  SEED.forEach(p=>{
    const o=overlay[p.id]; if(!o) return;   // 名單沒有任何排程才不掃，避免 3547 筆全進來
    if(cores.length && !(regs.some(rg=>normR(p.region||'')===normR(rg)) || cores.some(core=>normR(p.address||'').includes(core)))) return;
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
  const targets=collectVisitTargets(weekCfg.regions,weekEnd,includeGrade);
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
      const origin=(weekCfg.regions&&weekCfg.regions[0])||'';
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
  if(!Array.isArray(routeCfg.regions)) routeCfg.regions=[];
  if(!routeCfg.regions.length){ const tn=regs.find(r=>normR(r).includes('臺南'))||regs[0]; if(tn)routeCfg.regions=[tn]; }
  if(!routeCfg.rules||!routeCfg.rules.length) routeCfg.rules=[{status:'',channel:'',grade:'',n:5}];
  let h=`<div class="info">可加多組條件(例如:陌生×肥料行 2 家 + 既有×農會 1 家),系統會分別挑選再合併排成一條順路路線。資料皆在本機計算。</div>`;
  h+=`<div class="card"><div class="field"><label>區域（可複選）</label>${regionMultiHTML(routeCfg.regions,'toggleRouteRegion')}</div></div>`;
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
  // 區域改為多選晶片，由 toggleRouteRegion 直接維護 routeCfg.regions
  if(!Array.isArray(routeCfg.regions)) routeCfg.regions=[];
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
  const regs=routeCfg.regions||[];
  const cores=regs.map(r=>normR(r).replace(/[縣市]$/,'')).filter(Boolean);
  const exIds=existingProspectIds();
  let pool=[];
  customers.forEach(c=>{ if(!c.address)return; if(!cores.length || cores.some(core=>normR(c.address).includes(core)))
    pool.push({kind:'cust',id:c.id,name:c.name,channel:TYPE2CHAN[c.type]||c.type,status:'existing',grade:c.grade||'',address:c.address,phone:c.phone,district:district(c.address),due:dueInfo(c)}); });
  SEED.forEach(p=>{ if(!p.address)return; if(!cores.length || regs.some(rg=>normR(p.region)===normR(rg)) || cores.some(core=>normR(p.address).includes(core)))
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
  if(!pick.length){ routeCfg._last=`<div class="card empty"><div class="big">📍</div>「${esc(regs.join('、')||'所選區域')}」找不到符合組合條件的對象。<br>放寬條件，或換個區域再試。</div>`; $('#route-result').innerHTML=routeCfg._last; return; }
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
  h+=drow('區域', esc(regs.join('、')||'全部'));
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
  const origin=routeCfg.home||regs[0]||'';
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

// ========== 即時競品價格 ==========
let compFilter = {q:'', region:''};
function renderCompetitors(){
  const regs = regionsSorted();
  let h = `<div class="info">🔒 蒐集各地競爭對手報價，方便比價與訂價。資料只存在本機、不外傳。</div>`;
  // 上網快查（本機無後端，改用瀏覽器開啟比價站即時查詢）
  h += `<div class="card"><div class="sec-title" style="margin-top:0"><span class="bar"></span>🔍 上網查競品價格</div>
    <div class="field"><label>搜尋關鍵字</label><input id="comp-kw" value="有機質肥料 粒狀 20kg" placeholder="例如 有機質肥料 粒狀 20kg"></div>
    <div class="btn-row" style="flex-wrap:wrap;gap:8px;margin-top:2px">
      <button class="btn btn-out" onclick="compWeb('feebee')">飛比比價</button>
      <button class="btn btn-out" onclick="compWeb('biggo')">BigGo</button>
      <button class="btn btn-out" onclick="compWeb('shopee')">蝦皮</button>
      <button class="btn btn-out" onclick="compWeb('momo')">momo</button>
      <button class="btn btn-out" onclick="compWeb('afa')">農糧署品牌價</button>
    </div>
    <div class="tagline" style="margin-top:7px">點按鈕用瀏覽器開啟即時比價結果；看到合適報價，按下方「新增競品報價」記下來。</div></div>`;
  h += `<div class="btn-row"><button class="btn btn-pri" onclick="editCompetitor(null,true)">➕ 新增競品報價</button></div>`;
  h += `<div class="search"><input id="csearch" placeholder="🔍 搜尋公司 / 產品 / 地區" value="${esc(compFilter.q)}" oninput="onCompSearch(this.value)"></div>`;
  h += `<div class="rowsel"><span class="rowsel-l">縣市</span><select class="regsel" onchange="compFilter.region=this.value;renderCompetitors()">
        <option value="">全部地區</option>${regs.map(r=>`<option ${compFilter.region===r?'selected':''}>${esc(r)}</option>`).join('')}</select></div>`;
  const q=compFilter.q.trim();
  const res = competitors.filter(c=>{
    if(compFilter.region && c.region!==compFilter.region) return false;
    if(q){ const blob=[c.company,c.product,c.item,c.region,c.town,c.note].join(''); if(!blob.includes(q)) return false; }
    return true;
  }).sort((a,b)=>(b.date||'').localeCompare(a.date||''));
  h += `<div class="count">共 ${res.length} 筆競品報價</div>`;
  if(!res.length){ h+=`<div class="card empty"><div class="big">🏷️</div>還沒有競品報價。<br>用上方「上網查」找價格，或按「新增競品報價」手動建立。</div>`; }
  else { h += res.map(compCard).join(''); }
  viewHTML(h);
  const inp=$('#csearch'); if(inp&&compFilter._focus){ inp.focus(); inp.setSelectionRange(inp.value.length,inp.value.length); compFilter._focus=false; }
}
function compCard(c){
  const loc=[c.region,c.town].filter(Boolean).join(' ');
  const spec=[c.form,c.weight?c.weight+'kg':''].filter(Boolean).join(' ');
  return `<div class="card" style="padding:12px 14px;margin-bottom:10px">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
      <div style="min-width:0"><div style="font-weight:700;font-size:15px">${esc(c.company||'競品')}</div>
        <div style="color:var(--muted);font-size:13px;margin-top:1px">${esc(c.product||'')}${c.item?`・${esc(c.item)}`:''}</div></div>
      <div style="text-align:right;flex:none"><div style="font-size:19px;font-weight:800;color:var(--red)">${c.price?'$'+esc(c.price):'—'}</div>
        <div style="font-size:11px;color:var(--muted)">${esc(c.freight||'')}</div></div></div>
    <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px">
      ${spec?`<span class="badge b-其他">${esc(spec)}</span>`:''}
      ${loc?`<span class="badge b-農會">📍 ${esc(loc)}</span>`:''}
      ${c.checkPeriod?`<span class="badge b-合作社">${esc(c.checkPeriod)}</span>`:''}
      ${c.date?`<span class="badge b-其他">${esc(c.date)}</span>`:''}</div>
    ${c.note?`<div class="tagline" style="margin-top:7px">📝 ${esc(c.note)}</div>`:''}
    <div class="btn-row" style="margin-top:9px;gap:8px">
      <button class="btn btn-out" onclick="editCompetitor('${c.id}')">✏️ 編輯</button>
      <button class="btn btn-out" style="color:var(--red);border-color:var(--red)" onclick="delCompetitor('${c.id}')">🗑️ 刪除</button></div></div>`;
}
function compWeb(site){
  const kw=(($('#comp-kw')||{}).value||'有機質肥料').trim(), e=encodeURIComponent(kw);
  const url={ feebee:`https://feebee.com.tw/s/${e}/`, biggo:`https://biggo.com.tw/s/${e}`,
    shopee:`https://shopee.tw/search?keyword=${e}`, momo:`https://www.momoshop.com.tw/search/searchShop.jsp?keyword=${e}`,
    afa:`https://www.afa.gov.tw/cht/index.php?code=list&flag=detail&ids=2212` }[site];
  if(url) window.open(url,'_blank');
}
function onCompSearch(v){ compFilter.q=v; compFilter._focus=true; renderCompetitors(); }
function editCompetitor(id, isNew){
  const c = isNew ? {id:'k'+Date.now(), date:todayStr(), form:'粒狀', freight:'含運'} : (competitors.find(x=>x.id===id)||{});
  const regs=regionsSorted();
  const sel=(arr,v)=>arr.map(x=>`<option ${x===v?'selected':''}>${x}</option>`).join('');
  let h='';
  h+=`<div class="field-2">
    <div class="field"><label>報價縣市</label><select id="k-region"><option value="">未設定</option>${regs.map(r=>`<option ${c.region===r?'selected':''}>${esc(r)}</option>`).join('')}</select></div>
    <div class="field"><label>鄉鎮區</label><input id="k-town" value="${esc(c.town||'')}" placeholder="例如 新化區"></div></div>`;
  h+=`<div class="field"><label>公司名稱</label><input id="k-company" value="${esc(c.company||'')}" placeholder="競品公司 / 品牌"></div>`;
  h+=`<div class="field"><label>產品名稱</label><input id="k-product" value="${esc(c.product||'')}" placeholder="競品產品名"></div>`;
  h+=`<div class="field"><label>料品目</label><input id="k-item" value="${esc(c.item||'')}" placeholder="例如 雜項堆肥(5-11)"></div>`;
  h+=`<div class="field-2">
    <div class="field"><label>性狀</label><select id="k-form">${sel(FORMS,c.form||'粒狀')}</select></div>
    <div class="field"><label>重量(kg)</label><input id="k-weight" type="number" inputmode="decimal" value="${esc(c.weight||'')}" placeholder="20"></div></div>`;
  h+=`<div class="field-2">
    <div class="field"><label>價格(元)</label><input id="k-price" type="number" inputmode="decimal" value="${esc(c.price||'')}" placeholder="一包單價"></div>
    <div class="field"><label>是否含運</label><select id="k-freight">${sel(FREIGHTS,c.freight||'含運')}</select></div></div>`;
  h+=checkPeriodHTML(c.checkPeriod||'');
  h+=`<div class="field"><label>報價日期</label><input type="date" id="k-date" value="${esc(c.date||todayStr())}"></div>`;
  h+=`<div class="field"><label>備註</label><textarea id="k-note" placeholder="來源、附帶條件、聯絡資訊…">${esc(c.note||'')}</textarea></div>`;
  h+=`<div class="btn-row"><button class="btn btn-pri" onclick="saveCompetitor('${c.id}',${isNew?'true':'false'})">💾 儲存</button></div>`;
  openModal(isNew?'新增競品報價':'編輯競品報價', h);
}
function saveCompetitor(id, isAdd){
  const g=i=>{const e=$('#'+i); return e?e.value.trim():'';};
  const obj={ id, region:$('#k-region').value, town:g('k-town'), company:g('k-company'), product:g('k-product'),
    item:g('k-item'), form:$('#k-form').value, weight:g('k-weight'), price:g('k-price'),
    freight:$('#k-freight').value, checkPeriod:readCheckPeriod(), date:g('k-date'), note:g('k-note') };
  if(!obj.company && !obj.product){ toast('至少要填公司或產品名稱'); return; }
  const i=competitors.findIndex(x=>x.id===id);
  if(i>=0) competitors[i]=obj; else competitors.unshift(obj);
  saveComp(); closeModal(); toast('已儲存競品報價'); renderCompetitors();
}
function delCompetitor(id){ if(!confirm('確定刪除這筆競品報價？')) return; competitors=competitors.filter(x=>x.id!==id); saveComp(); toast('已刪除'); renderCompetitors(); }

// ========== 拜訪週報（彙整本週拜訪紀錄；工作週＝週一～週五）==========
let reportWeekStart=''; // 該週週一（空字串＝本週）
function repMonday(){ return reportWeekStart||thisMonday(); }
function shiftReportWeek(n){ reportWeekStart=addDays(repMonday(),n*7); renderReport(); }
function resetReportWeek(){ reportWeekStart=''; renderReport(); }
// 蒐集某週（週一～週五）內，我的客戶＋目標名單的所有拜訪紀錄
function collectWeekVisits(){
  const mon=repMonday(), fri=addDays(mon,4);
  const inRange=d=>d&&d>=mon&&d<=fri;
  const out=[];
  customers.forEach(c=>{ (c.inter||[]).forEach(it=>{ if(inRange(it.date)) out.push({date:it.date,name:c.name,kind:'客戶',type:it.type||'拜訪',content:it.content||'',id:c.id,who:'cust'}); }); });
  Object.keys(overlay).forEach(pid=>{ const o=overlay[pid]; if(!o||!o.inter) return; if(custByProspect(pid)) return; /* 已轉為我的客戶→紀錄改記在客戶卡片，避免重複 */ const p=SEED.find(x=>x.id===pid); const nm=p?p.name:'(名單)'; o.inter.forEach(it=>{ if(inRange(it.date)) out.push({date:it.date,name:nm,kind:'名單',type:it.type||'拜訪',content:it.content||'',id:pid,who:'prospect'}); }); });
  out.sort((a,b)=>a.date.localeCompare(b.date));
  return out;
}
// 彙整本週拜訪 + 結構分析 + 跟進 + 下週回訪（純本機規則運算）
function weekAnalysis(){
  const mon=repMonday(), fri=addDays(mon,4);
  const visits=collectWeekVisits();
  const metaOf=v=>{
    if(v.who==='cust'){ const c=findCust(v.id)||{}; return {chan:TYPE2CHAN[c.type]||c.type||'其他', county:cityOf(c.address)||custCity(c)||'未分區', region:regionFull(c.address), grade:c.grade||'', conv:!!c.fromProspect}; }
    const p=SEED.find(x=>x.id===v.id)||{}; const o=overlay[v.id]||{}; return {chan:p.category||'其他', county:cityOf(p.address)||normR(p.region||'')||'未分區', region:regionFull(p.address), grade:o.grade||'', conv:false};
  };
  visits.forEach(v=>{ v.m=metaOf(v); });
  const names=new Set(visits.map(v=>v.name));
  const custVisits=visits.filter(v=>v.who==='cust'), prospVisits=visits.filter(v=>v.who==='prospect');
  const byChan={}, byCounty={}, byGrade={};
  visits.forEach(v=>{ byChan[v.m.chan]=(byChan[v.m.chan]||0)+1; byCounty[v.m.county]=(byCounty[v.m.county]||0)+1; if(v.m.grade)byGrade[v.m.grade]=(byGrade[v.m.grade]||0)+1; });
  const newCust=[], seenNew=new Set();
  custVisits.forEach(v=>{ if(v.m.conv && !seenNew.has(v.id)){ seenNew.add(v.id); newCust.push(v.name); } });
  // 待跟進（未完成）
  const follows=[];
  customers.forEach(c=>{(c.follow||[]).forEach(f=>{ if(!f.done) follows.push({name:c.name,text:f.text,due:f.due||''}); });});
  Object.keys(overlay).forEach(pid=>{ if(custByProspect(pid))return; const o=overlay[pid]; const p=SEED.find(x=>x.id===pid); ((o&&o.follow)||[]).forEach(f=>{ if(!f.done) follows.push({name:p?p.name:'(名單)',text:f.text,due:f.due||''}); });});
  follows.sort((a,b)=>(a.due||'9999').localeCompare(b.due||'9999'));
  // 下週應回訪（next 落在下週一～下週五）
  const nwm=addDays(mon,7), nwf=addDays(mon,11), nextWk=[];
  customers.forEach(c=>{ if(c.next&&c.next>=nwm&&c.next<=nwf) nextWk.push({name:c.name,due:c.next,grade:c.grade||''}); });
  Object.keys(overlay).forEach(pid=>{ if(custByProspect(pid))return; const o=overlay[pid]; const p=SEED.find(x=>x.id===pid); if(o&&o.next&&o.next>=nwm&&o.next<=nwf) nextWk.push({name:p?p.name:'(名單)',due:o.next,grade:(o&&o.grade)||''}); });
  nextWk.sort((a,b)=>a.due.localeCompare(b.due));
  return {mon,fri,visits,names,custVisits,prospVisits,byChan,byCounty,byGrade,newCust,follows,nextWk};
}
function sortedKeys(obj){ return Object.keys(obj).sort((x,y)=>obj[y]-obj[x]); }
function reportText(){
  const a=weekAnalysis();
  let t=`【業務週報】${a.mon} ～ ${a.fri}\n業務員：莊政遠（碩成肥料）\n════════════════\n`;
  if(!a.visits.length){ return t+'\n本週尚無拜訪紀錄。\n建議到「拜訪路線」安排行程，當日跑完後按「完成今日拜訪」即可自動彙整成週報。\n'; }
  const custN=new Set(a.custVisits.map(v=>v.id)).size, prospN=new Set(a.prospVisits.map(v=>v.id)).size;
  t+=`\n一、本週執行摘要\n`;
  t+=`　本週共拜訪 ${a.visits.length} 次、接觸 ${a.names.size} 家（既有客戶 ${custN} 家、目標開發 ${prospN} 家）。\n`;
  if(a.newCust.length) t+=`　本週新轉入「我的客戶」${a.newCust.length} 家：${a.newCust.join('、')}。\n`;
  t+=`　足跡涵蓋 ${Object.keys(a.byCounty).length} 個縣市：${sortedKeys(a.byCounty).map(k=>`${k} ${a.byCounty[k]} 次`).join('、')}。\n`;
  t+=`\n二、拜訪結構分析\n`;
  t+=`　‧ 通路別：${sortedKeys(a.byChan).map(k=>`${k} ${a.byChan[k]}`).join('、')}\n`;
  if(Object.keys(a.byGrade).length) t+=`　‧ 客戶分級：${sortedKeys(a.byGrade).map(k=>`${k}級 ${a.byGrade[k]}`).join('、')}\n`;
  t+=`\n三、每日行程紀要\n`;
  for(let i=0;i<5;i++){
    const d=addDays(a.mon,i); const dv=a.visits.filter(v=>v.date===d); if(!dv.length) continue;
    t+=`\n■ ${d.slice(5)}（週${WD_NAME[new Date(d).getDay()]}）　${dv.length} 家\n`;
    dv.forEach(v=>{ t+=`　・${v.name}（${[v.m.chan,v.m.region].filter(Boolean).join('・')}${v.m.grade?` ${v.m.grade}級`:''}）\n　　${v.content||'完成拜訪'}\n`; });
  }
  let sec=4;
  if(a.follows.length){ t+=`\n四、待跟進事項（${a.follows.length}）\n`; a.follows.slice(0,15).forEach(f=>{ t+=`　‧ ${f.name}：${f.text}${f.due?`（期限 ${f.due}）`:''}\n`; }); sec=5; }
  t+=`\n${sec===5?'五':'四'}、下週工作規劃\n`;
  if(a.nextWk.length){ t+=`　依拜訪頻率，下週應回訪 ${a.nextWk.length} 家：\n`; a.nextWk.slice(0,15).forEach(x=>{ t+=`　‧ ${x.due.slice(5)} ${x.name}${x.grade?` ${x.grade}級`:''}\n`; }); }
  else t+=`　下週無系統排定回訪，建議持續開發目標名單、深耕本週新接觸客戶。\n`;
  t+=`\n────────────────\n本報表由「客戶戰情室」依本機拜訪紀錄自動產生。\n`;
  return t;
}
function copyReport(){
  const t=reportText();
  if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(t).then(()=>toast('週報文字已複製，可貼到 LINE/記事本')).catch(()=>repFallbackCopy(t)); }
  else repFallbackCopy(t);
}
function repFallbackCopy(t){ const ta=document.createElement('textarea'); ta.value=t; ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta); ta.select(); try{ document.execCommand('copy'); toast('週報文字已複製'); }catch(e){ toast('複製失敗，請長按下方文字手動複製'); } document.body.removeChild(ta); }
function renderReport(){
  const a=weekAnalysis();
  const isThis=(repMonday()===thisMonday());
  let h=`<div class="info">📊 自動把本週（週一～週五）拜訪彙整成可給主管看的<b>業務週報</b>，含摘要、結構分析、每日紀要、跟進與下週規劃。資料只存本機。在「拜訪路線」按「完成今日拜訪」會自動寫進這裡。</div>`;
  h+=`<div class="seg"><button class="seg-b" onclick="shiftReportWeek(-1)">← 上一週</button>
      <button class="seg-b ${isThis?'on':''}" onclick="resetReportWeek()">本週</button>
      <button class="seg-b" onclick="shiftReportWeek(1)">下一週 →</button></div>`;
  h+=`<div class="count">${a.mon} ～ ${a.fri}　·　拜訪 ${a.visits.length} 次　·　接觸 ${a.names.size} 家</div>`;
  h+=`<div class="btn-row" style="margin-top:0"><button class="btn btn-pri" onclick="copyReport()">📋 複製主管週報（文字）</button></div>`;
  if(!a.visits.length){ h+=`<div class="card"><div class="empty"><div class="big">📝</div>本週尚無拜訪紀錄。<br>到「拜訪路線」排行程，當日跑完按「完成今日拜訪」，<br>或在客戶/名單按「記錄拜訪」，這裡就會自動彙整。</div></div>`; viewHTML(h); return; }
  const custN=new Set(a.custVisits.map(v=>v.id)).size, prospN=new Set(a.prospVisits.map(v=>v.id)).size;
  // 一、摘要
  h+=`<div class="sec-title"><span class="bar"></span>① 本週執行摘要</div><div class="card">`;
  h+=drow('拜訪 / 接觸', `${a.visits.length} 次　·　${a.names.size} 家`);
  h+=drow('既有 / 目標', `既有客戶 ${custN} 家　·　目標開發 ${prospN} 家`);
  if(a.newCust.length) h+=drow('新轉入客戶', `⭐ ${esc(a.newCust.join('、'))}`);
  h+=drow('縣市足跡', sortedKeys(a.byCounty).map(k=>`${esc(k)} ${a.byCounty[k]}`).join('　'));
  h+=`</div>`;
  // 二、結構分析
  h+=`<div class="sec-title"><span class="bar"></span>② 拜訪結構分析</div><div class="card">`;
  h+=drow('通路別', sortedKeys(a.byChan).map(k=>`<span class="badge b-${k}">${esc(k)} ${a.byChan[k]}</span>`).join(' '));
  if(Object.keys(a.byGrade).length) h+=drow('客戶分級', sortedKeys(a.byGrade).map(k=>`<span class="badge grade-${k}">${k}級 ${a.byGrade[k]}</span>`).join(' '));
  h+=`</div>`;
  // 三、每日紀要
  h+=`<div class="sec-title"><span class="bar"></span>③ 每日行程紀要</div>`;
  for(let i=0;i<5;i++){
    const d=addDays(a.mon,i); const dv=a.visits.filter(v=>v.date===d); if(!dv.length) continue;
    h+=`<div class="sec-title" style="font-size:13px;margin-top:8px"><span class="bar"></span>${d.slice(5)}　週${WD_NAME[new Date(d).getDay()]}　(${dv.length})</div><div class="card">`;
    dv.forEach(v=>{
      const pill=`<span class="badge b-${v.kind==='客戶'?'農會':'其他'}">${v.kind}</span>`;
      const click=v.who==='cust'?`viewCustomer('${v.id}')`:`viewProspect('${v.id}')`;
      h+=itemRow({name:v.name,sub:[v.m.chan,v.m.region].filter(Boolean).join('・')+'｜'+(v.content||'完成拜訪'),pill,onclick:click});
    });
    h+=`</div>`;
  }
  // 四、跟進
  if(a.follows.length){
    h+=`<div class="sec-title"><span class="bar"></span>④ 待跟進事項（${a.follows.length}）</div><div class="card">`;
    a.follows.slice(0,15).forEach(f=>{ const od=f.due&&f.due<todayStr(); h+=`<div class="drow"><div class="dk">${esc(f.name)}</div><div class="dv">${esc(f.text)}${f.due?` <span class="${od?'over':''}" style="color:${od?'var(--red)':'var(--muted)'}">📅${esc(f.due)}${od?'逾期':''}</span>`:''}</div></div>`; });
    h+=`</div>`;
  }
  // 五、下週規劃
  h+=`<div class="sec-title"><span class="bar"></span>${a.follows.length?'⑤':'④'} 下週工作規劃</div><div class="card">`;
  if(a.nextWk.length){
    h+=`<div class="tagline" style="margin:0 0 6px">依拜訪頻率，下週應回訪 ${a.nextWk.length} 家：</div>`;
    a.nextWk.slice(0,15).forEach(x=>{ h+=`<div class="drow"><div class="dk">${esc(x.due.slice(5))}</div><div class="dv">${esc(x.name)}${x.grade?` <span class="badge grade-${x.grade}">${x.grade}級</span>`:''}</div></div>`; });
  } else h+=`<div class="tagline" style="margin:0">下週無系統排定回訪，建議持續開發目標名單、深耕本週新接觸客戶。</div>`;
  h+=`</div>`;
  viewHTML(h);
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
  const valid=['map','prospects','route','customers','compete','report','settings'];
  const hash=(location.hash||'').replace('#','');
  go(valid.includes(hash)?hash:'map');
  showInAppWarning();
  maybeAutoBackup();
}
window.addEventListener('hashchange',()=>{ const h=(location.hash||'').replace('#',''); const valid=['map','prospects','route','customers','compete','report','settings']; if(valid.includes(h)) go(h); });
initApp();
