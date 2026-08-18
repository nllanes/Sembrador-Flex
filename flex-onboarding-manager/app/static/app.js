/* Flex Onboarding Manager — UI handoff + API FastAPI */
const API = "/api";

const $ = (s) => document.querySelector(s);
const chk =
  '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
const dots =
  '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></svg>';
const caretSvg =
  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>';

const STATUS_LABELS = {
  not_started: "Sin iniciar",
  invited: "Invitado",
  registration_started: "Cuenta creada",
  documents_pending: "Documentos",
  documents_submitted: "Documentos enviados",
  background_check: "Background check",
  waitlisted: "Lista de espera",
  approved_active: "Listo para handoff",
  rejected: "Rechazado",
  inactive: "Inactivo",
};

const AVATAR_COLORS = ["#F59E0B", "#60A5FA", "#A78BFA", "#34D399", "#F87171", "#22D3EE"];

/** Checklist visual del handoff (8 pasos · etiqueta + hint). */
const ONBOARDING_CHECKLIST = [
  ["Crear cuenta Amazon Flex", "Email verificado · 2FA activo"],
  ["Subir licencia de conducir", "Vigente ≥ 6 meses"],
  ["Registro de vehículo + seguro", "Póliza a nombre del candidato"],
  ["Consentimiento background check", "Firmado digitalmente"],
  ["Background check aprobado", "Checkr · 3–5 días hábiles"],
  ["Cuenta bancaria (payout)", "Routing + account verificados"],
  ["Instalar app y login de prueba", "Confirmar bloques visibles"],
  ["Handoff al candidato", "Entrega de credenciales"],
];

const DISPATCH_ELIGIBLE = new Set(["not_started", "invited"]);

let STATIONS = [];
let SIEMBRAS = [];
let filtered = [];
let sel = {};
let groupBy = "state";
let map = null;
let markers = {};
let expOpen = {};
let expSel = {};
let selectedExpId = null;
let codeToState = {};
let siembraByCode = {};
let statusesMeta = [];

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body.detail || msg;
    } catch (_) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  if (res.status === 204) return null;
  return res.json();
}

