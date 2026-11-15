import { state, api, chip, esc, icon, when, hm, dur, addMin, minutesBetween, fieldName, fieldProps, jobById, planFor, unitName,
  productName, stateBox, loadPlan, toast } from './core.js';

const PRI = ['high', 'medium', 'normal', 'low'];
const PRI_L = { high: 'High', medium: 'Medium', normal: 'Normal', low: 'Low' };

export async function renderSchedule(root) {
  root.innerHTML = '<div class="page"><div class="skeleton" style="height:320px"></div></div>';
  let plan, tls, accepted;
  try {
    plan = await loadPlan();
    accepted = await api('/api/schedule/accepted').catch(() => ({ status: 'none' }));
    tls = Object.fromEntries(await Promise.all(state.jobs.map(async (j) => [j.id, await api('/api/timeline?field_id=' + j.field_id)])));
  } catch (e) {
    root.innerHTML = `<div class="page">${stateBox('error', 'Schedule could not load', e.message)}</div>`;
    return;
  }
  const c = plan.chosen, d = plan.default;
  const changed = c.order.join() !== d.order.join();
  const unsched = plan.jobs.filter((r) => !r.scheduled);
  root.innerHTML = `
  <div class="page">
    <div class="page-head">
      <div><h1>Schedule</h1>
        <p class="sub">${plan.sequences_evaluated} job orders evaluated · generated ${hm(plan.generated_at)} · rule ${esc(plan.rule_version)} · <span class="tag sim">Simulated scenario</span></p></div>
      <div class="btn-row"><button class="btn primary" id="recalc">${icon('reset')}Recalculate plan</button>
        <button class="btn" data-explain="order" data-field="${esc(state.selectedField)}">${icon('chat')}Why this order?</button></div>
    </div>

    <section class="panel" aria-labelledby="ord-h">
      <div class="section-title"><h2 id="ord-h" style="margin:0">Proposed order</h2>
        ${accepted.status === 'none' ? '<span class="tag sim">Proposed - not accepted</span>' : accepted.order.join() === plan.order.join()
          ? `<span class="tag user">Accepted by ${esc(accepted.by)} · ${esc(accepted.at.replace('T', ' ').slice(0, 16))}</span>`
          : `<span class="tag sim">Changed since acceptance (${esc(accepted.order.join(' → '))})</span>`}</div>
      <div class="compare-orders">
        <div class="order-card chosen"><div class="small muted">Proposed</div><div class="order-seq">${esc(c.order.join(' → '))}</div>
          <div class="small">${c.scheduled.length} of ${c.order.length} jobs fit before their deadlines${c.unscheduled.length ? `; ${esc(c.unscheduled.join(', '))} unscheduled` : ''}.</div></div>
        <div class="order-card"><div class="small muted">Request order (as received)</div><div class="order-seq">${esc(d.order.join(' → '))}</div>
          <div class="small">${d.scheduled.length} of ${d.order.length} jobs fit${d.unscheduled.length ? `; ${esc(d.unscheduled.join(', '))} would be unscheduled` : ''}.</div></div>
      </div>
      <p class="small" style="margin-top:10px">${changed ? 'The order changed because ' + esc(reasonText(plan)) : 'The request order is already the best evaluated order.'}</p>
      <p class="xs muted" style="margin-top:4px">${esc(plan.objective)} ${esc(plan.conditional_note)}</p>
      <form id="accept-form" class="btn-row" style="margin-top:14px;align-items:center"><label class="sr" for="acc-name">Operator name</label>
        <input id="acc-name" type="text" placeholder="Operator name" style="max-width:220px"><button class="btn primary" type="submit">${icon('go', 'sm')}Accept this plan</button>
        <span class="xs muted">Accepting records the plan and who accepted it. Each job still needs a fresh local check before starting.</span></form>
    </section>

    <section class="panel" aria-labelledby="g-h">
      <div class="section-title"><h2 id="g-h">Timeline</h2>
        <div class="legend"><span><i class="lg prep"></i>Travel + setup</span>
          <span><i class="lg app"></i>Application</span><span><i class="lg rain"></i>Rain-free interval</span>
          <span><i class="lg slot"></i>Field slot without blocking flags</span><span><i class="lg dl"></i>Deadline</span></div></div>
      ${gantt(plan, tls)}
    </section>

    ${unsched.length ? `<section class="panel" aria-labelledby="u-h"><h2 id="u-h">Unscheduled</h2>
      ${unsched.map((r) => { const j = jobById(r.job_id); return `<div class="unsched">${chip('STOP')} <b>${esc(j.id)} · ${esc(fieldName(j.field_id))}</b>
        <p style="margin:6px 0">${esc(r.message)}</p><ul class="small" style="margin:0;padding-left:1.1em">${(r.details || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
        <div class="btn-row" style="margin-top:8px"><button class="btn sm" data-edit="${esc(j.id)}">${icon('edit', 'sm')}Edit request</button>
        <button class="btn sm ghost" data-explain="${r.reason_code === 'equipment_conflict' ? 'equipment' : 'missing'}" data-field="${esc(j.field_id)}">What is missing?</button></div></div>`; }).join('')}
      <p class="xs muted" style="margin-top:8px">Weather and product constraints are never relaxed to force a schedule.</p></section>` : ''}

    <section class="panel" aria-labelledby="r-h">
      <div class="section-title"><h2 id="r-h">Treatment requests</h2><button class="btn sm" id="add-req">${icon('plus', 'sm')}Add request</button></div>
      <div class="table-wrap"><table class="data"><thead><tr><th>Request</th><th>Field</th><th>Earliest</th><th>Preferred</th><th>Latest completion</th><th>Priority</th><th>Equipment</th><th>Product</th><th></th></tr></thead>
      <tbody>${state.jobs.map((j) => `<tr><td><b>${esc(j.id)}</b><div class="xs muted">${esc(j.reference)}</div></td>
        <td>${esc(fieldName(j.field_id))}<div class="xs muted">${esc(fieldProps(j.field_id).crop)}</div></td>
        <td class="nowrap small">${when(j.earliest_start)}</td><td class="nowrap small">${when(j.preferred_start)}</td><td class="nowrap small"><b>${when(j.latest_completion)}</b></td>
        <td><span class="tag">${esc(PRI_L[j.priority])}</span></td><td class="small">${esc(unitName(j.unit_id))}</td><td class="small">${esc(productName(j.product_id))}</td>
        <td><button class="btn sm ghost" data-edit="${esc(j.id)}" aria-label="Edit ${esc(j.id)}">${icon('edit', 'sm')}</button></td></tr>`).join('')}</tbody></table></div>
      <div id="editor"></div>
    </section>
  </div>`;

  root.querySelector('#accept-form').onsubmit = async (e) => {
    e.preventDefault();
    try { const a = await api('/api/schedule/accept', { method: 'POST', body: { operator: root.querySelector('#acc-name').value } }); toast(`Plan accepted by ${a.by} and recorded.`); renderSchedule(root); }
    catch (err) { toast(err.message, true); }
  };
  root.querySelector('#recalc').onclick = async () => {
    try { await loadPlan(true, 'operator recalculated'); toast('Plan recalculated and recorded.'); renderSchedule(root); } catch (e) { toast(e.message, true); }
  };
  root.querySelectorAll('[data-edit]').forEach((b) => b.onclick = () => editor(root, jobById(b.dataset.edit)));
  root.querySelector('#add-req').onclick = () => editor(root, null);
}

