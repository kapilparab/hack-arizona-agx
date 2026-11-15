// Shared state, API client, formatting and UI primitives.
// API calls are same-origin relative paths, so the app works from a phone on the LAN.

export const state = {
  meta: null, fields: null, catalog: null, plan: null, jobs: [],
  time: null,            // scenario time being viewed (ISO, MST offset)
  selectedField: 'A', lang: 'en', online: true, lastOk: null,
};
const subs = new Set();
export const on = (fn) => { subs.add(fn); return () => subs.delete(fn); };
export const emit = (what) => subs.forEach((fn) => fn(what));

// ------------------------------------------------------------------ API
export async function api(path, opts = {}) {
  const init = { headers: { 'Content-Type': 'application/json' }, ...opts };
  if (opts.body && typeof opts.body !== 'string') init.body = JSON.stringify(opts.body);
  let res;
  try {
    res = await fetch(path, init);
  } catch (e) {
    setOnline(false);
    throw new ApiError('Cannot reach the CanopyGuard server. Check the connection; showing the last loaded data.', 0);
  }
  setOnline(true);
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const j = await res.json(); if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new ApiError(msg, res.status);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('json') ? res.json() : res.text();
}
export class ApiError extends Error { constructor(m, s) { super(m); this.status = s; } }

function setOnline(ok) {
  const was = state.online;
  state.online = ok;
  if (ok) state.lastOk = new Date();
  const el = document.getElementById('conn');
  if (!ok) {
    el.hidden = false; el.className = 'conn err';
    el.textContent = 'Offline: the server is unreachable. Values shown are from the last successful load' +
      (state.lastOk ? ` at ${state.lastOk.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : '') + ' and may be stale. Do not start an application from stale data.';
  } else if (!was) {
    el.hidden = true; toast('Connection restored.');
  }
}
window.addEventListener('offline', () => setOnline(false));

// ----------------------------------------------------------- formatting
// Scenario times carry a fixed -07:00 offset (Arizona, no DST). Read wall-clock
// parts directly from the ISO string so the browser's own timezone never shifts them.
export const hm = (iso) => (iso ? iso.slice(11, 16) : '—');
export function dayLabel(iso) {
  if (!iso || !state.meta) return '';
  const d0 = state.meta.scenario.day0.slice(0, 10);
  const d = iso.slice(0, 10);
  if (d === d0) return state.lang === 'es' ? 'Hoy' : 'Today';
  const next = addMin(state.meta.scenario.day0, 24 * 60).slice(0, 10);
  if (d === next) return state.lang === 'es' ? 'Mañana' : 'Tomorrow';
  return d;
}
export const when = (iso) => (iso ? `${dayLabel(iso)} ${hm(iso)}` : '—');
export function addMin(iso, min) {
  const t = new Date(new Date(iso).getTime() + min * 60000);
  // re-render in MST (UTC-7)
  const m = new Date(t.getTime() - 7 * 3600000);
  return m.toISOString().slice(0, 19) + '-07:00';
}
export const minutesBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 60000);
export function dur(min) {
  if (min == null) return '—';
  const h = Math.floor(Math.abs(min) / 60), m = Math.abs(min) % 60;
  return (min < 0 ? '−' : '') + (h ? `${h} h ${m ? m + ' min' : ''}` : `${m} min`).trim();
}
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const icon = (id, cls = '') => `<svg class="ic ${cls}" aria-hidden="true"><use href="#i-${id}"/></svg>`;

const STATUS = {
  GO: { icon: 'go', en: 'Go', es: 'Adelante' },
  CAUTION: { icon: 'caution', en: 'Caution', es: 'Precaución' },
  STOP: { icon: 'stop', en: 'Stop', es: 'Alto' },
  INSUFFICIENT_DATA: { icon: 'nodata', en: 'Insufficient data', es: 'Datos insuficientes' },
};
export const statusText = (s) => (STATUS[s] || STATUS.INSUFFICIENT_DATA)[state.lang] || s;
export function chip(s, size = '') {
  const d = STATUS[s] || STATUS.INSUFFICIENT_DATA;
  return `<span class="chip ${esc(s)} ${size}">${icon(d.icon)}${esc(d[state.lang] || d.en)}</span>`;
}
export const kindTag = (kind) => {
  if (!kind) return '<span class="tag">No data</span>';
  if (kind.startsWith('simulated')) return `<span class="tag sim">${kind === 'simulated_forecast' ? 'Simulated forecast' : 'Simulated observation'}</span>`;
  if (kind === 'model_estimate') return '<span class="tag model">Model estimate</span>';
  return `<span class="tag">${esc(kind)}</span>`;
};
export const compass = (deg) => ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(((deg % 360) + 360) % 360 / 45) % 8];

// --------------------------------------------------------------- toasts
export function toast(msg, err = false) {
  const t = document.createElement('div');
  t.className = 'toast' + (err ? ' err' : '');
  t.textContent = msg;
  document.getElementById('toasts').appendChild(t);
  setTimeout(() => t.remove(), err ? 6000 : 3500);
}

export function stateBox(kind, title, body, action = '') {
  return `<div class="state ${kind === 'error' ? 'err' : ''}" role="${kind === 'error' ? 'alert' : 'status'}"><h3>${esc(title)}</h3><p>${esc(body)}</p>${action}</div>`;
}

// ------------------------------------------------------------- loaders
export async function loadBase() {
  const [meta, fields, catalog, jobs] = await Promise.all([api('/api/meta'), api('/api/fields'), api('/api/catalog'), api('/api/jobs')]);
  Object.assign(state, { meta, fields, catalog, jobs });
  if (!state.time) state.time = meta.scenario.now;
  return state;
}
export async function loadPlan(recalc = false, reason) {
  state.plan = recalc ? await api('/api/schedule', { method: 'POST', body: { reason: reason || 'operator request' } }) : await api('/api/schedule');
  state.jobs = await api('/api/jobs');
  emit('plan');
  return state.plan;
}
export const fieldName = (fid) => state.fields?.fields.features.find((f) => f.properties.id === fid)?.properties.name || fid;
export const fieldProps = (fid) => state.fields?.fields.features.find((f) => f.properties.id === fid)?.properties;
export const jobById = (jid) => state.jobs.find((j) => j.id === jid);
export const planFor = (jid) => state.plan?.jobs.find((r) => r.job_id === jid);
export const unitName = (uid) => state.catalog?.units.find((u) => u.id === uid)?.name || uid;
export const productName = (pid) => state.catalog?.products[pid]?.name || 'Not entered';

// -------------------------------------------------------- explain drawer
const TOPICS = [
  { id: 'hold', en: 'Why is this field on hold?', es: '¿Por qué está en espera este campo?', needs: 'field' },
  { id: 'order', en: 'Why this job order?', es: '¿Por qué este orden?', needs: null },
  { id: 'rain', en: 'Can it finish before the forecast rain?', es: '¿Termina antes de la lluvia?', needs: 'job' },
  { id: 'equipment', en: 'Why is this equipment only a candidate?', es: '¿Por qué el equipo es solo candidato?', needs: 'job' },
  { id: 'neighbors', en: 'Which neighboring area needs attention?', es: '¿Qué área vecina requiere atención?', needs: 'field' },
  { id: 'missing', en: 'What information is missing?', es: '¿Qué información falta?', needs: 'field' },
];
let explainCtx = { topic: 'hold', field: null, opener: null };

export function openExplain(topic, fieldId, opener) {
  explainCtx = { topic: topic || 'hold', field: fieldId || state.selectedField, opener: opener || document.activeElement };
  const el = document.getElementById('explain');
  el.hidden = false;
  renderExplain();
  el.querySelector('[data-close-explain]').focus();
}
export function closeExplain() {
  const el = document.getElementById('explain');
  if (el.hidden) return;
  el.hidden = true;
  explainCtx.opener?.focus?.();
}
async function renderExplain() {
  const el = document.getElementById('explain');
  if (el.hidden) return;
  const { topic, field } = explainCtx;
  document.getElementById('explain-title').textContent =
    (state.lang === 'es' ? 'Explicación' : 'Explanation') + ` · ${fieldName(field)}`;
  document.getElementById('explain-topics').innerHTML = TOPICS.map((t) =>
    `<button type="button" data-topic="${t.id}" aria-pressed="${t.id === topic}">${esc(t[state.lang])}</button>`).join('');
  const body = document.getElementById('explain-body');
  body.innerHTML = '<div class="skeleton" style="height:22px;width:70%"></div><div class="skeleton" style="height:64px;margin-top:12px"></div>';
  const job = state.jobs.find((j) => j.field_id === field && j.status === 'open');
  const q = new URLSearchParams({ topic, lang: state.lang, time: state.time });
  if (field) q.set('field_id', field);
  if (job) q.set('job_id', job.id);
  try {
    const r = await api('/api/explain?' + q);
    const lines = (r.mode === 'ai' ? [r.ai_text] : r.lines).map((l) => `<li>${esc(l)}</li>`).join('');
    body.innerHTML = `
      <div class="label"><span class="tag ${r.mode === 'ai' ? 'model' : ''}">${esc(r.label)}</span></div>
      <h3>${esc(r.title)}</h3>
      <ul class="lines">${lines}</ul>
      ${r.mode === 'ai' ? `<details style="margin-top:12px"><summary>Engine lines used</summary><ul class="lines">${r.lines.map((l) => `<li>${esc(l)}</li>`).join('')}</ul></details>` : ''}
      <p class="xs muted" style="margin-top:16px">${state.lang === 'es'
        ? 'Basado solo en los resultados del motor y datos simulados. No recomienda dosis ni anula condiciones bloqueantes.'
        : 'Based only on engine results and simulated data. Does not recommend rates or override blocking conditions.'}${state.meta?.ai_enabled ? '' : (state.lang === 'es' ? ' IA no configurada: explicación basada en reglas.' : ' AI not configured: rule-based explanation shown.')}</p>`;
  } catch (e) {
    body.innerHTML = stateBox('error', state.lang === 'es' ? 'No se pudo cargar la explicación' : 'Explanation unavailable', e.message,
      `<button class="btn sm" style="margin-top:8px" data-retry-explain>${state.lang === 'es' ? 'Reintentar' : 'Retry'}</button>`);
  }
}
document.addEventListener('click', (e) => {
  const t = e.target.closest('[data-topic]');
  if (t) { explainCtx.topic = t.dataset.topic; renderExplain(); return; }
  if (e.target.closest('[data-close-explain]')) closeExplain();
  if (e.target.closest('[data-retry-explain]')) renderExplain();
  const o = e.target.closest('[data-explain]');
  if (o) openExplain(o.dataset.explain, o.dataset.field, o);
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeExplain(); });
on((what) => { if (what === 'lang' || what === 'time') renderExplain(); });

export function setLang(l) {
  state.lang = l;
  document.documentElement.lang = l;
  document.querySelectorAll('.lang button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.lang === l)));
  try { localStorage.setItem('cg-lang', l); } catch {}
  emit('lang');
}

// --------------------------------------------------------------- alerts
export function showAlert(alert, onAck) {
  const bar = document.getElementById('alert-bar');
  bar.hidden = false;
  bar.innerHTML = `${icon('bell')}<div style="flex:1;min-width:220px"><strong>${esc(statusText(alert.severity))}: ${esc(fieldName(alert.field_id))}</strong>
    <div class="small">${esc(alert.message)} <span class="tag sim">Simulated</span> · scenario ${esc(when(alert.last_seen))}${alert.occurrences > 1 ? ` · repeated ${alert.occurrences}×, grouped` : ''}</div></div>
    <label class="sr" for="ack-name">Operator name</label>
    <input id="ack-name" type="text" placeholder="Operator name" autocomplete="name">
    <button class="btn sm" data-ack="${alert.id}">Acknowledge</button>`;
  bar.querySelector('[data-ack]').onclick = async () => {
    const who = bar.querySelector('#ack-name').value;
    try {
      await api(`/api/alerts/${alert.id}/ack`, { method: 'POST', body: { operator: who } });
      bar.hidden = true;
      toast('Alert acknowledged and recorded. The critical status stays active until conditions change.');
      onAck?.();
    } catch (e) { toast(e.message, true); }
  };
}
export const hideAlert = () => { document.getElementById('alert-bar').hidden = true; };

// --------------------------------------------------------------- theme
export function setTheme(t, persist = true) {
  state.theme = t;
  document.documentElement.dataset.theme = t;
  const b = document.getElementById('theme-toggle');
  if (b) {
    b.innerHTML = icon(t === 'dark' ? 'sun' : 'moon');
    b.setAttribute('aria-label', t === 'dark' ? 'Switch to day mode' : 'Switch to night mode');
  }
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', t === 'dark' ? '#070B09' : '#F4F6F2');
  if (persist) { try { localStorage.setItem('cg-theme', t); } catch {} }
  emit('theme');
}
export function initTheme() {
  let t = null;
  try { t = localStorage.getItem('cg-theme'); } catch {}
  setTheme(t || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'), false);
  document.getElementById('theme-toggle')?.addEventListener('click', () => setTheme(state.theme === 'dark' ? 'light' : 'dark'));
}

// Map view preferences shared by the map and the prototype drawer.
state.ui = { view: 'overview', thermal: false, thermalHeight: 'lower', wind: 'both', colorBy: 'status',
  showAreas: true, showPasses: true, is3d: true, basemap: 'imagery' };
state.mapCtl = null; // set by the map view while it is mounted
