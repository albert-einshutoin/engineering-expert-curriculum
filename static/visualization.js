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
  var ANNOUNCEMENT = '.visualization__announcement';
  var CLASSES = ['is-enhanced', 'is-active', 'is-complete', 'has-runtime-error'];
  var EVENTS = ['next', 'previous', 'timer', 'parameter-change', 'reset'];
  var KINDS = ['complexity-growth', 'memory-access', 'scheduler-interleaving', 'request-path', 'retry-contract', 'isolation-schedule', 'distributed-failure', 'queue-capacity', 'slo-burn', 'accessible-ui-state', 'migration-phase', 'release-safety'];
  var MODE_ACTIONS = {
    scenario: ['apply', 'reset'],
    stepper: ['next', 'previous', 'reset'],
    playback: ['next', 'pause', 'play', 'previous', 'reset'],
    hybrid: ['apply', 'next', 'pause', 'play', 'previous', 'reset'],
    explorer: ['apply', 'next', 'previous', 'reset']
  };
  var controllers = new Map();

  function values(list) { return Array.from(list); }
  function sameSorted(left, right) {
    if (left.length !== right.length) { return false; }
    var expected = right.concat().sort();
    return left.concat().sort().every(function (value, index) {
      return value === expected[index];
    });
  }
  function attribute(element, name) { return element.getAttribute(name); }
  function exactData(element, expected) {
    // Reject unknown renderer data instead of letting malformed markup silently
    // become an unconditional state or an ignored control.
    var names = element.getAttributeNames().filter(function (name) { return name.indexOf('data-') === 0; }).sort();
    return sameSorted(names, expected);
  }
  function exactAttributes(element, required, optional) {
    var names = element.getAttributeNames().sort();
    var allowed = required.concat(optional || []);
    return required.every(function (name) { return names.indexOf(name) >= 0; }) &&
      names.every(function (name) { return allowed.indexOf(name) >= 0; });
  }
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
      text: element === controller.status || element === controller.announcement || element === controller.playButton ? element.textContent : undefined,
      value: 'value' in element ? element.value : undefined,
      checked: 'checked' in element ? element.checked : undefined
    };
  }
  function conditionMap(element, selector) {
    var result = new Map();
    values(element.querySelectorAll(selector)).forEach(function (item) {
      var parameter = attribute(item, 'data-parameter-id');
      var option = attribute(item, 'data-option-id');
      if (!exactData(item, ['data-parameter-id', 'data-option-id']) || !parameter || !option || result.has(parameter)) { throw new Error('invalid condition'); }
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
  var ControllerMethods = {};
  function Controller(root) {
    this.validate = ControllerMethods.validate;
    this.selection = ControllerMethods.selection;
    this.validateTransitionDomain = ControllerMethods.validateTransitionDomain;
    this.transition = ControllerMethods.transition;
    this.scenarioState = ControllerMethods.scenarioState;
    this.hasTransition = ControllerMethods.hasTransition;
    this.setPlaying = ControllerMethods.setPlaying;
    this.stop = ControllerMethods.stop;
    this.unbind = ControllerMethods.unbind;
    this.restore = ControllerMethods.restore;
    this.fail = ControllerMethods.fail;
    this.applyState = ControllerMethods.applyState;
    this.schedule = ControllerMethods.schedule;
    this.restoreParameters = ControllerMethods.restoreParameters;
    this.action = ControllerMethods.action;
    this.bind = ControllerMethods.bind;
    this.initialize = ControllerMethods.initialize;
    this.dispose = ControllerMethods.dispose;
    this.root = root;
    this.controls = root.querySelector(CONTROLS);
    this.status = root.querySelector(STATUS);
    this.announcement = root.querySelector(ANNOUNCEMENT);
    this.states = values(root.querySelectorAll(STATE));
    this.nodes = values(root.querySelectorAll(NODE));
    this.edges = values(root.querySelectorAll(EDGE));
    this.transitionElements = values(root.querySelectorAll(TRANSITION));
    this.outcomeElements = values(root.querySelectorAll(OUTCOME));
    this.playButton = this.controls ? this.controls.querySelector('[data-action="play"]') : null;
    this.speed = this.controls ? this.controls.querySelector('select[data-action="speed"]') : null;
    this.parameterDefaults = new Map();
    this.mutable = [root, this.controls, this.status, this.announcement]
      .concat(this.states, this.nodes, this.edges)
      .concat(values(this.controls ? this.controls.querySelectorAll('button, select, input, fieldset') : []))
      .filter(Boolean);
    this.snapshot = new Map();
    this.listeners = [];
    this.timer = null;
    this.playing = false;
    this.mutated = false;
    var motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
    this.reduced = motionPreference.matches;
    this.mutable.forEach(function (element) { this.snapshot.set(element, capture(element, this)); }, this);
  }
  ControllerMethods.validate = function () {
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
    if (!this.controls || !this.status || !this.announcement || !this.states.length || this.states.length > 64 ||
        !rootId || rootId !== visualizationId ||
        !exactData(this.root, ['data-visualization-id', 'data-simulation-kind', 'data-interaction-mode', 'data-initial-state-id', 'data-default-interval-ms']) ||
        !unique(domIds, 'id') || KINDS.indexOf(kind) < 0 || !expected ||
        !unique(this.states, 'data-state-id') || !unique(this.nodes, 'data-node-id') ||
        !unique(this.edges, 'data-edge-id') || this.transitionElements.length > 128 ||
        !unique(this.transitionElements, 'data-transition-id') || !this.outcomeElements.length ||
        this.outcomeElements.length > 64 || !unique(this.outcomeElements, 'data-outcome-id') ||
        (mode === 'scenario' && this.transitionElements.length !== 0) ||
        !sameSorted(actions, expected) ||
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
    this.knownDataElements = new Set([this.root]);
    var parameterControls = values(this.controls.querySelectorAll('select[data-parameter-id], input[data-parameter-id]'));
    var actualControls = values(this.controls.querySelectorAll('button, select, input'));
    if (actualControls.some(function (control) {
      if (control.tagName === 'BUTTON') {
        return attribute(control, 'type') !== 'button' || !control.disabled ||
          !exactAttributes(control, ['id', 'type', 'data-action', 'disabled']) ||
          expected.indexOf(attribute(control, 'data-action')) < 0;
      }
      if (control.tagName === 'INPUT') {
        return attribute(control, 'type') !== 'radio' || !control.disabled ||
          !exactAttributes(control, ['id', 'data-parameter-id', 'type', 'name', 'value', 'disabled'], ['checked']);
      }
      if (!control.disabled) { return true; }
      if (attribute(control, 'data-action') === 'speed') {
        return control !== this.speed || !exactAttributes(control, ['id', 'data-action', 'disabled']);
      }
      return !exactAttributes(control, ['id', 'data-parameter-id', 'disabled']);
    }, this)) { throw new Error('invalid control inventory'); }
    actualControls.forEach(function (control) { this.knownDataElements.add(control); }, this);
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
    this.parameters.forEach(function (options, parameter) {
      var controls = parameterControls.filter(function (control) { return attribute(control, 'data-parameter-id') === parameter; });
      var defaults;
      if (controls.length === 1 && controls[0].tagName === 'SELECT') {
        defaults = values(controls[0].querySelectorAll('option')).filter(function (option) { return attribute(option, 'selected') !== null; }).map(function (option) { return option.value; });
      } else {
        defaults = controls.filter(function (control) { return attribute(control, 'checked') !== null; }).map(function (control) { return control.value; });
      }
      if (defaults.length !== 1 || !options.has(defaults[0])) { throw new Error('invalid parameter default'); }
      this.parameterDefaults.set(parameter, defaults[0]);
    }, this);
    this.states.forEach(function (state, ordinal) {
      var source = attribute(state, 'data-step-index');
      var id = attribute(state, 'data-state-id');
      if (!exactData(state, ['data-state-id', 'data-step-index']) || source === null || String(ordinal) !== source) { throw new Error('invalid step index'); }
      var nodeItems = values(state.querySelectorAll('.visualization__state-node[data-node-id]'));
      var edgeItems = values(state.querySelectorAll('.visualization__state-edge[data-edge-id]'));
      if (nodeItems.some(function (item) { return !exactData(item, ['data-node-id']); }) || edgeItems.some(function (item) { return !exactData(item, ['data-edge-id']); })) { throw new Error('invalid active inventory'); }
      var nodeIds = nodeItems.map(function (item) { return attribute(item, 'data-node-id'); });
      var edgeIds = edgeItems.map(function (item) { return attribute(item, 'data-edge-id'); });
      if (nodeIds.some(function (value) { return !this.nodeIds.has(value); }, this) ||
          edgeIds.some(function (value) { return !this.edgeIds.has(value); }, this)) { throw new Error('dangling active reference'); }
      var conditionItems = values(state.querySelectorAll('.visualization__state-condition'));
      this.stateById.set(id, { element: state, conditions: conditionMap(state, '.visualization__state-condition'), nodes: new Set(nodeIds), edges: new Set(edgeIds) });
      this.knownDataElements.add(state);
      nodeItems.concat(edgeItems, conditionItems).forEach(function (item) { this.knownDataElements.add(item); }, this);
    }, this);
    this.initialId = attribute(this.root, 'data-initial-state-id');
    if (!this.stateById.has(this.initialId)) { throw new Error('dangling initial state'); }
    this.transitions = this.transitionElements.map(function (element) {
      var from = attribute(element, 'data-from-state-id');
      var to = attribute(element, 'data-to-state-id');
      var eventName = attribute(element, 'data-transition-event');
      if (!exactData(element, ['data-transition-id', 'data-transition-event', 'data-from-state-id', 'data-to-state-id']) || EVENTS.indexOf(eventName) < 0 || !this.stateById.has(from) || !this.stateById.has(to)) { throw new Error('dangling transition'); }
      var conditionItems = values(element.querySelectorAll('.visualization__transition-condition'));
      this.knownDataElements.add(element);
      conditionItems.forEach(function (item) { this.knownDataElements.add(item); }, this);
      return { from: from, to: to, eventName: eventName, conditions: conditionMap(element, '.visualization__transition-condition') };
    }, this);
    this.outcomes = this.outcomeElements.map(function (element) {
      var state = attribute(element, 'data-state-id');
      if (!exactData(element, ['data-outcome-id', 'data-state-id']) || !this.stateById.has(state)) { throw new Error('dangling outcome'); }
      this.knownDataElements.add(element);
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
    this.nodes.forEach(function (node) { if (!exactData(node, ['data-node-id'])) { throw new Error('invalid node inventory'); } this.knownDataElements.add(node); }, this);
    this.edges.forEach(function (edge) { if (!exactData(edge, ['data-edge-id'])) { throw new Error('invalid edge inventory'); } this.knownDataElements.add(edge); }, this);
    values(this.root.querySelectorAll('*')).forEach(function (element) {
      var hasData = element.getAttributeNames().some(function (name) { return name.indexOf('data-') === 0; });
      if (hasData && !this.knownDataElements.has(element)) { throw new Error('ignored data attribute'); }
    }, this);
    if ((mode === 'scenario' || mode === 'hybrid' || mode === 'explorer') !== Boolean(this.parameters.size)) { throw new Error('invalid parameter set'); }
    this.selection();
    this.validateTransitionDomain();
    if (mode === 'scenario') {
      var defaultStates = [];
      this.stateById.forEach(function (state, stateId) {
        if (matches(state.conditions, this.parameterDefaults)) { defaultStates.push(stateId); }
      }, this);
      if (defaultStates.length !== 1 || defaultStates[0] !== this.initialId) { throw new Error('scenario defaults do not select initial state'); }
    }
    this.currentId = this.initialId;
  };
  ControllerMethods.selection = function () {
    var result = new Map();
    this.parameters.forEach(function (options, parameter) {
      var controls = values(this.controls.querySelectorAll('[data-parameter-id]')).filter(function (control) { return attribute(control, 'data-parameter-id') === parameter; });
      var selected = controls.filter(function (control) { return control.type === 'radio' ? control.checked : true; });
      if (selected.length !== 1 || !options.has(selected[0].value)) { throw new Error('invalid parameter selection'); }
      result.set(parameter, selected[0].value);
    }, this);
    return result;
  };
  ControllerMethods.validateTransitionDomain = function () {
    // The schema caps the Cartesian selection domain at 64. Enumerating that
    // finite domain makes ambiguity a pre-mutation validation error.
    var selections = [new Map()];
    this.parameters.forEach(function (options, parameter) {
      var expanded = [];
      selections.forEach(function (selection) {
        options.forEach(function (option) {
          var next = new Map(selection);
          next.set(parameter, option);
          expanded.push(next);
        });
      });
      selections = expanded;
    });
    if (!selections.length || selections.length > 64) { throw new Error('invalid parameter domain'); }
    selections.forEach(function (selection) {
      var applicable = new Set();
      this.stateById.forEach(function (state, stateId) {
        if (matches(state.conditions, selection)) { applicable.add(stateId); }
      });
      if (this.mode === 'scenario') {
        if (applicable.size !== 1) { throw new Error('invalid scenario partition'); }
        return;
      }
      if (!applicable.has(this.initialId)) { throw new Error('initial state condition mismatch'); }
      var active = this.transitions.filter(function (transition) {
        return matches(transition.conditions, selection);
      });
      active.forEach(function (transition) {
        if (!applicable.has(transition.from) || !applicable.has(transition.to)) { throw new Error('transition endpoint condition mismatch'); }
      });
      this.stateById.forEach(function (state, stateId) {
        EVENTS.forEach(function (eventName) {
          var matchesForEvent = active.filter(function (transition) {
            return transition.from === stateId && transition.eventName === eventName;
          });
          if (matchesForEvent.length > 1) { throw new Error('ambiguous transition event'); }
        }, this);
      }, this);
      // Reset is validated over the selected reachable graph so every state a
      // learner can enter has one deterministic recovery edge to the initial.
      var reachable = new Set([this.initialId]);
      var changed = true;
      while (changed) {
        changed = false;
        active.forEach(function (transition) {
          if (reachable.has(transition.from) && !reachable.has(transition.to)) {
            reachable.add(transition.to);
            changed = true;
          }
        });
      }
      reachable.forEach(function (stateId) {
        if (stateId === this.initialId) { return; }
        var resets = active.filter(function (transition) {
          return transition.from === stateId && transition.eventName === 'reset';
        });
        if (resets.length !== 1 || resets[0].to !== this.initialId) { throw new Error('invalid reset invariant'); }
      }, this);
    }, this);
  };
  ControllerMethods.transition = function (eventName, announce) {
    // Authored event identity is part of the edge key; ordinal state position
    // is deliberately absent so a missing edge cannot become an implicit move.
    var selection = this.selection();
    var candidates = this.transitions.filter(function (transition) {
      return transition.from === this.currentId && transition.eventName === eventName && matches(transition.conditions, selection);
    }, this);
    if (candidates.length > 1) { throw new Error('ambiguous transition event'); }
    if (!candidates.length) {
      if (announce) { this.status.textContent = this.stateById.get(this.currentId).element.textContent.trim(); }
      return false;
    }
    this.currentId = candidates[0].to;
    this.applyState(this.currentId, announce);
    return true;
  };
  ControllerMethods.scenarioState = function () {
    var selection = this.selection();
    var states = [];
    this.stateById.forEach(function (state, stateId) {
      if (matches(state.conditions, selection)) { states.push(stateId); }
    });
    if (states.length !== 1) { throw new Error('invalid scenario partition'); }
    return states[0];
  };
  ControllerMethods.hasTransition = function (eventName) {
    var selection = this.selection();
    return this.transitions.some(function (transition) {
      return transition.from === this.currentId && transition.eventName === eventName && matches(transition.conditions, selection);
    }, this);
  };
  ControllerMethods.setPlaying = function (playing) {
    this.playing = playing;
    if (this.playButton) {
      this.playButton.setAttribute('aria-pressed', playing ? 'true' : 'false');
      this.playButton.textContent = playing ? '再生中' : '再生';
    }
  };
  ControllerMethods.stop = function () {
    if (this.timer !== null) { window.clearTimeout(this.timer); this.timer = null; }
    this.setPlaying(false);
  };
  ControllerMethods.unbind = function () {
    this.listeners.forEach(function (binding) { binding[0].removeEventListener(binding[1], binding[2]); });
    this.listeners = [];
  };
  ControllerMethods.restore = function () {
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
      if (saved.value !== undefined) { element.value = saved.value; }
      if (saved.checked !== undefined) { element.checked = saved.checked; }
    });
  };
  ControllerMethods.fail = function () {
    var showFallback = this.mutated;
    this.unbind();
    if (showFallback) { this.restore(); }
    else if (this.timer !== null) { window.clearTimeout(this.timer); this.timer = null; }
    if (showFallback && this.root && this.status && this.controls) {
      this.root.classList.add('has-runtime-error');
      this.controls.hidden = true;
      this.status.textContent = '動的表示を利用できません。静的図を表示しています。';
      if (this.announcement) { this.announcement.textContent = this.status.textContent; }
    }
  };
  ControllerMethods.applyState = function (stateId, announce) {
    var selected = this.stateById.get(stateId);
    if (!selected) { throw new Error('unknown state'); }
    this.states.forEach(function (state) {
      var active = state === selected.element;
      state.classList.toggle('is-active', active);
      if (active) { state.setAttribute('aria-current', 'step'); } else { state.removeAttribute('aria-current'); }
    });
    this.nodes.forEach(function (node) { node.classList.toggle('is-active', selected.nodes.has(attribute(node, 'data-node-id'))); });
    this.edges.forEach(function (edge) { edge.classList.toggle('is-active', selected.edges.has(attribute(edge, 'data-edge-id'))); });
    var forwardEvent = this.mode === 'playback' || this.mode === 'hybrid' ? 'timer' : 'next';
    this.root.classList.toggle('is-complete', !this.hasTransition(forwardEvent));
    this.status.textContent = selected.element.textContent.trim();
    if (announce) { this.announcement.textContent = this.status.textContent; }
    if (!this.hasTransition('timer') && this.playing) { this.stop(); }
  };
  ControllerMethods.schedule = function () {
    var controller = this;
    if (!this.playing || this.reduced || this.timer !== null || !this.hasTransition('timer')) { return; }
    this.timer = window.setTimeout(function () {
      controller.timer = null;
      try {
        controller.transition('timer', false);
        controller.schedule();
      } catch (error) { controller.fail(); }
    }, this.interval * (this.speed ? { '0.5': 2, '1': 1, '2': 0.5 }[this.speed.value] : 1));
  };
  ControllerMethods.restoreParameters = function () {
    values(this.controls.querySelectorAll('[data-parameter-id]')).forEach(function (control) {
      var defaultValue = this.parameterDefaults.get(attribute(control, 'data-parameter-id'));
      if (control.tagName === 'SELECT') { control.value = defaultValue; }
      else { control.checked = control.value === defaultValue; }
    }, this);
  };
  ControllerMethods.action = function (name) {
    if (name === 'next') {
      this.stop();
      this.transition('next', true);
    } else if (name === 'previous') {
      this.stop();
      this.transition('previous', true);
    } else if (name === 'apply') {
      this.stop();
      if (this.mode === 'scenario') {
        this.currentId = this.scenarioState();
        this.applyState(this.currentId, true);
      } else { this.transition('parameter-change', true); }
    } else if (name === 'reset') {
      this.stop();
      if (this.mode === 'scenario') {
        this.restoreParameters();
        this.currentId = this.initialId;
        this.applyState(this.currentId, true);
      } else { this.transition('reset', true); }
    } else if (name === 'pause') {
      this.stop();
    } else if (name === 'play' && !this.reduced && this.hasTransition('timer')) {
      this.setPlaying(true);
      this.schedule();
    }
  };
  ControllerMethods.bind = function () {
    var controller = this;
    function add(target, type, handler) {
      target.addEventListener(type, handler);
      controller.listeners.push([target, type, handler]);
    }
    add(this.controls, 'click', function (event) {
      var target = event.target.closest('button');
      if (!target || !controller.controls.contains(target)) { return; }
      try { controller.action(attribute(target, 'data-action')); } catch (error) { controller.fail(); }
    });
    add(this.controls, 'change', function (event) {
      if (event.target === controller.speed && controller.playing) {
        try { controller.stop(); controller.setPlaying(true); controller.schedule(); } catch (error) { controller.fail(); }
      }
    });
  };
  ControllerMethods.initialize = function () {
    this.validate();
    this.bind();
    this.mutated = true;
    this.applyState(this.currentId, false);
    values(this.controls.querySelectorAll('button, select, input, fieldset')).forEach(function (control) { control.disabled = false; });
    if (this.reduced) {
      [this.playButton, this.controls.querySelector('[data-action="pause"]'), this.speed].filter(Boolean).forEach(function (control) { control.disabled = true; });
      this.status.textContent += '（視差低減設定のため自動再生は利用できません）';
      this.announcement.textContent = '視差低減設定のため自動再生は利用できません';
    }
    this.controls.hidden = false;
    this.root.classList.add('is-enhanced');
  };
  ControllerMethods.dispose = function () { this.unbind(); this.restore(); };

  function initialize(root) {
    var controller = new Controller(root);
    try { controller.initialize(); controllers.set(root, controller); }
    catch (error) { controller.fail(); }
  }
  var simulationRoots = document.querySelectorAll(ROOT);
  values(simulationRoots).forEach(initialize);
  window.addEventListener('pagehide', function () {
    controllers.forEach(function (controller) { controller.dispose(); });
    controllers.clear();
  });
  window.addEventListener('pageshow', function (event) {
    if (event.persisted && controllers.size === 0) { values(simulationRoots).forEach(initialize); }
  });
}());
