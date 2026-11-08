import { expect, test } from '@playwright/test'
import { reconcileSnapshot, sameDiagramSnapshot } from '../src/snapshot'
import type { Snapshot } from '../src/types'

const baseline = (): Snapshot => ({ run: null, events: [], transactions: [], nodes: { A: { node: 'A', available: true, kv: { balance: 100 } } }, services: { A: { alive: true, pid: 10, port: 8000, boot_id: 'boot-one', observed_at: 1 } } })

test('heartbeat freshness updates without invalidating unchanged protocol data', () => {
  const previous = baseline(), incoming = structuredClone(previous)
  incoming.services.A.observed_at = 2
  const result = reconcileSnapshot(previous, incoming)
  expect(result.services.A.observed_at).toBe(2)
  expect(result.nodes).toBe(previous.nodes)
  expect(result.events).toBe(previous.events)
  expect(sameDiagramSnapshot(previous, result)).toBe(true)
})

test('real KV changes, event payloads and unavailable services invalidate the diagram', () => {
  const previous = baseline(), incoming = structuredClone(previous)
  incoming.nodes.A.kv!.balance = 90
  incoming.events.push({ seq: 1, run_id: 'tx-one', time: 1, source: 'A', target: 'coordinator', kind: 'COMMIT', detail: 'Actual decision', data: { balance: 90 } })
  const result = reconcileSnapshot(previous, incoming)
  expect(result.nodes.A.kv!.balance).toBe(90)
  expect(sameDiagramSnapshot(previous, result)).toBe(false)
  const unavailable = structuredClone(result)
  unavailable.services.A.alive = false
  expect(sameDiagramSnapshot(result, reconcileSnapshot(result, unavailable))).toBe(false)
  const updatedEvent = structuredClone(result)
  updatedEvent.events[0].data.balance = 80
  expect(reconcileSnapshot(result, updatedEvent).events[0].data.balance).toBe(80)
})

test('cached tabs retain canvas and viewport while idle SSE does not churn graph DOM', async ({ page }) => {
  await page.goto('/rpc')
  await expect(page.getByTestId('connection')).toHaveAttribute('data-connected', 'true')
  const canvas = page.locator('[data-topology-page=rpc]:not([hidden])')
  await expect(canvas.locator('.service-node')).toHaveCount(2)
  await expect.poll(() => page.locator('.page-rpc').getAttribute('class')).toContain('page-rpc')
  if (await canvas.locator('.react-flow').count()) {
    await canvas.getByRole('button', { name: /zoom in/i }).click()
  } else {
    await canvas.getByRole('button', { name: 'Phóng to sơ đồ', exact: true }).click()
  }
  await page.waitForTimeout(250)
  const viewport = canvas.locator('.react-flow__viewport, .offline-world')
  const transform = await viewport.getAttribute('style')
  await canvas.evaluate(element => {
    const win = window as any
    win.__cachedCanvas = element.querySelector('.diagram')
    win.__graphMutations = 0
    win.__graphObserver = new MutationObserver(items => { win.__graphMutations += items.length })
    win.__graphObserver.observe(win.__cachedCanvas, { subtree: true, attributes: true, childList: true })
  })
  await page.waitForTimeout(1300)
  expect(await page.evaluate(() => (window as any).__graphMutations)).toBe(0)
  await page.locator('.nav-item').nth(2).click()
  await expect(page.locator('[data-topology-page=rpc]')).toBeHidden()
  await expect(page.locator('[data-topology-page=rpc]')).toHaveAttribute('inert', '')
  await page.locator('.nav-item').nth(1).click()
  await expect(canvas).toBeVisible()
  expect(await canvas.evaluate(element => element.querySelector('.diagram') === (window as any).__cachedCanvas)).toBe(true)
  await expect(viewport).toHaveAttribute('style', transform!)
  await expect(canvas.locator('.message-pulse')).toHaveCount(0)
  await page.screenshot({ path: '../test-results/performance-cached-rpc.png', fullPage: true })
})
