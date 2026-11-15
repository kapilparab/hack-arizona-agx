import { state, api, chip, esc, icon, when, hm, fieldName, stateBox, toast } from './core.js';

const KINDS = { '': 'All', assessment: 'Assessments', alert: 'Alerts', ack: 'Acknowledgements', schedule: 'Schedule revisions',
  equipment: 'Equipment', request: 'Requests', area: 'Areas', scenario: 'Scenario', config: 'Settings' };
let filter = '';

export async function renderRecords(root) {
  root.innerHTML = '<div class="page"><div class="skeleton" style="height:300px"></div></div>';
  let recs, alerts;
  try {
    [recs, alerts] = await Promise.all([api('/api/records?limit=300' + (filter ? '&kind=' + filter : '')), api('/api/alerts')]);
  } catch (e) {
    root.innerHTML = `<div class="page">${stateBox('error', 'Records could not load', e.message)}</div>`;
    return;
  }
  root.innerHTML = `
  <div class="page">
    <div class="page-head">
      <div><h1>Records</h1><p class="sub">Timestamped readings, triggered rules, equipment configurations, schedule revisions, alerts and acknowledgements.</p></div>
      <div class="btn-row">
        <button class="btn" id="snap">${icon('records')}Record current assessment</button>
        <a class="btn primary" href="/api/records/export.csv" download>${icon('download')}Export CSV</a></div>
    </div>
    <p class="small muted" style="margin:-12px 0 16px">Stored locally in SQLite and appended by the app. Decision-support log only: not tamper-proof and not a regulatory record.</p>

    <section class="panel" aria-labelledby="al-h">
      <div class="section-title"><h2 id="al-h">Alerts</h2><span class="small muted">Persistent conditions are grouped into one alert per field</span></div>
      ${alerts.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Status</th><th>Field</th><th>Conditions</th><th>First / last seen (scenario)</th><th>Repeats</th><th>Acknowledged</th></tr></thead><tbody>
        ${alerts.map((a) => `<tr><td>${chip(a.severity)}${a.active ? '<div class="xs" style="font-weight:600">Active</div>' : '<div class="xs muted">Cleared</div>'}</td>
          <td>${esc(fieldName(a.field_id))}</td><td class="small">${esc(a.message)}</td>
          <td class="small nowrap">${when(a.first_seen)}<br>${when(a.last_seen)}</td><td>${a.occurrences}</td>
          <td class="small">${a.acknowledged_by ? `${esc(a.acknowledged_by)}<div class="xs muted">${esc(a.acknowledged_at.replace('T', ' ').slice(0, 16))}</div>`
            : `<form class="ack" data-id="${a.id}" style="display:flex;gap:6px"><label class="sr" for="ack-${a.id}">Operator name</label><input id="ack-${a.id}" type="text" placeholder="Operator name" style="min-width:120px"><button class="btn sm">Acknowledge</button></form>`}</td></tr>`).join('')}
      </tbody></table></div>` : '<p class="muted">No alerts yet. Run an application replay on the map and use "Simulate critical change" to see one.</p>'}
    </section>

    <section class="panel" aria-labelledby="log-h">
      <div class="section-title"><h2 id="log-h">Log</h2>
        <label class="sr" for="kind">Filter</label><select id="kind" style="width:auto">${Object.entries(KINDS).map(([k, l]) => `<option value="${k}" ${k === filter ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
      ${recs.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>#</th><th>Recorded (wall clock)</th><th>Scenario time</th><th>Type</th><th>Field</th><th>Status</th><th>Summary</th><th>Rule version</th><th>Data</th></tr></thead><tbody>
        ${recs.map((r) => `<tr><td class="small">${r.id}</td><td class="small nowrap">${esc(r.recorded_at.replace('T', ' ').slice(0, 19))}</td>
          <td class="small nowrap">${r.scenario_time ? when(r.scenario_time) : '—'}</td><td><span class="tag">${esc(r.kind)}</span></td>
          <td class="small">${r.field_id ? esc(fieldName(r.field_id)) : '—'}</td><td>${['GO', 'CAUTION', 'STOP', 'INSUFFICIENT_DATA'].includes(r.status) ? chip(r.status) : esc(r.status || '')}</td>
          <td class="small" style="min-width:260px">${esc(r.summary)}${r.payload ? `<details><summary class="xs">Details</summary><pre class="xs" style="white-space:pre-wrap;max-height:220px;overflow:auto">${esc(JSON.stringify(r.payload, null, 1))}</pre></details>` : ''}</td>
          <td class="xs">${esc(r.rule_version)}</td><td>${r.simulated ? '<span class="tag sim">Simulated</span>' : '<span class="tag user">Operator</span>'}</td></tr>`).join('')}
      </tbody></table></div>` : stateBox('empty', 'No records of this type yet', 'Records appear as you plan, change equipment, mark areas, and replay applications.')}
    </section>

    <section class="panel" aria-labelledby="rc-h" id="regional">
      <div class="section-title"><h2 id="rc-h">Regional context</h2><button class="btn sm" id="load-rc">${icon('reset', 'sm')}Load Open-Meteo context</button></div>
      <p class="small muted">Live model estimates for the Yuma area at their native heights. Context only: never used for Go/Stop and not the 5 ft / 30 ft field sensors.</p>
      <div id="rc-body" style="margin-top:8px"></div>
    </section>
  </div>`;

  root.querySelector('#kind').onchange = (e) => { filter = e.target.value; renderRecords(root); };
  root.querySelector('#snap').onclick = async () => {
    try { await api('/api/records/snapshot', { method: 'POST', body: { field_id: state.selectedField, time: state.time } }); toast(`Assessment for ${fieldName(state.selectedField)} recorded.`); renderRecords(root); }
    catch (e) { toast(e.message, true); }
  };
  root.querySelectorAll('form.ack').forEach((f) => f.onsubmit = async (e) => {
    e.preventDefault();
    try { await api(`/api/alerts/${f.dataset.id}/ack`, { method: 'POST', body: { operator: f.querySelector('input').value } }); toast('Acknowledgement recorded.'); renderRecords(root); }
    catch (err) { toast(err.message, true); }
  });
  root.querySelector('#load-rc').onclick = () => loadRegional(root.querySelector('#rc-body'));
}

async function loadRegional(el) {
  el.innerHTML = '<div class="skeleton" style="height:80px"></div>';
  try {
    const r = await api('/api/context/regional');
    if (r.status === 'unavailable') { el.innerHTML = stateBox('error', 'Regional context unavailable', r.error + ' Retrieved ' + r.retrieved_at.replace('T', ' ')); return; }
    el.innerHTML = `${r.status === 'stale' ? `<div class="state" style="margin-bottom:8px"><b>Stale:</b> ${esc(r.error)}</div>` : ''}
      <p class="small"><span class="tag model">Model estimate</span> Source time ${esc(r.source_time || 'unknown')} (${esc(r.source_timezone || '')}) · retrieved ${esc(r.retrieved_at.replace('T', ' '))} · <a href="${esc(r.source_url)}" target="_blank" rel="noopener">${esc(r.source)}</a></p>
      <div class="table-wrap"><table class="data" style="margin-top:6px"><thead><tr><th>Variable</th><th>Height</th><th>Value</th></tr></thead><tbody>
      ${r.values.map((v) => `<tr><td>${esc(v.label)}</td><td>${v.height_m != null ? v.height_m + ' m' : '—'}</td><td>${v.missing ? '<span class="muted">Missing</span>' : `${esc(v.value)} ${esc(v.unit)}`}</td></tr>`).join('')}</tbody></table></div>
      <p class="xs muted" style="margin-top:6px">${esc(r.note)}</p>`;
  } catch (e) { el.innerHTML = stateBox('error', 'Regional context unavailable', e.message); }
}
