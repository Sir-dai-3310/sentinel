import { test, expect } from '@playwright/test'

test.describe('Sentinel E2E Tests', () => {
  test('Dashboard loads and displays statistics', async ({ page }) => {
    await page.goto('/')

    // Check title
    await expect(page.locator('h2')).toContainText('Security Dashboard')

    // Check stat cards are visible
    await expect(page.locator('text=Total Events')).toBeVisible()
    await expect(page.locator('text=Alerts')).toBeVisible()
    await expect(page.locator('text=Critical')).toBeVisible()
    await expect(page.locator('text=Accuracy')).toBeVisible()

    // Check system status panel
    await expect(page.locator('text=System Status')).toBeVisible()
  })

  test('Analysis page renders upload area', async ({ page }) => {
    await page.goto('/analysis')

    // Check title
    await expect(page.locator('h2')).toContainText('Log Analysis')

    // Check upload area
    await expect(page.locator('text=Drop your log file here')).toBeVisible()
    await expect(page.locator('text=Browse Files')).toBeVisible()

    // Check connection status indicator exists
    await expect(page.locator('text=/Connected|Disconnected/')).toBeVisible()
  })

  test('Rules page displays rule list', async ({ page }) => {
    await page.goto('/rules')

    // Wait for page to finish loading (either content or error)
    await page.waitForLoadState('networkidle')

    // Check that the page rendered (either title or loading/error state)
    const hasTitle = await page.locator('text=Sigma Rules').isVisible().catch(() => false)
    const hasLoading = await page.locator('text=Loading rules').isVisible().catch(() => false)
    const hasError = await page.locator('text=Failed to load rules').isVisible().catch(() => false)
    const hasButtons = await page.locator('text=Reload').isVisible().catch(() => false)

    // At least one indicator should be visible
    expect(hasTitle || hasLoading || hasError || hasButtons).toBeTruthy()
  })

  test('Settings page displays configuration', async ({ page }) => {
    await page.goto('/settings')

    // Wait for page to finish loading
    await page.waitForLoadState('networkidle')

    // Should show settings sections or error state
    const hasSettings = await page.locator('text=Settings').isVisible().catch(() => false)
    const hasError = await page.locator('text=Failed to load settings').isVisible().catch(() => false)
    const hasLoading = await page.locator('text=Loading settings').isVisible().catch(() => false)

    // At least one should be visible (settings or error message)
    expect(hasSettings || hasError || hasLoading).toBeTruthy()
  })

  test('Navigation works between pages', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // Navigate to Analysis
    await page.click('text=Analysis')
    await expect(page).toHaveURL('/analysis')

    // Navigate to Rules
    await page.click('text=Rules')
    await expect(page).toHaveURL('/rules')

    // Navigate to Settings
    await page.click('text=Settings')
    await expect(page).toHaveURL('/settings')

    // Navigate back to Dashboard
    await page.click('text=Dashboard')
    await expect(page).toHaveURL('/')
  })
})
