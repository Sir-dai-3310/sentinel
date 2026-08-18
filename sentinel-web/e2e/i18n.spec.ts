import { test, expect, Page } from '@playwright/test'

/**
 * i18n E2E: verifies that the language switcher actually re-renders the UI
 * in the selected language and that the preference persists across reloads.
 */

async function selectLanguage(page: Page, code: string) {
  const switcher = page.getByTestId('language-switcher').locator('select')
  await switcher.selectOption(code)
}

test.describe('Internationalization', () => {
  test('defaults to English navigation', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Analysis' })).toBeVisible()
    await expect(page.locator('h2')).toContainText('Security Dashboard')
  })

  test('switches to Chinese and renders translated nav + dashboard', async ({ page }) => {
    await page.goto('/')
    await selectLanguage(page, 'zh')

    // Nav labels
    await expect(page.getByRole('link', { name: '仪表盘' })).toBeVisible()
    await expect(page.getByRole('link', { name: '日志分析' })).toBeVisible()
    await expect(page.getByRole('link', { name: '规则管理' })).toBeVisible()
    await expect(page.getByRole('link', { name: '系统设置' })).toBeVisible()

    // Dashboard content
    await expect(page.locator('h2')).toContainText('安全仪表盘')
    await expect(page.locator('text=总事件数')).toBeVisible()
    await expect(page.locator('text=系统状态')).toBeVisible()
  })

  test('switches to Japanese', async ({ page }) => {
    await page.goto('/')
    await selectLanguage(page, 'ja')

    await expect(page.getByRole('link', { name: 'ダッシュボード' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'ルール管理' })).toBeVisible()
    await expect(page.locator('h2')).toContainText('セキュリティダッシュボード')
    await expect(page.locator('text=総イベント数')).toBeVisible()
  })

  test('switches to Korean', async ({ page }) => {
    await page.goto('/')
    await selectLanguage(page, 'ko')

    await expect(page.getByRole('link', { name: '대시보드' })).toBeVisible()
    await expect(page.locator('h2')).toContainText('보안 대시보드')
  })

  test('switches to Spanish', async ({ page }) => {
    await page.goto('/')
    await selectLanguage(page, 'es')

    await expect(page.getByRole('link', { name: 'Panel' })).toBeVisible()
    await expect(page.locator('h2')).toContainText('Panel de Seguridad')
  })

  test('language preference persists across reload', async ({ page }) => {
    await page.goto('/')
    await selectLanguage(page, 'zh')
    await expect(page.locator('h2')).toContainText('安全仪表盘')

    // localStorage must contain the i18next language cache
    const stored = await page.evaluate(() => localStorage.getItem('i18nextLng'))
    expect(stored).toBe('zh')

    // Reload and verify the preference survives
    await page.reload()
    await expect(page.getByRole('link', { name: '仪表盘' })).toBeVisible()
    await expect(page.locator('h2')).toContainText('安全仪表盘')
  })

  test('switching back to English restores original text', async ({ page }) => {
    await page.goto('/')
    await selectLanguage(page, 'ja')
    await expect(page.locator('h2')).toContainText('セキュリティダッシュボード')

    await selectLanguage(page, 'en')
    await expect(page.locator('h2')).toContainText('Security Dashboard')
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
  })
})
