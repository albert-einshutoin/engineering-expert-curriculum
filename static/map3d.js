import * as THREE from './three.module.js';
import { OrbitControls } from './three/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from './three/CSS2DRenderer.js';

const C = window.CURRICULUM;
const domains = C.domains;
const tracks = C.tracks;
const progressKey = 'engineering-curriculum-progress-v1';

function loadProgress(){
  try{return JSON.parse(localStorage.getItem(progressKey)||'{}')}catch{return{}}
}

function getCompletedLessonIds(){
  const p = loadProgress();
  return new Set(Object.keys(p).filter(id => p[id]?.completed));
}

function domainCompletedRatio(domainId){
  const completed = getCompletedLessonIds();
  let count = 0;
  for(let m=1; m<=10; m++){
    for(let l=1; l<=3; l++){
      if(completed.has(`D${String(domainId).padStart(2,'0')}-M${String(m).padStart(2,'0')}-L${l}`)) count++;
    }
  }
  return count / 30;
}

const GROUP_COLORS = {
  core: 0x60a5fa, systems: 0xa78bfa, language: 0x818cf8,
  'lang-impl': 0x4ade80, backend: 0xf472b6, architecture: 0xf87171,
  data: 0xfacc15, distributed: 0xfbbf24, cloud: 0x7dd3fc,
  delivery: 0xa3e635, reliability: 0x34d399, ai: 0x67e8f9,
  security: 0xfb7185, quality: 0xd946ef, perf: 0xc084fc,
  tools: 0x94a3b8, product: 0x6366f1, frontend: 0x60a5fa,
  mobile: 0x4ade80, embedded: 0x2dd4bf, robotics: 0xfb923c,
  gpu: 0xf87171, signal: 0xfacc15, network: 0x22d3ee,
};

const DOMAIN_GROUP = {
  1:'core',2:'core',3:'core',4:'core',
  5:'systems',6:'systems',7:'systems',
  8:'language',9:'language',
  10:'network',
  11:'lang-impl',12:'lang-impl',13:'lang-impl',
  14:'backend',
  15:'architecture',
  16:'data',26:'data',
  17:'distributed',
  18:'cloud',19:'cloud',
  20:'delivery',
  21:'reliability',22:'reliability',
  23:'perf',
  24:'security',
  25:'quality',
  27:'ai',28:'ai',29:'ai',
  30:'tools',
  31:'product',32:'product',
  33:'frontend',
  34:'mobile',
  35:'embedded',
  36:'robotics',
  37:'gpu',
  38:'signal',
};

const GROUP_LABELS = {
  core:'基礎理論', systems:'Systems', language:'言語理論',
  'lang-impl':'言語実装', backend:'Backend', architecture:'設計',
  data:'Data', distributed:'分散', cloud:'Cloud',
  delivery:'Delivery', reliability:'信頼性', ai:'AI/ML',
  security:'Security', quality:'品質', perf:'性能',
  tools:'DevTools', product:'Product', frontend:'Frontend',
  mobile:'Mobile', embedded:'組込', robotics:'Robotics',
  gpu:'GPU/HPC', signal:'信号処理', network:'Network',
};

const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b1020);

const camera = new THREE.PerspectiveCamera(45, container.clientWidth/container.clientHeight, 0.1, 1000);
camera.position.set(25, 18, 28);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
container.appendChild(renderer.domElement);

const labelRenderer = new CSS2DRenderer();
labelRenderer.setSize(container.clientWidth, container.clientHeight);
labelRenderer.domElement.style.position = 'absolute';
labelRenderer.domElement.style.top = '0';
labelRenderer.domElement.style.left = '0';
labelRenderer.domElement.style.pointerEvents = 'none';
container.appendChild(labelRenderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 8;
controls.maxDistance = 60;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.6;
controls.target.set(0, 0, 0);

const ambient = new THREE.AmbientLight(0x404060, 0.6);
scene.add(ambient);

const dirLight = new THREE.DirectionalLight(0xffffff, 1.8);
dirLight.position.set(20, 30, 10);
dirLight.castShadow = true;
scene.add(dirLight);

const fillLight = new THREE.DirectionalLight(0x4488ff, 0.5);
fillLight.position.set(-10, 0, -15);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0x88ddff, 0.4);
rimLight.position.set(-5, -10, 20);
scene.add(rimLight);

