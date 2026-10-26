const COPY_FEEDBACK_MS = 1500
const COPY_BASE_CLASSES = 'bg-gray-100 hover:bg-gray-200 text-gray-700'
const COPY_OK_CLASSES = 'bg-green-600 text-white'
const LINK_OK_CLASSES = 'bg-emerald-600 text-white'
const TOAST_DURATION_MS = 5000
let toastTimer

export function announce(message) {
  const status = document.getElementById('copyStatus')
  if (!status) return
  status.textContent = ''
  window.setTimeout(() => {
    status.textContent = message
  }, 50)
}

export function showToast(message, type = 'success') {
  const toast = document.getElementById('toast')
  const toastMessage = document.getElementById('toastMessage')
  if (!toast || !toastMessage) return

  window.clearTimeout(toastTimer)
  toastMessage.textContent = message
  toast.setAttribute('role', type === 'error' ? 'alert' : 'status')
  toast.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite')
  toast.classList.remove('hidden', 'bg-green-700', 'dark:bg-green-800', 'bg-red-700', 'dark:bg-red-900')
  toast.classList.add(
    ...(type === 'error'
      ? ['bg-red-700', 'dark:bg-red-900']
      : ['bg-green-700', 'dark:bg-green-800']),
  )

  toastTimer = window.setTimeout(() => {
    toast.classList.add('hidden')
  }, TOAST_DURATION_MS)
}

export async function copyText(text) {
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch (err) {
      // Sin permiso o sin soporte: se intenta el camino legacy.
    }
  }

  const helper = document.createElement('textarea')
  helper.value = text
  helper.setAttribute('readonly', '')
  helper.style.position = 'fixed'
  helper.style.top = '0'
  helper.style.left = '-9999px'
  helper.style.opacity = '0'
  document.body.appendChild(helper)

  let copied = false
  try {
    helper.select()
    helper.setSelectionRange(0, text.length)
    copied = document.execCommand('copy')
  } catch (err) {
    copied = false
  } finally {
    document.body.removeChild(helper)
  }

  return copied
}

function flashButton(button, successClasses, title) {
  if (button.dataset.flashing === '1') return
  button.dataset.flashing = '1'
  button.classList.remove(...COPY_BASE_CLASSES.split(' '))
  button.classList.add(...successClasses.split(' '))
  button.title = 'Copiado'

  window.setTimeout(() => {
    button.dataset.flashing = '0'
    button.classList.remove(...successClasses.split(' '))
    button.classList.add(...COPY_BASE_CLASSES.split(' '))
    button.title = title
  }, COPY_FEEDBACK_MS)
}

export function flashCopied(button) {
  flashButton(
    button,
    COPY_OK_CLASSES,
    `Copiar URL de ${button.dataset.quality}`,
  )
}

export function flashShortened(button, label) {
  flashButton(button, LINK_OK_CLASSES, `Acortar y copiar ${label}`)
}

document.getElementById('toastDismiss')?.addEventListener('click', () => {
  window.clearTimeout(toastTimer)
  document.getElementById('toast')?.classList.add('hidden')
})
