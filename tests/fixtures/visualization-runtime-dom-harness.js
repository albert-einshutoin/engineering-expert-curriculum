'use strict';

const fs = require('fs');
const vm = require('vm');

const runtimePath = process.argv[2];
if (!runtimePath) { throw new Error('runtime path is required'); }
const runtime = fs.readFileSync(runtimePath, 'utf8');

function assert(condition, message) {
  if (!condition) { throw new Error(message); }
}

class Tracker {
  constructor() {
    this.active = false;
    this.mutations = 0;
    this.failAt = null;
    this.listenerAdds = 0;
    this.failListenerAt = null;
    this.timers = new Map();
    this.nextTimer = 1;
  }
  mutation() {
    if (!this.active) { return; }
    this.mutations += 1;
    if (this.mutations === this.failAt) { throw new Error('injected mutation fault'); }
  }
  listener() {
    if (!this.active) { return; }
    this.listenerAdds += 1;
    if (this.listenerAdds === this.failListenerAt) { throw new Error('injected listener fault'); }
  }
  setTimeout(callback) {
    const id = this.nextTimer++;
    this.timers.set(id, callback);
    return id;
  }
  clearTimeout(id) { this.timers.delete(id); }
  flushOne() {
    const first = this.timers.entries().next();
    if (first.done) { return false; }
    const [id, callback] = first.value;
    this.timers.delete(id);
    callback();
    return true;
  }
}

class EventTarget {
  constructor(tracker) { this.tracker = tracker; this.listeners = new Map(); }
  addEventListener(type, handler, options) {
    this.tracker.listener();
    if (!this.listeners.has(type)) { this.listeners.set(type, []); }
    this.listeners.get(type).push({ handler, once: Boolean(options && options.once) });
  }
  removeEventListener(type, handler) {
    const items = this.listeners.get(type) || [];
    this.listeners.set(type, items.filter((item) => item.handler !== handler));
  }
  dispatchEvent(event) {
    event.target = event.target || this;
    for (const item of [...(this.listeners.get(event.type) || [])]) {
      item.handler.call(this, event);
      if (item.once) { this.removeEventListener(event.type, item.handler); }
    }
  }
  listenerCount() {
    let count = 0;
    for (const items of this.listeners.values()) { count += items.length; }
    return count;
  }
}

class ClassList {
  constructor(owner, tracker, initial = []) { this.owner = owner; this.tracker = tracker; this.values = new Set(initial); }
  contains(name) { return this.values.has(name); }
  add(name) { this.tracker.mutation(); this.values.add(name); }
  toggle(name, force) {
    this.tracker.mutation();
    const enabled = force === undefined ? !this.values.has(name) : Boolean(force);
    if (enabled) { this.values.add(name); } else { this.values.delete(name); }
    return enabled;
  }
  toString() { return [...this.values].sort().join(' '); }
}

