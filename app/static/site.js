(() => {
  'use strict';

  const menu = document.querySelector('details.site-menu');
  const nav = document.getElementById('site-nav');
  if (!menu || !nav) return;

  const toggle = menu.querySelector('summary');

  function closeMenu({ restoreFocus = false } = {}) {
    if (!menu.open) return;
    menu.open = false;
    if (restoreFocus) toggle?.focus();
  }

  document.addEventListener('click', (event) => {
    if (!menu.open || !(event.target instanceof Node)) return;
    if (menu.contains(event.target) || nav.contains(event.target)) return;
    closeMenu();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || !menu.open) return;
    closeMenu({ restoreFocus: true });
  });

  const desktop = window.matchMedia('(min-width: 768px)');
  const handleViewportChange = (event) => {
    if (event.matches) closeMenu();
  };
  if (typeof desktop.addEventListener === 'function') {
    desktop.addEventListener('change', handleViewportChange);
  } else if (typeof desktop.addListener === 'function') {
    desktop.addListener(handleViewportChange);
  }

  // Evita que el menú quede abierto al volver atrás desde un enlace.
  nav.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) return;
    if (event.target.closest('a[href]')) closeMenu();
  });
})();
