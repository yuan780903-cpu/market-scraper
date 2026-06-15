/* ===== 工具 ===== */
function svgFor(id){
  return `<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg"><g fill="none" stroke="#1a1a1a" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">${DRAW[id]}</g></svg>`;
}
function shuffle(a){ const b=a.slice(); for(let i=b.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[b[i],b[j]]=[b[j],b[i]];} return b; }
function nameOf(id){ return NAMES[id]||id; }

/* ===== 狀態 ===== */
let selected = [];           // {key, type:'svg', id} 或 {key, type:'img', name, data}
let uploads = [];            // {uid, name, data}  (上傳/網址/AI 產生的圖)
const isSel = key => selected.some(s=>s.key===key);

/* ===== 建立畫面 ===== */
const wrap = document.getElementById('wrap');

GROUPS.forEach((g, gi)=>{
  const lbl = document.createElement('div'); lbl.className='grp-label'; lbl.textContent=g.label;
  wrap.appendChild(lbl);
  g.themes.forEach((t, ti)=>{
    const tid = 'g'+gi+'t'+ti;
    const el = document.createElement('div'); el.className='theme'; el.dataset.tid=tid;
    el.innerHTML = `
      <div class="theme-head">
        <span class="theme-emo">${t.emoji}</span>
        <span class="theme-name">${t.name}</span>
        <span class="theme-badge" data-badge="${tid}">0</span>
        <span class="theme-arrow">▼</span>
      </div>
      <div class="theme-body">
        <div class="mini-bar">
          <button class="mini-btn" data-act="all" data-tid="${tid}">全選</button>
          <button class="mini-btn" data-act="rand" data-tid="${tid}">🎲 隨機 4 個</button>
          <button class="mini-btn" data-act="none" data-tid="${tid}">清除</button>
        </div>
        <div class="chips">${t.ids.map(id=>chipHTML('svg',id,nameOf(id),'svg:'+id)).join('')}</div>
      </div>`;
    el.querySelector('.theme-head').onclick = e=>{ if(e.target.closest('.mini-btn'))return; el.classList.toggle('open'); };
    wrap.appendChild(el);
  });
});

/* ===== 我的圖片區（上傳 / 網址 / AI） ===== */
const myLbl = document.createElement('div'); myLbl.className='grp-label'; myLbl.textContent='🖼️ 我的圖片（卡通／Tomica 自己加）';
wrap.appendChild(myLbl);
const myCard = document.createElement('div'); myCard.className='theme open';
myCard.innerHTML = `
  <div class="theme-head"><span class="theme-emo">📥</span><span class="theme-name">從網站挑圖 / 上傳 / AI 生圖</span><span class="theme-arrow">▼</span></div>
  <div class="theme-body">
    <div class="site-box">
      <div class="site-title">🔎 從圖庫網站挑圖</div>
      <div class="tool-row">
        <a class="btn" href="https://www.supercoloring.com/zh-tw" target="_blank" rel="noopener">🎨 開 SuperColoring</a>
        <a class="btn soft" href="https://www.pinterest.com/search/pins/?q=coloring%20page" target="_blank" rel="noopener">📌 開 Pinterest</a>
      </div>
      <p class="hint"><b>方法 1（最穩）</b>：在網站找到喜歡的圖 → 下載／儲存到手機 → 回來按下面「📂 從手機選圖」。<br>
      <b>方法 2</b>：長按圖片 →「拷貝圖片位址」→ 貼到下面網址欄 → 加入。<span style="color:#c98">（部分網站擋外連，失敗請改用方法 1）</span></p>
    </div>
    <div class="tool-row">
      <input type="file" id="fileInput" accept="image/*" multiple style="display:none">
      <button class="btn soft" id="pickBtn">📂 從手機選圖</button>
    </div>
    <div class="tool-row">
      <input class="ipt" id="urlInput" placeholder="貼上圖片網址 https://...">
      <button class="btn" id="urlBtn">加入</button>
    </div>
    <div class="tool-row">
      <input class="ipt" id="aiInput" placeholder="AI 生圖：描述內容，例如「可愛的小貓」">
      <button class="btn" id="aiBtn">✨ 生成</button>
    </div>
    <p class="hint">想要 Tomica、寶可夢等卡通？把圖<b>下載後上傳</b>或<b>貼網址</b>加入（個人列印用）。AI 生圖免費、需連網，只能產生原創風格。</p>
    <div class="chips" id="myChips" style="margin-top:10px"></div>
  </div>`;
