(function () {
  'use strict';

  var ROOT = '[data-visualization-id][data-simulation-kind][data-interaction-mode]';
  var STATE = '.visualization__simulation-states [data-state-id]';
  var MODEL_NODE = '.visualization__model-node[data-node-id]';
  var MODEL_EDGE = '.visualization__model-edge[data-edge-id]';
  var CONTROLS = '.visualization__controls';
  var STATUS = '.visualization__current-status';
  var STATE_CLASSES = ['is-enhanced', 'is-active', 'is-complete', 'has-runtime-error'];
  var controllers = new Map();

  function values(list) { return Array.prototype.slice.call(list); }
  function hasUnique(elements, name) {
    var seen = new Set();
    return elements.every(function (element) {
      var value = element.getAttribute(name);
      if (!value || seen.has(value)) { return false; }
      seen.add(value);
      return true;
    });
  }
  function capture(element, controller) {
    return {
      classes: STATE_CLASSES.map(function (name) { return element.classList.contains(name); }),
      hidden: element === controller.controls ? element.hidden : null,
      disabled: 'disabled' in element ? element.disabled : null,
      current: controller.states.indexOf(element) >= 0 ? element.getAttribute('aria-current') : undefined,
      pressed: element === controller.playButton ? element.getAttribute('aria-pressed') : undefined,
      text: element === controller.status || element === controller.playButton ? element.textContent : undefined
    };
  }
  function Controller(root) {
    this.root = root;
    this.controls = root.querySelector(CONTROLS);
    this.states = values(root.querySelectorAll(STATE));
    this.nodes = values(root.querySelectorAll(MODEL_NODE));
    this.edges = values(root.querySelectorAll(MODEL_EDGE));
    this.status = root.querySelector(STATUS);
    this.playButton = this.controls ? this.controls.querySelector('[data-action="play"]') : null;
    this.speed = this.controls ? this.controls.querySelector('select[data-action="speed"]') : null;
    this.mutable = [root, this.controls, this.status]
      .concat(this.states, this.nodes, this.edges)
      .concat(values(this.controls ? this.controls.querySelectorAll('button, select, input, fieldset') : []))
      .filter(Boolean);
    this.snapshot = new Map();
    this.timer = null;
    this.index = 0;
    this.playing = false;
    this.reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // Snapshot before the first visible mutation so a partial initialization
    // can return to the complete renderer-owned fallback transactionally.
    this.mutable.forEach(function (element) { this.snapshot.set(element, capture(element, this)); }, this);
  }
  Controller.prototype.validate = function () {
    var mode = this.root.getAttribute('data-interaction-mode');
    var intervalSource = this.root.getAttribute('data-default-interval-ms');
    var interval = Number(intervalSource);
    var expected = {
      scenario: ['apply', 'reset'],
      stepper: ['next', 'previous', 'reset'],
      playback: ['next', 'pause', 'play', 'previous', 'reset'],
      hybrid: ['apply', 'next', 'pause', 'play', 'previous', 'reset'],
      explorer: ['apply', 'next', 'previous', 'reset']
    }[mode];
    var actions = values(this.controls ? this.controls.querySelectorAll('button[data-action]') : [])
      .map(function (button) { return button.getAttribute('data-action'); }).sort();
    if (!this.controls || !this.status || !this.states.length || this.states.length > 64 ||
        !hasUnique(this.states, 'data-state-id') || !hasUnique(this.nodes, 'data-node-id') ||
        !hasUnique(this.edges, 'data-edge-id') || !expected || actions.join(',') !== expected.sort().join(',') ||
        intervalSource === null || !Number.isInteger(interval) || interval < 250 || interval > 10000 ||
        ((mode === 'playback' || mode === 'hybrid') !== Boolean(this.speed)) ||
        (this.speed && ['0.5', '1', '2'].indexOf(this.speed.value) < 0)) {
      throw new Error('invalid visualization DOM');
    }
    this.interval = interval;
  };
  Controller.prototype.stop = function () {
    // A controller owns at most one timeout; clearing it before every state
    // boundary keeps independent figures idle and prevents reset leaks.
    if (this.timer !== null) { window.clearTimeout(this.timer); this.timer = null; }
    this.playing = false;
    if (this.playButton) { this.playButton.setAttribute('aria-pressed', 'false'); this.playButton.textContent = '再生'; }
  };
  Controller.prototype.restore = function (failed) {
    this.stop();
    this.snapshot.forEach(function (saved, element) {
      STATE_CLASSES.forEach(function (name, index) { element.classList.toggle(name, saved.classes[index]); });
      if (saved.hidden !== null) { element.hidden = saved.hidden; }
      if (saved.disabled !== null) { element.disabled = saved.disabled; }
      if (saved.current !== undefined) {
        if (saved.current === null) { element.removeAttribute('aria-current'); } else { element.setAttribute('aria-current', saved.current); }
      }
      if (saved.pressed !== undefined) {
        if (saved.pressed === null) { element.removeAttribute('aria-pressed'); } else { element.setAttribute('aria-pressed', saved.pressed); }
      }
      if (saved.text !== undefined) { element.textContent = saved.text; }
    });
    if (failed) {
      this.root.classList.add('has-runtime-error');
      if (this.controls) { this.controls.hidden = true; }
      if (this.status) { this.status.textContent = '動的表示を利用できません。静的図を表示しています。'; }
    }
  };
  Controller.prototype.apply = function (index, announce) {
    if (index < 0 || index >= this.states.length) { return; }
    this.index = index;
    this.states.forEach(function (state, ordinal) {
      var active = ordinal === index;
      state.classList.toggle('is-active', active);
      if (active) { state.setAttribute('aria-current', 'step'); } else { state.removeAttribute('aria-current'); }
    });
    var state = this.states[index];
    var activeNodes = new Set(values(state.querySelectorAll('.visualization__state-node[data-node-id]')).map(function (item) { return item.getAttribute('data-node-id'); }));
    var activeEdges = new Set(values(state.querySelectorAll('.visualization__state-edge[data-edge-id]')).map(function (item) { return item.getAttribute('data-edge-id'); }));
    this.nodes.forEach(function (node) { node.classList.toggle('is-active', activeNodes.has(node.getAttribute('data-node-id'))); });
    this.edges.forEach(function (edge) { edge.classList.toggle('is-active', activeEdges.has(edge.getAttribute('data-edge-id'))); });
    this.root.classList.toggle('is-complete', index === this.states.length - 1);
    if (announce) { this.status.textContent = this.states[index].textContent.trim(); }
    if (index === this.states.length - 1) { this.stop(); }
  };
  Controller.prototype.schedule = function () {
    var self = this;
    if (!this.playing || this.reduced || this.timer !== null) { return; }
    this.timer = window.setTimeout(function () {
      self.timer = null;
      try { self.apply(self.index + 1, false); self.schedule(); } catch (error) { self.restore(true); }
    }, this.interval * (this.speed ? { '0.5': 2, '1': 1, '2': 0.5 }[this.speed.value] : 1));
  };
  Controller.prototype.action = function (name) {
    if (name === 'next') { this.stop(); this.apply(Math.min(this.index + 1, this.states.length - 1), true); }
    else if (name === 'previous') { this.stop(); this.apply(Math.max(this.index - 1, 0), true); }
    else if (name === 'reset' || name === 'apply') { this.restore(false); this.initialize(); }
    else if (name === 'pause') { this.stop(); }
    else if (name === 'play' && !this.reduced) {
      this.playing = true;
      if (this.playButton) { this.playButton.setAttribute('aria-pressed', 'true'); this.playButton.textContent = '再生中'; }
      this.schedule();
    }
  };
  Controller.prototype.initialize = function () {
    this.validate();
    this.apply(0, false);
    values(this.controls.querySelectorAll('button, select, input, fieldset')).forEach(function (control) { control.disabled = false; });
    this.controls.hidden = false;
    this.root.classList.add('is-enhanced');
  };
  Controller.prototype.bind = function () {
    var self = this;
    this.controls.addEventListener('click', function (event) {
      var target = event.target.closest('button');
      if (!target || !self.controls.contains(target)) { return; }
      try { self.action(target.getAttribute('data-action')); } catch (error) { self.restore(true); }
    });
    this.controls.addEventListener('change', function (event) {
      if (event.target === self.speed && self.playing) {
        self.stop(); self.playing = true;
        if (self.playButton) { self.playButton.setAttribute('aria-pressed', 'true'); self.playButton.textContent = '再生中'; }
        self.schedule();
      }
    });
  };
  function initialize(root) {
    var controller = new Controller(root);
    // One malformed figure must never prevent later figures from initializing.
    try { controller.initialize(); controller.bind(); controllers.set(root, controller); }
    catch (error) { controller.restore(true); }
  }
  values(document.querySelectorAll(ROOT)).forEach(initialize);
  window.addEventListener('pagehide', function () { controllers.forEach(function (controller) { controller.stop(); }); }, { once: true });
}());
