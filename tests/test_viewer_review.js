// Run with: node --test tests/test_viewer_review.js
// Evaluate production functions without importing app.py, opening a browser, or using project data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'cfd_studio/app.py'), 'utf8');
const tracer = fs.readFileSync(path.join(root, 'cfd_studio/tracer_viewer.js'), 'utf8');
const warehouse = fs.readFileSync(path.join(root, 'cfd_studio/warehouse_workspace.html'), 'utf8');

function declaration(source, prefix) {
  const lines = source.split('\n');
  const start = lines.findIndex(line => line.startsWith(prefix));
  assert.ok(start >= 0, `Missing declaration: ${prefix}`);
  // Let the JavaScript parser find the complete declaration, including nested functions.
  for (let end = start + 1; end <= lines.length; end++) {
    const code = lines.slice(start, end).join('\n');
    try { new vm.Script(code); return code; } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
    }
  }
  throw Error(`Incomplete declaration: ${prefix}`);
}

function dom() {
  const elements = new Map();
  function element(id = '') {
    return {
      id, style: {}, dataset: {}, checked: false, disabled: false, value: '',
      textContent: '', innerHTML: '', children: [], listeners: {},
      classList: {toggle() {}, remove() {}},
      append(...children) { this.children.push(...children); },
      appendChild(child) { this.append(child); },
      add(child) { this.append(child); },
      replaceChildren(...children) { this.children = children; },
      addEventListener(name, callback) { (this.listeners[name] ??= []).push(callback); },
      setAttribute() {},
      querySelector(selector) { return get(id + selector); },
      closest() { return get(id + ':label'); },
    };
  }
  function get(id) {
    if (!elements.has(id)) elements.set(id, element(id));
    return elements.get(id);
  }
  const outputs = ['outBub', 'outPhase', 'outFlow', 'outTherm'];
  outputs.forEach((id, i) => {
    get(id).closest = () => get(['outOptBub', 'outOptPhase', 'outOptFlow', 'outOptTherm'][i]);
  });
  const walk = node => [node, ...node.children.flatMap(walk)];
  const document = {
    getElementById: get, body: get('body'),
    createElement: () => element(), createTextNode: text => ({text, children: []}),
    querySelector: selector => selector === '#tcbar .grad' ? null : get(selector),
    querySelectorAll: selector => {
      if (selector === '#outGrid input[data-output]') return outputs.map(get);
      if (selector === '[data-group]') return ['geometry', 'mesh'].flatMap(id => walk(get(id))).filter(e => e.dataset?.group);
      return [];
    },
  };
  return {document, get};
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

async function eventually(predicate) {
  for (let i = 0; i < 100; i++) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 5));
  }
  assert.fail('State did not settle');
}

const immersionConfig = () => ({
  _해석유형: 'immersion', tank: {width_mm: 456, depth_mm: 70, liquid_height_mm: 800},
  layers: {dielectric_mm: 400}, board: {}, coil: {}, heater: {cpus: []},
  run: {output_fields: ['bubble', 'phase', 'flow', 'therm']},
});
const siloConfig = () => ({_해석유형: 'grain_silo', silo: {}, run: {output_fields: ['pressure', 'turbulence', 'flow']}});
const tracerConfig = () => ({
  _해석유형: 'gas_transport', tracer: {lengths_m: [1, 1, 1], shape_xyz: [1, 1, 1]},
  run: {output_fields: ['concentration', 'sorbed']},
  scalar_ranges: {concentration: [0, 10], sorbed: [0, 10]},
});
const tracerRows = () => Array.from({length: 11}, (_, i) => ({
  t: i / 10, concentration: `concentration_${i / 10}.bin`, sorbed: `sorbed_${i / 10}.bin`,
}));

function scalarBuffer(filename) {
  const data = new ArrayBuffer(44), view = new DataView(data);
  view.setUint32(0, filename.includes('sorbed') ? 0x534f5231 : 0x434f4e31, false);
  for (let i = 0; i < 3; i++) { view.setUint32(4 + i * 4, 1, true); view.setFloat32(28 + i * 4, 1, true); }
  view.setFloat32(40, Number(filename.match(/_([\d.]+)\.bin/)[1]) * 10, true);
  return data;
}

