(() => {
  const views = [...document.querySelectorAll('.view')];
  const navItems = [...document.querySelectorAll('.nav-item')];
  const introScreen = document.getElementById('introScreen');
  const continueButton = document.getElementById('continueButton');
  const continueDevice = document.getElementById('continueDevice');
  const engineDot = document.getElementById('engineDot');
  const runtimeLabel = document.getElementById('runtimeLabel');
  const playStatus = document.getElementById('playStatus');
  const playButton = document.getElementById('playButton');
  const trainingPlayButton = document.getElementById('trainingPlayButton');
  const footerHints = document.getElementById('footerHints');
  const acceptGlyph = document.getElementById('acceptGlyph');
  const backGlyph = document.getElementById('backGlyph');
  const shoulderGlyph = document.getElementById('shoulderGlyph');
  const toast = document.getElementById('toast');

  let currentView = 'home';
  let runtimeReady = false;
  let introActive = true;
  let toastTimer = null;
  let focusIndex = 0;
  let focusables = [];
  let lastInput = 'keyboard';
  let gamepadType = 'xbox';
  let lastPadState = {};
  let lastAxisMove = 0;

  function showToast(message, error = false) {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.toggle('error', error);
    toast.classList.add('show');
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3400);
  }

  function detectGamepadType(gamepad) {
    const id = (gamepad?.id || '').toLowerCase();
    if (id.includes('playstation') || id.includes('dualshock') || id.includes('dualsense') || id.includes('sony')) return 'playstation';
    return 'xbox';
  }

  function setInputMode(mode, gamepad = null) {
    lastInput = mode;
    const usingPad = mode === 'gamepad';
    footerHints?.classList.toggle('gamepad', usingPad);
    if (usingPad && gamepad) gamepadType = detectGamepadType(gamepad);
    if (acceptGlyph) acceptGlyph.textContent = gamepadType === 'playstation' ? '✕' : 'A';
    if (backGlyph) backGlyph.textContent = gamepadType === 'playstation' ? '○' : 'B';
    if (shoulderGlyph) shoulderGlyph.textContent = gamepadType === 'playstation' ? 'L1/R1' : 'LB/RB';
  }

  function dismissIntro(source = 'keyboard', gamepad = null) {
    if (!introActive) return;
    introActive = false;
    setInputMode(source, gamepad);
    introScreen.classList.add('hidden');
    refreshFocusables();
    setFocus(0);
  }

  function getViewElement() {
    return document.getElementById(currentView);
  }

  function refreshFocusables() {
    const view = getViewElement();
    focusables = view ? [...view.querySelectorAll('[data-focusable]:not([disabled])')].filter(el => el.offsetParent !== null) : [];
    focusIndex = Math.max(0, Math.min(focusIndex, Math.max(0, focusables.length - 1)));
  }

  function setFocus(index) {
    refreshFocusables();
    document.querySelectorAll('.ui-focused').forEach(el => el.classList.remove('ui-focused'));
    if (!focusables.length) return;
    focusIndex = (index + focusables.length) % focusables.length;
    const target = focusables[focusIndex];
    target.classList.add('ui-focused');
    try { target.focus({ preventScroll: true }); } catch (_) { target.focus(); }
  }

  function moveFocus(delta) {
    if (!focusables.length) refreshFocusables();
    setFocus(focusIndex + delta);
  }

  function activateFocused() {
    refreshFocusables();
    const target = focusables[focusIndex];
    if (!target || target.disabled) return;
    target.click();
  }

  function go(viewName) {
    const next = document.getElementById(viewName);
    if (!next) return;
    currentView = viewName;
    views.forEach(view => view.classList.toggle('active-view', view === next));
    navItems.forEach(item => item.classList.toggle('active', item.dataset.view === viewName));
    focusIndex = 0;
    requestAnimationFrame(() => setFocus(0));
  }

  function changeTab(delta) {
    const current = Math.max(0, navItems.findIndex(item => item.dataset.view === currentView));
    const next = (current + delta + navItems.length) % navItems.length;
    go(navItems[next].dataset.view);
  }

  function setRuntimeState(ready) {
    runtimeReady = !!ready;
    engineDot.classList.toggle('ready', runtimeReady);
    engineDot.classList.toggle('error', !runtimeReady);
    runtimeLabel.textContent = runtimeReady ? 'MOTOR · LISTO' : 'MOTOR · NO DISPONIBLE';
    runtimeLabel.classList.toggle('ready', runtimeReady);
    runtimeLabel.classList.toggle('error', !runtimeReady);
    playStatus.textContent = runtimeReady ? 'MOTOR LISTO · PULSA PARA SALTAR AL CAMPO' : 'EL MOTOR 3D AÚN NO ESTÁ COMPILADO EN ESTE EQUIPO';
    playStatus.classList.toggle('ready', runtimeReady);
    playStatus.classList.toggle('error', !runtimeReady);
    playButton.disabled = !runtimeReady;
    trainingPlayButton.disabled = !runtimeReady;
    refreshFocusables();
  }

  async function callApi(method, ...args) {
    if (!window.pywebview?.api?.[method]) throw new Error('Puente nativo no disponible');
    return window.pywebview.api[method](...args);
  }

  async function refreshRuntime() {
    try {
      const state = await callApi('runtime_state');
      setRuntimeState(state.ready);
    } catch (error) {
      setRuntimeState(false);
      console.error(error);
    }
  }

  async function launch(level = 'match') {
    if (!runtimeReady) {
      showToast('El motor 3D todavía no está listo en este equipo.', true);
      return;
    }
    const button = level === 'training' ? trainingPlayButton : playButton;
    const old = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span>ABRIENDO CAMPO…</span><b>●</b>';
    try {
      const result = await callApi('play', 1, false);
      showToast(result.message || (result.ok ? 'Partido iniciado' : 'No se pudo iniciar'), !result.ok);
      if (!result.ok) setRuntimeState(false);
    } catch (error) {
      showToast(String(error), true);
    } finally {
      button.innerHTML = old;
      button.disabled = !runtimeReady;
      refreshFocusables();
    }
  }

  continueButton.addEventListener('click', () => dismissIntro('keyboard'));
  document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click', () => go(button.dataset.go)));
  navItems.forEach(button => button.addEventListener('click', () => go(button.dataset.view)));
  playButton.addEventListener('click', () => launch('match'));
  trainingPlayButton.addEventListener('click', () => launch('training'));

  document.querySelectorAll('[data-action]').forEach(button => {
    button.addEventListener('click', () => {
      const label = button.dataset.action === 'coop' ? 'CO-OP LOCAL' : button.dataset.action === 'career' ? 'LIGA MÁSTER 2.0' : 'TORNEOS';
      showToast(`${label}: interfaz restaurada; este modo se conectará al motor jugable después del partido rápido.`);
    });
  });

  document.querySelectorAll('.training-tile').forEach(tile => {
    tile.addEventListener('click', () => {
      const group = tile.closest('.view');
      group.querySelectorAll('.training-tile').forEach(item => item.classList.remove('active'));
      tile.classList.add('active');
    });
  });

  document.getElementById('fullscreenButton').addEventListener('click', async () => {
    try { await callApi('toggle_fullscreen'); } catch (error) { showToast(String(error), true); }
  });
  document.getElementById('closeButton').addEventListener('click', async () => {
    try { await callApi('close'); } catch (error) { showToast(String(error), true); }
  });

  document.addEventListener('mousemove', () => setInputMode('keyboard'), { passive: true });
  document.addEventListener('keydown', event => {
    setInputMode('keyboard');
    if (introActive) {
      event.preventDefault();
      dismissIntro('keyboard');
      return;
    }
    if (event.key === 'F11') {
      event.preventDefault();
      callApi('toggle_fullscreen').catch(() => {});
      return;
    }
    if (event.key === 'Escape' || event.key === 'Backspace') {
      event.preventDefault();
      if (currentView !== 'home') go('home');
      return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      activateFocused();
      return;
    }
    if (event.key === 'ArrowDown' || event.key.toLowerCase() === 's') {
      event.preventDefault(); moveFocus(1); return;
    }
    if (event.key === 'ArrowUp' || event.key.toLowerCase() === 'w') {
      event.preventDefault(); moveFocus(-1); return;
    }
    if (event.key === 'ArrowRight' || event.key.toLowerCase() === 'd') {
      event.preventDefault(); moveFocus(1); return;
    }
    if (event.key === 'ArrowLeft' || event.key.toLowerCase() === 'a') {
      event.preventDefault(); moveFocus(-1); return;
    }
    if (event.key === 'PageUp' || event.key === 'q') { event.preventDefault(); changeTab(-1); }
    if (event.key === 'PageDown' || event.key === 'e') { event.preventDefault(); changeTab(1); }
  });

  function pressed(gamepad, index) {
    const value = !!gamepad?.buttons?.[index]?.pressed;
    const key = `${gamepad.index}:${index}`;
    const previous = !!lastPadState[key];
    lastPadState[key] = value;
    return value && !previous;
  }

  function pollGamepads(now = performance.now()) {
    const pads = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : [];
    const pad = pads[0];
    if (pad) {
      gamepadType = detectGamepadType(pad);
      if (introActive && pad.buttons.some(button => button.pressed)) {
        dismissIntro('gamepad', pad);
      } else if (!introActive) {
        const anyDigital = pad.buttons.some(button => button.pressed);
        if (anyDigital || Math.abs(pad.axes[0] || 0) > .55 || Math.abs(pad.axes[1] || 0) > .55) setInputMode('gamepad', pad);

        // Xbox/PlayStation standard mapping: A/X=0, B/O=1, LB/L1=4, RB/R1=5, D-pad=12..15.
        if (pressed(pad, 0)) activateFocused();
        if (pressed(pad, 1) && currentView !== 'home') go('home');
        if (pressed(pad, 4)) changeTab(-1);
        if (pressed(pad, 5)) changeTab(1);
        if (pressed(pad, 12)) moveFocus(-1);
        if (pressed(pad, 13)) moveFocus(1);
        if (pressed(pad, 14)) moveFocus(-1);
        if (pressed(pad, 15)) moveFocus(1);

        const ax = pad.axes[0] || 0;
        const ay = pad.axes[1] || 0;
        if (now - lastAxisMove > 185) {
          if (ax > .62 || ay > .62) { moveFocus(1); lastAxisMove = now; }
          else if (ax < -.62 || ay < -.62) { moveFocus(-1); lastAxisMove = now; }
        }
      }
    }
    requestAnimationFrame(pollGamepads);
  }

  window.addEventListener('gamepadconnected', event => {
    setInputMode('gamepad', event.gamepad);
    if (introActive) continueDevice.textContent = detectGamepadType(event.gamepad) === 'playstation' ? 'MANDO PLAYSTATION DETECTADO' : 'MANDO XBOX DETECTADO';
  });
  window.addEventListener('pywebviewready', refreshRuntime);
  requestAnimationFrame(pollGamepads);

  // Browser preview / CI can render the frontend without a Python host.
  if (!window.pywebview) {
    runtimeLabel.textContent = 'MOTOR · PREVISUALIZACIÓN';
    playStatus.textContent = 'PREVISUALIZACIÓN DE INTERFAZ';
    playButton.disabled = true;
    trainingPlayButton.disabled = true;
  }
})();
