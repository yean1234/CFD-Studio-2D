import * as THREE from "/studies/three.module.js";

const $ = (id) => document.getElementById(id);
const labels = {
  layout: "적재 배치",
  spacing_m: "적재 간격",
  supply_positions: "가스 공급 위치",
  total_supply: "총 공급량",
  temperature_K: "온도",
  leakage: "누설",
  bag_resistance: "포대 전달 저항",
  porosity: "공극률",
  diffusion: "확산 계수",
  reaction: "반응 계수",
  mesh_m: "격자 간격",
  dt_s: "계산 시간간격",
  evaluation_s: "평가시간",
  write_interval_s: "저장 간격",
  convergence: "수렴 기준",
};
let schema,
  study = "",
  revision = null,
  baseline = null,
  preview = null,
  dirty = false,
  ready = false,
  listed = false,
  loading = false,
  creating = false,
  previewing = false,
  committing = false,
  importing = false,
  incompatible = false,
  previewReadOnly = true,
  generation = 0;
const fields = {};
const drafts = new Map();
const commonTemplate = {
  geometry: { length_m: null, width_m: null, eaves_m: null },
  stored_mass_kg: null,
  mass_tolerance_kg: null,
  source_count: null,
  supply_duration_s: null,
  wall_clearance_m: null,
  maximum_stack_height_m: null,
  aisles: [],
  allowed_source_regions: [],
};
async function api(path, data) {
  const r = await fetch(
    path,
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  const v = await r.json();
  if (!r.ok || v.ok === false) throw Error(v.msg || "요청 실패");
  return v;
}
function message(v) {
  $("status").textContent = v.message || v;
}
function storage(method, key, value) {
  try {
    return localStorage[method](key, value);
  } catch {
    $("draftStatus").textContent =
      "브라우저 보관함을 사용할 수 없습니다. 이 페이지를 닫으면 미확정 입력을 잃을 수 있습니다.";
    return null;
  }
}
function draftKey(id = study) {
  return "cfd-research-draft-" + id;
}
function controls() {
  const blocked = !ready || creating || committing;
  const designBlocked = blocked || incompatible;
  $("study").disabled = !listed || creating || committing;
  $("name").disabled = blocked;
  $("create").disabled = blocked || importing || !$("name").value.trim();
  for (const id of ["common", "seed", "baseline", "download"])
    $(id).disabled = designBlocked;
  $("import").disabled = designBlocked || importing;
  $("preview").disabled = designBlocked || !study || previewing;
  $("commit").disabled =
    designBlocked ||
    importing ||
    previewReadOnly ||
    !preview?.candidates.some((r) => r.valid);
  for (const f of Object.values(fields))
    for (const [kind, el] of Object.entries(f))
      el.disabled = designBlocked || (kind === "value" && f.mode.value === "derived");
  $("groups").setAttribute("aria-busy", String(loading));
}
function rememberSelection() {
  storage("setItem", "cfd-selected-study", JSON.stringify(study));
  const url = new URL(window.location.href);
  if (study) url.searchParams.set("study", study);
  else url.searchParams.delete("study");
  window.history.replaceState(null, "", url);
  $("studiesLink").href =
    "/studies" + (study ? "?study=" + encodeURIComponent(study) : "");
}
// JSON이 완성되지 않아도 공백과 입력 문자열을 그대로 Study별로 보관한다.
function capture() {
  return {
    version: 1,
    profile: schema.profile,
    variables: Object.fromEntries(
      Object.entries(fields).map(([key, f]) => [
        key,
        Object.fromEntries(
          Object.entries(f).map(([kind, el]) => [kind, el.value]),
        ),
      ]),
    ),
    common: $("common").value,
    seed: $("seed").value,
    baseline,
  };
}
function saveDraft() {
  const raw = capture();
  drafts.set(study, raw);
  storage("setItem", draftKey(), JSON.stringify(raw));
}
function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function check(ok, label) {
  if (!ok) throw Error("설계 형식을 확인해 주세요: " + label);
}
function validMode(key, mode) {
  return (
    ["fixed", "search", "derived"].includes(mode) &&
    (!schema.locked_in_initial_comparison.includes(key) || mode === "fixed") &&
    (mode !== "derived" || key === "spacing_m")
  );
}
// 전체 형식을 검사하고 문자열을 준비한 뒤 한 번에 적용해 부분 덮어쓰기를 막는다.
function designDraft(d) {
  const keys = Object.keys(fields);
  check(object(d) && d.profile === schema.profile, "연구 설계 프로필");
  check(
    Object.keys(d).length === 5 &&
      ["variables", "common", "sampling", "baseline"].every((k) =>
        Object.hasOwn(d, k),
      ),
    "필수 항목",
  );
  check(
    object(d.variables) && Object.keys(d.variables).length === keys.length,
    "변수 목록",
  );
  const variables = {};
  for (const key of keys) {
    const v = d.variables[key];
    check(object(v) && validMode(key, v.mode), labels[key] + " 적용 방식");
    check(
      Object.keys(v).every((k) =>
        [
          "mode",
          "value",
          "choices",
          "bounds",
          "count",
          "unit",
          "evidence",
          "rule",
        ].includes(k),
      ),
      labels[key] + " 항목",
    );
    check(v.unit == null || typeof v.unit === "string", labels[key] + " 단위");
    if (v.mode === "fixed")
      check(Object.hasOwn(v, "value"), labels[key] + " 값");
    if (v.mode === "derived")
      check(
        v.rule === schema.derived_rules[key],
        labels[key] + " 자동 계산 규칙",
      );
    if (v.mode === "search")
      check(
        Array.isArray(v.choices)
          ? v.choices.length > 0
          : v.choices == null &&
              key === "spacing_m" &&
              Array.isArray(v.bounds) &&
              v.bounds.length === 2 &&
              v.bounds.every(
                (n) => typeof n === "number" && Number.isFinite(n),
              ) &&
              Number.isInteger(v.count),
        labels[key] + " 후보 목록·범위",
      );
    variables[key] = {
      mode: v.mode,
      value: JSON.stringify(
        v.mode === "search"
          ? (v.choices ?? { bounds: v.bounds, count: v.count })
          : (v.value ?? null),
        null,
        2,
      ),
      unit: v.unit || "",
      evidence:
        typeof v.evidence === "string"
          ? v.evidence
          : v.evidence == null
            ? ""
            : JSON.stringify(v.evidence),
    };
  }
  check(
    object(d.common) &&
      Object.keys(commonTemplate).every((k) => Object.hasOwn(d.common, k)),
    "공통 조건",
  );
  check(
    object(d.common.geometry) &&
      Object.keys(commonTemplate.geometry).every(
        (k) =>
          Object.hasOwn(d.common.geometry, k) &&
          (d.common.geometry[k] === null ||
            Number.isFinite(d.common.geometry[k])),
      ),
    "저장고 치수",
  );
  for (const [key, value] of Object.entries(commonTemplate)) {
    if (Array.isArray(value))
      check(Array.isArray(d.common[key]) && d.common[key].every(object), key);
    else if (value === null)
      check(d.common[key] === null || Number.isFinite(d.common[key]), key);
  }
  check(
    object(d.sampling) &&
      Object.keys(d.sampling).length === 2 &&
      d.sampling.method === "cartesian_choices" &&
      Number.isSafeInteger(d.sampling.seed),
    "샘플링·정수 시드",
  );
  check(
    d.baseline === null ||
      (object(d.baseline) &&
        Object.keys(d.baseline).every((k) => keys.includes(k)) &&
        keys.every(
          (k) =>
            d.variables[k].mode === "derived" || Object.hasOwn(d.baseline, k),
        )),
    "기준안 변수",
  );
  return {
    version: 1,
    profile: d.profile,
    variables,
    common: JSON.stringify(d.common, null, 2),
    seed: String(d.sampling.seed),
    baseline: d.baseline,
  };
}
function restore(raw) {
  check(
    object(raw) &&
      raw.version === 1 &&
      raw.profile === schema.profile &&
      object(raw.variables) &&
      typeof raw.common === "string" &&
      typeof raw.seed === "string" &&
      (raw.baseline === null || object(raw.baseline)),
    "초안",
  );
  for (const [key, f] of Object.entries(fields))
    check(
      object(raw.variables[key]) &&
        validMode(key, raw.variables[key].mode) &&
        Object.keys(f).every(
          (kind) => typeof raw.variables[key][kind] === "string",
        ),
      labels[key] + " 초안",
    );
  for (const [key, f] of Object.entries(fields))
    for (const [kind, el] of Object.entries(f))
      el.value = raw.variables[key][kind];
  $("common").value = raw.common;
  $("seed").value = raw.seed;
  baseline = raw.baseline;
  $("baselineData").textContent = baseline
    ? JSON.stringify(baseline, null, 2)
    : "미지정";
}
function clearPreview() {
  preview = null;
  previewReadOnly = true;
  $("candidates").replaceChildren();
  $("diff").textContent = "";
  $("selected").textContent = "";
  clearScene();
}
function read() {
  const variables = {};
  for (const [key, f] of Object.entries(fields)) {
    const mode = f.mode.value,
      entry = {
        mode,
        unit: f.unit.value || null,
        evidence: f.evidence.value || null,
      };
    if (mode === "derived") entry.rule = "minimum_horizontal_clearance";
    else {
      let value;
      try {
        value = JSON.parse(f.value.value);
      } catch {
        throw Error(labels[key] + " JSON을 확인해 주세요");
      }
      if (mode === "search") {
        if (Array.isArray(value)) entry.choices = value;
        else {
          check(
            object(value) &&
              Object.keys(value).every((k) => ["bounds", "count"].includes(k)),
            labels[key] + " 범위",
          );
          Object.assign(entry, value);
        }
      } else entry.value = value;
    }
    variables[key] = entry;
  }
  let common;
  try {
    common = JSON.parse($("common").value);
  } catch {
    throw Error("공통 고정 조건 JSON을 확인해 주세요");
  }
  const seed = Number($("seed").value);
  check(
    $("seed").value.trim() !== "" && Number.isSafeInteger(seed),
    "정수 시드",
  );
  return {
    profile: schema.profile,
    variables,
    common,
    sampling: { method: "cartesian_choices", seed },
    baseline,
  };
}
function changed() {
  if (!ready || creating || committing) return;
  generation++;
  dirty = true;
  clearPreview();
  controls();
  message("미확정 변경");
  saveDraft();
}
async function list() {
  const data = await api("/api/studies");
  $("study").replaceChildren(new Option("실험 선택", ""));
  for (const s of data.studies) $("study").add(new Option(s.name, s.id));
  if (!data.studies.some((s) => s.id === study)) study = "";
  $("study").value = study;
  listed = true;
}
async function select(id = study, carried = null) {
  const token = ++generation;
  study = id;
  $("study").value = study;
  ready = false;
  loading = true;
  dirty = false;
  incompatible = false;
  revision = null;
  clearPreview();
  $("revision").textContent = "";
  $("profileNotice").hidden = true;
  rememberSelection();
  controls();
  message("실험을 불러오는 중입니다");
  try {
    const detail = id
      ? await api("/api/studies/" + encodeURIComponent(id))
      : null;
    // 선택이나 편집 이후 도착한 응답은 현재 화면에 적용하지 않는다.
    if (token !== generation) return;
    revision = detail?.current_revision || null;
    const saved = detail?.revisions.find((r) => r.id === revision)?.data;
    incompatible = !!revision && saved?.design?.profile !== schema.profile;
    const design =
      !incompatible && saved?.design
        ? saved.design
        : {
            profile: schema.profile,
            variables: schema.variables,
            common: commonTemplate,
            sampling: schema.sampling,
            baseline: null,
          };
    let raw = incompatible ? null : carried || drafts.get(id),
      draftError = "";
    if (!raw && !incompatible) {
      try {
        const stored = storage("getItem", draftKey(id));
        if (stored) {
          const parsed = JSON.parse(stored);
          raw = parsed.version === 1 ? parsed : designDraft(parsed);
        }
      } catch {
        draftError =
          "보관된 초안을 읽지 못했습니다. 기존 보관 내용은 유지됩니다. ";
      }
    }
    if (raw) {
      try {
        restore(raw);
        dirty = true;
      } catch {
        draftError =
          "보관된 초안을 읽지 못했습니다. 기존 보관 내용은 유지됩니다. ";
        raw = null;
      }
    }
    if (!raw) restore(designDraft(design));
    if (carried && raw) saveDraft();
    ready = true;
    $("profileNotice").hidden = !incompatible;
    $("revision").textContent = revision
      ? "확정 버전 " + revision.slice(0, 8)
      : "확정 버전 없음";
    if (!dirty && !incompatible && Array.isArray(saved?.candidates)) {
      preview = saved;
      renderCandidates();
    }
    message(
      draftError +
        (dirty
          ? "미확정 입력 복원됨"
          : preview
            ? "저장된 후보 · 읽기 전용 · 다시 생성·검사한 뒤 확정할 수 있습니다"
            : ""),
    );
  } catch (e) {
    if (token === generation) message(e);
  } finally {
    if (token === generation) {
      loading = false;
      controls();
    }
  }
}
$("study").onchange = async () => {
  if (!listed || creating || committing) return;
  if (dirty && !confirm("현재 미확정 입력을 보관하고 실험을 바꿀까요?")) {
    $("study").value = study;
    return;
  }
  if (dirty) saveDraft();
  await select($("study").value);
};
$("create").onclick = async () => {
  if (!ready || creating || committing || importing || !$("name").value.trim())
    return;
  const token = ++generation,
    carried = dirty ? capture() : null;
  if (dirty) saveDraft();
  creating = true;
  controls();
  try {
    const name = $("name").value.trim();
    const id = (await api("/api/studies", { name })).result.id;
    if (token !== generation) return;
    $("study").add(new Option(name, id));
    $("name").value = "";
    // 실험을 만들기 전에 작성한 입력은 새 실험으로도 이어서 보관한다.
    if (carried) storage("setItem", draftKey(id), JSON.stringify(carried));
    await select(id, carried);
  } catch (e) {
    if (token === generation) message(e);
  } finally {
    creating = false;
    controls();
  }
};
$("baseline").onclick = () => {
  if (!ready || creating || committing) return;
  try {
    const d = read();
    baseline = Object.fromEntries(
      Object.entries(d.variables)
        .filter(([, v]) => v.mode !== "derived")
        .map(([k, v]) => [
          k,
          v.mode === "search" ? (v.choices?.[0] ?? v.bounds?.[0]) : v.value,
        ]),
    );
    $("baselineData").textContent = JSON.stringify(baseline, null, 2);
    changed();
    message("기준안 지정됨 · 후보 검사 전");
  } catch (e) {
    message(e);
  }
};
$("preview").onclick = async () => {
  if (!ready || creating || committing || previewing || incompatible) return;
  const token = generation,
    id = study;
  try {
    if (!study) throw Error("실험을 선택해 주세요");
    if (!baseline) throw Error("기준안을 먼저 지정해 주세요");
    const design = read();
    previewing = true;
    clearPreview();
    controls();
    message("후보를 생성·검사하는 중입니다");
    const result = (
      await api("/api/studies/" + encodeURIComponent(id) + "/preview", {
        design,
      })
    ).result;
    if (token !== generation) return;
    preview = result;
    previewReadOnly = false;
    renderCandidates();
    message(
      preview.candidates.filter((r) => r.valid).length +
        "개 후보 확정 가능 · 저장고 계산 미연결",
    );
  } catch (e) {
    if (token === generation) message(e);
  } finally {
    previewing = false;
    controls();
  }
};
function renderCandidates() {
  $("candidates").replaceChildren();
  preview.candidates.forEach((row, i) => {
    const tr = document.createElement("tr");
    tr.tabIndex = i === 0 ? 0 : -1;
    tr.setAttribute("aria-selected", "false");
    tr.setAttribute(
      "aria-label",
      (row.baseline ? "기준안" : "후보 " + i) +
        " · " +
        (row.valid ? "유효" : "제외"),
    );
    for (const value of [
      row.baseline ? "기준안" : String(i),
      row.valid ? "유효" : "제외",
      row.violations.map((v) => v.message).join(", "),
    ]) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    const activate = () => {
      for (const r of $("candidates").children) {
        r.setAttribute("aria-selected", String(r === tr));
        r.tabIndex = r === tr ? 0 : -1;
      }
      $("diff").textContent = JSON.stringify(row.changed, null, 2);
      try {
        show(row.input);
      } catch {
        clearScene();
        message("이 후보의 3D 배치를 표시할 수 없습니다");
      }
      $("selected").textContent =
        (row.baseline ? "기준안" : "후보 " + i) +
        " · " +
        row.input_hash.slice(0, 12) +
        (previewReadOnly ? " · 저장된 후보" : "");
    };
    tr.onfocus = activate;
    tr.onclick = () => {
      activate();
      tr.focus();
    };
    tr.onkeydown = (e) => {
      const rows = Array.from($("candidates").children);
      let target;
      if (e.key === "ArrowDown")
        target = rows[Math.min(i + 1, rows.length - 1)];
      else if (e.key === "ArrowUp") target = rows[Math.max(i - 1, 0)];
      else if (e.key === "Home") target = rows[0];
      else if (e.key === "End") target = rows[rows.length - 1];
      else if (e.key === "Enter" || e.key === " ") target = tr;
      if (target) {
        e.preventDefault();
        target.focus();
        if (target === tr) activate();
      }
    };
    $("candidates").append(tr);
  });
  $("candidates").firstChild?.onfocus();
}
$("commit").onclick = async () => {
  if (
    !ready ||
    creating ||
    committing ||
    importing ||
    incompatible ||
    previewReadOnly ||
    !preview?.candidates.some((r) => r.valid)
  )
    return;
  const token = ++generation,
    id = study,
    candidatePreview = preview;
  committing = true;
  controls();
  try {
    const r = (
      await api("/api/studies/" + encodeURIComponent(id) + "/commit", {
        design: candidatePreview.design,
        preview_hash: candidatePreview.preview_hash,
        expected_revision: revision,
      })
    ).result;
    if (token !== generation) return;
    revision = r.revision;
    dirty = false;
    drafts.delete(id);
    storage("removeItem", draftKey(id));
    previewReadOnly = true;
    renderCandidates();
    $("revision").textContent = "확정 버전 " + revision.slice(0, 8);
    message("입력·후보·검사·소스 버전 저장 완료");
  } catch (e) {
    if (token === generation) message(e);
  } finally {
    committing = false;
    controls();
  }
};
$("download").onclick = () => {
  if (!ready || creating || committing) return;
  try {
    const url = URL.createObjectURL(
        new Blob([JSON.stringify(read(), null, 2)], {
          type: "application/json",
        }),
      ),
      a = document.createElement("a");
    a.href = url;
    a.download = "research-design.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    message(e);
  }
};
$("import").onchange = async () => {
  if (!ready || creating || committing || importing) return;
  const token = generation;
  importing = true;
  controls();
  try {
    const file = $("import").files[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024)
      throw Error("설계 파일은 2 MiB 이하여야 합니다");
    const d = JSON.parse(await file.text());
    if (token !== generation) return;
    const raw = designDraft(d);
    if (dirty && !confirm("현재 미확정 입력을 가져온 설계로 덮어쓸까요?"))
      return;
    restore(raw);
    changed();
  } catch (e) {
    if (token === generation) message(e);
  } finally {
    importing = false;
    $("import").value = "";
    controls();
  }
};
$("name").oninput = controls;
$("common").oninput = changed;
$("seed").oninput = changed;
window.addEventListener("beforeunload", (e) => {
  if (dirty || committing || creating) {
    e.preventDefault();
    e.returnValue = "";
  }
});

// 후보 기하만 그린다. 농도 결과나 물리 해석처럼 보이게 보간하지 않는다.
const host = $("scene"),
  scene = new THREE.Scene();
scene.background = new THREE.Color("#e7edf0");
const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 10000);
camera.up.set(0, 0, 1);
let renderer,
  group = new THREE.Group(),
  radius = 10,
  yaw = -1,
  pitch = 0.65;
