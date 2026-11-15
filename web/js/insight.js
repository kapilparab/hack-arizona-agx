// Evidence and planning panels built only from engine/API outputs.
import { state, esc, icon, when, hm, dur, compass } from './core.js';

const tag = (s) => {
  const map = { observed: ['tag user', 'Observed'], simulated: ['tag sim', 'Simulated'], simulated_observation: ['tag sim', 'Simulated observation'],
    simulated_forecast: ['tag sim', 'Simulated forecast'], forecast: ['tag model', 'Forecast'], model: ['tag model', 'Model estimate'],
    estimated: ['tag model', 'Estimated'], experimental: ['tag model', 'Experimental'], interpolated: ['tag', 'Interpolated'], operator: ['tag user', 'Operator-entered'] };
  const [c, l] = map[s] || ['tag', s];
  return `<span class="${c}">${esc(l)}</span>`;
};
const hft = (ft) => (ft == null ? '—' : ft < 2 ? `${Math.round(ft * 12)} in` : `${(+ft).toFixed(ft < 10 ? 1 : 0)} ft`);

// --------------------------------------------------------- release height
export function releaseSection(a) {
  const r = a.at_release;
  if (!r) return '';
  if (r.status !== 'ok') return `<div class="side-sec"><h3>At the release height</h3><p class="small muted">${esc(r.reason || 'Unavailable')}</p></div>`;
  const t = r.temperature, w = r.wind;
  return `<div class="side-sec"><h3>At the release height · ${esc(r.unit || '')}</h3>
    <div class="value-grid">
      <div><div class="k">Release height</div><div class="v">${hft(r.release.agl_ft)}<small> AGL</small></div><div class="s">${esc(r.release.value)}</div></div>
      <div><div class="k">Air temperature there</div><div class="v">${t.value_f != null ? t.value_f.toFixed(1) + '<small>°F</small>' : '—'}</div>
        <div class="s">${t.status === 'interpolated' ? 'Interpolated between installed sensors' : esc(t.reason || t.status)}</div></div>
      <div style="grid-column:1/-1"><div class="k">Wind there (estimate)</div><div class="v">${w.value_mph != null ? w.value_mph.toFixed(1) + '<small>mph</small>' : '—'}</div>
        <div class="s">${esc(w.method || w.reason || '')}${w.from_levels ? ` from ${esc(w.from_levels)}` : ''}${w.roughness ? ` · d ${w.roughness.d_ft} ft, z₀ ${w.roughness.z0_ft} ft` : ''}</div>
        <div class="s" style="color:${w.status === 'estimated_unreliable' ? 'var(--caution)' : 'inherit'}">${esc(w.validity || '')}</div></div>
    </div>
    ${r.spray_plane?.status === 'ok' ? `<div class="table-wrap" style="margin-top:10px"><table class="data"><thead><tr><th>Above release</th><th>ΔT</th><th>Wind change</th></tr></thead><tbody>
      ${r.spray_plane.rows.map((x) => `<tr><td>+${x.offset_m} m <span class="xs muted">(${x.height_agl_ft} ft AGL)</span></td>
        <td>${x.dt_f == null ? '<span class="xs muted">outside measured range</span>' : `<b style="color:${x.dt_f > 0 ? 'var(--stop)' : 'inherit'}">${x.dt_f > 0 ? '+' : ''}${x.dt_f} °F</b>`}</td>
        <td>${x.speed_change_mph == null ? '<span class="xs muted">not available</span>' : `${x.speed_change_mph > 0 ? '+' : ''}${x.speed_change_mph} mph, ${x.dir_change_deg}°`}</td></tr>`).join('')}</tbody></table></div>
      <p class="value-basis">Spray plane: ${esc(r.spray_plane.method)}. ${esc(r.spray_plane.note)} Warmer air above the release height means droplets are released under a stable layer.</p>` : ''}
    <p class="value-basis">${esc(r.note)} Wind method: FAO-56 logarithmic profile (d = ⅔h, z₀ = 0.123h).</p></div>`;
}

// ------------------------------------------------------- versioned decision
export const decisionTag = (id, rule) => (id ? `<span class="dec-id" title="One versioned decision: the same ID appears on the map, status, schedule, explanation and record">${icon('info', 'sm')}Decision <code>${esc(id)}</code>${rule ? ` · ${esc(rule)}` : ''}</span>` : '');

