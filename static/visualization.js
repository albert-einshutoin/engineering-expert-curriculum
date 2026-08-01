(function () {
  'use strict';

  var ROOT = '[data-visualization-id][data-simulation-kind][data-interaction-mode]';
  var STATE = '.visualization__simulation-states [data-state-id]';
  var NODE = '.visualization__model-node[data-node-id]';
  var EDGE = '.visualization__model-edge[data-edge-id]';
  var TRANSITION = '.visualization__simulation-transition[data-transition-id]';
  var OUTCOME = '.visualization__simulation-outcome[data-outcome-id]';
  var CONTROLS = '.visualization__controls';
  var STATUS = '.visualization__current-status';
  var CLASSES = ['is-enhanced', 'is-active', 'is-complete', 'has-runtime-error'];
  var KINDS = ['complexity-growth', 'memory-access', 'scheduler-interleaving', 'request-path', 'retry-contract', 'isolation-schedule', 'distributed-failure', 'queue-capacity', 'slo-burn', 'accessible-ui-state', 'migration-phase', 'release-safety'];
  var MODE_ACTIONS = {
    scenario: ['apply', 'reset'],
    stepper: ['next', 'previous', 'reset'],
    playback: ['next', 'pause', 'play', 'previous', 'reset'],
    hybrid: ['apply', 'next', 'pause', 'play', 'previous', 'reset'],
    explorer: ['apply', 'next', 'previous', 'reset']
  };
  var controllers = new Map();

  function values(list) { return Array.prototype.slice.call(list); }
  function attribute(element, name) { return element.getAttribute(name); }
  function unique(elements, name) {
    var seen = new Set();
    return elements.every(function (element) {
      var value = attribute(element, name);
      if (!value || seen.has(value)) { return false; }
      seen.add(value);
      return true;
    });
  }
  function capture(element, controller) {
    return {
      classes: CLASSES.map(function (name) { return element.classList.contains(name); }),
      hidden: element === controller.controls ? element.hidden : null,
      disabled: 'disabled' in element ? element.disabled : null,
      current: controller.states.indexOf(element) >= 0 ? attribute(element, 'aria-current') : undefined,
      pressed: element === controller.playButton ? attribute(element, 'aria-pressed') : undefined,
      text: element === controller.status || element === controller.playButton ? element.textContent : undefined
    };
  }
  function conditionMap(element, selector) {
    var result = new Map();
    values(element.querySelectorAll(selector)).forEach(function (item) {
      var parameter = attribute(item, 'data-parameter-id');
      var option = attribute(item, 'data-option-id');
      if (!parameter || !option || result.has(parameter)) { throw new Error('invalid condition'); }
      result.set(parameter, option);
    });
    return result;
  }
  function matches(conditions, selection) {
    var result = true;
    conditions.forEach(function (option, parameter) {
      if (selection.get(parameter) !== option) { result = false; }
    });
    return result;
  }
  function Controller(root) {
    this.root = root;
    this.controls = root.querySelector(CONTROLS);
    this.status = root.querySelector(STATUS);
    this.states = values(root.querySelectorAll(STATE));
    this.nodes = values(root.querySelectorAll(NODE));
    this.edges = values(root.querySelectorAll(EDGE));
    this.transitionElements = values(root.querySelectorAll(TRANSITION));
    this.outcomeElements = values(root.querySelectorAll(OUTCOME));
    this.playButton = this.controls ? this.controls.querySelector('[data-action="play"]') : null;
    this.speed = this.controls ? this.controls.querySelector('select[data-action="speed"]') : null;
    this.mutable = [root, this.controls, this.status]
      .concat(this.states, this.nodes, this.edges)
      .concat(values(this.controls ? this.controls.querySelectorAll('button, select, input, fieldset') : []))
      .filter(Boolean);
    this.snapshot = new Map();
    this.listeners = [];
    this.timer = null;
    this.playing = false;
    this.enhanced = false;
    this.mutated = false;
    this.index = 0;
    this.path = [];
    this.pathIndex = 0;
    this.reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.mutable.forEach(function (element) { this.snapshot.set(element, capture(element, this)); }, this);
  }
  Controller.prototype.validate = function () {
    var mode = attribute(this.root, 'data-interaction-mode');
    var kind = attribute(this.root, 'data-simulation-kind');
    var intervalSource = attribute(this.root, 'data-default-interval-ms');
    var interval = Number(intervalSource);
    var expected = MODE_ACTIONS[mode];
    var rootId = attribute(this.root, 'id');
    var visualizationId = attribute(this.root, 'data-visualization-id');
    var domIds = [this.root].concat(values(this.root.querySelectorAll('[id]')));
    var actions = values(this.controls ? this.controls.querySelectorAll('button[data-action]') : [])
      .map(function (button) { return attribute(button, 'data-action'); }).sort();
    if (!this.controls || !this.status || !this.states.length || this.states.length > 64 ||
        !rootId || rootId !== visualizationId || !unique(domIds, 'id') || KINDS.indexOf(kind) < 0 || !expected ||
        !unique(this.states, 'data-state-id') || !unique(this.nodes, 'data-node-id') ||
        !unique(this.edges, 'data-edge-id') || this.transitionElements.length > 128 ||
        !unique(this.transitionElements, 'data-transition-id') || !this.outcomeElements.length ||
        this.outcomeElements.length > 64 || !unique(this.outcomeElements, 'data-outcome-id') ||
        actions.join(',') !== expected.slice().sort().join(',') ||
        intervalSource === null || !Number.isInteger(interval) || interval < 250 || interval > 5000 ||
        ((mode === 'playback' || mode === 'hybrid') !== Boolean(this.speed)) ||
        (this.speed && ['0.5', '1', '2'].indexOf(this.speed.value) < 0)) {
      throw new Error('invalid visualization DOM');
    }
    this.mode = mode;
    this.interval = interval;
    this.stateById = new Map();
    this.nodeIds = new Set(this.nodes.map(function (node) { return attribute(node, 'data-node-id'); }));
    this.edgeIds = new Set(this.edges.map(function (edge) { return attribute(edge, 'data-edge-id'); }));
    this.parameters = new Map();
    var parameterControls = values(this.controls.querySelectorAll('select[data-parameter-id], input[data-parameter-id]'));
    parameterControls.forEach(function (control) {
      var parameter = attribute(control, 'data-parameter-id');
      var options = control.tagName === 'SELECT' ? values(control.querySelectorAll('option')).map(function (option) { return option.value; }) : [control.value];
      if (!parameter || !options.length || options.some(function (option) { return !option; })) { throw new Error('invalid parameter control'); }
      if (!this.parameters.has(parameter)) { this.parameters.set(parameter, new Set()); }
      options.forEach(function (option) {
        if (this.parameters.get(parameter).has(option)) { throw new Error('duplicate parameter option'); }
        this.parameters.get(parameter).add(option);
      }, this);
    }, this);
    this.states.forEach(function (state, ordinal) {
      var source = attribute(state, 'data-step-index');
      var id = attribute(state, 'data-state-id');
      if (source === null || String(ordinal) !== source) { throw new Error('invalid step index'); }
      var nodeIds = values(state.querySelectorAll('.visualization__state-node[data-node-id]')).map(function (item) { return attribute(item, 'data-node-id'); });
      var edgeIds = values(state.querySelectorAll('.visualization__state-edge[data-edge-id]')).map(function (item) { return attribute(item, 'data-edge-id'); });
      if (nodeIds.some(function (value) { return !this.nodeIds.has(value); }, this) ||
          edgeIds.some(function (value) { return !this.edgeIds.has(value); }, this)) { throw new Error('dangling active reference'); }
      this.stateById.set(id, { element: state, conditions: conditionMap(state, '.visualization__state-condition[data-parameter-id][data-option-id]'), nodes: new Set(nodeIds), edges: new Set(edgeIds), ordinal: ordinal });
    }, this);
    this.initialId = attribute(this.root, 'data-initial-state-id');
    if (!this.stateById.has(this.initialId)) { throw new Error('dangling initial state'); }
    this.transitions = this.transitionElements.map(function (element) {
      var from = attribute(element, 'data-from-state-id');
      var to = attribute(element, 'data-to-state-id');
      if (!this.stateById.has(from) || !this.stateById.has(to)) { throw new Error('dangling transition'); }
      return { from: from, to: to, conditions: conditionMap(element, '.visualization__transition-condition[data-parameter-id][data-option-id]') };
    }, this);
    this.outcomes = this.outcomeElements.map(function (element) {
      var state = attribute(element, 'data-state-id');
      if (!this.stateById.has(state)) { throw new Error('dangling outcome'); }
      return { state: state, element: element };
    }, this);
    this.stateById.forEach(function (state) {
      state.conditions.forEach(function (option, parameter) {
        if (!this.parameters.has(parameter) || !this.parameters.get(parameter).has(option)) { throw new Error('invalid state condition'); }
      }, this);
    }, this);
    this.transitions.forEach(function (transition) {
      transition.conditions.forEach(function (option, parameter) {
        if (!this.parameters.has(parameter) || !this.parameters.get(parameter).has(option)) { throw new Error('invalid transition condition'); }
      }, this);
    }, this);
    if ((mode === 'scenario' || mode === 'hybrid' || mode === 'explorer') !== Boolean(this.parameters.size)) { throw new Error('invalid parameter set'); }
    this.selection();
    this.buildPath();
  };
  Controller.prototype.selection = function () {
    var result = new Map();
    this.parameters.forEach(function (options, parameter) {
      var controls = values(this.controls.querySelectorAll('[data-parameter-id]')).filter(function (control) { return attribute(control, 'data-parameter-id') === parameter; });
      var selected = controls.filter(function (control) { return control.type === 'radio' ? control.checked : true; });
      if (selected.length !== 1 || !options.has(selected[0].value)) { throw new Error('invalid parameter selection'); }
      result.set(parameter, selected[0].value);
    }, this);
    this.currentSelection = result;
    return result;
  };
  Controller.prototype.buildPath = function () {
    var selection = this.selection();
    var applicable = [];
    this.stateById.forEach(function (state, id) { if (matches(state.conditions, selection)) { applicable.push(id); } });
    if (!applicable.length) { throw new Error('no applicable state'); }
    var start = this.initialId;
    if (this.mode === 'scenario') {
      if (applicable.length !== 1) { throw new Error('ambiguous scenario'); }
      start = applicable[0];
    }
    if (applicable.indexOf(start) < 0) { throw new Error('unavailable initial state'); }
    var path = [start];
    var seen = new Set(path);
    while (path.length <= this.states.length) {
      var current = path[path.length - 1];
      var outgoing = this.transitions.filter(function (transition) { return transition.from === current && matches(transition.conditions, selection) && applicable.indexOf(transition.to) >= 0; });
      if (!outgoing.length) { break; }
      if (outgoing.length !== 1 || seen.has(outgoing[0].to)) { throw new Error('ambiguous transition path'); }
      path.push(outgoing[0].to);
      seen.add(outgoing[0].to);
    }
    if (path.length > this.states.length || (this.mode !== 'scenario' && path.length !== applicable.length)) { throw new Error('incomplete transition path'); }
    this.path = path;
    this.pathIndex = 0;
    return path;
  };
  Controller.prototype.setPlaying = function (playing) {
    this.playing = playing;
    if (this.playButton) {
      this.playButton.setAttribute('aria-pressed', playing ? 'true' : 'false');
      this.playButton.textContent = playing ? '再生中' : '再生';
    }
  };
  Controller.prototype.stop = function () {
    if (this.timer !== null) { window.clearTimeout(this.timer); this.timer = null; }
    this.setPlaying(false);
  };
  Controller.prototype.unbind = function () {
    this.listeners.forEach(function (binding) { binding[0].removeEventListener(binding[1], binding[2]); });
    this.listeners = [];
  };
  Controller.prototype.restore = function () {
    if (this.timer !== null) { window.clearTimeout(this.timer); this.timer = null; }
    this.playing = false;
    this.snapshot.forEach(function (saved, element) {
      CLASSES.forEach(function (name, index) { element.classList.toggle(name, saved.classes[index]); });
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
    this.enhanced = false;
  };
  Controller.prototype.fail = function () {
    var showFallback = this.mutated;
    this.unbind();
    if (showFallback) { this.restore(); }
    else if (this.timer !== null) { window.clearTimeout(this.timer); this.timer = null; }
    if (showFallback && this.root && this.status && this.controls) {
      this.root.classList.add('has-runtime-error');
      this.controls.hidden = true;
      this.status.textContent = '動的表示を利用できません。静的図を表示しています。';
    }
  };
  Controller.prototype.applyState = function (stateId, announce) {
    var selected = this.stateById.get(stateId);
    if (!selected) { throw new Error('unknown state'); }
    this.index = selected.ordinal;
    this.states.forEach(function (state) {
      var active = state === selected.element;
      state.classList.toggle('is-active', active);
      if (active) { state.setAttribute('aria-current', 'step'); } else { state.removeAttribute('aria-current'); }
    });
    this.nodes.forEach(function (node) { node.classList.toggle('is-active', selected.nodes.has(attribute(node, 'data-node-id'))); });
    this.edges.forEach(function (edge) { edge.classList.toggle('is-active', selected.edges.has(attribute(edge, 'data-edge-id'))); });
    this.root.classList.toggle('is-complete', this.pathIndex === this.path.length - 1);
    if (announce) { this.status.textContent = selected.element.textContent.trim(); }
    if (this.pathIndex === this.path.length - 1 && this.playing) { this.stop(); }
  };
  Controller.prototype.schedule = function () {
    var self = this;
    if (!this.playing || this.reduced || this.timer !== null || this.pathIndex >= this.path.length - 1) { return; }
    this.timer = window.setTimeout(function () {
      self.timer = null;
      try {
        self.pathIndex += 1;
        self.applyState(self.path[self.pathIndex], false);
        self.schedule();
      } catch (error) { self.fail(); }
    }, this.interval * (this.speed ? { '0.5': 2, '1': 1, '2': 0.5 }[this.speed.value] : 1));
  };
  Controller.prototype.action = function (name) {
    if (name === 'next') {
      this.stop();
      this.pathIndex = Math.min(this.pathIndex + 1, this.path.length - 1);
      this.applyState(this.path[this.pathIndex], true);
    } else if (name === 'previous') {
      this.stop();
      this.pathIndex = Math.max(this.pathIndex - 1, 0);
      this.applyState(this.path[this.pathIndex], true);
    } else if (name === 'apply') {
      this.stop();
      this.buildPath();
      var target = this.mode === 'scenario' || this.mode === 'explorer' ? this.path[this.path.length - 1] : this.path[0];
      this.pathIndex = this.path.indexOf(target);
      this.applyState(target, true);
    } else if (name === 'reset') {
      this.stop();
      this.buildPath();
      this.applyState(this.path[0], true);
    } else if (name === 'pause') {
      this.stop();
    } else if (name === 'play' && !this.reduced) {
      this.setPlaying(true);
      this.schedule();
    }
  };
  Controller.prototype.bind = function () {
    var self = this;
    function add(target, type, handler) {
      target.addEventListener(type, handler);
      self.listeners.push([target, type, handler]);
    }
    add(this.controls, 'click', function (event) {
      var target = event.target.closest('button');
      if (!target || !self.controls.contains(target)) { return; }
      try { self.action(attribute(target, 'data-action')); } catch (error) { self.fail(); }
    });
    add(this.controls, 'change', function (event) {
      if (event.target === self.speed && self.playing) {
        try { self.stop(); self.setPlaying(true); self.schedule(); } catch (error) { self.fail(); }
      }
    });
  };
  Controller.prototype.initialize = function () {
    this.validate();
    this.bind();
    this.mutated = true;
    this.applyState(this.path[0], false);
    values(this.controls.querySelectorAll('button, select, input, fieldset')).forEach(function (control) { control.disabled = false; });
    this.controls.hidden = false;
    this.root.classList.add('is-enhanced');
    this.enhanced = true;
  };
  Controller.prototype.dispose = function () { this.unbind(); this.restore(); };

  function initialize(root) {
    var controller = new Controller(root);
    try { controller.initialize(); controllers.set(root, controller); }
    catch (error) { controller.fail(); }
  }
  values(document.querySelectorAll(ROOT)).forEach(initialize);
  window.addEventListener('pagehide', function () {
    controllers.forEach(function (controller) { controller.dispose(); });
    controllers.clear();
  }, { once: true });
}());
