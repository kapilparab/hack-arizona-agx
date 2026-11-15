import { state, api, chip, esc, icon, when, hm, dur, minutesBetween, fieldName, fieldProps, jobById, planFor, unitName,
  productName, stateBox, loadPlan } from './core.js';

// Today is the shop-yard lineup board: jobs are strips in run order, the first one pulled out.
const PRI = { high: 'High', medium: 'Medium', normal: 'Normal', low: 'Low' };
const STATUS_ICON = { GO: 'go', CAUTION: 'caution', STOP: 'stop', INSUFFICIENT_DATA: 'nodata' };

const magnet = (status, label) => `<span class="magnet ${status}" aria-hidden="true">${label != null ? `<b>${label}</b>` : icon(STATUS_ICON[status] || 'nodata')}</span>`;
const letter = (jid) => jobById(jid)?.field_id || jid;
const isToday = (iso) => iso.slice(0, 10) === state.meta.scenario.day0.slice(0, 10);
const shortDay = (iso) => (isToday(iso) ? '' : ` <span class="day">${esc(when(iso).split(' ')[0].toLowerCase())}</span>`);

export async function renderToday(root) {
  root.innerHTML = `<div class="page lineup-page"><div class="skeleton" style="height:56px;max-width:420px"></div>
    <div class="lineup-grid" style="margin-top:20px"><div class="skeleton" style="height:420px"></div><div class="skeleton" style="height:420px"></div></div></div>`;
  let all, plan, timelines;
  try {
    [all, plan] = await Promise.all([api('/api/assess/all?time=' + encodeURIComponent(state.meta.scenario.now)), loadPlan()]);
    timelines = await Promise.all(state.fields.fields.features.map((f) => api('/api/timeline?field_id=' + f.properties.id)));
  } catch (e) {
    root.innerHTML = `<div class="page lineup-page">${stateBox('error', 'Today could not load', e.message, '<button class="btn sm" style="margin-top:8px" onclick="location.reload()">Reload</button>')}</div>`;
    return;
  }
  const now = state.meta.scenario.now;
  const sched = plan.jobs.filter((r) => r.scheduled).sort((a, b) => a.start.localeCompare(b.start));
  const [next, ...rest] = sched;
  const unscheduled = plan.jobs.filter((r) => !r.scheduled);
  const rescued = plan.default.unscheduled.filter((j) => plan.chosen.scheduled.includes(j));
  const reorder = plan.chosen.order.join() !== plan.default.order.join() && rescued.length;
  const open = state.jobs.filter((j) => j.status === 'open');
  const attention = all.fields.filter((f) => f.status !== 'GO' || f.neighbors_attention.length);
  const blind = attention.filter((f) => f.blind_spot);
  const statusOf = Object.fromEntries(all.fields.map((f) => [f.field_id, f.status]));
  const dateLabel = new Date(state.meta.scenario.day0).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'America/Phoenix' });

  root.innerHTML = `
  <div class="page lineup-page">
    <header class="board-head">
      <div>
        <h1>Lineup <span class="date">${esc(dateLabel)}</span></h1>
        <p class="sub"><span class="clockline">${icon('clock', 'sm')}${hm(now)} MST</span> · ${open.length} open requests <span class="tag sim">Simulated scenario</span></p>
      </div>
      <div class="btn-row head-actions">
        <a class="btn" href="#/map">${icon('map')}Field map</a>
        <a class="btn" href="#/schedule">${icon('schedule')}Full schedule</a>
      </div>
    </header>

    <div class="lineup-grid">
      <section class="board" aria-labelledby="lineup-h">
        <h2 id="lineup-h" class="sr">Lineup in run order</h2>
        ${reorder ? `<p class="marker-note">${icon('swap', 'sm')}<span>Reordered. Request order <span class="nowrap">${esc(plan.default.order.map(letter).join(' → '))}</span> would leave ${esc(rescued.map((j) => fieldName(letter(j))).join(', '))} without a window.</span></p>` : ''}

        ${next ? leadStrip(next, now, statusOf) : `
        <div class="strip lead empty">${magnet('STOP')}<div class="strip-body">
          <p class="strip-name">No job can be proposed yet</p>
          <p class="strip-meta">No open request has a suitable window before its deadline. Review the requests with your PCA.</p>
          <div class="lead-actions"><a class="btn primary" href="#/schedule">Review requests</a></div></div></div>`}

        ${rest.length ? `<h3 class="slot">Then</h3>
        <ol class="strips" start="2">${rest.map((r, i) => laterStrip(r, i + 2, statusOf)).join('')}</ol>` : ''}

        ${unscheduled.length ? `<h3 class="slot">Off the board</h3>
        <ul class="strips">${unscheduled.map((r) => offStrip(r)).join('')}</ul>` : ''}
      </section>

      <div class="side">
        <section class="side-block" aria-labelledby="att-h">
          <div class="block-title"><h2 id="att-h">Fields needing attention</h2><span class="muted small">at ${hm(now)}</span></div>
          ${blind.length ? `<p class="marker-note">${icon('temp', 'sm')}<span>Inversion on ${esc(blind.map((f) => fieldName(f.field_id)).join(', '))}: fine droplets can stay suspended in the stable layer. A 5 ft station alone would say Go there.</span></p>` : ''}
          ${attention.length ? `<ul class="flags">${attention.map((f) => `
            <li>${chip(f.status)}<div>
              <p class="flag-name">${esc(fieldName(f.field_id))}</p>
              <p class="flag-meta">${esc(f.reason.split('. ')[0].replace(/\.$/, ''))}.</p>
              ${f.neighbors_attention.length ? `<p class="flag-meta">Nearby: ${esc(f.neighbors_attention.join(', '))}</p>` : ''}</div>
              <a class="btn sm ghost" href="#/map?field=${esc(f.field_id)}" aria-label="Open ${esc(fieldName(f.field_id))} on the map">Map</a></li>`).join('')}</ul>`
            : '<p class="muted">No field has an active flag at the scenario time.</p>'}
        </section>

        <section class="side-block" aria-labelledby="win-h">
          <div class="block-title"><h2 id="win-h">Weather windows</h2><span class="muted small">Today and tomorrow, 05:00–20:00</span></div>
          ${timelines.map((tl) => ribbon(tl)).join('')}
          <div class="legend">
            <span><i class="sw ok"></i>No blocking flags</span><span><i class="sw CAUTION"></i>Caution</span>
            <span><i class="sw STOP"></i>Stop</span><span><i class="sw INSUFFICIENT_DATA"></i>Insufficient data</span>
          </div>
          <p class="xs muted demo-note">Simulated paired-height sensors. After ${hm(now)} the strip is a simulated scenario forecast, not an observation.</p>
          <p class="xs muted">A suitable slot still needs the full job, travel, setup and rain-free time to fit.</p>
        </section>
      </div>
    </div>

    <section class="requests" aria-labelledby="req-h">
      <div class="block-title"><h2 id="req-h">Treatment requests</h2><a class="small" href="#/schedule">Edit requests</a></div>
      <p class="small muted req-note">Treatment need comes from the PCA or the spray schedule. CanopyGuard only times the work.</p>
      <table class="req-table">
        <thead><tr><th scope="col">Field</th><th scope="col">Reference</th><th scope="col">Window requested</th><th scope="col">Priority</th><th scope="col">Plan</th></tr></thead>
        <tbody>${open.map((j) => {
          const r = planFor(j.id); const fp = fieldProps(j.field_id);
          return `<tr>
            <td data-label="Field"><b>${esc(fp.name)}</b><span class="xs muted">${esc(fp.crop)} · ${fp.acres} ac</span></td>
            <td data-label="Reference">${esc(j.reference)}<span class="xs muted">${esc(productName(j.product_id))}</span></td>
            <td data-label="Window" class="nowrap">${when(j.earliest_start)} → <b>${when(j.latest_completion)}</b></td>
            <td data-label="Priority"><span class="pri ${esc(j.priority)}">${esc(PRI[j.priority])}</span></td>
            <td data-label="Plan">${r?.scheduled ? `<span class="plan-ok">${icon('go', 'sm')}${when(r.start)}–${hm(r.end)}</span>` : `<span class="plan-no">${icon('stop', 'sm')}No window</span>`}</td></tr>`;
        }).join('')}</tbody></table>
    </section>
  </div>`;

}

