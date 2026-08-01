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

function fixture(tracker, mode, suffix = '') {
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
  const status = element(tracker, 'p', { 'aria-live': 'polite' }, ['visualization__current-status'], 'static status');
  const controls = element(tracker, 'div', { hidden: '' }, ['visualization__controls']);
  const parameterized = ['scenario', 'hybrid', 'explorer'].includes(mode);
  if (parameterized) {
    const select = element(tracker, 'select', { 'data-parameter-id': 'choice', disabled: '', value: 'a' });
    select.value = 'a';
    const optionA = element(tracker, 'option', { value: 'a' }, [], 'A');
    optionA.value = 'a';
    const optionB = element(tracker, 'option', { value: 'b' }, [], 'B');
    optionB.value = 'b';
    select.append(optionA, optionB);
    controls.append(select);
  }
  for (const action of ACTIONS[mode]) {
    controls.append(element(tracker, 'button', { 'data-action': action, disabled: '', type: 'button' }, [], action === 'play' ? '再生' : action));
  }
  if (mode === 'playback' || mode === 'hybrid') {
    const speed = element(tracker, 'select', { 'data-action': 'speed', disabled: '', value: '1' });
    speed.value = '1';
    controls.append(speed);
  }

  const addState = (id, index, parameter, option, nodeId, edgeId) => {
    const state = element(tracker, 'li', { 'data-state-id': id, 'data-step-index': String(index) }, [], id);
    if (parameter) { state.append(code(tracker, 'visualization__state-condition', parameter, option)); }
    if (nodeId) { state.append(element(tracker, 'code', { 'data-node-id': nodeId }, ['visualization__state-node'], nodeId)); }
    if (edgeId) { state.append(element(tracker, 'code', { 'data-edge-id': edgeId }, ['visualization__state-edge'], edgeId)); }
    statesList.append(state);
  };
  const addTransition = (id, from, to, parameter, option) => {
    const transition = element(tracker, 'tr', { 'data-transition-id': id, 'data-from-state-id': from, 'data-to-state-id': to }, ['visualization__simulation-transition']);
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
    addTransition('to-a', 'state-0', 'state-a', 'choice', 'a');
    addTransition('to-b', 'state-0', 'state-b', 'choice', 'b');
    addOutcome('outcome-a', 'state-a');
    addOutcome('outcome-b', 'state-b');
  } else {
    addState('state-0', 0, null, null, 'node-0', null);
    addState('state-1', 1, null, null, 'node-1', 'edge-0');
    addState('state-2', 2, null, null, 'node-2', 'edge-1');
    addTransition('to-1', 'state-0', 'state-1', null, null);
    addTransition('to-2', 'state-1', 'state-2', null, null);
    addOutcome('done', 'state-2');
  }
  root.append(...nodes, ...edges, statesList, transitionsTable, outcomesTable, status, controls);
  return { root, controls, status, statesList, nodes, edges };
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
function parameter(fixtureValue) { return fixtureValue.controls.querySelector('select[data-parameter-id]'); }
function controlListenerCount(fixtureValue) { return fixtureValue.controls.listenerCount(); }

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
  parameter(scenario).value = 'b';
  scenario.controls.dispatchEvent({ type: 'change', target: parameter(scenario) });
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
  click(playback, 'pause');
  assert(tracker.timers.size === 0, 'pause leaked timer');
  parameter(hybrid).value = 'b';
  click(hybrid, 'apply');
  click(hybrid, 'next');
  assert(activeState(hybrid) === 'state-b', 'hybrid did not select path');
  parameter(explorer).value = 'b';
  click(explorer, 'apply');
  assert(activeState(explorer) === 'state-b', 'explorer did not highlight selection');
  assert(explorer.nodes[2].classList.contains('is-active'), 'explorer node highlight missing');
  assert(explorer.edges[1].classList.contains('is-active'), 'explorer edge highlight missing');
  assert(activeState(stepper) === 'state-0', 'figures were not isolated');
  window.dispatchEvent({ type: 'pagehide', target: window });
  assert(fixtures.every((item) => controlListenerCount(item) === 0), 'pagehide leaked listeners');
  assert(tracker.timers.size === 0, 'pagehide leaked timers');
}

function runReducedMotion() {
  const tracker = new Tracker();
  const value = fixture(tracker, 'playback');
  environment(tracker, [value], true);
  click(value, 'play');
  assert(tracker.timers.size === 0, 'reduced motion started timer');
  assert(activeState(value) === 'state-0', 'reduced motion advanced state');
}

