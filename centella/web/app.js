(() => {
  const views = [...document.querySelectorAll('.view')];
  const navItems = [...document.querySelectorAll('.nav-item')];
  const engineDot = document.getElementById('engineDot');
  const runtimeLabel = document.getElementById('runtimeLabel');
  const playStatus = document.getElementById('playStatus');
  const playButton = document.getElementById('playButton');
  const trainingPlayButton = document.getElementById('trainingPlayButton');
  const toast = document.getElementById('toast');
  let currentView = 'home';
  let runtimeReady = false;
  let toastTimer = null;

  function showToast(message, error = false) {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.toggle('error', error);
    toast.classList.add('show');
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3400);
  }

  function go(viewName) {
    const next = document.getElementById(viewName);
    if (!next) return;
    currentView = viewName;
    views.forEach(view => view.classList.toggle('active-view', view === next));
    navItems.forEach(item => item.classList.toggle('active', item.dataset.view === viewName));
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
  }

  async function callApi(method, ...args) {
    if (!window.pywebview?.api?.[method]) {
      throw new Error('Puente nativo no disponible');
    }
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
      showToast('El motor 3D todavía no está listo. El menú ya no fingirá que sí lo está.', true);
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
    }
  }

  document.querySelectorAll('[data-go]').forEach(button => {
    button.addEventListener('click', () => go(button.dataset.go));
  });
  navItems.forEach(button => button.addEventListener('click', () => go(button.dataset.view)));
  playButton.addEventListener('click', () => launch('match'));
  trainingPlayButton.addEventListener('click', () => launch('training'));

  document.querySelectorAll('.training-tile').forEach(tile => {
    tile.addEventListener('click', () => {
      document.querySelectorAll('.training-tile').forEach(item => item.classList.remove('active'));
      tile.classList.add('active');
    });
  });

  document.getElementById('fullscreenButton').addEventListener('click', async () => {
    try { await callApi('toggle_fullscreen'); } catch (error) { showToast(String(error), true); }
  });
  document.getElementById('closeButton').addEventListener('click', async () => {
    try { await callApi('close'); } catch (error) { showToast(String(error), true); }
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && currentView !== 'home') go('home');
    if (event.key === 'Enter') {
      if (currentView === 'kickoff') launch('match');
      if (currentView === 'training') launch('training');
    }
    if (event.key === 'F11') {
      event.preventDefault();
      callApi('toggle_fullscreen').catch(() => {});
    }
  });

  window.addEventListener('pywebviewready', refreshRuntime);
  // Browser preview / CI can render the full frontend without a Python host.
  if (!window.pywebview) {
    runtimeLabel.textContent = 'MOTOR · PREVISUALIZACIÓN';
    playStatus.textContent = 'PREVISUALIZACIÓN DE INTERFAZ';
    playButton.disabled = true;
    trainingPlayButton.disabled = true;
  }
})();