// ------------------------------------------------- developing / dissipating
const TREND_LABEL = { strengthening: 'Inversion strengthening', weakening: 'Inversion weakening', developing: 'Inversion may be developing',
  mixing: 'Mixing increasing', uncertain: 'No clear trend' };
export function trendSection(a) {
  const tc = a.metrics?.trend_class;
  if (!tc) return '';
  const warn = tc.class === 'strengthening' || tc.class === 'developing';
  const persist = a.checks.find((c) => c.id === 'inversion_persistence');
  return `<div class="trend ${warn ? 'warn' : ''}"><div class="k">Trend over successive paired readings</div>
    <b>${esc(TREND_LABEL[tc.class] || tc.class)}</b><p class="small">${esc(tc.text)}</p>
    ${persist ? `<p class="small" style="color:var(--caution)">${esc(persist.reason)}</p>` : ''}
    <p class="xs muted">Rules (prototype): an inversion clears only after 2 consecutive readings without it; an active alert clears only after 2 consecutive clean checks; sunrise or a better forecast never clears a measured inversion.</p></div>`;
}

// ------------------------------------------------- vertical height references
export function heightRefs(a, fp, releaseFt) {
  const rd = a.reading;
  if (!rd) return '';
  const can = fp.canopy_ft ?? 0, terr = a.field_terrain?.status === 'ok' ? a.field_terrain.mean_m * 3.2808 : null;
  const agl = (h, ref) => (h == null ? null : ref === 'canopy' ? h + can : h);
  const rows = [
    ['Upper temperature sensor', rd.upper.height_ft, rd.upper.ref, agl(rd.upper.height_ft, rd.upper.ref), 'Observed (simulated)'],
    ['Lower temperature sensor', rd.lower.height_ft, rd.lower.ref, agl(rd.lower.height_ft, rd.lower.ref), 'Observed (simulated)'],
    ...(rd.lower.wind_installed ? [['Wind sensor', rd.lower.wind_height_ft, rd.lower.wind_ref, agl(rd.lower.wind_height_ft, rd.lower.wind_ref), 'Observed (simulated)']] : []),
    ['Release height (spray plan)', releaseFt, 'ground', releaseFt, 'Plan input'],
    ['Crop canopy top', can, 'ground', can, 'Field record'],
  ].filter((r) => r[1] != null).sort((x, y) => y[3] - x[3]);
  const lo = agl(rd.lower.height_ft, rd.lower.ref), hi = agl(rd.upper.height_ft, rd.upper.ref);
  return `<div class="side-sec"><h3>Height references</h3>
    <div class="table-wrap"><table class="data"><thead><tr><th>Level</th><th>Above ground</th><th>Above sea level</th></tr></thead><tbody>
    ${rows.map(([n, h, ref, g, kind]) => `<tr><td>${esc(n)}<div class="xs muted">${ref === 'ground' ? '' : `${hft(h)} above ${esc(ref)} · `}${esc(kind)}</div></td><td>${hft(g)}</td>
      <td>${terr != null ? Math.round(terr + g) + ' ft' : '—'}</td></tr>`).join('')}</tbody></table></div>
    <p class="value-basis">Ground elevation ${terr != null ? `${Math.round(terr)} ft (${a.field_terrain.mean_m} m NAVD88, USGS 3DEP field mean)` : 'not loaded'}. Observed coverage is only between ${hft(lo)} and ${hft(hi)} above ground; nothing above or below the installed sensors is extrapolated.</p></div>`;
}

// ----------------------------------------------------- field observations
const OBS_LABEL = { dust_suspended: 'Dust hanging in the air', smoke_layer: 'Smoke layering', fog: 'Fog', dew: 'Dew', frost: 'Frost',
  cloud_cover: 'Cloud cover', wind_variability: 'Local wind' };
