(() => {
  const storageKey = 'twitch-tools-theme';
  const modes = ['auto', 'light', 'dark'];
  const labels = { auto: 'auto', light: 'claro', dark: 'oscuro' };
  const root = document.documentElement;
  const media = window.matchMedia?.('(prefers-color-scheme: dark)');

  function isMode(value) {
    return modes.includes(value);
  }

  function readMode() {
    try {
      const saved = window.localStorage.getItem(storageKey);
      return isMode(saved) ? saved : 'auto';
    } catch (error) {
      console.warn('No se pudo leer la preferencia del tema.', error);
      return 'auto';
    }
  }

  function saveMode(mode) {
    try {
      window.localStorage.setItem(storageKey, mode);
    } catch (error) {
      console.warn('No se pudo guardar la preferencia del tema.', error);
    }
  }

  function nextMode(mode) {
    return modes[(modes.indexOf(mode) + 1) % modes.length];
  }

  function resolvedTheme(mode) {
    if (mode === 'auto') return media?.matches ? 'dark' : 'light';
    return mode;
  }

  function updateTheme(mode) {
    const theme = resolvedTheme(mode);
    root.dataset.theme = theme;
    root.dataset.themeMode = mode;
    root.classList.toggle('dark', theme === 'dark');
    root.style.colorScheme = theme;
    document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => {
      meta.content = theme === 'dark' ? '#171322' : '#6441a5';
    });
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      const current = labels[mode];
      const next = labels[nextMode(mode)];
      button.setAttribute('aria-label', `Tema actual: ${current}. Cambiar a ${next}.`);
      button.setAttribute(
        'title',
        mode === 'auto'
          ? `Tema actual: auto (sigue el sistema, ${labels[theme]}). Cambiar a ${next}.`
          : `Tema actual: ${current}. Cambiar a ${next}.`
      );
    });
  }

  let mode = readMode();
  updateTheme(mode);

  document.addEventListener('DOMContentLoaded', () => {
    updateTheme(mode);
  }, { once: true });

  media?.addEventListener('change', () => {
    if (mode === 'auto') updateTheme(mode);
  });

  window.addEventListener('storage', (event) => {
    if (event.key !== storageKey) return;
    mode = isMode(event.newValue) ? event.newValue : 'auto';
    updateTheme(mode);
  });

  document.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest('[data-theme-toggle]');
    if (!button) return;

    mode = nextMode(mode);
    updateTheme(mode);
    saveMode(mode);
  });
})();