function simpleMatch(element, selector) {
  let source = selector.trim();
  if (source.includes(' ')) {
    const parts = source.split(/\s+/);
    source = parts.pop();
    const ancestorSelector = parts.join(' ');
    let parent = element.parent;
    let found = false;
    while (parent) {
      if (simpleMatch(parent, ancestorSelector)) { found = true; break; }
      parent = parent.parent;
    }
    if (!found) { return false; }
  }
  const tag = source.match(/^[a-z]+/);
  if (tag && element.tag !== tag[0]) { return false; }
  for (const match of source.matchAll(/\.([A-Za-z0-9_-]+)/g)) {
    if (!element.classList.contains(match[1])) { return false; }
  }
  for (const match of source.matchAll(/\[([A-Za-z0-9_-]+)(?:="([^"]*)")?\]/g)) {
    if (!element.attributes.has(match[1])) { return false; }
    if (match[2] !== undefined && element.getAttribute(match[1]) !== match[2]) { return false; }
  }
  return true;
}

class Element extends EventTarget {
  constructor(tracker, tag, attrs = {}, classes = [], text = '') {
    super(tracker);
    this.tag = tag;
    this.attributes = new Map(Object.entries(attrs));
    this.classList = new ClassList(this, tracker, classes);
    this.children = [];
    this.parent = null;
    this._hidden = Object.hasOwn(attrs, 'hidden');
    this._disabled = Object.hasOwn(attrs, 'disabled');
    this._text = text;
    this.value = attrs.value || '';
    this.checked = Object.hasOwn(attrs, 'checked');
    this.type = attrs.type || '';
    this.tagName = tag.toUpperCase();
  }
  append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } return this; }
  get hidden() { return this._hidden; }
  set hidden(value) { this.tracker.mutation(); this._hidden = Boolean(value); }
  get disabled() { return this._disabled; }
  set disabled(value) { this.tracker.mutation(); this._disabled = Boolean(value); }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  set textContent(value) { this.tracker.mutation(); this._text = String(value); this.children = []; }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  getAttributeNames() { return [...this.attributes.keys()]; }
  setAttribute(name, value) { this.tracker.mutation(); this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.tracker.mutation(); this.attributes.delete(name); }
  contains(other) { for (let item = other; item; item = item.parent) { if (item === this) { return true; } } return false; }
  closest(selector) { for (let item = this; item; item = item.parent) { if (simpleMatch(item, selector)) { return item; } } return null; }
  querySelectorAll(selector) {
    const selectors = selector.split(',').map((item) => item.trim());
    const result = [];
    const visit = (item) => {
      for (const child of item.children) {
        if (selectors.some((part) => simpleMatch(child, part))) { result.push(child); }
        visit(child);
      }
    };
    visit(this);
    return result;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

class Document {
  constructor(roots) { this.roots = roots; }
  querySelectorAll(selector) { return this.roots.filter((root) => simpleMatch(root, selector)); }
}

function element(tracker, tag, attrs, classes, text) { return new Element(tracker, tag, attrs, classes, text); }
function code(tracker, className, parameter, option) {
  return element(tracker, 'code', { 'data-parameter-id': parameter, 'data-option-id': option }, [className], `${parameter}=${option}`);
}

const ACTIONS = {
  scenario: ['apply', 'reset'],
  stepper: ['previous', 'next', 'reset'],
  playback: ['play', 'pause', 'previous', 'next', 'reset'],
  hybrid: ['apply', 'play', 'pause', 'previous', 'next', 'reset'],
  explorer: ['apply', 'previous', 'next', 'reset'],
};

function fixture(tracker, mode, suffix = '', controlKind = 'select') {
  const rootId = `viz-${mode}${suffix}`;
  const root = element(tracker, 'figure', {
    id: rootId,
    'data-visualization-id': rootId,
    'data-simulation-kind': 'request-path',
    'data-interaction-mode': mode,
    'data-initial-state-id': mode === 'scenario' ? 'state-a' : 'state-0',
    'data-default-interval-ms': '250',
  }, ['visualization']);
  const nodes = ['node-0', 'node-1', 'node-2'].map((id) => element(tracker, 'dt', { 'data-node-id': id }, ['visualization__model-node'], id));
  const edges = ['edge-0', 'edge-1'].map((id) => element(tracker, 'li', { 'data-edge-id': id }, ['visualization__model-edge'], id));
  const statesList = element(tracker, 'ol', {}, ['visualization__simulation-states']);
  const transitionsTable = element(tracker, 'tbody');
  const outcomesTable = element(tracker, 'tbody');
  const status = element(tracker, 'p', {}, ['visualization__current-status'], 'static status');
  const announcement = element(tracker, 'p', { 'aria-live': 'polite', 'aria-atomic': 'true' }, ['visualization__announcement']);
  const controls = element(tracker, 'div', { hidden: '' }, ['visualization__controls']);
  const parameterized = ['scenario', 'hybrid', 'explorer'].includes(mode);
  if (parameterized) {
    if (controlKind === 'radio') {
      const radioA = element(tracker, 'input', { id: `${rootId}-a`, 'data-parameter-id': 'choice', disabled: '', type: 'radio', name: `${rootId}-choice`, value: 'a', checked: '' });
      const radioB = element(tracker, 'input', { id: `${rootId}-b`, 'data-parameter-id': 'choice', disabled: '', type: 'radio', name: `${rootId}-choice`, value: 'b' });
      radioA.value = 'a';
      radioA.checked = true;
      radioB.value = 'b';
      controls.append(radioA, radioB);
    } else {
      const select = element(tracker, 'select', { id: `${rootId}-choice`, 'data-parameter-id': 'choice', disabled: '' });
      select.value = 'a';
      const optionA = element(tracker, 'option', { value: 'a', selected: '' }, [], 'A');
      optionA.value = 'a';
      const optionB = element(tracker, 'option', { value: 'b' }, [], 'B');
      optionB.value = 'b';
      select.append(optionA, optionB);
      controls.append(select);
    }
  }
  for (const action of ACTIONS[mode]) {
    controls.append(element(tracker, 'button', { id: `${rootId}-${action}`, 'data-action': action, disabled: '', type: 'button' }, [], action === 'play' ? '再生' : action));
  }
  if (mode === 'playback' || mode === 'hybrid') {
    const speed = element(tracker, 'select', { id: `${rootId}-speed`, 'data-action': 'speed', disabled: '' });
    speed.value = '1';
    const speedHalf = element(tracker, 'option', { value: '0.5' }, [], '0.5x');
    speedHalf.value = '0.5';
    const speedOne = element(tracker, 'option', { value: '1', selected: '' }, [], '1x');
    speedOne.value = '1';
    const speedTwo = element(tracker, 'option', { value: '2' }, [], '2x');
    speedTwo.value = '2';
    speed.append(speedHalf, speedOne, speedTwo);
    controls.append(speed);
  }

  const addState = (id, index, parameter, option, nodeId, edgeId) => {
    const state = element(tracker, 'li', { 'data-state-id': id, 'data-step-index': String(index) }, [], id);
    if (parameter) { state.append(code(tracker, 'visualization__state-condition', parameter, option)); }
    if (nodeId) { state.append(element(tracker, 'code', { 'data-node-id': nodeId }, ['visualization__state-node'], nodeId)); }
    if (edgeId) { state.append(element(tracker, 'code', { 'data-edge-id': edgeId }, ['visualization__state-edge'], edgeId)); }
    statesList.append(state);
  };
  const addTransition = (id, eventName, from, to, parameter, option) => {
    const transition = element(tracker, 'tr', { 'data-transition-id': id, 'data-transition-event': eventName, 'data-from-state-id': from, 'data-to-state-id': to }, ['visualization__simulation-transition']);
    if (parameter) { transition.append(code(tracker, 'visualization__transition-condition', parameter, option)); }
    transitionsTable.append(transition);
  };
  const addOutcome = (id, state) => outcomesTable.append(element(tracker, 'tr', { 'data-outcome-id': id, 'data-state-id': state }, ['visualization__simulation-outcome'], id));

  if (mode === 'scenario') {
    addState('state-a', 0, 'choice', 'a', 'node-0', null);
    addState('state-b', 1, 'choice', 'b', 'node-2', 'edge-1');
    addOutcome('outcome-a', 'state-a');
    addOutcome('outcome-b', 'state-b');
  } else if (mode === 'hybrid' || mode === 'explorer') {
    addState('state-0', 0, null, null, 'node-0', null);
    addState('state-a', 1, 'choice', 'a', 'node-1', 'edge-0');
    addState('state-b', 2, 'choice', 'b', 'node-2', 'edge-1');
    addTransition('to-a', 'parameter-change', 'state-0', 'state-a', 'choice', 'a');
    addTransition('to-b', 'parameter-change', 'state-0', 'state-b', 'choice', 'b');
    addTransition('initial-reset', 'reset', 'state-0', 'state-0', null, null);
    addTransition('a-reset', 'reset', 'state-a', 'state-0', 'choice', 'a');
    addTransition('b-reset', 'reset', 'state-b', 'state-0', 'choice', 'b');
    if (mode === 'hybrid') {
      addState('state-a-done', 3, 'choice', 'a', 'node-2', 'edge-1');
      addState('state-b-done', 4, 'choice', 'b', 'node-2', 'edge-1');
      addTransition('a-next', 'next', 'state-a', 'state-a-done', 'choice', 'a');
      addTransition('b-next', 'next', 'state-b', 'state-b-done', 'choice', 'b');
      addTransition('a-timer', 'timer', 'state-a', 'state-a-done', 'choice', 'a');
      addTransition('b-timer', 'timer', 'state-b', 'state-b-done', 'choice', 'b');
      addTransition('a-done-previous', 'previous', 'state-a-done', 'state-a', 'choice', 'a');
      addTransition('b-done-previous', 'previous', 'state-b-done', 'state-b', 'choice', 'b');
      addTransition('a-done-reset', 'reset', 'state-a-done', 'state-0', 'choice', 'a');
      addTransition('b-done-reset', 'reset', 'state-b-done', 'state-0', 'choice', 'b');
    }
    addOutcome('outcome-a', 'state-a');
    addOutcome('outcome-b', 'state-b');
  } else {
    addState('state-0', 0, null, null, 'node-0', null);
    addState('state-1', 1, null, null, 'node-1', 'edge-0');
    addState('state-2', 2, null, null, 'node-2', 'edge-1');
    const forwardEvent = mode === 'playback' ? 'timer' : 'next';
    addTransition('to-1', forwardEvent, 'state-0', 'state-1', null, null);
    addTransition('to-2', forwardEvent, 'state-1', 'state-2', null, null);
    if (mode === 'playback') {
      addTransition('next-1', 'next', 'state-0', 'state-1', null, null);
      addTransition('next-2', 'next', 'state-1', 'state-2', null, null);
    }
    addTransition('back-1', 'previous', 'state-1', 'state-0', null, null);
    addTransition('back-2', 'previous', 'state-2', 'state-1', null, null);
    addTransition('reset-0', 'reset', 'state-0', 'state-0', null, null);
    addTransition('reset-1', 'reset', 'state-1', 'state-0', null, null);
    addTransition('reset-2', 'reset', 'state-2', 'state-0', null, null);
    addOutcome('done', 'state-2');
  }
  root.append(...nodes, ...edges, statesList, transitionsTable, outcomesTable, status, announcement, controls);
  return { root, controls, status, announcement, statesList, nodes, edges };
}

function environment(tracker, fixtures, reduced = false) {
  const window = new EventTarget(tracker);
  window.setTimeout = (callback) => tracker.setTimeout(callback);
  window.clearTimeout = (id) => tracker.clearTimeout(id);
  window.matchMedia = () => ({ matches: reduced });
  const context = { window, document: new Document(fixtures.map((item) => item.root)), Map, Set, Number, String, Boolean, Array, Error };
  tracker.active = true;
  vm.runInNewContext(runtime, context, { filename: runtimePath });
  return window;
}

function click(fixtureValue, action) {
  const button = fixtureValue.controls.querySelector(`[data-action="${action}"]`);
  fixtureValue.controls.dispatchEvent({ type: 'click', target: button });
}
function activeState(fixtureValue) {
  const active = fixtureValue.statesList.children.filter((state) => state.classList.contains('is-active'));
  assert(active.length === 1, 'expected one active state');
  return active[0].getAttribute('data-state-id');
}
function parameter(fixtureValue) { return fixtureValue.controls.querySelector('select[data-parameter-id]') || fixtureValue.controls.querySelector('input[data-parameter-id]'); }
function setParameter(fixtureValue, selectedValue) {
  const select = fixtureValue.controls.querySelector('select[data-parameter-id]');
  if (select) { select.value = selectedValue; return select; }
  const radios = fixtureValue.controls.querySelectorAll('input[data-parameter-id]');
  radios.forEach((radio) => { radio.checked = radio.value === selectedValue; });
  return radios.find((radio) => radio.checked);
}
function controlListenerCount(fixtureValue) { return fixtureValue.controls.listenerCount(); }
function snapshotObject(root, allowFallback = false) {
  let classes = root.classList.toString();
  let text = root._text;
  if (allowFallback && root.classList.contains('has-runtime-error')) {
    classes = classes.split(' ').filter((name) => name !== 'has-runtime-error').join(' ');
  }
  if (allowFallback && root.classList.contains('visualization__current-status') && text === '動的表示を利用できません。静的図を表示しています。') {
    text = 'static status';
  }
  if (allowFallback && root.classList.contains('visualization__announcement') && text === '動的表示を利用できません。静的図を表示しています。') {
    text = '';
  }
  return {
    tag: root.tag,
    attributes: [...root.attributes].sort(),
    classes,
    hidden: root.hidden,
    disabled: root.disabled,
    value: root.value,
    checked: root.checked,
    text,
    children: root.children.map((child) => snapshotObject(child, allowFallback)),
  };
}
function domSnapshot(root, allowFallback = false) { return JSON.stringify(snapshotObject(root, allowFallback)); }
function snapshotDifference(left, right) {
  let index = 0;
  while (index < left.length && left[index] === right[index]) { index += 1; }
  return `${left.slice(index, index + 80)} != ${right.slice(index, index + 80)}`;
}

function runLoadAbsence() {
  const tracker = new Tracker();
  const value = fixture(tracker, 'stepper');
  assert(value.controls.hidden, 'no-script fallback revealed controls');
  assert(value.controls.querySelectorAll('button, select, input, fieldset').every((control) => control.disabled), 'no-script fallback enabled controls');
  assert(value.status.textContent === 'static status', 'no-script fallback changed status');
  assert(value.statesList.children.every((state) => !state.classList.contains('is-active')), 'no-script fallback selected state');
}

function runModes() {
  const tracker = new Tracker();
  const fixtures = ['scenario', 'stepper', 'playback', 'hybrid', 'explorer'].map((mode) => fixture(tracker, mode));
  const window = environment(tracker, fixtures);
  for (let fixtureIndex = 0; fixtureIndex < fixtures.length; fixtureIndex += 1) {
    const value = fixtures[fixtureIndex];
    assert(value.root.classList.contains('is-enhanced'), `mode ${fixtureIndex} did not enhance classes=${value.root.classList.toString()} mutations=${tracker.mutations}`);
    assert(!value.controls.hidden, 'controls stayed hidden');
    assert(controlListenerCount(value) === 2, 'delegated listeners missing');
  }
  const [scenario, stepper, playback, hybrid, explorer] = fixtures;
  const initialStatus = scenario.status.textContent;
  const changedScenario = setParameter(scenario, 'b');
  scenario.controls.dispatchEvent({ type: 'change', target: changedScenario });
  assert(scenario.status.textContent === initialStatus, 'parameter change announced without action');
  click(scenario, 'apply');
  assert(activeState(scenario) === 'state-b', 'scenario did not resolve selection');
  click(stepper, 'next');
  assert(activeState(stepper) === 'state-1', 'stepper next ignored transition');
  click(stepper, 'previous');
  assert(activeState(stepper) === 'state-0', 'stepper previous ignored path');
  click(playback, 'play');
  assert(tracker.timers.size === 1, 'playback timer missing');
  tracker.flushOne();
  assert(activeState(playback) === 'state-1', 'playback did not advance');
  assert(playback.status.textContent.startsWith('state-1'), 'timer did not synchronize visible status');
  assert(playback.announcement.textContent === '', 'timer produced a live announcement');
  click(playback, 'pause');
  assert(tracker.timers.size === 0, 'pause leaked timer');
  setParameter(hybrid, 'b');
  click(hybrid, 'apply');
  click(hybrid, 'next');
  assert(activeState(hybrid) === 'state-b-done', 'hybrid did not select path');
  setParameter(explorer, 'b');
  click(explorer, 'apply');
  assert(activeState(explorer) === 'state-b', 'explorer did not highlight selection');
  assert(explorer.nodes[2].classList.contains('is-active'), 'explorer node highlight missing');
  assert(explorer.edges[1].classList.contains('is-active'), 'explorer edge highlight missing');
  assert(activeState(stepper) === 'state-0', 'figures were not isolated');
  window.dispatchEvent({ type: 'pagehide', target: window });
  assert(fixtures.every((item) => controlListenerCount(item) === 0), 'pagehide leaked listeners');
  assert(tracker.timers.size === 0, 'pagehide leaked timers');
  assert(window.listenerCount() === 2, 'BFCache lifecycle listeners changed');
}

function runExactTeardown() {
  for (const controlKind of ['select', 'radio']) {
    const tracker = new Tracker();
    const modes = ['scenario', 'stepper', 'playback', 'hybrid', 'explorer'];
    const fixtures = modes.map((mode) => fixture(tracker, mode, `-${controlKind}`, controlKind));
    const baselines = fixtures.map((item) => domSnapshot(item.root));
    const window = environment(tracker, fixtures);
    fixtures.forEach((item, index) => {
      const action = ['apply', 'next', 'next', 'apply', 'apply'][index];
      click(item, action);
    });
    window.dispatchEvent({ type: 'pagehide', target: window });
    fixtures.forEach((item, index) => assert(domSnapshot(item.root) === baselines[index], `pagehide did not restore exact DOM mode=${modes[index]} control=${controlKind}`));
    assert(fixtures.every((item) => controlListenerCount(item) === 0), 'exact teardown leaked listeners');
    assert(tracker.timers.size === 0, 'exact teardown leaked timer');
  }
}

function runReducedMotion() {
  const tracker = new Tracker();
  const value = fixture(tracker, 'playback');
  environment(tracker, [value], true);
  click(value, 'play');
  assert(tracker.timers.size === 0, 'reduced motion started timer');
  assert(activeState(value) === 'state-0', 'reduced motion advanced state');
  for (const action of ['play', 'pause', 'speed']) {
    assert(value.controls.querySelector(`[data-action="${action}"]`).disabled, `reduced motion left ${action} enabled`);
  }
  assert(value.status.textContent.includes('視差低減'), 'reduced motion reason was not visible');
  assert(value.announcement.textContent.includes('視差低減'), 'reduced motion reason was not accessible');
}

function runScenarioResetDefaults() {
  for (const controlKind of ['select', 'radio']) {
    const tracker = new Tracker();
    const value = fixture(tracker, 'scenario', `-${controlKind}-defaults`, controlKind);
    environment(tracker, [value]);
    setParameter(value, 'b');
    click(value, 'apply');
    assert(activeState(value) === 'state-b', 'scenario setup did not select b');
    click(value, 'reset');
    const selected = value.controls.querySelector('select[data-parameter-id]');
    const radios = value.controls.querySelectorAll('input[data-parameter-id]');
    assert(selected ? selected.value === 'a' : radios.find((radio) => radio.value === 'a').checked && !radios.find((radio) => radio.value === 'b').checked, 'scenario reset did not restore default parameter');
    assert(activeState(value) === 'state-a', 'scenario reset did not restore initial state');
  }
}

function runBfcacheLifecycle() {
  const tracker = new Tracker();
  const value = fixture(tracker, 'stepper', '-bfcache');
  const baseline = domSnapshot(value.root);
  const window = environment(tracker, [value]);
  for (let cycle = 0; cycle < 3; cycle += 1) {
    click(value, 'next');
    window.dispatchEvent({ type: 'pagehide', persisted: true, target: window });
    assert(domSnapshot(value.root) === baseline, 'BFCache pagehide did not restore exact DOM');
    assert(controlListenerCount(value) === 0, 'BFCache pagehide leaked control listeners');
    window.dispatchEvent({ type: 'pageshow', persisted: true, target: window });
    assert(value.root.classList.contains('is-enhanced'), 'BFCache pageshow did not reinitialize');
    assert(controlListenerCount(value) === 2, 'BFCache pageshow duplicated listeners');
    assert(tracker.timers.size === 0, 'BFCache lifecycle leaked timer');
  }
  window.dispatchEvent({ type: 'pagehide', persisted: true, target: window });
  tracker.failAt = tracker.mutations + 1;
  window.dispatchEvent({ type: 'pageshow', persisted: true, target: window });
  assert(value.root.classList.contains('has-runtime-error'), 'BFCache reinitialization failure did not expose fallback');
  assert(value.controls.hidden, 'BFCache reinitialization failure exposed controls');
  assert(controlListenerCount(value) === 0, 'BFCache reinitialization failure leaked listeners');
  assert(tracker.timers.size === 0, 'BFCache reinitialization failure leaked timer');
}

function runTerminalPlayback() {
  const tracker = new Tracker();
  const value = fixture(tracker, 'playback', '-terminal');
  environment(tracker, [value]);
  click(value, 'next');
  click(value, 'next');
  const status = value.status.textContent;
  click(value, 'play');
  const play = value.controls.querySelector('[data-action="play"]');
  assert(tracker.timers.size === 0, 'terminal playback scheduled a timer');
  assert(play.getAttribute('aria-pressed') === 'false', 'terminal playback stayed pressed');
  assert(play.textContent === '再生', 'terminal playback kept playing label');
  assert(value.status.textContent === status, 'terminal playback changed status');
}

function runExactEventResolution() {
  const cases = [
    ['to-1', 'timer', 'next'],
    ['back-1', 'timer', 'previous'],
  ];
  for (const [transitionId, replacementEvent, action] of cases) {
    const tracker = new Tracker();
    const value = fixture(tracker, 'stepper', `-${action}`);
    value.root.querySelectorAll('.visualization__simulation-transition').find((item) => item.getAttribute('data-transition-id') === transitionId).attributes.set('data-transition-event', replacementEvent);
    environment(tracker, [value]);
    if (action !== 'next') { click(value, 'next'); }
    const before = activeState(value);
    click(value, action);
    assert(activeState(value) === before, `${action} fell back to array position without its authored edge`);
  }
}

function runValidationMutations() {
  const mutations = [
    ['stepper', (value) => value.root.attributes.set('data-simulation-kind', 'unknown')],
    ['stepper', (value) => value.root.attributes.set('data-interaction-mode', 'unknown')],
    ['stepper', (value) => value.root.attributes.set('data-default-interval-ms', '249')],
    ['stepper', (value) => value.root.attributes.set('data-unexpected', 'x')],
    ['stepper', (value) => value.statesList.children[1].attributes.set('data-state-id', 'state-0')],
    ['stepper', (value) => value.statesList.children[1].attributes.set('data-step-index', '9')],
    ['stepper', (value) => value.statesList.children[1].attributes.set('data-unexpected', 'x')],
    ['stepper', (value) => value.statesList.children[1].children.find((item) => item.classList.contains('visualization__state-node')).attributes.set('data-node-id', 'missing')],
    ['stepper', (value) => value.root.querySelector('.visualization__simulation-transition').attributes.set('data-to-state-id', 'missing')],
    ['stepper', (value) => value.root.querySelector('.visualization__simulation-transition').attributes.delete('data-transition-event')],
    ['stepper', (value) => value.root.querySelector('.visualization__simulation-transition').attributes.set('data-transition-event', 'unknown')],
    ['scenario', (value) => value.root.querySelector('.visualization__state-condition').attributes.delete('data-option-id')],
    ['scenario', (value) => value.root.querySelectorAll('.visualization__state-condition').find((item) => item.getAttribute('data-option-id') === 'b').attributes.set('data-option-id', 'a')],
    ['scenario', (value) => {
      value.statesList.children.pop();
      const outcome = value.root.querySelectorAll('.visualization__simulation-outcome').find((item) => item.getAttribute('data-state-id') === 'state-b');
      outcome.parent.children = outcome.parent.children.filter((item) => item !== outcome);
    }],
    ['scenario', (value, tracker) => {
      const transition = element(tracker, 'tr', { 'data-transition-id': 'forbidden', 'data-transition-event': 'parameter-change', 'data-from-state-id': 'state-a', 'data-to-state-id': 'state-b' }, ['visualization__simulation-transition']);
      value.root.children.filter((item) => item.tag === 'tbody')[0].append(transition);
    }],
    ['stepper', (value) => {
      const transition = value.root.querySelectorAll('.visualization__simulation-transition').find((item) => item.getAttribute('data-transition-id') === 'reset-2');
      transition.parent.children = transition.parent.children.filter((item) => item !== transition);
    }],
    ['stepper', (value) => value.root.querySelectorAll('.visualization__simulation-transition').find((item) => item.getAttribute('data-transition-id') === 'reset-2').attributes.set('data-to-state-id', 'state-1')],
    ['stepper', (value, tracker) => {
      const transition = element(tracker, 'tr', { 'data-transition-id': 'duplicate-reset', 'data-transition-event': 'reset', 'data-from-state-id': 'state-2', 'data-to-state-id': 'state-0' }, ['visualization__simulation-transition']);
      value.root.children.filter((item) => item.tag === 'tbody')[0].append(transition);
    }],
    ['hybrid', (value) => {
      const transition = value.root.querySelectorAll('.visualization__simulation-transition').find((item) => item.getAttribute('data-transition-id') === 'b-done-reset');
      transition.parent.children = transition.parent.children.filter((item) => item !== transition);
    }],
    ['hybrid', (value) => value.root.querySelector('.visualization__transition-condition').attributes.delete('data-parameter-id')],
    ['scenario', (value) => value.root.querySelector('.visualization__state-condition').attributes.set('data-unexpected', 'x')],
    ['scenario', (value) => value.controls.querySelector('option[selected]').attributes.delete('selected')],
    ['scenario', (value) => value.controls.querySelectorAll('input[data-parameter-id]').find((item) => item.value === 'b').attributes.set('checked', ''), 'radio'],
    ['stepper', (value, tracker) => value.controls.append(element(tracker, 'button', { type: 'button', disabled: '' }, [], 'ignored'))],
    ['stepper', (value, tracker) => value.controls.append(element(tracker, 'select', { 'data-action': 'unknown', disabled: '' }))],
    ['stepper', (value) => value.controls.children.find((item) => item.tag === 'button').attributes.set('data-action', 'play')],
    ['stepper', (value) => value.controls.children.find((item) => item.tag === 'button').attributes.set('type', 'submit')],
    ['scenario', (value) => value.controls.querySelector('input[data-parameter-id]').attributes.set('type', 'text'), 'radio'],
  ];
  for (let mutationIndex = 0; mutationIndex < mutations.length; mutationIndex += 1) {
    const [mode, mutate, controlKind = 'select'] = mutations[mutationIndex];
    const tracker = new Tracker();
    const value = fixture(tracker, mode, '', controlKind);
    mutate(value, tracker);
    environment(tracker, [value]);
    assert(tracker.mutations === 0, `invalid DOM ${mutationIndex} was visibly mutated count=${tracker.mutations}`);
    assert(value.controls.hidden, 'invalid DOM revealed controls');
    assert(controlListenerCount(value) === 0, 'invalid DOM leaked listener');
  }
}

function actionSequence(value, tracker, mode) {
  if (mode === 'scenario') {
    click(value, 'apply');
    click(value, 'reset');
  } else if (mode === 'stepper') {
    click(value, 'next');
    click(value, 'previous');
    click(value, 'next');
    click(value, 'reset');
  } else if (mode === 'playback') {
    click(value, 'next');
    click(value, 'previous');
    click(value, 'play');
    tracker.flushOne();
    click(value, 'pause');
    click(value, 'reset');
  } else if (mode === 'hybrid') {
    click(value, 'apply');
    click(value, 'play');
    tracker.flushOne();
    click(value, 'previous');
    click(value, 'next');
    click(value, 'reset');
  } else {
    click(value, 'apply');
    click(value, 'next');
    click(value, 'previous');
    click(value, 'reset');
  }
}

function runFaultMatrix() {
  const configurations = [];
  for (const mode of ['scenario', 'stepper', 'playback', 'hybrid', 'explorer']) {
    configurations.push([mode, 'select']);
    if (['scenario', 'hybrid', 'explorer'].includes(mode)) { configurations.push([mode, 'radio']); }
  }
  for (const [mode, controlKind] of configurations) {
    const countTracker = new Tracker();
    const countFixture = fixture(countTracker, mode, '-count', controlKind);
    const countWindow = environment(countTracker, [countFixture]);
    if (['scenario', 'hybrid', 'explorer'].includes(mode)) { setParameter(countFixture, 'b'); }
    actionSequence(countFixture, countTracker, mode);
    const mutationCount = countTracker.mutations;
    countWindow.dispatchEvent({ type: 'pagehide', target: countWindow });
    assert(mutationCount > 10, `fault matrix did not cover ${mode}`);
    for (let fault = 1; fault <= mutationCount; fault += 1) {
      const tracker = new Tracker();
      tracker.failAt = fault;
      const value = fixture(tracker, mode, `-${controlKind}-${fault}`, controlKind);
      const baseline = domSnapshot(value.root);
      const window = environment(tracker, [value]);
      if (value.root.classList.contains('is-enhanced') && ['scenario', 'hybrid', 'explorer'].includes(mode)) { setParameter(value, 'b'); }
      actionSequence(value, tracker, mode);
      assert(controlListenerCount(value) === 0, `${mode} mutation ${fault} leaked listeners`);
      assert(tracker.timers.size === 0, `${mode} mutation ${fault} leaked timer`);
      assert(value.controls.hidden, `${mode} mutation ${fault} did not restore controls`);
      const restored = domSnapshot(value.root, true);
      assert(restored === baseline, `${mode} mutation ${fault} did not restore exact DOM ${snapshotDifference(restored, baseline)}`);
      window.dispatchEvent({ type: 'pagehide', target: window });
      assert(controlListenerCount(value) === 0, `${mode} mutation ${fault} pagehide leaked listeners`);
      assert(tracker.timers.size === 0, `${mode} mutation ${fault} pagehide leaked timer`);
      assert(domSnapshot(value.root, true) === baseline, `${mode} mutation ${fault} pagehide changed fallback`);
    }
  }
  const listenerTracker = new Tracker();
  listenerTracker.failListenerAt = 2;
  const listenerFixture = fixture(listenerTracker, 'stepper');
  environment(listenerTracker, [listenerFixture]);
  assert(listenerTracker.mutations === 0, 'listener failure visibly mutated DOM');
  assert(controlListenerCount(listenerFixture) === 0, 'listener failure leaked first listener');

  const timerTracker = new Tracker();
  const timerFixture = fixture(timerTracker, 'playback');
  const timerBaseline = domSnapshot(timerFixture.root);
  const timerWindow = environment(timerTracker, [timerFixture]);
  click(timerFixture, 'play');
  timerTracker.failAt = timerTracker.mutations + 1;
  timerTracker.flushOne();
  assert(timerTracker.timers.size === 0, 'timer callback failure leaked timer');
  assert(controlListenerCount(timerFixture) === 0, 'timer callback failure leaked listeners');
  assert(timerFixture.controls.hidden, 'timer callback failure did not restore fallback');
  assert(domSnapshot(timerFixture.root, true) === timerBaseline, 'timer callback failure did not restore exact DOM');
  timerWindow.dispatchEvent({ type: 'pagehide', target: timerWindow });
  assert(controlListenerCount(timerFixture) === 0, 'timer callback pagehide leaked listeners');
  assert(timerTracker.timers.size === 0, 'timer callback pagehide leaked timer');
  assert(domSnapshot(timerFixture.root, true) === timerBaseline, 'timer callback pagehide changed fallback');
  return true;
}

function runResetCycles() {
  for (const controlKind of ['select', 'radio']) {
    for (const mode of ['scenario', 'stepper', 'playback', 'hybrid', 'explorer']) {
      const tracker = new Tracker();
      const value = fixture(tracker, mode, `-${controlKind}-reset`, controlKind);
      const baseline = domSnapshot(value.root);
      const window = environment(tracker, [value]);
      const listeners = controlListenerCount(value);
      for (let index = 0; index < 100; index += 1) { click(value, 'reset'); }
      assert(controlListenerCount(value) === listeners, `${mode} reset duplicated listeners`);
      assert(tracker.timers.size === 0, `${mode} reset leaked timer`);
      window.dispatchEvent({ type: 'pagehide', target: window });
      assert(controlListenerCount(value) === 0, `${mode} reset fixture leaked listeners`);
      assert(domSnapshot(value.root) === baseline, `${mode} reset fixture did not restore exact DOM`);
    }
  }
}

runLoadAbsence();
runModes();
runExactTeardown();
runReducedMotion();
runScenarioResetDefaults();
runBfcacheLifecycle();
runTerminalPlayback();
runExactEventResolution();
runValidationMutations();
const faultMatrix = runFaultMatrix();
runResetCycles();
process.stdout.write(JSON.stringify({
  modes: ['scenario', 'stepper', 'playback', 'hybrid', 'explorer'],
  faultMatrix,
  listenerLeaks: 0,
  timerLeaks: 0,
  resetCycles: 100,
  loadAbsence: true,
}));
