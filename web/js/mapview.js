import { state, api, on, emit, chip, esc, icon, when, hm, dur, addMin, minutesBetween, fieldProps, planFor, toast, stateBox,
  showAlert, hideAlert, loadPlan, compass, statusText, demoText } from './core.js';
import { statusPanel, equipmentPanel } from './panels.js';
import { nozzleCards, liquidCard, terrainCard, sunElevation } from './insight.js';

const STATUS_COLOR = { GO: '#46D39A', CAUTION: '#F5B83D', STOP: '#FF6B5E', INSUFFICIENT_DATA: '#9AA7B4' };
const KIND_COLOR = { neighbor_crop: '#A3D65C', worker_area: '#C08CFF', home: '#FF8FB8', road: '#C9CED3', waterway: '#5AB8FF' };
const KIND_LABEL = { neighbor_crop: 'Neighboring crop', worker_area: 'Worker area', home: 'Homes', road: 'Road', waterway: 'Waterway / ditch' };
const SLOTS = 192;
const MAST_EXAG = 4;          // mast drawn 4x taller than 30 ft so it is visible; labeled in legend
const WIND_EXAG = 70;         // particle travel speed exaggeration for readability; labeled in legend
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const isMobile = () => matchMedia('(max-width: 820px)').matches;
const UI = () => state.ui;

let V = null;

export function renderMap(root, params) {
  teardown();
  if (params.get('field')) state.selectedField = params.get('field');
  V = { root, map: null, markers: [], all: null, assess: null, ev: null, rec: null, unitId: null, cfgOverride: {}, orientation: 0,
    draw: null, play: null, unsub: null, fallback: false, sheet: 'peek', pane: 'status', windFx: null, vehicleMk: null, speed: 5,
    pickerOpen: false, orbitRaf: null, povBrg: null, live: null, terrainStats: null, profiles: {}, liveMarkers: [] };
  const fp = fieldProps(state.selectedField);
  root.innerHTML = `
  <div class="mapview" id="mv">
    <div class="center">
      <div id="map" role="region" aria-label="3D field map. Field details are listed in the side panels."></div>
      <canvas id="wind-canvas" aria-hidden="true"></canvas>
      <div class="hud" id="hud" aria-live="polite"></div>
      <div class="view-pill" id="view-pill" hidden></div>
      <div class="map-legend" id="legend"></div>
      <div class="map-tools">
        <button type="button" class="btn sm legend-toggle" id="legend-toggle" aria-expanded="false" aria-controls="legend">${icon('layers', 'sm')}Legend</button>
      </div>
      <div class="replay-pill" id="replay-pill" hidden></div>
      <div class="map-chip" id="map-chip" hidden></div>
      <p class="map-note demo-note" id="map-note"><b>Fictional demo fields</b> over real imagery. Wind and thermal layers are interpolated from 2 simulated masts and shown only near them.</p>
    </div>
    <div class="sheet" id="sheet" data-state="peek">
      <button class="sheet-grip" type="button" id="grip" aria-label="Expand or collapse panel"></button>
      <div class="sheet-tabs" role="tablist" aria-label="Map panels" style="grid-template-columns:repeat(3,1fr)">
        <button role="tab" type="button" data-pane="status" aria-selected="true">Status</button>
        <button role="tab" type="button" data-pane="setup" aria-selected="false">Field &amp; plan</button>
        <button type="button" data-explain="hold" data-field="${esc(fp.id)}" id="sheet-explain">Explain</button>
      </div>
      <div class="sheet-body">
        <section class="right pane active" data-pane="status" id="pane-status" aria-label="Field status"><div class="side-sec"><div class="skeleton" style="height:220px"></div></div></section>
        <section class="left pane" data-pane="setup" id="pane-setup" aria-label="Field, equipment and schedule"></section>
      </div>
    </div>
  </div>`;
  renderSetup();
  bindChrome();
  initMap();
  state.mapCtl = { apply: applyUi, renderSim, inject: injectCritical };
  V.unsub = on((what) => {
    if (what === 'lang') refreshAll();
    if (what === 'theme') applyTheme();
    if (what === 'reset') { stopPlay(true); hideAlert(); V.rec = null; refreshAll(true); }
  });
  emit('mapstate');
  refreshAll(true);
}

function teardown() {
  if (!V) return;
  stopPlay();
  stopOrbit();
  V.unsub?.();
  V.windFx?.stop();
  V.markers.forEach((m) => m.remove());
  V.vehicleMk?.remove(); V.vehLabel?.remove();
  try { V.map?.remove(); } catch {}
  V = null;
  state.mapCtl = null;
  emit('mapstate');
}
export const leaveMap = teardown;

// ------------------------------------------------------------- chrome
function bindChrome() {
  const mv = V.root.querySelector('#mv');
  mv.addEventListener('click', (e) => {
    const t = e.target;
    const tab = t.closest('.sheet-tabs [data-pane]'); if (tab) return setPane(tab.dataset.pane);
    if (t.closest('#legend-toggle')) {
      const open = V.root.querySelector('#legend').classList.toggle('open');
      V.root.querySelector('#legend-toggle').setAttribute('aria-expanded', String(open));
    }
    if (t.closest('[data-pill-play]')) { V.play?.running ? pausePlay() : startPlay(); }
    if (t.closest('[data-pill-stop]')) stopPlay(true);
  });
  const grip = V.root.querySelector('#grip');
  let y0 = null;
  grip.addEventListener('pointerdown', (e) => { y0 = e.clientY; grip.setPointerCapture(e.pointerId); });
  grip.addEventListener('pointerup', (e) => {
    const dy = y0 == null ? 0 : e.clientY - y0; y0 = null;
    const order = ['peek', 'half', 'full'];
    let i = order.indexOf(V.sheet);
    if (Math.abs(dy) < 8) i = (i + 1) % 3; else i = Math.max(0, Math.min(2, i + (dy < 0 ? 1 : -1)));
    setSheet(order[i]);
  });
  document.addEventListener('click', closePickerOutside, true);
}
function closePickerOutside(e) {
  if (V?.pickerOpen && !e.target.closest('.picker')) { V.pickerOpen = false; renderSetup(); }
}
function setSheet(s) { V.sheet = s; V.root.querySelector('#sheet').dataset.state = s; }
function setPane(p) {
  V.pane = p;
  V.root.querySelectorAll('.sheet-tabs [data-pane]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.pane === p)));
  V.root.querySelectorAll('.sheet-body .pane').forEach((s) => s.classList.toggle('active', s.dataset.pane === p));
  if (V.sheet === 'peek') setSheet('half');
}

// Apply a view setting coming from the prototype drawer.
function applyUi(key) {
  if (!V) return;
  if (key === 'view') return applyView();
  if (key === 'is3d') return set3d(UI().is3d);
  if (key === 'basemap') return setBase(UI().basemap);
  if (key === 'wind') { V.windFx?.reseed(); renderLegend(); return; }
  if (key === 'lighting') { applyTheme(); if (V.play?.pos) setVehicle(V.play.pos); return; }
  if (key === 'exaggeration') { if (UI().is3d) { try { V.map.setTerrain({ source: 'dem', exaggeration: UI().exaggeration }); } catch {} } updateMapChip(); return; }
  if (key === 'terrainColor' || key === 'contours') { updateTerrainLayers(); renderLegend(); return; }
  if (key === 'liveStations' || key === 'liveModel') { updateLiveLayers(); renderLegend(); return; }
  if (key === 'terrainSite') return flyTerrainSite();
  updateMapData(); renderLegend();
}

// -------------------------------------------------------------- data
let refreshSeq = 0;
async function refreshAll(first = false) {
  if (!V) return;
  const seq = ++refreshSeq;
  const fid = state.selectedField;
  const job = state.jobs.find((j) => j.field_id === fid && j.status === 'open');
  try {
    if (!state.plan) await loadPlan();
    if (!state.photos) state.photos = await api('/api/photos').catch(() => ({ credits: {}, fields: {}, equipment: {} }));
    if (!V.terrainStats) V.terrainStats = await api('/api/terrain/fields').catch(() => ({}));
    const recP = (!V.rec || V.rec.field_id !== fid) ? api('/api/recommend?field_id=' + fid).catch(() => null) : null;
    const [all, a] = await Promise.all([
      api('/api/assess/all?time=' + encodeURIComponent(state.time)),
      api(`/api/assess?field_id=${fid}&time=${encodeURIComponent(state.time)}`),
    ]);
    if (!V || seq !== refreshSeq) return;
    V.all = all; V.assess = a;
    if (first || !V.ev || V.ev.field !== fid) await evaluateEquipment(job, first);
    renderStatus();
    renderHud();
    if (recP) { const rec = await recP; if (V && rec) { V.rec = rec; if (first || !job) { /* keep job's unit */ } } }
    if (V && !V.pickerOpen) renderSetup();
    updateMapData();
    renderLegend();
    renderTimeMeta();
    applyTheme();
  } catch (e) {
    if (!V) return;
    V.root.querySelector('#pane-status').innerHTML = `<div class="side-sec">${stateBox('error', 'Conditions could not load', e.message + ' Status is unknown, so treat this field as not assessed.')}</div>`;
    V.root.querySelector('#hud').innerHTML = `<div class="cell status-cell">${chip('INSUFFICIENT_DATA')}<span class="small">Server unreachable</span></div>`;
  }
}

async function evaluateEquipment(job, first) {
  const fid = state.selectedField;
  if (first || !V.unitId || (V.ev && V.ev.field !== fid)) {
    V.unitId = job?.unit_id || V.rec?.recommended_unit || (fieldProps(fid).crop_class === 'orchard' ? 'U2' : 'U1');
    V.cfgOverride = { ...(job?.config_override || {}) };
    V.orientation = job?.orientation_deg || 0;
  }
  try {
    const ev = await api('/api/equipment/evaluate', { method: 'POST', body: {
      field_id: fid, unit_id: V.unitId, config: V.cfgOverride, product_id: job?.product_id, orientation_deg: V.orientation, time: state.time } });
    if (!V) return;
    ev.field = fid;
    V.ev = ev;
  } catch (e) { V.ev = null; toast(e.message, true); }
  renderSetup();
  updatePaths();
}

// ------------------------------------------------------------ panels
function releaseFt() {
  if (!V.ev) return null;
  const c = V.ev.config;
  if (V.ev.unit.type === 'drone') return c.height_m * 3.281;
  if (c.boom_height_in != null) return c.boom_height_in / 12;
  return null;
}
function renderStatus() {
  const fp = fieldProps(state.selectedField);
  V.root.querySelector('#pane-status').innerHTML = statusPanel(V.assess, fp, releaseFt(), V.live && V.live.field === fp.id ? V.live : null,
    V.obs && V.obs.field === fp.id ? V.obs : null);
  V.root.querySelector('[data-load-live]')?.addEventListener('click', loadLive);
  V.root.querySelector('[data-obs-form]')?.addEventListener('submit', submitObservation);
  if (!V.obs || V.obs.field !== fp.id) loadObservations(fp.id);
  V.root.querySelector('#sheet-explain').dataset.field = fp.id;
}
async function loadObservations(fid) {
  V.obs = { field: fid, meta: V.obsMeta || null, list: null };
  try {
    const o = await api('/api/observations?field_id=' + encodeURIComponent(fid));
    if (!V || state.selectedField !== fid) return;
    V.obsMeta = { items: o.items, rules: o.rules };
    V.obs = { field: fid, meta: V.obsMeta, list: o.observations };
  } catch (e) { if (V) V.obs = { field: fid, meta: null, list: [] }; }
  if (V) renderStatus();
}
async function submitObservation(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.currentTarget), fid = state.selectedField;
  const items = {};
  for (const k of Object.keys(V.obsMeta.items)) items[k] = fd.get(k);
  const btn = ev.currentTarget.querySelector('button[type=submit]'); btn.disabled = true;
  try {
    await api('/api/observations', { method: 'POST', body: { field_id: fid, time: state.time, observer: fd.get('observer'), notes: fd.get('notes'), items } });
    toast('Observation recorded. It can add caution; it never clears a measured flag.');
    V.obs = null;
    await refreshAll();
  } catch (e) { toast(e.message, true); btn.disabled = false; }
}
async function loadLive() {
  const fid = state.selectedField;
  V.live = { status: 'loading', field: fid }; renderStatus();
  try {
    const e = await api('/api/live/estimate?field_id=' + fid);
    if (!V) return;
    V.live = { ...e, field: fid, status: e.status || 'experimental' };
  } catch (err) { if (V) V.live = { status: 'error', message: err.message, field: fid }; }
  if (V) renderStatus();
}

const hh = (lv, wind) => {
  if (!lv) return '';
  const h = wind ? (lv.wind_height_ft ?? lv.height_ft) : lv.height_ft;
  return h == null ? '' : h < 2 ? `${Math.round(h * 12)} in` : `${(+h).toFixed(h < 10 ? 1 : 0).replace('.0', '')} ft`;
};
const hudPair = (rd) => (rd ? `${hh(rd.upper)} − ${hh(rd.lower)}${rd.lower.ref === 'canopy' ? ' (canopy)' : ''}` : 'Upper − lower');

