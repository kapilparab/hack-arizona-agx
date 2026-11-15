import { state, chip, esc, icon, when, hm, dur, kindTag, compass, fieldProps, productName, unitName, planFor } from './core.js';
import { releaseSection, dataSupport } from './insight.js';

// ----------------------------------------------------- cross-section SVG
// Vertical slice at the sensor mast: 5 ft and 30 ft sensors, temperatures, and
// wind at each height drawn as compass dials showing where air is moving TO.
export function crossSection(a, releaseFt, canopyFt = 0) {
  const rd = a.reading;
  const W = 340, H = 236, gy = 200, top = 26;
  const agl = (lv) => (lv.ref === 'canopy' ? (canopyFt || 0) : 0) + lv.height_ft;
  const zTop = rd ? Math.max(agl(rd.upper), releaseFt || 0) * 1.2 : 36;
  const yFt = (ft) => gy - (ft / zTop) * (gy - top);
  if (!rd) {
    return `<svg class="xsec" viewBox="0 0 ${W} ${H}" role="img" aria-label="No paired-height sensor for this field">
      <rect width="${W}" height="${H}" rx="14" fill="#0B1210"/>
      <rect x="0" y="${gy}" width="${W}" height="${H - gy}" fill="#141B17"/>
      <text x="${W / 2}" y="${H / 2 - 8}" text-anchor="middle" font-size="14" font-weight="600" fill="#AAB7AF">No paired-height sensor</text>
      <text x="${W / 2}" y="${H / 2 + 12}" text-anchor="middle" font-size="11.5" fill="#74827A">Inversions cannot be detected at this field</text></svg>`;
  }
  const lo = rd.lower, up = rd.upper, dT = a.metrics.delta_t_f, u = a.metrics.delta_t_uncertainty_f;
  const inv = dT != null && dT > 0, warm = dT != null && dT > u;
  const mastX = 74;
  const dial = (cx, cy, r, from, mph, upper) => {
    if (from == null || mph == null) return `<text x="${cx}" y="${cy + 4}" text-anchor="middle" font-size="10.5" fill="#FF6B5E">missing</text>`;
    const col = upper ? '#8EC9FF' : '#7CF0BE';
    const to = (from + 180) % 360, rad = (to - 90) * Math.PI / 180, len = r - 4;
    const x2 = cx + Math.cos(rad) * len, y2 = cy + Math.sin(rad) * len, x1 = cx - Math.cos(rad) * len * .6, y1 = cy - Math.sin(rad) * len * .6;
    const hx = (ang) => [x2 + Math.cos(rad + ang) * 7, y2 + Math.sin(rad + ang) * 7];
    const [ax, ay] = hx(Math.PI * .8), [bx, by] = hx(-Math.PI * .8);
    return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="rgba(255,255,255,.04)" stroke="rgba(255,255,255,.14)"/>
      <text x="${cx}" y="${cy - r - 4}" text-anchor="middle" font-size="8.5" fill="#74827A">N</text>
      <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${col}" stroke-width="2.4" stroke-linecap="round"/>
      <path d="M${ax},${ay} L${x2},${y2} L${bx},${by}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>`;
  };
  const hl = (lv) => (lv.height_ft < 2 ? Math.round(lv.height_ft * 12) + ' in' : lv.height_ft + ' ft');
  const row = (lv, r, upper) => {
    const y = yFt(agl(lv));
    return `<rect x="${mastX - 8}" y="${y - 6}" width="16" height="12" rx="3" fill="${upper ? '#8EC9FF' : '#7CF0BE'}"/>
      <text x="${mastX - 16}" y="${y + 4}" text-anchor="end" font-size="11.5" font-weight="600" fill="#AAB7AF">${hl(lv)}</text>
      <text x="${mastX + 20}" y="${y - 2}" font-size="19" font-weight="600" fill="#EEF3EF" letter-spacing="-0.5">${r.temp_f != null ? r.temp_f.toFixed(1) + '°' : 'missing'}</text>
      <text x="${mastX + 20}" y="${y + 14}" font-size="10.5" fill="#AAB7AF">${r.wind_installed === false ? 'no wind sensor at this level' : r.wind_mph != null ? `${r.wind_mph.toFixed(1)} mph from ${compass(r.dir_from_deg)} ${Math.round(r.dir_from_deg)}° (${r.wind_height_ft < 2 ? Math.round(r.wind_height_ft * 12) + ' in' : (+r.wind_height_ft).toFixed(1) + ' ft'})` : 'wind missing'}</text>
      ${r.wind_installed === false ? '' : dial(W - 38, y, 20, r.dir_from_deg, r.wind_mph, upper)}`;
  };
  const relY = releaseFt != null ? yFt(Math.min(releaseFt, 35)) : null;
  const lidY = yFt(agl(up));
  const msg = warm ? [`Inversion lid · +${dT} °F warmer above`, '#FF8A7E'] : inv ? [`Slightly warmer above · within ±${u} °F`, '#F5B83D'] : dT != null ? [`Cooler above · no inversion (${dT} °F)`, '#46D39A'] : ['', ''];
  return `<svg class="xsec" viewBox="0 0 ${W} ${H}" role="img" aria-label="Cross-section: 5 ft ${lo.temp_f ?? 'missing'} °F, 30 ft ${up.temp_f ?? 'missing'} °F, difference ${dT ?? 'unknown'} °F">
    <defs>
      <linearGradient id="xs-air" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#0E1A22"/><stop offset="1" stop-color="#0B1311"/></linearGradient>
      <linearGradient id="xs-lid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${warm ? 'rgba(255,138,80,.38)' : inv ? 'rgba(245,184,61,.22)' : 'rgba(0,0,0,0)'}"/><stop offset="1" stop-color="rgba(0,0,0,0)"/></linearGradient>
      <pattern id="xs-crop" width="7" height="9" patternUnits="userSpaceOnUse"><path d="M3.5 9V3.5M3.5 6 1.2 3M3.5 5.2 5.8 2.4" stroke="#3E8F5E" stroke-width="1.2" fill="none"/></pattern>
    </defs>
    <rect width="${W}" height="${H}" rx="14" fill="url(#xs-air)"/>
    <rect x="0" y="${lidY - 26}" width="${W}" height="${gy - lidY + 10}" fill="url(#xs-lid)"/>
    ${warm ? `<line x1="0" y1="${lidY - 26}" x2="${W}" y2="${lidY - 26}" stroke="rgba(255,138,80,.5)" stroke-dasharray="3 4"/>` : ''}
    <text x="14" y="${top - 6}" font-size="10.5" font-weight="600" fill="${msg[1]}">${msg[0]}</text>
    <rect x="0" y="${gy - 9}" width="${W}" height="9" fill="url(#xs-crop)"/>
    <rect x="0" y="${gy}" width="${W}" height="${H - gy}" fill="#16120C"/>
    <line x1="${mastX}" y1="${gy}" x2="${mastX}" y2="${yFt(agl(up) * 1.06)}" stroke="#DDE7E1" stroke-width="2" stroke-linecap="round"/>
    ${relY != null ? `<line x1="10" y1="${relY}" x2="${mastX - 10}" y2="${relY}" stroke="#FFD166" stroke-width="1.4" stroke-dasharray="4 3"/>
      <text x="10" y="${H - 12}" font-size="9" fill="#FFD166">- - release height ${releaseFt < 3 ? (releaseFt * 12).toFixed(0) + ' in' : releaseFt.toFixed(1) + ' ft'} above ground</text>` : ''}
    ${canopyFt && (lo.ref === 'canopy') ? `<rect x="0" y="${yFt(canopyFt)}" width="${W}" height="${gy - yFt(canopyFt)}" fill="rgba(62,143,94,.25)"/><text x="${W - 10}" y="${yFt(canopyFt) - 3}" text-anchor="end" font-size="9" fill="#7FBF95">canopy ${canopyFt} ft</text>` : ''}
    ${row(up, up, true)}${row(lo, lo, false)}
    <text x="${W - 10}" y="${H - 11}" text-anchor="end" font-size="9" fill="#74827A">arrows: where air moves</text>
  </svg>`;
}