const particleGeo = new THREE.BufferGeometry();
const particleCount = 800;
const positions = new Float32Array(particleCount * 3);
for(let i=0;i<particleCount*3;i++) positions[i] = (Math.random()-0.5)*120;
particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
const particleMat = new THREE.PointsMaterial({
  color: 0x4488ff, size: 0.08, transparent: true, opacity: 0.4,
});
const particles = new THREE.Points(particleGeo, particleMat);
scene.add(particles);

const ringGeo = new THREE.RingGeometry(14, 16, 64);
const ringMat = new THREE.MeshBasicMaterial({
  color: 0x4488ff, transparent: true, opacity: 0.06, side: THREE.DoubleSide,
});
const ring = new THREE.Mesh(ringGeo, ringMat);
ring.rotation.x = -Math.PI/2;
ring.position.y = -5;
scene.add(ring);

const nodeMap = new Map();
const nodes = [];

domains.forEach(d => {
  const group = DOMAIN_GROUP[d.id] || 'core';
  const color = GROUP_COLORS[group] || 0x60a5fa;
  const ratio = domainCompletedRatio(d.id);
  const completed = ratio >= 0.7;

  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(1, 32, 32),
    new THREE.MeshPhysicalMaterial({
      color, roughness: 0.2, metalness: 0.3, clearcoat: 0.2,
      emissive: completed ? color : new THREE.Color(color).multiplyScalar(0.15),
      emissiveIntensity: completed ? 0.6 : 0.2,
      transparent: true, opacity: 1,
    })
  );
  sphere.castShadow = true;
  sphere.userData = { domainId: d.id, slug: d.slug, title: d.title,
    desc: d.description, group, color, ratio, completed,
    moduleCount: d.modules.length };

  if(completed){
    const glow = new THREE.Mesh(
      new THREE.RingGeometry(1.3, 1.8, 32),
      new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.15, side: THREE.DoubleSide,
      })
    );
    glow.userData.isGlow = true;
    sphere.add(glow);
  }

  const labelDiv = document.createElement('div');
  labelDiv.textContent = `D${String(d.id).padStart(2,'0')} ${d.title}`;
  labelDiv.style.color = '#fff';
  labelDiv.style.fontSize = '12px';
  labelDiv.style.fontWeight = '500';
  labelDiv.style.fontFamily = 'Inter, sans-serif';
  labelDiv.style.textShadow = '0 0 10px rgba(0,0,0,0.9),0 0 4px rgba(0,0,0,0.8)';
  labelDiv.style.padding = '4px 10px';
  labelDiv.style.borderRadius = '6px';
  labelDiv.style.background = 'rgba(11,16,32,0.7)';
  labelDiv.style.border = '1px solid rgba(255,255,255,0.08)';
  labelDiv.style.backdropFilter = 'blur(4px)';
  labelDiv.style.pointerEvents = 'none';
  labelDiv.style.whiteSpace = 'nowrap';
  labelDiv.style.transition = 'transform 0.15s';

  const label = new CSS2DObject(labelDiv);
  label.position.y = -1.8;

  const obj = new THREE.Group();
  obj.add(sphere);
  obj.add(label);
  obj.userData = { domainId: d.id, sphere, label, ...sphere.userData };

  nodeMap.set(d.id, obj);
  nodes.push(obj);
  scene.add(obj);
});

const edgeGroup = new THREE.Group();
scene.add(edgeGroup);