function renderHud() {
  const a = V.assess, fp = fieldProps(state.selectedField), m = a.metrics, rd = a.reading;
  const dT = m.delta_t_f, u = m.delta_t_uncertainty_f;
  const dCls = dT == null ? '' : dT > u ? 'warn' : dT > 0 ? 'mid' : 'ok';
  const w = (r) => (r && r.wind_mph != null ? `${r.wind_mph.toFixed(1)}<small>mph ${compass(r.dir_from_deg)}</small>` : '—');
  const wCls = (r) => (r && r.wind_mph != null ? (r.wind_mph < 3 || r.wind_mph > 10 ? 'warn' : 'ok') : '');
  V.root.querySelector('#hud').innerHTML = `
    <div class="cell status-cell">${chip(a.status, 'lg')}<div><div class="k">Selected</div><div class="small" style="font-weight:600">${esc(fp.name)}</div><div class="xs muted" title="Versioned decision ID">${esc(a.decision_id || '')}</div></div></div>
    <div class="cell"><div class="k">${esc(hudPair(rd))}</div><div class="v ${dCls}">${dT != null ? (dT > 0 ? '+' : '') + dT.toFixed(1) : '—'}<small>°F</small></div></div>
    <div class="cell"><div class="k">Wind ${esc(hh(rd?.lower, true))}</div><div class="v ${wCls(rd?.lower)}">${w(rd?.lower)}</div></div>
    ${rd?.upper?.wind_installed === false ? '' : `<div class="cell"><div class="k">Wind ${esc(hh(rd?.upper, true))}</div><div class="v">${w(rd?.upper)}</div></div>`}
    <div class="cell opt"><div class="k">Rain chance</div><div class="v">${rd?.rain_prob_pct != null ? rd.rain_prob_pct.toFixed(0) : '—'}<small>%</small></div></div>
    <div class="cell opt"><div class="k">${state.time > state.meta.scenario.now ? 'Sim. forecast' : 'Sim. observation'}</div><div class="v">${hm(a.time)}<small>MST</small></div></div>`;
}

function photoFor(fid) {
  const key = state.photos?.fields?.[fid];
  return key ? { src: state.photos.credits[key].file, credit: state.photos.credits[key] } : null;
}
function equipPhoto(type) {
  const key = state.photos?.equipment?.[type];
  if (key) return { src: state.photos.credits[key].file, credit: state.photos.credits[key], photo: true };
  return { src: state.catalog.equipment_types[type]?.illustration || 'img/boom.svg', photo: false };
}
const creditLine = (c, extra = '') => c ? `<p class="credit">Representative photo${extra}: “${esc(c.title.replace(/\.(jpe?g|png)$/i, ''))}” by ${esc(c.artist || 'unknown')}, <a href="${esc(c.license_url || c.source)}" target="_blank" rel="noopener">${esc(c.license)}</a>, via <a href="${esc(c.source)}" target="_blank" rel="noopener">Wikimedia Commons</a>${c.modified ? ` (${esc(c.modified.toLowerCase())})` : ''}.</p>` : '';

function optionState(o, rec) {
  if (!o.compatible) return ['no', 'Blocked'];
  if (!o.scheduled) return ['no', 'No window'];
  if (rec && o.unit_id === rec.recommended_unit) return ['rec', 'Recommended'];
  return ['ok', 'Candidate'];
}

function renderSetup() {
  if (!V) return;
  const fid = state.selectedField, fp = fieldProps(fid);
  const job = state.jobs.find((j) => j.field_id === fid && j.status === 'open');
  const statuses = Object.fromEntries((V.all?.fields || []).map((f) => [f.field_id, f.status]));
  const ph = photoFor(fid);
  const rec = V.rec && V.rec.field_id === fid ? V.rec : null;
  const recOpt = rec?.options.find((o) => o.unit_id === rec.recommended_unit);
  const selOpt = rec?.options.find((o) => o.unit_id === V.unitId);
  const el = V.root.querySelector('#pane-setup');
  const fieldOpt = (p, tag) => {
    const pph = photoFor(p.id);
    return `<${tag} class="${tag === 'li' ? 'picker-opt' : ''}" ${tag === 'li' ? `role="option" data-pick="${esc(p.id)}" aria-selected="${p.id === fid}" tabindex="-1"` : ''}>
      ${pph ? `<img src="${esc(pph.src)}" alt="">` : '<span></span>'}
      <span><span class="n">${esc(p.name)}</span><br><span class="c">${esc(p.crop)} · ${p.acres} ac</span></span>
      ${statuses[p.id] ? chip(statuses[p.id]) : ''}</${tag}>`;
  };
  const ep = (type) => equipPhoto(type);
  const recBlock = () => {
    if (!job) return `<div class="state"><h3>No open request</h3><p>This field has no treatment request, so no equipment is recommended.</p></div>`;
    if (!rec) return '<div class="skeleton" style="height:300px"></div>';
    const o = recOpt || rec.options[0];
    const img = ep(o.type);
    const e = o.estimate || {};
    return `<div class="rec-card">
      <div class="rec-img"><img src="${esc(img.src)}" alt="${esc(o.unit_name)}">
        <span class="badge ${recOpt ? '' : 'no'}">${recOpt ? 'Recommended' : 'No option fits'}</span>
        ${img.photo ? '' : '<span class="illus">Illustration · no licensed photo available</span>'}</div>
      <div class="rec-body"><div class="name">${esc(o.unit_name)}</div>
        <div class="xs muted">${esc(state.catalog.equipment_types[o.type].name)} · ${esc(o.crew)}</div>
        <p class="why">${esc(recOpt ? o.why : rec.message)}</p>
        ${e.total_min ? `<div class="metrics">
          <div class="metric"><div class="k">Job time</div><div class="v">${dur(e.total_min)}</div></div>
          <div class="metric"><div class="k">Spraying</div><div class="v">${dur(e.spray_min)}</div></div>
          <div class="metric"><div class="k">${o.type === 'drone' ? 'Refill + battery' : 'Refills'}</div><div class="v">${e.loads - 1}<small>stops · ${dur(e.reload_min)}</small></div></div>
          <div class="metric"><div class="k">Swath · speed</div><div class="v">${e.swath_m}<small>m · ${e.speed_m_s} m/s</small></div></div>
        </div>` : ''}
        ${recOpt ? valueBlock(rec, recOpt) : ''}
      </div></div>
      ${img.photo ? creditLine(img.credit, ', not the unit in this plan') : ''}`;
  };
  const schedBlock = () => {
    if (!rec || !selOpt) return '';
    const o = selOpt;
    if (!o.compatible || !o.scheduled) {
      return `<div class="sched-card"><div class="k">With ${esc(o.unit_name)}</div><div class="big" style="font-size:1.4rem;color:var(--stop)">No suitable window</div>
        <p class="sub">${esc(o.compatible ? 'No suitable window found before the requested deadline - review with your PCA.' : 'This equipment has a blocking conflict for this job.')}</p>
        <p class="sub">${esc(o.why)}</p></div>`;
    }
    const sc = o.schedule;
    const margin = minutesBetween(sc.end, job.latest_completion);
    const rh = state.catalog.products[job.product_id]?.constraints.rainfast_h.value;
    const total = (sc.travel_min + sc.setup_min) + minutesBetween(sc.start, sc.end) + (rh ? rh * 60 : 0);
    const pct = (m) => `${(m / total * 100).toFixed(1)}%`;
    const isCurrent = job.unit_id === o.unit_id;
    return `<div class="sched-card">
      <div class="k">With ${esc(o.unit_name)} · ${esc(when(sc.start).split(' ')[0])}</div>
      <div class="big">${hm(sc.start)} – ${hm(sc.end)}</div>
      <p class="sub">Depart ${hm(sc.depart)} · ${sc.travel_min} min travel · ${sc.setup_min} min setup${sc.wait_min > 0 ? ` · waits ${dur(sc.wait_min)} for conditions` : ''}</p>
      <div class="timeline-mini" aria-hidden="true">
        <span style="width:${pct(sc.travel_min + sc.setup_min)};background:repeating-linear-gradient(135deg,rgba(91,227,165,.35) 0 4px,transparent 4px 8px)"></span>
        <span style="width:${pct(minutesBetween(sc.start, sc.end))};background:var(--brand)"></span>
        ${rh ? `<span style="width:${pct(rh * 60)};background:rgba(124,196,255,.45)"></span>` : ''}</div>
      <div class="steps">
        <div><span>Deadline</span><b>${when(job.latest_completion)} · ${margin >= 0 ? dur(margin) + ' margin' : 'missed'}</b></div>
        <div><span>Rain-free after last pass</span><b>${sc.rain_ok == null ? 'Check incomplete' : sc.rain_ok ? (rh ? rh + ' h clear' : 'OK') : 'Conflict'}</b></div>
        <div><span>Other jobs still scheduled</span><b>${o.others_scheduled} of ${o.others_total}</b></div>
        <div><span>Plan order</span><b>${esc(o.plan_order.join(' → '))}</b></div>
      </div>
      <div class="btn-row" style="margin-top:16px">
        ${isCurrent ? `<button class="btn sm" type="button" disabled>In the current plan</button>` : `<button class="btn primary" type="button" id="apply-eq">Use this equipment and replan</button>`}
        <button class="btn sm ghost" type="button" data-explain="rain" data-field="${esc(fid)}">${icon('rain', 'sm')}Rain question</button></div>
      <p class="xs muted demo-note" style="margin-top:10px">Conditional estimate from simulated data. Take fresh local readings before starting.</p></div>`;
  };
  el.innerHTML = `
    <div class="side-sec">
      <div class="sec-title"><h2>Field</h2><span class="xs muted">${state.fields.fields.features.length} fields<span class="demo-note"> · fictional</span></span></div>
      <div class="picker">
        <button type="button" class="picker-btn" id="picker-btn" aria-haspopup="listbox" aria-expanded="${V.pickerOpen}" aria-controls="picker-list">
          ${ph ? `<img src="${esc(ph.src)}" alt="">` : '<span></span>'}
          <span><span class="n">${esc(fp.name)}</span> ${statuses[fid] ? chip(statuses[fid]) : ''}<br><span class="c">${esc(fp.crop)} · ${fp.acres} ac</span></span>
          <svg class="ic chev" aria-hidden="true"><use href="#i-chev"/></svg></button>
        ${V.pickerOpen ? `<ul class="picker-list" id="picker-list" role="listbox" aria-label="Fields">${state.fields.fields.features.map((f) => fieldOpt(f.properties, 'li')).join('')}</ul>` : ''}
      </div>
      ${ph ? `<div class="photo-card"><img src="${esc(ph.src)}" alt="${esc(fp.crop)} crop, representative photo">
        <div class="photo-rec"><span>Representative photo</span>${statuses[fid] ? `<span>${esc(statusText(statuses[fid]))}</span>` : ''}</div>
        <div class="photo-cap"><div class="crop">Crop in field</div><div class="cn">${esc(fp.crop)}</div>
          <div class="meta">${fp.acres} ac · ${esc(fp.grower)}</div></div></div>${creditLine(ph.credit, ', not this field')}` : ''}
    </div>
    <div class="side-sec">
      <div class="sec-title"><h2>Recommended equipment</h2>${job ? `<button class="btn sm ghost" type="button" data-explain="equipment" data-field="${esc(fid)}">Why?</button>` : ''}</div>
      ${recBlock()}
      ${rec ? `<details class="fold" style="margin-top:14px" ${V.compareOpen ? 'open' : ''} id="compare-fold"><summary>Compare other equipment</summary>
      <div class="opts" role="radiogroup" aria-label="Available equipment" style="margin-top:4px">${rec.options.map((o) => {
        const [cls, txt] = optionState(o, rec); const img = ep(o.type);
        return `<button type="button" class="opt" role="radio" aria-checked="${o.unit_id === V.unitId}" data-unit="${esc(o.unit_id)}">
          <span class="thumb"><img src="${esc(img.src)}" alt=""></span>
          <span><span class="n">${esc(o.unit_name)}</span><br><span class="c">${o.estimate?.total_min ? dur(o.estimate.total_min) + ' job · ' : ''}${esc(o.crew)}</span></span>
          <span class="opt-state ${cls}">${txt}</span></button>`;
      }).join('')}
      <button type="button" class="opt" data-unsupported="aircraft" aria-disabled="true"><span class="thumb"><img src="${esc(ep('aircraft').src)}" alt=""></span>
        <span><span class="n">Aircraft</span><br><span class="c">Optional extension</span></span><span class="opt-state no">Not supported</span></button></div></details>` : ''}
    </div>
    ${rec && selOpt ? `<div class="side-sec"><div class="sec-title"><h2>Recommended schedule</h2></div>${schedBlock()}</div>` : ''}
    ${liquidCard(job, V.ev, job && planFor(job.id))}
    ${terrainCard(V.terrainStats?.[fid], V.profiles[fid])}
    <div class="side-sec">
      ${V.ev?.unit?.type === 'ground_boom' || V.ev?.nozzle_engine ? `<details class="fold" ${V.nozzleOpen ? 'open' : ''} id="nozzle-fold"><summary>${V.ev?.nozzle_engine?.status === 'not_modelled' ? `Nozzles · not sized for ${esc((V.ev.nozzle_engine.equipment || 'this rig').toLowerCase())}` : `Nozzle candidates (TeeJet tables)${(() => { const n = V.ev?.nozzle_engine?.candidates?.length || 0; return n > 4 ? ` · top 4 of ${n}` : n ? ` · ${n}` : ''; })()}`}</summary>${nozzleCards(V.ev)}</details>` : ''}
      <details class="fold"><summary>Advanced equipment configuration</summary>
        ${equipmentPanel(V.ev, state.catalog, V.unitId, { noCards: true })}
        <div class="field" style="margin-top:12px"><label for="orient">Pass orientation · ${V.orientation}° (0 = north–south)</label>
          <input id="orient" type="range" min="0" max="175" step="5" value="${V.orientation}"></div></details>
      <details class="fold" ${V.draw ? 'open' : ''}><summary>Mark a sensitive area or exclusion</summary>
        <div class="form-grid" style="grid-template-columns:1fr;margin-top:4px">
          <div class="field"><label for="draw-kind">Type</label><select id="draw-kind">
            ${Object.entries(KIND_LABEL).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}
            <option value="exclusion">Exclusion inside ${esc(fp.name)}</option></select></div>
          <div class="field"><label for="draw-name">Name</label><input id="draw-name" type="text" placeholder="e.g. School bus stop"></div>
          <label class="check"><input type="checkbox" id="draw-hold"> Hold application while air moves toward it (user-entered)</label></div>
        <div class="btn-row" style="margin-top:12px">${V.draw
          ? `<button class="btn sm primary" type="button" id="draw-finish" ${V.draw.pts.length < 3 ? 'disabled' : ''}>Finish (${V.draw.pts.length} points)</button><button class="btn sm" type="button" id="draw-cancel">Cancel</button>`
          : `<button class="btn sm" type="button" id="draw-start">${icon('plus', 'sm')}Start marking on map</button>`}</div>
        ${V.draw ? '<p class="xs" style="margin-top:8px;color:var(--brand)">Click or tap the map to add corners. At least 3.</p>' : ''}
        ${userAreasList()}</details>
    </div>`;
  bindSetup(el, job);
}
function valueBlock(rec, o) {
  const e = o.economics; if (!e) return '';
  const money = (v) => `$${Math.abs(v).toLocaleString('en-US')}`;
  const rows = rec.savings.map((sv) => {
    const faster = sv.minutes_saved, cheaper = sv.usd_saved;
    const t = faster === 0 ? 'same time' : `${dur(Math.abs(faster))} ${faster > 0 ? 'faster' : 'slower'}`;
    const c = cheaper === 0 ? 'same cost' : `${money(cheaper)} ${cheaper > 0 ? 'less' : 'more'}`;
    return `<li class="${sv.reference_only ? 'ref' : ''}"><span class="vs">vs ${esc(sv.unit_name)}</span>
      <span class="gain ${faster > 0 || cheaper > 0 ? 'up' : ''}">${t} · ${c}${sv.crew_hours_saved > 0 ? ` · ${sv.crew_hours_saved} crew-h saved` : ''}</span>
      ${sv.reference_only ? `<span class="refnote">${esc(sv.note)}</span>` : ''}</li>`;
  }).join('');
  const cb = rec.cost_basis;
  return `<div class="value">
    <h3>Why it saves time and money</h3>
    <div class="value-grid">
      <div><div class="k">Time on site</div><div class="v">${dur(e.on_site_min)}</div><div class="s">${e.travel_min} travel · ${e.setup_min} setup · ${dur(e.job_min)} job</div></div>
      <div><div class="k">Estimated cost</div><div class="v">${money(e.total_usd)}</div><div class="s">${money(e.usd_per_acre ?? 0)}/ac · ${e.crew_hours} crew-h</div></div>
      <div><div class="k">Work rate</div><div class="v">${e.acres_per_hour}<small> ac/h</small></div><div class="s">${e.treated_acres} ac treated</div></div>
      <div><div class="k">Spraying share</div><div class="v">${e.spray_share_pct}<small>%</small></div><div class="s">of job time is spraying</div></div>
    </div>
    ${rows ? `<ul class="value-vs">${rows}</ul>` : '<p class="s">No other available unit can do this job, so there is nothing to compare against.</p>'}
    ${rec.sequencing ? `<p class="value-seq">${icon('schedule', 'sm')}<span>${esc(rec.sequencing)}</span></p>` : ''}
    <p class="value-basis">Cost = crew × hours on site × $${cb.labor_usd_per_person_h}/person-h + machine hours × $${cb.machine_usd_per_h[o.unit_id]}/h. ${esc(cb.source)}. Times come from the planned path, turns, refills, travel and setup.</p>
  </div>`;
}

