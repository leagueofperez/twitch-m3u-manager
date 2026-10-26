import { extractStreams, shortenStream } from './api.js'
import {
  announce,
  copyText,
  flashCopied,
  flashShortened,
  showToast,
} from './clipboard.js'
import { renderEmpty, renderError, renderStreams } from './render.js'

const ACTION_TEXT = {
  created: 'creada',
  updated: 'actualizada',
  unchanged: 'sin cambios',
}

async function shortenAndCopy(button) {
  const quality = button.dataset.quality

  button.disabled = true
  try {
    const data = await shortenStream(button)
    if (data.error) {
      showToast(`No se pudo acortar: ${data.error}`, 'error')
      return
    }

    const copied = await copyText(data.shortUrl)
    if (copied) {
      flashShortened(button, quality)
      showToast(
        `URL corta ${ACTION_TEXT[data.action] || ''}: ${data.shortUrl}, copiada.`,
      )
    } else {
      showToast(
        `URL corta ${ACTION_TEXT[data.action] || ''}: ${data.shortUrl}. No se pudo copiar.`,
        'error',
      )
    }
  } catch (err) {
    console.error(err)
    showToast('No se pudo contactar con el servidor para acortar.', 'error')
  } finally {
    button.disabled = false
  }
}

async function extract() {
  const input = document.getElementById('twitchUrl')
  const result = document.getElementById('result')
  const url = input.value.trim()

  if (!url) {
    announce('Introduce un canal, un ID de VOD o una URL de Twitch.')
    return
  }

  result.innerHTML =
    '<p class="text-gray-500 dark:text-gray-400">Obteniendo calidades...</p>'

  try {
    const data = await extractStreams(url)

    if (data.error) {
      renderError(result, data.error)
    } else if (!data.streams || data.streams.length === 0) {
      renderEmpty(result)
    } else {
      renderStreams(result, data.streams)
    }
  } catch (err) {
    console.error(err)
    renderError(
      result,
      `Error de red: ${err.message || 'No se pudo conectar al servidor.'}`,
    )
  }
}

function handleResultClick(event) {
  const button = event.target.closest('button[data-action]')
  if (!button) return

  const quality = button.dataset.quality
  if (button.dataset.action === 'shorten') {
    shortenAndCopy(button)
    return
  }

  copyText(button.dataset.url).then((copied) => {
    if (copied) {
      flashCopied(button)
      showToast(`URL de ${quality} copiada al portapapeles.`)
    } else {
      showToast(
        `No se pudo copiar la URL de ${quality}. Abre el stream y cópiala manualmente.`,
        'error',
      )
    }
  })
}

const extractForm = document.getElementById('extractForm')
extractForm?.addEventListener('submit', (event) => {
  event.preventDefault()
  extract()
})

document
  .getElementById('result')
  ?.addEventListener('click', handleResultClick)
