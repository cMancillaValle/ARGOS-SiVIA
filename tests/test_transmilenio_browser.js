// Requiere Edge o Chrome con DevTools en C4_CDP_PORT y no usa SQLite.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const catalog = JSON.parse(fs.readFileSync(
  path.join(root, 'backend/data/estaciones_transmilenio.json'), 'utf8'
));
const view = fs.readFileSync(path.join(root, 'frontend/views/mapa_transmilenio.html'), 'utf8');
const css = view.split('<style>')[1].split('</style>')[0];
const layoutUrl = pathToFileURL(path.join(root, 'frontend/js/transmilenio-layout.js')).href;
const rendererUrl = pathToFileURL(path.join(root, 'frontend/js/transmilenio-schematic-map.js')).href;
const previewPath = path.join(os.tmpdir(), 'argos_tm_c4_browser_test.html');
fs.writeFileSync(previewPath, `<!doctype html><html><head><meta charset="utf-8">
  <style>:root{--bg:#080b12;--bg2:#111927;--bg3:#172033;--texto:#e9eef9;
  --dim:#8997ad;--muted:#66738b;--borde2:#314057;--azul:#00a6d8;
  --rojo:#e40022;--verde:#74b51c;--amarillo:#ffc400}
  body{margin:0;background:#080b12}#map{width:1400px;height:900px;position:relative}
  ${css}</style></head><body><div id="map"></div>
  <script src="${layoutUrl}"></script><script src="${rendererUrl}"></script>
  <script>window.selected=[];window.map=new TransmilenioSchematicMap({
    container:document.getElementById('map'),layout:TRANSMILENIO_LAYOUT,
    estaciones:${JSON.stringify(catalog.estaciones)},troncales:[],
    onSelectStation:code=>selected.push(code)});</script></body></html>`, 'utf8');
const viewPreviewPath = path.join(os.tmpdir(), 'argos_tm_c4_view_test.html');
const mockFetch = `<script>
  const stations=${JSON.stringify(catalog.estaciones)};
  const trunks=${JSON.stringify(catalog.troncales)};
  window.failNextDetail=false;
  window.delayNextDetail=false;
  window.fetch=async url=>{
    if(url.endsWith('/api/transmilenio/estaciones')){
      return {ok:true,json:async()=>({estaciones:stations})};
    }
    if(url.endsWith('/api/transmilenio/troncales')){
      return {ok:true,json:async()=>({troncales:trunks})};
    }
    if(url.endsWith('/api/transmilenio/resumen')){
      return {ok:true,json:async()=>({red:{total_estaciones:155,cobertura_pct:0},
        camaras:{activas:0},evasiones_hoy:{total:0}})};
    }
    const code=decodeURIComponent(url.split('/').pop());
    if(window.delayNextDetail){
      window.delayNextDetail=false;
      await new Promise(resolve=>setTimeout(resolve,180));
    }
    if(window.failNextDetail){
      window.failNextDetail=false;
      return {ok:false,status:503,json:async()=>({})};
    }
    const item=stations.find(station=>station.codigo===code);
    return item
      ? {ok:true,json:async()=>({...item,camaras:[],estadisticas:{hoy_total:0},
          eventos_recientes:[]})}
      : {ok:false,status:404,json:async()=>({})};
  };
  </script>`;
fs.writeFileSync(viewPreviewPath, `<!doctype html><html><head><meta charset="utf-8">
  <style>:root{--bg:#080b12;--bg2:#111927;--bg3:#172033;--texto:#e9eef9;
  --dim:#8997ad;--muted:#66738b;--borde2:#314057;--azul:#00a6d8;
  --rojo:#e40022;--verde:#74b51c;--amarillo:#ffc400}
  body{margin:0;background:#080b12}.hidden{display:none}
  #tm-schematic-container{width:1400px;height:900px;position:relative}</style>
  <script src="${layoutUrl}"></script><script src="${rendererUrl}"></script>
  ${mockFetch}</head><body>${view}</body></html>`, 'utf8');