function userAreasList() {
  const ua = [...state.fields.sensitive.features.filter((f) => f.properties.user_added), ...state.fields.exclusions.features.filter((f) => f.properties.id !== 'X1')];
  return ua.length ? `<ul class="rows" style="margin-top:10px">${ua.map((f) => `<li>${icon('flag', 'sm')}<div class="small">${esc(f.properties.name)}</div>
    <button class="btn sm ghost" type="button" data-del-area="${esc(f.properties.id)}">Remove</button></li>`).join('')}</ul>` : '';
}

function bindSetup(el, job) {
  el.querySelector('#compare-fold')?.addEventListener('toggle', (e) => { V.compareOpen = e.target.open; });
  el.querySelector('#nozzle-fold')?.addEventListener('toggle', (e) => { V.nozzleOpen = e.target.open; });
  el.querySelector('[data-load-profile]')?.addEventListener('click', async () => {
    const seg = V.ev?.path?.segments.find((x) => x.type === 'spray');
    if (!seg) return toast('No pass to profile.', true);
    try { V.profiles[state.selectedField] = await api('/api/terrain/profile', { method: 'POST', body: { coords: seg.coords } }); renderSetup(); }
    catch (e) { toast('Terrain profile unavailable: ' + e.message, true); }
  });
  const pbtn = el.querySelector('#picker-btn');
  pbtn.onclick = () => { V.pickerOpen = !V.pickerOpen; renderSetup(); if (V.pickerOpen) el.querySelector('.picker-opt[aria-selected="true"]')?.focus(); };
  pbtn.onkeydown = (e) => { if (e.key === 'ArrowDown') { e.preventDefault(); V.pickerOpen = true; renderSetup(); el.querySelector('.picker-opt')?.focus(); } };
  const opts = [...el.querySelectorAll('.picker-opt')];
  opts.forEach((o, i) => {
    o.onclick = () => { V.pickerOpen = false; selectField(o.dataset.pick); };
    o.onkeydown = (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); opts[Math.min(opts.length - 1, i + 1)].focus(); }
      if (e.key === 'ArrowUp') { e.preventDefault(); opts[Math.max(0, i - 1)].focus(); }
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); o.click(); }
      if (e.key === 'Escape') { V.pickerOpen = false; renderSetup(); el.querySelector('#picker-btn').focus(); }
    };
  });
  el.querySelectorAll('[data-unit]').forEach((b) => (b.onclick = () => selectUnit(b.dataset.unit)));
  el.querySelector('[data-unsupported]')?.addEventListener('click', () => toast(state.catalog.equipment_types.aircraft.unsupported, true));
  el.querySelectorAll('[data-cfg]').forEach((inp) => inp.addEventListener('change', () => {
    const k = inp.dataset.cfg; let v = inp.value;
    if (inp.type === 'number') v = v === '' ? null : Number(v);
    if (v === '' && k === 'droplet_class_entered') v = null;
    V.cfgOverride[k] = v;
    evaluateEquipment(job);
  }));
  el.querySelector('#orient')?.addEventListener('change', (e) => { V.orientation = Number(e.target.value); evaluateEquipment(job); });
  el.querySelector('#apply-eq')?.addEventListener('click', async () => {
    try {
      await api('/api/equipment/evaluate', { method: 'POST', body: { field_id: job.field_id, unit_id: V.unitId, config: V.cfgOverride, product_id: job.product_id, orientation_deg: V.orientation, record: true, job_id: job.id } });
      await api('/api/jobs', { method: 'POST', body: { ...job, unit_id: V.unitId, config_override: V.cfgOverride, orientation_deg: V.orientation } });
      await loadPlan(true, `equipment changed for ${job.id}`);
      const r = planFor(job.id);
      toast(r?.scheduled ? `Replanned: ${job.id} ${when(r.start)}–${hm(r.end)}.` : `Replanned: ${job.id} has no suitable window with this equipment.`, !r?.scheduled);
      V.rec = null;
      refreshAll();
    } catch (e) { toast(e.message, true); }
  });
  el.querySelector('#draw-start')?.addEventListener('click', () => { V.draw = { pts: [] }; renderSetup(); drawUpdate(); if (isMobile()) setSheet('peek'); });
  el.querySelector('#draw-cancel')?.addEventListener('click', () => { V.draw = null; renderSetup(); drawUpdate(); });
  el.querySelector('#draw-finish')?.addEventListener('click', finishDraw);
  el.querySelectorAll('[data-del-area]').forEach((b) => b.onclick = async () => {
    try { await api('/api/areas/' + b.dataset.delArea, { method: 'DELETE' }); await reloadFields(); toast('Area removed and recorded.'); } catch (e) { toast(e.message, true); }
  });
}

async function finishDraw() {
  const kind = V.root.querySelector('#draw-kind').value;
  const body = { coordinates: V.draw.pts, name: V.root.querySelector('#draw-name').value, hold_when_toward: V.root.querySelector('#draw-hold').checked };
  if (kind === 'exclusion') Object.assign(body, { type: 'exclusion', field_id: state.selectedField });
  else Object.assign(body, { type: 'sensitive', kind });
  try {
    await api('/api/areas', { method: 'POST', body });
    V.draw = null;
    await reloadFields();
    await loadPlan(true, 'area marked');
    toast('Area saved and recorded. Assessment and plan updated.');
  } catch (e) { toast(e.message, true); }
}
async function reloadFields() {
  state.fields = await api('/api/fields');
  if (!V) return;
  V.ev = null;
  drawUpdate();
  await refreshAll(false);
  const job = state.jobs.find((j) => j.field_id === state.selectedField && j.status === 'open');
  await evaluateEquipment(job);
}

function selectUnit(uid) {
  if (uid === V.unitId) return;
  V.unitId = uid; V.cfgOverride = {};
  stopPlay(true);
  evaluateEquipment(state.jobs.find((j) => j.field_id === state.selectedField && j.status === 'open'));
}

function selectField(fid) {
  if (fid === state.selectedField) return;
  stopPlay(true);
  state.selectedField = fid;
  history.replaceState(null, '', '#/map?field=' + fid);
  V.ev = null;
  refreshAll(true);
  flyToField(fid, false);
}
function flyToField(fid, intro) {
  const f = state.fields.fields.features.find((x) => x.properties.id === fid);
  if (!V?.map || !f) return;
  if (UI().view === 'pov') return povCamera(true);
  const opts = { center: f.properties.centroid, zoom: isMobile() ? 14.9 : 15.35, pitch: UI().is3d ? 56 : 0, bearing: UI().is3d ? -24 : 0,
    padding: isMobile() ? { top: 60, bottom: 140, left: 0, right: 0 } : { left: 380, right: 400, top: 60, bottom: 40 } };
  if (reduceMotion) V.map.jumpTo(opts); else V.map.flyTo({ ...opts, duration: intro ? 3400 : 1500, curve: 1.3, essential: true });
  if (UI().view === 'orbit') setTimeout(startOrbit, intro ? 3500 : 1600);
}

