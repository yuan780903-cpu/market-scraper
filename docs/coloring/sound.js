/* ===== 可愛音效 + 背景音樂（Web Audio 即時合成，無版權、離線可用） ===== */
const Sound = (function(){
  let ctx, master, musicGain, musicOn=false, timer=null, step=0;

  function ac(){
    if(!ctx){
      ctx = new (window.AudioContext||window.webkitAudioContext)();
      master = ctx.createGain(); master.gain.value=0.6; master.connect(ctx.destination);
      musicGain = ctx.createGain(); musicGain.gain.value=0.0; musicGain.connect(master);
    }
    if(ctx.state==='suspended') ctx.resume();
    return ctx;
  }

  function tone(freq, dur, type, vol, dest, when){
    const c=ac(); const t=(when||c.currentTime);
    const o=c.createOscillator(), g=c.createGain();
    o.type=type||'sine'; o.frequency.value=freq;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(vol, t+0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t+dur);
    o.connect(g).connect(dest||master);
    o.start(t); o.stop(t+dur+0.03);
  }

  /* 互動音效 */
  function sfx(name){
    ac();
    const n=name||'click';
    if(n==='select'){ tone(880,0.12,'triangle',0.25); tone(1320,0.14,'triangle',0.18,null,ctx.currentTime+0.06); }
    else if(n==='deselect'){ tone(620,0.12,'triangle',0.2); tone(440,0.14,'sine',0.16,null,ctx.currentTime+0.05); }
    else if(n==='click'){ tone(740,0.09,'square',0.12); }
    else if(n==='rand'){ [660,880,990,1320].forEach((f,i)=>tone(f,0.12,'triangle',0.16,null,ctx.currentTime+i*0.05)); }
    else if(n==='pop'){ tone(1046,0.1,'sine',0.25); tone(1568,0.12,'sine',0.16,null,ctx.currentTime+0.04); }
    else if(n==='fanfare'){ [523,659,784,1046,1318].forEach((f,i)=>tone(f,0.3,'triangle',0.2,null,ctx.currentTime+i*0.09)); }
  }

  /* 背景音樂：原創五聲音階循環，輕柔可愛 */
  const C5=523.25,D5=587.33,E5=659.25,G5=783.99,A5=880,C6=1046.5;
  const C3=130.81,F3=174.61,G3=196.0;
  const MEL=[C5,E5,G5,E5, A5,G5,E5,D5, C5,E5,G5,A5, G5,E5,D5,C5];
  const BASS=[C3,0,0,0, F3,0,0,0, G3,0,0,0, C3,0,0,0];
  const STEP=0.22;

  function tick(){
    const c=ac(); const t=c.currentTime+0.04;
    const m=MEL[step%MEL.length];
    if(m) tone(m,STEP*0.9,'triangle',0.09,musicGain,t);
    const b=BASS[step%BASS.length];
    if(b) tone(b,STEP*2.4,'sine',0.10,musicGain,t);
    if(step%4===2) tone(2200,0.05,'square',0.02,musicGain,t); /* 輕點綴 */
    step++;
  }
  function startMusic(){
    ac(); musicOn=true; step=0;
    musicGain.gain.cancelScheduledValues(ctx.currentTime);
    musicGain.gain.linearRampToValueAtTime(0.8, ctx.currentTime+0.6);
    tick(); timer=setInterval(tick, STEP*1000);
  }
  function stopMusic(){
    musicOn=false;
    if(timer){ clearInterval(timer); timer=null; }
    if(musicGain) musicGain.gain.linearRampToValueAtTime(0.0001, ctx.currentTime+0.3);
  }
  function toggleMusic(){ musicOn?stopMusic():startMusic(); return musicOn; }

  return { sfx, toggleMusic, isOn:()=>musicOn };
})();