function viewer() {
  const {document, get} = dom(), draws = [], messages = [];
  const ctx = {
    document, console, performance, MODE: 'cfd', CFG: null, RUNCFG: null, VIZCFG: null,
    IMMERSIONCFG: null, RUNPREF: false, G: {}, PROBEPTS: [], FRAMES: [], idx: 0,
    clock: 0, last: 0, playing: false, PLAYENDED: false, PLAYBUFFERING: false, PLAYBUFSEQ: 0,
    VFRAMEGEN: 0, VLOADGEN: 0, VSTREAMERR: new Set(), VPREFETCHTOKEN: 0,
    VPREFETCHEND: -1, VPREFETCHBUSY: false, LOADED_RID: '', VPROJ: null, PROJ: '',
    PROJGEN: 0, NEWMODE: false, RESETREADY: false, HASPEND: true, CURC: 'active', CFGREF: '', LASTPROJS: [],
    FLOWMAP: {}, THERMMAP: {}, PHASEMAP: {}, PRESSUREMAP: {}, TURBMAP: {},
    PHASECACHE: new Map(), FDT: .1, REC: null, VW: 800, VH: 600, rad: 1000, tgt: [0, 0, 0],
    gl: new Proxy({}, {get: () => () => {}}),
    mesh: () => ({b: {}}), boxEdges: () => [], boxTris: () => [],
    cylinderTris: () => [], cylinderEdges: () => [],
    LY: id => get(id).checked, uiTick: async () => {},
    toast: message => messages.push(message),
    drawTvol: grid => draws.push(grid.v[0]), updateScalarBar() {}, dL() {},
    persp() {}, eye() {}, viewUp() {}, lookAt() {}, mul() {},
    refreshVizInfo() {}, resize() {}, saveUI() {},
    runBusyNow: () => false, clearDash() {}, updateConfigDeleteButton() {},
    updateSlots() {}, setDataAvail() {}, fillConds() {}, renderProjects() {},
    srvFromInfo() {}, showExtract() {}, adoptExtractWatch() {},
    vzrid: () => 'tracer-test', fetchVizBuffer: async filename => scalarBuffer(filename),
    setTimeout: (callback, delay) => delay === 60 || delay === 30 ? 0 : setTimeout(callback, delay),
    loadMsg: message => { get('frSt').textContent = message; },
    fetch: async () => ({json: async () => ({rid: 'tracer-test', config: tracerConfig(), tracer_frames: tracerRows()})}),
  };
  vm.createContext(ctx);
  const constants = ['const OUTIDS=', 'const OUTPUT_LAYOUTS=', 'const VIEWLAYERSTATE='];
  const functions = [
    'configureViewerFields', 'configureOutputFields', 'selectedOutputList', 'setConfig',
    'setMode', 'isSiloConfig', 'applyAnalysisTypeUI', 'fillRunInputs',
    'trimFieldCache', 'trimVizCache', 'vizFrameReady', 'ensureVizFrame', 'prefetchViz',
    'playbackStride', 'playbackBufferReady', 'readyFrameAtOrBefore',
    'framePlayTime', 'frameIndexAt', 'runAxis', 'fmtPlaybackSeconds', 'finishFrames',
    'uploadPoints', 'loadFrames', 'renderPlayButton', 'setPlay', 'setPlaybackEnded',
    'resetPlaybackToStart', 'startBufferedPlayback', 'togglePlay', 'scrub', 'changePlaybackSpeed',
    'newProj', 'run',
  ];
  const code = constants.map(prefix => declaration(app, prefix));
  for (const name of functions) code.push(declaration(app, `${['ensureVizFrame', 'loadFrames', 'startBufferedPlayback', 'newProj', 'run'].includes(name) ? 'async ' : ''}function ${name}(`));
  vm.runInContext(code.join('\n') + '\n' + tracer, ctx);
  get('speed').value = '1';
  return {ctx, get, draws, messages, run: code => vm.runInContext(code, ctx)};
}

for (const [name, config] of [['immersion', immersionConfig], ['silo', siloConfig]]) {
  test(`tracer Viewer preserves ${name} CFD outputs through new-project submission`, async () => {
    const {ctx} = viewer(), original = config(), result = tracerConfig();
    ctx.setConfig(original); ctx.fillRunInputs(original);
    ctx.setMode('viz'); ctx.setConfig(result); ctx.setMode('cfd');
    assert.equal(ctx.CFG, original);
    assert.deepEqual(Array.from(ctx.selectedOutputList()).sort(), original.run.output_fields.slice().sort());
    assert.equal(ctx.VIZCFG, result);
    ctx.setMode('viz'); assert.equal(ctx.CFG, result);
    await ctx.newProj();
    assert.equal(ctx.NEWMODE, true); assert.equal(ctx.CFG, original);
    let submitted;
    ctx.fetch = async (url, options) => {
      assert.equal(url, '/api/run'); submitted = JSON.parse(options.body);
      return {json: async () => ({ok: false, msg: 'Isolated test; no solver launched'})};
    };
    await ctx.run('fresh');
    assert.equal(submitted.config._해석유형, original._해석유형);
    assert.deepEqual(submitted.output_fields.slice().sort(), original.run.output_fields.slice().sort());
  });

  test(`tracer selected after ${name} remains the CFD configuration after tab switching`, () => {
    const {ctx} = viewer(), result = tracerConfig();
    ctx.setConfig(config()); ctx.setConfig(result);
    ctx.setMode('viz'); ctx.setMode('cfd');
    assert.equal(ctx.CFG, result);
    assert.equal(ctx.RUNCFG, result);
    assert.deepEqual(Array.from(ctx.selectedOutputList()), ['concentration', 'sorbed']);
  });
}

