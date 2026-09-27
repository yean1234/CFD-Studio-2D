const $ = (id) => document.getElementById(id);
const fieldIds = [
  "variable",
  "method",
  "values",
  "low",
  "high",
  "count",
  "seed",
];
const defaults = {
  variable: "K_porous_m2_s",
  method: "manual",
  values: "0.001,0.002,0.004",
  low: "0.001",
  high: "0.004",
  count: "3",
  seed: "42",
};
const states = {
  queued: "대기",
  running: "계산 중",
  finished: "계산 종료",
  failed: "실행 오류",
  cancelled: "취소",
  recovery_required: "복구 확인 필요",
};
const qualities = { unchecked: "미검사", pass: "통과", fail: "미통과" };
let study = "",
  detail = null,
  preview = null,
  dirty = false,
  generation = 0,
  editVersion = 0;
let baseRevision = null,
  action = null,
  polling = false,
  lastRows = "",
  comparison = null,
  pendingRequest = null;
let recoveryTarget = null;
const attemptRequests = new Map();

function message(value) {
  $("msg").textContent = value?.message || value || "";
}
function storage(key, value) {
  try {
    if (value === undefined) {
      const raw = localStorage.getItem(key);
      if (key === "cfd-selected-study" && /^[a-f0-9]{32}$/.test(raw || ""))
        return raw;
      return JSON.parse(raw || "null");
    }
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    message(
      "브라우저 임시 저장을 사용할 수 없습니다. 확정 전에는 창을 닫지 마세요.",
    );
  }
  return null;
}
async function api(path, data) {
  const response = await fetch(
    path,
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  const result = await response.json();
  if (!response.ok || result.ok === false)
    throw Error(result.msg || result.err || "서버 요청 실패");
  return result;
}
const draftKey = () => "cfd-study-draft-" + study;
const rawForm = () =>
  Object.fromEntries(fieldIds.map((key) => [key, $(key).value]));
const ticket = () => ({ generation, editVersion, study });
const current = (t, edits = false) =>
  t.generation === generation &&
  t.study === study &&
  (!edits || t.editVersion === editVersion);
const activeRevision = () =>
  detail?.revisions.find((r) => r.id === detail.current_revision);
const warehouse = () =>
  activeRevision()?.data.design.profile === "warehouse_joint_v1";
const activeAttempts = () =>
  detail?.attempts.filter((a) =>
    ["queued", "running", "recovery_required"].includes(a.state),
  ) || [];

function syncActions() {
  const ready = !!detail && !warehouse(),
    busy = !!action;
  $("studies").disabled = busy;
  $("name").disabled = busy;
  for (const key of fieldIds) $(key).disabled = !ready || busy;
  $("preview").disabled = !ready || busy;
  $("commit").disabled =
    !ready || busy || !preview || detail.current_revision !== baseRevision;
  const cases =
    detail?.cases.filter((c) => c.revision_id === detail.current_revision) ||
    [];
  $("enqueue").disabled =
    !ready ||
    busy ||
    dirty ||
    !!preview ||
    !cases.length ||
    !!detail.recovery_blocker ||
    activeAttempts().length > 0;
  $("enqueue").textContent = detail?.attempts.some((a) =>
    cases.some((c) => c.id === a.case_id),
  )
    ? "확정 후보 다시 실행"
    : "확정 후보 실행 예약";
  $("export").disabled = busy || !comparison?.rows.length;
  $("pause").disabled = !detail || busy || detail.paused;
  $("resume").disabled =
    !detail || busy || !detail.paused || !!detail.recovery_blocker;
  $("create").disabled = busy || !$("name").value.trim();
  for (const button of document.querySelectorAll("[data-attempt-action]"))
    button.disabled = busy;
  $("revert").disabled = !detail || busy || (!dirty && !preview);
  $("range").hidden = $("method").value === "manual";
  $("valuesLabel").hidden = $("method").value !== "manual";
  document.querySelector('a[href^="/studies/design"]').href =
    "/studies/design" + (study ? "?study=" + study : "");
}
function populate(form) {
  for (const key of fieldIds) $(key).value = form[key] ?? defaults[key];
  syncActions();
}
function formFromDesign(d) {
  return {
    ...defaults,
    variable: d.variable,
    method: d.method,
    values: d.values?.join(",") ?? "",
    low: d.low ?? defaults.low,
    high: d.high ?? defaults.high,
    count: d.count ?? defaults.count,
    seed: d.seed ?? 42,
  };
}
function drawCandidates(rows = []) {
  $("candidates").replaceChildren();
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const value of [
      row.baseline ? "기준안" : "후보",
      row.value ?? "-",
      row.valid ? "유효" : row.violations.map((v) => v.message || v).join(", "),
    ]) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    $("candidates").append(tr);
  }
}
function changed() {
  editVersion++;
  dirty = true;
  preview = null;
  pendingRequest = null;
  storage(draftKey(), { form: rawForm(), baseRevision });
  drawCandidates();
  $("download").hidden = true;
  $("dirty").textContent = "미확정 변경 · 후보 확인이 필요합니다";
  syncActions();
}
for (const key of fieldIds) $(key).oninput = changed;
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});

