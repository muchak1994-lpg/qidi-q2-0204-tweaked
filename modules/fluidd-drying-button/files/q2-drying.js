/* SPDX-License-Identifier: GPL-3.0-only
 * Q2 02.04 tweaked - "Filament drying" button for Fluidd.
 *
 * Adds one entry at the end of the left navigation panel. It opens a window
 * with the same settings the printer screen offers (filament type, drying
 * temperature, drying time) and sends the same commands the screen sends:
 *   prepare_filament_dry
 *   SET_FILAMENT_DRY END_TIME=<seconds> BED_TEMP=<C> CHAMBER_TEMP=<C>
 *   SET_FILAMENT_DRY END_TIME=0 BED_TEMP=0 CHAMBER_TEMP=0      (stop)
 * The values below are the screen program's own table (QIDI 01.01.02.04).
 * This file does not touch Fluidd's own code: it only adds the entry and the window.
 */
(function () {
  'use strict';
  if (window.q2Drying) return;

  // [type, build plate C, chamber C] - the screen's table; the chamber value is not editable there either
  var MATERIALS = [
    ['ABS', 90, 60], ['ASA', 90, 60], ['PA', 90, 60], ['PA-CF', 90, 60], ['PA-GF', 90, 60],
    ['PAHT-CF', 90, 60], ['PC', 90, 60], ['PET-CF', 90, 60], ['PETG', 90, 60], ['PETG-CF', 70, 55],
    ['PLA', 70, 55], ['PLA-CF', 70, 55], ['PPS', 90, 60], ['PPS-CF', 90, 60], ['TPU', 90, 60]
  ];
  var DEFAULT_TYPE = 'PLA', DEFAULT_HOURS = 12;
  // The screen accepts up to 120 C; the highest value in its own table is 90 C. This window stops at 100 C.
  var MIN_TEMP = 30, MAX_TEMP = 100;
  var MIN_HOURS = 1, MAX_HOURS = 24;   // the screen accepts 1..24
  var ICON = 'M6 2c-2 2.5 2 5 0 7.5s2 5 0 7.5h2c2-2.5-2-5 0-7.5s-2-5 0-7.5zM11 2c-2 2.5 2 5 0 7.5s2 5 0 7.5h2c2-2.5-2-5 0-7.5s-2-5 0-7.5zM16 2c-2 2.5 2 5 0 7.5s2 5 0 7.5h2c2-2.5-2-5 0-7.5s-2-5 0-7.5zM4 19h16v2H4z';

  var TEXT = {
    en: {
      title: 'Filament drying', type: 'Filament', temp: 'Build plate (°C)',
      hours: 'Time (h)', chamber: 'Chamber', bed: 'Build plate',
      s1: 'Check that nothing lies on the build plate or on the bottom of the printer, and that the PEI plate is placed correctly.',
      s2: 'Press "Lower the bed". The printer homes (if needed) and lowers the bed - the build plate must be EMPTY for this.',
      s3: 'Place the spool on the build plate and cover it with a lid printed from a high-temperature material (PA-CF, PC) or with a cardboard packaging box.',
      s4: 'Close the front door and the top cover.',
      s5: 'Press "Start drying". Do not leave a heating printer unattended.',
      lower: 'Lower the bed', start: 'Start drying', confirm: 'Confirm: {t} °C, {h} h', stop: 'Stop drying', close: 'Close',
      idle: 'Drying is off', active: 'Drying is running', left: 'about {t} left',
      busy: 'A print is running or paused - drying cannot be started now.',
      notready: 'The printer is not ready (Klipper).', working: 'Working…', lowered: 'Bed lowered.',
      started: 'Drying started.', stopped: 'Drying stopped.', failed: 'The printer refused: ',
      noapi: 'No connection to the printer.', range: 'Temperature {a}-{b} °C, time {c}-{d} h.'
    },
    pl: {
      title: 'Suszenie filamentu', type: 'Filament', temp: 'Stół (°C)',
      hours: 'Czas (h)', chamber: 'Komora', bed: 'Stół',
      s1: 'Sprawdź, czy na stole i na dnie drukarki nic nie leży i czy płyta PEI jest poprawnie założona.',
      s2: 'Naciśnij „Opuść stół”. Drukarka zbazuje osie (jeśli trzeba) i opuści stół - stół musi być wtedy PUSTY.',
      s3: 'Połóż szpulę na stole i przykryj ją pokrywą wydrukowaną z materiału odpornego na temperaturę (PA-CF, PC) albo kartonowym pudełkiem.',
      s4: 'Zamknij drzwi i górną pokrywę.',
      s5: 'Naciśnij „Start suszenia”. Nie zostawiaj grzejącej drukarki bez nadzoru.',
      lower: 'Opuść stół', start: 'Start suszenia', confirm: 'Potwierdź: {t} °C, {h} h', stop: 'Zatrzymaj suszenie', close: 'Zamknij',
      idle: 'Suszenie wyłączone', active: 'Suszenie trwa', left: 'zostało ok. {t}',
      busy: 'Trwa druk albo pauza - suszenia nie można teraz uruchomić.',
      notready: 'Drukarka nie jest gotowa (Klipper).', working: 'Pracuję…', lowered: 'Stół opuszczony.',
      started: 'Suszenie uruchomione.', stopped: 'Suszenie zatrzymane.', failed: 'Drukarka odmówiła: ',
      noapi: 'Brak połączenia z drukarką.', range: 'Temperatura {a}-{b} °C, czas {c}-{d} h.'
    }
  };

  function lang() {
    var l = '';
    try {
      var app = document.getElementById('app');
      var vm = app && app.__vue__;
      l = (vm && vm.$i18n && vm.$i18n.locale) || '';
    } catch (e) { /* ignore */ }
    l = (l || navigator.language || 'en').toLowerCase();
    return l.indexOf('pl') === 0 ? 'pl' : 'en';
  }
  function tr(key, vars) {
    var s = (TEXT[lang()] || TEXT.en)[key] || TEXT.en[key] || key;
    if (vars) Object.keys(vars).forEach(function (k) { s = s.replace('{' + k + '}', vars[k]); });
    return s;
  }

  // ---- printer access (Moonraker, same address as Fluidd) -------------------------------------
  function api(method, path, body) {
    var opt = { method: method, headers: {} };
    if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) {
          var m = (j && j.error && j.error.message) || ('HTTP ' + r.status);
          throw new Error(String(m));
        }
        return j.result;
      });
    });
  }
  function gcode(script) { return api('POST', '/printer/gcode/script', { script: script }); }
  function readState() {
    return api('GET', '/printer/objects/query?webhooks&print_stats&pause_resume&virtual_sdcard' +
      '&heater_bed&heater_generic%20chamber&multi_color_controller=drying').then(function (res) {
      var s = (res && res.status) || {};
      var dry = ((s.multi_color_controller || {}).drying || {}).extra || {};
      var ps = ((s.print_stats || {}).state || '').toLowerCase();
      return {
        ready: (s.webhooks || {}).state === 'ready',
        printing: ps === 'printing' || ps === 'paused' || !!(s.pause_resume || {}).is_paused ||
          !!(s.virtual_sdcard || {}).is_active,
        bed: s.heater_bed || {}, chamber: s['heater_generic chamber'] || {},
        drying: Number(dry.dry_state || 0) === 1, endTime: Number(dry.end_time || 0)
      };
    });
  }

  // ---- window ---------------------------------------------------------------------------------
  var dlg = null, timer = null, state = null, confirmUntil = 0, busyCmd = false;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function theme() {
    var app = document.querySelector('.v-application');
    var dark = !app || app.classList.contains('theme--dark');
    var card = '', primary = '';
    try {
      var c = document.querySelector('.v-card');
      if (c) card = getComputedStyle(c).backgroundColor;
      var p = document.querySelector('.v-application .primary, .v-btn.primary');
      if (p) primary = getComputedStyle(p).backgroundColor;
      if (!primary && app) primary = getComputedStyle(app).getPropertyValue('--v-primary-base').trim();
    } catch (e) { /* ignore */ }
    if (!card || card === 'rgba(0, 0, 0, 0)') card = dark ? '#28282b' : '#ffffff';
    return { dark: dark, card: card, primary: primary || '#2196f3' };
  }
  function css() {
    if (document.getElementById('q2-drying-css')) return;
    var s = el('style');
    s.id = 'q2-drying-css';
    s.textContent =
      '.q2d-back{position:fixed;inset:0;z-index:3000;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;padding:12px}' +
      '.q2d-card{width:100%;max-width:600px;max-height:100%;overflow:auto;border-radius:6px;box-shadow:0 11px 15px -7px rgba(0,0,0,.2),0 24px 38px 3px rgba(0,0,0,.14);font-size:14px;line-height:1.4}' +
      '.q2d-card *{box-sizing:border-box}' +
      '.q2d-head{font-size:18px;font-weight:500;padding:14px 18px 6px}' +
      '.q2d-body{padding:6px 18px 4px}' +
      '.q2d-status{padding:8px 10px;border-radius:4px;margin-bottom:12px;background:rgba(128,128,128,.16)}' +
      '.q2d-status span{white-space:nowrap}.q2d-status div{margin-top:2px;opacity:.85}' +
      '.q2d-status b{font-weight:600}' +
      '.q2d-row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px}' +
      '.q2d-row{flex-wrap:nowrap}.q2d-row label{flex:1 1 90px;min-width:0;display:block;font-size:12px;opacity:.8;white-space:nowrap}' +
      '.q2d-row label.q2d-num{flex:0 0 84px}' +
      '.q2d-row select:disabled,.q2d-row input:disabled{opacity:.5}' +
      '.q2d-row select,.q2d-row input{display:block;width:100%;margin-top:4px;padding:8px;font-size:15px;border-radius:4px;border:1px solid rgba(128,128,128,.5);background:transparent;color:inherit}' +
      '.q2d-row select option{color:#000}' +
      '.q2d-steps{margin:6px 0 4px;padding-left:20px}.q2d-steps li{margin-bottom:5px}' +
      '.q2d-msg{min-height:20px;margin:6px 0;font-weight:500}.q2d-msg.err{color:#ff5252}' +
      '.q2d-foot{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;padding:8px 18px 16px}' +
      '.q2d-btn{border:0;border-radius:4px;padding:9px 12px;font-size:14px;font-weight:500;letter-spacing:.01em;white-space:nowrap;cursor:pointer;color:inherit;background:rgba(128,128,128,.25)}' +
      '.q2d-btn.err{margin-right:auto}' +
      '.q2d-tip{position:fixed;z-index:3001;pointer-events:none;background:rgba(97,97,97,.9);color:#fff;border-radius:4px;font-size:14px;line-height:22px;padding:5px 16px;white-space:nowrap;transform:translateY(-50%)}' +
      '.q2d-btn.pri{color:#fff}.q2d-btn.warn{background:#fb8c00;color:#fff}.q2d-btn.err{background:#ff5252;color:#fff}' +
      '.q2d-btn:disabled{opacity:.4;cursor:default}';
    document.head.appendChild(s);
  }
  function fmtLeft(sec) {
    var h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
    return (h ? h + ' h ' : '') + m + ' min';
  }
  function num(v) { return typeof v === 'number' && isFinite(v) ? v.toFixed(0) : '-'; }

  function settings() {
    var t = parseInt(dlg.temp.value, 10), h = parseInt(dlg.hours.value, 10);
    var mat = MATERIALS.filter(function (m) { return m[0] === dlg.type.value; })[0] || MATERIALS[10];
    var ok = t >= MIN_TEMP && t <= MAX_TEMP && h >= MIN_HOURS && h <= MAX_HOURS &&
      String(t) === dlg.temp.value.trim() && String(h) === dlg.hours.value.trim();
    return { ok: ok, temp: t, hours: h, chamber: mat[2] };
  }
  function message(text, isErr) {
    dlg.msg.textContent = text || '';
    dlg.msg.className = 'q2d-msg' + (isErr ? ' err' : '');
  }
  function render() {
    if (!dlg) return;
    var s = state, set = settings();
    var confirming = Date.now() < confirmUntil;
    if (!s) {
      dlg.status.textContent = tr('noapi');
    } else {
      dlg.status.textContent = '';
      var head = el('span');
      head.appendChild(el('b', null, s.drying ? tr('active') : tr('idle')));
      if (s.drying && s.endTime > 1e9) {
        var left = s.endTime - Date.now() / 1000;
        if (left > 0) head.appendChild(document.createTextNode(' (' + tr('left', { t: fmtLeft(left) }) + ')'));
      }
      dlg.status.appendChild(head);
      var temps = el('div');
      temps.appendChild(el('span', null, tr('bed') + ' ' + num(s.bed.temperature) + ' / ' + num(s.bed.target) + ' °C'));
      temps.appendChild(document.createTextNode('  ·  '));
      temps.appendChild(el('span', null, tr('chamber') + ' ' + num(s.chamber.temperature) + ' / ' + num(s.chamber.target) + ' °C'));
      dlg.status.appendChild(temps);
    }
    var lock = !!s && s.drying;
    dlg.type.disabled = dlg.temp.disabled = dlg.hours.disabled = lock;
    var can = !!s && s.ready && !s.printing && !busyCmd;
    dlg.lower.disabled = !can || s.drying;
    dlg.start.disabled = !can || s.drying || !set.ok;
    dlg.stop.disabled = !s || !s.ready || busyCmd;
    dlg.start.textContent = confirming && set.ok ? tr('confirm', { t: set.temp, h: set.hours }) : tr('start');
    dlg.start.className = 'q2d-btn ' + (confirming ? 'warn' : 'pri');
    if (!confirming) dlg.start.style.background = theme().primary; else dlg.start.style.background = '';
    if (!busyCmd && !dlg.msg.dataset.keep) {
      if (s && !s.ready) message(tr('notready'), true);
      else if (s && s.printing) message(tr('busy'), true);
      else if (!set.ok) message(tr('range', { a: MIN_TEMP, b: MAX_TEMP, c: MIN_HOURS, d: MAX_HOURS }), true);
      else message('');
    }
  }
  function refresh() {
    return readState().then(function (s) { state = s; }, function () { state = null; }).then(render);
  }
  function run(script, doneKey) {
    busyCmd = true; confirmUntil = 0;
    dlg.msg.dataset.keep = '1';
    message(tr('working'));
    render();
    return gcode(script).then(function () { message(tr(doneKey)); }, function (e) {
      message(tr('failed') + (e && e.message ? e.message : ''), true);
    }).then(function () {
      busyCmd = false;
      setTimeout(function () { if (dlg) { delete dlg.msg.dataset.keep; } }, 6000);
      return refresh();
    });
  }
  function close() {
    if (timer) clearInterval(timer);
    timer = null;
    if (dlg) dlg.back.remove();
    dlg = null;
    document.removeEventListener('keydown', onKey, true);
  }
  function onKey(e) { if (e.key === 'Escape') { e.stopPropagation(); close(); } }

  function open() {
    if (dlg) return;
    css();
    var th = theme();
    var back = el('div', 'q2d-back');
    var card = el('div', 'q2d-card');
    card.style.background = th.card;
    try { back.style.fontFamily = getComputedStyle(document.querySelector('.v-application') || document.body).fontFamily; } catch (e) { /* ignore */ }
    card.style.color = th.dark ? '#fff' : 'rgba(0,0,0,.87)';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-label', tr('title'));
    card.appendChild(el('div', 'q2d-head', tr('title')));
    var body = el('div', 'q2d-body');
    var status = el('div', 'q2d-status', '…');
    body.appendChild(status);

    var row = el('div', 'q2d-row');
    var lType = el('label', null, tr('type')), type = el('select');
    MATERIALS.forEach(function (m) { var o = el('option', null, m[0]); o.value = m[0]; type.appendChild(o); });
    lType.appendChild(type);
    var lTemp = el('label', null, tr('temp')), temp = el('input');
    temp.type = 'number'; temp.min = MIN_TEMP; temp.max = MAX_TEMP; temp.step = 1; temp.inputMode = 'numeric';
    lTemp.className = 'q2d-num';
    lTemp.appendChild(temp);
    var lHours = el('label', null, tr('hours')), hours = el('input');
    hours.type = 'number'; hours.min = MIN_HOURS; hours.max = MAX_HOURS; hours.step = 1; hours.inputMode = 'numeric';
    lHours.className = 'q2d-num';
    lHours.appendChild(hours);
    row.appendChild(lType); row.appendChild(lTemp); row.appendChild(lHours);
    body.appendChild(row);

    var steps = el('ol', 'q2d-steps');
    ['s1', 's2', 's3', 's4', 's5'].forEach(function (k) { steps.appendChild(el('li', null, tr(k))); });
    body.appendChild(steps);
    var msg = el('div', 'q2d-msg');
    body.appendChild(msg);
    card.appendChild(body);

    var foot = el('div', 'q2d-foot');
    var bStop = el('button', 'q2d-btn err', tr('stop'));
    var bLower = el('button', 'q2d-btn', tr('lower'));
    var bStart = el('button', 'q2d-btn pri', tr('start'));
    var bClose = el('button', 'q2d-btn', tr('close'));
    [bStop, bLower, bStart, bClose].forEach(function (b) { b.type = 'button'; foot.appendChild(b); });
    card.appendChild(foot);
    back.appendChild(card);
    document.body.appendChild(back);

    dlg = { back: back, status: status, type: type, temp: temp, hours: hours, msg: msg,
      lower: bLower, start: bStart, stop: bStop };

    function preset() {
      var m = MATERIALS.filter(function (x) { return x[0] === type.value; })[0];
      if (m) temp.value = m[1];
      confirmUntil = 0; render();
    }
    type.value = DEFAULT_TYPE; hours.value = DEFAULT_HOURS; preset();
    type.addEventListener('change', preset);
    [temp, hours].forEach(function (i) { i.addEventListener('input', function () { confirmUntil = 0; render(); }); });
    back.addEventListener('mousedown', function (e) { if (e.target === back) close(); });
    bClose.addEventListener('click', close);
    bLower.addEventListener('click', function () { run('prepare_filament_dry', 'lowered'); });
    bStop.addEventListener('click', function () {
      run('SET_FILAMENT_DRY END_TIME=0 BED_TEMP=0 CHAMBER_TEMP=0', 'stopped');
    });
    bStart.addEventListener('click', function () {
      var set = settings();
      if (!set.ok) return;
      if (Date.now() >= confirmUntil) {          // first press: ask to confirm, second press within 6 s: start
        confirmUntil = Date.now() + 6000;
        setTimeout(render, 6100);
        render();
        return;
      }
      run('SET_FILAMENT_DRY END_TIME=' + (set.hours * 3600) + ' BED_TEMP=' + set.temp +
        ' CHAMBER_TEMP=' + set.chamber, 'started');
    });
    document.addEventListener('keydown', onKey, true);
    refresh();
    timer = setInterval(refresh, 2000);
  }

  // ---- entry in the left navigation panel -----------------------------------------------------
  // The entry is a copy of the panel's last entry (Settings), so it looks the same on a phone and
  // on a computer. Fluidd hides the whole list while there is no connection; the entry hides with it.
  var BTN_ID = 'q2-drying-nav', pending = false;

  var tip = null;
  function hideTip() { if (tip) tip.remove(); tip = null; }
  function showTip(a) {
    hideTip();
    if (a.querySelector('.v-list-item__title') && a.getBoundingClientRect().width > 120) return;  // text is visible
    css();
    var r = a.getBoundingClientRect();
    tip = el('div', 'q2d-tip', tr('title'));
    try { tip.style.fontFamily = getComputedStyle(document.querySelector('.v-application') || document.body).fontFamily; } catch (e) { /* ignore */ }
    tip.style.left = (r.right + 10) + 'px';
    tip.style.top = (r.top + r.height / 2) + 'px';
    document.body.appendChild(tip);
  }
  function makeItem(src) {
    var a = src.cloneNode(true);
    a.id = BTN_ID;
    ['href', 'aria-current', 'aria-describedby', 'aria-haspopup', 'aria-expanded'].forEach(function (n) {
      a.removeAttribute(n);
    });
    a.classList.remove('v-list-item--active', 'secondary--text', 'router-link-active', 'router-link-exact-active');
    a.setAttribute('role', 'button');
    a.setAttribute('tabindex', '0');
    a.setAttribute('aria-label', tr('title'));
    var p = a.querySelector('svg path');
    if (p) p.setAttribute('d', ICON);
    var t = a.querySelector('.v-list-item__title');
    if (t) t.textContent = ' ' + tr('title') + ' ';
    a.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); open(); });
    a.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
    });
    // the same kind of label Fluidd shows next to its own entries when the pointer is over them
    a.addEventListener('mouseenter', function () { showTip(a); });
    ['mouseleave', 'click', 'blur'].forEach(function (n) { a.addEventListener(n, hideTip); });
    return a;
  }
  function place() {
    pending = false;
    var list = document.querySelector('.nav-items');
    var mine = document.getElementById(BTN_ID);
    if (!list) { if (mine) mine.remove(); return; }
    var items = list.querySelectorAll('a.v-list-item:not(#' + BTN_ID + ')');
    if (!items.length) { if (mine) mine.remove(); return; }
    if (mine && mine.parentElement === list && !mine.nextElementSibling) return;
    if (mine) mine.remove();
    list.appendChild(makeItem(items[items.length - 1]));
  }
  function schedule() {
    if (pending) return;
    pending = true;
    setTimeout(place, 50);   // not requestAnimationFrame: that one waits while the page is in the background
  }
  function startWatching() {
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
    schedule();
  }
  if (document.body) startWatching();
  else document.addEventListener('DOMContentLoaded', startWatching);

  window.q2Drying = { open: open, close: close };
})();