const SICON = { GO: 'go', CAUTION: 'caution', STOP: 'stop', INSUFFICIENT_DATA: 'nodata' };
const sdot = (st) => `<span class="sdot ${esc(st)}" aria-hidden="true">${icon(SICON[st] || 'nodata', 'sm')}</span>`;
export const askRows = (fid, items) => `<div class="ask">${items.map(([topic, ic, label, hint]) =>
  `<button type="button" class="ask-row" data-explain="${topic}" data-field="${esc(fid)}">
     <span class="ask-ic">${icon(ic, 'sm')}</span><span class="ask-t">${esc(label)}${hint ? `<span>${esc(hint)}</span>` : ''}</span>
     <svg class="ic sm ask-go" aria-hidden="true"><use href="#i-chev"/></svg></button>`).join('')}</div>`;

// ------------------------------------------------------------ status panel
export function statusPanel(a, fp, releaseFt, live) {
  const m = a.metrics, rd = a.reading, g = a.ground_only, pv = a.provenance;
  const flagged = a.checks;
  const job = state.jobs.find((j) => j.field_id === fp.id && j.status === 'open');
  const r = job && planFor(job.id);
  return `
  <div class="side-sec">
    <div class="status-head"><div><h2 style="margin:0">${esc(fp.name)}</h2>
      <div class="small muted">${esc(fp.crop)} · ${fp.acres} ac · ${esc(fp.grower)}</div></div>${chip(a.status, 'lg')}</div>
    <p class="reason"><b>${esc(a.headline)}.</b> ${esc(a.reason)}</p>
    <div class="small muted">${kindTag(pv.kind)} Reading ${pv.observed_at ? when(pv.observed_at) + ' MST' : 'unavailable'} · viewed ${when(a.time)} ${m.age_min != null ? `· ${Math.round(m.age_min)} min old` : ''}</div>
    <div class="compare">
      <div><div class="k">Single low station only</div>${chip(g.status)}</div>
      <div><div class="k">Paired-height mast</div>${chip(a.status)}</div>
      ${a.blind_spot ? `<div class="blind">${icon('caution', 'sm')} Ground-only reading looks acceptable. The upper sensor exposes the problem.</div>` : ''}
    </div>
    ${askRows(fp.id, [['hold', 'chat', 'Explain this status', 'Plain-language reason, English or Spanish'],
      ['neighbors', 'pin', 'Which neighbors need attention?', ''], ['missing', 'info', 'What information is missing?', '']])}
  </div>
  <div class="side-sec">
    <h3>At the sensor mast</h3>
    <p class="xs muted" style="margin:-4px 0 8px">${esc(a.metrics.config_name || '')}${a.metrics.pair_label ? ' · ' + esc(a.metrics.pair_label) : ''}</p>
    ${crossSection(a, releaseFt, fp.canopy_ft)}
    <dl class="kv" style="margin-top:8px">
      <dt>Upper minus lower</dt><dd>${m.delta_t_f != null ? `${m.delta_t_f > 0 ? '+' : ''}${m.delta_t_f} °F ± ${m.delta_t_uncertainty_f}` : '—'}</dd>
      <dt>Speed difference</dt><dd>${m.speed_diff_mph != null ? m.speed_diff_mph + ' mph' : '—'}</dd>
      <dt>Direction difference</dt><dd>${m.dir_diff_deg != null ? m.dir_diff_deg + '°' + (m.dir_comparison_reliable ? '' : ' (calm: unreliable)') : '—'}</dd>
      <dt>Source</dt><dd>${esc(pv.source || 'None')}</dd>
    </dl>
    <details style="margin-top:8px"><summary>More conditions</summary>
      <dl class="kv"><dt>Gust (5 ft)</dt><dd>${rd?.lower.gust_mph != null ? rd.lower.gust_mph + ' mph<span class="demo-note"> (simulated)</span>' : '—'}</dd>
      <dt>Humidity</dt><dd>${rd?.rh_pct != null ? rd.rh_pct + ' %' : '—'}</dd>
      <dt>Rain probability</dt><dd>${rd?.rain_prob_pct != null ? rd.rain_prob_pct + ' %<span class="demo-note"> (simulated forecast)</span>' : '—'}</dd>
      <dt>Rule version</dt><dd>${esc(a.rule_version)}</dd></dl></details>
  </div>
  ${releaseSection(a)}
  <div class="side-sec">
    <h3>Checks</h3>
    <ul class="checklist">${flagged.map((c) => `<li class="ck ${esc(c.status)}">${sdot(c.status)}<div class="ck-b"><div class="ck-h"><b>${esc(c.label)}</b><span class="ck-v">${esc(c.measured)}</span></div>
      <div class="small">${esc(c.reason)}</div><div class="src">Threshold ${esc(c.threshold)} · ${esc(c.threshold_source)}</div></div></li>`).join('')}</ul>
  </div>
  <div class="side-sec">
    <h3>Sensitive areas nearby</h3>
    ${a.neighbors.length ? `<ul class="checklist">${a.neighbors.map((n) => `<li class="ck">${sdot(n.blocking ? 'STOP' : n.attention ? 'CAUTION' : 'GO')}
      <div><b>${esc(n.name)}</b><div class="small">${n.distance_ft} ft to the ${compass(n.bearing_deg)} · ${esc(n.kind.replace('_', ' '))}</div>
      ${Object.values(n.downwind).filter(Boolean).map((d) => `<div class="xs muted">${d.height_ft} ft: wind from ${compass(d.from_deg)} ${Math.round(d.from_deg)}°, air moving toward ${compass(d.toward_deg)} ${Math.round(d.toward_deg)}°${d.toward_area ? ' (toward this area)' : ''}</div>`).join('')}
      ${n.notes.map((t) => `<div class="xs">${esc(t)}</div>`).join('')}</div></li>`).join('')}</ul>
      <p class="xs muted" style="margin-top:6px">Attention check from wind direction and distance only. Not an exposure, deposition or safe-distance prediction.</p>`
      : '<p class="small muted">No marked area within the attention radius.</p>'}
  </div>
  ${dataSupport(a, live)}
  ${job ? `<div class="side-sec"><h3>Treatment request</h3>
    <dl class="kv"><dt>Reference</dt><dd>${esc(job.reference)}</dd><dt>Product</dt><dd>${esc(productName(job.product_id))}</dd>
    <dt>Window</dt><dd>${when(job.earliest_start)} → ${when(job.latest_completion)}</dd>
    <dt>Plan</dt><dd>${r?.scheduled ? `${when(r.start)}–${hm(r.end)} with ${esc(unitName(r.unit_id))}` : 'No suitable window found before the requested deadline - review with your PCA.'}</dd></dl>
    <div style="margin-top:12px">${askRows(fp.id, [['rain', 'rain', 'Can it finish before the forecast rain?', ''], ['order', 'schedule', 'Why this job order?', '']])}</div></div>` : ''}`;
}

