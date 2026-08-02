(function () {
  'use strict';

  var HARNESS_VERSION = '1.0.0';
  var violations = [];
  var truncated = {
    violations: false, runtimeErrors: false, longTasks: false,
    externalResources: false, resourceNames: false
  };
  function boundedPush(target, value, key, limit) {
    if (target.length < limit) { target.push(value); } else { truncated[key] = true; }
  }
  var listenerCount = 0;
  var listenerRegistry = new WeakMap();
  var activeTimers = new Set();
  var longTasks = [];
  var initialLocation = window.location.href;
  var runtimeErrors = [];
  var NativeError = window.Error;
  var originalAdd = EventTarget.prototype.addEventListener;
  var originalRemove = EventTarget.prototype.removeEventListener;
  var originalSetTimeout = window.setTimeout;
  var originalClearTimeout = window.clearTimeout;

  window.Error = function (message) {
    boundedPush(runtimeErrors, String(message).slice(0, 120), 'runtimeErrors', 128);
    return new NativeError(message);
  };
  window.Error.prototype = NativeError.prototype;

  function captureOption(options) {
    return typeof options === 'boolean' ? options : Boolean(options && options.capture);
  }
  function listenerRecords(target) {
    var records = listenerRegistry.get(target);
    if (!records) { records = []; listenerRegistry.set(target, records); }
    return records;
  }
  function invokeListener(callback, target, event) {
    if (typeof callback === 'function') { return callback.call(target, event); }
    return callback.handleEvent.call(callback, event);
  }
  EventTarget.prototype.addEventListener = function (type, callback, options) {
    if (callback === null || callback === undefined) {
      return originalAdd.call(this, type, callback, options);
    }
    var capture = captureOption(options);
    var records = listenerRecords(this);
    if (records.some(function (record) {
      return record.type === type && record.callback === callback && record.capture === capture;
    })) { return; }
    var once = Boolean(options && typeof options === 'object' && options.once);
    var target = this;
    var record = { type: type, callback: callback, capture: capture, wrapped: callback };
    if (once) {
      record.wrapped = function (event) {
        var index = records.indexOf(record);
        if (index >= 0) { records.splice(index, 1); listenerCount -= 1; }
        return invokeListener(callback, target, event);
      };
    }
    records.push(record);
    listenerCount += 1;
    return originalAdd.call(this, type, record.wrapped, options);
  };
  EventTarget.prototype.removeEventListener = function (type, callback, options) {
    var capture = captureOption(options);
    var records = listenerRegistry.get(this) || [];
    var index = records.findIndex(function (record) {
      return record.type === type && record.callback === callback && record.capture === capture;
    });
    if (index < 0) { return originalRemove.call(this, type, callback, options); }
    var record = records[index];
    records.splice(index, 1);
    listenerCount -= 1;
    return originalRemove.call(this, type, record.wrapped, options);
  };
  window.setTimeout = function (callback, delay) {
    var identifier = originalSetTimeout.call(window, function () {
      activeTimers.delete(identifier);
      callback();
    }, delay);
    activeTimers.add(identifier);
    return identifier;
  };
  window.clearTimeout = function (identifier) {
    activeTimers.delete(identifier);
    return originalClearTimeout.call(window, identifier);
  };

  function forbidden(name) {
    return function () {
      boundedPush(violations, name, 'violations', 128);
      throw new Error('forbidden browser capability: ' + name);
    };
  }
  if (typeof window.fetch === 'function') { window.fetch = forbidden('fetch'); }
  if (typeof window.XMLHttpRequest === 'function') { window.XMLHttpRequest = forbidden('XMLHttpRequest'); }
  if (typeof window.WebSocket === 'function') { window.WebSocket = forbidden('WebSocket'); }
  if (typeof window.EventSource === 'function') { window.EventSource = forbidden('EventSource'); }
  if (typeof window.open === 'function') { window.open = forbidden('window.open'); }
  if (window.Storage && window.Storage.prototype) {
    window.Storage.prototype.setItem = forbidden('storage.setItem');
    window.Storage.prototype.removeItem = forbidden('storage.removeItem');
    window.Storage.prototype.clear = forbidden('storage.clear');
  }
  if (window.history) {
    window.history.pushState = forbidden('history.pushState');
    window.history.replaceState = forbidden('history.replaceState');
  }
  originalAdd.call(document, 'securitypolicyviolation', function (event) {
    boundedPush(violations, 'csp:' + event.violatedDirective, 'violations', 128);
  });
  originalAdd.call(window, 'error', function (event) {
    boundedPush(violations, 'error:' + String(event.message).slice(0, 160), 'violations', 128);
  });

  var observerAvailable = typeof window.PerformanceObserver === 'function';
  var observer = null;
  if (observerAvailable) {
    try {
      observer = new window.PerformanceObserver(function (list) {
        list.getEntries().forEach(function (entry) {
          boundedPush(longTasks, entry.duration, 'longTasks', 128);
        });
      });
      observer.observe({ entryTypes: ['longtask'] });
    } catch (error) {
      observerAvailable = false;
    }
  }

  function flushObserverCallbacks() {
    return new Promise(function (resolve) { originalSetTimeout.call(window, resolve, 0); });
  }
  function takeLongTasks() {
    if (!observer) { return; }
    observer.takeRecords().forEach(function (entry) {
      boundedPush(longTasks, entry.duration, 'longTasks', 128);
    });
  }

  function verifyListenerInstrumentation() {
    var target = new EventTarget();
    var baseline = listenerCount;
    var calls = 0;
    function duplicate() { calls += 1; }
    target.addEventListener('probe', duplicate, false);
    target.addEventListener('probe', duplicate, false);
    target.removeEventListener('probe', duplicate, true);
    if (listenerCount !== baseline + 1) { throw new Error('listener duplicate semantics drifted'); }
    target.removeEventListener('probe', duplicate, false);
    target.addEventListener('once-probe', duplicate, { once: true });
    target.dispatchEvent(new Event('once-probe'));
    target.dispatchEvent(new Event('once-probe'));
    if (listenerCount !== baseline || calls !== 1) { throw new Error('listener once semantics drifted'); }
  }

  function click(root, action) {
    var control = root.querySelector('[data-action="' + action + '"]');
    if (control && !control.disabled && !control.hidden) { control.click(); }
  }

  function exerciseSimulations() {
    var roots = Array.prototype.slice.call(document.querySelectorAll('[data-simulation-kind]'));
    var reached = new Set();
    var requested = typeof window.__browserContractRequestedState === 'string'
      ? window.__browserContractRequestedState : '';
    function record(root) {
      var active = root.querySelector('[data-state-id].is-active');
      if (active) { reached.add(active.getAttribute('data-state-id')); }
      return Boolean(active && requested && active.getAttribute('data-state-id') === requested);
    }
    function applyRequestedConditions(root) {
      if (!requested) { return; }
      var target = Array.prototype.find.call(
        root.querySelectorAll('[data-state-id]'),
        function (item) { return item.getAttribute('data-state-id') === requested; }
      );
      if (!target) { return; }
      Array.prototype.forEach.call(
        target.querySelectorAll('.visualization__state-condition'),
        function (condition) {
          var parameter = condition.getAttribute('data-parameter-id');
          var option = condition.getAttribute('data-option-id');
          var controls = root.querySelectorAll('[data-parameter-id]');
          Array.prototype.forEach.call(controls, function (control) {
            if (control.getAttribute('data-parameter-id') !== parameter) { return; }
            if (control.tagName === 'SELECT') {
              control.value = option;
              control.dispatchEvent(new Event('change', { bubbles: true }));
            } else if (control.type === 'radio' && control.value === option) {
              control.click();
            }
          });
        }
      );
      click(root, 'apply');
      record(root);
    }
    roots.forEach(function (root) {
      if (record(root)) { return; }
      applyRequestedConditions(root);
      if (record(root)) { return; }
      for (var targetStep = 0; targetStep < 64 && !record(root); targetStep += 1) {
        click(root, 'next');
      }
      if (record(root)) { return; }
      click(root, 'reset');
      var controls = root.querySelectorAll('select[data-parameter-id], input[data-parameter-id]');
      Array.prototype.forEach.call(controls, function (control) {
        if (control.tagName === 'SELECT') {
          Array.prototype.forEach.call(control.options, function (_option, optionIndex) {
            control.selectedIndex = optionIndex;
            control.dispatchEvent(new Event('change', { bubbles: true }));
            click(root, 'apply');
            record(root);
          });
        } else if (control.type === 'radio') {
          control.click();
          control.dispatchEvent(new Event('change', { bubbles: true }));
          click(root, 'apply');
          record(root);
        }
      });
      click(root, 'apply');
      for (var step = 0; step < 64 && !record(root); step += 1) { click(root, 'next'); }
      if (!record(root)) {
        click(root, 'previous');
        click(root, 'play');
        click(root, 'pause');
      }
      if (!requested || !record(root)) { click(root, 'reset'); record(root); }
    });
    return { count: roots.length, reached: Array.from(reached).sort(), targetReached: !requested || reached.has(requested) };
  }

  function sampleMaximumFixture() {
    var root = document.getElementById('browser-maximum-fixture');
    var nodes = document.querySelectorAll('#browser-maximum-fixture .visualization__model-node[data-node-id]');
    var edges = document.querySelectorAll('#browser-maximum-fixture .visualization__model-edge[data-edge-id]');
    if (nodes.length === 0 && edges.length === 0) { return 0; }
    if (nodes.length !== 64 || edges.length !== 128) {
      throw new Error('maximum fixture item or relationship count drifted');
    }
    if (!root.classList.contains('is-enhanced')) {
      throw new Error('maximum fixture was not enhanced by the product runtime');
    }
    var start = performance.now();
    var mutations = 0;
    for (var iteration = 0; iteration < 16; iteration += 1) {
      click(root, 'next');
      var active = root.querySelectorAll('.visualization__model-node.is-active, .visualization__model-edge.is-active').length;
      if (active !== 192) { throw new Error('maximum fixture native next did not activate its full model'); }
      mutations += active;
      click(root, 'reset');
      if (root.querySelectorAll('.visualization__model-node.is-active, .visualization__model-edge.is-active').length !== 0) {
        throw new Error('maximum fixture native reset did not restore its model');
      }
      mutations += active;
    }
    return { durationMs: performance.now() - start, mutations: mutations };
  }

  function sampleWorkload() {
    if (document.getElementById('browser-maximum-fixture')) {
      return sampleMaximumFixture();
    }
    var roots = document.querySelectorAll('[data-simulation-kind]');
    if (!roots.length) { throw new Error('performance workload is unavailable'); }
    var mutations = 0;
    var start = performance.now();
    for (var iteration = 0; iteration < 16; iteration += 1) {
      roots.forEach(function (root) {
        var before = root.querySelector('[data-state-id].is-active');
        var beforeId = before ? before.getAttribute('data-state-id') : '';
        click(root, 'next');
        var afterNext = root.querySelector('[data-state-id].is-active');
        var nextId = afterNext ? afterNext.getAttribute('data-state-id') : '';
        if (nextId !== beforeId) { mutations += 1; }
        click(root, 'reset');
        var afterReset = root.querySelector('[data-state-id].is-active');
        var resetId = afterReset ? afterReset.getAttribute('data-state-id') : '';
        if (resetId !== nextId) { mutations += 1; }
      });
    }
    var duration = performance.now() - start;
    if (mutations === 0 || !Number.isFinite(duration) || duration <= 0) {
      throw new Error('performance workload did not mutate runtime state with positive timing');
    }
    return { durationMs: duration, mutations: mutations };
  }

  function heapBytes() {
    return performance.memory && Number.isFinite(performance.memory.usedJSHeapSize)
      ? Math.floor(performance.memory.usedJSHeapSize) : -1;
  }

  function countDomNodes() {
    return document.getElementsByTagName('*').length;
  }

  async function report() {
    var resultNode = document.getElementById('browser-contract-result');
    if (!resultNode) {
      resultNode = document.createElement('p');
      resultNode.id = 'browser-contract-result';
      resultNode.hidden = true;
      document.body.appendChild(resultNode);
    }
    try {
      verifyListenerInstrumentation();
      var simulationRoots = Array.prototype.slice.call(
        document.querySelectorAll('[data-simulation-kind]')
      );
      var initialStateIds = simulationRoots.map(function (root) {
        var active = root.querySelector('[data-state-id].is-active');
        return active ? active.getAttribute('data-state-id') : '';
      });
      var simulationEvidence = exerciseSimulations();
      var warmups = [];
      var samples = [];
      var workloadMutationSamples = [];
      var longTaskSamples = [];
      var index;
      var measurePerformance = window.__browserContractMeasurePerformance === true;
      if (measurePerformance) {
        for (index = 0; index < 3; index += 1) {
          var warmup = sampleWorkload();
          warmups.push(warmup.durationMs);
        }
      }
      var baseline = {
        domNodes: countDomNodes(), listeners: listenerCount,
        timers: activeTimers.size, heapBytes: heapBytes()
      };
      if (measurePerformance) {
        for (index = 0; index < 20; index += 1) {
          var longTaskStart = longTasks.length;
          var sample = sampleWorkload();
          await flushObserverCallbacks();
          takeLongTasks();
          samples.push(sample.durationMs);
          workloadMutationSamples.push(sample.mutations);
          longTaskSamples.push(longTasks.slice(longTaskStart).reduce(function (maximum, duration) {
            return Math.max(maximum, duration);
          }, 0));
        }
      }
      for (index = 0; index < 100; index += 1) {
        simulationRoots.forEach(function (root) {
          click(root, 'next'); click(root, 'reset');
        });
      }
      simulationRoots.forEach(function (root, rootIndex) {
        var active = root.querySelector('[data-state-id].is-active');
        var restored = active ? active.getAttribute('data-state-id') : '';
        if (restored !== initialStateIds[rootIndex]) {
          boundedPush(violations, 'reset-restoration', 'violations', 128);
        }
      });
      var gcAvailable = typeof window.gc === 'function' && baseline.heapBytes >= 0;
      if (gcAvailable) { window.gc(); window.gc(); }
      var finalCounts = {
        domNodes: countDomNodes(), listeners: listenerCount,
        timers: activeTimers.size, heapBytes: heapBytes()
      };
      var externalResources = [];
      var resourceNames = [];
      performance.getEntriesByType('resource').forEach(function (entry) {
        var resource = new URL(entry.name, window.location.href);
        var approvedFileRoots = Array.isArray(window.__browserContractApprovedFileRoots) ?
          window.__browserContractApprovedFileRoots : [];
        var approvedFile = resource.protocol === 'file:' && resource.host === '' &&
          resource.search === '' && resource.hash === '' &&
          !/%(?:2e|2f|5c)/i.test(resource.pathname) &&
          approvedFileRoots.some(function (root) { return resource.href.indexOf(root) === 0; });
        if ((resource.protocol === 'file:' && !approvedFile) ||
            (resource.protocol !== 'file:' && resource.origin !== window.location.origin)) {
          boundedPush(externalResources, String(entry.name).slice(0, 240), 'externalResources', 128);
        }
        boundedPush(resourceNames, String(entry.name).split('/').pop().slice(0, 80), 'resourceNames', 128);
      });
      var enhancedCount = document.querySelectorAll('[data-simulation-kind].is-enhanced').length;
      var runtimeErrorCount = document.querySelectorAll('[data-simulation-kind].has-runtime-error').length;
      if (simulationEvidence.count !== enhancedCount) { boundedPush(violations, 'runtime-initialization', 'violations', 128); }
      if (runtimeErrorCount > 0) { boundedPush(violations, 'runtime-error', 'violations', 128); }
      if (window.location.href !== initialLocation) { boundedPush(violations, 'navigation', 'violations', 128); }
      if (externalResources.length) { boundedPush(violations, 'external-resource', 'violations', 128); }
      if (Object.keys(truncated).some(function (key) { return truncated[key]; })) {
        boundedPush(violations, 'evidence-truncated', 'violations', 128);
      }
      var result = {
        schemaVersion: 1,
        harnessVersion: HARNESS_VERSION,
        passed: violations.length === 0 && simulationEvidence.targetReached,
        simulationCount: simulationEvidence.count,
        reachedStateIds: simulationEvidence.reached,
        requestedStateReached: simulationEvidence.targetReached,
        runtimeEnhancedCount: enhancedCount,
        runtimeErrorCount: runtimeErrorCount,
        runtimeErrors: runtimeErrors,
        warmupsMs: warmups,
        samplesMs: samples,
        workloadMutationSamples: workloadMutationSamples,
        longTasksMs: longTaskSamples,
        observedLongTasksMs: longTasks,
        resetCycles: 100,
        baseline: baseline,
        final: finalCounts,
        instrumentation: {
          listeners: true, timers: true, gc: gcAvailable,
          longTasks: observerAvailable
        },
        violations: violations,
        violationKinds: violations.map(function (item) { return item.split(':', 1)[0]; }),
        externalResources: externalResources,
        resourceNames: resourceNames,
        truncated: truncated
      };
      resultNode.setAttribute('data-browser-contract-result', JSON.stringify(result));
      resultNode.textContent = result.passed ? 'browser contract complete' : 'browser contract failed';
    } catch (error) {
      resultNode.setAttribute('data-browser-contract-result', JSON.stringify({
        schemaVersion: 1, harnessVersion: HARNESS_VERSION, passed: false,
        violations: violations.concat(['harness:' + String(error.message).slice(0, 160)]),
        violationKinds: violations.map(function (item) { return item.split(':', 1)[0]; }).concat(['harness']),
        truncated: truncated
      }));
      resultNode.textContent = 'browser contract failed';
    }
  }

  originalAdd.call(window, 'load', report, { once: true });
}());