function reasonText(plan) {
  const lost = plan.default.unscheduled.filter((j) => plan.chosen.scheduled.includes(j));
  if (lost.length) {
    const why = lost.map((j) => `${j} (${(plan.default.jobs[j].reason || '').replace('_', ' ')})`).join(', ');
    return `the request order would leave ${why} without a window.`;
  }
  return 'higher-priority work finishes earlier.';
}

function gantt(plan, tls) {
  const d0 = state.meta.scenario.day0;
  const start = addMin(d0, 5 * 60), end = addMin(d0, (24 + 19) * 60);
  const span = minutesBetween(start, end);
  const x = (iso) => Math.max(0, Math.min(100, minutesBetween(start, iso) / span * 100));
  const hours = [];
  for (let m = 0; m <= span; m += 120) hours.push(addMin(start, m));
  const axis = `<div class="g-axis" style="grid-template-columns:repeat(${hours.length - 1},1fr)">${hours.slice(0, -1).map((h) => `<span>${when(h)}</span>`).join('')}</div>`;
  const lanes = state.jobs.map((j) => {
    const r = planFor(j.id);
    const tl = tls[j.id];
    const slots = tl.slots.filter((s) => s.time >= start && s.time < end);
    const bg = `<div class="g-bg" aria-hidden="true">${slots.map((s) => `<span class="${s.suitable ? 'ok' : 'bad'}"></span>`).join('')}</div>`;
    let bars = '';
    if (r?.scheduled) {
      const prepL = x(r.depart), prepW = x(r.start) - prepL;
      bars += `<div class="g-bar prep" style="left:${prepL}%;width:${Math.max(0.6, prepW)}%" title="Travel ${r.travel_min} min + setup ${r.setup_min} min"></div>`;
      bars += `<button type="button" class="g-bar" style="left:${x(r.start)}%;width:${Math.max(1.2, x(r.end) - x(r.start))}%" data-explain="hold" data-field="${esc(j.field_id)}"
        aria-label="${esc(j.id)} ${when(r.start)} to ${hm(r.end)}"></button>`;
      bars += `<div class="g-lab" style="left:${x(r.depart)}%">${esc(j.id)} · ${hm(r.start)}–${hm(r.end)} <span>${r.wait_min > 0 ? `waits ${dur(r.wait_min)} for conditions` : ''}</span></div>`;
      const rh = state.catalog.products[j.product_id]?.constraints.rainfast_h.value;
      if (rh) bars += `<div class="g-bar rain" style="left:${x(r.end)}%;width:${x(addMin(r.end, rh * 60)) - x(r.end)}%" title="${rh} h rain-free interval (${esc(state.catalog.products[j.product_id].constraints.rainfast_h.source)})"></div>`;
    }
    const dl = j.latest_completion < end ? `<div class="g-deadline" style="left:${x(j.latest_completion)}%" title="Deadline ${when(j.latest_completion)}"></div>` : '';
    const now = `<div class="g-now" style="left:${x(state.meta.scenario.now)}%" title="Scenario now"></div>`;
    return `<div class="g-lane"><div class="lbl"><b>${esc(j.id)}</b> ${esc(fieldName(j.field_id))}<div class="xs muted">${esc(unitName(j.unit_id))}</div>
      ${r?.scheduled ? '' : '<div class="xs" style="color:var(--red);font-weight:600">No suitable window</div>'}</div>
      <div class="track">${bg}${bars}${dl}${now}</div></div>`;
  }).join('');
  const rainRow = (() => {
    const rs = state.plan && (Object.values(tls)[0]?.rain || []).filter((p) => p.time >= start && p.time < end);
    return `<div class="g-lane" style="min-height:34px"><div class="lbl small">Rain probability<div class="xs muted">simulated forecast</div></div>
      <div class="track" style="display:grid;grid-auto-flow:column;grid-auto-columns:1fr;align-items:end">${rs.map((p) => `<span title="${when(p.time)}: ${p.prob_pct}%" style="height:${Math.max(2, p.prob_pct * 0.3)}px;background:${p.prob_pct >= 40 ? 'var(--marker-blue)' : 'color-mix(in srgb, var(--marker-blue) 35%, transparent)'};margin:0 1px"></span>`).join('')}</div></div>`;
  })();
  return `<div class="gantt" role="region" aria-label="Schedule timeline" tabindex="0"><div class="gantt-inner">${axis}${lanes}${rainRow}</div></div>
    <p class="xs muted" style="margin-top:6px">Shaded green slots have no blocking flags for that field. A job also needs its whole duration, travel, setup, crew shift and rain-free interval to fit.</p>`;
}

