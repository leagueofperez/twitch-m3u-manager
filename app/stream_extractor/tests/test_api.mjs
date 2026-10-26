import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = await readFile(new URL('../static/js/api.js', import.meta.url), 'utf8')
const api = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
)

test('extract maps gateway authentication errors to the UI error contract', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => ({
    ok: false,
    status: 401,
    json: async () => ({ detail: 'Login required' }),
  })

  try {
    assert.deepEqual(await api.extractStreams('channel'), {
      error: 'Login required',
    })
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('shorten maps non-JSON upstream failures to a useful UI error', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => ({
    ok: false,
    status: 502,
    json: async () => {
      throw new SyntaxError('not JSON')
    },
  })

  try {
    assert.deepEqual(await api.shortenStream({ dataset: {} }), {
      error: 'La solicitud falló (502).',
    })
  } finally {
    globalThis.fetch = originalFetch
  }
})