const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));
let socket;
let nextId = 1;
const pending = new Map();
async function command(method, params = {}) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
async function evaluate(expression) {
  const response = await command('Runtime.evaluate', {
    expression, returnByValue: true, awaitPromise: true
  });
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
  return response.result.value;
}
async function mouse(type, x, y, extra = {}) {
  await command('Input.dispatchMouseEvent', {
    type, x, y, button: type === 'mousePressed' || type === 'mouseReleased' ? 'left' : 'none',
    clickCount: 1, ...extra
  });
}
async function stationCenter(code) {
  return evaluate(`(() => {
    const node=document.querySelector('[data-code="${code}"]');
    const r=node.querySelector('.tm-station-shape').getBoundingClientRect();
    return {x:r.left+r.width/2,y:r.top+r.height/2,width:r.width,height:r.height};
  })()`);
}
async function hoverAndClick(code) {
  const before = await stationCenter(code);
  await mouse('mouseMoved', before.x, before.y);
  await delay(80);
  const after = await stationCenter(code);
  assert.ok(Math.abs(after.x - before.x) < 0.1, `${code} moved on x`);
  assert.ok(Math.abs(after.y - before.y) < 0.1, `${code} moved on y`);
  assert.ok(Math.abs(after.width - before.width) < 0.1, `${code} changed width`);
  assert.ok(Math.abs(after.height - before.height) < 0.1, `${code} changed height`);
  const tip = await evaluate(`(() => {
    const t=document.getElementById('tm-station-tooltip'),s=getComputedStyle(t);
    const r=t.getBoundingClientRect();
    return {opacity:s.opacity,visibility:s.visibility,pointerEvents:s.pointerEvents,
      filter:s.filter,background:s.backgroundColor,color:s.color,
      left:r.left,right:r.right,top:r.top,bottom:r.bottom,
      width:innerWidth,height:innerHeight,text:t.textContent};
  })()`);
  assert.equal(tip.opacity, '1');
  assert.equal(tip.visibility, 'visible');
  assert.equal(tip.pointerEvents, 'none');
  assert.equal(tip.filter, 'none');
  assert.equal(tip.background, 'rgb(17, 25, 39)');
  assert.equal(tip.color, 'rgb(241, 245, 249)');
  assert.ok(tip.left >= 0 && tip.right <= tip.width);
  assert.ok(tip.top >= 0 && tip.bottom <= tip.height);
  assert.ok(tip.text.includes(code));
  if (code === 'TM-B-02') {
    const shot = await command('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(os.tmpdir(), 'argos_tm_c4_hover.png'),
      Buffer.from(shot.data, 'base64'));
  }
  await mouse('mousePressed', before.x, before.y);
  await mouse('mouseReleased', before.x, before.y);
  await delay(80);
  assert.equal((await evaluate('window.selected.at(-1)')), code);
  return { code, before, after, tip };
}

