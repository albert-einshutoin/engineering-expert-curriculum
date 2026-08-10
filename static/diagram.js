(function () {
  'use strict';

  var namespace = 'http://www.w3.org/2000/svg';
  var sourceSelector = '.mermaid-source';
  var renderedClass = 'is-rendered';
  var nodeWidth = 132;
  var nodeHeight = 54;
  var nodeGap = 22;
  var horizontalPadding = 20;

  function create(tag) {
    return document.createElementNS(namespace, tag);
  }

  function set(element, name, value) {
    element.setAttribute(name, String(value));
  }

  function parseLine(line) {
    var trimmed = line.trim();
    if (!trimmed || trimmed.indexOf('flowchart ') === 0 || trimmed.indexOf('graph ') === 0) {
      return null;
    }
    var pieces = trimmed.split('-->');
    if (pieces.length !== 2) {
      return null;
    }
    var from = parseNode(pieces[0].trim());
    var to = parseNode(pieces[1].trim());
    if (!from || !to) {
      return null;
    }
    return { from: from, to: to };
  }

  function parseNode(value) {
    var opening = value.indexOf('[');
    var closing = value.lastIndexOf(']');
    if (opening < 1) {
      var bareId = value.trim();
      if (!/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(bareId)) {
        return null;
      }
      return { id: bareId, label: bareId };
    }
    if (closing <= opening + 1 || closing !== value.length - 1) {
      return null;
    }
    var id = value.slice(0, opening).trim();
    var label = value.slice(opening + 1, closing).trim();
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(id) || label.length < 1 || label.length > 40) {
      return null;
    }
    return { id: id, label: label };
  }

  function parse(source) {
    var nodes = [];
    var byId = new Map();
    var edges = [];
    source.textContent.split('\n').forEach(function (line) {
      var edge = parseLine(line);
      if (!edge) {
        return;
      }
      [edge.from, edge.to].forEach(function (node) {
        if (!byId.has(node.id) && nodes.length < 8) {
          byId.set(node.id, node);
          nodes.push(node);
        }
      });
      if (byId.has(edge.from.id) && byId.has(edge.to.id) && edges.length < 8) {
        edges.push(edge);
      }
    });
    return { nodes: nodes, edges: edges };
  }

  function label(svg, text, x, y, className) {
    var element = create('text');
    set(element, 'x', x);
    set(element, 'y', y);
    set(element, 'class', className);
    element.textContent = text;
    svg.appendChild(element);
  }

  function render(source) {
    var stage = source.parentNode.querySelector('.diagram-stage');
    if (!stage) {
      return;
    }
    var parsed = parse(source);
    if (parsed.nodes.length < 2 || parsed.edges.length < 1) {
      return;
    }
    var narrow = stage.clientWidth > 0 && stage.clientWidth < 700;
    var columns = narrow ? 2 : parsed.nodes.length;
    var rowGap = narrow ? 18 : 0;
    var width = horizontalPadding * 2 + columns * nodeWidth + (columns - 1) * nodeGap;
    var rows = Math.ceil(parsed.nodes.length / columns);
    var height = rows * nodeHeight + (rows - 1) * rowGap + 46;
    var positions = new Map();
    parsed.nodes.forEach(function (node, index) {
      positions.set(node.id, {
        x: horizontalPadding + (index % columns) * (nodeWidth + nodeGap),
        y: 8 + Math.floor(index / columns) * (nodeHeight + rowGap)
      });
    });
    var svg = create('svg');
    set(svg, 'class', 'diagram-graphic');
    set(svg, 'viewBox', '0 0 ' + width + ' ' + height);
    set(svg, 'role', 'img');
    set(svg, 'aria-label', '読む、試す、説明する、証拠を残す、転用する、復習する学習ループ');
    var marker = create('marker');
    set(marker, 'id', 'journey-arrow');
    set(marker, 'viewBox', '0 0 10 10');
    set(marker, 'refX', '9');
    set(marker, 'refY', '5');
    set(marker, 'markerWidth', '6');
    set(marker, 'markerHeight', '6');
    set(marker, 'orient', 'auto-start-reverse');
    var markerPath = create('path');
    set(markerPath, 'class', 'diagram-arrowhead');
    set(markerPath, 'd', 'M 0 0 L 10 5 L 0 10 z');
    marker.appendChild(markerPath);
    var defs = create('defs');
    defs.appendChild(marker);
    svg.appendChild(defs);
    parsed.edges.forEach(function (edge) {
      var from = positions.get(edge.from.id);
      var to = positions.get(edge.to.id);
      if (!from || !to) {
        return;
      }
      var line = create('line');
      var horizontal = Math.abs(to.x - from.x) >= Math.abs(to.y - from.y);
      set(line, 'x1', horizontal ? (to.x > from.x ? from.x + nodeWidth : from.x) : from.x + nodeWidth / 2);
      set(line, 'y1', horizontal ? from.y + nodeHeight / 2 : (to.y > from.y ? from.y + nodeHeight : from.y));
      set(line, 'x2', horizontal ? (to.x > from.x ? to.x : to.x + nodeWidth) : to.x + nodeWidth / 2);
      set(line, 'y2', horizontal ? to.y + nodeHeight / 2 : (to.y > from.y ? to.y : to.y + nodeHeight));
      set(line, 'class', 'diagram-edge');
      set(line, 'marker-end', 'url(#journey-arrow)');
      svg.appendChild(line);
    });
    parsed.nodes.forEach(function (node) {
      var position = positions.get(node.id);
      var x = position.x;
      var rect = create('rect');
      set(rect, 'x', x);
      set(rect, 'y', position.y);
      set(rect, 'width', nodeWidth);
      set(rect, 'height', nodeHeight);
      set(rect, 'rx', '10');
      set(rect, 'class', 'diagram-node');
      svg.appendChild(rect);
      label(svg, node.label, x + nodeWidth / 2, position.y + 40, 'diagram-label');
    });
    stage.appendChild(svg);
    source.parentNode.classList.add(renderedClass);
  }

  document.querySelectorAll(sourceSelector).forEach(render);
}());
