// Prototype controls: demo-only view and simulation tools, kept out of the product UI.
import { state, api, on, emit, esc, icon, toast, setTheme, loadPlan } from './core.js';

const el = () => document.getElementById('sim');
let tab = 'view';
let opener = null;

export function initSim() {
  const fab = document.getElementById('sim-fab');
  fab.addEventListener('click', () => (el().hidden ? openSim() : closeSim()));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !el().hidden) closeSim();
    // Shift+P opens the prototype controls even when their button is hidden.
    if (e.key === 'P' && e.shiftKey && !e.target.closest('input, textarea, select, [contenteditable]')) { e.preventDefault(); el().hidden ? openSim() : closeSim(); }
  });
  let hide = false;
  try { hide = localStorage.getItem('cg-hide-demo') === '1'; } catch {}
  setHideDemo(hide);
  let hideLabels = false;
  try { hideLabels = localStorage.getItem('cg-hide-labels') === '1'; } catch {}
  setHideLabels(hideLabels, false);
  on((what) => { if (['route', 'mapstate', 'theme', 'plan'].includes(what) && !el().hidden) render(); });
}
export function openSim() {
  opener = document.activeElement;
  el().hidden = false;
  document.body.classList.add('sim-open');
  document.getElementById('sim-fab').setAttribute('aria-expanded', 'true');
  render();
  el().querySelector('#sim-close')?.focus();
}
export function closeSim() {
  el().hidden = true;
  document.body.classList.remove('sim-open');
  document.getElementById('sim-fab').setAttribute('aria-expanded', 'false');
  opener?.focus?.();
}

function setHideDemo(on) {
  state.ui.hideDemo = on;
  document.body.classList.toggle('hide-demo', on);
  try { localStorage.setItem('cg-hide-demo', on ? '1' : '0'); } catch {}
}

// Presentation mode: removes every Simulated / Fictional tag, demo disclaimer line and "(fictional)" suffix.
function setHideLabels(on, rerender = true) {
  state.ui.hideLabels = on;
  document.body.classList.toggle('hide-labels', on);
  try { localStorage.setItem('cg-hide-labels', on ? '1' : '0'); } catch {}
  if (rerender) emit('lang'); // re-renders the current view so text-level labels are rebuilt
}

const sw = (id, checked, label, desc) => `<label class="toggle-row" for="${id}"><span><span class="t">${label}</span>${desc ? `<br><span class="d">${desc}</span>` : ''}</span>
  <span class="switch"><input type="checkbox" id="${id}" ${checked ? 'checked' : ''}><span></span></span></label>`;
const seg = (name, opts, cur, label) => `<div class="seg" role="group" aria-label="${label}">${opts.map(([v, l]) =>
  `<button type="button" data-${name}="${v}" aria-pressed="${String(cur) === String(v)}">${l}</button>`).join('')}</div>`;