(async () => {
  const port = process.env.C4_CDP_PORT || '9223';
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = targets.find(item => item.type === 'page' &&
    (item.url.includes('argos_tm_c4_browser_test.html') || item.url.includes('argos_tm_c4_view_test.html')));
  if (!page) throw new Error('No se encontro la pagina de prueba en DevTools');
  socket = new WebSocket(page.webSocketDebuggerUrl);
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const entry = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) entry.reject(new Error(message.error.message));
    else entry.resolve(message.result);
  });
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  await command('Emulation.setDeviceMetricsOverride', {
    width: 1400, height: 900, deviceScaleFactor: 1, mobile: false
  });
  await command('Page.navigate', { url: pathToFileURL(previewPath).href });
  for (let attempt = 0; attempt < 30; attempt++) {
    if (await evaluate('Boolean(window.map && document.querySelector("[data-code=\'TM-B-02\']"))')) break;
    await delay(100);
  }
  assert.equal(await evaluate('document.querySelectorAll(".tm-station-node").length'), 147);
  const normal = await hoverAndClick('TM-B-02');
  const portal = await hoverAndClick('TM-L-01');
  const interchange = await hoverAndClick('TM-G-09');
  await hoverAndClick('TM-B-02');
  const panBefore = await evaluate('({x:map.panX,y:map.panY})');
  await mouse('mouseMoved', 1200, 700);
  await mouse('mousePressed', 1200, 700);
  await mouse('mouseMoved', 1202, 702);
  assert.deepEqual(await evaluate('({x:map.panX,y:map.panY})'), panBefore);
  await mouse('mouseMoved', 1225, 725);
  await mouse('mouseReleased', 1225, 725);
  const panAfter = await evaluate('({x:map.panX,y:map.panY})');
  assert.notDeepEqual(panAfter, panBefore);
  await command('Input.dispatchMouseEvent', {
    type: 'mouseWheel', x: 700, y: 450, deltaY: -180, deltaX: 0
  });
  assert.ok((await evaluate('map.scale')) > 0.94);
  const afterZoom = await hoverAndClick('TM-G-09');
  const zoomScale = await evaluate('map.scale');
  const repeatedSelection = await evaluate('window.selected');
  assert.deepEqual(repeatedSelection,
    ['TM-B-02', 'TM-L-01', 'TM-G-09', 'TM-B-02', 'TM-G-09']);
  const slightMove = await stationCenter('TM-B-03');
  await mouse('mouseMoved', slightMove.x, slightMove.y);
  await mouse('mousePressed', slightMove.x, slightMove.y);
  await mouse('mouseMoved', slightMove.x + 2, slightMove.y + 2);
  await mouse('mouseReleased', slightMove.x + 2, slightMove.y + 2);
  assert.equal(await evaluate('window.selected.at(-1)'), 'TM-B-03');
  await command('Page.navigate', { url: pathToFileURL(viewPreviewPath).href });
  for (let attempt = 0; attempt < 30; attempt++) {
    if (await evaluate('Boolean(document.querySelector("[data-code=\'TM-B-02\']"))')) break;
    await delay(100);
  }
  assert.equal(await evaluate('document.querySelectorAll(".tm-station-node").length'), 147);
  const viewCenter = await stationCenter('TM-B-02');
  await mouse('mouseMoved', viewCenter.x, viewCenter.y);
  const viewTooltip = await evaluate(`(() => {
    const style=getComputedStyle(document.getElementById('tm-station-tooltip'));
    return {opacity:style.opacity,background:style.backgroundColor,color:style.color};
  })()`);
  assert.equal(viewTooltip.opacity, '1');
  assert.equal(viewTooltip.background, 'rgb(17, 25, 39)');
  assert.equal(viewTooltip.color, 'rgb(241, 245, 249)');
  await evaluate('window.delayNextDetail=true');
  await mouse('mousePressed', viewCenter.x, viewCenter.y);
  await mouse('mouseReleased', viewCenter.x, viewCenter.y);
  const loadingDrawer = await evaluate(`({
    open: !document.getElementById('drawer-detalle-estacion').classList.contains('translate-x-full'),
    loading: !document.getElementById('drawer-load-status').classList.contains('hidden')
  })`);
  assert.equal(loadingDrawer.open, true);
  assert.equal(loadingDrawer.loading, true);
  await delay(220);
  const drawer = await evaluate(`({
    open: !document.getElementById('drawer-detalle-estacion').classList.contains('translate-x-full'),
    name: document.getElementById('drawer-estacion-nombre').textContent,
    statusHidden: document.getElementById('drawer-load-status').classList.contains('hidden')
  })`);
  assert.equal(drawer.open, true);
  assert.equal(drawer.name, 'Toberín');
  assert.equal(drawer.statusHidden, true);
  await evaluate(`document.querySelector('[data-code="TM-L-01"]')
    .dispatchEvent(new MouseEvent('click',{bubbles:true}))`);
  await delay(100);
  assert.equal(await evaluate('document.getElementById("drawer-estacion-nombre").textContent'),
    'Portal 20 de Julio');
  await evaluate(`window.failNextDetail=true;
    document.querySelector('[data-code="TM-G-09"]')
      .dispatchEvent(new MouseEvent('click',{bubbles:true}))`);
  await delay(100);
  const errorDrawer = await evaluate(`({
    open: !document.getElementById('drawer-detalle-estacion').classList.contains('translate-x-full'),
    text: document.getElementById('drawer-load-status').textContent,
    visible: !document.getElementById('drawer-load-status').classList.contains('hidden')
  })`);
  assert.equal(errorDrawer.open, true);
  assert.equal(errorDrawer.visible, true);
  assert.match(errorDrawer.text, /No se pudo cargar/);
  console.log(JSON.stringify({
    passed: true,
    stations: [normal.code, portal.code, interchange.code],
    centersStable: true, tooltipComputedStyle: normal.tip,
    pan: panAfter, zoomScale,
    repeatedSelection,
    smallMotionClick: 'TM-B-03', viewTooltip, loadingDrawer, drawer, errorDrawer
  }));
  socket.close();
})().catch(error => {
  console.error(error);
  if (socket) socket.close();
  process.exitCode = 1;
});
