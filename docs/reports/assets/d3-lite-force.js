/*
 * d3-lite-force.js
 * Local offline visualization helper for ManiPsych reports.
 *
 * This is a tiny D3-inspired force layout helper, not the full D3 distribution.
 * It exists so the generated file:// report can render bundled interactive
 * network visualizations without CDN access. API surface intentionally stays
 * small: window.d3.version and window.d3LiteForce.layout(nodes, links, opts).
 */
(function () {
  "use strict";
  function cloneNode(node, index, width, height) {
    var angle = (index / Math.max(1, arguments[5] || 1)) * Math.PI * 2;
    return Object.assign({}, node, {
      x: Number.isFinite(node.x) ? node.x : width / 2 + Math.cos(angle) * width * 0.26,
      y: Number.isFinite(node.y) ? node.y : height / 2 + Math.sin(angle) * height * 0.26,
      vx: 0,
      vy: 0,
    });
  }
  function layout(nodes, links, options) {
    options = options || {};
    var width = options.width || 780;
    var height = options.height || 520;
    var iterations = options.iterations || 170;
    var charge = options.charge || -260;
    var spring = options.spring || 0.018;
    var damping = options.damping || 0.84;
    var idToNode = new Map();
    var working = nodes.map(function (node, index) {
      var n = cloneNode(node, index, width, height, nodes.length);
      idToNode.set(n.id, n);
      return n;
    });
    var workingLinks = links
      .map(function (link) {
        return {
          source: idToNode.get(link.source),
          target: idToNode.get(link.target),
          weight: Math.max(1, Number(link.weight) || 1),
          kind: link.kind || "edge",
        };
      })
      .filter(function (link) {
        return link.source && link.target;
      });
    for (var step = 0; step < iterations; step++) {
      for (var i = 0; i < working.length; i++) {
        for (var j = i + 1; j < working.length; j++) {
          var a = working[i];
          var b = working[j];
          var dx = a.x - b.x || 0.01;
          var dy = a.y - b.y || 0.01;
          var dist2 = Math.max(80, dx * dx + dy * dy);
          var force = charge / dist2;
          a.vx += dx * force;
          a.vy += dy * force;
          b.vx -= dx * force;
          b.vy -= dy * force;
        }
      }
      workingLinks.forEach(function (link) {
        var dx = link.target.x - link.source.x;
        var dy = link.target.y - link.source.y;
        var distance = Math.sqrt(dx * dx + dy * dy) || 1;
        var desired = 72 + 18 / Math.sqrt(link.weight);
        var force = (distance - desired) * spring;
        var fx = (dx / distance) * force;
        var fy = (dy / distance) * force;
        link.source.vx += fx;
        link.source.vy += fy;
        link.target.vx -= fx;
        link.target.vy -= fy;
      });
      working.forEach(function (node) {
        node.vx += (width / 2 - node.x) * 0.003;
        node.vy += (height / 2 - node.y) * 0.003;
        node.vx *= damping;
        node.vy *= damping;
        node.x = Math.max(18, Math.min(width - 18, node.x + node.vx));
        node.y = Math.max(18, Math.min(height - 18, node.y + node.vy));
      });
    }
    return { nodes: working, links: workingLinks };
  }
  window.d3 = window.d3 || { version: "d3-lite-force-local" };
  window.d3LiteForce = { layout: layout };
})();
