/* SPDX-License-Identifier: GPL-3.0-only
 * Q2 02.04 tweaked - touch for the Fluidd "Printer screen" window (optional module printer-screen-touch).
 *
 * Adds a "Touch off / on" button to the window of printer-screen-view. Touch is OFF every time the window opens.
 * Switching it on ARMS the q2-screen-touch service on the printer (it is off in the service itself, not only here):
 * the arming lasts about a minute and this window renews it every 20 s while touch is on. Switching off, closing the
 * window or leaving the page disarms it. While armed, a click in the picture sends the place (0..1 of the picture) to
 * the service, which presses the same place on the real touch screen. A click is refused when the picture is missing,
 * of the wrong size, or older than 1.5 s (so nothing is pressed "blind" on a screen that has changed since).
 * Nothing else is sent anywhere.
 */
(function () {
  'use strict';
  var URLS = { arm: '/webcam3/?action=arm', disarm: '/webcam3/?action=disarm', tap: '/webcam3/?action=tap' };
  var RENEW_MS = 20000;           // the service keeps the arming for 60 s
  var MAX_AGE_MS = 1500;          // oldest picture a click may be based on
  var TEXT = {
    en: { off: 'Touch: off', on: 'Touch: ON', warn: 'WARNING: a click presses the printer\'s real screen. A sleeping screen needs 2 clicks at the start: the first one only wakes it.',
      fail: 'Tap not sent: ', stale: 'No fresh screen picture. Wait a moment.',
      armfail: 'Touch could not be switched on: ', expired: 'Touch was switched off. Switch it on again.' },
    pl: { off: 'Dotyk: wyłączony', on: 'Dotyk: WŁĄCZONY', warn: 'UWAGA: kliknięcie naciska prawdziwy ekran drukarki. Uśpiony ekran wymaga 2 kliknięć na start: pierwsze tylko go wybudza.',
      fail: 'Dotyk nie poszedł: ', stale: 'Brak świeżego obrazu. Poczekaj chwilę.',
      armfail: 'Nie włączono dotyku: ', expired: 'Dotyk wyłączony. Włącz go ponownie.' }
  };
  function lang() {
    var l = '';
    try { var app = document.getElementById('app'); var vm = app && app.__vue__; l = (vm && vm.$i18n && vm.$i18n.locale) || ''; } catch (e) { /* ignore */ }
    l = (l || navigator.language || 'en').toLowerCase();
    return l.indexOf('pl') === 0 ? 'pl' : 'en';
  }
  function tr(k) { return (TEXT[lang()] || TEXT.en)[k]; }

  // One request to the service. Every request carries X-Q2-Touch (a page of another site cannot send it without a
  // CORS preflight, which the service never allows).
  function send(action, body, keepalive) {
    return fetch(URLS[action], { method: 'POST', keepalive: !!keepalive,
      headers: { 'Content-Type': 'application/json', 'X-Q2-Touch': '1' }, body: JSON.stringify(body || {}) })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); });
  }

  document.addEventListener('q2-screen-open', function (ev) {
    var d = ev.detail, img = d.img, warn = d.warn;
    var enabled = false, busy = false, renew = null, gone = false;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'q2s-btn';
    btn.style.cssText = 'margin-right:auto;background:rgba(128,128,128,.35)';
    d.foot.insertBefore(btn, d.foot.firstChild);

    function say(text, err) { warn.textContent = text; warn.className = 'q2s-msg q2s-warn' + (err ? ' err' : ''); }
    function show() {
      btn.textContent = enabled ? tr('on') : tr('off');
      btn.style.background = enabled ? '#fb8c00' : 'rgba(128,128,128,.35)';
      img.style.cursor = enabled ? 'crosshair' : '';
      img.style.outline = enabled ? '3px solid #fb8c00' : '';
      if (enabled) say(tr('warn'), false); else say('', false);
    }
    // the picture is good for a click: loaded, 480x272, and shown less than 1.5 s ago by the picture window
    function fresh() {
      return img.complete && img.naturalWidth === 480 && img.naturalHeight === 272 &&
        Date.now() - Number(img.dataset.q2Ts || 0) <= MAX_AGE_MS;
    }
    function stopRenewing() { if (renew) { clearInterval(renew); renew = null; } }
    function setOff(keepalive) {
      var was = enabled;
      enabled = false;
      stopRenewing();
      if (was) send('disarm', {}, keepalive).catch(function () { /* the service switches itself off after 60 s */ });
      show();
    }
    function teardown() {
      if (gone) return;
      gone = true;
      document.removeEventListener('q2-screen-close', onClose);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('pagehide', onHide);
      setOff(true);
    }
    function onClose() { teardown(); }
    function onHide() { setOff(true); }
    function renewNow() {
      if (!enabled || gone) return;
      if (!img.isConnected) { teardown(); return; }               // the window is gone without telling us
      if (document.hidden) return;                                // a hidden page does not keep touch armed
      send('arm').catch(function (err) {
        if (!enabled) return;
        setOff(false);
        say(tr('armfail') + err.message, true);
      });
    }
    function onVisible() { if (!document.hidden) renewNow(); }
    document.addEventListener('q2-screen-close', onClose);
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('pagehide', onHide);

    btn.addEventListener('click', function () {
      if (enabled) { setOff(false); return; }
      if (busy) return;
      busy = true;
      send('arm').then(function () {
        if (gone) { send('disarm', {}, true).catch(function () { /* ignore */ }); return; }
        enabled = true;
        renew = setInterval(renewNow, RENEW_MS);
        show();
      }).catch(function (err) { say(tr('armfail') + err.message, true); })
        .then(function () { busy = false; });
    });
    img.addEventListener('click', function (e) {
      if (!enabled || busy || gone) return;
      if (!fresh()) { say(tr('stale'), true); return; }
      var r = img.getBoundingClientRect();
      if (!r.width || !r.height) return;
      var x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      if (x < 0 || x > 1 || y < 0 || y > 1) return;
      busy = true;
      send('tap', { x: Math.round(x * 10000) / 10000, y: Math.round(y * 10000) / 10000 })
        .then(function () { if (enabled) say(tr('warn'), false); })
        .catch(function (err) {
          if (/HTTP 403/.test(err.message) && enabled) { setOff(false); say(tr('expired'), true); }
          else say(tr('fail') + err.message, true);
        })
        .then(function () { setTimeout(function () { busy = false; }, 300); });
    });
    show();
  });
})();