// ---------------------------------------------------- camera view modes
function applyView() {
  stopOrbit();
  const pill = V.root.querySelector('#view-pill');
  const v = UI().view;
  pill.hidden = v === 'overview';
  pill.textContent = v === 'pov' ? demoText('Operator POV · simulated view from the planned path') : 'Orbit · drag the map to stop';
  if (v === 'overview') { flyToField(state.selectedField, false); }
  if (v === 'pov') { if (!UI().is3d) { UI().is3d = true; set3d(true); } povCamera(true); toast('Operator POV. Start the replay from Prototype controls to ride along.'); }
  if (v === 'orbit') flyToField(state.selectedField, false);
  emit('mapstate');
}
function povTarget() {
  if (V.play?.cur && V.play.pos) return { pos: V.play.pos, brg: V.vehBrg || 0 };
  const seg = V.ev?.path?.segments.find((s) => s.type === 'spray');
  if (!seg) return null;
  const [a, b] = [seg.coords[0], seg.coords[seg.coords.length - 1]];
  const dx = (b[0] - a[0]) * 111320 * Math.cos(a[1] * Math.PI / 180), dy = (b[1] - a[1]) * 110540;
  return { pos: a, brg: (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360 };
}
function povCamera(animate) {
  if (!V?.map) return;
  const t = povTarget(); if (!t) return;
  // ease the bearing so headland turns do not whip the camera around
  const prev = V.povBrg == null ? t.brg : V.povBrg;
  const d = ((t.brg - prev + 540) % 360) - 180;
  V.povBrg = animate ? t.brg : (prev + d * 0.08 + 360) % 360;
  const h = V.map.getContainer().clientHeight;
  const opts = { center: t.pos, zoom: 17.6, pitch: 76, bearing: V.povBrg, padding: { top: 0, bottom: Math.round(h * 0.42), left: 0, right: 0 } };
  if (animate && !reduceMotion) V.map.flyTo({ ...opts, duration: 2200, essential: true }); else V.map.jumpTo(opts);
}
function startOrbit() {
  if (!V?.map || UI().view !== 'orbit') return;
  if (reduceMotion) { toast('Orbit is paused because reduced motion is on.'); return; }
  stopOrbit();
  let last = performance.now();
  const step = (now) => {
    if (!V?.map || UI().view !== 'orbit') return;
    V.map.setBearing(V.map.getBearing() + (now - last) * 0.006); last = now;
    V.orbitRaf = requestAnimationFrame(step);
  };
  V.orbitRaf = requestAnimationFrame(step);
  const stop = () => { stopOrbit(); V?.map?.off('mousedown', stop); V?.map?.off('touchstart', stop); };
  V.map.once('mousedown', stop); V.map.once('touchstart', stop);
}
function stopOrbit() { if (V?.orbitRaf) { cancelAnimationFrame(V.orbitRaf); V.orbitRaf = null; } }

// ------------------------------------------- simulation controls (drawer)
function renderSim(slot) {
  if (!V || !slot) return;
  const d0 = state.meta.scenario.day0, now = state.meta.scenario.now;
  const nowIdx = Math.round((new Date(now) - new Date(d0)) / 900000);
  const idx = Math.round((new Date(state.time) - new Date(d0)) / 900000);
  const { job, r } = jobAndPlan();
  slot.innerHTML = `
    <div class="field" style="margin-top:0"><label for="tslider">Conditions at <span id="tlabel"></span></label>
      <div class="time-track" aria-hidden="true">${Array.from({ length: 48 }, (_, i) => `<span class="${i * 4 <= nowIdx ? 'obs' : 'fc'}"></span>`).join('')}</div>
      <input id="tslider" type="range" min="0" max="${SLOTS - 1}" step="1" value="${idx}">
      <div class="time-meta"><span>Today 00:00</span><span>${document.body.classList.contains('hide-labels') ? 'Observed' : 'Simulated'} to ${hm(now)}, forecast after</span><span>Tomorrow 24:00</span></div></div>
    <div class="btn-row" style="margin-top:10px"><button class="btn sm" type="button" id="pb-now">${icon('clock', 'sm')}Back to scenario now</button></div>
    <div style="margin-top:20px">
      <div class="label" style="margin-bottom:8px">Application replay · ${esc(job ? `${job.id} on ${fieldProps(job.field_id).name}` : 'no request on this field')}${r?.scheduled ? ` · planned ${hm(r.start)}–${hm(r.end)}` : ''}</div>
      <div class="big-play">
        <button class="icon-btn play" type="button" id="pb-play" aria-label="${V.play?.running ? 'Pause' : 'Play'} application replay">${icon(V.play?.running ? 'pause' : 'play')}</button>
        <button class="icon-btn" type="button" id="pb-reset" aria-label="Reset replay">${icon('reset')}</button>
        <label class="sr" for="pb-speed">Replay speed</label>
        <select id="pb-speed" style="width:auto">${[2, 5, 15].map((v) => `<option value="${v}" ${v === V.speed ? 'selected' : ''}>${v} min / s</option>`).join('')}</select>
      </div>
      <input id="pb-scrub" type="range" min="0" max="1000" value="${Math.round((V.play?.frac || 0) * 1000)}" aria-label="Scrub application progress" style="margin-top:10px">
      <div class="prog" id="pb-prog" aria-live="polite"></div></div>`;
  const s = slot.querySelector('#tslider');
  let tmr;
  s.addEventListener('input', () => {
    stopPlay(true);
    state.time = addMin(d0, Number(s.value) * 15);
    renderTimeMeta();
    clearTimeout(tmr); tmr = setTimeout(() => { emit('time'); refreshAll(); }, 120);
  });
  slot.querySelector('#pb-now').onclick = () => { stopPlay(true); state.time = now; renderTimeMeta(); refreshAll(); };
  slot.querySelector('#pb-play').onclick = () => (V.play?.running ? pausePlay() : startPlay());
  slot.querySelector('#pb-reset').onclick = () => stopPlay(true);
  slot.querySelector('#pb-speed').onchange = (e) => { V.speed = Number(e.target.value); if (V.play?.running) { pausePlay(); startPlay(); } };
  slot.querySelector('#pb-scrub').addEventListener('input', (e) => { pausePlay(); seekPlay(Number(e.target.value) / 1000, true); });
  renderTimeMeta();
}
function renderTimeMeta() {
  if (!V) return;
  const lab = document.getElementById('tlabel');
  if (lab) lab.innerHTML = `${when(state.time)} MST <span class="tag sim">${state.time > state.meta.scenario.now ? 'Simulated forecast' : 'Simulated observation'}</span>`;
  const s = document.getElementById('tslider');
  if (s) s.value = Math.round((new Date(state.time) - new Date(state.meta.scenario.day0)) / 900000);
  updatePlayLabel();
}

// ------------------------------------------------------------- playback
function jobAndPlan() {
  const job = state.jobs.find((j) => j.field_id === state.selectedField && j.status === 'open');
  return { job, r: job && planFor(job.id) };
}
function buildTimeline() {
  // Distribute the job duration over spray/turn/transit segments; insert the
  // configured refill/battery pauses at equal spray-volume intervals.
  const ev = V.ev; if (!ev?.path) return null;
  const est = ev.estimate, segs = ev.path.segments;
  const sp = est.speed_m_s, turnS = ev.config.turn_s || 30;
  const sprayTotal = segs.filter((s) => s.type === 'spray').reduce((a, s) => a + s.length_m, 0);
  const pauses = [];
  for (let k = 1; k < est.loads; k++) pauses.push(sprayTotal * k / est.loads);
  const perLoad = (est.reload_min * 60) / Math.max(1, est.loads - 1);
  let acc = 0, t = 0, pi = 0; const tl = [];
  segs.forEach((s, i) => {
    const sec = s.type === 'turn' ? turnS : s.length_m / sp;
    if (s.type === 'spray' && pi < pauses.length && acc + s.length_m >= pauses[pi]) {
      const frac = (pauses[pi] - acc) / s.length_m;
      tl.push({ i, s, t0: t, t1: t + sec * frac, f0: 0, f1: frac }); t += sec * frac;
      tl.push({ i, s, pause: true, t0: t, t1: t + perLoad, f0: frac, f1: frac }); t += perLoad;
      tl.push({ i, s, t0: t, t1: t + sec * (1 - frac), f0: frac, f1: 1 }); t += sec * (1 - frac);
      pi++;
    } else { tl.push({ i, s, t0: t, t1: t + sec, f0: 0, f1: 1 }); t += sec; }
    if (s.type === 'spray') acc += s.length_m;
  });
  const total = ev.estimate.total_min * 60, k = total / t;
  tl.forEach((x) => { x.t0 *= k; x.t1 *= k; });
  return { tl, total };
}
const lerp = (a, b, f) => [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
function posAt(seg, f) {
  const c = seg.coords; if (c.length === 2) return lerp(c[0], c[1], f);
  const n = c.length - 1, x = Math.min(n - 1e-9, f * n), i = Math.floor(x);
  return lerp(c[i], c[i + 1], x - i);
}
function seekPlay(frac, fromScrub = false) {
  const { r } = jobAndPlan();
  if (!V.ev?.path) return;
  if (!V.play) V.play = { running: false, frac: 0, lastSlot: null, tl: buildTimeline() };
  V.play.frac = Math.max(0, Math.min(1, frac));
  const { tl, total } = V.play.tl;
  const tsec = V.play.frac * total;
  const cur = tl.find((x) => tsec >= x.t0 && tsec <= x.t1) || tl[tl.length - 1];
  const f = cur.pause ? cur.f0 : cur.f0 + (cur.f1 - cur.f0) * ((tsec - cur.t0) / Math.max(1e-6, cur.t1 - cur.t0));
  V.play.cur = { segIndex: cur.i, f, pause: !!cur.pause, pass: cur.s.pass, type: cur.s.type };
  updatePaths();
  const pos = posAt(cur.s, f), prev = posAt(cur.s, Math.max(0, f - 0.02));
  setVehicle(pos, prev);
  V.play.pos = pos;
  if (UI().view === 'pov') povCamera(false);
  const sc = document.getElementById('pb-scrub'); if (sc && !fromScrub) sc.value = Math.round(V.play.frac * 1000);
  if (r?.scheduled) { state.time = addMin(r.start, Math.floor(tsec / 60)); renderTimeMeta(); }
  updatePlayLabel();
}
function updatePlayLabel() {
  if (!V) return;
  const { job, r } = jobAndPlan();
  const p = V.play;
  let txt;
  if (!V.ev?.path) txt = 'No path for this configuration.';
  else if (!p) txt = r?.scheduled ? `Ready: ${job.id} planned ${hm(r.start)}–${hm(r.end)}.` : `${job ? job.id : 'No request'} is not scheduled; replay shows passes only.`;
  else {
    const what = p.cur?.pause ? (V.ev.unit.type === 'drone' ? 'refill + battery swap' : 'refilling') : p.cur?.type === 'spray' ? `pass ${p.cur.pass + 1} of ${V.ev.path.passes}` : p.cur?.type === 'turn' ? 'turning' : 'non-spray move';
    txt = `${Math.round(p.frac * 100)}% · ${what}${p.halted ? ' · paused by alert' : ''}`;
  }
  const el = document.getElementById('pb-prog'); if (el) el.textContent = txt;
  const pill = V.root.querySelector('#replay-pill');
  if (!pill) return;
  pill.hidden = !p;
  if (p) pill.innerHTML = `<button type="button" class="icon-btn" data-pill-play aria-label="${p.running ? 'Pause' : 'Resume'} replay">${icon(p.running ? 'pause' : 'play')}</button>
    <span><b>${esc(job?.id || '')}</b> ${esc(txt)}</span><span class="bar"><span style="width:${(p.frac * 100).toFixed(1)}%"></span></span>
    <span class="muted">${hm(state.time)} MST<span class="demo-note"> · simulated</span></span>
    <button type="button" class="icon-btn" data-pill-stop aria-label="Stop replay">${icon('close')}</button>`;
}
function startPlay() {
  if (!V.ev?.path) return;
  if (!V.play || V.play.frac >= 1) { V.play = null; seekPlay(0); }
  V.play.running = true; V.play.halted = false;
  hideAlert();
  const btn = document.getElementById('pb-play'); if (btn) { btn.innerHTML = icon('pause'); btn.setAttribute('aria-label', 'Pause application replay'); }
  const speed = V.speed;
  let last = performance.now();
  const total = V.play.tl.total;
  const step = (now) => {
    if (!V?.play?.running) return;
    const dt = Math.min(0.25, (now - last) / 1000); last = now;
    seekPlay(Math.min(1, V.play.frac + (dt * speed * 60) / total));
    monitorTick();
    if (V.play.frac >= 1) { pausePlay(); toast('Replay finished. All planned passes shown as completed.'); return; }
    V.play.raf = requestAnimationFrame(step);
  };
  V.play.raf = requestAnimationFrame(step);
}
function pausePlay() {
  if (!V?.play) return;
  V.play.running = false;
  cancelAnimationFrame(V.play.raf);
  const btn = document.getElementById('pb-play'); if (btn) { btn.innerHTML = icon('play'); btn.setAttribute('aria-label', 'Play application replay'); }
  updatePlayLabel();
}
function stopPlay(clear) {
  pausePlay();
  if (clear && V) { V.play = null; const sc = document.getElementById('pb-scrub'); if (sc) sc.value = 0; updatePaths(); setVehicle(null); updatePlayLabel(); }
}
async function monitorTick() {
  const { job, r } = jobAndPlan();
  if (!job || !r?.scheduled) return;
  const slot = state.time.slice(0, 14) + String(Math.floor(+state.time.slice(14, 16) / 15) * 15).padStart(2, '0');
  if (slot === V.play.lastSlot) return;
  V.play.lastSlot = slot;
  try {
    const m = await api('/api/monitor', { method: 'POST', body: { job_id: job.id, time: state.time, pass_index: V.play.cur?.pass } });
    if (!V?.play) return;
    refreshAll(); // keep HUD, panel, map and wind bound to the replay time
    if (m.critical) {
      pausePlay();
      V.play.halted = true;
      updatePaths(); seekPlay(V.play.frac);
      if (m.alert) showAlert(m.alert, () => refreshAll());
      toast(`${statusText(m.status)}: simulated vehicle paused on pass ${(V.play.cur?.pass ?? 0) + 1}. ${m.instruction}`, true);
      refreshAll();
    }
  } catch (e) { pausePlay(); toast('Monitoring unavailable: ' + e.message + ' Replay paused.', true); }
}
async function injectCritical() {
  const fp = fieldProps(state.selectedField);
  if (!fp.sensor_id) { toast('This field has no sensor to change.', true); return; }
  const at = addMin(state.time, 15);
  try {
    await api('/api/scenario/inject', { method: 'POST', body: { field_id: fp.id, time: at } });
    toast(`Simulated wind surge scheduled at ${fp.name} from ${when(at)} for 60 min.`);
  } catch (e) { toast(e.message, true); }
}

// ================================================================ MAP
function webglOK() {
  try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; }
}
const empty = () => ({ type: 'FeatureCollection', features: [] });

function initMap() {
  const el = V.root.querySelector('#map');
  if (!window.maplibregl || !webglOK()) { V.fallback = true; renderFallback(); return; }
  const f = state.fields.fields.features.find((x) => x.properties.id === state.selectedField);
  let map;
  try {
    map = new maplibregl.Map({
      container: el, center: [f.properties.centroid[0] + 0.01, f.properties.centroid[1] - 0.01], zoom: 12.4, pitch: UI().is3d ? 20 : 0, bearing: 0, maxPitch: 78,
      attributionControl: { compact: true }, fadeDuration: 250,
      style: {
        version: 8,
        sources: {
          imagery: { type: 'raster', tileSize: 256, maxzoom: 19, tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
            attribution: 'Imagery © Esri, Maxar, Earthstar Geographics' },
          streets: { type: 'raster', tileSize: 256, tiles: ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png', 'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'],
            attribution: '© OpenStreetMap contributors © CARTO' },
          'streets-light': { type: 'raster', tileSize: 256, tiles: ['https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png', 'https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'],
            attribution: '© OpenStreetMap contributors © CARTO' },
          dem: { type: 'raster-dem', encoding: 'terrarium', tileSize: 256, maxzoom: 14, tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
            attribution: 'Terrain: AWS Terrain Tiles' },
          hs: { type: 'raster-dem', encoding: 'terrarium', tileSize: 256, maxzoom: 14, tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'] },
        },
        layers: [
          { id: 'bg', type: 'background', paint: { 'background-color': '#0A100D' } },
          { id: 'imagery', type: 'raster', source: 'imagery', paint: { 'raster-saturation': -0.25, 'raster-brightness-max': 0.72, 'raster-contrast': 0.12 } },
          { id: 'streets', type: 'raster', source: 'streets', layout: { visibility: 'none' } },
          { id: 'streets-light', type: 'raster', source: 'streets-light', layout: { visibility: 'none' } },
          { id: 'hillshade', type: 'hillshade', source: 'hs', paint: { 'hillshade-exaggeration': 0.35, 'hillshade-shadow-color': '#000', 'hillshade-highlight-color': 'rgba(255,255,255,.15)' } },
        ],
      },
    });
  } catch { V.fallback = true; renderFallback(); return; }
  V.map = map;
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
  map.on('error', (e) => {
    if (e?.sourceId === 'imagery' || e?.sourceId === 'streets') noteTiles();
  });
  map.on('load', () => {
    if (!V) return;
    applyTheme();
    if (UI().is3d) { try { map.setTerrain({ source: 'dem', exaggeration: UI().exaggeration || 1 }); } catch {} }
    addPatterns(map);
    for (const id of ['fields', 'areas', 'excl', 'paths', 'active', 'masts', 'draw']) map.addSource(id, { type: 'geojson', data: empty() });
    const blank = document.createElement('canvas'); blank.width = blank.height = 2;
    map.addSource('thermal', { type: 'image', url: blank.toDataURL(), coordinates: [[-114.75, 32.68], [-114.68, 32.68], [-114.68, 32.64], [-114.75, 32.64]] });
    map.addLayer({ id: 'thermal', type: 'raster', source: 'thermal', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.46, 'raster-resampling': 'linear', 'raster-fade-duration': 300 } });
    map.addLayer({ id: 'areas-3d', type: 'fill-extrusion', source: 'areas', paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['case', ['get', 'att'], 5, 2], 'fill-extrusion-opacity': 0.5 } });
    map.addLayer({ id: 'areas-line', type: 'line', source: 'areas', paint: { 'line-color': ['get', 'color'], 'line-width': ['case', ['get', 'att'], 2.5, 1.2], 'line-opacity': 0.9 } });
    map.addLayer({ id: 'fields-hit', type: 'fill', source: 'fields', paint: { 'fill-color': '#000', 'fill-opacity': 0.01 } });
    map.addLayer({ id: 'fields-sel', type: 'fill', source: 'fields', filter: ['get', 'sel'], paint: { 'fill-color': ['get', 'fill'], 'fill-opacity': 0.28 } });
    map.addLayer({ id: 'fields-3d', type: 'fill-extrusion', source: 'fields', filter: ['!', ['get', 'sel']], paint: {
      'fill-extrusion-color': ['get', 'fill'], 'fill-extrusion-height': ['get', 'h'], 'fill-extrusion-base': 0,
      'fill-extrusion-opacity': 0.62, 'fill-extrusion-vertical-gradient': true } });
    map.addLayer({ id: 'fields-hatch', type: 'fill', source: 'fields', filter: ['==', ['get', 'hatch'], true], paint: { 'fill-pattern': 'hatch', 'fill-opacity': 0.7 } });
    map.addLayer({ id: 'fields-glow', type: 'line', source: 'fields', paint: { 'line-color': ['get', 'edge'], 'line-width': ['case', ['get', 'sel'], 14, 6], 'line-blur': ['case', ['get', 'sel'], 10, 5], 'line-opacity': ['case', ['get', 'sel'], 0.65, 0.3] } });
    map.addLayer({ id: 'fields-line', type: 'line', source: 'fields', paint: { 'line-color': ['case', ['get', 'sel'], '#FFFFFF', ['get', 'edge']], 'line-width': ['case', ['get', 'sel'], 2.2, 1.2] } });
    map.addLayer({ id: 'excl-fill', type: 'fill', source: 'excl', paint: { 'fill-pattern': 'hatch-red' } });
    map.addLayer({ id: 'excl-line', type: 'line', source: 'excl', paint: { 'line-color': '#FF6B5E', 'line-width': 1.5 } });
    map.addLayer({ id: 'pass-todo', type: 'line', source: 'paths', filter: ['all', ['==', ['get', 'type'], 'spray'], ['!', ['get', 'done']]], paint: { 'line-color': '#FFFFFF', 'line-width': 1.2, 'line-opacity': 0.55, 'line-dasharray': [2, 2] } });
    map.addLayer({ id: 'pass-done-glow', type: 'line', source: 'paths', filter: ['all', ['==', ['get', 'type'], 'spray'], ['get', 'done']], paint: { 'line-color': '#5BE3A5', 'line-width': 7, 'line-blur': 5, 'line-opacity': 0.55 } });
    map.addLayer({ id: 'pass-done', type: 'line', source: 'paths', filter: ['all', ['==', ['get', 'type'], 'spray'], ['get', 'done']], paint: { 'line-color': '#B8FFDD', 'line-width': 2.2 } });
    map.addLayer({ id: 'pass-turn', type: 'line', source: 'paths', filter: ['==', ['get', 'type'], 'turn'], paint: { 'line-color': '#FFFFFF', 'line-width': 0.8, 'line-opacity': 0.35 } });
    map.addLayer({ id: 'pass-transit', type: 'line', source: 'paths', filter: ['==', ['get', 'type'], 'transit'], paint: { 'line-color': '#F5B83D', 'line-width': 1.4, 'line-dasharray': [0.6, 1.6] } });
    map.addLayer({ id: 'pass-active', type: 'fill', source: 'active', paint: { 'fill-color': ['case', ['get', 'halted'], '#FF6B5E', '#FFD166'], 'fill-opacity': 0.5 } });
    map.addLayer({ id: 'pass-active-edge', type: 'line', source: 'active', paint: { 'line-color': ['case', ['get', 'halted'], '#FFB4AB', '#FFF1C2'], 'line-width': 1.4 } });
    map.addLayer({ id: 'masts-3d', type: 'fill-extrusion', source: 'masts', paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['get', 'top'], 'fill-extrusion-base': ['get', 'base'], 'fill-extrusion-opacity': 0.95 } });
    map.addLayer({ id: 'draw-line', type: 'line', source: 'draw', paint: { 'line-color': '#FFD166', 'line-width': 2.5 } });
    map.addLayer({ id: 'draw-pt', type: 'circle', source: 'draw', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-radius': 6, 'circle-color': '#FFD166', 'circle-stroke-color': '#0A100D', 'circle-stroke-width': 2 } });
    map.on('click', 'fields-hit', (e) => { if (!V.draw) selectField(e.features[0].properties.id); });
    map.on('click', async (e) => {
      if (V.draw) { V.draw.pts.push([e.lngLat.lng, e.lngLat.lat]); drawUpdate(); renderSetup(); return; }
      if (e.originalEvent?.target?.closest?.('.maplibregl-marker')) return;
      const pop = new maplibregl.Popup({ closeButton: true, className: 'elev-pop' }).setLngLat(e.lngLat).setHTML('<div class="small">Elevation…</div>').addTo(map);
      try {
        const r = await api(`/api/terrain/point?lon=${e.lngLat.lng.toFixed(6)}&lat=${e.lngLat.lat.toFixed(6)}`);
        pop.setHTML(r.elevation_m == null ? `<div class="small">Elevation unavailable here.</div>`
          : `<div class="small"><b>${r.elevation_m} m</b> (${r.elevation_ft} ft) ${esc(r.vertical_datum)}<br><span class="xs">${esc(r.source)}</span><br><span class="xs">${esc(r.method)}</span>${UI().exaggeration > 1 ? `<br><span class="xs">Display exaggerated ×${UI().exaggeration}; value is true elevation.</span>` : ''}</div>`);
      } catch (err) { pop.setHTML('<div class="small">Elevation unavailable.</div>'); }
    });
    map.on('mouseenter', 'fields-hit', () => { map.getCanvas().style.cursor = V.draw ? 'crosshair' : 'pointer'; });
    map.on('mouseleave', 'fields-hit', () => { map.getCanvas().style.cursor = V.draw ? 'crosshair' : ''; });
    updateMapData();
    updatePaths();
    addTerrainLayers(map);
    V.windFx = windParticles(map, V.root.querySelector('#wind-canvas'));
    flyToField(state.selectedField, true);
    if (UI().view !== 'overview') setTimeout(applyView, 600);
  });
}
function noteTiles() {
  const n = V?.root.querySelector('#map-note');
  if (n && !n.dataset.tiles) { n.dataset.tiles = 1; n.innerHTML += ' <b>Basemap tiles unavailable</b>: overlays shown on a plain background.'; }
}
function addPatterns(map) {
  const mk = (stroke, bg) => {
    const c = document.createElement('canvas'); c.width = c.height = 12; const g = c.getContext('2d');
    g.fillStyle = bg; g.fillRect(0, 0, 12, 12); g.strokeStyle = stroke; g.lineWidth = 2;
    g.beginPath(); g.moveTo(0, 12); g.lineTo(12, 0); g.moveTo(-3, 3); g.lineTo(3, -3); g.moveTo(9, 15); g.lineTo(15, 9); g.stroke();
    return g.getImageData(0, 0, 12, 12);
  };
  map.addImage('hatch', mk('rgba(200,210,218,.75)', 'rgba(60,70,78,.35)'));
  map.addImage('hatch-red', mk('rgba(255,107,94,.85)', 'rgba(80,20,16,.35)'));
}

function fieldFeatures() {
  const by = Object.fromEntries((V.all?.fields || []).map((f) => [f.field_id, f]));
  return state.fields.fields.features.map((f) => {
    const a = by[f.properties.id];
    const sel = f.properties.id === state.selectedField;
    let fill = '#2A3A33', hatch = false, edge = '#DDE7E1';
    if (a && UI().colorBy === 'status') { fill = STATUS_COLOR[a.status]; edge = fill; hatch = a.status === 'INSUFFICIENT_DATA'; }
    if (a && UI().colorBy === 'inversion') {
      const d = a.metrics.delta_t_f;
      if (d == null) { hatch = true; fill = '#5B6670'; } else { fill = d > a.metrics.delta_t_uncertainty_f ? '#FF6B5E' : d > 0 ? '#F5B83D' : '#43B4E0'; }
      edge = fill;
    }
    if (UI().colorBy === 'none') { fill = 'rgba(0,0,0,0)'; }
    return { ...f, properties: { ...f.properties, fill, edge, hatch, sel, h: UI().colorBy === 'none' ? 0 : 6 } };
  });
}

function mastFeatures() {
  // Each mast: a thin column plus two rings at 5 ft and 30 ft colored by measured temperature.
  const feats = [];
  const tColor = (t) => (t == null ? '#5B6670' : t < 50 ? '#43B4E0' : t < 56 ? '#7FD3E8' : t < 62 ? '#BDEBD3' : t < 68 ? '#F6D57A' : t < 74 ? '#F59A4A' : '#E5484D');
  for (const s of state.fields.sensors.features) {
    const [lon, lat] = s.geometry.coordinates;
    const r = V.all?.sensors.find((x) => x.id === s.properties.id)?.reading;
    const sq = (m) => {
      const dLon = m / (111320 * Math.cos(lat * Math.PI / 180)), dLat = m / 110540;
      return [[[lon - dLon, lat - dLat], [lon + dLon, lat - dLat], [lon + dLon, lat + dLat], [lon - dLon, lat + dLat], [lon - dLon, lat - dLat]]];
    };
    const ft = 0.3048 * MAST_EXAG;
    feats.push({ type: 'Feature', geometry: { type: 'Polygon', coordinates: sq(1.6) }, properties: { base: 0, top: 33 * ft, color: '#E8EEF0' } });
    feats.push({ type: 'Feature', geometry: { type: 'Polygon', coordinates: sq(4.5) }, properties: { base: 4 * ft, top: 6 * ft, color: tColor(r?.lower.temp_f) } });
    feats.push({ type: 'Feature', geometry: { type: 'Polygon', coordinates: sq(4.5) }, properties: { base: 29 * ft, top: 31 * ft, color: tColor(r?.upper.temp_f) } });
  }
  return { type: 'FeatureCollection', features: feats };
}

function updateMapData() {
  if (!V) return;
  if (V.fallback) { renderFallback(); return; }
  const map = V.map; if (!map?.getSource('fields')) return;
  map.getSource('fields').setData({ type: 'FeatureCollection', features: fieldFeatures() });
  const nb = Object.fromEntries((V.assess?.neighbors || []).map((n) => [n.area_id, n]));
  map.getSource('areas').setData({ type: 'FeatureCollection', features: UI().showAreas ? state.fields.sensitive.features.map((f) => ({
    ...f, properties: { ...f.properties, color: KIND_COLOR[f.properties.kind] || '#999', att: !!nb[f.properties.id]?.attention } })) : [] });
  map.getSource('excl').setData({ type: 'FeatureCollection', features: UI().showAreas ? state.fields.exclusions.features : [] });
  updateThermal();
  map.getSource('masts').setData(mastFeatures());
  ['pass-todo', 'pass-done', 'pass-done-glow', 'pass-turn', 'pass-transit'].forEach((l) => map.setLayoutProperty(l, 'visibility', UI().showPasses ? 'visible' : 'none'));
  renderMarkers();
}

const sensorReading = (id) => V.all?.sensors.find((s) => s.id === id)?.reading;

// Ironbow-style palette, as used by thermal cameras.
const IRON = [[0, [10, 6, 30]], [0.2, [62, 15, 112]], [0.4, [150, 30, 120]], [0.6, [222, 73, 80]], [0.8, [254, 159, 70]], [1, [252, 240, 170]]];
function ironbow(t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < IRON.length; i++) {
    if (t <= IRON[i][0]) {
      const [a0, c0] = IRON[i - 1], [a1, c1] = IRON[i], f = (t - a0) / (a1 - a0);
      return c0.map((v, k) => Math.round(v + (c1[k] - v) * f));
    }
  }
  return IRON[IRON.length - 1][1];
}
function thermalImage() {
  // Inverse-distance interpolation of the selected height between the simulated masts.
  // Beyond 1.2 km from every mast the pixel is transparent (unassessed).
  const sens = state.fields.sensors.features.map((f) => ({ c: f.geometry.coordinates, r: sensorReading(f.properties.id) }))
    .filter((x) => x.r && x.r[UI().thermalHeight].temp_f != null);
  if (!sens.length) return null;
  const lons = sens.map((x) => x.c[0]), lats = sens.map((x) => x.c[1]);
  const x0 = Math.min(...lons) - 0.016, x1 = Math.max(...lons) + 0.016, y0 = Math.min(...lats) - 0.014, y1 = Math.max(...lats) + 0.014;
  const W = 220, H = Math.round(W * ((y1 - y0) * 110540) / ((x1 - x0) * 93700));
  const vals = sens.map((x) => x.r[UI().thermalHeight].temp_f);
  const lo = Math.min(...vals) - 1.5, hi = Math.max(...vals) + 1.5;
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
  const g = cv.getContext('2d'), img = g.createImageData(W, H);
  const mLon = 111320 * Math.cos(32.66 * Math.PI / 180), mLat = 110540;
  for (let j = 0; j < H; j++) for (let i = 0; i < W; i++) {
    const lon = x0 + (i + 0.5) / W * (x1 - x0), lat = y1 - (j + 0.5) / H * (y1 - y0);
    let ws = 0, vs = 0, dmin = Infinity;
    for (const x of sens) {
      const d = Math.hypot((lon - x.c[0]) * mLon, (lat - x.c[1]) * mLat); dmin = Math.min(dmin, d);
      const w = 1 / Math.max(30, d) ** 2; ws += w; vs += w * x.r[UI().thermalHeight].temp_f;
    }
    const k = (j * W + i) * 4;
    const alpha = Math.max(0, Math.min(1, (1200 - dmin) / 250));
    const [r, gg, b] = ironbow(((vs / ws) - lo) / (hi - lo));
    img.data[k] = r; img.data[k + 1] = gg; img.data[k + 2] = b; img.data[k + 3] = Math.round(alpha * 205);
  }
  g.putImageData(img, 0, 0);
  V.thermalRange = [lo + 1.5, hi - 1.5];
  return { url: cv.toDataURL(), coordinates: [[x0, y1], [x1, y1], [x1, y0], [x0, y0]] };
}
function updateThermal() {
  const map = V?.map; if (!map?.getLayer('thermal')) return;
  if (!UI().thermal) { map.setLayoutProperty('thermal', 'visibility', 'none'); return; }
  const im = thermalImage(); if (!im) return;
  map.getSource('thermal').updateImage(im);
  map.setLayoutProperty('thermal', 'visibility', 'visible');
}