for (const cached of [false, true]) {
  test(`8x tracer playback resumes at 0.8s near a 1s end (${cached ? 'cached' : 'uncached'})`, async () => {
    const {ctx, get, run} = viewer(); ctx.MODE = 'viz';
    await ctx.loadFrames(false);
    await eventually(() => !ctx.VPREFETCHBUSY);
    get('speed').value = '8';
    if (!cached) run('TRACERMAP={concentration:{},sorbed:{}}');
    ctx.idx = 8; ctx.clock = .8;
    try {
      const playback = ctx.startBufferedPlayback(true);
      await eventually(() => ctx.playing);
      await playback;
      assert.equal(ctx.PLAYBUFFERING, false);
      ctx.frameTracer(100, .025);
      await eventually(() => ctx.tracerFrameReady(10));
      ctx.frameTracer(110, .025);
      assert.equal(ctx.clock, 1);
      assert.equal(ctx.PLAYENDED, true);
    } finally { ctx.PLAYBUFSEQ++; }
  });
}

test('switching tracer layers near the end checks the selected field cache', async () => {
  const {ctx, get} = viewer(); ctx.MODE = 'viz';
  await ctx.loadFrames(false); await eventually(() => !ctx.VPREFETCHBUSY);
  get('speed').value = '8'; get('lyPhase').checked = true; get('lyBub').checked = false;
  assert.equal(ctx.playbackBufferReady(8, 1.5), false);
  ctx.prefetchViz(8, true);
  await eventually(() => !ctx.VPREFETCHBUSY);
  assert.equal(ctx.playbackBufferReady(8, 1.5), true);
});

test('pausing and resuming preserve the interpolated field and physical time', async () => {
  const {ctx, draws, get, run} = viewer(); ctx.MODE = 'viz'; ctx.setConfig(tracerConfig());
  ctx.FRAMES = [{t: 0, pt: 0}, {t: 1, pt: 1}]; ctx.FDT = 1; ctx.clock = .5;
  run('TRACERMAP.concentration={0:{v:new Float32Array([0])},1:{v:new Float32Array([10])}}');
  ctx.playing = true; ctx.frameTracer(100, 0); ctx.togglePlay(); ctx.frameTracer(120, 0);
  assert.deepEqual(draws, [5, 5]); assert.match(get('tlab').textContent, /0\.50/);
  ctx.togglePlay(); await eventually(() => ctx.playing);
  assert.equal(ctx.clock, .5);
});

test('tracer interpolation remains throttled while playing and exact when paused', () => {
  const {ctx, draws, run} = viewer(); ctx.MODE = 'viz'; ctx.setConfig(tracerConfig());
  ctx.FRAMES = [{t: 0, pt: 0}, {t: 1, pt: 1}]; ctx.FDT = 1; ctx.clock = .5;
  run('TRACERMAP.concentration={0:{v:new Float32Array([0])},1:{v:new Float32Array([10])}}');
  ctx.playing = true; ctx.prefetchViz = () => {};
  ctx.frameTracer(100, 0); const first = run('TRACERBLEND.T.v');
  ctx.frameTracer(116, .016);
  assert.equal(run('TRACERBLEND.T.v'), first);
  ctx.playing = false; ctx.frameTracer(120, 0);
  assert.notEqual(run('TRACERBLEND.T.v'), first);
  assert.ok(Math.abs(draws.at(-1) - 5.16) < 1e-5);
  const paused = run('TRACERBLEND.T.v'); ctx.frameTracer(200, 0);
  assert.equal(run('TRACERBLEND.T.v'), paused);
});

test('Play requested during tracer loading is honored after loading', async () => {
  const {ctx} = viewer(), response = deferred(); ctx.MODE = 'viz';
  ctx.fetch = () => response.promise;
  const loading = ctx.loadFrames(false);
  ctx.togglePlay(); assert.equal(ctx.loadFrames.autoplay, true);
  response.resolve({json: async () => ({rid: 'tracer-test', config: tracerConfig(), tracer_frames: tracerRows()})});
  await loading; await eventually(() => ctx.playing);
  assert.equal(ctx.FRAMES.length, 11);
  assert.equal(ctx.PLAYBUFFERING, false);
});