function runValidationMutations() {
  const mutations = [
    (value) => value.root.attributes.set('data-simulation-kind', 'unknown'),
    (value) => value.root.attributes.set('data-interaction-mode', 'unknown'),
    (value) => value.root.attributes.set('data-default-interval-ms', '249'),
    (value) => value.statesList.children[1].attributes.set('data-state-id', 'state-0'),
    (value) => value.statesList.children[1].attributes.set('data-step-index', '9'),
    (value) => value.statesList.children[1].children.find((item) => item.classList.contains('visualization__state-node')).attributes.set('data-node-id', 'missing'),
    (value) => value.root.querySelector('.visualization__simulation-transition').attributes.set('data-to-state-id', 'missing'),
    (value) => value.controls.children.find((item) => item.tag === 'button').attributes.set('data-action', 'play'),
  ];
  for (let mutationIndex = 0; mutationIndex < mutations.length; mutationIndex += 1) {
    const mutate = mutations[mutationIndex];
    const tracker = new Tracker();
    const value = fixture(tracker, 'stepper');
    mutate(value);
    environment(tracker, [value]);
    assert(tracker.mutations === 0, `invalid DOM ${mutationIndex} was visibly mutated count=${tracker.mutations}`);
    assert(value.controls.hidden, 'invalid DOM revealed controls');
    assert(controlListenerCount(value) === 0, 'invalid DOM leaked listener');
  }
}

function actionSequence(value, tracker) {
  click(value, 'next');
  click(value, 'previous');
  click(value, 'play');
  tracker.flushOne();
  click(value, 'pause');
  click(value, 'reset');
}

function runFaultMatrix() {
  const countTracker = new Tracker();
  const countFixture = fixture(countTracker, 'playback');
  const countWindow = environment(countTracker, [countFixture]);
  actionSequence(countFixture, countTracker);
  const mutationCount = countTracker.mutations;
  countWindow.dispatchEvent({ type: 'pagehide', target: countWindow });
  assert(mutationCount > 20, 'fault matrix did not cover mutations');
  for (let fault = 1; fault <= mutationCount; fault += 1) {
    const tracker = new Tracker();
    tracker.failAt = fault;
    const value = fixture(tracker, 'playback', `-${fault}`);
    const window = environment(tracker, [value]);
    actionSequence(value, tracker);
    window.dispatchEvent({ type: 'pagehide', target: window });
    assert(controlListenerCount(value) === 0, `mutation ${fault} leaked listeners`);
    assert(tracker.timers.size === 0, `mutation ${fault} leaked timer`);
    assert(value.controls.hidden, `mutation ${fault} did not restore controls`);
  }
  const listenerTracker = new Tracker();
  listenerTracker.failListenerAt = 2;
  const listenerFixture = fixture(listenerTracker, 'stepper');
  environment(listenerTracker, [listenerFixture]);
  assert(listenerTracker.mutations === 0, 'listener failure visibly mutated DOM');
  assert(controlListenerCount(listenerFixture) === 0, 'listener failure leaked first listener');

  const timerTracker = new Tracker();
  const timerFixture = fixture(timerTracker, 'playback');
  environment(timerTracker, [timerFixture]);
  click(timerFixture, 'play');
  timerTracker.failAt = timerTracker.mutations + 1;
  timerTracker.flushOne();
  assert(timerTracker.timers.size === 0, 'timer callback failure leaked timer');
  assert(controlListenerCount(timerFixture) === 0, 'timer callback failure leaked listeners');
  assert(timerFixture.controls.hidden, 'timer callback failure did not restore fallback');
  return true;
}

function runResetCycles() {
  const tracker = new Tracker();
  const value = fixture(tracker, 'stepper');
  const window = environment(tracker, [value]);
  const listeners = controlListenerCount(value);
  for (let index = 0; index < 100; index += 1) { click(value, 'reset'); }
  assert(controlListenerCount(value) === listeners, 'reset duplicated listeners');
  assert(tracker.timers.size === 0, 'reset leaked timer');
  window.dispatchEvent({ type: 'pagehide', target: window });
  assert(controlListenerCount(value) === 0, 'reset fixture leaked listeners');
}

runModes();
runReducedMotion();
runValidationMutations();
const faultMatrix = runFaultMatrix();
runResetCycles();
process.stdout.write(JSON.stringify({
  modes: ['scenario', 'stepper', 'playback', 'hybrid', 'explorer'],
  faultMatrix,
  listenerLeaks: 0,
  timerLeaks: 0,
  resetCycles: 100,
}));