function renderMarkers() {
  V.markers.forEach((m) => m.remove()); V.markers = [];
  const map = V.map; if (!map) return;
  const by = Object.fromEntries((V.all?.fields || []).map((f) => [f.field_id, f]));
  const add = (el, ll, anchor = 'center', offset = [0, 0]) => { const m = new maplibregl.Marker({ element: el, anchor, offset }).setLngLat(ll).addTo(map); V.markers.push(m); return m; };
  for (const f of state.fields.fields.features) {
    const p = f.properties, a = by[p.id];
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'mk-field' + (p.id === state.selectedField ? ' sel' : '');
    el.setAttribute('aria-label', `${p.name}, ${p.crop}, ${a ? statusText(a.status) : 'loading'}`);
    const c = a ? STATUS_COLOR[a.status] : '#888';
    el.innerHTML = `<span class="dot" style="background:${c};box-shadow:0 0 12px ${c}"></span><span><b>${esc(p.name)}</b> <span class="muted">${esc(p.crop)}</span></span>${a ? `<span class="st" style="color:${c}">${esc(statusText(a.status))}</span>` : ''}`;
    el.onclick = (e) => { e.stopPropagation(); if (!V.draw) selectField(p.id); };
    add(el, p.centroid, 'bottom', [0, -6]);
  }
  for (const s of state.fields.sensors.features) {
    const r = sensorReading(s.properties.id);
    if (!r) continue;
    const dT = r.upper.temp_f != null && r.lower.temp_f != null ? +(r.upper.temp_f - r.lower.temp_f).toFixed(1) : null;
    const el = document.createElement('div');
    el.className = 'mk-mast';
    const fmt = (v, u) => (v == null ? '<span style="color:var(--stop)">missing</span>' : v.toFixed(1) + u);
    el.innerHTML = `<b>${esc(s.properties.id)} · paired mast</b>
      <div class="r"><span>${esc(hh(r.upper))}</span><span>${fmt(r.upper.temp_f, '°')}${r.upper.wind_installed === false ? '' : ' · ' + fmt(r.upper.wind_mph, ' mph')}</span></div>
      <div class="r"><span>${esc(hh(r.lower))}</span><span>${fmt(r.lower.temp_f, '°')}${r.lower.wind_installed === false ? '' : ' · ' + fmt(r.lower.wind_mph, ' mph') + (r.lower.wind_height_ft !== r.lower.height_ft ? ' @ ' + esc(hh(r.lower, true)) : '')}</span></div>
      <div class="xs" style="opacity:.75">${r.lower.ref === 'canopy' ? 'Heights above canopy' : 'Heights above ground'}</div>
      <div class="dt" style="color:${dT == null ? 'var(--nodata)' : dT > 0.7 ? 'var(--stop)' : dT > 0 ? 'var(--caution)' : 'var(--go)'}">ΔT ${dT == null ? '—' : (dT > 0 ? '+' : '') + dT + ' °F'}${dT > 0.7 ? ' · inversion' : ''}</div>`;
    add(el, s.geometry.coordinates, 'bottom', [0, -54]);
    if (UI().thermal) {
      const t = document.createElement('div'); t.className = 'mk-temp';
      const v = r[UI().thermalHeight].temp_f; t.textContent = v != null ? `${v.toFixed(1)} °F @ ${UI().thermalHeight === 'lower' ? 5 : 30} ft` : 'missing';
      add(t, s.geometry.coordinates, 'top', [0, 12]);
    }
  }
  if (UI().showAreas) {
    const nb = Object.fromEntries((V.assess?.neighbors || []).map((n) => [n.area_id, n]));
    for (const f of state.fields.sensitive.features) {
      const ring = f.geometry.coordinates[0].slice(0, -1);
      const c = [ring.reduce((a, p) => a + p[0], 0) / ring.length, ring.reduce((a, p) => a + p[1], 0) / ring.length];
      const n = nb[f.properties.id];
      const el = document.createElement('div');
      el.className = 'mk-area' + (n?.blocking ? ' blk' : n?.attention ? ' att' : '');
      el.textContent = `${KIND_LABEL[f.properties.kind]}${n?.blocking ? ' · hold' : n?.attention ? ' · attention' : ''}`;
      el.title = f.properties.name;
      add(el, f.properties.kind === 'road' ? [c[0] + 0.004, c[1]] : c);
    }
  }
}

