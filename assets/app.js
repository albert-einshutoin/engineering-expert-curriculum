(() => {
  const KEY = 'engineering-curriculum-progress-v1';
  const SERVED_KEY = 'engineering-curriculum-served-v1';

  function loadProgress() {
    try { return JSON.parse(localStorage.getItem(KEY) || '{}'); }
    catch { return {}; }
  }
  function saveProgress(data) {
    localStorage.setItem(KEY, JSON.stringify(data));
    window.dispatchEvent(new CustomEvent('curriculum-progress-changed'));
  }
  function loadServed() {
    try { return JSON.parse(localStorage.getItem(SERVED_KEY) || '{}'); }
    catch { return {}; }
  }
  function saveServed(data) { localStorage.setItem(SERVED_KEY, JSON.stringify(data)); }
  function markComplete(id, complete = true) {
    const p = loadProgress();
    p[id] = p[id] || {};
    p[id].completed = complete;
    p[id].completedAt = complete ? new Date().toISOString() : null;
    p[id].reviewCount = p[id].reviewCount || 0;
    p[id].nextReviewAt = complete ? new Date(Date.now() + 7*86400000).toISOString() : null;
    saveProgress(p);
  }
  function isComplete(id) { return !!loadProgress()[id]?.completed; }
  function updateLessonButton() {
    const btn = document.querySelector('[data-complete-lesson]');
    if (!btn) return;
    const id = btn.dataset.completeLesson;
    const done = isComplete(id);
    btn.textContent = done ? '完了を取り消す' : 'このLessonを完了';
    btn.classList.toggle('secondary', done);
    btn.onclick = () => { markComplete(id, !isComplete(id)); updateLessonButton(); };
  }
  function updateStats() {
    if (!window.CURRICULUM) return;
    const p = loadProgress();
    const completed = window.CURRICULUM.lessons.filter(x => p[x.id]?.completed).length;
    const total = window.CURRICULUM.lessons.length;
    document.querySelectorAll('[data-stat-total]').forEach(el => el.textContent = total.toLocaleString());
    document.querySelectorAll('[data-stat-completed]').forEach(el => el.textContent = completed.toLocaleString());
    document.querySelectorAll('[data-stat-percent]').forEach(el => el.textContent = total ? Math.round(completed/total*100) + '%' : '0%');
    document.querySelectorAll('[data-progress-bar]').forEach(el => el.style.width = (total ? completed/total*100 : 0) + '%');
  }
  function setupSearch() {
    const input = document.querySelector('[data-curriculum-search]');
    const target = document.querySelector('[data-search-results]');
    if (!input || !target || !window.CURRICULUM) return;
    const run = () => {
      const q = input.value.trim().toLowerCase();
      if (!q) { target.innerHTML = ''; return; }
      const tokens = q.split(/\s+/).filter(Boolean);
      const items = window.CURRICULUM.lessons.filter(item => {
        const hay = `${item.id} ${item.domainTitle} ${item.moduleTitle} ${item.title} ${item.concepts.join(' ')}`.toLowerCase();
        return tokens.every(t => hay.includes(t));
      }).slice(0, 40);
      target.innerHTML = items.length ? items.map(item => `
        <div class="search-result">
          <a href="${window.CURRICULUM.basePrefix || ''}${item.path}">${item.id} — ${item.title}</a>
          <div class="small">${item.domainTitle} / ${item.moduleTitle} / ${item.levelLabel}</div>
        </div>`).join('') : '<p class="small">該当するLessonがありません。</p>';
    };
    input.addEventListener('input', run);
  }
  function unlocked(lesson, progress) {
    if (lesson.level === 1) return true;
    const prev = window.CURRICULUM.lessons.find(x => x.domainId === lesson.domainId && x.moduleIndex === lesson.moduleIndex && x.level === lesson.level - 1);
    return !prev || !!progress[prev.id]?.completed;
  }
  function hashString(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function seededSort(items, seed) {
    return [...items].sort((a,b) => hashString(seed+a.id) - hashString(seed+b.id));
  }
  function setupDaily() {
    const form = document.querySelector('[data-daily-form]');
    const out = document.querySelector('[data-daily-output]');
    if (!form || !out || !window.CURRICULUM) return;
    const dateKey = new Date().toISOString().slice(0,10);
    const render = (force = false) => {
      const count = Math.min(5, Math.max(1, Number(form.elements.count.value || 3)));
      const track = form.elements.track.value;
      const progress = loadProgress();
      const served = loadServed();
      const todayKey = `${dateKey}:${track}:${count}`;
      let ids = !force ? served[todayKey] : null;
      let picks = ids ? ids.map(id => window.CURRICULUM.lessons.find(x => x.id === id)).filter(Boolean) : [];
      if (!picks.length) {
        let candidates = window.CURRICULUM.lessons.filter(x => !progress[x.id]?.completed && unlocked(x, progress));
        if (track !== 'balanced') {
          const trackDomains = window.CURRICULUM.tracks[track] || [];
          const filtered = candidates.filter(x => trackDomains.includes(x.domainId));
          if (filtered.length >= count) candidates = filtered;
        }
        const historicallyServed = new Set(Object.values(served).flat());
        const fresh = candidates.filter(x => !historicallyServed.has(x.id));
        if (fresh.length >= count) candidates = fresh;
        picks = seededSort(candidates, force ? dateKey + Date.now() : dateKey + track).slice(0, count);
        served[todayKey] = picks.map(x => x.id);
        saveServed(served);
      }
      out.innerHTML = picks.length ? picks.map((item, i) => `
        <article class="daily-item">
          <div class="small">${i+1}/${picks.length} · ${item.id} · ${item.levelLabel}</div>
          <h3><a href="${item.path}">${item.title}</a></h3>
          <p>${item.domainTitle} / ${item.moduleTitle}</p>
          <div class="badges">${item.concepts.map(c => `<span class="badge">${c}</span>`).join('')}</div>
        </article>`).join('') : '<p>選択可能な未完了Lessonがありません。進捗を取り消すか、履歴をリセットしてください。</p>';
    };
    form.addEventListener('submit', e => { e.preventDefault(); render(false); });
    document.querySelector('[data-daily-regenerate]')?.addEventListener('click', () => render(true));
    render(false);
  }
  function setupProgressTools() {
    const exportBtn = document.querySelector('[data-export-progress]');
    if (exportBtn) exportBtn.onclick = () => {
      const payload = { version: 1, exportedAt: new Date().toISOString(), progress: loadProgress(), served: loadServed() };
      const blob = new Blob([JSON.stringify(payload, null, 2)], {type:'application/json'});
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'engineering-curriculum-progress.json'; a.click(); URL.revokeObjectURL(a.href);
    };
    const importInput = document.querySelector('[data-import-progress]');
    if (importInput) importInput.onchange = async () => {
      const file = importInput.files?.[0]; if (!file) return;
      try {
        const payload = JSON.parse(await file.text());
        if (payload.progress) saveProgress(payload.progress);
        if (payload.served) saveServed(payload.served);
        alert('進捗を読み込みました。'); location.reload();
      } catch { alert('進捗ファイルを読み込めませんでした。'); }
    };
    document.querySelector('[data-reset-progress]')?.addEventListener('click', () => {
      if (confirm('すべての完了状態と配信履歴を削除しますか？')) {
        localStorage.removeItem(KEY); localStorage.removeItem(SERVED_KEY); location.reload();
      }
    });
  }
  window.CurriculumProgress = { loadProgress, saveProgress, markComplete, isComplete };
  document.addEventListener('DOMContentLoaded', () => {
    updateLessonButton(); updateStats(); setupSearch(); setupDaily(); setupProgressTools();
  });
  window.addEventListener('curriculum-progress-changed', updateStats);
})();