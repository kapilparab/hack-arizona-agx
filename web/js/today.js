import { state, api, chip, esc, icon, when, hm, dur, minutesBetween, fieldName, fieldProps, jobById, planFor, unitName,
  productName, stateBox, loadPlan, toast } from './core.js';

const PRI = { high: 'High', medium: 'Medium', normal: 'Normal', low: 'Low' };
const dayLabelLower = (iso) => when(iso).split(' ')[0].toLowerCase();

export async function renderToday(root) {
  root.innerHTML = `<div class="page"><div class="skeleton" style="height:150px"></div>
    <div class="grid-2" style="margin-top:16px"><div class="skeleton" style="height:260px"></div><div class="skeleton" style="height:260px"></div></div></div>`;
  let all, plan, timelines;
  try {
    [all, plan] = await Promise.all([api('/api/assess/all?time=' + encodeURIComponent(state.meta.scenario.now)), loadPlan()]);
    timelines = await Promise.all(state.fields.fields.features.map((f) => api('/api/timeline?field_id=' + f.properties.id)));
  } catch (e) {
    root.innerHTML = `<div class="page">${stateBox('error', 'Today could not load', e.message, '<button class="btn sm" style="margin-top:8px" onclick="location.reload()">Reload</button>')}</div>`;
    return;
  }
  const now = state.meta.scenario.now;
  const sched = plan.jobs.filter((r) => r.scheduled).sort((a, b) => a.start.localeCompare(b.start));
  const next = sched[0];
  const nextJob = next && jobById(next.job_id);
  const unscheduled = plan.jobs.filter((r) => !r.scheduled);
  const reorder = plan.chosen.order.join() !== plan.default.order.join() && plan.default.unscheduled.some((j) => plan.chosen.scheduled.includes(j));

  // jobs approaching latest acceptable time: slack between planned end (or now) and deadline
  const approaching = state.jobs.filter((j) => j.status === 'open').map((j) => {
    const r = planFor(j.id);
    const left = minutesBetween(now, j.latest_completion);
    const slack = r?.scheduled ? minutesBetween(r.end, j.latest_completion) : null;
    return { j, r, left, slack };
  }).filter((x) => x.left < 24 * 60).sort((a, b) => a.left - b.left);

  const attention = all.fields.filter((f) => f.status !== 'GO' || f.neighbors_attention.length);

  root.innerHTML = `
  <div class="page">
    <div class="page-head">
      <div>
        <h1>Today, ${esc(new Date(state.meta.scenario.day0).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'America/Phoenix' }))}</h1>
        <p class="sub">Scenario clock ${hm(now)} MST · ${state.jobs.filter((j) => j.status === 'open').length} open treatment requests · <span class="tag sim">Simulated scenario</span></p>
      </div>
      <div class="btn-row">
        <a class="btn" href="#/map">${icon('map')}Open map</a>
        <a class="btn" href="#/schedule">${icon('schedule')}Review plan</a>
      </div>
    </div>

    ${next ? `
    <section class="decision" aria-labelledby="next-h">
      <div>
        <p class="eyebrowless">Next proposed job · ${esc(unitName(next.unit_id))}</p>
        <h1 id="next-h">${esc(fieldName(nextJob.field_id))}, ${esc(dayLabelLower(next.start))} at ${hm(next.start)}</h1>
        <p class="why">Depart ${hm(next.depart)} for ${next.travel_min} min travel and ${next.setup_min} min setup. Full job ${dur(next.duration_min)}, finishing ${when(next.end)} - ${esc(minutesBetween(next.end, nextJob.latest_completion) >= 0 ? dur(minutesBetween(next.end, nextJob.latest_completion)) + ' before the requested deadline' : 'after the deadline')}.
        ${reorder ? `<br>Order changed from the request list: ${esc(plan.default.order.join(' → '))} would leave ${esc(plan.default.unscheduled.filter((j) => plan.chosen.scheduled.includes(j)).join(', '))} unscheduled.` : ''}</p>
        <div class="hero-stats">
          <div><div class="k">Starts in</div><div class="v">${dur(minutesBetween(now, next.start))}</div></div>
          <div><div class="k">Deadline margin</div><div class="v">${dur(minutesBetween(next.end, nextJob.latest_completion))}</div></div>
          <div><div class="k">Jobs with a window</div><div class="v">${plan.chosen.scheduled.length}<span class="muted" style="font-size:1rem"> / ${plan.chosen.order.length}</span></div></div>
          <div><div class="k">Orders evaluated</div><div class="v">${plan.sequences_evaluated}</div></div>
        </div>
        <p class="why small" style="margin-top:16px;opacity:.8">Conditional estimate from simulated data. Take fresh local readings before starting.</p>
      </div>
      <div class="actions">
        <a class="btn primary" href="#/map?field=${esc(nextJob.field_id)}">${icon('map')}Open on map</a>
        <button class="btn" type="button" data-explain="order" data-field="${esc(nextJob.field_id)}">${icon('chat')}Why this order?</button>
      </div>
    </section>` : `
    <section class="decision"><div><h1>No job can be proposed yet</h1>
      <p class="why">No open request has a suitable window before its deadline. Review the requests with your PCA.</p></div>
      <div class="actions"><a class="btn primary" href="#/schedule">Review requests</a></div></section>`}

    <div class="grid-2" style="margin-top:16px">
      <div class="stack">
        ${approaching.length || unscheduled.length ? `
        <section class="panel" aria-labelledby="dl-h">
          <div class="section-title"><h2 id="dl-h">Deadlines and conflicts</h2><span class="muted small">Next 24 h</span></div>
          <ul class="rows">
            ${unscheduled.map((r) => {
              const j = jobById(r.job_id);
              return `<li>${chip('STOP')}<div><div class="title">${esc(fieldName(j.field_id))} · ${esc(j.id)} unscheduled</div>
                <div class="meta">${esc(r.message)}</div>
                <div class="meta">${esc((r.details || []).slice(0, 2).join('; '))}</div></div>
                <button class="btn sm ghost" data-explain="${r.reason_code === 'equipment_conflict' ? 'equipment' : r.reason_code === 'data' ? 'missing' : 'hold'}" data-field="${esc(j.field_id)}">Why?</button></li>`;
            }).join('')}
            ${approaching.filter((x) => x.r?.scheduled).map(({ j, r, left, slack }) => `
              <li>${icon('clock')}<div><div class="title">${esc(fieldName(j.field_id))} · due ${when(j.latest_completion)}</div>
                <div class="meta ${slack != null && slack < 120 ? 'urgent' : ''}">${dur(left)} until the deadline. Planned finish ${when(r.end)}${slack != null ? `, ${dur(slack)} margin` : ''}.</div></div>
                <span class="tag">${esc(PRI[j.priority])}</span></li>`).join('')}
          </ul>
        </section>` : ''}

        <section class="panel" aria-labelledby="req-h">
          <div class="section-title"><h2 id="req-h">Treatment requests</h2><a class="small" href="#/schedule">Edit requests</a></div>
          <p class="small muted" style="margin-bottom:8px">Treatment need comes from the PCA or the spray schedule. CanopyGuard only times the work.</p>
          <div class="table-wrap"><table class="data">
            <thead><tr><th>Field</th><th>Reference</th><th>Window requested</th><th>Priority</th><th>Plan</th></tr></thead>
            <tbody>${state.jobs.filter((j) => j.status === 'open').map((j) => {
              const r = planFor(j.id); const fp = fieldProps(j.field_id);
              return `<tr><td><b>${esc(fp.name)}</b><div class="xs muted">${esc(fp.crop)} · ${fp.acres} ac</div></td>
                <td class="small">${esc(j.reference)}<div class="xs muted">${esc(productName(j.product_id))}</div></td>
                <td class="small nowrap">${when(j.earliest_start)} → <b>${when(j.latest_completion)}</b></td>
                <td><span class="tag">${esc(PRI[j.priority])}</span></td>
                <td class="small">${r?.scheduled ? `${chip('GO')}<div class="nowrap">${when(r.start)}–${hm(r.end)}</div>` : chip('STOP') + '<div>No window</div>'}</td></tr>`;
            }).join('')}</tbody></table></div>
        </section>
      </div>

      <div class="stack">
        <section class="panel" aria-labelledby="att-h">
          <div class="section-title"><h2 id="att-h">Fields needing attention</h2><span class="muted small">at ${hm(now)}</span></div>
          ${attention.length ? `<ul class="rows">${attention.map((f) => `
            <li>${chip(f.status)}<div><div class="title">${esc(fieldName(f.field_id))}</div>
              <div class="meta">${esc(f.reason.split('. ').slice(0, 2).join('. '))}</div>
              ${f.blind_spot ? `<div class="meta urgent">A 5 ft station alone would say Go. The 30 ft sensor changes the decision.</div>` : ''}
              ${f.neighbors_attention.length ? `<div class="meta">Nearby: ${esc(f.neighbors_attention.join(', '))}</div>` : ''}</div>
              <a class="btn sm ghost" href="#/map?field=${esc(f.field_id)}">Map</a></li>`).join('')}</ul>`
            : '<p class="muted">No field has an active flag at the scenario time.</p>'}
        </section>

        <section class="panel" aria-labelledby="win-h">
          <div class="section-title"><h2 id="win-h">Candidate weather windows</h2><span class="muted small">Today and tomorrow</span></div>
          ${timelines.map((tl) => ribbon(tl)).join('')}
          <div class="legend" style="margin-top:10px">
            <span><i style="background:#5E9A73"></i>No blocking flags</span><span><i style="background:#E3A33A"></i>Caution</span>
            <span><i style="background:#C9483E"></i>Stop</span><span><i style="background:repeating-linear-gradient(135deg,#B9C1C8 0 3px,#E3E7EA 3px 6px)"></i>Insufficient data</span>
          </div>
          <p class="xs muted" style="margin-top:8px">Simulated paired-height sensors. After ${hm(now)} the strip is a simulated scenario forecast, not an observation. A suitable slot still needs the full job, travel, setup and rain-free time to fit.</p>
        </section>
      </div>
    </div>
  </div>`;

}