function render() {
  const ui = state.ui, onMap = !!state.mapCtl;
  const mapOnly = onMap ? '' : '<p class="hint">Open the Field map to use these controls.</p>';
  el().innerHTML = `
    <div class="sim-head"><div><h2 id="sim-title">Prototype controls</h2>
      <p>Demo and simulation tools for this prototype. They are not part of the planning product.</p></div>
      <button type="button" class="icon-btn" id="sim-close" aria-label="Close prototype controls">${icon('close')}</button></div>
    <div class="sim-tabs" role="tablist">
      <button role="tab" type="button" data-simtab="view" aria-selected="${tab === 'view'}">View</button>
      <button role="tab" type="button" data-simtab="sim" aria-selected="${tab === 'sim'}">Simulation</button></div>
    <div class="sim-body">${tab === 'view' ? `
      <section class="sim-sec"><h3>Camera</h3><p class="hint">How the field map is framed.</p>
        <div class="view-modes">
          ${[['overview', 'overview', 'Overview', 'Tilted view of the selected field'], ['pov', 'pov', 'Operator POV', 'Low first-person view; rides along during replay'],
             ['orbit', 'orbit', 'Orbit', 'Slow fly-around of the field']].map(([v, ic, n, c]) =>
            `<button type="button" class="view-mode" data-view="${v}" aria-pressed="${ui.view === v}" ${onMap ? '' : 'disabled'}>${icon(ic)}<span class="n">${n}</span><span class="c">${c}</span></button>`).join('')}
        </div>${mapOnly}</section>
      <section class="sim-sec"><h3>Presentation</h3>
        ${sw('sim-hidedemo', ui.hideDemo, 'Hide demo badges', 'Hides the “Simulated demo data” badge and this button. Reopen with Shift + P. Per-reading “Simulated” tags stay visible.')}
        ${sw('sim-hidelabels', ui.hideLabels, 'Hide all demo labels', 'Hides every “Simulated” and “Fictional” tag, the demo disclaimer lines and the “(fictional)” suffixes on names. For presentations only: the data is still simulated.')}</section>
      <section class="sim-sec"><h3>Appearance</h3>
        <div class="toggle-row"><span class="t">Theme</span>${seg('theme', [['light', 'Day'], ['dark', 'Night']], state.theme, 'Theme')}</div>
        <div class="toggle-row"><span><span class="t">Scene lighting</span><br><span class="d">Auto follows the scenario clock (sun below the horizon = night)</span></span>${seg('lighting', [['auto', 'Auto'], ['day', 'Day'], ['night', 'Night']], ui.lighting, 'Scene lighting')}</div>
        <div class="toggle-row"><span class="t">Map</span>${seg('dim', [['2d', '2D'], ['3d', '3D']], ui.is3d ? '3d' : '2d', 'Map dimension')}</div>
        <div class="toggle-row"><span class="t">Basemap</span>${seg('base', [['imagery', 'Satellite'], ['streets', 'Streets']], ui.basemap, 'Basemap')}</div></section>
      <section class="sim-sec"><h3>Terrain (USGS 3DEP)</h3><p class="hint">Real elevation. Exaggeration changes the picture only; elevations and calculations stay true.</p>
        <div class="toggle-row"><span class="t">Vertical exaggeration</span>${seg('exag', [[1, '1×'], [2, '2×'], [3, '3×'], [5, '5×']], ui.exaggeration, 'Vertical exaggeration')}</div>
        ${sw('sim-tcolor', ui.terrainColor, 'Elevation colours + hillshade', 'Demo district, 3DEP Bare Earth DEM')}
        ${sw('sim-contours', ui.contours, 'Contour lines')}
        <button type="button" class="btn sm" id="sim-tsite" ${onMap ? '' : 'disabled'} style="margin-top:8px">${icon('map', 'sm')}Fly to terrain check site (Gila Mountains)</button></section>
      <section class="sim-sec"><h3>Regional real data</h3><p class="hint">Real observations and model output, shown separately from the simulated demo.</p>
        ${sw('sim-livest', ui.liveStations, 'AZMET stations (observed)', 'Yuma Valley, Yuma N.Gila, Yuma South with sensor heights')}
        ${sw('sim-livemod', ui.liveModel, 'HRRR 2 m temperature (raw model)', '3 km native grid, cell-centre dots')}</section>
      <section class="sim-sec"><h3>Layers</h3>
        ${sw('sim-thermal', ui.thermal, 'Thermal heat map', 'Interpolated air temperature from the 2 simulated masts. Not a drift-risk map.')}
        <div class="toggle-row"><span class="t" style="padding-left:2px">Thermal height</span>${seg('theight', [['lower', '5 ft'], ['upper', '30 ft']], ui.thermalHeight, 'Thermal height')}</div>
        <div class="toggle-row"><span class="t">Wind flow</span>${seg('wind', [['lower', '5 ft'], ['upper', '30 ft'], ['both', 'Both'], ['off', 'Off']], ui.wind, 'Wind flow')}</div>
        <div class="toggle-row"><span class="t">Color fields by</span>${seg('colorby', [['status', 'Decision'], ['inversion', 'ΔT'], ['none', 'Off']], ui.colorBy, 'Color fields by')}</div>
        ${sw('sim-areas', ui.showAreas, 'Sensitive areas and exclusions')}
        ${sw('sim-passes', ui.showPasses, 'Application passes')}</section>` : `
      <section class="sim-sec"><h3>Scenario clock and replay</h3><p class="hint">Scrub simulated observations and forecast, and replay the planned application.</p>
        <div id="sim-map-slot">${mapOnly}</div></section>
      <section class="sim-sec"><h3>Events</h3><p class="hint">Inject a sudden wind surge at the selected field, 15 minutes after the current scenario time, to test monitoring and alerts.</p>
        <button type="button" class="btn danger" id="sim-inject" ${onMap ? '' : 'disabled'}>${icon('caution', 'sm')}Simulate critical change</button></section>
      <section class="sim-sec"><h3>Rule thresholds</h3><p class="hint">Prototype assumptions and challenge defaults. Changes are recorded and the plan is recalculated.</p>
        <form id="sim-thr" class="form-grid" style="grid-template-columns:1fr 1fr">${Object.entries(state.meta.thresholds).map(([k, t]) =>
          `<div class="field"><label for="thr-${k}" title="${esc(t.source)}">${esc(k.replace(/_/g, ' '))}</label><input id="thr-${k}" name="${k}" type="number" step="any" value="${t.value}"></div>`).join('')}
          <div class="btn-row" style="grid-column:1/-1;margin-top:8px"><button class="btn sm primary" type="submit">Apply thresholds</button><button class="btn sm" type="button" id="thr-reset">Restore defaults</button></div></form></section>
      <section class="sim-sec"><h3>Demo</h3><p class="hint">Restore the original requests, clear alerts and simulated events.</p>
        <button type="button" class="btn" id="sim-reset">${icon('reset', 'sm')}Reset demo scenario</button></section>`}
    </div>`;
  if (tab === 'sim' && state.mapCtl) state.mapCtl.renderSim(el().querySelector('#sim-map-slot'));
  bind();
}

