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
  dirty = false;
const fields = {};
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
      const value = JSON.parse(f.value.value || "null");
      if (mode === "search") {
        if (Array.isArray(value)) entry.choices = value;
        else Object.assign(entry, value);
      } else entry.value = value;
    }
    variables[key] = entry;
  }
  return {
    profile: schema.profile,
    variables,
    common: JSON.parse($("common").value),
    sampling: { method: "cartesian_choices", seed: Number($("seed").value) },
    baseline,
  };
}
function changed() {
  dirty = true;
  preview = null;
  $("commit").disabled = true;
  message("미확정 변경");
  try {
    localStorage.setItem("cfd-research-draft-" + study, JSON.stringify(read()));
  } catch {
    /* 작성 중인 불완전한 JSON은 확정 입력으로 저장하지 않는다. */
  }
}
function populate(d) {
  for (const [key, f] of Object.entries(fields)) {
    const v = d.variables[key];
    f.mode.value = v.mode;
    f.value.value = JSON.stringify(
      v.mode === "search"
        ? (v.choices ?? { bounds: v.bounds, count: v.count })
        : (v.value ?? null),
      null,
      2,
    );
    f.unit.value = v.unit || "";
    f.evidence.value =
      typeof v.evidence === "string"
        ? v.evidence
        : JSON.stringify(v.evidence ?? "");
    f.value.disabled = v.mode === "derived";
  }
  $("common").value = JSON.stringify(d.common, null, 2);
  $("seed").value = d.sampling.seed;
  baseline = d.baseline;
  $("baselineData").textContent = baseline
    ? JSON.stringify(baseline, null, 2)
    : "미지정";
  preview = null;
  $("commit").disabled = true;
}
async function list() {
  const data = await api("/api/studies");
  $("study").replaceChildren(new Option("실험 선택", ""));
  for (const s of data.studies) $("study").add(new Option(s.name, s.id));
  $("study").value = study;
}
async function select() {
  revision = null;
  let design = null;
  if (study) {
    const d = await api("/api/studies/" + study);
    revision = d.current_revision;
    design = d.revisions.find((r) => r.id === revision)?.data.design;
  }
  const draft = localStorage.getItem("cfd-research-draft-" + study);
  populate(
    draft
      ? JSON.parse(draft)
      : design?.profile === schema.profile
        ? design
        : { ...schema, common: commonTemplate, baseline: null },
  );
  dirty = !!draft;
  $("revision").textContent = revision
    ? "확정 버전 " + revision.slice(0, 8)
    : "확정 버전 없음";
  message(dirty ? "미확정 입력 복원됨" : "");
  $("candidates").replaceChildren();
  $("diff").textContent = "";
}
$("study").onchange = async () => {
  if (dirty && !confirm("현재 미확정 입력을 보관하고 실험을 바꿀까요?")) {
    $("study").value = study;
    return;
  }
  study = $("study").value;
  try {
    await select();
  } catch (e) {
    message(e);
  }
};
$("create").onclick = async () => {
  try {
    if (dirty) changed();
    study = (await api("/api/studies", { name: $("name").value })).result.id;
    await list();
    await select();
  } catch (e) {
    message(e);
  }
};
$("baseline").onclick = () => {
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
  try {
    if (!study) throw Error("실험을 선택해 주세요");
    if (!baseline) throw Error("기준안을 먼저 지정해 주세요");
    preview = (
      await api("/api/studies/" + study + "/preview", { design: read() })
    ).result;
    $("candidates").replaceChildren();
    preview.candidates.forEach((row, i) => {
      const tr = document.createElement("tr");
      for (const value of [
        row.baseline ? "기준안" : String(i),
        row.valid ? "유효" : "제외",
        row.violations.map((v) => v.message).join(", "),
      ]) {
        const td = document.createElement("td");
        td.textContent = value;
        tr.append(td);
      }
      tr.onclick = () => {
        for (const r of $("candidates").children)
          r.setAttribute("aria-selected", String(r === tr));
        $("diff").textContent = JSON.stringify(row.changed, null, 2);
        show(row.input);
        $("selected").textContent =
          (row.baseline ? "기준안" : "후보 " + i) +
          " · " +
          row.input_hash.slice(0, 12);
      };
      $("candidates").append(tr);
    });
    $("candidates").firstChild?.click();
    $("commit").disabled = !preview.candidates.some((r) => r.valid);
    message(
      preview.candidates.filter((r) => r.valid).length +
        "개 후보 확정 가능 · 저장고 계산 미연결",
    );
  } catch (e) {
    message(e);
  }
};
$("commit").onclick = async () => {
  try {
    const r = (
      await api("/api/studies/" + study + "/commit", {
        design: preview.design,
        preview_hash: preview.preview_hash,
        expected_revision: revision,
      })
    ).result;
    revision = r.revision;
    dirty = false;
    localStorage.removeItem("cfd-research-draft-" + study);
    $("commit").disabled = true;
    $("revision").textContent = "확정 버전 " + revision.slice(0, 8);
    message("입력·후보·검사·소스 버전 저장 완료");
  } catch (e) {
    message(e);
  }
};
$("download").onclick = () => {
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
  try {
    const file = $("import").files[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024)
      throw Error("설계 파일은 2 MiB 이하여야 합니다");
    const d = JSON.parse(await file.text());
    if (d.profile !== schema.profile || !d.variables || !d.common)
      throw Error("연구 설계 형식을 확인해 주세요");
    populate(d);
    changed();
  } catch (e) {
    message(e);
  }
};
$("common").oninput = changed;
$("seed").oninput = changed;
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
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
  message("3D 그래픽을 사용할 수 없습니다. 후보 검사와 저장은 가능합니다");
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
function show(spec) {
  while (group.children.length) {
    const child = group.children[0];
    child.geometry?.dispose();
    child.material?.dispose();
    group.remove(child);
  }
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
  for (const p of spec.variables.supply_positions) {
    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(Math.max(L, W) * 0.009, 16, 12),
      new THREE.MeshBasicMaterial({ color: "#b02067" }),
    );
    marker.position.set(...p);
    group.add(marker);
  }
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
            f.value.disabled = f.mode.value === "derived";
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
    await list();
    await select();
  } catch (e) {
    message(e);
  }
})();
