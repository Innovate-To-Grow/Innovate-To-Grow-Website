import AxeBuilder from '@axe-core/playwright'
import {expect, test} from '@playwright/test'

function statusFixture(status = 'operational') {
  const generatedAt = new Date().toISOString()
  const end = Date.parse(`${generatedAt.slice(0, 10)}T00:00:00Z`)
  const history = Array.from({length: 90}, (_, index) => ({
    date: new Date(end - (89 - index) * 86_400_000).toISOString().slice(0, 10),
    status,
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
    overallStatus: status,
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
  const campusLogo = page.getByRole('img', {name: 'UC Merced'})
  await expect(campusLogo).toBeVisible()
  const logoState = await campusLogo.evaluate((image: HTMLImageElement) => ({
    complete: image.complete,
    naturalWidth: image.naturalWidth,
    naturalHeight: image.naturalHeight,
    localSource:
      image.currentSrc.startsWith('data:image/') ||
      new URL(image.currentSrc).origin === window.location.origin,
  }))
  expect(logoState).toMatchObject({
    complete: true,
    naturalWidth: 230,
    naturalHeight: 57,
    localSource: true,
  })
  await expect(page.locator('.component-card')).toHaveCount(5)
  await expect(page.locator('.history-bar')).toHaveCount(450)
  await expect(page.getByText('No incidents have been recorded in the past 90 days.')).toBeVisible()

  const results = await new AxeBuilder({page}).analyze()
  expect(results.violations).toEqual([])
})

test('loads the self-hosted Inter variable typeface across the page', async ({page}) => {
  await page.goto('/')
  await expect(page.getByRole('heading', {name: 'All systems operational'})).toBeVisible()

  const typography = await page.evaluate(async () => {
    await document.fonts.ready
    const heading = document.querySelector('h1')
    return {
      bodyFamily: getComputedStyle(document.body).fontFamily,
      headingFamily: heading ? getComputedStyle(heading).fontFamily : '',
      loadedInterFace: [...document.fonts].some(
        (face) => face.family === 'Inter Variable' && face.status === 'loaded',
      ),
    }
  })

  expect(typography.bodyFamily).toContain('Inter Variable')
  expect(typography.headingFamily).toContain('Inter Variable')
  expect(typography.loadedInterFace).toBe(true)
})

test('keeps active incident headings in order and passes accessibility checks', async ({page}) => {
  const base = statusFixture('degraded')
  const fixture = {
    ...base,
    summary: {
      ...base.summary,
      message: 'Automated checks detected an issue affecting the production API.',
      activeIncidentCount: 1,
      incidents24h: 1,
    },
    incidents: [
      {
        id: 'incident-production-api-test',
        kind: 'incident',
        state: 'investigating',
        impact: 'degraded',
        title: 'Production API errors',
        startedAt: base.generatedAt,
        resolvedAt: null,
        affectedComponentIds: ['production-api'],
        updates: [
          {
            timestamp: base.generatedAt,
            state: 'investigating',
            message: 'The team is investigating.',
          },
        ],
      },
    ],
  }
  await page.unroute('**/api/status')
  await page.route('**/api/status', (route) =>
    route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(fixture)}),
  )

  await page.goto('/')
  await expect(page.getByRole('heading', {level: 2, name: 'Active incidents'})).toBeVisible()
  await expect(page.getByRole('heading', {level: 3, name: 'Production API errors'})).toBeVisible()
  const results = await new AxeBuilder({page}).analyze()
  expect(results.violations).toEqual([])
})

test('keeps all runtime requests same-origin and does not register a service worker', async ({page, baseURL}) => {
  const requests: string[] = []
  page.on('request', (request) => requests.push(request.url()))
  await page.goto('/')
  await expect(page.getByRole('heading', {name: 'All systems operational'})).toBeVisible()

  const expectedOrigin = new URL(baseURL ?? 'http://127.0.0.1:4173').origin
  expect([...new Set(requests.map((url) => new URL(url).origin))]).toEqual([expectedOrigin])
  expect(await page.evaluate(() => navigator.serviceWorker.getRegistrations().then((items) => items.length))).toBe(0)
})

test('uses roving keyboard focus for the complete 90-day histories', async ({page}) => {
  await page.goto('/')
  await expect(page.locator('.history-bar[tabindex="0"]')).toHaveCount(5)
  await expect(page.locator('.history-bar[tabindex="-1"]')).toHaveCount(445)

  const bars = page.locator('.component-card').first().locator('.history-bar')
  await bars.nth(89).focus()
  await bars.nth(89).press('ArrowLeft')
  await expect(bars.nth(88)).toBeFocused()
  await bars.nth(88).press('Home')
  await expect(bars.first()).toBeFocused()
  await bars.first().press('End')
  await expect(bars.last()).toBeFocused()
})

test('all overall states retain text labels and pass automated accessibility checks', async ({page}) => {
  const states = [
    ['degraded', 'Some systems are degraded'],
    ['partial_outage', 'Some systems are unavailable'],
    ['major_outage', 'Major service outage'],
    ['maintenance', 'Maintenance in progress'],
    ['unknown', 'Current status is unavailable'],
  ] as const

  for (const [status, heading] of states) {
    await page.unroute('**/api/status')
    await page.route('**/api/status', (route) =>
      route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(statusFixture(status))}),
    )
    await page.goto('/')
    await expect(page.getByRole('heading', {name: heading})).toBeVisible()
    const results = await new AxeBuilder({page}).analyze()
    expect(results.violations).toEqual([])
  }
})

test('fits the mobile viewport without horizontal page overflow', async ({page}, testInfo) => {
  test.skip(!testInfo.project.name.includes('mobile'), 'mobile-only layout assertion')
  await page.goto('/')
  await expect(page.getByRole('heading', {name: 'All systems operational'})).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})

test('reflows at a 320px viewport without dropping any history day', async ({page}) => {
  await page.setViewportSize({width: 320, height: 800})
  await page.goto('/')
  await expect(page.locator('.history-bar')).toHaveCount(450)
  const campusLogo = page.getByRole('img', {name: 'UC Merced'})
  await expect(campusLogo).toBeInViewport()
  const [brandBox, affiliationBox] = await Promise.all([
    page.locator('.brand').boundingBox(),
    page.locator('.header-affiliation').boundingBox(),
  ])
  expect(brandBox).not.toBeNull()
  expect(affiliationBox).not.toBeNull()
  expect(affiliationBox!.y).toBeGreaterThanOrEqual(brandBox!.y + brandBox!.height - 1)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})

test('keeps an explanatory shell when JavaScript is unavailable', async ({browser, baseURL}) => {
  const context = await browser.newContext({javaScriptEnabled: false})
  const page = await context.newPage()
  await page.goto(baseURL ?? 'http://127.0.0.1:4173')

  await expect(page.getByRole('heading', {name: 'Checking system status'})).toBeVisible()
  await expect(page.getByRole('img', {name: 'UC Merced'})).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('JavaScript is required to retrieve live status data')
  await context.close()
})
