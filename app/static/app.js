(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function toast(message, kind = 'ok') {
    const box = $('#toasts');
    if (!box) return;
    const el = document.createElement('div');
    const colors = kind === 'error'
      ? 'border-red-800 bg-red-950 text-red-200'
      : 'border-emerald-800 bg-emerald-950 text-emerald-200';
    el.className = `max-w-sm rounded-lg border px-4 py-3 text-sm shadow-lg ${colors}`;
    el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    el.textContent = message;
    box.appendChild(el);
    setTimeout(() => el.remove(), 4500);
  }

  function flash(message, kind = 'ok') {
    sessionStorage.setItem('flash', JSON.stringify({ message, kind }));
  }

  function showFlash() {
    const raw = sessionStorage.getItem('flash');
    if (!raw) return;
    sessionStorage.removeItem('flash');
    try {
      const { message, kind } = JSON.parse(raw);
      toast(message, kind);
    } catch {
      toast('No se pudo mostrar el aviso anterior.', 'error');
    }
  }

  function errorMessage(detail, status) {
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
    return `Error ${status}`;
  }

  async function api(method, url, body, { raw = false, contentType = 'application/json' } = {}) {
    const init = { method, headers: {} };
    if (body !== undefined) {
      init.headers['Content-Type'] = contentType;
      init.body = raw ? body : JSON.stringify(body);
    }
    const response = await fetch(url, init);
    if (response.status === 204) return null;
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = null;
    }
    if (!response.ok) {
      throw new Error(errorMessage(data && data.detail, response.status));
    }
    return data;
  }

  async function run(button, action) {
    if (button) button.disabled = true;
    try {
      await action();
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand('copy');
      textarea.remove();
      if (!copied) return toast('No se pudo copiar', 'error');
    }
    toast('Copiado al portapapeles');
  }

  const playlistName = () => $('[data-playlist]')?.dataset.playlist || '';
  const playlistUrl = (suffix = '') => `/api/playlists/${encodeURIComponent(playlistName())}${suffix}`;

  function channelStatusMessage(statuses) {
    const live = statuses.filter((item) => item.live).map((item) => item.channel);
    const offline = statuses.filter((item) => !item.live).map((item) => item.channel);
    const parts = [];
    if (live.length) parts.push(`En directo: ${live.join(', ')}`);
    if (offline.length) parts.push(`Offline (guardados, sin enlace al exportar): ${offline.join(', ')}`);
    return parts.join(' · ');
  }

  const actions = {
    async logout() {
      await api('POST', '/auth/logout', {});
      location.href = '/login';
    },

    async 'delete-playlist'() {
      const name = playlistName();
      if (!confirm(`¿Eliminar la lista '${name}'? Esta acción no se puede deshacer.`)) return;
      await api('DELETE', playlistUrl());
      flash(`Lista '${name}' eliminada`);
      location.href = '/manager';
    },

    async 'delete-channel'(button) {
      const name = button.dataset.channel;
      if (!confirm(`¿Eliminar '${name}' de la lista?`)) return;
      await api('DELETE', playlistUrl(`/channels/${encodeURIComponent(name)}`));
      flash(`Entrada '${name}' eliminada`);
      location.reload();
    },
  };

  document.addEventListener('click', (event) => {
    const element = event.target.closest('[data-copy],[data-copy-path],[data-action]');
    if (!element) return;
    if (element.dataset.copy !== undefined) {
      if (element.dataset.copy) copyText(element.dataset.copy);
      return;
    }
    if (element.dataset.copyPath) {
      copyText(location.origin + element.dataset.copyPath);
      return;
    }
    const action = actions[element.dataset.action];
    if (action) run(element, () => action(element));
  });

  const forms = {
    async 'login-form'(form) {
      const credentials = Object.fromEntries(new FormData(form));
      const result = await api('POST', '/auth/login', {
        username: credentials.username,
        password: credentials.password,
        next: form.dataset.next || '/',
      });
      form.elements.password.value = '';
      location.href = result.redirect;
    },

    async 'create-form'(form) {
      const data = Object.fromEntries(new FormData(form));
      const created = await api('POST', '/api/playlists', {
        name: data.name.trim(),
        channels: data.channels || '',
      });
      const statusMessage = channelStatusMessage(created.channel_status || []);
      flash(`Lista '${created.name}' creada${statusMessage ? ` · ${statusMessage}` : ''}`);
      location.href = `/manager/p/${encodeURIComponent(created.name)}`;
    },

    async 'add-form'(form) {
      const channels = new FormData(form).get('channels');
      const response = await api('POST', playlistUrl('/channels'), { channels });
      const messages = [];
      if (response.added.length) messages.push(`Añadidos: ${response.added.join(', ')}`);
      if (response.skipped.length) messages.push(`Ya existían: ${response.skipped.join(', ')}`);
      const statuses = response.playlist.channel_status || [];
      const statusMessage = channelStatusMessage(statuses);
      if (statusMessage) messages.push(statusMessage);
      flash(messages.join(' · ') || 'Sin cambios', response.added.length ? 'ok' : 'error');
      location.reload();
    },
  };

  document.addEventListener('submit', (event) => {
    const handler = forms[event.target.id];
    if (!handler) return;
    event.preventDefault();
    run(event.target.querySelector('[type=submit]'), () => handler(event.target));
  });

  const importInput = $('#import-file');
  if (importInput) {
    importInput.addEventListener('change', async () => {
      const file = importInput.files[0];
      if (!file) return;

      const typed = ($('#create-form [name=name]').value || '').trim();
      const fromFile = file.name
        .replace(/\.m3u8?$/i, '')
        .replace(/[^A-Za-z0-9._-]+/g, '-')
        .replace(/^[^A-Za-z0-9]+/, '')
        .slice(0, 64);
      const name = typed || fromFile;
      if (!name) {
        toast('Indica un nombre para la lista', 'error');
        importInput.value = '';
        return;
      }

      let existing = [];
      try {
        existing = JSON.parse($('#playlists').dataset.names || '[]');
      } catch {
        toast('No se pudo cargar la lista de playlists existentes.', 'error');
        importInput.value = '';
        return;
      }
      if (existing.includes(name) && !confirm(`La lista '${name}' ya existe. ¿Reemplazarla?`)) {
        importInput.value = '';
        return;
      }

      await run(importInput, async () => {
        const text = await file.text();
        const result = await api('PUT', `/m3u/${encodeURIComponent(name)}.m3u`, text, {
          raw: true,
          contentType: 'text/plain',
        });
        flash(`Lista '${result.name}' importada (${result.count} entrada(s))`);
        location.href = `/manager/p/${encodeURIComponent(result.name)}`;
      });
      importInput.value = '';
    });
  }

  const filter = $('#filter');
  if (filter) {
    filter.addEventListener('input', () => {
      const query = filter.value.trim().toLowerCase();
      let visible = 0;
      $$('tr[data-row]').forEach((row) => {
        const show = !query || row.dataset.name.includes(query);
        row.classList.toggle('hidden', !show);
        if (show) visible += 1;
      });
      $('#no-match')?.classList.toggle('hidden', visible > 0);
    });
  }

  showFlash();
})();