export function observationsSection(meta, list) {
  if (!meta) return `<div class="side-sec"><h3>Field observations</h3><div class="skeleton" style="height:60px"></div></div>`;
  const val = (v) => v.replace('_', ' ');
  return `<div class="side-sec"><div class="sec-title"><h2>Field observations</h2><span class="xs muted">supporting evidence</span></div>
    <form class="obs-form" data-obs-form>
      <div class="obs-grid">${Object.entries(meta.items).map(([k, opts]) => `<div class="field"><label for="obs-${k}">${esc(OBS_LABEL[k] || k)}</label>
        <select id="obs-${k}" name="${k}">${opts.slice().sort((x, y) => (x === 'not_checked' ? -1 : y === 'not_checked' ? 1 : 0)).map((o) => `<option value="${o}">${esc(val(o))}</option>`).join('')}</select></div>`).join('')}</div>
      <div class="obs-grid"><div class="field"><label for="obs-observer">Observer</label><input id="obs-observer" name="observer" type="text" placeholder="Name or role" autocomplete="name"></div>
        <div class="field"><label for="obs-notes">Notes</label><input id="obs-notes" name="notes" type="text" placeholder="Optional"></div></div>
      <button class="btn sm primary" type="submit">Record observation</button>
    </form>
    <p class="xs muted" style="margin-top:8px">${esc(meta.rules)} Everything starts as "not checked".</p>
    ${list?.length ? `<ul class="obs-list">${list.slice(0, 4).map((o) => `<li><b>${esc(o.scenario_time?.slice(11, 16) || '')}</b> ${esc(o.observer || 'Unnamed observer')}:
      ${esc(Object.entries(o.items).filter(([, v]) => v !== 'not_checked').map(([k, v]) => `${(OBS_LABEL[k] || k).toLowerCase()} ${val(v)}`).join(', ') || 'nothing checked')}</li>`).join('')}</ul>` : ''}</div>`;
}

// ------------------------------------------------- rain & surface concerns
export function surfaceSection(r) {
  if (!r?.surface) return '';
  const lab = { checked: 'Checked', noted: 'Noted', unknown: 'Unknown' };
  return `<div class="surface"><div class="k">Rain and surface concerns (checked separately)</div>
    <ul class="sf-list">${r.surface.map((s) => `<li class="sf ${esc(s.status)}"><div class="sf-h"><b>${esc(s.label)}</b><span class="sf-v">${lab[s.status] || esc(s.status)}</span></div>
      <div class="small">${esc(s.text)}</div>${s.source ? `<div class="xs muted">${esc(s.source)}</div>` : ''}</li>`).join('')}</ul></div>`;
}
export function preChecks(r) {
  if (!r?.pre_checks) return '';
  return `<details class="prechecks"><summary>Before starting: ${r.pre_checks.length} checks</summary>
    <ol class="small">${r.pre_checks.map((c) => `<li>${esc(c)}</li>`).join('')}</ol></details>`;
}

// ------------------------------------------------------------ data support
export function dataSupport(a, live) {
  const rd = a.reading, m = a.metrics, pv = a.provenance;
  const rows = [];
  if (rd) {
    for (const [name, lv] of [['Lower', rd.lower], ['Upper', rd.upper]]) {
      rows.push(`<tr><td>${name} temperature</td><td>${hft(lv.height_ft)} above ${esc(lv.ref)}</td><td>${lv.temp_f ?? '—'} °F</td><td><span class="tag sim">Sim.</span></td></tr>`);
      if (lv.wind_installed) rows.push(`<tr><td>${name} wind</td><td>${hft(lv.wind_height_ft)} above ${esc(lv.wind_ref)}</td><td>${lv.wind_mph ?? '—'} mph from ${lv.dir_from_deg ?? '—'}°</td><td><span class="tag sim">Sim.</span></td></tr>`);
    }
  }
  const liveBlock = !live ? `<button class="btn sm" type="button" data-load-live>${icon('reset', 'sm')}Load regional real data (AZMET + HRRR)</button>`
    : live.status === 'loading' ? '<div class="skeleton" style="height:120px"></div>' : liveSection(live);
  return `<div class="side-sec"><h3>Data support</h3>
    <dl class="kv"><dt>Configuration</dt><dd>${esc(m.config_name || '—')}</dd><dt>Pair</dt><dd>${esc(m.pair_label || '—')}</dd>
      <dt>Basis</dt><dd class="small">${esc(m.config_source || '—')}</dd>
      <dt>Uncertainty</dt><dd>${m.delta_t_uncertainty_f != null ? '±' + m.delta_t_uncertainty_f + ' °F combined' : '—'}</dd>
      <dt>Averaging</dt><dd>${esc(pv.averaging || 'not documented')}</dd><dt>Gust</dt><dd>${esc(pv.gust_interval || 'not documented')}</dd>
      <dt>Shielding</dt><dd>${esc(pv.shielding || 'not documented')}</dd>
      <dt>Trend</dt><dd>${m.trend ? `${m.trend.per_hour_f > 0 ? '+' : ''}${m.trend.per_hour_f} °F/h (${m.trend.points} pairs, ${m.trend.window_min} min)` : 'Not enough recent pairs'}</dd></dl>
    ${rows.length ? `<div class="table-wrap" style="margin-top:10px"><table class="data"><thead><tr><th>Variable</th><th>Installed height</th><th>Value</th><th>Status</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>` : ''}
    <p class="xs muted" style="margin:8px 0 12px">Local mast readings in this demo are simulated. Regional real data below are separate and never substitute for them.</p>
    ${liveBlock}</div>`;
}