// ----------------------------------------------------------- equipment
const FIELD_META = {
  nozzle_id: ['Nozzle / atomizer', null], orifice_size: ['Tip size code', 'e.g. 04 = 0.4 gpm at 40 psi'], pressure_psi: ['Pressure', 'psi'],
  nozzle_spacing_in: ['Nozzle spacing', 'in'], speed_mph: ['Ground speed', 'mph'], rate_gpa: ['Application rate', 'GPA'],
  boom_height_in: ['Boom release height', 'in above target'], swath_ft: ['Swath', 'ft'], tank_gal: ['Tank', 'gal'],
  refill_min: ['Refill time', 'min'], setup_min: ['Setup time', 'min'], turn_s: ['Headland turn', 's'],
  droplet_class_entered: ['Droplet class (from manufacturer chart)', 'operator-entered'], row_spacing_ft: ['Row spacing', 'ft'],
  fan_setting: ['Fan setting', null], droplet_um: ['Atomizer droplet setting', 'µm'], flow_l_min: ['Flow', 'L/min'],
  swath_m: ['Swath', 'm'], speed_m_s: ['Max flight speed', 'm/s'], height_m: ['Application height', 'm above target'],
  rate_l_ha: ['Application rate', 'L/ha'], tank_l: ['Tank', 'L'], battery_swap_min: ['Battery swap', 'min'],
};