function updatePaths() {
  if (!V) return;
  if (V.fallback) { renderFallback(); return; }
  const map = V.map; if (!map?.getSource('paths')) return;
  const segs = V.ev?.path?.segments || [];
  const cur = V.play?.cur;
  map.getSource('paths').setData({ type: 'FeatureCollection', features: segs.map((s, i) => ({ type: 'Feature', geometry: { type: 'LineString', coordinates: s.coords },
    properties: { type: s.type, done: !!(V.play && cur && (i < cur.segIndex || (i === cur.segIndex && cur.f >= 0.999))) } })) });
  const active = V.play && cur && cur.type === 'spray' ? segs.filter((s) => s.type === 'spray' && s.pass === cur.pass) : [];
  // Active pass drawn as its swath-width strip (a draped polygon), not a wide glowing line.
  const half = (V.ev?.estimate?.swath_m || 10) / 2;
  const strip = (c) => {
    const [a, b] = [c[0], c[c.length - 1]];
    const mLon = 111320 * Math.cos(a[1] * Math.PI / 180), mLat = 110540;
    const dx = (b[0] - a[0]) * mLon, dy = (b[1] - a[1]) * mLat, L = Math.hypot(dx, dy) || 1;
    const nx = (-dy / L) * half, ny = (dx / L) * half;
    const off = (p, k) => [p[0] + (k * nx) / mLon, p[1] + (k * ny) / mLat];
    return [[off(a, 1), off(b, 1), off(b, -1), off(a, -1), off(a, 1)]];
  };
  map.getSource('active').setData({ type: 'FeatureCollection', features: active.map((s) => ({ type: 'Feature', geometry: { type: 'Polygon', coordinates: strip(s.coords) }, properties: { halted: !!V.play?.halted } })) });
  if (!V.play) setVehicle(null);
}

