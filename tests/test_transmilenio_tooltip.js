const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const SchematicMap = require('../frontend/js/transmilenio-schematic-map.js');

const source = fs.readFileSync(
  path.join(__dirname, '../frontend/js/transmilenio-schematic-map.js'), 'utf8'
);
assert.equal(source.includes("createElementNS(SVG_NS, 'text')"), false);
assert.equal(source.includes('labelsGroup'), false);

global.window = { innerWidth: 300, innerHeight: 200 };
global.document = { documentElement: { clientWidth: 300, clientHeight: 200 } };

function classList() {
  const values = new Set();
  return {
    add: (value) => values.add(value),
    remove: (value) => values.delete(value),
    contains: (value) => values.has(value)
  };
}

function stationNode(rect) {
  const attributes = new Map();
  return {
    rect,
    classList: classList(),
    closest(selector) { return selector === '.tm-station-node' ? this : null; },
    setAttribute: (key, value) => attributes.set(key, value),
    removeAttribute: (key) => attributes.delete(key),
    getAttribute: (key) => attributes.get(key),
    getBoundingClientRect() { return this.rect; }
  };
}

let contentUpdates = 0;
const tooltip = {
  id: 'tm-station-tooltip',
  classList: classList(),
  style: {},
  offsetWidth: 220,
  offsetHeight: 130,
  setAttribute(key, value) { this[key] = value; },
  set innerHTML(value) { this.content = value; contentUpdates += 1; },
  get innerHTML() { return this.content; }
};
const map = Object.create(SchematicMap.prototype);
map.tooltip = tooltip;
map.hoveredCode = null;
map.hoveredNode = null;
map.layout = { stations: {
  'TM-E-12': { troncalId: 'E' },
  'TM-F-01': { troncalId: 'F' }
} };
map.estacionesMap = new Map([
  ['TM-E-12', {
    nombre: 'Calle 75', troncal_id: 'E', troncal: 'NQS Central',
    estado_operativo: 'por_verificar',
    camaras: { total: 3, activas: 2 },
    eventos_hoy: { total_hoy: 0 }, riesgo: 'normal'
  }],
  ['TM-F-01', {
    nombre: 'Portal Américas', troncal_id: 'F',
    camaras: { total: 0, activas: 0 }
  }]
]);
map.troncalesMap = new Map([['F', { nombre: 'Américas' }]]);

const rightNode = stationNode({ left: 270, right: 284, top: 170, height: 14 });
map._showTooltip('TM-E-12', rightNode);
assert.equal(map.hoveredCode, 'TM-E-12');
assert.equal(tooltip.classList.contains('is-visible'), true);
assert.equal(rightNode.classList.contains('tm-station--hovered'), true);
assert.equal(rightNode.getAttribute('aria-describedby'), tooltip.id);
assert.match(tooltip.innerHTML, /Calle 75/);
assert.match(tooltip.innerHTML, /Por verificar/);
assert.match(tooltip.innerHTML, /2 \/ 3 activas/);
assert.match(tooltip.innerHTML, /Evasiones hoy/);
assert.doesNotMatch(tooltip.innerHTML, /Operación Normal/);
assert.ok(parseFloat(tooltip.style.left) >= 8);
assert.ok(parseFloat(tooltip.style.left) + tooltip.offsetWidth <= 292);
assert.ok(parseFloat(tooltip.style.top) >= 8);
assert.ok(parseFloat(tooltip.style.top) + tooltip.offsetHeight <= 192);

map._showTooltip('TM-E-12', rightNode);
assert.equal(contentUpdates, 1);

const leftNode = stationNode({ left: 10, right: 24, top: 10, height: 14 });
map._showTooltip('TM-F-01', leftNode);
assert.equal(contentUpdates, 2);
assert.equal(rightNode.classList.contains('tm-station--hovered'), false);
assert.equal(rightNode.getAttribute('aria-describedby'), undefined);
assert.match(tooltip.innerHTML, /Portal Américas/);
assert.match(tooltip.innerHTML, /0 \/ 0 activas/);
assert.doesNotMatch(tooltip.innerHTML, /Evasiones hoy/);
assert.doesNotMatch(tooltip.innerHTML, /Estado/);

leftNode.rect = { left: 80, right: 94, top: 50, height: 14 };
map._positionTooltip(leftNode);
assert.ok(parseFloat(tooltip.style.left) >= 8);
map._hideTooltip();
assert.equal(map.hoveredCode, null);
assert.equal(tooltip.classList.contains('is-visible'), false);
assert.equal(leftNode.classList.contains('tm-station--hovered'), false);

let selected = null;
map.render = () => {};
map.onSelectStation = (code) => { selected = code; };
map.selectStation('TM-E-12');
assert.equal(selected, 'TM-E-12');
assert.equal(map.estacionSeleccionada, 'TM-E-12');

const stationEvents = new Map();
const windowEvents = new Map();
map.stationsGroup = {
  contains: (node) => node === leftNode || node === rightNode,
  addEventListener: (name, handler) => stationEvents.set(name, handler)
};
map.svg = {
  style: {},
  addEventListener() {},
  createSVGPoint: () => ({ matrixTransform() { return { x: 0, y: 0 }; } }),
  getScreenCTM: () => ({ inverse() { return {}; } })
};
map.container = { addEventListener() {} };
window.addEventListener = (name, handler) => windowEvents.set(name, handler);
map._bindEvents();
leftNode.dataset = { code: 'TM-F-01' };
rightNode.dataset = { code: 'TM-E-12' };
stationEvents.get('pointerover')({ target: leftNode, pointerType: 'mouse' });
assert.equal(map.hoveredCode, 'TM-F-01');
stationEvents.get('pointerout')({ target: leftNode, relatedTarget: leftNode });
assert.equal(map.hoveredCode, 'TM-F-01');
stationEvents.get('pointerout')({ target: leftNode, relatedTarget: rightNode });
assert.equal(map.hoveredCode, 'TM-F-01');
stationEvents.get('pointerover')({ target: rightNode, pointerType: 'mouse' });
assert.equal(map.hoveredCode, 'TM-E-12');
stationEvents.get('pointerout')({ target: rightNode, relatedTarget: null });
assert.equal(map.hoveredCode, null);
windowEvents.get('keydown')();
stationEvents.get('focusin')({ target: rightNode });
assert.equal(map.hoveredCode, 'TM-E-12');
stationEvents.get('focusout')({ relatedTarget: null });
assert.equal(map.hoveredCode, null);
stationEvents.get('pointerdown')({ pointerType: 'touch' });
stationEvents.get('focusin')({ target: rightNode });
stationEvents.get('pointerover')({ target: rightNode, pointerType: 'touch' });
assert.equal(map.hoveredCode, null);
console.log('Tooltip y nodos: PASS');