function set(key, val) {
  state.ui[key] = val;
  state.mapCtl?.apply(key, val);
  render();
}

function bind() {
  const root = el();
  root.querySelector('#sim-close').onclick = closeSim;
  root.querySelectorAll('[data-simtab]').forEach((b) => (b.onclick = () => { tab = b.dataset.simtab; render(); }));
  root.querySelectorAll('[data-view]').forEach((b) => (b.onclick = () => set('view', b.dataset.view)));
  root.querySelectorAll('[data-theme]').forEach((b) => (b.onclick = () => { setTheme(b.dataset.theme); render(); }));
  root.querySelectorAll('[data-dim]').forEach((b) => (b.onclick = () => set('is3d', b.dataset.dim === '3d')));
  root.querySelectorAll('[data-lighting]').forEach((b) => (b.onclick = () => set('lighting', b.dataset.lighting)));
  root.querySelectorAll('[data-exag]').forEach((b) => (b.onclick = () => set('exaggeration', Number(b.dataset.exag))));
  root.querySelector('#sim-tcolor')?.addEventListener('change', (e) => set('terrainColor', e.target.checked));
  root.querySelector('#sim-contours')?.addEventListener('change', (e) => set('contours', e.target.checked));
  root.querySelector('#sim-livest')?.addEventListener('change', (e) => set('liveStations', e.target.checked));
  root.querySelector('#sim-livemod')?.addEventListener('change', (e) => set('liveModel', e.target.checked));
  root.querySelector('#sim-tsite')?.addEventListener('click', () => state.mapCtl?.apply('terrainSite'));
  root.querySelectorAll('[data-base]').forEach((b) => (b.onclick = () => set('basemap', b.dataset.base)));
  root.querySelectorAll('[data-theight]').forEach((b) => (b.onclick = () => { state.ui.thermal = true; set('thermalHeight', b.dataset.theight); }));
  root.querySelectorAll('[data-wind]').forEach((b) => (b.onclick = () => set('wind', b.dataset.wind)));
  root.querySelectorAll('[data-colorby]').forEach((b) => (b.onclick = () => set('colorBy', b.dataset.colorby)));
  root.querySelector('#sim-thermal')?.addEventListener('change', (e) => set('thermal', e.target.checked));
  root.querySelector('#sim-areas')?.addEventListener('change', (e) => set('showAreas', e.target.checked));
  root.querySelector('#sim-hidedemo')?.addEventListener('change', (e) => {
    setHideDemo(e.target.checked);
    if (e.target.checked) toast('Demo badges hidden. Press Shift + P to reopen prototype controls.');
  });
  root.querySelector('#sim-hidelabels')?.addEventListener('change', (e) => {
    setHideLabels(e.target.checked);
    toast(e.target.checked ? 'Demo labels hidden. The data shown is still simulated.' : 'Demo labels shown.');
  });
  root.querySelector('#sim-passes')?.addEventListener('change', (e) => set('showPasses', e.target.checked));
  root.querySelector('#sim-inject')?.addEventListener('click', () => state.mapCtl?.inject());
  root.querySelector('#sim-reset')?.addEventListener('click', async () => {
    try {
      await api('/api/scenario/reset', { method: 'POST', body: {} });
      state.meta = await api('/api/meta');
      state.time = state.meta.scenario.now;
      await loadPlan();
      toast('Demo reset: requests, alerts, thresholds and simulated events restored.');
      emit('reset');
      render();
    } catch (e) { toast(e.message, true); }
  });
  const thr = root.querySelector('#sim-thr');
  thr?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = Object.fromEntries([...new FormData(thr)].map(([k, v]) => [k, v === '' ? null : Number(v)]));
    try { state.meta = await api('/api/settings/thresholds', { method: 'POST', body }); await loadPlan(true, 'thresholds changed'); toast('Thresholds applied and recorded; plan recalculated.'); emit('reset'); render(); }
    catch (err) { toast(err.message, true); }
  });
  root.querySelector('#thr-reset')?.addEventListener('click', async () => {
    try { state.meta = await api('/api/settings/thresholds', { method: 'POST', body: {} }); await loadPlan(true, 'thresholds reset'); toast('Default thresholds restored.'); emit('reset'); render(); }
    catch (err) { toast(err.message, true); }
  });
}