scene.add(group, new THREE.HemisphereLight(0xffffff, 0x777777, 2));
try {
  renderer = new THREE.WebGLRenderer({
    antialias: true,
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  host.append(renderer.domElement);
} catch {
  $("sceneEmpty").textContent =
    "3D 그래픽을 사용할 수 없습니다. 후보 검사와 저장은 가능합니다";
}
function render() {
  if (!renderer) return;
  const w = host.clientWidth,
    h = host.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  const distance =
    (radius /
      Math.sin(
        Math.min(
          (camera.fov * Math.PI) / 360,
          Math.atan(Math.tan((camera.fov * Math.PI) / 360) * camera.aspect),
        ),
      )) *
    1.15;
  camera.position.set(
    distance * Math.cos(yaw) * Math.cos(pitch),
    distance * Math.sin(yaw) * Math.cos(pitch),
    distance * Math.sin(pitch),
  );
  camera.lookAt(0, 0, 0);
  renderer.render(scene, camera);
}
new ResizeObserver(render).observe(host);
let dragging = null;
host.onpointerdown = (e) => {
  if (e.button !== 0) return;
  dragging = [e.clientX, e.clientY];
  host.setPointerCapture(e.pointerId);
};
host.onpointerup = () => (dragging = null);
host.onpointercancel = () => (dragging = null);
host.onpointermove = (e) => {
  if (!dragging) return;
  yaw -= (e.clientX - dragging[0]) * 0.008;
  pitch = Math.max(
    0.05,
    Math.min(1.5, pitch + (e.clientY - dragging[1]) * 0.008),
  );
  dragging = [e.clientX, e.clientY];
  render();
};
host.oncontextmenu = (e) => e.preventDefault();
function clearScene() {
  while (group.children.length) {
    const child = group.children[0];
    child.geometry?.dispose();
    child.material?.dispose();
    group.remove(child);
  }
  group.position.set(0, 0, 0);
  dragging = null;
  $("sceneEmpty").hidden = false;
  render();
}
function show(spec) {
  clearScene();
  const g = spec.common.geometry,
    L = g.length_m,
    W = g.width_m,
    H = g.eaves_m;
  radius = Math.hypot(L, W, H) / 2;
  group.position.set(-L / 2, -W / 2, -H / 2);
  function cube(lo, hi, color, wire = false) {
    const geo = new THREE.BoxGeometry(...hi.map((v, i) => v - lo[i]));
    let obj;
    if (wire) {
      const edges = new THREE.EdgesGeometry(geo);
      geo.dispose();
      obj = new THREE.LineSegments(
        edges,
        new THREE.LineBasicMaterial({ color }),
      );
    } else
      obj = new THREE.Mesh(
        geo,
        new THREE.MeshStandardMaterial({
          color,
          transparent: true,
          opacity: 0.65,
          depthWrite: false,
        }),
      );
    obj.position.set(...hi.map((v, i) => (v + lo[i]) / 2));
    group.add(obj);
  }
  cube([0, 0, 0], [L, W, H], "#65737c", true);
  for (const a of spec.common.aisles) cube(a.min, a.max, "#278eac");
  for (const b of spec.variables.layout.blocks) cube(b.min, b.max, "#57a47b");
  // 제외 후보에 공급 위치가 없더라도 나머지 형상과 제외 사유는 계속 확인한다.
  const sources = Array.isArray(spec.variables.supply_positions) ? spec.variables.supply_positions : [];
  for (const p of sources) {
    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(Math.max(L, W) * 0.009, 16, 12),
      new THREE.MeshBasicMaterial({ color: "#b02067" }),
    );
    marker.position.set(...p);
    group.add(marker);
  }
  $("sceneEmpty").hidden = !!renderer;
  render();
}

(async () => {
  try {
    schema = await api("/api/studies/schema");
    for (const group of Object.values(schema.groups)) {
      const section = document.createElement("section"),
        heading = document.createElement("h2");
      heading.textContent = group.label;
      section.append(heading);
      const scroll = document.createElement("div");
      scroll.className = "scroll";
      const table = document.createElement("table");
      table.innerHTML =
        "<thead><tr><th>항목</th><th>적용</th><th>값 / 후보 목록 / 범위 JSON</th><th>단위</th><th>출처·가정</th></tr></thead>";
      const body = document.createElement("tbody");
      for (const key of group.keys) {
        const tr = document.createElement("tr"),
          name = document.createElement("td");
        name.textContent = labels[key];
        tr.append(name);
        const f = {};
        for (const kind of ["mode", "value", "unit", "evidence"]) {
          const td = document.createElement("td"),
            el = document.createElement(
              kind === "mode"
                ? "select"
                : kind === "value"
                  ? "textarea"
                  : "input",
            );
          el.setAttribute("aria-label", labels[key] + " " + kind);
          el.disabled = true;
          if (kind === "mode") {
            for (const [v, label] of [
              ["fixed", "고정"],
              ["search", "탐색"],
              ["derived", "자동 계산"],
            ]) {
              const option = new Option(label, v);
              option.disabled =
                (schema.locked_in_initial_comparison.includes(key) &&
                  v !== "fixed") ||
                (v === "derived" && key !== "spacing_m");
              el.add(option);
            }
          } else if (kind === "value") el.rows = 3;
          f[kind] = el;
          el.oninput = () => {
            changed();
          };
          td.append(el);
          tr.append(td);
        }
        fields[key] = f;
        body.append(tr);
      }
      table.append(body);
      scroll.append(table);
      section.append(scroll);
      $("groups").append(section);
    }
    controls();
    const requested = new URL(window.location.href).searchParams.get("study");
    let saved = storage("getItem", "cfd-selected-study");
    try {
      saved = JSON.parse(saved);
    } catch {
      // 이전 실행 화면이 보관한 따옴표 없는 Study ID도 읽는다.
    }
    study = requested ?? (typeof saved === "string" ? saved : "");
    await list();
    await select();
  } catch (e) {
    message(e);
  }
})();