myCard.querySelector('.theme-head').onclick = ()=> myCard.classList.toggle('open');
wrap.appendChild(myCard);

/* ===== 我的 Tomica 收藏（僅本機；公開網站沒有此檔會自動略過） ===== */
(function loadTomica(){
  const s=document.createElement('script');
  s.src='tomica_local.js';
  s.onload=()=>{ if(window.TOMICA_LOCAL && window.TOMICA_LOCAL.length) buildTomica(window.TOMICA_LOCAL); };
  s.onerror=()=>{};            // 公開 GitHub 版沒有此檔，靜默略過
  document.head.appendChild(s);
})();
function buildTomica(items){
  items.forEach(it=>{ imgReg[it.uid]={name:it.name,data:it.data}; });
  const lbl=document.createElement('div'); lbl.className='grp-label'; lbl.textContent='🚗 我的 Tomica 收藏（僅本機）';
  wrap.insertBefore(lbl, myLbl);
  const tid='tomica';
  const el=document.createElement('div'); el.className='theme open'; el.dataset.tid=tid;
  el.innerHTML=`
    <div class="theme-head">
      <span class="theme-emo">🚗</span>
      <span class="theme-name">Tomica 著色（${items.length} 張）</span>
      <span class="theme-badge" data-badge="${tid}">0</span>
      <span class="theme-arrow">▼</span>
    </div>
    <div class="theme-body">
      <div class="mini-bar">
        <button class="mini-btn" data-act="all" data-tid="${tid}">全選</button>
        <button class="mini-btn" data-act="rand" data-tid="${tid}">🎲 隨機 4 個</button>
        <button class="mini-btn" data-act="none" data-tid="${tid}">清除</button>
      </div>
      <div class="chips">${items.map(it=>chipHTML('img',it.uid,it.name,'img:'+it.uid,it.data)).join('')}</div>
    </div>`;
  el.querySelector('.theme-head').onclick = e=>{ if(e.target.closest('.mini-btn'))return; el.classList.toggle('open'); };
  wrap.insertBefore(el, myLbl);
  refresh();
}

/* ===== chip HTML ===== */
function chipHTML(type, id, name, key, data){
  const art = type==='svg' ? svgFor(id) : `<img src="${data}" alt="">`;
  return `<div class="chip${isSel(key)?' sel':''}" data-key="${key}" data-type="${type}" data-id="${id||''}">
    ${art}<div class="nm">${name}</div><div class="tk">✓</div></div>`;
}

/* ===== 點選（事件委派） ===== */
document.addEventListener('click', e=>{
  const chip = e.target.closest('.chip');
  if(chip){ Sound.sfx(isSel(chip.dataset.key)?'deselect':'select'); toggleChip(chip); return; }
  const mb = e.target.closest('.mini-btn[data-act]');
  if(mb){ Sound.sfx(mb.dataset.act==='rand'?'rand':'click'); themeAction(mb.dataset.act, mb.dataset.tid); }
});

