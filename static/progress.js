import { CURRICULUM } from './curriculum-data.js';

const PROGRESS_KEY = 'engineering-curriculum-progress-v1';
const C = CURRICULUM;

// Data is pinned at build time; escaping also protects the dashboard when
// future curriculum text changes without requiring runtime HTML trust.
function escapeHtml(value) {
  const node = document.createElement('span');
  node.textContent = String(value);
  return node.innerHTML;
}

const domains = C.domains;
const tracks = C.tracks;
const trackNames = {
  backend:'Backend', systems:'Systems', cloud:'Cloud/SRE',
  ai:'Data/AI', product:'Product/Leadership', physical:'Physical AI'
};

const GROUP_COLORS = {
  core:'#60a5fa', systems:'#a78bfa', language:'#818cf8',
  'lang-impl':'#4ade80', backend:'#f472b6', architecture:'#f87171',
  data:'#facc15', distributed:'#fbbf24', cloud:'#7dd3fc',
  delivery:'#a3e635', reliability:'#34d399', ai:'#67e8f9',
  security:'#fb7185', quality:'#d946ef', perf:'#c084fc',
  tools:'#94a3b8', product:'#fbbf24', frontend:'#60a5fa',
  mobile:'#4ade80', embedded:'#2dd4bf', robotics:'#fb923c',
  gpu:'#f87171', signal:'#facc15', network:'#22d3ee',
};
const DOMAIN_GROUP = {
  1:'core',2:'core',3:'core',4:'core',5:'systems',6:'systems',7:'systems',
  8:'language',9:'language',10:'network',11:'lang-impl',12:'lang-impl',
  13:'lang-impl',14:'backend',15:'architecture',16:'data',26:'data',
  17:'distributed',18:'cloud',19:'cloud',20:'delivery',21:'reliability',
  22:'reliability',23:'perf',24:'security',25:'quality',27:'ai',28:'ai',
  29:'ai',30:'tools',31:'product',32:'product',33:'frontend',34:'mobile',
  35:'embedded',36:'robotics',37:'gpu',38:'signal',
};

function loadP(){try{return JSON.parse(localStorage.getItem(PROGRESS_KEY)||'{}')}catch{return{}}}
let p = loadP();

function lessonId(did,mi,li){return `D${String(did).padStart(2,'0')}-M${String(mi).padStart(2,'0')}-L${li}`}
function isComplete(id){return p[id]?.completed===true}
function completedAt(id){return p[id]?.completedAt||null}

function domainStats(did){
  let done=0,total=30;
  for(let m=1;m<=10;m++) for(let l=1;l<=3;l++) if(isComplete(lessonId(did,m,l))) done++;
  return {done,total,pct:Math.round(done/total*100)};
}

function moduleStats(did,mi){
  let done=0,total=3;
  for(let l=1;l<=3;l++) if(isComplete(lessonId(did,mi,l))) done++;
  return {done,total,pct:Math.round(done/total*100)};
}

function trackStats(track){
  const ids = tracks[track];
  if(!ids) return {done:0,total:0,pct:0};
  let total=0,done=0;
  ids.forEach(did=>{const s=domainStats(did);done+=s.done;total+=s.total});
  return {done,total,pct:total?Math.round(done/total*100):0};
}

// Certification Level
function certLevel(pct){
  if(pct>=100) return {level:'Platinum',label:'完全習得',badge:'platinum',emoji:'🏆',req:'全1,140Lesson完了'};
  if(pct>=75) return {level:'Gold',label:'高度習得',badge:'gold',emoji:'🥇',req:'75%以上完了'};
  if(pct>=50) return {level:'Silver',label:'中間習得',badge:'silver',emoji:'🥈',req:'50%以上完了'};
  if(pct>=25) return {level:'Bronze',label:'基礎習得',badge:'bronze',emoji:'🥉',req:'25%以上完了'};
  return {level:'Beginner',label:'学習開始',badge:'',emoji:'📚',req:'最初のLessonを完了しよう'};
}

// Render certification display
function renderCert(){
  const total = C.lessons.length;
  const done = C.lessons.filter(x => isComplete(x.id)).length;
  const pct = total?Math.round(done/total*100):0;
  const cl = certLevel(pct);
  const doneDomains = domains.filter(d=>domainStats(d.id).pct>=70).length;
  const doneTracks = Object.keys(tracks).filter(t=>trackStats(t).pct>=80).length;

  document.getElementById('stat-total').textContent = total.toLocaleString();
  document.getElementById('stat-completed').textContent = done.toLocaleString();
  document.getElementById('stat-percent').textContent = pct+'%';
  document.getElementById('stat-domains').textContent = doneDomains+'/38';
  document.getElementById('stat-tracks').textContent = doneTracks+'/6';

  // Donut
  const circumference = 2 * Math.PI * 72;
  const offset = circumference - (pct/100)*circumference;
  const fill = document.getElementById('donut-fill');
  if(fill){fill.style.strokeDasharray = circumference; fill.style.strokeDashoffset = offset;}
  const donutPercent = document.getElementById('donut-pct');
  if(donutPercent) donutPercent.textContent = pct+'%';

  // Level display
  const ld = document.getElementById('cert-level-display');
  if(cl.level==='Beginner'){
    ld.innerHTML = `<div class="cert-level"><div class="cert-badge" style="background:rgba(255,255,255,.06);border-color:var(--line);color:var(--muted);font-size:18px">📚</div><div class="cert-label"><h2>学習開始</h2><p>${cl.req}</p></div></div>`;
  } else {
    ld.innerHTML = `<div class="cert-level"><div class="cert-badge ${cl.badge}">${cl.emoji}</div><div class="cert-label"><h2>${cl.level}</h2><p>${cl.label} · ${cl.req}</p></div></div>`;
  }

  // Milestones
  const ms = document.getElementById('milestones');
  const milestones = [
    {pct:25,label:'Bronze 25%'},{pct:50,label:'Silver 50%'},
    {pct:75,label:'Gold 75%'},{pct:100,label:'Platinum 100%'}
  ];
  ms.innerHTML = milestones.map(m=>
    `<span class="cert-milestone ${pct>=m.pct?'done':''}">${pct>=m.pct?'✓':''}${m.label}</span>`
  ).join('');
}

