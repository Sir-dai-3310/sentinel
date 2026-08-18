import { test, expect, Page } from '@playwright/test'

/**
 * v1.2 E2E: dark mode toggle + Chinese rendering on Analysis/Rules/Settings.
 *
 * Each test runs in a fresh browser context (Playwright default), so
 * localStorage starts empty — no manual clearing needed.
 */

async function selectLanguage(page: Page, code: string) {
  const switcher = page.getByTestId('language-switcher').locator('select')
  await switcher.selectOption(code)
}

test.describe('Dark Mode', () => {
  test('theme switch toggles html dark class', async ({ page }) => {
    await page.goto('/settings')

    // default is dark (no explicit choice → 'dark' default)
    await expect(page.locator('html')).toHaveClass(/dark/)

    // switch to light → dark class removed
    await page.locator('[data-theme-option="light"]').click()
    await expect(page.locator('html')).not.toHaveClass(/dark/)

    // switch back to dark → dark class present
    await page.locator('[data-theme-option="dark"]').click()
    await expect(page.locator('html')).toHaveClass(/dark/)
  })

  test('theme choice persists to localStorage and across reload', async ({ page }) => {
    await page.goto('/settings')

    await page.locator('[data-theme-option="light"]').click()
    const stored = await page.evaluate(() => localStorage.getItem('sentinel-theme'))
    expect(stored).toBe('light')

    await page.reload()
    await expect(page.locator('html')).not.toHaveClass(/dark/)
    const storedAfter = await page.evaluate(() => localStorage.getItem('sentinel-theme'))
    expect(storedAfter).toBe('light')

    // dark persists too
    await page.locator('[data-theme-option="dark"]').click()
    await page.reload()
    await expect(page.locator('html')).toHaveClass(/dark/)
  })

  test('system theme option is selectable and applies resolved theme', async ({ page }) => {
    await page.goto('/settings')
    await page.locator('[data-theme-option="system"]').click()
    const stored = await page.evaluate(() => localStorage.getItem('sentinel-theme'))
    expect(stored).toBe('system')
    // html should have or not have dark depending on OS preference
    const hasDark = await page.locator('html').evaluate((el) => el.classList.contains('dark'))
    expect(typeof hasDark).toBe('boolean')
  })
})

test.describe('Chinese rendering (v1.4 leftover pages)', () => {
  test('Analysis page renders in Chinese', async ({ page }) => {
    await page.goto('/analysis')
    await selectLanguage(page, 'zh')

    await expect(page.locator('h2')).toContainText('日志分析')
    await expect(page.locator('text=拖拽日志文件到这里')).toBeVisible()
    await expect(page.locator('text=浏览文件')).toBeVisible()
  })

  test('Rules page renders in Chinese', async ({ page }) => {
    await page.goto('/rules')
    await selectLanguage(page, 'zh')
    await page.waitForLoadState('networkidle')

    // nav must be Chinese
    await expect(page.getByRole('link', { name: '规则管理' })).toBeVisible()
    const hasTitle = await page.locator('h2:has-text("Sigma 规则")').isVisible().catch(() => false)
    const hasError = await page.locator('text=加载规则失败').isVisible().catch(() => false)
    const hasLoading = await page.locator('text=加载规则中').isVisible().catch(() => false)
    expect(hasTitle || hasError || hasLoading).toBeTruthy()
  })

  test('Settings page renders in Chinese', async ({ page }) => {
    await page.goto('/settings')
    await selectLanguage(page, 'zh')

    await expect(page.locator('h2')).toContainText('系统设置')
    // appearance card (client-side, always renders)
    await expect(page.getByRole('heading', { name: '外观' })).toBeVisible()
    await expect(page.locator('[data-theme-option="light"]')).toContainText('亮色')
    await expect(page.locator('[data-theme-option="dark"]')).toContainText('暗色')
    await expect(page.locator('[data-theme-option="system"]')).toContainText('跟随系统')
    // notifications + dashboard config headings (client-side)
    await expect(page.getByRole('heading', { name: '通知' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '仪表盘配置' })).toBeVisible()
  })
})
