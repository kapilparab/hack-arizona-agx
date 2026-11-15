import { state, loadBase, setLang, stateBox, hm, on, emit, closeExplain, initTheme } from './core.js';
import { initSim } from './sim.js';
import { renderToday } from './today.js';
import { renderMap, leaveMap } from './mapview.js';
import { renderSchedule } from './schedule.js';
import { renderRecords } from './records.js';

const VIEWS = { today: renderToday, map: renderMap, schedule: renderSchedule, records: renderRecords };
const TITLES = { today: 'Today', map: 'Field map', schedule: 'Schedule', records: 'Records' };
const main = document.getElementById('main');
// Views drawn in the lineup-board theme with the blurred field backdrop (not the map).
const BOARD = new Set(['today', 'schedule', 'records']);
let current = null;

function parse() {
  const h = location.hash.replace(/^#\/?/, '') || 'today';
  const [route, qs] = h.split('?');
  return { route: VIEWS[route] ? route : 'today', params: new URLSearchParams(qs || '') };
}

async function route() {
  const { route: r, params } = parse();
  if (current === 'map' && r !== 'map') leaveMap();
  current = r;
  document.querySelectorAll('[data-route]').forEach((a) => {
    if (a.dataset.route === r) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  document.title = `${TITLES[r]} · Observair`;
  document.body.classList.toggle('on-map', r === 'map');
  document.body.classList.toggle('on-today', r === 'today');
  document.body.classList.toggle('cg-board', BOARD.has(r));
  closeExplain();
  await VIEWS[r](main, params);
  emit('route');
  if (r !== 'map') main.focus({ preventScroll: true });
}

async function boot() {
  initTheme();
  try { const l = localStorage.getItem('cg-lang'); if (l) setLang(l); } catch {}
  document.querySelectorAll('.lang button').forEach((b) => (b.onclick = () => setLang(b.dataset.lang)));
  main.innerHTML = '<div class="page"><div class="skeleton" style="height:140px"></div></div>';
  try {
    await loadBase();
  } catch (e) {
    main.innerHTML = `<div class="page">${stateBox('error', 'Observair could not start', e.message + ' Start the server (see README) and reload.',
      '<button class="btn sm" style="margin-top:8px" onclick="location.reload()">Reload</button>')}</div>`;
    return;
  }
  document.getElementById('clock').textContent = `Scenario ${hm(state.meta.scenario.now)} MST`;
  initSim();
  on((what) => { if ((what === 'lang' || what === 'reset') && current !== 'map') route(); });
  window.addEventListener('hashchange', route);
  route();
}
boot();