function leadStrip(r, now, statusOf) {
  const j = jobById(r.job_id); const fp = fieldProps(j.field_id);
  const margin = minutesBetween(r.end, j.latest_completion);
  const rainH = state.catalog?.products[j.product_id]?.constraints?.rainfast_h?.value;
  // to-scale bar: depart → max(deadline, end of rain-free interval)
  const t0 = r.depart;
  const rainEnd = rainH ? new Date(new Date(r.end).getTime() + rainH * 3600000).toISOString() : r.end;
  const tEnd = [j.latest_completion, rainEnd].sort((a, b) => new Date(a) - new Date(b))[1];
  const span = Math.max(1, minutesBetween(t0, tEnd));
  const pct = (m) => `${(Math.max(0, m) / span) * 100}%`;
  const deadlineAt = (minutesBetween(t0, j.latest_completion) / span) * 100;
  return `
  <article class="strip lead" aria-labelledby="lead-h">
    ${magnet('GO', 1)}
    <div class="strip-body">
      <div class="lead-top">
        <div>
          <h3 id="lead-h" class="strip-name">${esc(fp.name)}</h3>
          <p class="strip-meta">${esc(fp.crop)} · ${fp.acres} ac · <span class="nowrap">${esc(unitName(r.unit_id))}</span></p>
        </div>
        <p class="lead-time"><span class="sr">Starts </span>${hm(r.start)}${shortDay(r.start)}</p>
      </div>
      ${nowLine(j.field_id, statusOf, r)}
      <dl class="cells">
        <div><dt>Leave yard</dt><dd>${hm(r.depart)}</dd></div>
        <div><dt>Starts in</dt><dd>${dur(minutesBetween(now, r.start))}</dd></div>
        <div><dt>Travel + setup</dt><dd>${r.travel_min + r.setup_min} min</dd></div>
        <div><dt>Spray done</dt><dd>${hm(r.end)}</dd></div>
        <div><dt>Deadline</dt><dd>${hm(j.latest_completion)}</dd></div>
        <div><dt>Margin</dt><dd class="${margin < 120 ? 'urgent' : ''}">${margin >= 0 ? dur(margin) : 'Late'}</dd></div>
      </dl>
      <div class="scale" role="img" aria-label="To scale from ${hm(t0)}: ${r.travel_min} min travel, ${r.setup_min} min setup, ${r.duration_min} min spraying${rainH ? `, then ${rainH} h rain-free` : ''}; deadline ${hm(j.latest_completion)}.">
        <div class="scale-bar">
          <i class="travel" style="width:${pct(r.travel_min)}"></i><i class="setup" style="width:${pct(r.setup_min)}"></i><i class="wait" style="width:${pct(minutesBetween(t0, r.start) - r.travel_min - r.setup_min)}"></i><i class="spray" style="width:${pct(r.duration_min)}"></i>${rainH ? `<i class="rain" style="width:${pct(rainH * 60)}"></i>` : ''}
          <span class="deadline" style="left:${deadlineAt}%"></span>
        </div>
        <div class="scale-key"><span><i class="travel"></i>Travel<span class="wide-only"> + setup</span></span><span><i class="spray"></i>Spray</span>${rainH ? `<span><i class="rain"></i>Rain-free ${rainH} h</span>` : ''}<span><i class="dl"></i>Deadline ${hm(j.latest_completion)}</span></div>
      </div>
      <p class="strip-note demo-note">Conditional estimate from simulated data. Take fresh local readings before starting.</p>
      <div class="lead-actions">
        <a class="btn primary" href="#/map?field=${esc(j.field_id)}">${icon('map')}<span>Open<span class="wide-only"> ${esc(fp.name)}</span> on map</span></a>
        <button class="btn" type="button" data-explain="order" data-field="${esc(j.field_id)}">${icon('chat')}Why this order?</button>
      </div>
    </div>
  </article>`;
}