function loadRevision() {
  baseRevision = detail.current_revision;
  editVersion++;
  preview = null;
  const rev = activeRevision(),
    draft = storage(draftKey());
  dirty = !!draft;
  if (warehouse()) {
    dirty = false;
    populate(defaults);
    drawCandidates();
    message(
      "저장고 형상 후보입니다. 연구 변수·3D 후보 화면에서 확인해 주세요. 실제 저장고 계산은 미연결입니다.",
    );
  } else {
    populate(draft?.form || (rev ? formFromDesign(rev.data.design) : defaults));
    if (draft) baseRevision = draft.baseRevision;
    drawCandidates(draft ? [] : rev?.data.candidates);
  }
  $("revision").textContent = detail.current_revision
    ? "확정 버전 " + detail.current_revision.slice(0, 8)
    : "확정 버전 없음";
  $("dirty").textContent = dirty ? "미확정 입력 복원됨" : "";
}
function clearSelection() {
  $("recoveryDialog").close();
  recoveryTarget = null;
  detail = null;
  preview = null;
  comparison = null;
  dirty = false;
  baseRevision = null;
  pendingRequest = null;
  lastRows = "";
  action = null;
  drawCandidates();
  $("attempts").replaceChildren();
  $("log").textContent = "";
  $("legend").replaceChildren();
  $("comparisonEmpty").hidden = false;
  $("chart")
    .getContext("2d")
    .clearRect(0, 0, $("chart").width, $("chart").height);
  $("revision").textContent = "확정 버전 없음";
  $("dirty").textContent = "";
  $("queueState").textContent = "";
  $("queueBlocker").replaceChildren();
  $("download").hidden = true;
  $("download").removeAttribute("href");
  $("packageStatus").textContent = "";
  message("");
  syncActions();
}
async function list() {
  const data = await api("/api/studies");
  $("studies").replaceChildren(new Option("실험 선택", ""));
  for (const item of data.studies)
    $("studies").add(
      new Option(item.name + " · " + item.id.slice(0, 6), item.id),
    );
  $("studies").value = study;
}
async function choose(id) {
  generation++;
  study = id;
  clearSelection();
  $("studies").value = study;
  storage("cfd-selected-study", study);
  history.replaceState(null, "", "/studies" + (study ? "?study=" + study : ""));
  if (!study) return;
  const t = ticket();
  try {
    const d = await api("/api/studies/" + study);
    if (!current(t)) return;
    detail = d;
    loadRevision();
    renderAttempts();
    syncActions();
    const comp = await api("/api/studies/" + study + "/comparison");
    if (!current(t)) return;
    comparison = comp;
    chart();
    $("connection").textContent = "연결됨";
    syncActions();
  } catch (e) {
    if (current(t)) {
      message(e);
      $("connection").textContent = "연결 오류";
    }
  }
}
$("studies").onchange = async () => {
  if (dirty && !confirm("미확정 입력을 보관하고 다른 실험으로 이동할까요?")) {
    $("studies").value = study;
    return;
  }
  await choose($("studies").value);
};
$("name").oninput = syncActions;
$("revert").onclick = async () => {
  if (dirty && !confirm("미확정 입력을 버리고 마지막 확정 설정을 불러올까요?"))
    return;
  storage(draftKey(), null);
  await choose(study);
};
$("create").onclick = async () => {
  if (action) return;
  const t = ticket();
  action = "create";
  syncActions();
  try {
    const r = await api("/api/studies", { name: $("name").value });
    if (!current(t)) return;
    await list();
    if (current(t)) await choose(r.result.id);
  } catch (e) {
    if (current(t)) message(e);
  } finally {
    if (current(t)) {
      action = null;
      syncActions();
    }
  }
};
function design() {
  const value = rawForm();
  const numeric = (key) => {
    if (!value[key].trim() || !Number.isFinite(Number(value[key])))
      throw Error("유한한 숫자를 입력해 주세요");
    return Number(value[key]);
  };
  return value.method === "manual"
    ? {
        variable: value.variable,
        method: value.method,
        values: value.values.split(",").map((x) => {
          if (!x.trim() || !Number.isFinite(Number(x)))
            throw Error("후보값을 확인해 주세요");
          return Number(x);
        }),
        seed: numeric("seed"),
      }
    : {
        variable: value.variable,
        method: value.method,
        low: numeric("low"),
        high: numeric("high"),
        count: numeric("count"),
        seed: numeric("seed"),
      };
}
$("preview").onclick = async () => {
  if (action || !detail) return;
  const t = ticket();
  action = "preview";
  syncActions();
  try {
    const r = await api("/api/studies/" + t.study + "/preview", {
      design: design(),
    });
    if (!current(t, true)) return;
    preview = r.result;
    drawCandidates(preview.candidates);
    message(
      preview.candidates.filter((x) => x.valid).length + "개 후보 확정 가능",
    );
  } catch (e) {
    if (current(t, true)) message(e);
  } finally {
    if (current(t)) {
      action = null;
      syncActions();
    }
  }
};
$("commit").onclick = async () => {
  if (action || !preview) return;
  const t = ticket(),
    submitted = preview;
  action = "commit";
  syncActions();
  try {
    const r = await api("/api/studies/" + t.study + "/commit", {
      design: submitted.design,
      preview_hash: submitted.preview_hash,
      expected_revision: baseRevision,
    });
    if (!current(t, true)) return;
    storage(draftKey(), null);
    dirty = false;
    preview = null;
    editVersion++;
    message("실행용 입력 확정됨");
    await choose(t.study);
  } catch (e) {
    if (current(t)) message(e);
  } finally {
    if (current(t)) {
      action = null;
      syncActions();
    }
  }
};
$("enqueue").onclick = async () => {
  if (action || !detail || dirty) return;
  const t = ticket();
  action = "enqueue";
  syncActions();
  pendingRequest ??= crypto.randomUUID();
  try {
    await api("/api/studies/" + t.study + "/enqueue", {
      cases: detail.cases
        .filter((c) => c.revision_id === detail.current_revision)
        .map((c) => c.id),
      request_id: pendingRequest,
    });
    if (!current(t)) return;
    pendingRequest = null;
    message("순차 실행을 예약했습니다");
    await refresh();
  } catch (e) {
    if (current(t)) message(e);
  } finally {
    if (current(t)) {
      action = null;
      syncActions();
    }
  }
};
for (const [id, paused] of [
  ["pause", true],
  ["resume", false],
])
  $(id).onclick = async () => {
    if (action) return;
    const t = ticket();
    action = id;
    syncActions();
    try {
      await api("/api/study-queue", { paused });
      if (current(t)) await refresh();
    } catch (e) {
      if (current(t)) message(e);
    } finally {
      if (current(t)) {
        action = null;
        syncActions();
      }
    }
  };
