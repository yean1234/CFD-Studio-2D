import * as THREE from '/studies/three.module.js';

const $ = id => document.getElementById(id);
let meta = null, scene, camera, renderer, points, frameGeneration = 0, caseGeneration = 0, rotation = 0, currentFrame = null;

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
  camera.position.set(0, 24, 60);
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
  if (points) {scene.remove(points); points.traverse(p => {p.geometry?.dispose(); p.material?.dispose();});}
  currentFrame = data;
  const field = $('field').value;
  const values = field === 'temperature' ? data.temperature_field_C : field === 'velocity' ? data.speed_m_s : data.concentration;
  const bounds = field === 'temperature' ? data.temperature_range_C : field === 'velocity' ? data.speed_range_m_s : [data.minimum, data.maximum];
  const unit = field === 'temperature' ? '°C' : field === 'velocity' ? 'm/s' : data.concentration_unit;
  const indices = data.cell_centres_m.map((_,i) => i).filter(i => $('slice').value === 'all' || Math.abs(data.cell_centres_m[i][1]-meta.geometry.width_m/2) <= .6);
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(indices.length * 3);
  const colors = new Float32Array(indices.length * 3);
  const span = Math.max(bounds[1] - bounds[0], Number.EPSILON);
  for (let i = 0; i < indices.length; i++) {
    const sourceIndex = indices[i];
    const xyz = data.cell_centres_m[sourceIndex];
    positions[3*i] = xyz[0] - meta.geometry.length_m/2;
    positions[3*i+1] = xyz[2] - (meta.geometry.eaves_m+meta.geometry.roof_rise_m)/2;
    positions[3*i+2] = xyz[1] - meta.geometry.width_m/2;
    const ratio = Math.max(0, Math.min(1, (values[sourceIndex]-bounds[0])/span));
    const c = new THREE.Color().setHSL((1-ratio)*0.66, 0.9, 0.56);
    colors[3*i] = c.r; colors[3*i+1] = c.g; colors[3*i+2] = c.b;
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  points = new THREE.Group();
  points.add(new THREE.Points(geometry, new THREE.PointsMaterial({size: 1.0, vertexColors: true, sizeAttenuation: true})));
  if (field === 'velocity' && bounds[1] > 0) {
    const stride = Math.max(1, Math.ceil(indices.length / 180));
    for (let j=0; j<indices.length; j+=stride) {
      const i=indices[j], xyz=data.cell_centres_m[i], u=data.velocity_m_s[i];
      const magnitude=data.speed_m_s[i];
      if (magnitude < bounds[1]*.03) continue;
      const direction=new THREE.Vector3(u[0],u[2],u[1]).normalize();
      const origin=new THREE.Vector3(xyz[0]-meta.geometry.length_m/2,
        xyz[2]-(meta.geometry.eaves_m+meta.geometry.roof_rise_m)/2,xyz[1]-meta.geometry.width_m/2);
      points.add(new THREE.ArrowHelper(direction,origin,3*magnitude/bounds[1],0xffffff,.4,.2));
    }
  }
  for (const block of meta.loading?.blocks || []) {
    const lo=block.min_m, hi=block.max_m;
    const box = new THREE.BoxGeometry(hi[0]-lo[0],hi[2]-lo[2],hi[1]-lo[1]);
    const outline = new THREE.LineSegments(new THREE.EdgesGeometry(box), new THREE.LineBasicMaterial({color:0xffffff}));
    box.dispose();
    outline.position.set((hi[0]+lo[0]-meta.geometry.length_m)/2,
      (hi[2]+lo[2]-meta.geometry.eaves_m-meta.geometry.roof_rise_m)/2,
      (hi[1]+lo[1]-meta.geometry.width_m)/2);
    points.add(outline);
  }
  points.rotation.y = rotation;
  scene.add(points);
  renderer.render(scene, camera);
  $('time').value = data.time_s;
  $('legend').textContent = `${data.time_s} s (${(data.time_s/3600).toFixed(2)} h) · ${bounds[0].toPrecision(5)}–${bounds[1].toPrecision(5)} ${unit} · 파랑: 낮음 / 빨강: 높음 (프레임별 범위) · 표시 ${indices.length.toLocaleString()} / 전체 ${data.total_cells.toLocaleString()}셀 · 원본장 대조 통과` + (field === 'velocity' ? ' · 화살표: 방향, 길이: 현재 최대속도 대비 상대값' : '') + (data.temperature_C == null ? '' : ` · 가정 기온 ${data.temperature_C.toFixed(2)} °C`);
  $('status').textContent = `원본장: ${data.source_files ? Object.values(data.source_files).join(' , ') : data.raw_file}`;
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
  const caseRequest = ++caseGeneration;
  ++frameGeneration;
  $('facts').replaceChildren();
  $('probeResult').textContent = '';
  $('legend').textContent = '계산 결과를 읽는 중입니다.';
  if (points && scene) {scene.remove(points); points.traverse(p => {p.geometry?.dispose(); p.material?.dispose();}); points=null; renderer.render(scene,camera);}
  $('frame').disabled = true;
  meta = null;
  currentFrame = null;
  if (!$('case').value) return;
  try {
    const loaded = await api(`/api/warehouse/results/meta?id=${encodeURIComponent($('case').value)}`);
    if (caseRequest !== caseGeneration) return;
    meta = loaded;
    $('field').value = 'concentration';
    for (const option of $('field').options) option.disabled = !(meta.available_fields || ['concentration']).includes(option.value);
    fact('연구 대상', '포대식 쌀 저장고의 ClO₂ 훈증');
    fact('계산 모델', meta.model === 'normalized_gable_verification' ? '정규화 추적자 수치시험' : meta.model === 'clo2_coupled_scenario' ? '부력 유동·열전달·ClO₂ 수송 연결 계산' : meta.model === 'clo2_plan_scenario' ? '계획도면·가정 기반 ClO₂ 확산' : 'ClO₂ 공기 중 가스 입력 시험');
    fact('농도 단위', meta.model === 'normalized_gable_verification' ? 'C/C_ref' : 'mg/m³ (저장 원본 kg/m³)');
    fact('수치 검증', meta.grid_assessment && !meta.grid_assessment.grid_converged ? '실행·보존 검사 통과 / 격자 수렴 기준 미달' : meta.numerical_pass ? '해당 시험 통과' : '실행·질량수지 검사 통과 / 수렴 미검증');
    fact('실험 검증', '미완료');
    fact('온도', meta.model === 'clo2_coupled_scenario' ? '열방정식으로 계산한 공간 온도장' : meta.temperature_timeseries_C ? '논문 외기온 곡선을 공간 균일 입력으로 가정' : '계산되지 않음');
    if (meta.loading) fact('적재 가정', `${meta.loading.blocks.length}개 블록 · 공극률 ${meta.loading.porosity} · 굴곡도 ${meta.loading.tortuosity}`);
    if (meta.model === 'clo2_plan_scenario') fact('수송 가정', '정지 공기·폐쇄 경계·초기 농도 펄스 · 반응/누출 생략');
    if (meta.porous_grain) {
      fact('곡물 모델', '포대에 담긴 곡물 적재 영역을 균질 다공성으로 정의');
      fact('가스 경계', '밀폐 · 누출은 해석 범위에서 제외');
      if (meta.grain_volume_report?.grain_bulk_volume_m3 != null)
        fact('곡물 영역 / 공극 부피', `${meta.grain_volume_report.grain_bulk_volume_m3.toFixed(2)} / ${meta.grain_volume_report.grain_pore_volume_m3.toFixed(2)} m³`);
    }
    if (meta.grid_assessment) fact('격자 비교', `${meta.grid_assessment.grid_converged ? '설정한 지표 통과' : '수렴 미완료'} · 비교 구간 ${meta.grid_assessment.compared_until_s} s`);
    if (meta.model === 'clo2_coupled_scenario') {
      fact('유속', '압력·운동량 계산 / 부력·적재 저항 / 겉보기 유속 m/s');
      fact('열수지 상대오차', meta.relative_energy_balance_error);
    }
    if (meta.assumptions?.length) {
      const details=document.createElement('details');
      details.style.gridColumn='1 / -1';
      const summary=document.createElement('summary');
      summary.textContent='입력에 기록된 가정·미검증 항목 펼치기';
      const list=document.createElement('ul');
      for (const text of meta.assumptions) {const item=document.createElement('li');item.textContent=text;list.append(item);}
      details.append(summary,list); $('facts').append(details);
    }
    fact('조회 위치', meta.coordinate_representation?.startsWith('exact_volume_centres') ? 'OpenFOAM과 대조한 셀 체적 중심' : '여섯 면 중심 평균의 근사 대표점');
    fact('형상', `${meta.geometry_basis} · 저장동 공칭 외형`);
    fact('질량수지 상대오차', meta.relative_balance_error);
    fact('원본 배열', meta.array_file);
    $('frame').max = meta.times_s.length - 1;
    $('frame').value = 0;
    $('frame').disabled = false;
    await loadFrame();
  } catch (error) {if (caseRequest === caseGeneration) $('status').textContent = error.message;}
}
$('frame').addEventListener('input', loadFrame);
for (const id of ['field', 'slice']) $(id).addEventListener('change', () => {if (currentFrame) showFrame(currentFrame);});
$('case').addEventListener('change', loadCase);
$('probe').addEventListener('submit', async e => {
  e.preventDefault();
  if (!meta) {$('probeResult').textContent = '먼저 계산 결과를 선택하세요.'; return;}
  const queryGeneration = caseGeneration;
  const params = new URLSearchParams({id: meta.id, x: $('x').value, y: $('y').value,
    z: $('z').value, time: $('time').value, max_distance: $('distance').value});
  try {
    const v = await api('/api/warehouse/results/sample?' + params);
    if (queryGeneration !== caseGeneration) return;
    $('probeResult').textContent = `농도: ${v.concentration.toPrecision(7)} ${v.concentration_unit}\n셀 #${v.cell_index} · 중심 거리 ${v.cell_centre_distance_m.toPrecision(4)} m · ${v.sampling}\n온도: ${v.temperature == null ? '계산되지 않음' : v.temperature.toFixed(3)+' °C '+(v.temperature_status === 'solved_energy_C' ? '(열방정식 계산)' : '(공간 균일 입력 가정)')}\n유속: ${v.velocity_m_s ? v.speed_m_s.toPrecision(6)+' m/s · 벡터 ('+v.velocity_m_s.map(x=>x.toPrecision(5)).join(', ')+') m/s' : '계산되지 않음'}\n원본: ${v.source_files.join(' , ')}`;
  } catch (error) {if (queryGeneration === caseGeneration) $('probeResult').textContent = error.message;}
});
try {
  const data = await api('/api/warehouse/results');
  $('case').replaceChildren(new Option('계산 결과 선택', ''));
  for (const entry of data.results) $('case').add(new Option(`${entry.id} · ${entry.model} · ${entry.cells.toLocaleString()}셀`, entry.id));
  $('status').textContent = data.results.length ? '완료된 계산을 선택하세요.' : '완료된 저장고 결과가 없습니다.';
} catch (error) {$('status').textContent = error.message;}