function ribbon(tl) {
  const fp = fieldProps(tl.field_id);
  const slots = tl.slots.filter((s) => { const h = +s.time.slice(11, 13); return h >= 5 && h < 20; });
  const cells = slots.map((s) => {
    const cls = s.suitable ? 'ok' : s.status === 'INSUFFICIENT_DATA' ? 'INSUFFICIENT_DATA' : s.status === 'CAUTION' ? 'CAUTION' : 'STOP';
    return `<span class="${cls}${s.time === tl.now ? ' now' : ''}" title="${esc(s.time.slice(0, 10))} ${hm(s.time)}: ${s.suitable ? 'no blocking flags' : esc(s.cause || s.status)}"></span>`;
  }).join('');
  const goCount = slots.filter((s) => s.suitable).length;
  return `<div style="margin:10px 0 4px"><div class="small" style="display:flex;justify-content:space-between"><b>${esc(fp.name)} · ${esc(fp.crop)}</b>
    <span class="muted">${goCount ? `${dur(goCount * 15)} of suitable slots` : 'No suitable slots'}</span></div>
    <div class="ribbon" role="img" aria-label="${esc(fp.name)}: ${goCount} suitable 15-minute slots between 05:00 and 20:00 today and tomorrow">${cells}</div>
    <div class="ribbon-axis"><span>Today 05:00</span><span>12:00</span><span>20:00 · Tomorrow 05:00</span><span>12:00</span><span>20:00</span></div></div>`;
}