function renderAttempts() {
  $("queueState").textContent = detail.paused ? "대기열 보류" : "순차 실행";
  $("queueBlocker").replaceChildren();
  if (detail.recovery_blocker) {
    const blocker = detail.recovery_blocker,
      link = document.createElement("a");
    link.href = "/studies?study=" + blocker.study_id;
    link.textContent =
      blocker.study_name + " · " + blocker.attempt_id.slice(0, 8);
    $("queueBlocker").append(
      document.createTextNode("중단 상태 확인 필요: "),
      link,
    );
  }
  const serialized = JSON.stringify(detail.attempts);
  if (serialized === lastRows) return;
  lastRows = serialized;
  $("attempts").replaceChildren();
  for (const a of detail.attempts) {
    const tr = document.createElement("tr");
    for (const val of [
      a.id.slice(0, 8),
      states[a.state] || a.state,
      qualities[a.quality] || a.quality,
      a.result?.metrics?.physical_end_s != null
        ? a.result.metrics.physical_end_s + " s"
        : "-",
      a.result?.metrics?.wall_s != null
        ? a.result.metrics.wall_s.toFixed(2) + " s"
        : "-",
    ]) {
      const td = document.createElement("td");
      td.textContent = val;
      tr.append(td);
    }
    const td = document.createElement("td"),
      log = document.createElement("button");
    log.textContent = "로그";
    log.onclick = async () => {
      const t = ticket();
      try {
        const r = await api("/api/attempts/" + a.id + "/log");
        if (!current(t)) return;
        $("log").textContent = r.log;
        document.querySelector("details").open = true;
      } catch (e) {
        if (current(t)) message(e);
      }
    };
    td.append(log);
    const addAction = (kind, label) => {
      const button = document.createElement("button");
      button.textContent = label;
      button.dataset.attemptAction = kind;
      button.dataset.attemptId = a.id;
      button.onclick = () => attemptAction(a, kind);
      td.append(button);
    };
    if (a.state === "queued") addAction("cancel", "예약 취소");
    if (["failed", "cancelled"].includes(a.state))
      addAction("retry", "처음부터 재시도");
    if (a.state === "failed") addAction("resume", "저장 시점부터 재개");
    if (a.recovery_available) addAction("resolve_recovery", "중단 상태 확인");
    if (a.result?.project_id) {
      const link = document.createElement("a");
      link.textContent = " 3D 보기";
      link.href = "/?study_project=" + encodeURIComponent(a.result.project_id);
      td.append(link);
    }
    if (a.result?.error)
      td.append(document.createTextNode(" " + a.result.error));
    else if (a.quality === "fail")
      td.append(
        document.createTextNode(" 수치 검사 미통과 · 로그를 확인하세요"),
      );
    tr.append(td);
    $("attempts").append(tr);
  }
}
async function attemptAction(attempt, kind, extra = {}) {
  if (action) return;
  if (kind === "resolve_recovery" && !extra.confirmed_stopped) {
    recoveryTarget = { attempt, token: ticket() };
    $("recoveryForm").reset();
    $("recoveryError").textContent = "";
    $("recoveryDialog").showModal();
    return;
  }
  if (
    kind === "retry" &&
    !confirm("기존 실행 기록을 보존하고 이 후보를 0초부터 다시 실행할까요?")
  )
    return;
  const t = ticket(),
    key = study + ":" + attempt.id + ":" + kind;
  if (!attemptRequests.has(key)) attemptRequests.set(key, crypto.randomUUID());
  action = kind;
  syncActions();
  $("recoverySubmit").disabled = true;
  try {
    await api("/api/studies/" + t.study + "/attempts/" + attempt.id, {
      action: kind,
      request_id: attemptRequests.get(key),
      ...extra,
    });
    attemptRequests.delete(key);
    if (!current(t)) return;
    if (kind === "resolve_recovery") $("recoveryDialog").close();
    message(
      kind === "resolve_recovery"
        ? "중단 기록을 보존했습니다. 재시도·재개를 선택한 뒤 대기열을 계속할 수 있습니다."
        : "실행 요청을 반영했습니다.",
    );
    await refresh();
  } catch (e) {
    if (current(t)) {
      message(e);
      $("recoveryError").textContent = e.message;
    }
  } finally {
    if (current(t)) {
      action = null;
      syncActions();
      $("recoverySubmit").disabled = false;
    }
  }
}
$("recoveryCancel").onclick = () => $("recoveryDialog").close();
$("recoveryForm").onsubmit = async (e) => {
  e.preventDefault();
  if (!recoveryTarget || !current(recoveryTarget.token)) return;
  const note = $("recoveryNote").value.trim();
  if (!note) {
    $("recoveryError").textContent = "확인 내용을 입력해 주세요";
    return;
  }
  await attemptAction(recoveryTarget.attempt, "resolve_recovery", {
    confirmed_stopped: $("stoppedConfirmed").checked,
    operator_note: note,
  });
};
function chart() {
  const canvas = $("chart"),
    ctx = canvas.getContext("2d"),
    width = canvas.clientWidth || 600,
    height = 260,
    dpr = Math.min(devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * dpr);
  canvas.height = height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  $("legend").replaceChildren();
  const rows = comparison?.rows || [];
  $("comparisonEmpty").hidden = rows.length > 0;
  if (!rows.length) return;
  const colors = ["#167b70", "#c55d29", "#765caa", "#277eae"],
    end = Math.max(...rows.map((x) => x.metrics.physical_end_s), 1e-12),
    max = Math.max(...rows.flatMap((x) => x.metrics.mean_C), 1e-12) * 1.05;
  ctx.strokeStyle = "#65727a";
  ctx.beginPath();
  ctx.moveTo(52, 24);
  ctx.lineTo(52, 218);
  ctx.lineTo(width - 12, 218);
  ctx.stroke();
  ctx.fillStyle = "#334";
  ctx.font = "13px sans-serif";
  ctx.fillText("C/C_ref", 4, 15);
  ctx.fillText("0", 30, 238);
  ctx.fillText(end + " s", width - 65, 245);
  ctx.fillText(max.toFixed(3), 2, 34);
  rows.forEach((row, index) => {
    ctx.strokeStyle = colors[index % colors.length];
    ctx.beginPath();
    row.metrics.times.forEach((t, i) => {
      const x = 52 + (t / end) * (width - 70),
        y = 218 - (row.metrics.mean_C[i] / max) * 184;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
    const label = document.createElement("span");
    label.className = "legendItem";
    label.style.color = colors[index % colors.length];
    label.textContent =
      (row.changed_variable?.label || "후보") +
      " " +
      row.value +
      " · " +
      row.attempt.slice(0, 8) +
      (row.baseline ? " 기준안" : "");
    $("legend").append(label);
  });
}
new ResizeObserver(chart).observe($("chart"));
async function refresh() {
  if (!study || !detail) return;
  const t = ticket();
  try {
    const d = await api("/api/studies/" + t.study);
    if (!current(t)) return;
    detail = d;
    if (
      detail.current_revision !== baseRevision &&
      !dirty &&
      !preview &&
      !action
    )
      loadRevision();
    else if (detail.current_revision !== baseRevision)
      message(
        "다른 창에서 버전이 변경되었습니다. 미확정 입력은 보존되어 있습니다. 다시 선택해 비교해 주세요.",
      );
    renderAttempts();
    syncActions();
    const comp = await api("/api/studies/" + t.study + "/comparison");
    if (!current(t)) return;
    if (JSON.stringify(comp) !== JSON.stringify(comparison)) {
      comparison = comp;
      chart();
    }
    $("connection").textContent = "연결됨";
    syncActions();
  } catch (e) {
    if (current(t)) {
      $("connection").textContent = "연결 오류";
      message(e);
    }
  }
}
$("export").onclick = async () => {
  if (action || !detail) return;
  const t = ticket();
  action = "export";
  syncActions();
  try {
    const r = (await api("/api/studies/" + t.study + "/export", {})).result;
    if (!current(t)) return;
    $("download").href = "/api/study-packages/" + r.filename;
    $("download").download = r.filename;
    $("download").hidden = false;
    $("packageStatus").textContent =
      "대표 사례 패키지 · " + (r.bytes / 1024 / 1024).toFixed(2) + " MiB";
  } catch (e) {
    if (current(t)) message(e);
  } finally {
    if (current(t)) {
      action = null;
      syncActions();
    }
  }
};
$("import").onchange = () => {
  const f = $("import").files[0];
  if (!f) return;
  const t = ticket();
  if (f.size > 20 * 1024 * 1024) {
    message("20 MiB 이하 ZIP을 선택해 주세요");
    $("import").value = "";
    return;
  }
  const reader = new FileReader();
  reader.onload = async () => {
    try {
      const r = (
        await api("/api/study-packages/import", {
          base64: String(reader.result).split(",")[1],
        })
      ).result;
      if (current(t))
        $("packageStatus").textContent =
          r.files + "개 파일 검사·가져오기 완료 · 코드 실행 없음 · " + r.id;
    } catch (e) {
      if (current(t)) message(e);
    } finally {
      $("import").value = "";
    }
  };
  reader.onerror = () => message("파일을 읽을 수 없습니다");
  reader.readAsDataURL(f);
};
(async () => {
  syncActions();
  try {
    const caps = await api("/api/capabilities");
    for (const [key, v] of Object.entries(caps.variables))
      $("variable").add(new Option(v.label + " (" + v.unit + ")", key));
    populate(defaults);
    await list();
    const id =
      new URLSearchParams(location.search).get("study") ||
      storage("cfd-selected-study");
    if ([...$("studies").options].some((o) => o.value === id)) await choose(id);
    $("connection").textContent = "연결됨";
  } catch (e) {
    message(e);
    $("connection").textContent = "설정 로딩 실패";
  }
})();
setInterval(async () => {
  if (polling) return;
  polling = true;
  try {
    await refresh();
  } finally {
    polling = false;
  }
}, 2000);
