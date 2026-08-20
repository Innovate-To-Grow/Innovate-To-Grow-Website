import AxeBuilder from '@axe-core/playwright'
import {expect, test} from '@playwright/test'

function statusFixture() {
  const generatedAt = new Date().toISOString()
  const end = Date.parse(`${generatedAt.slice(0, 10)}T00:00:00Z`)
  const history = Array.from({length: 90}, (_, index) => ({
    date: new Date(end - (89 - index) * 86_400_000).toISOString().slice(0, 10),
    status: 'operational',
    uptimePercent: 100,
    coveragePercent: 100,
    sampleCount: 288,
    maintenanceSampleCount: 0,
  }))
  const components = [
    ['production-website', 'Production Website', 'production'],
    ['production-api', 'Production API', 'production'],
    ['demo-website', 'Demo Website', 'demo'],
    ['demo-api', 'Demo API', 'demo'],
    ['project-archive', 'Project Archive', 'archive'],
  ].map(([id, name, group]) => ({
    id,
    name,
    group,
    status: 'operational',
    checkedAt: generatedAt,
    uptime: {hours24: 100, days90: 99.99},
    history,
  }))
  return {
    schemaVersion: 1,
    generatedAt,
    nextCheckAt: new Date(Date.now() + 300_000).toISOString(),
    stale: false,
    overallStatus: 'operational',
    summary: {
      message: 'All monitored services are operating normally.',
      availability24h: {
        percent: 100,
        availableChecks: 1_440,
        eligibleChecks: 1_440,
        scheduledChecks: 1_440,
        maintenanceChecks: 0,
        monitoringCoveragePercent: 100,
      },
      activeIncidentCount: 0,
      incidents24h: 0,
    },
    components,
    incidents: [],
  }
}

test.beforeEach(async ({page}) => {
  await page.route('**/api/status', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(statusFixture())}),
  )
})

test('shows the complete public status and passes automated accessibility checks', async ({page}) => {
  await page.goto('/')
  await expect(page.getByRole('heading', {name: 'All systems operational'})).toBeVisible()
  await expect(page.locator('.component-card')).toHaveCount(5)
  await expect(page.locator('.history-bar')).toHaveCount(450)
  await expect(page.getByText('No incidents have been recorded in the past 90 days.')).toBeVisible()

  const results = await new AxeBuilder({page}).analyze()
  expect(results.violations).toEqual([])
})

test('fits the mobile viewport without horizontal page overflow', async ({page}, testInfo) => {
  test.skip(!testInfo.project.name.includes('mobile'), 'mobile-only layout assertion')
  await page.goto('/')
  await expect(page.getByRole('heading', {name: 'All systems operational'})).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})

test('keeps an explanatory shell when JavaScript is unavailable', async ({browser, baseURL}) => {
  const context = await browser.newContext({javaScriptEnabled: false})
  const page = await context.newPage()
  await page.goto(baseURL ?? 'http://127.0.0.1:4173')

  await expect(page.getByRole('heading', {name: 'Checking system status'})).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('JavaScript is required to retrieve live status data')
  await context.close()
})