function toast(msg, type = "success") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  setTimeout(() => el.classList.add("hidden"), 3200);
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function initials(n) {
  return n
    .split(" ")
    .map((x) => x[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function avatarColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h + name.charCodeAt(i) * 17) % AVATAR_COLORS.length;
  return AVATAR_COLORS[h];
}

function relTime(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return "hace minutos";
  if (h < 24) return `hace ${h} h`;
  const d = Math.floor(h / 24);
  return d === 1 ? "ayer" : `hace ${d} d`;
}

function parseCity(city) {
  if (!city) return "";
  return city.split(",")[0].trim();
}

function parseState(city, st) {
  if (st) return st;
  const m = String(city || "").match(/,\s*([A-Z]{2})\s*$/);
  return m ? m[1] : "—";
}

function siembraCount(code) {
  return siembraByCode[code] || 0;
}

function mapApiStation(s) {
  const parts = String(s.name || "").split(" - ");
  const label = parts.length > 1 ? parts.slice(1).join(" - ") : s.name;
  const st = s.state || parseState(s.city);
  return {
    code: s.code,
    name: label,
    city: parseCity(s.city),
    st,
    dist: s.distance_km,
    ll: [s.lat, s.lng],
  };
}

function resolveStationCode(c) {
  const fromName = c.full_name.match(/^([A-Z0-9]+)\s·/);
  if (fromName) return fromName[1];
  const fromNotes = String(c.notes || "").match(/Estación:\s*([A-Z0-9]+)/);
  return fromNotes ? fromNotes[1] : null;
}

function resolveUsState(c) {
  const code = resolveStationCode(c);
  if (code) {
    if (codeToState[code]) return codeToState[code];
    const hit = STATIONS.find((x) => x.code === code);
    if (hit?.st) return hit.st;
  }
  const reg = String(c.region || "").trim();
  if (/^[A-Z]{2}$/.test(reg)) return reg;
  return "—";
}

function mapCandidate(c) {
  const stationLabel = c.full_name.includes(" · ") ? c.full_name.split(" · ").slice(1).join(" · ") : c.region || "—";
  const code = resolveStationCode(c);
  const st = resolveUsState(c);
  const total = 8;
  const stepMap = {
    not_started: 1,
    invited: 2,
    registration_started: 3,
    documents_pending: 4,
    documents_submitted: 5,
    background_check: 6,
    waitlisted: 6,
    approved_active: 8,
    rejected: 4,
    inactive: 2,
  };
  const step = stepMap[c.status] || 1;
  return {
    id: c.id,
    name: c.full_name.includes(" · ") ? c.full_name.split(" · ").slice(1).join(" · ").replace(/ #\d+$/, "") : c.full_name,
    mail: c.assigned_email,
    st: code ? `${code} · ${stationLabel}` : stationLabel,
    state: st,
    stage: STATUS_LABELS[c.status] || c.status,
    step: c.status === "approved_active" ? total : step,
    total,
    upd: relTime(c.updated_at),
    color: avatarColor(c.full_name),
    status: c.status,
    hasCredential: !!c.has_mailbox_credential,
    raw: c,
  };
}

function dispatchBlockReason(e) {
  if (!DISPATCH_ELIGIBLE.has(e.status || e.raw?.status)) {
    return "Ya enviada a creación Amazon Flex";
  }
  if (!e.hasCredential) {
    return "Sin credencial de buzón guardada";
  }
  return null;
}

function canEditSiembraCredentials(c) {
  return DISPATCH_ELIGIBLE.has(c.status);
}

function renderCredentialsEditHtml(c, e) {
  if (!canEditSiembraCredentials(c)) return "";
  const passHint = e.hasCredential
    ? "Contraseña guardada — escribe una nueva (≥8, letras+números) o «Ver actual»"
    : "Pass Amazon ≥8 chars, letras+números (ej. FlexMiami01!)";
  const zipVal = c.zip_code || "";
  return (
    `<div class="dsec dsec--creds" id="detailCreds">` +
    `<div class="dsec__t">Credenciales Amazon <span style="font-weight:500;text-transform:none;letter-spacing:0;color:var(--muted)">· paso 1 crear/login · editable antes de Sembrar</span></div>` +
    `<div class="creds">` +
    `<div class="fld creds__fld"><span class="fld__l">Email</span><input class="inp creds__inp" id="editMail" type="email" value="${escapeHtml(c.assigned_email)}" autocomplete="off"/></div>` +
    `<div class="fld creds__fld"><span class="fld__l">Contraseña</span><input class="inp creds__inp" id="editPass" type="password" placeholder="${escapeHtml(passHint)}" autocomplete="new-password"/></div>` +
    `<div class="fld creds__fld"><span class="fld__l">ZIP región Flex</span><input class="inp creds__inp" id="editZip" type="text" inputmode="numeric" maxlength="10" value="${escapeHtml(zipVal)}" placeholder="Ej. 33101"/></div>` +
    `<div class="creds__acts">` +
    `<button type="button" class="btn btn--ghost btn--sm" id="btnLoadPass">Ver actual</button>` +
    `<button type="button" class="btn btn--primary btn--sm" id="btnSaveCreds">Guardar</button>` +
    `</div></div></div>`
  );
}

function isDispatchEligible(e) {
  return !dispatchBlockReason(e);
}

function siembrasInState(st) {
  return SIEMBRAS.filter((e) => (e.state || "—") === st);
}

function selectedEligibleSiembras() {
  return SIEMBRAS.filter((e) => expSel[e.id] && isDispatchEligible(e));
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function renderChecklistHtml(step, total) {
  return ONBOARDING_CHECKLIST.map((item, k) => {
    const cls = k < step - 1 ? "done" : k === step - 1 ? "cur" : "";
    return (
      `<div class="ck ${cls}"><span class="ck__box">${cls === "done" ? chk : ""}</span>` +
      `<span><div class="ck__l">${escapeHtml(item[0])}</div><div class="ck__m">${escapeHtml(item[1])}</div></span></div>`
    );
  }).join("");
}

function renderDetailEmpty() {
  $("#expDetail").innerHTML =
    '<div class="empty exp-detail__empty">' +
    '<span class="empty__ic"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg></span>' +
    '<div class="empty__t">Selecciona una siembra</div>' +
    '<div class="empty__s">Haz clic en un candidato de la lista para ver el checklist y avanzar el onboarding.</div></div>';
}

function stageTagCls(step, total) {
  if (step === total) return "done";
  return step > 3 ? "wait" : "new";
}

/* ---------- KPIs ---------- */
async function loadKpis() {
  const data = await api("/meta/summary");
  const by = data.by_status;
  const total = Object.values(by).reduce((a, b) => a + b, 0);
  const proc =
    (by.invited || 0) +
    (by.registration_started || 0) +
    (by.documents_pending || 0) +
    (by.documents_submitted || 0) +
    (by.background_check || 0) +
    (by.waitlisted || 0);
  const act = by.approved_active || 0;
  $("#kpiTotal").textContent = total;
  $("#kpiProc").textContent = proc;
  $("#kpiAct").textContent = act;
  $("#stepCount2").textContent = total - act;
  $("#stepCount3").textContent = act;
}

async function loadStationIndex() {
  try {
    const data = await api("/meta/station-index");
    codeToState = data.index || {};
  } catch (_) {
    codeToState = {};
  }
}

async function loadSiembraCounts() {
  try {
    const data = await api("/candidates/grouped?limit=2000");
    siembraByCode = {};
    (data.groups || []).forEach((g) => {
      if (g.station_code && g.station_code !== "__none__") {
        siembraByCode[g.station_code] = g.total;
      }
    });
  } catch (_) {
    siembraByCode = {};
  }
}

async function loadMeta() {
  const [states, statuses] = await Promise.all([api("/meta/us-states"), api("/meta/statuses")]);
  statusesMeta = statuses.all;
  const sel = $("#fState");
  states.states.forEach((s) => {
    const o = document.createElement("option");
    o.value = s.code;
    o.textContent = `${s.name} (${s.code})`;
    sel.appendChild(o);
  });
  const expSt = $("#expStatus");
  statuses.all.forEach((s) => {
    const o = document.createElement("option");
    o.value = s;
    o.textContent = STATUS_LABELS[s] || s.replace(/_/g, " ");
    expSt.appendChild(o);
  });
}

/* ---------- STAGE 1 ---------- */
async function applyFilters(showAll) {
  const q = $("#q").value.trim().toLowerCase();
  const st = $("#fState").value;
  const city = $("#fCity").value.trim();
  const zip = $("#fZip").value.trim();
  const any = q || st || city || zip;

  if (!any && !showAll) {
    filtered = [];
    renderChips({ q, st, city, zip });
    renderStations();
    drawMap();
    return;
  }

  const params = new URLSearchParams();
  if (st) params.set("state", st);
  if (city) params.set("city", city);
  if (zip) params.set("zip", zip);

  try {
    const data = await api("/meta/flex-stations?" + params.toString());
    STATIONS = data.stations.map(mapApiStation);
    STATIONS.forEach((s) => {
      codeToState[s.code] = s.st;
    });
    filtered = STATIONS.filter((s) => {
      if (q && (s.code + " " + s.name + " " + s.city + " " + s.st).toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
    await loadSiembraCounts();
    renderChips({ q, st, city, zip });
    renderStations();
    drawMap();
    refreshStationFilters();
  } catch (e) {
    toast(e.message, "error");
  }
}

function refreshStationFilters() {
  const codes = [...new Set(SIEMBRAS.map((e) => e.st.split(" · ")[0]).filter(Boolean))];
  const selEl = $("#expStation");
  selEl.innerHTML = '<option value="">Todas</option>';
  codes.forEach((c) => {
    const o = document.createElement("option");
    o.value = c;
    o.textContent = c;
    selEl.appendChild(o);
  });
}

function renderChips(f) {
  const box = $("#chips");
  const out = [];
  const L = { q: "Búsqueda", st: "Estado", city: "Ciudad", zip: "ZIP" };
  Object.keys(L).forEach((k) => {
    if (f[k]) out.push(`<span class="chip">${L[k]}: <b style="color:var(--ink)">${escapeHtml(f[k])}</b><button type="button" data-x="${k}">✕</button></span>`);
  });
  box.style.display = out.length ? "flex" : "none";
  box.innerHTML = '<span class="chips__l">Filtros activos:</span>' + out.join("");
}

function stationRow(s) {
  const on = !!sel[s.code];
  const n = siembraCount(s.code);
  const dist =
    s.dist != null ? `<div class="saddr">${s.dist} km</div>` : "";
  return (
    `<div class="row${on ? " is-sel" : ""}" data-code="${escapeHtml(s.code)}">` +
    `<span class="cb${on ? " is-on" : ""}">${on ? chk : ""}</span>` +
    `<span class="code">${escapeHtml(s.code)}</span>` +
    `<span style="min-width:0"><div class="sname">${escapeHtml(s.name)}</div>${dist}</span>` +
    `<span class="cell">${escapeHtml(s.city)}</span>` +
    `<span class="cell--mono">${escapeHtml(s.st)}</span>` +
    `<span class="cell--num">${n}</span>` +
    `<span class="rowico">${dots}</span></div>`
  );
}

function groupSiembraTotal(stations) {
  return stations.reduce((t, s) => t + siembraCount(s.code), 0);
}

function renderStations() {
  const box = $("#stations");
  $("#count").textContent = filtered.length ? filtered.length + " resultados" : "— resultados";
  if (!filtered.length) {
    box.innerHTML =
      '<div class="empty"><span class="empty__ic"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg></span>' +
      '<div class="empty__t">Busca estaciones para empezar</div>' +
      '<div class="empty__s">Filtra por estado, ciudad o ZIP code y pulsa <b style="color:var(--ink2)">Aplicar filtros</b>. Luego marca las estaciones y crea sus siembras.</div></div>';
    return;
  }
  if (groupBy === "flat") {
    box.innerHTML = filtered.map(stationRow).join("");
    return;
  }
  const by = {};
  filtered.forEach((s) => {
    (by[s.st] = by[s.st] || []).push(s);
  });
  box.innerHTML = Object.keys(by)
    .sort()
    .map((st) => {
      const g = by[st];
      const siembras = groupSiembraTotal(g);
      return (
        `<div class="grp"><div class="grp__h"><span class="grp__st">${escapeHtml(st)}</span>` +
        `<span class="grp__n">${g.length} estaciones</span>` +
        `<span class="grp__c">${siembras} siembra${siembras === 1 ? "" : "s"}</span></div>${g.map(stationRow).join("")}</div>`
      );
    })
    .join("");
}

function refreshSel() {
  const n = Object.keys(sel).length;
  $("#selbar").classList.toggle("is-on", n > 0);
  $("#selN").textContent = n;
  $("#createN").textContent = n;
  const picked = STATIONS.filter((s) => sel[s.code]);
  const sts = [...new Set(picked.map((s) => s.st))];
  const existing = picked.reduce((t, s) => t + siembraCount(s.code), 0);
  $("#selMeta").textContent =
    (sts.length ? sts.join(", ") : "—") +
    (existing ? ` · ${existing} siembra${existing === 1 ? "" : "s"} ya registrada${existing === 1 ? "" : "s"}` : "");
  $("#mapMeta").textContent = n ? n + " resaltadas" : "Selecciona estaciones para resaltarlas";
  drawMap();
}

function drawMap() {
  if (!map) return;
  Object.keys(markers).forEach((k) => map.removeLayer(markers[k]));
  markers = {};
  const list = filtered;
  list.forEach((s) => {
    if (!s.ll || !s.ll[0]) return;
    const on = !!sel[s.code];
    const n = siembraCount(s.code);
    markers[s.code] = L.circleMarker(s.ll, {
      radius: on ? 10 : 6,
      color: on ? "#F59E0B" : "#0B0F19",
      weight: on ? 3 : 1.5,
      fillColor: on ? "#F59E0B" : "#60A5FA",
      fillOpacity: on ? 1 : 0.75,
    })
      .addTo(map)
      .bindPopup(
        `<b>${escapeHtml(s.code)}</b> · ${escapeHtml(s.city)}, ${escapeHtml(s.st)}<br>${escapeHtml(s.name)}` +
          (s.dist != null ? `<br><span style='color:#8492AB'>${s.dist} km del filtro</span>` : "") +
          `<br><span style='color:#8492AB'>${n} siembra${n === 1 ? "" : "s"} en tu CRM</span>`
      );
  });
  $("#mfVis").textContent = list.length;
  $("#mfStates").textContent = new Set(list.map((s) => s.st)).size;
  $("#mfSiembras").textContent = groupSiembraTotal(list);
  if (list.length) {
    try {
      map.fitBounds(
        list.map((s) => s.ll),
        { padding: [34, 34], maxZoom: 9 }
      );
    } catch (_) {}
  }
}

function openOv() {
  const picked = STATIONS.filter((s) => sel[s.code]);
  if (!picked.length) return;
  $("#ovList").innerHTML = picked
    .map(
      (s) =>
        `<div class="mitem"><span class="mitem__c">${escapeHtml(s.code)}</span>` +
        `<span style="flex:1;min-width:0"><div class="sname">${escapeHtml(s.name)}</div><div class="saddr">${escapeHtml(s.city)}, ${escapeHtml(s.st)}</div></span>` +
        `<span class="cell--num">${siembraCount(s.code)}</span></div>`
    )
    .join("");
  const qty = Math.max(1, parseInt($("#ovQty").value, 10) || 1);
  const total = picked.length * qty;
  $("#ovN").textContent = total;
  $("#ovMeta").textContent = `${total} siembra(s) nueva(s) · ${picked.length} estación(es)`;
  if ($("#ovZip") && !$("#ovZip").value.trim()) {
    $("#ovZip").value = $("#fZip").value.trim() || "";
  }
  $("#ov").classList.add("is-on");
}

async function createSiembras() {
  const picked = STATIONS.filter((s) => sel[s.code]);
  if (!picked.length) return;
  const prefix = ($("#ovPrefix").value || "flexamazon_").trim();
  const domain = ($("#ovDomain").value || "cosecha.it.com").replace(/^@+/, "");
  const qty = Math.max(1, parseInt($("#ovQty").value, 10) || 1);
  const baseNum = String(Date.now()).slice(-8);
  const zip = ($("#ovZip")?.value || $("#fZip").value || "").trim() || null;
  const city = $("#fCity").value.trim() || null;
  let created = 0;
  let idx = 0;
  $("#ovOk").disabled = true;
  for (const s of picked) {
    for (let q = 0; q < qty; q++) {
      const local = `${prefix}${baseNum}${idx}`;
      idx++;
      const email = `${local}@${domain}`;
      const shortName = s.name.replace(/ Delivery Station$/, "");
      try {
        const c = await api("/candidates", {
          method: "POST",
          body: JSON.stringify({
            full_name: `${s.code} · ${shortName}${qty > 1 ? ` #${q + 1}` : ""}`,
            assigned_email: email,
            region: s.st || city,
            zip_code: zip,
            notes: `Siembra auto. Estación: ${s.code} — ${s.name}`,
            seed_checklist: true,
          }),
        });
        await api(`/candidates/${c.id}/mailbox-credential`, {
          method: "PUT",
          body: JSON.stringify({ password: local }),
        });
        created++;
      } catch (_) {}
    }
  }
  $("#ovOk").disabled = false;
  $("#ov").classList.remove("is-on");
  sel = {};
  toast(`${created} siembra(s) creada(s)`);
  expOpen = {};
  picked.forEach((s) => {
    if (s.st) expOpen[s.st] = true;
  });
  await loadSiembraCounts();
  await loadSiembras();
  await loadKpis();
  goStage("2");
}

/* ---------- STAGE 2 ---------- */
async function loadSiembras() {
  const search = $("#expQ").value.trim();
  const status = $("#expStatus").value;
  const station = $("#expStation").value;
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (status) params.set("status", status);
  params.set("limit", "500");
  const data = await api("/candidates?" + params.toString());
  SIEMBRAS = data.items.map(mapCandidate);
  if (station) SIEMBRAS = SIEMBRAS.filter((e) => e.st.startsWith(station + " ·") || e.st.startsWith(station));
  $("#expCount").textContent = SIEMBRAS.length + " registros";
  renderExps();
  if (SIEMBRAS.length) {
    const still = SIEMBRAS.find((e) => e.id === selectedExpId);
    if (!still) {
      selectedExpId = SIEMBRAS[0].id;
      if (SIEMBRAS[0].state && SIEMBRAS[0].state !== "—") expOpen[SIEMBRAS[0].state] = true;
      renderExps();
    }
    await renderDetail(selectedExpId);
  } else {
    selectedExpId = null;
    renderDetailEmpty();
  }
  refreshStationFilters();
  refreshExpSel();
}

function refreshExpSel() {
  const ids = Object.keys(expSel);
  const n = ids.length;
  const eligible = selectedEligibleSiembras();
  const pend = eligible.length;
  const bar = $("#expSelbar");
  if (bar) bar.classList.toggle("is-on", n > 0);
  if ($("#expSelN")) $("#expSelN").textContent = n;
  if ($("#expSembrarN")) $("#expSembrarN").textContent = pend;
  const sembrarBtn = $("#expSembrar");
  if (sembrarBtn) {
    sembrarBtn.disabled = pend === 0;
    sembrarBtn.title = pend === 0 && n > 0 ? "Las seleccionadas ya están creadas o no tienen credencial" : "";
  }
  const headBtn = $("#expSembrarHead");
  if (headBtn) {
    headBtn.disabled = pend === 0;
    headBtn.textContent = pend > 0 ? `Sembrar (${pend})` : "Sembrar";
  }
  const states = [...new Set(SIEMBRAS.filter((e) => expSel[e.id]).map((e) => e.state))];
  if ($("#expSelMeta")) {
    if (!n) {
      $("#expSelMeta").textContent = "marca filas o usa el checkbox del estado";
    } else if (!pend) {
      $("#expSelMeta").textContent = "ninguna pendiente de creación en la selección";
    } else {
      $("#expSelMeta").textContent =
        pend + " pendiente" + (pend === 1 ? "" : "s") + " de envío" + (states.length ? " · " + states.join(", ") : "");
    }
  }
}

function toggleExpGroupSel(st, e) {
  if (e) e.stopPropagation();
  const list = siembrasInState(st);
  const all = list.length > 0 && list.every((x) => expSel[x.id]);
  list.forEach((x) => {
    if (all) delete expSel[x.id];
    else expSel[x.id] = true;
  });
  refreshExpSel();
  renderExps();
}

function formatDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderTimelineHtml(events) {
  const list = (events || []).slice(0, 4);
  if (!list.length) return "";
  return (
    `<div class="dsec dsec--timeline"><div class="dsec__t">Historial reciente</div><div class="tl">` +
    list
      .map(
        (ev) =>
          `<div class="tl__row"><div class="tl__msg">${escapeHtml(ev.message)}</div>` +
          `<div class="tl__when">${formatDateTime(ev.created_at)}</div></div>`
      )
      .join("") +
    `</div></div>`
  );
}

function closeSembrarResult() {
  $("#sembrarOv").classList.remove("is-on");
}

function flexOutcomeLabel(code) {
  const map = {
    region_ready: "Región aceptada · listo para docs (otra persona)",
    waitlisted: "Lista de interés (sin cupo en esa zona)",
    needs_app: "Cuenta OK · falta Appium/emulador o ZIP",
    needs_verification: "Paso 1: Amazon pide OTP (revisa forward email)",
    identity_ok: "Cuenta Amazon OK · región no confirmada aún",
    failed: "Falló",
  };
  return map[code] || code || "—";
}

function showSembrarResult(result) {
  const ok = result.items || [];
  const fail = result.skipped_items || [];
  const total = ok.length + fail.length;
  const title = ok.length
    ? fail.length
      ? "Sembrado parcial (hasta región)"
      : "Sembrado hasta región / lista"
    : "No se pudo sembrar";
  $("#sembrarOvTitle").textContent = title;
  $("#sembrarOvMeta").textContent = `${ok.length} correcta(s) · ${fail.length} fallida(s) de ${total}`;

  const rows = [];
  ok.forEach((item) => {
    const st = STATUS_LABELS[item.new_status] || item.new_status;
    const outcome = flexOutcomeLabel(item.flex_outcome);
    const zip = item.zip_used ? ` · ZIP ${item.zip_used}` : "";
    rows.push(
      `<div class="sres__row sres__row--ok">` +
        `<span class="sres__ic">✓</span>` +
        `<span><div class="sres__mail">${escapeHtml(item.assigned_email)}</div>` +
        `<div class="sres__msg">${escapeHtml(item.creation_message || "Enviado correctamente.")}</div>` +
        `<div class="sres__st">Outcome: ${escapeHtml(outcome)}${escapeHtml(zip)}</div>` +
        `<div class="sres__st">Estado CRM: ${escapeHtml(st)}</div></span></div>`
    );
  });
  fail.forEach((item) => {
    const outcome = item.flex_outcome
      ? `<div class="sres__st">Outcome: ${escapeHtml(flexOutcomeLabel(item.flex_outcome))}</div>`
      : "";
    rows.push(
      `<div class="sres__row sres__row--fail">` +
        `<span class="sres__ic">✕</span>` +
        `<span><div class="sres__mail">${escapeHtml(item.assigned_email || "Siembra #" + item.id)}</div>` +
        `<div class="sres__msg" style="white-space:pre-wrap;word-break:break-word">${escapeHtml(item.reason || item.creation_message || "Error desconocido")}</div>` +
        outcome +
        `<div class="sres__st">Sigue pendiente · no cambió de estado · mira también la línea de tiempo</div></span></div>`
    );
  });
  $("#sembrarOvBody").innerHTML =
    `<p style="font-size:12px;color:var(--muted);margin-bottom:12px;line-height:1.45">` +
    `Alcance: cuenta Amazon + región/lista. <b>No</b> sube licencia, SSN ni banco (eso lo hace otra persona).` +
    `</p><div class="sres">${rows.join("")}</div>`;
  $("#sembrarOv").classList.add("is-on");
}

function showSembrarProgress(jobId, message) {
  $("#sembrarOvTitle").textContent = "Sembrando…";
  $("#sembrarOvMeta").textContent = `Job ${jobId.slice(0, 8)}…`;
  $("#sembrarOvBody").innerHTML =
    `<p style="font-size:13px;color:var(--ink2);line-height:1.5">${escapeHtml(message || "En cola. El worker procesa en segundo plano…")}</p>` +
    `<p style="font-size:12px;color:var(--muted);margin-top:10px">Puedes dejar esta ventana abierta; se actualizará sola.</p>`;
  $("#sembrarOv").classList.add("is-on");
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function pollFlexJob(jobId, { timeoutMs = 15 * 60 * 1000, intervalMs = 2000 } = {}) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const job = await api(`/jobs/${jobId}`);
    showSembrarProgress(jobId, job.message || job.status);
    if (job.status === "completed" || job.status === "failed") return job;
    await sleep(intervalMs);
  }
  throw new Error("Timeout esperando el job de Sembrar");
}

async function sembrarCandidates(ids, confirmMsg) {
  const eligible = SIEMBRAS.filter((e) => ids.includes(e.id) && isDispatchEligible(e));
  if (!eligible.length) {
    toast("Ninguna siembra pendiente de creación en la selección", "error");
    return;
  }
  if (confirmMsg !== false) {
    const msg =
      confirmMsg ||
      `¿Sembrar ${eligible.length} siembra(s)?\n\n` +
      `1) Cuenta Amazon (web)\n` +
      `2) ZIP/región (web + app Android si Appium está activo)\n` +
      `3) Para ANTES de licencia/SSN/banco\n\n` +
      `El trabajo corre en cola (async). ¿Continuar?`;
    if (!confirm(msg)) return;
  }
  try {
    const enq = await api("/candidates/batch/dispatch-flex", {
      method: "POST",
      body: JSON.stringify({ candidate_ids: eligible.map((e) => e.id) }),
    });
    toast(`Job en cola · ${enq.candidate_count} siembra(s)`, "success");
    showSembrarProgress(enq.job_id, enq.message);
    const job = await pollFlexJob(enq.job_id);
    expSel = {};
    if (job.status === "failed") {
      toast("Sembrado falló — mira el motivo en el modal", "error");
      $("#sembrarOvTitle").textContent = "Sembrado falló";
      $("#sembrarOvMeta").textContent = `Job ${(job.id || "").slice(0, 8)}… · failed`;
      const errTxt = job.error || job.message || "Error desconocido (sin detalle del worker)";
      $("#sembrarOvBody").innerHTML =
        `<div class="sres__row sres__row--fail"><span class="sres__ic">✕</span>` +
        `<span><div class="sres__mail">Motivo</div>` +
        `<div class="sres__msg" style="white-space:pre-wrap;word-break:break-word">${escapeHtml(errTxt)}</div>` +
        `<div class="sres__st">También queda en la línea de tiempo del expediente.</div></span></div>`;
      return null;
    }
    const result = job.result || { dispatched: 0, skipped: 0, items: [], skipped_items: [] };
    showSembrarResult(result);
    const toastMsg = `${result.dispatched} creada(s) en Amazon${result.skipped ? ` · ${result.skipped} fallida(s)` : ""}`;
    toast(toastMsg, result.dispatched ? "success" : "error");
    await loadSiembraCounts();
    await loadSiembras();
    await loadKpis();
    const refreshId = selectedExpId || (result.items?.[0]?.id ?? result.skipped_items?.[0]?.id);
    if (refreshId) await renderDetail(refreshId);
    return result;
  } catch (err) {
    toast(err.message, "error");
    throw err;
  }
}

async function batchSembrar() {
  const eligible = selectedEligibleSiembras();
  if (!eligible.length) {
    toast("Selecciona siembras con etiqueta Pendiente (Sin iniciar / Invitado)", "error");
    return;
  }
  $("#expSembrar").disabled = true;
  try {
    await sembrarCandidates(eligible.map((e) => e.id));
  } catch (err) {
    toast(err.message, "error");
  } finally {
    refreshExpSel();
  }
}

function expRow(e) {
  const pipe = [];
  for (let k = 0; k < e.total; k++) {
    pipe.push(`<i class="${k < e.step - 1 ? "on" : k === e.step - 1 ? "cur" : ""}"></i>`);
  }
  const t = stageTagCls(e.step, e.total);
  const on = e.id === selectedExpId ? " is-on" : "";
  const selOn = !!expSel[e.id];
  const pending = isDispatchEligible(e);
  return (
    `<div class="erow${on}${selOn ? " is-sel" : ""}" data-eid="${e.id}">` +
    `<span class="cb${selOn ? " is-on" : ""}" data-ecb="${e.id}">${selOn ? chk : ""}</span>` +
    `<span class="cand"><span class="ava" style="background:${e.color}">${initials(e.name)}</span>` +
    `<span style="min-width:0"><div class="cname">${escapeHtml(e.name)}</div><div class="cmail">${escapeHtml(e.mail)}</div></span></span>` +
    `<span class="cell--mono">${escapeHtml(e.st)}</span>` +
    `<span><span class="tag tag--${t}"><span class="tag__dot"></span>${escapeHtml(e.stage)}</span>` +
    (pending ? `<span class="tag tag--new" style="margin-left:4px;font-size:10px;padding:2px 6px"><span class="tag__dot"></span>Pendiente</span>` : "") +
    `</span>` +
    `<span><div class="pipe">${pipe.join("")}</div><span class="pipe__t">${e.step}/${e.total} pasos</span></span>` +
    `<span class="cell" style="color:var(--muted2)">${escapeHtml(e.upd)}</span>` +
    `<span class="rowico">${dots}</span></div>`
  );
}

function renderExps() {
  if (!SIEMBRAS.length) {
    $("#exps").innerHTML =
      '<div class="empty" style="padding:32px 16px"><div class="empty__t">Sin siembras</div>' +
      '<div class="empty__s">Crea siembras desde el paso 1 o importa un CSV.</div></div>';
    refreshExpSel();
    return;
  }
  const by = {};
  SIEMBRAS.forEach((e) => {
    const st = e.state || "—";
    (by[st] = by[st] || []).push(e);
  });
  $("#exps").innerHTML = Object.keys(by)
    .sort((a, b) => (a === "—") - (b === "—") || a.localeCompare(b))
    .map((st) => {
      const list = by[st];
      const isOpen = !!expOpen[st];
      const ready = list.filter((e) => e.step === e.total).length;
      const siembraWord = list.length === 1 ? "siembra" : "siembras";
      const listaWord = ready === 1 ? "lista" : "listas";
      const allGrp = list.length > 0 && list.every((x) => expSel[x.id]);
      const head =
        `<div class="grp__h" data-egrp="${escapeHtml(st)}">` +
        `<span class="cb cb--grp${allGrp ? " is-on" : ""}" data-egrp-sel="${escapeHtml(st)}">${allGrp ? chk : ""}</span>` +
        `<span class="ecaret${isOpen ? " is-open" : ""}">${caretSvg}</span>` +
        `<span class="grp__st">${escapeHtml(st)}</span>` +
        `<span class="grp__n">${list.length} ${siembraWord}</span>` +
        `<span class="grp__c">${ready} ${listaWord} para handoff</span></div>`;
      return `<div class="grp">${head}${isOpen ? list.map(expRow).join("") : ""}</div>`;
    })
    .join("");
  refreshExpSel();
}

async function renderDetail(id) {
  selectedExpId = id;
  try {
    const c = await api(`/candidates/${id}`);
    const e = mapCandidate(c);
    if (e.state && e.state !== "—") expOpen[e.state] = true;
    const tagCls = e.step === e.total ? "done" : "wait";
    const checks = renderChecklistHtml(e.step, e.total);
    const notesHidden = "hidden";
    const blockReason = dispatchBlockReason(e);
    const canSembrar = !blockReason;
    const footPrimary = canSembrar
      ? `<button type="button" class="btn btn--primary" style="flex:1" id="btnSembrar">Sembrar en Amazon Flex</button>`
      : blockReason && DISPATCH_ELIGIBLE.has(e.status)
        ? `<button type="button" class="btn btn--primary" style="flex:1" disabled title="${escapeHtml(blockReason)}">Sembrar en Amazon Flex</button>`
        : `<button type="button" class="btn btn--primary" style="flex:1" id="btnAdvance">Avanzar paso</button>`;
    const footSecondary = canSembrar
      ? `<button type="button" class="btn btn--ghost" id="btnAdvance">Avanzar paso</button>`
      : `<button type="button" class="btn btn--ghost" id="btnNotes">Notas</button>`;

    $("#expDetail").innerHTML =
      `<div class="dhead"><div class="dtitle">${escapeHtml(e.name)}</div><div class="dsub">${escapeHtml(e.mail)} · ${escapeHtml(e.st)}</div>` +
      `<div style="margin-top:11px"><span class="tag tag--${tagCls}"><span class="tag__dot"></span>${escapeHtml(e.stage)}</span>` +
      (canSembrar ? `<span class="tag tag--new" style="margin-left:6px"><span class="tag__dot"></span>Pendiente de creación</span>` : "") +
      `</div></div>` +
      `<div class="dgrid">` +
      `<div><div class="dg__k">Estación</div><div class="dg__v">${escapeHtml(e.st)}</div></div>` +
      `<div><div class="dg__k">Progreso</div><div class="dg__v">${e.step} de ${e.total} pasos</div></div>` +
      `<div><div class="dg__k">Creado</div><div class="dg__v">${formatDate(c.created_at)}</div></div>` +
      `<div><div class="dg__k">Actualizado</div><div class="dg__v">${escapeHtml(e.upd)}</div></div></div>` +
      renderCredentialsEditHtml(c, e) +
      renderTimelineHtml(c.timeline_events) +
      `<div class="dsec dsec--scroll"><div class="dsec__t">Checklist de onboarding</div>${checks}</div>` +
      `<div class="dnotes ${notesHidden}" id="detailNotes"><div class="dsec__t">Notas</div>` +
      `<textarea class="dnotes__ta" id="detailNotesTa" rows="4" placeholder="Observaciones del operador…"></textarea>` +
      `<button type="button" class="btn btn--ghost btn--sm" id="btnSaveNotes">Guardar notas</button></div>` +
      `<div class="dfoot">` +
      footPrimary +
      footSecondary +
      `<button type="button" class="btn btn--quiet" id="btnMore" title="Ver credencial">${dots}</button></div>`;

    if ($("#btnSembrar")) {
      $("#btnSembrar").onclick = () => {
        const mail = $("#editMail")?.value.trim() || e.mail;
        sembrarCandidates([c.id], `¿Sembrar en Amazon con ${mail} y la contraseña guardada?`);
      };
    }
    if ($("#btnSaveCreds")) {
      $("#btnSaveCreds").onclick = () =>
        saveSiembraCredentials(c.id, c.assigned_email, c.zip_code);
    }
    if ($("#btnLoadPass")) $("#btnLoadPass").onclick = () => loadSiembraPassword(c.id);
    if ($("#btnAdvance")) $("#btnAdvance").onclick = () => advanceStatus(c);
    if ($("#btnNotes")) $("#btnNotes").onclick = () => $("#detailNotes").classList.toggle("hidden");
    $("#btnSaveNotes").onclick = () => saveNotes(c.id);
    $("#btnMore").onclick = () => revealCred(c.id);
    $("#detailNotesTa").value = c.notes || "";
    expSel = { [c.id]: true };
    refreshExpSel();
    renderExps();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function saveSiembraCredentials(id, originalEmail, originalZip) {
  const emailEl = $("#editMail");
  const passEl = $("#editPass");
  const zipEl = $("#editZip");
  if (!emailEl) return;
  const email = emailEl.value.trim();
  const pass = passEl?.value || "";
  const zip = (zipEl?.value || "").trim() || null;
  const prevZip = (originalZip || "").trim() || null;
  if (!email) {
    toast("El email es obligatorio", "error");
    return;
  }
  const emailChanged = email !== originalEmail;
  const zipChanged = zip !== prevZip;
  if (!emailChanged && !pass && !zipChanged) {
    toast("No hay cambios que guardar", "error");
    return;
  }
  $("#btnSaveCreds").disabled = true;
  try {
    const patch = {};
    if (emailChanged) patch.assigned_email = email;
    if (zipChanged) patch.zip_code = zip;
    if (Object.keys(patch).length) {
      await api(`/candidates/${id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
    }
    if (pass) {
      await api(`/candidates/${id}/mailbox-credential`, {
        method: "PUT",
        body: JSON.stringify({ password: pass }),
      });
    }
    toast("Credenciales / ZIP guardados");
    await loadSiembraCounts();
    await loadSiembras();
    await renderDetail(id);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    if ($("#btnSaveCreds")) $("#btnSaveCreds").disabled = false;
  }
}

async function loadSiembraPassword(id) {
  try {
    const data = await api(`/candidates/${id}/mailbox-credential`);
    const passEl = $("#editPass");
    if (passEl) {
      passEl.value = data.password;
      passEl.type = "text";
    }
    toast("Contraseña cargada");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function saveNotes(id) {
  const notes = $("#detailNotesTa").value.trim();
  try {
    await api(`/candidates/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ notes: notes || null }),
    });
    toast("Notas guardadas");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function advanceStatus(c) {
  const order = statusesMeta.length ? statusesMeta : Object.keys(STATUS_LABELS);
  const idx = order.indexOf(c.status);
  if (idx < 0 || idx >= order.length - 1) {
    toast("Ya está en el último paso", "error");
    return;
  }
  const next = order[idx + 1];
  await api(`/candidates/${c.id}/status`, { method: "POST", body: JSON.stringify({ status: next }) });
  toast("Estado actualizado");
  await loadSiembraCounts();
  await loadSiembras();
  await loadKpis();
  await renderDetail(c.id);
}

async function revealCred(id) {
  try {
    const data = await api(`/candidates/${id}/mailbox-credential`);
    toast(`Email: ${data.assigned_email} · Pass: ${data.password}`, "success");
  } catch (e) {
    toast(e.message, "error");
  }
}

/* ---------- STAGE 3 ---------- */
async function loadActive() {
  const data = await api("/candidates?status=approved_active&limit=500");
  const items = data.items.filter((c) => c.handoff_done);
  if (!items.length) {
    $("#activeEmpty").classList.remove("hidden");
    $("#activeList").classList.add("hidden");
    return;
  }
  $("#activeEmpty").classList.add("hidden");
  $("#activeList").classList.remove("hidden");
  $("#activeList").innerHTML = items
    .map(
      (c) =>
        `<div class="erow"><span class="cand"><span class="ava">${initials(c.full_name)}</span>` +
        `<span><div class="cname">${escapeHtml(c.full_name)}</div><div class="cmail">${escapeHtml(c.assigned_email)}</div></span></span></div>`
    )
    .join("");
}

function goStage(n) {
  document.querySelectorAll(".ws").forEach((w) => w.classList.remove("is-on"));
  $("#ws" + n).classList.add("is-on");
  document.querySelectorAll(".step").forEach((s) => s.classList.toggle("is-on", s.getAttribute("data-go") === n));
  if (n === "1") {
    loadSiembraCounts().then(() => {
      renderStations();
      refreshSel();
      if (map) setTimeout(() => map.invalidateSize(), 60);
    });
  }
  if (n === "2") loadSiembras();
  if (n === "3") loadActive();
}

/* ---------- WIRING ---------- */
function wire() {
  $("#stations").innerHTML = "";
  renderStations();

  $("#apply").onclick = () => applyFilters(false);
  $("#clear").onclick = () => {
    ["q", "fCity", "fZip"].forEach((id) => ($("#" + id).value = ""));
    $("#fState").value = "";
    sel = {};
    applyFilters(false);
    refreshSel();
  };
  $("#q").onkeydown = (e) => {
    if (e.key === "Enter") applyFilters(false);
  };

  $("#chips").onclick = (e) => {
    const b = e.target.closest("[data-x]");
    if (!b) return;
    const k = b.getAttribute("data-x");
    const mapId = { q: "q", city: "fCity", zip: "fZip", st: "fState" };
    if (mapId[k]) $(mapId[k]).value = "";
    applyFilters(false);
  };

  $("#stations").onclick = (e) => {
    const r = e.target.closest("[data-code]");
    if (!r) return;
    const c = r.getAttribute("data-code");
    if (sel[c]) delete sel[c];
    else sel[c] = true;
    renderStations();
    refreshSel();
  };

  $("#selAll").onclick = () => {
    if (!filtered.length) applyFilters(true);
    const all = filtered.every((s) => sel[s.code]);
    filtered.forEach((s) => {
      if (all) delete sel[s.code];
      else sel[s.code] = true;
    });
    renderStations();
    refreshSel();
  };
  $("#selClear").onclick = () => {
    sel = {};
    renderStations();
    refreshSel();
  };

  document.querySelectorAll("[data-grp]").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll("[data-grp]").forEach((x) => x.classList.remove("is-on"));
      b.classList.add("is-on");
      groupBy = b.getAttribute("data-grp");
      renderStations();
    };
  });

  document.querySelectorAll("[data-go]").forEach((b) => {
    b.onclick = () => goStage(b.getAttribute("data-go"));
  });

  $("#exps").onclick = (e) => {
    const grpCb = e.target.closest("[data-egrp-sel]");
    if (grpCb) {
      toggleExpGroupSel(grpCb.getAttribute("data-egrp-sel"), e);
      return;
    }
    const rowCb = e.target.closest("[data-ecb]");
    if (rowCb) {
      e.stopPropagation();
      const id = +rowCb.getAttribute("data-ecb");
      if (expSel[id]) delete expSel[id];
      else expSel[id] = true;
      refreshExpSel();
      renderExps();
      return;
    }
    const g = e.target.closest("[data-egrp]");
    if (g) {
      const st = g.getAttribute("data-egrp");
      if (expOpen[st]) delete expOpen[st];
      else expOpen[st] = true;
      renderExps();
      return;
    }
    const r = e.target.closest("[data-eid]");
    if (!r) return;
    const id = +r.getAttribute("data-eid");
    renderDetail(id);
  };

  $("#expSelClear").onclick = () => {
    expSel = {};
    refreshExpSel();
    renderExps();
  };
  $("#expSembrar").onclick = () => batchSembrar();
  $("#expSembrarHead").onclick = () => batchSembrar();

  $("#expApply").onclick = () => loadSiembras();
  $("#createBtn").onclick = openOv;
  ["ovX", "ovCancel"].forEach((id) => {
    $("#" + id).onclick = () => $("#ov").classList.remove("is-on");
  });
  $("#ov").onclick = (e) => {
    if (e.target === $("#ov")) $("#ov").classList.remove("is-on");
  };
  $("#ovOk").onclick = createSiembras;
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      $("#ov").classList.remove("is-on");
      $("#importOv").classList.remove("is-on");
      closeSembrarResult();
    }
  });

  $("#btnImport").onclick = () => $("#importOv").classList.add("is-on");
  ["importX", "importCancel"].forEach((id) => {
    $("#" + id).onclick = () => $("#importOv").classList.remove("is-on");
  });
  $("#importOk").onclick = async () => {
    const f = $("#importFile").files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    const res = await fetch(API + "/candidates/import?seed_checklist=true", { method: "POST", body: fd });
    const body = await res.json();
    $("#importResult").textContent = res.ok ? `Creados: ${body.created}, omitidos: ${body.skipped}` : body.detail;
    if (res.ok) {
      await loadSiembraCounts();
      await loadKpis();
      await loadSiembras();
    }
  };

  $("#btnNewSiembra").onclick = () => goStage("1");

  $("#sembrarOvOk").onclick = closeSembrarResult;
  $("#sembrarOvX").onclick = closeSembrarResult;
  $("#sembrarOv").onclick = (e) => {
    if (e.target === $("#sembrarOv")) closeSembrarResult();
  };

  map = L.map("map", { zoomControl: true, attributionControl: false }).setView([31.5, -88], 4);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", { maxZoom: 19 }).addTo(map);
  setTimeout(() => {
    map.invalidateSize();
    drawMap();
  }, 200);
}

async function init() {
  try {
    await loadStationIndex();
    await loadSiembraCounts();
    await loadMeta();
    await loadKpis();
  wire();
  renderDetailEmpty();
  await loadSiembras();
  } catch (e) {
    toast("Error al conectar API: " + e.message, "error");
  }
}

init();
