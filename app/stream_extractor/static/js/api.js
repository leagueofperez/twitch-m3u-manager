async function postJson(path, payload) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  let data
  try {
    data = await response.json()
  } catch {
    data = null
  }

  if (!response.ok) {
    const detail = data?.detail ?? data?.error
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || JSON.stringify(item)).join('; ')
      : detail || `La solicitud falló (${response.status}).`
    return { error: message }
  }

  if (!data || typeof data !== 'object') {
    return { error: 'El servidor devolvió una respuesta no válida.' }
  }
  return data
}

export function extractStreams(url) {
  return postJson('/extractor/extract', { url })
}

export function shortenStream(button) {
  return postJson('/extractor/shorten', {
    url: button.dataset.url,
    slug: button.dataset.slug,
    title: button.dataset.title,
    ts: button.dataset.ts,
    sig: button.dataset.sig,
  })
}