// -------------------------------------------------------------- editor
const toLocal = (iso) => (iso ? iso.slice(0, 16) : '');
const fromLocal = (v) => (v ? v + ':00-07:00' : '');

function editor(root, job) {
  const el = root.querySelector('#editor');
  const isNew = !job;
  const j = job || { field_id: 'A', reference: '', reference_type: 'pca', product_id: 'unknown', priority: 'normal', unit_id: 'U1',
    earliest_start: state.meta.scenario.now, preferred_start: state.meta.scenario.now, latest_completion: addMin(state.meta.scenario.now, 24 * 60), orientation_deg: 0, notes: '' };
  el.innerHTML = `<form class="panel" style="margin-top:12px;background:var(--paper)" id="req-form" novalidate>
    <h3 style="margin-bottom:10px">${isNew ? 'New treatment request' : 'Edit ' + esc(j.id)}</h3>
    <p class="small muted" style="margin-bottom:10px">Treatment need and urgency come from the PCA or schedule. Times are Arizona time (MST).</p>
    <div class="form-grid">
      <div class="field"><label for="f-field">Field</label><select id="f-field" name="field_id">${state.fields.fields.features.map(({ properties: p }) => `<option value="${p.id}" ${p.id === j.field_id ? 'selected' : ''}>${esc(p.name)} - ${esc(p.crop)}</option>`).join('')}</select></div>
      <div class="field"><label for="f-ref">PCA recommendation or schedule reference</label><input id="f-ref" name="reference" type="text" value="${esc(j.reference)}" required></div>
      <div class="field"><label for="f-es">Earliest permissible start</label><input id="f-es" name="earliest_start" type="datetime-local" value="${toLocal(j.earliest_start)}" required></div>
      <div class="field"><label for="f-ps">Preferred start</label><input id="f-ps" name="preferred_start" type="datetime-local" value="${toLocal(j.preferred_start)}"></div>
      <div class="field"><label for="f-lc">Latest acceptable completion</label><input id="f-lc" name="latest_completion" type="datetime-local" value="${toLocal(j.latest_completion)}" required></div>
      <div class="field"><label for="f-pri">Priority</label><select id="f-pri" name="priority">${PRI.map((p) => `<option value="${p}" ${p === j.priority ? 'selected' : ''}>${PRI_L[p]}</option>`).join('')}</select></div>
      <div class="field"><label for="f-unit">Equipment and crew</label><select id="f-unit" name="unit_id">${state.catalog.units.map((u) => `<option value="${u.id}" ${u.id === j.unit_id ? 'selected' : ''}>${esc(u.name)} · ${esc(u.crew)}</option>`).join('')}</select></div>
      <div class="field"><label for="f-prod">Operator-selected product</label><select id="f-prod" name="product_id">${Object.entries(state.catalog.products).map(([id, p]) => `<option value="${id}" ${id === j.product_id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select>
        <span class="hint">Constraints come from the product entry; unknown values stay unknown.</span></div>
      <div class="field"><label for="f-dur">Job duration override (min)</label><input id="f-dur" name="duration_override_min" type="number" min="0" step="5" value="${esc(j.duration_override_min ?? '')}" placeholder="Estimate from equipment"></div>
    </div>
    <div class="field" style="margin-top:10px"><label for="f-notes">Notes</label><textarea id="f-notes" name="notes" rows="2">${esc(j.notes || '')}</textarea></div>
    <div id="form-err" class="small" style="color:var(--red);margin-top:8px" role="alert"></div>
    <div class="btn-row" style="margin-top:10px"><button class="btn primary" type="submit">${isNew ? 'Add request and replan' : 'Save and replan'}</button>
      <button class="btn" type="button" id="f-cancel">Cancel</button>
      ${isNew ? '' : `<button class="btn danger" type="button" id="f-del">${icon('trash', 'sm')}Remove request</button>`}</div>
  </form>`;
  el.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
  const form = el.querySelector('#req-form');
  form.querySelector('#f-ref').focus();
  el.querySelector('#f-cancel').onclick = () => { el.innerHTML = ''; };
  el.querySelector('#f-del')?.addEventListener('click', async () => {
    try { await api('/api/jobs/' + j.id, { method: 'DELETE' }); await loadPlan(true, `request ${j.id} removed`); toast(`${j.id} removed and recorded.`); renderSchedule(root); } catch (e) { toast(e.message, true); }
  });
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const body = { ...j, ...Object.fromEntries(fd) };
    ['earliest_start', 'preferred_start', 'latest_completion'].forEach((k) => { body[k] = fromLocal(fd.get(k)); });
    body.duration_override_min = fd.get('duration_override_min') ? Number(fd.get('duration_override_min')) : null;
    const err = el.querySelector('#form-err');
    if (!body.reference.trim()) { err.textContent = 'Add the PCA recommendation or schedule reference.'; form.querySelector('#f-ref').focus(); return; }
    if (body.latest_completion <= body.earliest_start) { err.textContent = 'Latest completion must be after the earliest start.'; form.querySelector('#f-lc').focus(); return; }
    try {
      const saved = await api('/api/jobs', { method: 'POST', body });
      await loadPlan(true, `request ${saved.id} ${isNew ? 'added' : 'edited'}`);
      const r = planFor(saved.id);
      toast(r?.scheduled ? `${saved.id} scheduled ${when(r.start)}–${hm(r.end)}.` : `${saved.id}: no suitable window found before the requested deadline - review with your PCA.`, !r?.scheduled);
      renderSchedule(root);
    } catch (e2) { err.textContent = e2.message; }
  };
}