test('loading tracer results without Play stays paused', async () => {
  const {ctx} = viewer(); ctx.MODE = 'viz';
  await ctx.loadFrames(false); await eventually(() => !ctx.VPREFETCHBUSY);
  assert.equal(ctx.playing, false);
});

test('Studies is a direct header link with a mobile layout in all analysis modes', () => {
  const header = app.slice(app.indexOf('<div id="hdr">'), app.indexOf('<div id="app">'));
  assert.match(header, /<a\b[^>]*id="studiesLink"[^>]*href="\/studies"/);
  const mobile = app.slice(app.indexOf('@media(max-width:700px)'), app.indexOf('</style></head>'));
  assert.match(mobile, /#hdr\{display:grid;/);
  assert.match(mobile, /#studiesLink\{grid-column:2;grid-row:2;/);
  assert.doesNotMatch(mobile, /#studiesLink[^{}]*\{[^}]*display:none/);
});

const geometry = length => ({geometry: {length_m: length}, mesh: {nx: 2}, unresolved: []});
async function warehouseEditor() {
  const {document, get} = dom(), requests = [], waiting = [], store = {
    template: geometry(78), settings: [{id: 'a', name: 'A', geometry_spec: geometry(90)}], jobs: [],
  };
  const ctx = {
    document, structuredClone, console, confirm: () => false, setInterval() {},
    Option: function(text, value) { this.text = text; this.value = value; this.children = []; },
    fetch: async (url, options) => {
      if (!options?.method) return {ok: true, json: async () => structuredClone(store)};
      const response = deferred(); requests.push({url, body: JSON.parse(options.body)}); waiting.push(response);
      return response.promise;
    },
  };
  vm.createContext(ctx);
  vm.runInContext(warehouse.match(/<script>([\s\S]*?)<\/script>/)[1], ctx);
  await eventually(() => !get('save').disabled);
  return {ctx, get, store, requests, waiting, inputs: () => document.querySelectorAll('[data-group]')};
}

test('warehouse preset switching preserves unsaved inputs when cancelled', async () => {
  const {ctx, get, inputs} = await warehouseEditor();
  const input = inputs()[0]; input.value = '85'; input.oninput();
  get('presets').value = 'a'; get('presets').onchange();
  assert.equal(get('presets').value, ''); assert.equal(input.value, '85');
  assert.equal(get('check').disabled, true);
  ctx.confirm = () => true; get('presets').value = 'a'; get('presets').onchange();
  assert.equal(inputs()[0].value, 90); assert.equal(get('check').disabled, false);
  get('name').value = 'renamed'; get('name').oninput();
  await ctx.refresh(); assert.equal(get('check').disabled, true);
});

test('warehouse save locks the snapshot despite polling and blocks duplicate requests', async () => {
  const {ctx, get, store, inputs, requests, waiting} = await warehouseEditor();
  inputs()[0].value = '85'; inputs()[0].oninput(); get('name').value = 'Edited';
  const save = get('form').onsubmit({preventDefault() {}});
  assert.equal(get('save').disabled, true); assert.equal(get('presets').disabled, true);
  assert.equal(get('name').disabled, true); assert.ok(inputs().every(input => input.disabled));
  await ctx.refresh(); assert.equal(get('check').disabled, true);
  await get('form').onsubmit({preventDefault() {}}); await get('check').onclick();
  assert.equal(requests.length, 1); assert.equal(requests[0].body.geometry_spec.geometry.length_m, 85);
  store.settings.push({id: 'b', name: 'Edited', geometry_spec: geometry(85)});
  waiting[0].resolve({ok: true, json: async () => ({ok: true, result: {id: 'b'}})});
  await save;
  assert.equal(get('presets').value, 'b'); assert.equal(get('check').disabled, false);
  const check = get('check').onclick();
  assert.equal(requests[1].body.id, 'b');
  await ctx.refresh(); assert.equal(get('check').disabled, true);
  await get('check').onclick(); assert.equal(requests.length, 2);
  store.jobs = [{name: 'Edited', status: 'running'}];
  waiting[1].resolve({ok: true, json: async () => ({ok: true})}); await check;
  assert.equal(get('check').disabled, true); assert.equal(get('save').disabled, false);
});

test('warehouse failed save retains editable unsaved input and cannot check an older snapshot', async () => {
  const {get, inputs, waiting} = await warehouseEditor();
  get('presets').value = 'a'; get('presets').onchange();
  inputs()[0].value = '85'; inputs()[0].oninput();
  const save = get('form').onsubmit({preventDefault() {}});
  waiting[0].resolve({ok: false, json: async () => ({ok: false, msg: 'Save failed'})}); await save;
  assert.equal(get('save').disabled, false); assert.equal(get('check').disabled, true);
  assert.equal(inputs()[0].value, '85'); assert.equal(get('message').textContent, 'Save failed');
});
