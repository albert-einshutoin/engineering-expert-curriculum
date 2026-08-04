import { CURRICULUM } from './curriculum-data.js';

const PROGRESS_KEY = 'engineering-curriculum-progress-v1';
const SERVED_KEY = 'engineering-curriculum-served-v1';

function loadStoredObject(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || '{}');
  } catch {
    return {};
  }
}

function saveServed(value) {
  localStorage.setItem(SERVED_KEY, JSON.stringify(value));
}

// Curriculum content is repository-controlled, but escaping here keeps a
// future content-only contribution from becoming executable markup.
function escapeHtml(value) {
  const node = document.createElement('span');
  node.textContent = String(value);
  return node.innerHTML;
}

function isUnlocked(lesson, progress) {
  if (lesson.level === 1) return true;
  const prerequisite = CURRICULUM.lessons.find(item => (
    item.domainId === lesson.domainId
    && item.moduleIndex === lesson.moduleIndex
    && item.level === lesson.level - 1
  ));
  return !prerequisite || progress[prerequisite.id]?.completed === true;
}

// FNV-1a keeps the daily order stable without adding a random or remote source.
function hashString(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function seededSort(items, seed) {
  return [...items].sort(
    (left, right) => hashString(seed + left.id) - hashString(seed + right.id),
  );
}

function localDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function setupDaily() {
  const form = document.querySelector('[data-daily-form]');
  const output = document.querySelector('[data-daily-output]');
  if (!form || !output) return;

  // A daily recommendation follows the learner's calendar, not the UTC day.
  const dateKey = localDateKey(new Date());
  const render = (force = false) => {
    const count = Math.min(5, Math.max(1, Number(form.elements.count.value || 3)));
    const track = form.elements.track.value;
    const progress = loadStoredObject(PROGRESS_KEY);
    const served = loadStoredObject(SERVED_KEY);
    const selectionKey = `${dateKey}:${track}:${count}`;
    const storedIds = force ? null : served[selectionKey];
    let picks = Array.isArray(storedIds)
      ? storedIds.map(id => CURRICULUM.lessons.find(item => item.id === id)).filter(Boolean)
      : [];

    if (!picks.length) {
      let candidates = CURRICULUM.lessons.filter(
        lesson => !progress[lesson.id]?.completed && isUnlocked(lesson, progress),
      );
      if (track !== 'balanced') {
        const trackDomains = CURRICULUM.tracks[track] || [];
        const focused = candidates.filter(lesson => trackDomains.includes(lesson.domainId));
        if (focused.length >= count) candidates = focused;
      }
      const historicallyServed = new Set(Object.values(served).flat());
      const fresh = candidates.filter(lesson => !historicallyServed.has(lesson.id));
      const previouslyServed = candidates.filter(
        lesson => historicallyServed.has(lesson.id),
      );
      const seed = force ? `${dateKey}:${track}:${Date.now()}` : `${dateKey}:${track}`;
      const orderedFresh = seededSort(fresh, seed);
      const orderedPreviouslyServed = seededSort(previouslyServed, seed);
      picks = [...orderedFresh, ...orderedPreviouslyServed].slice(0, count);
      served[selectionKey] = picks.map(lesson => lesson.id);
      saveServed(served);
    }

    output.innerHTML = picks.length
      ? picks.map((lesson, index) => `
        <article class="daily-item">
          <div class="small">${index + 1}/${picks.length} · ${escapeHtml(lesson.id)} · ${escapeHtml(lesson.levelLabel)}</div>
          <h3><a href="catalog/index.html#${lesson.id.toLowerCase()}">${escapeHtml(lesson.title)}</a></h3>
          <p>${escapeHtml(lesson.domainTitle)} / ${escapeHtml(lesson.moduleTitle)}</p>
          <div class="badges">${lesson.concepts.map(concept => `<span class="badge">${escapeHtml(concept)}</span>`).join('')}</div>
        </article>`).join('')
      : '<p>選択可能な未完了Lessonがありません。進捗を取り消すか、履歴をリセットしてください。</p>';
  };

  form.addEventListener('submit', event => {
    event.preventDefault();
    render(false);
  });
  document.querySelector('[data-daily-regenerate]')?.addEventListener('click', () => render(true));
  render(false);
}

setupDaily();
