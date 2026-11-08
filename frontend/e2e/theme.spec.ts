import { expect, test } from '@playwright/test'

test('every workspace stays light even with a previously saved dark preference', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('fault-lab-theme', 'dark'))
  for (const route of ['/', '/rpc', '/group', '/commit', '/recovery']) {
    await page.goto(route)
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
    await expect(page.locator('.react-flow')).toHaveClass(/light/)
    await expect(page.getByRole('button', { name: /Chuyển sang chủ đề/ })).toHaveCount(0)
    const surfaces = await page.evaluate(() => {
      return ['.sidebar', '.topbar', '.topology-panel', '.diagram'].map(selector => ({
        selector, background: getComputedStyle(document.querySelector(selector)!).backgroundColor,
      }))
    })
    for (const surface of surfaces) expect(['rgb(248, 250, 252)', 'rgb(255, 255, 255)'], JSON.stringify(surface)).toContain(surface.background)
  }
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.screenshot({ path: '../test-results/light-mode-recovery.png', fullPage: true })
})

test('light palette has readable text, status colors, code blocks and inspector', async ({ page }) => {
  await page.goto('/commit')
  const contrasts = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement)
    const luminance = (token: string) => {
      const raw = style.getPropertyValue(token).trim().replace('#', '')
      const hex = raw.length === 3 ? [...raw].map(value => value + value).join('') : raw
      const channels = [0, 2, 4].map(index => parseInt(hex.slice(index, index + 2), 16) / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4)
      return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722
    }
    return ['--text', '--muted', '--cyan', '--teal', '--green', '--amber', '--blue', '--red'].flatMap(foreground =>
      ['--bg', '--panel'].map(background => {
        const a = luminance(foreground), b = luminance(background)
        return { foreground, background, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) }
      }))
  })
  for (const pair of contrasts) expect(pair.ratio, JSON.stringify(pair)).toBeGreaterThanOrEqual(4.5)
  await page.locator('.topology-page:not([hidden]) .service-node').filter({ hasText: 'Node A' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  expect(await dialog.evaluate(element => getComputedStyle(element).backgroundColor)).toBe('rgb(255, 255, 255)')
  expect(await dialog.locator('pre').evaluate(element => getComputedStyle(element).backgroundColor)).toBe('rgb(248, 250, 252)')
  await page.screenshot({ path: '../test-results/light-mode-inspector.png', fullPage: true })
  await page.keyboard.press('Escape')
})

test('SVG fallback and presentation remain light and keyboard execution still works', async ({ page, request }) => {
  expect((await request.post('/api/reset')).ok()).toBeTruthy()
  await page.goto('/rpc?renderer=svg')
  await expect(page.locator('[data-renderer="svg"]')).toBeVisible()
  await expect(page.getByTestId('connection')).toHaveAttribute('data-connected', 'true')
  await page.getByRole('button', { name: 'Từng bước', exact: true }).click()
  await page.getByRole('button', { name: /^Trình chiếu/ }).click()
  await page.getByRole('button', { name: 'Chạy thí nghiệm' }).click()
  await expect(page.getByRole('button', { name: /^Bước tiếp/ })).toBeEnabled()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await expect(page.getByRole('button', { name: /Chuyển sang chủ đề/ })).toHaveCount(0)
  await page.keyboard.press('n')
  await expect.poll(async () => (await (await request.get('/api/state')).json()).run.status).toBe('COMPLETED')
  await expect(page.getByTestId('rpc-executions')).toContainText('1 lần')
  await page.screenshot({ path: '../test-results/light-mode-svg-presentation.png', fullPage: true })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: /^Trình chiếu/ })).toBeVisible()
})