function liveSection(e) {
  if (e.status === 'error') return `<div class="state err"><h3>Regional data unavailable</h3><p>${esc(e.message)}</p></div>`;
  const mod = e.model, mpa = e.model_profile_analysis;
  const st = (e.stations || []).map((s) => `<tr><td>${esc(s.name)} <span class="xs muted">${esc(s.id)}</span></td><td>${s.distance_km} km</td><td>${s.temp_f} °F @ ${s.height_m} m</td><td>${s.residual_f != null ? (s.residual_f > 0 ? '+' : '') + s.residual_f : '—'}</td></tr>`).join('');
  return `<div class="live">
    <p class="small"><b>Regional real data</b> · valid ${esc(when(e.valid_mst))} MST ${tag('experimental')}</p>
    ${mod ? `<dl class="kv" style="margin-top:6px"><dt>HRRR 2 m (raw)</dt><dd>${mod.t2m_f} °F ${tag('model')}</dd>
      <dt>Model cell</dt><dd>${mod.cell_distance_km} km away · ${esc(mod.resolution)}</dd><dt>Cycle</dt><dd>${esc(mod.cycle_utc.slice(0, 13))} UTC, f${String(mod.lead_h).padStart(2, '0')}</dd>
      <dt>HRRR 10 m wind</dt><dd>${mod.wind10_mph} mph from ${compass(mod.wind10_from)}</dd></dl>`
      : `<p class="small muted">HRRR unavailable: ${esc(e.model_error || '')}</p>`}
    ${st ? `<div class="table-wrap" style="margin-top:8px"><table class="data"><thead><tr><th>AZMET station</th><th>Distance</th><th>Observed</th><th>Obs − model</th></tr></thead><tbody>${st}</tbody></table></div>` : ''}
    ${e.missing?.length ? `<p class="xs muted">Missing: ${esc(e.missing.map((x) => `${x.id} (${x.reason})`).join(', '))}</p>` : ''}
    <div class="value-grid" style="margin-top:10px">
      <div><div class="k">Nearest station</div><div class="v">${e.nearest_station ? e.nearest_station.temp_f + '<small>°F</small>' : '—'}</div><div class="s">${e.nearest_station ? esc(e.nearest_station.id) + ', ' + e.nearest_station.distance_km + ' km' : ''}</div></div>
      <div><div class="k">Corrected (experimental)</div><div class="v">${e.corrected ? e.corrected.temp_f + '<small>°F</small>' : '—'}</div><div class="s">${e.corrected ? 'model + IDW residual ' + e.corrected.residual_f + ' °F' : ''}</div></div></div>
    ${mpa?.status === 'ok' ? `<div class="value-seq" style="margin-top:10px">${icon('info', 'sm')}<span><b>Model profile:</b> ${esc(mpa.regime)}${mpa.inversion_top_m ? `, top ≈ ${mpa.inversion_top_m} m AGL, +${mpa.surface_inversion_strength_f} °F` : ''}. ${esc(mpa.resolution_note)}</span></div>
      ${profileChart(mod.profile)}` : ''}
    <details style="margin-top:8px"><summary class="xs">Assumptions</summary><ul class="xs muted" style="margin:4px 0 0;padding-left:1.1em">${(e.assumptions || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></details>
    <p class="xs muted">${esc(e.local_paired_sensor_note || '')}</p></div>`;
}

