(() => {
  const storageKey = 'twitch-tools-theme';
  const root = document.documentElement;
  const media = window.matchMedia?.('(prefers-color-scheme: dark)');

  function readTheme() {
    try {
      const saved = window.localStorage.getItem(storageKey);
      return saved === 'light' || saved === 'dark' ? saved : null;
    } catch (error) {
      console.warn('No se pudo leer la preferencia del tema.', error);
      return null;
    }
  }

  function updateTheme(theme) {
    root.dataset.theme = theme;
    root.classList.toggle('dark', theme === 'dark');
    root.style.colorScheme = theme;
    document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => {
      meta.content = theme === 'dark' ? '#171322' : '#6441a5';
    });
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      const label = theme === 'dark' ? 'oscuro' : 'claro';
      button.setAttribute('aria-pressed', String(theme === 'dark'));
      button.setAttribute('aria-label', `Cambiar a modo ${theme === 'dark' ? 'claro' : 'oscuro'}`);
      const text = button.querySelector('[data-theme-label]');
      if (text) text.textContent = label;
    });
  }

  let savedTheme = readTheme();
  updateTheme(savedTheme || (media?.matches ? 'dark' : 'light'));

  document.addEventListener('DOMContentLoaded', () => {
    updateTheme(root.dataset.theme);
  }, { once: true });

  media?.addEventListener('change', (event) => {
    if (!savedTheme) updateTheme(event.matches ? 'dark' : 'light');
  });

  window.addEventListener('storage', (event) => {
    if (event.key !== storageKey) return;
    savedTheme = event.newValue === 'light' || event.newValue === 'dark'
      ? event.newValue
      : null;
    updateTheme(savedTheme || (media?.matches ? 'dark' : 'light'));
  });

  document.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest('[data-theme-toggle]');
    if (!button) return;

    savedTheme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    updateTheme(savedTheme);
    try {
      window.localStorage.setItem(storageKey, savedTheme);
    } catch (error) {
      console.warn('No se pudo guardar la preferencia del tema.', error);
    }
  });
})();