// Current flag vs the planned window, in words, so a planned job never sits beside an unexplained Stop.
function nowLine(fid, statusOf, r) {
  const st = statusOf[fid] || 'INSUFFICIENT_DATA';
  const day = isToday(r.start) ? '' : ' ' + esc(when(r.start).split(' ')[0].toLowerCase());
  return `<p class="nowline">${chip(st)}<span>now · planned ${hm(r.start)}–${hm(r.end)}${day}: <span class="nowrap">no blocking flags</span></span></p>`;
}

function laterStrip(r, n, statusOf) {
  const j = jobById(r.job_id); const fp = fieldProps(j.field_id);
  const slack = minutesBetween(r.end, j.latest_completion);
  return `<li><a class="strip" href="#/map?field=${esc(j.field_id)}">
    ${magnet('GO', n)}
    <div class="strip-body">
      <p class="strip-name">${esc(fp.name)} <span class="crop">${esc(fp.crop)}</span></p>
      <p class="strip-meta">Leave ${hm(r.depart)} · done ${hm(r.end)} · <span class="nowrap">due ${when(j.latest_completion)}</span>${slack < 120 ? ` · <span class="urgent">${dur(slack)} margin</span>` : ''}</p>
      ${nowLine(j.field_id, statusOf, r)}
    </div>
    <p class="strip-time">${hm(r.start)}${shortDay(r.start)}</p>
  </a></li>`;
}

