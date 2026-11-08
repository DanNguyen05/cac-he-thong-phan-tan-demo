import { test, expect } from '@playwright/test'
import { spawn, execFile, type ChildProcess } from 'node:child_process'
import { mkdirSync, openSync, closeSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { createServer } from 'node:net'
import { promisify } from 'node:util'

test('browser reflects real before/after-decision crashes and inventory restart', async ({ page }, info) => {
  const root = resolve(import.meta.dirname, '../..')
  const names = ['gateway', 'coordinator', 'rpc', 'A', 'B', 'C']
  const dockerNames: Record<string, string> = { gateway: 'dashboard', coordinator: 'coordinator', rpc: 'rpc', A: 'participant-a', B: 'participant-b', C: 'participant-c' }
  const docker = process.env.KV_UI_DOCKER === '1'
  let base = 19000
  if (!docker) {
    for (let candidate = 23800; candidate < 23900; candidate += 10) {
      const sockets = []
      try {
        for (let offset = 0; offset < 6; offset++) {
          const socket = createServer(); sockets.push(socket)
          await new Promise<void>((ok, fail) => { socket.once('error', fail); socket.listen(candidate + offset, '127.0.0.1', ok) })
        }
        base = candidate
        break
      } catch { /* Try an unused range without stopping any other application. */ }
      finally { await Promise.all(sockets.map(socket => new Promise<void>(ok => { if (socket.listening) socket.close(() => ok()); else ok() }))) }
    }
    expect(base).not.toBe(19000)
  }
  const urls = Object.fromEntries(names.map((name, index) => [name, `http://127.0.0.1:${base + index}`]))
  const children: Record<string, ChildProcess> = {}, handles: number[] = []
  const compose = async (...args: string[]) => promisify(execFile)('docker', ['compose', '-p', 'kv-transaction-lab', '-f', join(root, 'compose.yaml'), ...args], { cwd: root })
  const stop = async (name: string) => {
    if (docker) { await compose('kill', '-s', 'SIGKILL', dockerNames[name]); return }
    const child = children[name]
    if (child && child.exitCode === null && !child.killed) await new Promise<void>(ok => { child.once('exit', () => ok()); child.kill() })
  }
  const start = async (name: string) => {
    if (docker) await compose('start', dockerNames[name])
    else {
      const folder = info.outputPath('services', name); mkdirSync(folder, { recursive: true })
      const log = openSync(join(folder, 'service.log'), 'a'); handles.push(log)
      const module = name === 'gateway' ? 'kv_gateway' : name === 'coordinator' ? 'kv_coordinator' : 'kv_node'
      children[name] = spawn(process.env.PYTHON || 'python', ['-m', 'uvicorn', `backend.${module}:app`, '--host', '127.0.0.1', '--port', String(base + names.indexOf(name)), '--log-level', 'warning'], { cwd: root, windowsHide: true, stdio: ['ignore', log, log], env: { ...process.env, LAB_DATA: folder, KV_SERVICE: name, KV_RUNTIME: 'process', KV_COORDINATOR: urls.coordinator, KV_RPC_SERVER: urls.rpc, KV_PEERS: JSON.stringify(Object.fromEntries(['A', 'B', 'C'].map(n => [n, urls[n]]))) } })
    }
    await expect.poll(async () => { try { return (await page.request.get(urls[name] + '/health')).ok() } catch { return false } }, { timeout: 20_000 }).toBe(true)
  }
  const reset = async () => expect((await page.request.post(urls.gateway + '/api/reset')).ok()).toBe(true)
  const run = async (route: string, scenario: string) => {
    await page.goto(urls.gateway + route)
    await expect(page.getByTestId('connection')).toHaveAttribute('data-connected', 'true')
    await page.locator('#scenario').selectOption(scenario)
    await page.getByRole('button', { name: '2×', exact: true }).click()
    await page.getByRole('button', { name: 'Chạy thí nghiệm', exact: true }).click()
  }
  const boot = async (name: string) => (await (await page.request.get(urls[name] + '/health')).json()).boot_id
  try {
    for (const name of names) await start(name)
    await reset()
    await run('/commit', 'coordinator_crash')
    await expect(page.locator('.external-fault')).toContainText('chưa ghi quyết định')
    await stop('coordinator')
    await expect(page.getByTestId('current-status')).toContainText('2PC đang blocking')
    await expect(page.locator('.timeline-symbol.red').first()).toBeVisible()
    await expect(page.locator('.topology-page:not([hidden]) .service-node .node-status').filter({ hasText: 'PREPARED' })).toHaveCount(3)
    await page.screenshot({ path: '../test-results/kv-crash-before-decision.png', fullPage: true })
    await start('coordinator')
    await expect(page.getByTestId('current-status')).toContainText('Giao dịch đã ABORT')
    await expect(page.getByTestId('kv-A')).toContainText('100')

    await reset()
    await run('/commit', 'coordinator_after_commit')
    await expect(page.locator('.external-fault')).toContainText('COMMIT bền vững')
    await stop('coordinator')
    await expect(page.getByTestId('current-status')).toContainText('2PC đang blocking')
    await page.screenshot({ path: '../test-results/kv-crash-after-decision.png', fullPage: true })
    await start('coordinator')
    await expect(page.getByTestId('current-status')).toContainText('Hoàn thành thành công')
    await expect(page.getByTestId('kv-A')).toContainText('90')
    await expect(page.getByTestId('kv-B')).toContainText('110')

    await run('/recovery', 'crash_recover')
    await expect(page.locator('.external-fault')).toContainText('restart Node A thật')
    await expect(page.getByRole('button', { name: /Bước tiếp/ })).toBeDisabled()
    const oldBoot = await boot('A')
    await stop('A')
    await expect(page.getByTestId('kv-A')).toContainText('OFFLINE')
    await page.screenshot({ path: '../test-results/kv-recovery-offline.png', fullPage: true })
    await start('A')
    await expect(page.getByTestId('current-status')).toContainText('Hoàn thành thành công')
    expect(await boot('A')).not.toBe(oldBoot)
    await expect(page.getByTestId('kv-A')).toContainText('95')
    const direct = await (await page.request.get(urls.A + '/kv/inventory')).json()
    expect(direct.value).toBe(95)
    await page.screenshot({ path: '../test-results/kv-recovery-restarted.png', fullPage: true })

    await run('/group', 'node_down')
    await expect(page.locator('.external-fault')).toContainText('dừng receiver B thật')
    await stop('B')
    await expect(page.getByTestId('current-status')).toContainText('Một số node chưa nhận', { timeout: 15_000 })
    await expect(page.getByTestId('kv-B')).toContainText('OFFLINE')
    await start('B')
    await page.getByRole('button', { name: 'Catch-up Node B', exact: true }).click()
    await expect(page.getByTestId('current-status')).toContainText('Hoàn thành thành công')
    await expect(page.getByTestId('kv-B')).toContainText('1 · 2 · 3')

    expect((await page.request.post(urls.gateway + '/api/kv/rpc', { data: { id: 'persistent-counter', key: 'counter', operation: 'INCREMENT', value: 7 } })).ok()).toBe(true)
    await run('/rpc', 'server_down')
    await expect(page.locator('.external-fault')).toContainText('dừng RPC Server thật')
    await stop('rpc')
    await expect(page.getByTestId('current-status')).toContainText('Thí nghiệm thất bại')
    await expect(page.getByTestId('kv-rpc')).toContainText('OFFLINE')
    await start('rpc')
    expect((await (await page.request.get(urls.rpc + '/kv/counter')).json()).value).toBe(7)
    await page.screenshot({ path: '../test-results/kv-rpc-restarted.png', fullPage: true })
  } finally {
    if (docker) { await compose('start', 'coordinator', 'participant-a', 'participant-b', 'rpc') }
    else for (const name of names) await stop(name)
    for (const handle of handles) closeSync(handle)
  }
})
