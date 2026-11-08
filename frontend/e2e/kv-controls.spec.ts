import { expect, test, type Page } from '@playwright/test'
import type { Snapshot } from '../src/types'
import { runControls } from '../src/runControls'

function interrupted(): Snapshot {
  return {
    runtime: { mode: 'kv', containerized: false, services: 5, name: 'KV Lab', gateway: { pid: 1, boot_id: 'gateway', available: true } },
    run: { id: 'stopped-rpc', module: 'rpc', scenario: 'server_down', status: 'INTERRUPTED', config: { mode: 'auto' }, result: { stage: 'AWAIT_RPC_STOP' }, created: 1 },
    nodes: { rpc: { node: 'rpc', available: true, kv: { counter: 7 } } },
    services: { rpc: { alive: true, pid: 2, port: 19102 } }, events: [], transactions: [],
  }
}

async function show(page: Page, state: Snapshot, route = '/rpc') {
  // A recorded snapshot fixture exercises the UI without resetting the live lab.
  await page.addInitScript(snapshot => {
    class RecordedSource extends EventTarget {
      timer: number
      constructor() {
        super()
        this.timer = window.setInterval(() => this.dispatchEvent(new MessageEvent('snapshot', { data: JSON.stringify(snapshot) })), 200)
      }
      close() { window.clearInterval(this.timer) }
    }
    window.EventSource = RecordedSource as unknown as typeof EventSource
  }, state)
  await page.goto(route)
  await expect(page.getByTestId('connection')).toHaveAttribute('data-connected', 'true')
}

test('interrupted non-commit workflows are restartable without erasing KV', () => {
  for (const module of ['rpc', 'group', 'recovery'] as const) {
    const state = interrupted(); state.run!.module = module
    expect(runControls(state)).toEqual({ running: false, unresolved: false, externalWait: false, restartable: true })
    expect(state.nodes.rpc.kv?.counter).toBe(7)
  }
})

test('durable commit uncertainty stays protected; live PREPARED step is still usable', () => {
  const state = interrupted()
  state.run!.module = 'commit'
  expect(runControls(state).unresolved).toBe(true)
  for (const status of ['BLOCKED', 'DECISION_PENDING']) {
    state.run!.status = status
    expect(runControls(state).unresolved).toBe(true)
  }
  state.run!.status = 'WAITING'
  state.run!.result = { phase: 'PAUSED_AFTER_PREPARE' }
  state.nodes.A = { node: 'A', available: true, locks: [{ key: 'balance', tx_id: 'tx' }], transactions: [{ id: 'tx', state: 'PREPARED' }] }
  expect(runControls(state).unresolved).toBe(false)
  expect(runControls(state).running).toBe(true)
  state.run!.status = 'INTERRUPTED'; state.run!.module = 'rpc'
  expect(runControls(state).unresolved).toBe(true)
  delete state.runtime
  expect(runControls(state).unresolved).toBe(true)
})

test('interrupted RPC unlocks scenario, speed, Step and Run without calling reset', async ({ page }) => {
  const writes: { path: string; body: unknown }[] = []
  await page.route('**/api/*', async handler => {
    const req = handler.request()
    if (req.method() !== 'POST') return handler.fallback()
    writes.push({ path: new URL(req.url()).pathname, body: req.postDataJSON() })
    await handler.fulfill({ json: { id: 'test-only-run' } })
  })
  await show(page, interrupted())
  await expect(page.locator('#scenario')).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Từng bước', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: '2×', exact: true })).toBeEnabled()
  await expect(page.locator('.external-fault')).toHaveCount(0)
  await expect(page.getByRole('note')).toContainText('dữ liệu KV vẫn được giữ')
  await page.locator('#scenario').selectOption('lost_response')
  await page.getByRole('button', { name: '2×', exact: true }).click()
  await page.getByRole('button', { name: 'Từng bước', exact: true }).click()
  await page.getByRole('button', { name: 'Chạy thí nghiệm', exact: true }).click()
  await expect.poll(() => writes.length).toBe(1)
  expect(writes[0]).toMatchObject({ path: '/api/runs', body: { module: 'rpc', scenario: 'lost_response', mode: 'step', pace_ms: 300 } })
  await expect(page.getByTestId('kv-rpc')).toContainText('7')
})

for (const containerized of [false, true]) test(`external wait stays gated with ${containerized ? 'Docker' : 'Process'} instructions`, async ({ page }) => {
  const state = interrupted(); state.run!.status = 'WAITING'
  state.runtime!.containerized = containerized
  await show(page, state)
  await expect(page.getByRole('button', { name: 'Chạy thí nghiệm', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: /Bước tiếp/ })).toBeDisabled()
  if (containerized) await expect(page.locator('.external-fault')).toContainText('kv-demo.ps1')
  else {
    await expect(page.locator('.external-fault')).toContainText('Không cần Docker')
    await expect(page.locator('.external-fault')).not.toContainText('kv-demo.ps1')
  }
})

test('interrupted commit cannot be bypassed by switching modules', async ({ page }) => {
  const state = interrupted(); state.run!.module = 'commit'
  await show(page, state)
  await expect(page.getByRole('button', { name: 'Chạy thí nghiệm', exact: true })).toBeDisabled()
  await expect(page.locator('#scenario')).toBeDisabled()
})