function offStrip(r) {
  const j = jobById(r.job_id); const fp = fieldProps(j.field_id);
  const kind = r.reason_code === 'equipment_conflict' ? 'equipment' : r.reason_code === 'data' ? 'missing' : 'hold';
  return `<li><div class="strip off">
    ${magnet('STOP')}
    <div class="strip-body">
      <p class="strip-name">${esc(fp.name)} <span class="crop">${esc(fp.crop)}</span></p>
      <p class="strip-meta">${esc(r.message)}</p>
      ${(r.details || []).slice(0, 2).map((d) => `<p class="strip-meta dim">${esc(d)}</p>`).join('')}
    </div>
    <button class="btn sm" type="button" data-explain="${kind}" data-field="${esc(j.field_id)}">Why?</button>
  </div></li>`;
}

function ribbon(tl) {
  const fp = fieldProps(tl.field_id);
  const slots = tl.slots.filter((s) => { const h = +s.time.slice(11, 13); return h >= 5 && h < 20; });
  const cells = slots.map((s) => {
    const cls = s.suitable ? 'ok' : s.status === 'INSUFFICIENT_DATA' ? 'INSUFFICIENT_DATA' : s.status === 'CAUTION' ? 'CAUTION' : 'STOP';
    return `<span class="${cls}${s.time === tl.now ? ' now' : ''}" title="${esc(s.time.slice(0, 10))} ${hm(s.time)}: ${s.suitable ? 'no blocking flags' : esc(s.cause || s.status)}"></span>`;
  }).join('');
  const goCount = slots.filter((s) => s.suitable).length;
  return `<div class="win">
    <p class="win-head"><b>${esc(fp.name)}</b> <span class="muted">${esc(fp.crop)}</span><span class="win-sum">${goCount ? `${dur(goCount * 15)} suitable` : 'No suitable slots'}</span></p>
    <div class="ribbon" role="img" aria-label="${esc(fp.name)}: ${goCount} suitable 15-minute slots between 05:00 and 20:00 today and tomorrow">${cells}</div>
    <div class="ribbon-axis"><span>05:00</span><span>12:00</span><span class="split">Tomorrow 05:00</span><span>12:00</span><span>20:00</span></div></div>`;
}