const imgReg={};   // uid -> {name, data}  （上傳圖、Tomica 收藏共用）
function chipObj(chip){
  const key=chip.dataset.key, type=chip.dataset.type;
  if(type==='svg') return {key,type,id:chip.dataset.id};
  const u=imgReg[key.slice(4)];   // key = 'img:'+uid
  return {key,type,name:u?u.name:'圖片',data:u?u.data:''};
}
function toggleChip(chip){
  const key=chip.dataset.key;
  const i=selected.findIndex(s=>s.key===key);
  if(i>=0) selected.splice(i,1); else selected.push(chipObj(chip));
  refresh();
}
function themeAction(act, tid){
  const card=document.querySelector(`.theme[data-tid="${tid}"]`);
  const chips=[...card.querySelectorAll('.chip')];
  if(act==='none'){ chips.forEach(c=>{ const i=selected.findIndex(s=>s.key===c.dataset.key); if(i>=0)selected.splice(i,1); }); }
  if(act==='all'){ chips.forEach(c=>{ if(!isSel(c.dataset.key)) selected.push(chipObj(c)); }); }
  if(act==='rand'){ chips.forEach(c=>{ const i=selected.findIndex(s=>s.key===c.dataset.key); if(i>=0)selected.splice(i,1); });
    shuffle(chips).slice(0,Math.min(4,chips.length)).forEach(c=>selected.push(chipObj(c))); }
  refresh();
}

