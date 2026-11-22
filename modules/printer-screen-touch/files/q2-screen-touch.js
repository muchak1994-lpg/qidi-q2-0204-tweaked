/* SPDX-License-Identifier: GPL-3.0-only
 * Q2 02.04 tweaked - touch for the Fluidd "Printer screen" window (optional module printer-screen-touch).
 *
 * Adds a "Touch off / on" button to the window of printer-screen-view. Touch is OFF every time the window opens.
 * When on, a click in the picture sends the place (0..1 of the picture) to the q2-screen-touch service on the printer,
 * which presses the same place on the real touch screen. Nothing else is sent anywhere.
 */
(function () {
  'use strict';
  var TAP_URL = '/webcam3/?action=tap';
  var TEXT = {
    en: { off: 'Touch: off', on: 'Touch: ON', warn: 'Touch is ON: a click presses the printer\'s real screen (it can move axes, pause or stop a print). A sleeping screen only wakes on the first click.',
      fail: 'The tap was not sent: ' },
    pl: { off: 'Dotyk: wyłączony', on: 'Dotyk: WŁĄCZONY', warn: 'Dotyk WŁĄCZONY: kliknięcie naciska prawdziwy ekran drukarki (może ruszyć osiami, spauzować lub zatrzymać druk). Uśpiony ekran tylko się wybudzi pierwszym kliknięciem.',
      fail: 'Nie wysłano dotyku: ' }
  };
  function lang() {
    var l = '';
    try { var app = document.getElementById('app'); var vm = app && app.__vue__; l = (vm && vm.$i18n && vm.$i18n.locale) || ''; } catch (e) { /* ignore */ }
    l = (l || navigator.language || 'en').toLowerCase();
    return l.indexOf('pl') === 0 ? 'pl' : 'en';
  }
  function tr(k) { return (TEXT[lang()] || TEXT.en)[k]; }

  document.addEventListener('q2-screen-open', function (ev) {
    var d = ev.detail, img = d.img, msg = d.msg;
    var enabled = false, busy = false;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'q2s-btn';
    btn.style.cssText = 'margin-right:auto;background:rgba(128,128,128,.35)';
    d.foot.insertBefore(btn, d.foot.firstChild);

    function show() {
      btn.textContent = enabled ? tr('on') : tr('off');
      btn.style.background = enabled ? '#fb8c00' : 'rgba(128,128,128,.35)';
      img.style.cursor = enabled ? 'crosshair' : '';
      img.style.outline = enabled ? '3px solid #fb8c00' : '';
      if (enabled) { msg.dataset.q2t = '1'; msg.textContent = tr('warn'); msg.className = 'q2s-msg'; } else { delete msg.dataset.q2t; }
    }
    btn.addEventListener('click', function () { enabled = !enabled; show(); });
    img.addEventListener('click', function (e) {
      if (!enabled || busy) return;
      var r = img.getBoundingClientRect();
      if (!r.width || !r.height) return;
      var x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      if (x < 0 || x > 1 || y < 0 || y > 1) return;
      busy = true;
      fetch(TAP_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x: Math.round(x * 10000) / 10000, y: Math.round(y * 10000) / 10000 }) })
        .then(function (r2) { if (!r2.ok) throw new Error('HTTP ' + r2.status); })
        .catch(function (err) { msg.textContent = tr('fail') + err.message; msg.className = 'q2s-msg err'; })
        .then(function () { setTimeout(function () { busy = false; }, 300); });
    });
    show();
  });
})();