function createEdge(from, to, color = 0x4488ff, opacity = 0.15){
  const curve = new THREE.CatmullRomCurve3([from.clone(), to.clone()]);
  const divisions = 20;
  const positions = new Float32Array((divisions+1)*3);
  const p = new THREE.Vector3();
  for(let i=0;i<=divisions;i++){
    curve.getPoint(i/divisions, p);
    positions[i*3] = p.x;
    positions[i*3+1] = p.y;
    positions[i*3+2] = p.z;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const mat = new THREE.LineBasicMaterial({
    color, transparent: true, opacity, depthWrite: false,
  });
  return new THREE.Line(geo, mat);
}

function updateEdges(){
  while(edgeGroup.children.length) edgeGroup.remove(edgeGroup.children[0]);
  const activeSet = new Set(activeDomainIds);
  domains.forEach(d => {
    d.prerequisites.forEach(preId => {
      if(!activeSet.has(d.id) || !activeSet.has(preId)) return;
      const from = nodeMap.get(preId);
      const to = nodeMap.get(d.id);
      if(!from || !to) return;
      const fg = DOMAIN_GROUP[preId]||'core';
      const color = GROUP_COLORS[fg]||0x4488ff;
      const edge = createEdge(from.position, to.position, color, 0.2);
      edgeGroup.add(edge);
    });
  });
}

function computeLayout(iterations = 80){
  const pos = new Map();
  nodes.forEach(n => {
    const id = n.userData.domainId;
    const angle = (id-1) / domains.length * Math.PI * 2;
    const radius = 8 + (id % 3) * 2;
    pos.set(id, new THREE.Vector3(
      Math.cos(angle) * radius,
      (id % 5 - 2) * 1.5,
      Math.sin(angle) * radius
    ));
  });

  const repulsion = 12;
  const attraction = 0.02;
  const gravity = 0.003;
  const minDist = 3;

  for(let iter=0; iter<iterations; iter++){
    const forces = new Map();
    nodes.forEach(n => forces.set(n.userData.domainId, new THREE.Vector3()));

    const ids = Array.from(pos.keys());
    for(let i=0;i<ids.length;i++){
      for(let j=i+1;j<ids.length;j++){
        const a = pos.get(ids[i]), b = pos.get(ids[j]);
        const diff = new THREE.Vector3().copy(a).sub(b);
        const dist = Math.max(diff.length(), 0.5);
        const force = repulsion / (dist * dist);
        diff.normalize().multiplyScalar(force);
        forces.get(ids[i]).add(diff);
        forces.get(ids[j]).sub(diff);
      }
    }

    domains.forEach(d => {
      d.prerequisites.forEach(preId => {
        const a = pos.get(preId), b = pos.get(d.id);
        if(!a||!b) return;
        const diff = new THREE.Vector3().copy(b).sub(a);
        const dist = diff.length();
        if(dist > minDist + 0.5){
          const force = diff.normalize().multiplyScalar((dist - minDist) * attraction);
          forces.get(preId).add(force);
          forces.get(d.id).sub(force);
        }
      });
    });

    ids.forEach(id => {
      const p = pos.get(id);
      forces.get(id).add(new THREE.Vector3().copy(p).multiplyScalar(-gravity));
    });

    const maxMove = 0.5;
    ids.forEach(id => {
      const f = forces.get(id);
      const len = f.length();
      if(len > maxMove) f.multiplyScalar(maxMove / len);
      pos.get(id).add(f);
    });
  }

  const center = new THREE.Vector3();
  nodes.forEach(n => center.add(pos.get(n.userData.domainId)));
  center.divideScalar(nodes.length);
  nodes.forEach(n => pos.get(n.userData.domainId).sub(center));

  nodes.forEach(n => {
    const p = pos.get(n.userData.domainId);
    n.position.copy(p);
  });
}

computeLayout(100);

function createGlowEdges(){
  const activeSet = new Set(activeDomainIds);
  domains.forEach(d => {
    d.prerequisites.forEach(preId => {
      if(!activeSet.has(d.id)||!activeSet.has(preId)) return;
      const from = nodeMap.get(preId);
      const to = nodeMap.get(d.id);
      if(!from||!to) return;
      const mid = new THREE.Vector3().copy(from.position).add(to.position).multiplyScalar(0.5);
      mid.y += 0.3;
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(0.06, 8, 8),
        new THREE.MeshBasicMaterial({
          color: 0x4488ff, transparent: true, opacity: 0.3,
        })
      );
      dot.position.copy(mid);
      edgeGroup.add(dot);
    });
  });
}