function setVehicle(pos, prev) {
  if (V.fallback) { V.fbVehicle = pos; renderFallback(); return; }
  if (!V.map) return;
  if (!pos) { V.vehicleMk?.remove(); V.vehLabel?.remove(); V.vehicleMk = V.vehLabel = null; return; }
  const drone = V.ev?.unit.type === 'drone';
  const halted = !!V.play?.halted;
  // compass heading from metric deltas
  let brg = V.vehBrg || 0;
  if (prev && (prev[0] !== pos[0] || prev[1] !== pos[1])) {
    const dx = (pos[0] - prev[0]) * 111320 * Math.cos(pos[1] * Math.PI / 180), dy = (pos[1] - prev[1]) * 110540;
    brg = V.vehBrg = (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360;
  }
  const col = halted ? '#FF6B5E' : '#FFD166';
  if (!V.vehicleMk || V.vehicleMk._drone !== drone) {
    V.vehicleMk?.remove(); V.vehLabel?.remove();
    const el = document.createElement('div');
    el.style.cssText = 'width:56px;height:56px;pointer-events:none;filter:drop-shadow(0 6px 10px rgba(0,0,0,.6))';
    V.vehicleMk = new maplibregl.Marker({ element: el, rotationAlignment: 'map', pitchAlignment: 'map' }).setLngLat(pos).addTo(V.map);
    V.vehicleMk._drone = drone;
    const lab = document.createElement('div'); lab.className = 'mk-vehicle';
    V.vehLabel = new maplibregl.Marker({ element: lab, anchor: 'bottom', offset: [0, -30] }).setLngLat(pos).addTo(V.map);
  }
  const el = V.vehicleMk.getElement();
  const beam = V.night && !drone ? `<defs><radialGradient id="hl" cx="0" cy="-10" r="60" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#FFF4C2" stop-opacity=".85"/><stop offset="1" stop-color="#FFF4C2" stop-opacity="0"/></radialGradient></defs><path d="M-8 -14 L-34 -78 L34 -78 L8 -14 Z" fill="url(#hl)"/>` : '';
  el.style.width = el.style.height = V.night && !drone ? '160px' : '56px';
  el.innerHTML = drone
    ? `<svg viewBox="-28 -28 56 56" width="56" height="56"><circle r="22" fill="none" stroke="${col}" stroke-opacity=".35" stroke-width="2" stroke-dasharray="3 4"/>
        <g stroke="#EEF3EF" stroke-width="3" stroke-linecap="round"><line x1="-15" y1="-15" x2="15" y2="15"/><line x1="15" y1="-15" x2="-15" y2="15"/></g>
        ${[[-15, -15], [15, -15], [15, 15], [-15, 15]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="7" fill="rgba(238,243,239,.18)" stroke="#EEF3EF" stroke-width="1.5"/>`).join('')}
        <rect x="-6" y="-8" width="12" height="16" rx="4" fill="${col}"/><path d="M0 -14 L4 -9 H-4 Z" fill="${col}"/></svg>`
    : `<svg viewBox="${V.night ? '-80 -80 160 160' : '-28 -28 56 56'}" width="${V.night ? 160 : 56}" height="${V.night ? 160 : 56}">${beam}<rect x="-27" y="9" width="54" height="4" rx="2" fill="#EEF3EF"/>
        <rect x="-8" y="-16" width="16" height="26" rx="4" fill="${col}"/><rect x="-6" y="-14" width="12" height="8" rx="2" fill="#0A100D" opacity=".55"/>
        <rect x="-12" y="-12" width="4" height="9" rx="1.5" fill="#0A100D"/><rect x="8" y="-12" width="4" height="9" rx="1.5" fill="#0A100D"/>
        <rect x="-13" y="2" width="5" height="10" rx="1.5" fill="#0A100D"/><rect x="8" y="2" width="5" height="10" rx="1.5" fill="#0A100D"/></svg>`;
  V.vehicleMk.setLngLat(pos).setRotation(brg);
  V.vehLabel.setLngLat(pos);
  const lab = V.vehLabel.getElement();
  lab.classList.add('mk-vehicle'); lab.classList.toggle('halt', halted); // keep MapLibre's own marker classes
  lab.textContent = demoText(halted ? 'Paused · simulated' : `${drone ? `Drone · ${V.ev.config.height_m} m AGL` : V.ev.unit.name.split(' - ')[0]} · simulated`);
}

function drawUpdate() {
  const src = V?.map?.getSource('draw'); if (!src) return;
  if (!V.draw) { src.setData(empty()); V.map.getCanvas().style.cursor = ''; return; }
  V.map.getCanvas().style.cursor = 'crosshair';
  const pts = V.draw.pts;
  src.setData({ type: 'FeatureCollection', features: [
    ...pts.map((p) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: p } })),
    ...(pts.length > 1 ? [{ type: 'Feature', geometry: { type: 'LineString', coordinates: [...pts, ...(pts.length > 2 ? [pts[0]] : [])] } }] : []),
  ] });
}

function set3d(on3d) {
  UI().is3d = on3d;
  if (V.fallback) { toast('3D needs WebGL, which is unavailable here. Showing the 2D schematic.', true); return; }
  const map = V.map;
  if (on3d) { try { map.setTerrain({ source: 'dem', exaggeration: UI().exaggeration || 1 }); } catch {} }
  else map.setTerrain(null);
  map.easeTo({ pitch: on3d ? 56 : 0, bearing: on3d ? -24 : 0, duration: reduceMotion ? 0 : 1100 });
  renderLegend();
}
function setBase(b) {
  UI().basemap = b;
  if (!V.map) return;
  const day = !V.night;
  V.map.setLayoutProperty('imagery', 'visibility', b === 'imagery' ? 'visible' : 'none');
  V.map.setLayoutProperty('streets', 'visibility', b === 'streets' && !day ? 'visible' : 'none');
  V.map.setLayoutProperty('streets-light', 'visibility', b === 'streets' && day ? 'visible' : 'none');
}
export function sceneIsNight() {
  const mode = UI().lighting || 'auto';
  if (mode !== 'auto') return mode === 'night';
  const c = state.fields?.fields.features[0]?.properties.centroid || [-114.72, 32.66];
  return sunElevation(new Date(state.time), c[1], c[0]) < -0.833;
}
function applyTheme() {
  const map = V?.map; if (!map?.getLayer('imagery')) return;
  const night = sceneIsNight();
  const day = !night;
  V.night = night;
  document.getElementById('mv')?.classList.toggle('scene-night', night);
  updateMapChip();
  map.setPaintProperty('imagery', 'raster-brightness-max', day ? 0.95 : 0.34);
  map.setPaintProperty('imagery', 'raster-saturation', day ? -0.08 : -0.55);
  map.setPaintProperty('imagery', 'raster-contrast', day ? 0.05 : 0.18);
  map.setPaintProperty('imagery', 'raster-hue-rotate', day ? 0 : 200);
  map.setPaintProperty('bg', 'background-color', day ? '#DDE4DC' : '#0A100D');
  try {
    map.setSky(day
      ? { 'sky-color': '#8FC1E3', 'horizon-color': '#E8F0F2', 'fog-color': '#E4ECEE', 'sky-horizon-blend': 0.5, 'horizon-fog-blend': 0.6, 'fog-ground-blend': 0.3, 'atmosphere-blend': 0.5 }
      : { 'sky-color': '#03070F', 'horizon-color': '#1B2A44', 'fog-color': '#060B14', 'sky-horizon-blend': 0.7, 'horizon-fog-blend': 0.75, 'fog-ground-blend': 0.45, 'atmosphere-blend': 0.8 });
  } catch {}
  setBase(UI().basemap);
  V.windFx?.reseed();
}

function renderLegend() {
  if (!V) return;
  const el = V.root.querySelector('#legend');
  const rows = ['<div class="legend-note xs demo-note"><b>Fictional demo fields</b> over real imagery. Passes are illustrative.</div>'];
  if (UI().colorBy === 'status') rows.push('<b>Decision status</b>', ...['GO', 'CAUTION', 'STOP', 'INSUFFICIENT_DATA'].map((s) => `<div class="row"><span class="sw" style="background:${STATUS_COLOR[s]};box-shadow:0 0 8px ${STATUS_COLOR[s]}"></span>${esc(statusText(s))}</div>`));
  if (UI().colorBy === 'inversion') rows.push('<b>30 ft − 5 ft temperature</b>', '<div class="row"><span class="sw" style="background:#FF6B5E"></span>Inversion beyond uncertainty</div>', '<div class="row"><span class="sw" style="background:#F5B83D"></span>Warmer above, within uncertainty</div>', '<div class="row"><span class="sw" style="background:#43B4E0"></span>Cooler above</div>', '<div class="row"><span class="sw" style="background:#5B6670"></span>No sensor: unassessed</div>');
  if (UI().wind !== 'off') rows.push(`<div style="margin-top:8px"><b>Wind flow</b></div>${UI().wind !== 'upper' ? '<div class="row"><span class="sw" style="background:linear-gradient(90deg,transparent,#7CF0BE)"></span>5 ft</div>' : ''}${UI().wind !== 'lower' ? '<div class="row"><span class="sw" style="background:linear-gradient(90deg,transparent,#8EC9FF)"></span>30 ft</div>' : ''}<div class="row"><span class="sw" style="background:linear-gradient(90deg,transparent,#FF6B5E)"></span>Above 10 mph</div><div class="xs muted" style="margin-top:3px">Interpolated from 2 masts, ${WIND_EXAG}× speed, shown within 1.5 km only.</div>`);
  if (UI().thermal) rows.push(`<div style="margin-top:8px"><b>Thermal · ${UI().thermalHeight === 'lower' ? '5 ft' : '30 ft'}</b></div><div class="row"><span class="sw" style="width:120px;height:10px;background:linear-gradient(90deg,#0A061E,#3E0F70,#961E78,#DE4950,#FE9F46,#FCF0AA)"></span></div><div class="row xs" style="justify-content:space-between;width:120px"><span>${V.thermalRange ? V.thermalRange[0].toFixed(1) : '–'}°</span><span>${V.thermalRange ? V.thermalRange[1].toFixed(1) : '–'}°F</span></div><div class="xs muted">Interpolated between 2 simulated masts, auto-ranged. Transparent = unassessed.</div>`);
  rows.push(`<div style="margin-top:8px"><b>Masts</b></div><div class="xs muted">Rings colored by measured temperature at 5 ft and 30 ft. Height drawn ${MAST_EXAG}× for visibility.</div>`);
  if (UI().terrainColor && V.terrainLayer?.status === 'ok') rows.push(`<div style="margin-top:8px"><b>Terrain elevation (3DEP)</b></div><div class="row"><span class="sw" style="width:120px;height:10px;background:linear-gradient(90deg,#225E4A,#5C8C52,#BEAA62,#AA7048,#F0ECE4)"></span></div><div class="row xs" style="justify-content:space-between;width:120px"><span>${V.terrainLayer.range_m[0]} m</span><span>${V.terrainLayer.range_m[1]} m</span></div><div class="xs muted">NAVD88 · ${esc(V.terrainLayer.grid)} · hillshaded</div>`);
  if (UI().contours && V.terrainLayer?.status === 'ok') rows.push(`<div class="row xs"><span class="sw" style="height:2px;background:#F3E9C6"></span>Contours every ${V.terrainLayer.contour_interval_m} m (bold every ${V.terrainLayer.contour_interval_m * 5} m)</div>`);
  if (UI().liveModel && V.liveModelMeta) rows.push(`<div style="margin-top:8px"><b>Raw model 2 m temperature</b></div><div class="xs muted">HRRR, ${esc(V.liveModelMeta.resolution)}; dots at cell centres, valid ${esc(when(V.liveModelMeta.valid_mst))}. Real data, separate from the simulated demo.</div>`);
  if (UI().liveStations) rows.push('<div class="xs muted" style="margin-top:6px"><b>AZMET stations</b>: real observation sites with documented sensor heights.</div>');
  if (UI().showPasses) rows.push('<div style="margin-top:8px"><b>Passes (illustrative)</b></div><div class="row"><span class="sw" style="background:#5BE3A5;box-shadow:0 0 8px #5BE3A5"></span>Completed</div><div class="row"><span class="sw" style="border:1px dashed #fff"></span>Remaining</div><div class="row"><span class="sw" style="background:#FFD166"></span>Active pass</div>');
  if (UI().showAreas) rows.push('<div class="row" style="margin-top:6px"><span class="sw" style="background:repeating-linear-gradient(135deg,#FF6B5E 0 2px,transparent 2px 5px)"></span>Exclusion (not treated)</div>');
  el.innerHTML = rows.join('') + `<div class="xs muted" style="margin-top:8px">${state.time > state.meta.scenario.now ? 'Simulated forecast' : 'Simulated observation'} · ${when(state.time)}</div>`;
}

// ====================================================== WIND PARTICLES
// Particles advected by an inverse-distance blend of the masts' wind vectors
// (direction air moves TO). Outside 1.5 km of any mast there is no flow: the
// area is unassessed. Motion is exaggerated for readability and labeled so.
function windParticles(map, canvas) {
  // Live inside the map's canvas container: above the WebGL layer, below HTML labels.
  map.getCanvasContainer().appendChild(canvas);
  Object.assign(canvas.style, { position: 'absolute', left: 0, top: 0, width: '100%', height: '100%', pointerEvents: 'none' });
  const ctx = canvas.getContext('2d');
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  let parts = [], raf = null, moving = false, lastT = performance.now();
  const N = isMobile() ? 500 : 1100;
  const mLat = 110540;
  const resize = () => {
    const r = canvas.getBoundingClientRect();
    canvas.width = r.width * dpr; canvas.height = r.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  resize();
  const ro = new ResizeObserver(resize); ro.observe(canvas);
  const sensors = () => state.fields.sensors.features.map((f) => ({ c: f.geometry.coordinates, r: sensorReading(f.properties.id) })).filter((s) => s.r);
  const bbox = () => {
    const s = state.fields.sensors.features.map((f) => f.geometry.coordinates);
    const lons = s.map((c) => c[0]), lats = s.map((c) => c[1]);
    return [Math.min(...lons) - 0.017, Math.max(...lons) + 0.017, Math.min(...lats) - 0.015, Math.max(...lats) + 0.015];
  };
  function field(lon, lat, h) {
    const mLon = 111320 * Math.cos(lat * Math.PI / 180);
    let wu = 0, wv = 0, ws = 0, sp = 0, dmin = Infinity;
    for (const s of sensors()) {
      const r = s.r[h];
      if (r.wind_mph == null || r.dir_from_deg == null) continue;
      const d = Math.hypot((lon - s.c[0]) * mLon, (lat - s.c[1]) * mLat); dmin = Math.min(dmin, d);
      const w = 1 / Math.max(60, d) ** 2;
      const to = ((r.dir_from_deg + 180) % 360) * Math.PI / 180;
      const ms = r.wind_mph * 0.44704;
      wu += w * Math.sin(to) * ms; wv += w * Math.cos(to) * ms; ws += w; sp += w * r.wind_mph;
    }
    if (!ws || dmin > 1500) return null;
    return { u: wu / ws, v: wv / ws, mph: sp / ws, mLon, fade: Math.min(1, (1500 - dmin) / 400) };
  }
  function spawn(h) {
    const [x0, x1, y0, y1] = bbox();
    for (let k = 0; k < 20; k++) {
      const lon = x0 + Math.random() * (x1 - x0), lat = y0 + Math.random() * (y1 - y0);
      if (field(lon, lat, h)) return { lon, lat, h, age: 0, max: 60 + Math.random() * 90 };
    }
    return { lon: 0, lat: 0, h, age: 999, max: 0 };
  }
  function reseed() {
    const w = state.ui.wind; const hs = w === 'both' ? ['lower', 'upper'] : w === 'off' ? [] : [w || 'lower'];
    parts = [];
    hs.forEach((h) => { for (let i = 0; i < N / hs.length; i++) { const p = spawn(h); p.age = Math.random() * p.max; parts.push(p); } });
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (reduceMotion) drawStatic();
  }
  const color = (h, mph, a) => {
    const day = state.theme === 'light';
    if (mph > 10) return `rgba(${day ? '214,40,30' : '255,107,94'},${a})`;
    return h === 'lower' ? `rgba(${day ? '230,255,240' : '124,240,190'},${a})` : `rgba(${day ? '170,215,255' : '142,201,255'},${a})`;
  };
  function frame(now) {
    raf = requestAnimationFrame(frame);
    const dt = Math.min(0.05, (now - lastT) / 1000); lastT = now;
    const w = canvas.width / dpr, hgt = canvas.height / dpr;
    if (moving) { ctx.clearRect(0, 0, w, hgt); }
    else {
      ctx.globalCompositeOperation = 'destination-out';
      ctx.fillStyle = 'rgba(0,0,0,0.09)'; ctx.fillRect(0, 0, w, hgt);
      ctx.globalCompositeOperation = 'lighter';
    }
    ctx.lineCap = 'round';
    for (let i = 0; i < parts.length; i++) {
      let p = parts[i];
      p.age += 1;
      const f = p.age < p.max ? field(p.lon, p.lat, p.h) : null;
      if (!f) { parts[i] = spawn(p.h); continue; }
      const a = map.project([p.lon, p.lat]);
      p.lon += (f.u * dt * WIND_EXAG) / f.mLon; p.lat += (f.v * dt * WIND_EXAG) / mLat;
      const b = map.project([p.lon, p.lat]);
      if (moving) continue;
      const life = Math.sin(Math.PI * (p.age / p.max));
      ctx.strokeStyle = color(p.h, f.mph, 0.75 * life * f.fade);
      ctx.lineWidth = p.h === 'upper' ? 1.3 : 1.7;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    ctx.globalCompositeOperation = 'source-over';
  }
  function drawStatic() {
    // Reduced motion: short static streamlines instead of animation.
    const w = canvas.width / dpr, hgt = canvas.height / dpr;
    ctx.clearRect(0, 0, w, hgt);
    for (const p0 of parts.slice(0, 260)) {
      let lon = p0.lon, lat = p0.lat; ctx.beginPath();
      for (let s = 0; s < 14; s++) {
        const f = field(lon, lat, p0.h); if (!f) break;
        const pt = map.project([lon, lat]); s ? ctx.lineTo(pt.x, pt.y) : ctx.moveTo(pt.x, pt.y);
        lon += (f.u * 0.4 * WIND_EXAG) / f.mLon; lat += (f.v * 0.4 * WIND_EXAG) / mLat;
        ctx.strokeStyle = color(p0.h, f.mph, 0.55);
      }
      ctx.lineWidth = 1.2; ctx.stroke();
    }
  }
  map.on('movestart', () => { moving = true; });
  map.on('moveend', () => { moving = false; if (reduceMotion) drawStatic(); });
  reseed();
  if (!reduceMotion) raf = requestAnimationFrame(frame);
  return { reseed, stop() { cancelAnimationFrame(raf); ro.disconnect(); } };
}

// ------------------------------------------------------- 2D SVG fallback
function renderFallback() {
  const el = V.root.querySelector('#map');
  const all = [...state.fields.fields.features, ...state.fields.sensitive.features];
  const pts = all.flatMap((f) => f.geometry.coordinates[0]);
  const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
  const W = 1000, H = Math.round(W * ((y1 - y0) * 110540) / ((x1 - x0) * 93700)) + 40;
  const P = ([lon, lat]) => `${(20 + (lon - x0) / (x1 - x0) * (W - 40)).toFixed(1)},${(H - 20 - (lat - y0) / (y1 - y0) * (H - 40)).toFixed(1)}`;
  const by = Object.fromEntries((V.all?.fields || []).map((f) => [f.field_id, f]));
  const poly = (f, fill, stroke, extra = '') => `<polygon points="${f.geometry.coordinates[0].map(P).join(' ')}" fill="${fill}" stroke="${stroke}" ${extra}/>`;
  const segs = (V.ev?.path?.segments || []).map((s) => `<polyline points="${s.coords.map(P).join(' ')}" fill="none" stroke="${s.type === 'spray' ? '#5BE3A5' : '#777'}" stroke-width="${s.type === 'spray' ? 1.2 : .8}"/>`).join('');
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="100%" role="img" aria-label="Schematic 2D map (WebGL unavailable)" style="background:#0A100D">
    ${state.fields.sensitive.features.map((f) => poly(f, KIND_COLOR[f.properties.kind] + '40', KIND_COLOR[f.properties.kind])).join('')}
    ${state.fields.fields.features.map((f) => { const a = by[f.properties.id]; return poly(f, (a ? STATUS_COLOR[a.status] : '#666') + '55', f.properties.id === state.selectedField ? '#fff' : '#888', `stroke-width="${f.properties.id === state.selectedField ? 3 : 1}" style="cursor:pointer" data-select-field="${f.properties.id}"`); }).join('')}
    ${UI().showPasses ? segs : ''}
    ${state.fields.fields.features.map((f) => { const [x, y] = P(f.properties.centroid).split(','); const a = by[f.properties.id]; return `<text x="${x}" y="${y}" text-anchor="middle" font-size="16" font-weight="600" fill="#EEF3EF">${esc(f.properties.name)}</text><text x="${x}" y="${+y + 18}" text-anchor="middle" font-size="13" fill="#AAB7AF">${a ? esc(statusText(a.status)) : ''}</text>`; }).join('')}
    ${V.fbVehicle ? (() => { const [x, y] = P(V.fbVehicle).split(','); return `<circle cx="${x}" cy="${y}" r="7" fill="#FFD166" stroke="#0A100D" stroke-width="2"/>`; })() : ''}
  </svg>`;
  V.root.querySelector('#map-note').innerHTML = '<b>Schematic 2D view</b>: WebGL is unavailable, so no basemap, 3D or wind animation. Fictional fields shown to scale.';
}


