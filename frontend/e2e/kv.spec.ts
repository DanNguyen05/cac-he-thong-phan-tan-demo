import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page, request }) => {
  await expect.poll(async () => {
    try {
      const response = await request.get('/api/health')
      const state = await response.json()
      return Object.keys(state.processes || {}).length === 5 && Object.values(state.processes).every((service: any) => service.alive)
    } catch { return false }
  }, { timeout: 20_000 }).toBe(true)
  expect((await request.post('/api/reset')).ok()).toBeTruthy()
  await page.goto('/rpc')
  await expect(page.getByTestId('connection')).toHaveAttribute('data-connected', 'true')
  await expect(page.getByTestId('kv-workbench')).toBeVisible()
})

test('KV editor sends real GET/PUT and inputs do not trigger protocol shortcuts', async ({ page, request }) => {
  await page.getByRole('button', { name: 'GET / PUT', exact: true }).click()
  await page.getByLabel('KV key', { exact: true }).fill('demo-key')
  await page.getByLabel('KV value', { exact: true }).fill('np')
  await page.getByRole('button', { name: 'Ghi KV', exact: true }).click()
  await expect(page.getByTestId('kv-http-result')).toContainText('np')
  const actual = await (await request.get('/api/kv/rpc/demo-key')).json()
  expect(actual.value).toBe('np')
  await page.getByRole('button', { name: 'GET', exact: true }).click()
  await expect(page.getByTestId('kv-http-result')).toContainText('demo-key')
  expect((await (await request.get('/api/state')).json()).run).toBeNull()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('lost response shows two attempts, one execution and actual counter', async ({ page, request }) => {
  await page.locator('#scenario').selectOption('lost_response')
  await page.getByRole('button', { name: '2×', exact: true }).click()
  await page.getByRole('button', { name: 'Chạy thí nghiệm', exact: true }).click()
  await expect(page.getByTestId('current-status')).toContainText('Hoàn thành thành công')
  await expect(page.getByTestId('kv-rpc')).toContainText('1')
  await expect(page.locator('.kv-verification')).toContainText('2 attempts / 1 executions')
  await expect(page.getByTestId('metric-Yêu cầu')).toHaveText('2')
  await expect(page.getByTestId('metric-Thành công')).toHaveText('1')
  const journal = (await (await request.get('/api/state')).json()).events
  expect(journal.filter((event: any) => event.kind === 'SEND').every((event: any) => event.target === 'rpc' && event.data.path === '/kv')).toBe(true)
  expect((await (await request.get('/api/kv/rpc/counter')).json()).value).toBe(1)
  await page.screenshot({ path: '../test-results/kv-rpc.png', fullPage: true })
})

test('multicast reports real NACK and FIFO delivery to all nodes', async ({ page, request }) => {
  await page.goto('/group')
  await page.locator('#scenario').selectOption('lost_message')
  await page.getByRole('button', { name: '2×', exact: true }).click()
  await page.getByRole('button', { name: 'Chạy thí nghiệm', exact: true }).click()
  await expect(page.getByTestId('current-status')).toContainText('Hoàn thành thành công')
  for (const name of ['A', 'B', 'C']) {
    await expect(page.getByTestId('kv-' + name)).toContainText('1 · 2 · 3')
    await expect(page.getByTestId('kv-' + name)).toContainText('Thiếu: —')
  }
  const state = await (await request.get('/api/state')).json()
  expect(state.events.some((event: any) => event.kind === 'NACK' && event.source === 'B')).toBe(true)
  await page.screenshot({ path: '../test-results/kv-group.png', fullPage: true })
})

test('2PC and local recovery render verified KV instead of sample numbers', async ({ page, request }) => {
  await page.goto('/commit')
  await page.getByRole('button', { name: '2×', exact: true }).click()
  await page.getByRole('button', { name: 'Chạy thí nghiệm', exact: true }).click()
  await expect(page.getByTestId('current-status')).toContainText('Hoàn thành thành công')
  await expect(page.getByTestId('kv-A')).toContainText('90')
  await expect(page.getByTestId('kv-B')).toContainText('110')
  await expect(page.locator('.kv-verification')).toContainText('Đã kiểm chứng')
  await page.getByRole('button', { name: 'Trình chiếu', exact: true }).click()
  await expect(page.locator('.sidebar')).toBeHidden()
  await page.screenshot({ path: '../test-results/kv-commit-presentation.png', fullPage: true })
  await page.keyboard.press('Escape')
  await page.goto('/recovery')
  await page.getByRole('button', { name: '2×', exact: true }).click()
  await page.getByRole('button', { name: 'Chạy thí nghiệm', exact: true }).click()
  await expect(page.getByTestId('current-status')).toContainText('Hoàn thành thành công')
  await expect(page.getByTestId('kv-A')).toContainText('95')
  expect((await (await request.get('/api/kv/A/inventory')).json()).value).toBe(95)
  await page.screenshot({ path: '../test-results/kv-recovery.png', fullPage: true })
})

test('recorded replay never sends run, step, control or write requests', async ({ page }) => {
  await page.getByRole('button', { name: 'Chạy thí nghiệm', exact: true }).click()
  await expect(page.getByTestId('current-status')).toContainText('Hoàn thành thành công')
  const mutations: string[] = []
  page.on('request', req => { if (req.method() === 'POST') mutations.push(req.url()) })
  await page.getByRole('button', { name: 'Replay log', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('REPLAY')
  await page.getByRole('button', { name: 'Phát replay', exact: true }).click()
  await page.getByRole('button', { name: 'Sự kiện tiếp', exact: true }).click()
  await page.keyboard.press('n')
  await page.keyboard.press('p')
  expect(mutations).toEqual([])
})

test('new KV UI fits every workspace and viewport, including SVG fallback', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message))
  for (const width of [375, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const route of ['/', '/rpc', '/group', '/commit', '/recovery']) {
      await page.goto(route)
      await expect(page.getByTestId('kv-workbench')).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
  }
  await page.goto('/rpc?renderer=svg')
  await expect(page.locator('[data-renderer=svg]')).toBeVisible()
  await page.getByRole('button', { name: 'Kiểm tra Server' }).click()
  await expect(page.getByRole('dialog')).toContainText('rpc')
  await expect(page.getByRole('button', { name: 'Crash tiến trình', exact: true })).toHaveCount(0)
  expect(errors).toEqual([])
})

test('step mode gates real RPC and N works after clicking the run button', async ({ page, request }) => {
  await page.getByRole('button', { name: 'Từng bước', exact: true }).click()
  await page.getByRole('button', { name: 'Chạy thí nghiệm', exact: true }).click()
  await expect(page.getByRole('button', { name: /Bước tiếp/ })).toBeEnabled()
  expect((await (await request.get('/api/kv/rpc/counter')).json()).value).toBe(0)
  await page.keyboard.press('n')
  await expect(page.getByTestId('current-status')).toContainText('Hoàn thành thành công')
  expect((await (await request.get('/api/kv/rpc/counter')).json()).value).toBe(1)
})