/* ===== 我的圖片：上傳 / 網址 / AI ===== */
document.getElementById('pickBtn').onclick = ()=> document.getElementById('fileInput').click();
document.getElementById('fileInput').onchange = e=>{
  [...e.target.files].forEach(f=>{
    const r=new FileReader();
    r.onload=ev=> addUpload(f.name.replace(/\.[^.]+$/,''), ev.target.result);
    r.readAsDataURL(f);
  });
  e.target.value='';
};
document.getElementById('urlBtn').onclick = ()=>{
  const v=document.getElementById('urlInput').value.trim();
  if(!/^https?:\/\//i.test(v)){ alert('請貼上 http(s) 開頭的圖片網址'); return; }
  const btn=document.getElementById('urlBtn'); const old=btn.textContent;
  btn.textContent='載入中…'; btn.disabled=true;
  const img=new Image();
  img.onload=()=>{ addUpload('網路圖片', v); document.getElementById('urlInput').value=''; btn.textContent=old; btn.disabled=false; };
  img.onerror=()=>{ alert('這張圖無法直接載入（網站可能擋外連）。\n請改用方法 1：在網站把圖片下載到手機，再按「📂 從手機選圖」上傳。'); btn.textContent=old; btn.disabled=false; };
  img.src=v;
};
document.getElementById('aiBtn').onclick = ()=>{
  const v=document.getElementById('aiInput').value.trim();
  if(!v){ alert('請先輸入要畫什麼'); return; }
  const btn=document.getElementById('aiBtn'); const old=btn.innerHTML;
  btn.innerHTML='<span class="spinner"></span>'; btn.disabled=true;
  const prompt = encodeURIComponent(v + ', black and white line art coloring book page for kids, thick clean outlines, no shading, no grey, pure white background');
  const url = 'https://image.pollinations.ai/prompt/'+prompt+'?width=768&height=1024&nologo=true&seed='+Math.floor(Math.random()*99999);
  const img=new Image();
  img.onload=()=>{ addUpload('AI:'+v, url); btn.innerHTML=old; btn.disabled=false; document.getElementById('aiInput').value=''; };
  img.onerror=()=>{ alert('AI 生圖失敗，請確認有連網或稍後再試'); btn.innerHTML=old; btn.disabled=false; };
  img.src=url;
};
function addUpload(name, data){
  const uid='u'+Date.now()+Math.random().toString(36).slice(2,5);
  uploads.push({uid,name,data});
  imgReg[uid]={name,data};
  renderMyChips();
}
function renderMyChips(){
  document.getElementById('myChips').innerHTML =
    uploads.map(u=>chipHTML('img',u.uid,u.name,'img:'+u.uid,u.data)).join('');
}

/* ===== 重新整理選取狀態 ===== */
function refresh(){
  document.querySelectorAll('.chip').forEach(c=> c.classList.toggle('sel', isSel(c.dataset.key)));
  document.querySelectorAll('.theme[data-tid]').forEach(card=>{
    const tid=card.dataset.tid;
    const n=[...card.querySelectorAll('.chip')].filter(c=>isSel(c.dataset.key)).length;
    const b=document.querySelector(`[data-badge="${tid}"]`);
    b.textContent=n; b.classList.toggle('on', n>0);
  });
  document.getElementById('selCount').textContent=selected.length;
  document.getElementById('goPDF').disabled = selected.length===0;
  document.getElementById('clearAll').style.display = selected.length? 'inline-block':'none';
}
document.getElementById('clearAll').onclick = ()=>{ selected=[]; refresh(); };

/* ===== 張數彈窗 ===== */
const overlay=document.getElementById('overlay');
const COUNTS=[1,4,6,8,12,20];
let chosenCount=4;
document.getElementById('countRow').innerHTML =
  COUNTS.map(n=>`<button class="cbtn${n===4?' sel':''}" data-n="${n}">${n}</button>`).join('');
document.getElementById('countRow').onclick = e=>{
  const b=e.target.closest('.cbtn'); if(!b)return;
  chosenCount=+b.dataset.n;
  document.querySelectorAll('.cbtn').forEach(x=>x.classList.toggle('sel',x===b));
  document.getElementById('customCount').value='';
  buildPreview();
};
document.getElementById('customCount').oninput = e=>{
  const v=parseInt(e.target.value); if(v>0){ chosenCount=v; document.querySelectorAll('.cbtn').forEach(x=>x.classList.remove('sel')); buildPreview(); }
};
document.getElementById('countRow').addEventListener('click', e=>{ if(e.target.closest('.cbtn')) Sound.sfx('click'); });
document.getElementById('goPDF').onclick = ()=>{
  if(!selected.length) return;
  Sound.sfx('pop');
  overlay.classList.add('show'); buildPreview();
};
overlay.onclick = e=>{ if(e.target===overlay) overlay.classList.remove('show'); };

let pages=[];
function buildPages(){
  const pool=selected.slice(); pages=[];
  if(!pool.length) return;
  while(pages.length<chosenCount){ shuffle(pool).forEach(p=>{ if(pages.length<chosenCount) pages.push(p); }); }
}
function buildPreview(){
  buildPages();
  document.getElementById('pvGrid').innerHTML = pages.map((p,i)=>{
    const art=p.type==='svg'?svgFor(p.id):`<img src="${p.data}">`;
    return `<div class="pv">${art}<div class="nm">${i+1}</div></div>`;
  }).join('');
}

/* ===== 列印 / 另存 PDF ===== */
document.getElementById('printBtn').onclick = ()=>{
  if(!pages.length) buildPages();
  if(!pages.length){ alert('請先選角色'); return; }
  const area=document.getElementById('printArea'); area.innerHTML='';
  pages.forEach((p,i)=>{
    const sheet=document.createElement('div'); sheet.className='sheet';
    const art=p.type==='svg'?svgFor(p.id):`<img src="${p.data}">`;
    sheet.innerHTML=`<div class="art">${art}</div><div class="nm">${p.type==='svg'?nameOf(p.id):(p.name||'')} ・ ${i+1}/${pages.length}</div>`;
    area.appendChild(sheet);
  });
  document.title='著色畫_'+pages.length+'張';
  Sound.sfx('fanfare');
  overlay.classList.remove('show');
  setTimeout(()=>window.print(), 250);
};

/* 音樂開關 */
const musicBtn=document.getElementById('musicToggle');
musicBtn.onclick=()=>{
  const on=Sound.toggleMusic();
  musicBtn.textContent = on?'🎵 音樂':'🔇 音樂';
  musicBtn.classList.toggle('off', !on);
};

refresh();