// Domain grid
function renderDomains(){
  const grid = document.getElementById('domain-grid');
  grid.innerHTML = domains.map(d=>{
    const s = domainStats(d.id);
    const g = DOMAIN_GROUP[d.id]||'core';
    const color = GROUP_COLORS[g]||'#60a5fa';
    const status = s.pct>=70?'done':s.done>0?'progress':'none';
    const statusLabel = s.pct>=70?'完了':s.done>0?`${s.pct}%`:'未着手';
    let modHtml = '';
    for(let m=1;m<=10;m++){
      const ms_ = moduleStats(d.id,m);
      const cls = ms_.done===3?'done':ms_.done>0?'partial':'';
      modHtml += `<div class="d-module ${cls}" title="M${String(m).padStart(2,'0')}: ${ms_.done}/3"></div>`;
    }
    return `<div class="domain-card">
      <div class="d-header">
        <a class="d-title" href="catalog/index.html#d${String(d.id).padStart(2,'0')}-m01-l1">D${String(d.id).padStart(2,'0')} ${escapeHtml(d.title)}</a>
        <span class="d-status ${status}">${statusLabel}</span>
      </div>
      <div class="d-bar-shell"><div class="d-bar-fill" style="width:${s.pct}%;background:${color}"></div></div>
      <div class="d-meta"><span>${s.done}/${s.total}</span><span>${s.pct}%</span></div>
      <div class="d-modules">${modHtml}</div>
    </div>`;
  }).join('');
}

// Track grid
function renderTracks(){
  const grid = document.getElementById('track-grid');
  grid.innerHTML = Object.entries(tracks).map(([key,ids])=>{
    const s = trackStats(key);
    const color = ['#60a5fa','#a78bfa','#22d3ee','#34d399','#fbbf24','#fb923c'][
      ['backend','systems','cloud','ai','product','physical'].indexOf(key)]||'#60a5fa';
    const status = s.pct>=80?'done':s.done>0?'progress':'none';
    const dots = ids.map(did=>{
      const ds = domainStats(did);
      const cls = ds.pct>=70?'done':ds.done>0?'progress':'';
      return `<div class="t-dot ${cls}" title="D${String(did).padStart(2,'0')}: ${ds.pct}%">D${did}</div>`;
    }).join('');
    return `<div class="track-card">
      <h3>${trackNames[key]||key}</h3>
      <div class="t-bar-shell"><div class="t-bar-fill" style="width:${s.pct}%;background:${color}"></div></div>
      <div class="d-meta"><span>${s.done}/${s.total}</span><span>${s.pct}%</span></div>
      <div class="t-domains">${dots}</div>
    </div>`;
  }).join('');
}

// Heatmap
function renderHeatmap(){
  const hm = document.getElementById('heatmap');
  let html = '<div class="heatmap-header"></div>';
  for(let m=1;m<=10;m++) html += `<div class="heatmap-header">M${String(m).padStart(2,'0')}</div>`;
  domains.forEach(d=>{
    html += `<div class="heatmap-row"><div class="heatmap-label">D${String(d.id).padStart(2,'0')} ${d.title}</div>`;
    for(let m=1;m<=10;m++){
      const ms_ = moduleStats(d.id,m);
      const cls = ms_.done===3?'done':ms_.done>0?'partial':'';
      html += `<div class="heatmap-cell ${cls}" title="${d.title} M${String(m).padStart(2,'0')}: ${ms_.done}/3"></div>`;
    }
    html += '</div>';
  });
  hm.innerHTML = html;
}

// History
function renderHistory(){
  const list = document.getElementById('history-list');
  const entries = C.lessons.filter(x=>isComplete(x.id)&&completedAt(x.id))
    .map(x=>({...x,at:new Date(completedAt(x.id)).getTime()}))
    .sort((a,b)=>b.at-a.at).slice(0,50);
  if(!entries.length){
    list.innerHTML = '<p class="small" style="text-align:center;padding:20px">完了したLessonがここに表示されます。</p>';
    return;
  }
  list.innerHTML = entries.map(e=>{
    const d = new Date(e.at);
    const dateStr = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    return `<div class="history-item">
      <span class="h-lesson"><a href="catalog/index.html#${e.id.toLowerCase()}">${escapeHtml(e.id)}</a> ${escapeHtml(e.title)}</span>
      <span><span class="h-domain">${escapeHtml(e.domainTitle)}</span> <span class="h-date">${dateStr}</span></span>
    </div>`;
  }).join('');
}

// Tabs
document.querySelectorAll('.tab').forEach(tab=>{
  tab.addEventListener('click',()=>{
    document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-'+tab.dataset.tab).classList.add('active');
  });
});

// Re-render on progress change
function refresh(){
  p = loadP();
  renderCert(); renderDomains(); renderTracks(); renderHeatmap(); renderHistory();
}
window.addEventListener('curriculum-progress-changed', refresh);
document.addEventListener('DOMContentLoaded', refresh);

// Make refresh available for app.js compatibility
window.CurriculumProgress = window.CurriculumProgress || {};
window.CurriculumProgress.refreshDashboard = refresh;