let activeDomainIds = new Set(domains.map(d=>d.id));
let activeFilter = 'all';

function applyFilter(filter){
  activeFilter = filter;
  document.querySelectorAll('#map-ui button').forEach(b => b.classList.remove('active'));
  const btn = document.querySelector(`#map-ui button[data-filter="${filter}"]`);
  if(btn) btn.classList.add('active');

  if(filter === 'all'){
    activeDomainIds = new Set(domains.map(d=>d.id));
  } else if(filter === 'core'){
    activeDomainIds = new Set([1,2,3,4]);
  } else if(filter === 'systems'){
    activeDomainIds = new Set([5,6,7]);
  } else if(filter === 'language'){
    activeDomainIds = new Set([8,9]);
  } else if(filter === 'lang-impl'){
    activeDomainIds = new Set([11,12,13]);
  } else if(filter === 'network'){
    activeDomainIds = new Set([10]);
  } else if(filter === 'backend'){
    activeDomainIds = new Set([10,11,12,13,14,15,16,17,20,23,24,25]);
  } else if(filter === 'architecture'){
    activeDomainIds = new Set([15]);
  } else if(filter === 'data'){
    activeDomainIds = new Set([16,26]);
  } else if(filter === 'distributed'){
    activeDomainIds = new Set([17]);
  } else if(filter === 'cloud'){
    activeDomainIds = new Set([10,17,18,19,20,21,22,23,24]);
  } else if(filter === 'delivery'){
    activeDomainIds = new Set([20]);
  } else if(filter === 'reliability'){
    activeDomainIds = new Set([21,22]);
  } else if(filter === 'ai'){
    activeDomainIds = new Set([1,16,17,26,27,28,29,37,38]);
  } else if(filter === 'security'){
    activeDomainIds = new Set([24]);
  } else if(filter === 'product'){
    activeDomainIds = new Set([15,21,25,30,31,32]);
  } else if(filter === 'physical'){
    activeDomainIds = new Set([1,5,7,27,29,34,35,36,37,38]);
  } else if(tracks[filter]){
    activeDomainIds = new Set(tracks[filter]);
  }

  nodes.forEach(n => {
    const id = n.userData.domainId;
    const visible = activeDomainIds.has(id);
    n.visible = visible;
    if(visible){
      n.userData.sphere.material.opacity = 1;
    }
  });
  updateEdges();
  createGlowEdges();
  updateInfoVisibility();
}

document.querySelectorAll('#map-ui button[data-filter]').forEach(btn => {
  btn.addEventListener('click', () => applyFilter(btn.dataset.filter));
});

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let hoveredNode = null;

renderer.domElement.addEventListener('pointermove', e => {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
});

let pointerStart = null;
renderer.domElement.addEventListener('pointerdown', e => {
  pointerStart = { x: e.clientX, y: e.clientY };
});
renderer.domElement.addEventListener('pointerup', e => {
  if(!pointerStart) return;
  const dx = e.clientX - pointerStart.x, dy = e.clientY - pointerStart.y;
  pointerStart = null;
  if(Math.sqrt(dx*dx+dy*dy) > 6) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  const y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(new THREE.Vector2(x, y), camera);
  const spheres = nodes.filter(n => n.visible).map(n => n.userData.sphere);
  const intersects = raycaster.intersectObjects(spheres);
  if(intersects.length > 0){
    const hit = intersects[0].object;
    const id = hit.userData.domainId;
    const domain = domains.find(d => d.id === id);
    if(domain) window.location.href = `${C.basePrefix||''}domains/${domain.slug}/index.html`;
  }
});

function updateInfoVisibility(){
  const panel = document.getElementById('info-panel');
  if(!hoveredNode && !activeDomainIds) { panel.classList.remove('visible'); return; }
  if(hoveredNode && activeDomainIds.has(hoveredNode.userData.domainId)){
    panel.classList.add('visible');
  } else {
    panel.classList.remove('visible');
  }
}