function profileChart(levels) {
  if (!levels?.length) return '';
  const pts = levels.filter((l) => l.height_agl_m <= 700);
  const W = 320, H = 160, P = 30;
  const ts = pts.map((p) => p.t_f), lo = Math.min(...ts) - 1, hi = Math.max(...ts) + 1, zmax = Math.max(...pts.map((p) => p.height_agl_m));
  const X = (t) => P + (t - lo) / (hi - lo) * (W - P - 10), Y = (z) => H - 20 - z / zmax * (H - 30);
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.t_f).toFixed(1)},${Y(p.height_agl_m).toFixed(1)}`).join(' ');
  return `<svg class="xsec" viewBox="0 0 ${W} ${H}" role="img" aria-label="HRRR temperature profile by height above model ground" style="margin-top:8px;background:var(--raise)">
    <path d="${path}" fill="none" stroke="#F59A4A" stroke-width="2"/>
    ${pts.map((p) => `<circle cx="${X(p.t_f)}" cy="${Y(p.height_agl_m)}" r="3" fill="#F59A4A"/><text x="${X(p.t_f) + 6}" y="${Y(p.height_agl_m) + 3}" font-size="9" fill="currentColor" opacity=".7">${Math.round(p.height_agl_m)} m</text>`).join('')}
    <text x="${P}" y="${H - 5}" font-size="9" fill="currentColor" opacity=".7">${lo.toFixed(0)} °F</text><text x="${W - 40}" y="${H - 5}" font-size="9" fill="currentColor" opacity=".7">${hi.toFixed(0)} °F</text>
    <text x="4" y="12" font-size="9" fill="currentColor" opacity=".7">HRRR native levels, height above model ground</text></svg>`;
}

// ------------------------------------------------------------ nozzles
export function nozzleCards(ev) {
  const ne = ev?.nozzle_engine;
  if (!ne) return '';
  if (ne.status === 'not_modelled' || ne.status === 'blocked') return `<p class="small muted">${esc(ne.message)}</p>`;
  const card = (c) => `<div class="nz ${c.id === ne.recommended ? 'rec' : ''}">
    <div class="nz-h"><img src="img/nozzle-${c.family === 'AIXR' ? 'airinduction' : 'flatfan'}.svg" alt="" class="nz-img">
      <div><b>${esc(c.model)}</b>${c.id === ne.recommended ? ' <span class="opt-state rec">Recommended</span>' : c.selected ? ' <span class="tag">Configured</span>' : ''}
      <div class="xs muted">${esc(c.family_name)} · ${c.angle_deg}° · size ${esc(c.size_code)} = ${c.nominal_gpm_at_40psi} GPM @ 40 psi · illustration</div></div></div>
    <div class="nz-grid"><div><span>Required</span><b>${c.required_gpm} GPM</b></div><div><span>Expected</span><b>${c.expected_gpm} GPM</b></div>
      <div><span>Pressure</span><b>${c.proposed_psi} psi</b></div><div><span>Droplet class</span><b>${c.droplet_class ? esc(c.droplet_class_name) : 'Not documented'}</b></div></div>
    <ul class="nz-list">${c.checks.map((k) => `<li class="${k.ok ? 'ok' : 'bad'}">${icon(k.ok ? 'go' : 'stop', 'sm')}${esc(k.label)} <span class="xs muted">${esc(k.source)}</span></li>`).join('')}</ul>
    <p class="xs"><b>Why this family:</b> ${esc(c.family_fit)}</p><p class="xs"><b>Why this size:</b> ${esc(c.why_size)}</p>
    ${c.alternatives.map((x) => `<p class="xs muted">${esc(x)}</p>`).join('')}
    ${c.missing.length ? `<p class="xs muted"><b>Missing checks:</b> ${esc(c.missing.join('; '))}</p>` : ''}
    <p class="xs muted">Droplet source: ${esc(c.droplet_source)} · <a href="${esc(c.source.url)}" target="_blank" rel="noopener">${esc(c.source.title)}</a>${c.source.pages.length ? ', p.' + c.source.pages.join(', ') : ''}</p>
    <p class="xs">${esc(c.rank_reason)}</p></div>`;
  return `<p class="small">Required flow: <b>${ne.required_gpm} GPM per nozzle</b> · ${esc(ne.formula)} <span class="xs muted">(${esc(ne.formula_source)})</span></p>
    ${ne.message ? `<p class="small" style="color:var(--stop)">${esc(ne.message)}</p>` : ''}
    <div class="nz-wrap">${ne.candidates.slice(0, 4).map(card).join('')}</div>
    ${ne.notes.map((n) => `<p class="xs muted">${esc(n)}</p>`).join('')}`;
}

// ------------------------------------------------------------ spray liquid
export function liquidCard(job, ev, r) {
  if (!job) return '';
  const p = state.catalog.products[job.product_id];
  const c = p.constraints, est = ev?.estimate;
  const rf = c.rainfast_h, tr = c.temp_range_f || { value: null, source: 'Not entered' };
  const carrier = ev?.config?.rate_gpa != null ? `${ev.config.rate_gpa} gal/ac carrier volume` : ev?.config?.rate_l_ha != null ? `${ev.config.rate_l_ha} L/ha carrier volume` : 'Carrier volume not entered';
  return `<div class="side-sec"><div class="sec-title"><h2>Spray liquid</h2><span class="xs muted">${p.is_demo ? 'fictional demo product' : 'operator product'}</span></div>
    <div class="liquid">
      <div class="liquid-h">${icon('rain', 'sm')}<div><b>${esc(p.name)}</b><div class="xs muted">${esc(job.reference)}</div></div></div>
      <div class="value-grid" style="margin-top:12px">
        <div><div class="k">Carrier volume</div><div class="v" style="font-size:1rem">${esc(carrier)}</div><div class="s">Water + product mix per area. Not a chemical dose.</div></div>
        <div><div class="k">Mix for this job</div><div class="v">${est ? esc(est.volume) : '—'}</div><div class="s">${est ? `${est.loads} tank load${est.loads > 1 ? 's' : ''} · ${dur(est.reload_min)} refilling` : ''}</div></div>
        <div><div class="k">Rain-free after last pass</div><div class="v">${rf.value != null ? rf.value + '<small> h</small>' : 'Unknown'}</div><div class="s">${esc(rf.source)}</div></div>
        <div><div class="k">Air temperature range</div><div class="v" style="font-size:1rem">${tr.value ? `${tr.value[0] ?? '–'}–${tr.value[1] ?? '–'} °F` : 'Not entered'}</div><div class="s">${esc(tr.source)}</div></div>
      </div>
      ${riskProfile(c)}
      ${r?.scheduled ? `<p class="value-seq" style="margin-top:10px">${icon('schedule', 'sm')}<span>Planned ${esc(when(r.start))}–${hm(r.end)}. ${esc(r.rain_note || '')}</span></p>`
        : `<p class="value-seq" style="margin-top:10px">${icon('info', 'sm')}<span>No suitable window yet. The scheduler checks wind, temperature range and inversion every 15 min of the job, plus the rain-free interval after the last pass.</span></p>`}
      <p class="value-basis">Spraying time uses this carrier volume: total mix ÷ tank size gives refill stops, which are added to the path-based job time. Rates of chemical product are never prescribed.</p>
    </div></div>`;
}

// Product risk factors: properties that tighten the weather checks (never loosen them).
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : 'Not entered');
function riskProfile(c) {
  const v = (k) => c[k]?.value ?? null;
  const vol = v('volatility'), haz = v('off_target_hazard');
  const rules = [];
  if (vol === 'high') rules.push(`Caution from ${state.meta.thresholds.vol_high_caution_temp_f.value} °F, Stop from ${state.meta.thresholds.vol_high_stop_temp_f.value} °F air temperature`);
  if (vol === 'moderate') rules.push(`Caution from ${state.meta.thresholds.vol_moderate_caution_temp_f.value} °F air temperature`);
  if (vol === 'high' || vol === 'moderate') rules.push('a possible weak inversion counts as Stop', 'Caution when an inversion is developing');
  if (haz === 'high') rules.push('air moving toward a nearby sensitive crop counts as Stop');
  return `<div class="value-grid risk-grid" style="margin-top:12px">
      <div><div class="k">Type</div><div class="v" style="font-size:1rem">${esc(cap(v('category')))} · ${esc(cap(v('mode_of_action')))}</div><div class="s">${esc(c.mode_of_action?.source || 'Not entered')}</div></div>
      <div><div class="k">Volatility</div><div class="v" style="font-size:1rem">${esc(cap(vol))}</div><div class="s">${esc(c.volatility?.source || 'Not entered')}</div></div>
      <div><div class="k">Off-target hazard</div><div class="v" style="font-size:1rem">${esc(cap(haz))}</div><div class="s">${esc(c.off_target_hazard?.source || 'Not entered')}</div></div>
    </div>
    <p class="value-seq" style="margin-top:10px">${icon('caution', 'sm')}<span>${rules.length ? `Product risk adjustments: ${esc(rules.join('; '))}.` : vol == null ? 'Volatility not entered: vapor-drift adjustments are not applied (shown as Caution).' : 'No extra product adjustments: low volatility and no high off-target hazard.'} These only tighten checks.</span></p>`;
}

// ------------------------------------------------------------ terrain
export function terrainCard(stats, prof) {
  if (!stats) return '';
  if (stats.status !== 'ok') return `<div class="side-sec"><h3>Terrain</h3><p class="small muted">Terrain unavailable (${esc(stats.error || stats.status)}). No relief is invented.</p></div>`;
  return `<div class="side-sec"><div class="sec-title"><h2>Terrain</h2><span class="xs muted">USGS 3DEP</span></div>
    <div class="value-grid">
      <div><div class="k">Elevation</div><div class="v">${stats.mean_m}<small> m</small></div><div class="s">${stats.min_m}–${stats.max_m} m · NAVD88</div></div>
      <div><div class="k">Slope</div><div class="v">${stats.slope_mean_deg}<small>° mean</small></div><div class="s">95th pct ${stats.slope_p95_deg}° · relief ${stats.relief_m} m</div></div></div>
    ${prof ? profileSvg(prof) : '<button class="btn sm" type="button" data-load-profile style="margin-top:10px">Show elevation profile along the first pass</button>'}
    <p class="value-basis">${esc(stats.grid)} from the 3DEP Bare Earth DEM. Display resampling adds no measured detail. Terrain detail says nothing about weather-estimate accuracy.</p></div>`;
}

function profileSvg(p) {
  const pts = p.points.filter((x) => x.elevation_m != null);
  if (pts.length < 2) return '<p class="small muted">No elevation along this path.</p>';
  const W = 320, H = 120, lo = Math.min(...pts.map((x) => x.elevation_m)), hi = Math.max(...pts.map((x) => x.elevation_m));
  const span = Math.max(hi - lo, 0.5);
  const X = (d) => 8 + d / p.length_m * (W - 16), Y = (e) => H - 22 - (e - lo) / span * (H - 40);
  const line = pts.map((x, i) => `${i ? 'L' : 'M'}${X(x.d_m).toFixed(1)},${Y(x.elevation_m).toFixed(1)}`).join(' ');
  return `<svg class="xsec" viewBox="0 0 ${W} ${H}" role="img" aria-label="Elevation profile along the first pass" style="margin-top:12px;background:var(--raise)">
    <path d="${line} L${X(p.length_m)},${H - 22} L8,${H - 22} Z" fill="rgba(91,227,165,.15)"/><path d="${line}" fill="none" stroke="var(--brand)" stroke-width="2"/>
    <text x="8" y="12" font-size="9.5" fill="currentColor" opacity=".75">${hi.toFixed(2)} m</text><text x="8" y="${H - 26}" font-size="9.5" fill="currentColor" opacity=".75">${lo.toFixed(2)} m</text>
    <text x="8" y="${H - 6}" font-size="9.5" fill="currentColor" opacity=".75">0 m</text><text x="${W - 50}" y="${H - 6}" font-size="9.5" fill="currentColor" opacity=".75">${Math.round(p.length_m)} m</text>
    <text x="${W - 8}" y="12" text-anchor="end" font-size="9.5" fill="currentColor" opacity=".75">relief ${span.toFixed(2)} m (y not to scale)</text></svg>`;
}

// ------------------------------------------------------------ night lighting
// NOAA-style solar elevation (degrees) for a UTC time and location.
export function sunElevation(date, lat, lon) {
  const d = (date.getTime() / 86400000) + 2440587.5 - 2451545.0;
  const g = (357.529 + 0.98560028 * d) % 360, q = (280.459 + 0.98564736 * d) % 360;
  const L = q + 1.915 * Math.sin(g * Math.PI / 180) + 0.020 * Math.sin(2 * g * Math.PI / 180);
  const e = 23.439 - 0.00000036 * d;
  const ra = Math.atan2(Math.cos(e * Math.PI / 180) * Math.sin(L * Math.PI / 180), Math.cos(L * Math.PI / 180)) * 180 / Math.PI;
  const dec = Math.asin(Math.sin(e * Math.PI / 180) * Math.sin(L * Math.PI / 180));
  const gmst = (18.697374558 + 24.06570982441908 * d) % 24;
  const ha = ((gmst * 15 + lon - ra) % 360) * Math.PI / 180;
  const la = lat * Math.PI / 180;
  return Math.asin(Math.sin(la) * Math.sin(dec) + Math.cos(la) * Math.cos(dec) * Math.cos(ha)) * 180 / Math.PI;
}