export function equipmentPanel(ev, cat, unitId, opts = {}) {
  const types = ['ground_boom', 'airblast', 'drone', 'aircraft', 'chemigation'];
  const unitByType = Object.fromEntries(cat.units.map((u) => [u.type, u]));
  const cards = types.map((t) => {
    const et = cat.equipment_types[t]; const u = unitByType[t];
    const sel = u && u.id === unitId;
    return `<button type="button" class="eq-card" data-eq-type="${t}" aria-pressed="${sel}" ${et.unsupported ? 'data-unsupported' : ''}>
      ${et.illustration ? `<img src="${esc(et.illustration)}" alt="">` : ''}
      <span class="n">${esc(et.name.replace(' (optional extension)', ''))}</span>
      <span class="s">${u ? esc(u.name) : 'Not supported'}</span></button>`;
  }).join('');
  if (!ev) return opts.noCards ? '' : `<div class="eq-cards">${cards}</div>`;
  const cfg = ev.config, ti = ev.type_info;
  const nozzles = cat.nozzles;
  const inputs = Object.keys(cfg).map((k) => {
    const [label, hint] = FIELD_META[k] || [k, null];
    let control;
    if (k === 'nozzle_id') {
      control = `<select data-cfg="${k}">${Object.entries(nozzles).map(([id, n]) => `<option value="${id}" ${id === cfg[k] ? 'selected' : ''}>${esc(n.model)}${n.compatible_with.includes(ev.unit.type) ? '' : ' (not compatible)'}</option>`).join('')}</select>`;
    } else if (k === 'droplet_class_entered') {
      control = `<select data-cfg="${k}"><option value="">Not entered</option>${cat.asabe.classes.map((c) => `<option value="${c}" ${c === cfg[k] ? 'selected' : ''}>${c} - ${esc(cat.asabe.names[c])}</option>`).join('')}</select>`;
    } else if (k === 'fan_setting' || k === 'orifice_size') {
      control = `<input type="text" data-cfg="${k}" value="${esc(cfg[k] ?? '')}">`;
    } else {
      control = `<input type="number" step="any" min="0" data-cfg="${k}" value="${esc(cfg[k] ?? '')}">`;
    }
    return `<div class="field"><label>${esc(label)}${hint ? ` <span class="muted">(${esc(hint)})</span>` : ''}</label>${control}</div>`;
  }).join('');
  const est = ev.estimate;
  return `
    ${opts.noCards ? '' : `<div class="eq-cards">${cards}</div>`}
    <p class="xs muted" style="margin-top:6px">${esc(ti.illustration_note || '')}${ti.reference ? ` · <a href="${esc(ti.reference.url)}" target="_blank" rel="noopener">${esc(ti.reference.model)} source</a>. ${esc(ti.reference.note)}` : ''}</p>
    ${ti.advisor ? `<p class="xs" style="margin-top:4px">${esc(ti.advisor.note)} <a href="${esc(ti.advisor.url)}" target="_blank" rel="noopener">${esc(ti.advisor.name)}</a></p>` : ''}
    <div style="margin:10px 0 6px;display:flex;align-items:center;gap:8px;justify-content:space-between">
      <b>${esc(ev.unit.name)}</b>${ev.compatible ? '<span class="tag">Candidate</span>' : chip('STOP')}</div>
    <div class="issues">${ev.issues.filter((i) => i.severity !== 'info' || i.code === 'droplet_ok').map((i) => `<div class="issue ${i.severity}">
      ${icon(i.severity === 'block' ? 'stop' : i.severity === 'warn' ? 'caution' : 'info', 'sm')}<div>${esc(i.message)}${i.source ? `<span class="src">${esc(i.source)}</span>` : ''}</div></div>`).join('')}</div>
    <div class="issue warn">${icon('info', 'sm')}<div>${esc(ev.weather_note)}${ev.weather_status ? ` Weather now: <b>${esc(ev.weather_status.status.replace('_', ' '))}</b>.` : ''}</div></div>
    ${est ? `<div style="margin-top:10px"><b>Estimated job time ${dur(est.total_min)}</b> <span class="xs muted">+ ${est.setup_min} min setup and travel</span>
      <dl class="kv" style="margin-top:4px"><dt>Spraying</dt><dd>${dur(est.spray_min)}</dd><dt>Turns</dt><dd>${dur(est.turn_min)}</dd>
      <dt>Non-spray moves</dt><dd>${dur(est.transit_min)}</dd><dt>Refills${ev.unit.type === 'drone' ? ' + batteries' : ''}</dt><dd>${dur(est.reload_min)} (${est.loads} load${est.loads > 1 ? 's' : ''}, ${esc(est.volume)})</dd>
      <dt>Treated</dt><dd>${ev.path.treated_acres} of ${ev.path.field_acres} ac${ev.path.excluded_acres ? `, ${ev.path.excluded_acres} ac excluded` : ''}</dd></dl>
      <p class="xs muted">${esc(est.basis)} ${esc(est.notes.join(' '))}</p></div>` : ''}
    ${ev.pressure ? `<p class="xs" style="margin-top:6px">Calibration: ${ev.pressure.required_gpm} gpm per nozzle needed, about ${ev.pressure.required_psi} psi for this tip size. ${esc(ev.pressure.basis)}</p>` : ''}
    <details style="margin-top:8px" open><summary>Configuration</summary><div class="form-grid" style="grid-template-columns:1fr 1fr;margin-top:6px">${inputs}</div>
      <p class="xs muted" style="margin-top:6px">${esc(ev.config_source)}</p></details>
    <details style="margin-top:8px"><summary>Compare nozzles / atomizers</summary>
      <p class="small" style="margin:6px 0">${esc(ev.recommendation.message)}</p>
      ${ev.candidates.map((n) => `<div class="nozzle"><img src="${esc(n.illustration)}" alt=""><div><b>${esc(n.model)}</b>${n.selected ? ' <span class="tag">Selected</span>' : ''}
        <div class="xs muted">${esc(n.illustration_note)}</div><div class="small">${esc(n.tradeoff)}</div>
        <div class="xs">Missing: ${esc(n.missing.join('; ') || 'nothing')} · <a href="${esc(n.source)}" target="_blank" rel="noopener">Source</a></div></div></div>`).join('')}
      ${ev.unit.type === 'drone' ? '<p class="xs" style="margin-top:6px">TeeJet tractor tips are listed under the ground boom only. They are not interchangeable with drone atomizers.</p>' : ''}
    </details>`;
}
