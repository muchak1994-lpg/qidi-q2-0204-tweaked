/* SPDX-License-Identifier: GPL-3.0-only
 * Q2 02.04 tweaked - "Printer screen" button for Fluidd.
 *
 * Adds one entry at the end of the left navigation panel (same technique as the filament drying entry).
 * It opens a window that shows what the printer's own touch screen shows, refreshed about twice a second
 * while the window is open. LOOK ONLY: nothing is sent to the printer. The picture comes from the
 * q2-screen service on the printer (through Fluidd's web server, address /webcam4/).
 * This file does not touch Fluidd's own code: it only adds the entry and the window.
 */
(function () {
  'use strict';
  if (window.q2ScreenView) return;

  var URL_BASE = '/webcam4/?action=snapshot';
  var REFRESH_MS = 500;                  // next picture is asked this long after the previous one arrived
  var ICON = 'M21,16H3V4H21M21,2H3C1.89,2 1,2.89 1,4V16A2,2 0 0,0 3,18H10V20H8V22H16V20H14V18H21A2,2 0 0,0 23,16V4C23,2.89 22.1,2 21,2Z';
  var TEXT = {
    en: { title: 'Printer screen', close: 'Close', loading: 'Loading the picture…',
      nopic: 'No picture from the printer screen. Is the "printer-screen-view" service running?',
      hint: 'Look only - this window cannot touch the printer screen.' },
    pl: { title: 'Ekran drukarki', close: 'Zamknij', loading: 'Wczytuję obraz…',
      nopic: 'Brak obrazu z ekranu drukarki. Czy usługa „printer-screen-view” działa?',
      hint: 'Tylko podgląd - z tego okna nie da się dotykać ekranu drukarki.' }
  };
  function lang() {
    var l = '';
    try { var app = document.getElementById('app'); var vm = app && app.__vue__; l = (vm && vm.$i18n && vm.$i18n.locale) || ''; } catch (e) { /* ignore */ }
    l = (l || navigator.language || 'en').toLowerCase();
    return l.indexOf('pl') === 0 ? 'pl' : 'en';
  }
  function tr(key) { return (TEXT[lang()] || TEXT.en)[key] || TEXT.en[key] || key; }
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
    if (document.getElementById('q2-screen-css')) return;
    var s = el('style');
    s.id = 'q2-screen-css';
    s.textContent =
      '.q2s-back{position:fixed;inset:0;z-index:3000;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;padding:12px}' +
      '.q2s-card{width:100%;max-width:980px;max-height:100%;overflow:auto;border-radius:6px;box-shadow:0 11px 15px -7px rgba(0,0,0,.2),0 24px 38px 3px rgba(0,0,0,.14);font-size:14px;line-height:1.4}' +
      '.q2s-card *{box-sizing:border-box}' +
      '.q2s-head{font-size:18px;font-weight:500;padding:14px 18px 6px}' +
      '.q2s-body{padding:6px 18px 4px;text-align:center}' +
      '.q2s-img{display:block;width:100%;height:auto;aspect-ratio:480/272;background:#000;border-radius:4px}' +
      '.q2s-msg{min-height:20px;margin:8px 0 0;opacity:.8}.q2s-msg.err{color:#ff5252;opacity:1}' +
      '.q2s-foot{display:flex;justify-content:flex-end;padding:8px 18px 16px}' +
      '.q2s-btn{border:0;border-radius:4px;padding:9px 12px;font-size:14px;font-weight:500;cursor:pointer;color:#fff}' +
      '.q2s-tip{position:fixed;z-index:3001;pointer-events:none;background:#0a0a0ae6;opacity:0;color:#fff;border-radius:4px;font-size:14px;line-height:22px;padding:5px 16px;white-space:nowrap;transform:translateY(-50%) scale(0);transition:opacity .3s cubic-bezier(.25,.8,.5,1),transform .3s cubic-bezier(.25,.8,.5,1)}' +
      '.q2s-tip.on{opacity:.9;transform:translateY(-50%) scale(1)}' +
      '.q2s-tip.off{opacity:0;transform:translateY(-50%) scale(1)}';
    document.head.appendChild(s);
  }

  // ---- window ---------------------------------------------------------------------------------
  var dlg = null;
  function close() {
    if (!dlg) return;
    clearTimeout(dlg.timer);
    dlg.back.remove();
    dlg = null;
    document.removeEventListener('keydown', onKey, true);
  }
  function onKey(e) { if (e.key === 'Escape') { e.stopPropagation(); close(); } }

  function next() {
    var d = dlg;
    if (!d) return;
    var probe = new Image();
    probe.onload = function () {
      if (dlg !== d) return;
      d.img.src = probe.src;
      d.msg.textContent = tr('hint');
      d.msg.className = 'q2s-msg';
      d.timer = setTimeout(next, REFRESH_MS);
    };
    probe.onerror = function () {
      if (dlg !== d) return;
      d.msg.textContent = tr('nopic');
      d.msg.className = 'q2s-msg err';
      d.timer = setTimeout(next, 3000);
    };
    probe.src = URL_BASE + '&t=' + Date.now();     // one request at a time, never piled up
  }
  function open() {
    if (dlg) return;
    css();
    var th = theme();
    var back = el('div', 'q2s-back'), card = el('div', 'q2s-card');
    card.style.background = th.card;
    try { back.style.fontFamily = getComputedStyle(document.querySelector('.v-application') || document.body).fontFamily; } catch (e) { /* ignore */ }
    card.style.color = th.dark ? '#fff' : 'rgba(0,0,0,.87)';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-label', tr('title'));
    card.appendChild(el('div', 'q2s-head', tr('title')));
    var body = el('div', 'q2s-body');
    var img = el('img', 'q2s-img');
    img.alt = tr('title');
    var msg = el('div', 'q2s-msg', tr('loading'));
    body.appendChild(img);
    body.appendChild(msg);
    card.appendChild(body);
    var foot = el('div', 'q2s-foot');
    var bClose = el('button', 'q2s-btn', tr('close'));
    bClose.type = 'button';
    bClose.style.background = th.primary;
    foot.appendChild(bClose);
    card.appendChild(foot);
    back.appendChild(card);
    document.body.appendChild(back);
    dlg = { back: back, img: img, msg: msg, timer: null };
    back.addEventListener('mousedown', function (e) { if (e.target === back) close(); });
    bClose.addEventListener('click', close);
    document.addEventListener('keydown', onKey, true);
    next();
  }

  // ---- entry in the left navigation panel -----------------------------------------------------
  // A copy of the panel's last Fluidd entry (Settings). The filament drying entry (another module) also wants
  // to be last: this one stays in front of it, so the two never fight over the place.
  var BTN_ID = 'q2-screen-nav', OTHER_ID = 'q2-drying-nav', pending = false;
  var tip = null;
  function hideTip() {
    var t = tip;
    tip = null;
    if (!t) return;
    t.classList.remove('on');
    t.classList.add('off');
    setTimeout(function () { t.remove(); }, 300);
  }
  function showTip(a) {
    hideTip();
    if (a.querySelector('.v-list-item__title') && a.getBoundingClientRect().width > 120) return;
    if (window.matchMedia && window.matchMedia('(hover: none)').matches) return;
    css();
    var r = a.getBoundingClientRect();
    tip = el('div', 'q2s-tip', tr('title'));
    try { tip.style.fontFamily = getComputedStyle(document.querySelector('.v-application') || document.body).fontFamily; } catch (e) { /* ignore */ }
    tip.style.left = (r.right + 10) + 'px';
    tip.style.top = (r.top + r.height / 2) + 'px';
    document.body.appendChild(tip);
    var t = tip;
    void t.offsetWidth;
    t.classList.add('on');
  }
  function makeItem(src) {
    var a = src.cloneNode(true);
    a.id = BTN_ID;
    ['href', 'aria-current', 'aria-describedby', 'aria-haspopup', 'aria-expanded'].forEach(function (n) { a.removeAttribute(n); });
    a.classList.remove('v-list-item--active', 'secondary--text', 'router-link-active', 'router-link-exact-active');
    a.setAttribute('role', 'button');
    a.setAttribute('tabindex', '0');
    a.setAttribute('aria-label', tr('title'));
    var p = a.querySelector('svg path');
    if (p) p.setAttribute('d', ICON);
    var t = a.querySelector('.v-list-item__title');
    if (t) t.textContent = ' ' + tr('title') + ' ';
    a.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); open(); });
    a.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    a.addEventListener('mouseenter', function () { showTip(a); });
    ['mouseleave', 'click', 'blur'].forEach(function (n) { a.addEventListener(n, hideTip); });
    return a;
  }
  function placed(mine, list) {
    if (mine.parentElement !== list) return false;
    var n = mine.nextElementSibling;
    return !n || (n.id === OTHER_ID && !n.nextElementSibling);
  }
  function place() {
    pending = false;
    var list = document.querySelector('.nav-items');
    var mine = document.getElementById(BTN_ID);
    if (!list) { if (mine) mine.remove(); return; }
    var items = list.querySelectorAll('a.v-list-item:not(#' + BTN_ID + '):not(#' + OTHER_ID + ')');
    if (!items.length) { if (mine) mine.remove(); return; }
    if (mine && placed(mine, list)) return;
    if (mine) mine.remove();
    var other = document.getElementById(OTHER_ID);
    var item = makeItem(items[items.length - 1]);
    if (other && other.parentElement === list) list.insertBefore(item, other);
    else list.appendChild(item);
  }
  function schedule() {
    if (pending) return;
    pending = true;
    setTimeout(place, 50);
  }
  function startWatching() {
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
    schedule();
  }
  if (document.body) startWatching();
  else document.addEventListener('DOMContentLoaded', startWatching);

  window.q2ScreenView = { open: open, close: close };
})();
