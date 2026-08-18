# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: app.spec.ts >> Sentinel E2E Tests >> Dashboard loads and displays statistics
- Location: e2e/app.spec.ts:4:3

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: page.goto: Test timeout of 30000ms exceeded.
Call log:
  - navigating to "http://localhost:3000/", waiting until "load"

```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test'
  2  | 
  3  | test.describe('Sentinel E2E Tests', () => {
  4  |   test('Dashboard loads and displays statistics', async ({ page }) => {
> 5  |     await page.goto('/')
     |                ^ Error: page.goto: Test timeout of 30000ms exceeded.
  6  | 
  7  |     // Check title
  8  |     await expect(page.locator('h2')).toContainText('Security Dashboard')
  9  | 
  10 |     // Check stat cards are visible
  11 |     await expect(page.locator('text=Total Events')).toBeVisible()
  12 |     await expect(page.locator('text=Alerts')).toBeVisible()
  13 |     await expect(page.locator('text=Critical')).toBeVisible()
  14 |     await expect(page.locator('text=Accuracy')).toBeVisible()
  15 | 
  16 |     // Check system status panel
  17 |     await expect(page.locator('text=System Status')).toBeVisible()
  18 |   })
  19 | 
  20 |   test('Analysis page renders upload area', async ({ page }) => {
  21 |     await page.goto('/analysis')
  22 | 
  23 |     // Check title
  24 |     await expect(page.locator('h2')).toContainText('Log Analysis')
  25 | 
  26 |     // Check upload area
  27 |     await expect(page.locator('text=Drop your log file here')).toBeVisible()
  28 |     await expect(page.locator('text=Browse Files')).toBeVisible()
  29 | 
  30 |     // Check connection status indicator exists
  31 |     await expect(page.locator('text=/Connected|Disconnected/')).toBeVisible()
  32 |   })
  33 | 
  34 |   test('Rules page displays rule list', async ({ page }) => {
  35 |     await page.goto('/rules')
  36 | 
  37 |     // Wait for page to finish loading (either content or error)
  38 |     await page.waitForLoadState('networkidle')
  39 | 
  40 |     // Check that the page rendered (either title or loading/error state)
  41 |     const hasTitle = await page.locator('text=Sigma Rules').isVisible().catch(() => false)
  42 |     const hasLoading = await page.locator('text=Loading rules').isVisible().catch(() => false)
  43 |     const hasError = await page.locator('text=Failed to load rules').isVisible().catch(() => false)
  44 |     const hasButtons = await page.locator('text=Reload').isVisible().catch(() => false)
  45 | 
  46 |     // At least one indicator should be visible
  47 |     expect(hasTitle || hasLoading || hasError || hasButtons).toBeTruthy()
  48 |   })
  49 | 
  50 |   test('Settings page displays configuration', async ({ page }) => {
  51 |     await page.goto('/settings')
  52 | 
  53 |     // Wait for page to finish loading
  54 |     await page.waitForLoadState('networkidle')
  55 | 
  56 |     // Should show settings sections or error state
  57 |     const hasSettings = await page.locator('text=Settings').isVisible().catch(() => false)
  58 |     const hasError = await page.locator('text=Failed to load settings').isVisible().catch(() => false)
  59 |     const hasLoading = await page.locator('text=Loading settings').isVisible().catch(() => false)
  60 | 
  61 |     // At least one should be visible (settings or error message)
  62 |     expect(hasSettings || hasError || hasLoading).toBeTruthy()
  63 |   })
  64 | 
  65 |   test('Navigation works between pages', async ({ page }) => {
  66 |     await page.goto('/')
  67 |     await page.waitForLoadState('networkidle')
  68 | 
  69 |     // Navigate to Analysis
  70 |     await page.click('text=Analysis')
  71 |     await expect(page).toHaveURL('/analysis')
  72 | 
  73 |     // Navigate to Rules
  74 |     await page.click('text=Rules')
  75 |     await expect(page).toHaveURL('/rules')
  76 | 
  77 |     // Navigate to Settings
  78 |     await page.click('text=Settings')
  79 |     await expect(page).toHaveURL('/settings')
  80 | 
  81 |     // Navigate back to Dashboard
  82 |     await page.click('text=Dashboard')
  83 |     await expect(page).toHaveURL('/')
  84 |   })
  85 | })
  86 | 
```