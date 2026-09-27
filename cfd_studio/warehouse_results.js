import * as THREE from '/studies/three.module.js';

const $ = id => document.getElementById(id);
let meta = null, scene, camera, renderer, points, frameGeneration = 0, rotation = 0;

async function api(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) throw Error(data.error || '결과를 읽지 못했습니다');
  return data;
}
function fact(label, value) {
  const item = document.createElement('div');
  const title = document.createElement('span');
  const detail = document.createElement('strong');
  title.textContent = label;
  detail.textContent = String(value);
  item.append(title, detail);
  $('facts').append(item);
}
function rendererReady() {
  if (renderer) return;
  const host = $('scene');
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x152530);
  camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
  camera.position.set(0, 42, 115);
  camera.lookAt(0, 0, 0);
  renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  host.append(renderer.domElement);
  const resize = () => {
    renderer.setSize(host.clientWidth, host.clientHeight);
    camera.aspect = host.clientWidth / host.clientHeight;
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
  };
  window.addEventListener('resize', resize);
  let down = null;
  host.addEventListener('pointerdown', e => {down = e.clientX; host.setPointerCapture(e.pointerId);});
  host.addEventListener('pointermove', e => {
    if (down === null || !points) return;
    rotation += (e.clientX - down) * 0.008;
    down = e.clientX;
    points.rotation.y = rotation;
    renderer.render(scene, camera);
  });
  host.addEventListener('pointerup', () => {down = null;});
  host.addEventListener('pointercancel', () => {down = null;});
  host.addEventListener('wheel', e => {
    e.preventDefault();
    camera.position.multiplyScalar(e.deltaY > 0 ? 1.08 : 0.92);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  }, {passive: false});
  resize();
}
function showFrame(data) {
  rendererReady();
  if (points) {scene.remove(points); points.geometry.dispose(); points.material.dispose();}
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(data.displayed_cells * 3);
  const colors = new Float32Array(data.displayed_cells * 3);
  const span = Math.max(data.maximum - data.minimum, Number.EPSILON);
  for (let i = 0; i < data.displayed_cells; i++) {
    const xyz = data.cell_centres_m[i];
    positions[3*i] = xyz[0] - meta.geometry.length_m/2;
    positions[3*i+1] = xyz[2] - (meta.geometry.eaves_m+meta.geometry.roof_rise_m)/2;
    positions[3*i+2] = xyz[1] - meta.geometry.width_m/2;
    const ratio = Math.max(0, Math.min(1, (data.concentration[i]-data.minimum)/span));
    const c = new THREE.Color().setHSL((1-ratio)*0.66, 0.9, 0.56);
    colors[3*i] = c.r; colors[3*i+1] = c.g; colors[3*i+2] = c.b;
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  points = new THREE.Points(geometry, new THREE.PointsMaterial({size: 1.0, vertexColors: true, sizeAttenuation: true}));
  points.rotation.y = rotation;
  scene.add(points);
  renderer.render(scene, camera);
  $('time').value = data.time_s;
  $('legend').textContent = `${data.time_s} s · ${data.minimum.toPrecision(5)}–${data.maximum.toPrecision(5)} ${data.concentration_unit} · 표시 ${data.displayed_cells.toLocaleString()} / 전체 ${data.total_cells.toLocaleString()}셀 · 원본장 대조 통과`;
  $('status').textContent = `원본장: ${data.raw_file}`;
}
async function loadFrame() {
  const generation = ++frameGeneration;
  if (!meta) return;
  try {
    const data = await api(`/api/warehouse/results/frame?id=${encodeURIComponent(meta.id)}&index=${$('frame').value}`);
    if (generation === frameGeneration) showFrame(data);
  } catch (error) {if (generation === frameGeneration) $('status').textContent = error.message;}
}
async function loadCase() {
  ++frameGeneration;
  $('facts').replaceChildren();
  $('frame').disabled = true;
  meta = null;
  if (!$('case').value) return;
  try {
    meta = await api(`/api/warehouse/results/meta?id=${encodeURIComponent($('case').value)}`);
    fact('연구 대상', '포대식 쌀 저장고의 ClO₂ 훈증');
    fact('계산 모델', meta.model === 'normalized_gable_verification' ? '정규화 추적자 수치시험' : 'ClO₂ 공기 중 가스 입력 시험');
    fact('농도 단위', meta.model === 'normalized_gable_verification' ? 'C/C_ref' : 'mg/m³ (저장 원본 kg/m³)');
    fact('수치 검증', meta.numerical_pass ? '해당 시험 통과' : '미검증');
    fact('실험 검증', '미완료');
    fact('온도장', '계산되지 않음');
    fact('형상', `${meta.geometry_basis} · 저장동 공칭 외형`);
    fact('질량수지 상대오차', meta.relative_balance_error);
    fact('원본 배열', meta.array_file);
    $('frame').max = meta.times_s.length - 1;
    $('frame').value = 0;
    $('frame').disabled = false;
    await loadFrame();
  } catch (error) {$('status').textContent = error.message;}
}
$('frame').addEventListener('input', loadFrame);
$('case').addEventListener('change', loadCase);
$('probe').addEventListener('submit', async e => {
  e.preventDefault();
  if (!meta) {$('probeResult').textContent = '먼저 계산 결과를 선택하세요.'; return;}
  const params = new URLSearchParams({id: meta.id, x: $('x').value, y: $('y').value,
    z: $('z').value, time: $('time').value, max_distance: $('distance').value});
  try {
    const v = await api('/api/warehouse/results/sample?' + params);
    $('probeResult').textContent = `농도: ${v.concentration.toPrecision(7)} ${v.concentration_unit}\n셀 #${v.cell_index} · 중심 거리 ${v.cell_centre_distance_m.toPrecision(4)} m · ${v.sampling}\n온도: 계산되지 않음\n원본: ${v.source_files.join(' , ')}`;
  } catch (error) {$('probeResult').textContent = error.message;}
});
try {
  const data = await api('/api/warehouse/results');
  $('case').replaceChildren(new Option('계산 결과 선택', ''));
  for (const entry of data.results) $('case').add(new Option(`${entry.id} · ${entry.model} · ${entry.cells.toLocaleString()}셀`, entry.id));
  $('status').textContent = data.results.length ? '완료된 계산을 선택하세요.' : '완료된 저장고 결과가 없습니다.';
} catch (error) {$('status').textContent = error.message;}