// =============================================================== TERRAIN / LIVE
function updateMapChip() {
  const el = V?.root.querySelector('#map-chip'); if (!el) return;
  const parts = [];
  if (V.night) parts.push(`${icon('moon', 'sm')} Night scene${UI().lighting === 'auto' ? ' (sun below horizon at scenario time)' : ''}`);
  if (UI().is3d && (UI().exaggeration || 1) > 1) parts.push(`Terrain elevation exaggerated ×${UI().exaggeration}`);
  el.hidden = !parts.length;
  el.innerHTML = parts.join(' · ');
}

function addTerrainLayers(map) {
  map.addSource('t-contours', { type: 'geojson', data: empty() });
  map.addLayer({ id: 't-contours', type: 'line', source: 't-contours', layout: { visibility: 'none' },
    paint: { 'line-color': ['case', ['get', 'major'], '#F3E9C6', '#D9CFA8'], 'line-width': ['case', ['get', 'major'], 1.4, 0.7], 'line-opacity': 0.8 } }, 'areas-3d');
  map.addSource('live-model', { type: 'geojson', data: empty() });
  map.addLayer({ id: 'live-model', type: 'circle', source: 'live-model', layout: { visibility: 'none' },
    paint: { 'circle-radius': 9, 'circle-color': ['interpolate', ['linear'], ['get', 't'], 45, '#3B6FD8', 55, '#9BE3C8', 65, '#F6D57A', 75, '#E5484D'],
      'circle-opacity': 0.55, 'circle-stroke-color': '#fff', 'circle-stroke-width': 1 } });
  updateTerrainLayers(); updateLiveLayers();
}

async function updateTerrainLayers() {
  const map = V?.map; if (!map?.getLayer('t-contours')) return;
  const want = UI().terrainColor || UI().contours;
  if (want && !V.terrainLayer) {
    try { V.terrainLayer = await api('/api/terrain/layer?area=district'); }
    catch (e) { V.terrainLayer = { status: 'unavailable', error: e.message }; }
    if (V.terrainLayer.status !== 'ok') { toast('3DEP terrain unavailable: ' + (V.terrainLayer.error || '') + ' No relief is shown instead.', true); }
    else {
      map.addSource('t-color', { type: 'image', url: V.terrainLayer.image_url, coordinates: V.terrainLayer.coordinates });
      map.addLayer({ id: 't-color', type: 'raster', source: 't-color', paint: { 'raster-opacity': 0.75 } }, 'areas-3d');
      map.getSource('t-contours').setData(V.terrainLayer.contours);
    }
  }
  if (map.getLayer('t-color')) map.setLayoutProperty('t-color', 'visibility', UI().terrainColor ? 'visible' : 'none');
  map.setLayoutProperty('t-contours', 'visibility', UI().contours && V.terrainLayer?.status === 'ok' ? 'visible' : 'none');
  renderLegend();
}

async function updateLiveLayers() {
  const map = V?.map; if (!map?.getLayer('live-model')) return;
  V.liveMarkers.forEach((m) => m.remove()); V.liveMarkers = [];
  if (UI().liveStations) {
    try {
      const st = await api('/api/live/stations');
      st.filter((x) => x.status === 'ok').forEach((x) => {
        const el = document.createElement('div'); el.className = 'mk-mast';
        el.innerHTML = `<b>${esc(x.name)} · AZMET</b><div class="r"><span>Temp</span><span>${x.temp_height_m} m</span></div><div class="r"><span>Wind</span><span>${x.wind_height_m} m</span></div><div class="xs">Observed station · real</div>`;
        V.liveMarkers.push(new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat([x.lon, x.lat]).addTo(map));
      });
    } catch (e) { toast('AZMET stations unavailable: ' + e.message, true); }
  }
  if (UI().liveModel) {
    try {
      const g = await api('/api/live/model_grid');
      if (g.status !== 'ok') throw new Error(g.error || 'unavailable');
      map.getSource('live-model').setData({ type: 'FeatureCollection', features: g.cells.map((c) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [c.lon, c.lat] }, properties: { t: c.t2m_f } })) });
      V.liveModelMeta = g;
    } catch (e) { toast('HRRR model layer unavailable: ' + e.message, true); }
  }
  map.setLayoutProperty('live-model', 'visibility', UI().liveModel ? 'visible' : 'none');
  renderLegend();
}

function flyTerrainSite() {
  if (!V?.map) return;
  if (!UI().is3d) { UI().is3d = true; set3d(true); }
  const opts = { center: [-114.47, 32.70], zoom: 12.6, pitch: 72, bearing: 70 };
  reduceMotion ? V.map.jumpTo(opts) : V.map.flyTo({ ...opts, duration: 3000, essential: true });
  toast('Terrain check: Gila Mountains, real 3DEP relief (study area). Click the ground to sample elevation.');
}