function updateHUD(){
  const completed = getCompletedLessonIds().size;
  document.getElementById('hud-count').textContent = completed;
  const pct = Math.round((completed / 1140) * 100);
  document.getElementById('hud-bar').style.width = Math.min(pct, 100) + '%';
}

function buildLegend(){
  const seen = new Set();
  let html = '';
  domains.forEach(d => {
    const g = DOMAIN_GROUP[d.id]||'core';
    if(seen.has(g)) return;
    seen.add(g);
    const color = GROUP_COLORS[g]||0x60a5fa;
    const hex = '#' + color.toString(16).padStart(6,'0');
    const label = GROUP_LABELS[g]||g;
    html += `<div class="legend-item"><div class="legend-dot" style="background:${hex}"></div>${label}</div>`;
  });
  document.getElementById('legend').innerHTML = html;
}
buildLegend();

document.getElementById('legend-toggle').addEventListener('click', () => {
  const l = document.getElementById('legend');
  const btn = document.getElementById('legend-toggle');
  const isOpen = l.classList.toggle('show');
  btn.textContent = isOpen ? '凡例 ▾' : '凡例 ▸';
});

function animate(){
  requestAnimationFrame(animate);

  raycaster.setFromCamera(pointer, camera);
  const spheres = nodes.filter(n => n.visible).map(n => n.userData.sphere);
  const intersects = raycaster.intersectObjects(spheres);

  if(intersects.length > 0){
    const hit = intersects[0].object;
    const id = hit.userData.domainId;
    const node = nodes.find(n => n.userData.domainId === id);
    if(node && node !== hoveredNode){
      if(hoveredNode){
        const hs = hoveredNode.userData.sphere;
        hs.material.emissiveIntensity = hoveredNode.userData.completed ? 0.6 : 0.15;
        hs.scale.set(1, 1, 1);
        const hl = hoveredNode.userData.label;
        hl.element.style.transform = 'scale(1)';
      }
      hoveredNode = node;
      const s = node.userData.sphere;
      s.material.emissiveIntensity = 0.8;
      s.scale.set(1.25, 1.25, 1.25);
      const l = node.userData.label;
      l.element.style.transform = 'scale(1.15)';

      const panel = document.getElementById('info-panel');
      document.getElementById('info-title').textContent = node.userData.title;
      document.getElementById('info-desc').textContent = node.userData.desc;
      const meta = document.getElementById('info-meta');
      meta.innerHTML = `<span class="badge">D${String(id).padStart(2,'0')}</span> <span class="badge">${node.userData.moduleCount} Modules</span> <span class="badge level">${GROUP_LABELS[DOMAIN_GROUP[id]]||''}</span> <span class="badge" style="color:${node.userData.completed?'#4ade80':'#fb923c'}">${node.userData.completed?'完了済':'未完了'} ${Math.round(node.userData.ratio*100)}%</span>`;
      panel.classList.add('visible');
      controls.autoRotate = false;
    }
  } else {
    if(hoveredNode){
      const hs = hoveredNode.userData.sphere;
      hs.material.emissiveIntensity = hoveredNode.userData.completed ? 0.6 : 0.15;
      hs.scale.set(1, 1, 1);
      const hl = hoveredNode.userData.label;
      hl.element.style.transform = 'scale(1)';
      hoveredNode = null;
      document.getElementById('info-panel').classList.remove('visible');
      setTimeout(() => { if(!hoveredNode) controls.autoRotate = true; }, 3000);
    }
  }

  controls.update();
  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
}

function onResize(){
  const w = container.clientWidth;
  const h = container.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  labelRenderer.setSize(w, h);
}
window.addEventListener('resize', onResize);

updateHUD();
applyFilter('all');

setTimeout(() => {
  const hint = document.getElementById('hint');
  if(hint) hint.style.opacity = '0';
}, 5000);

animate();
