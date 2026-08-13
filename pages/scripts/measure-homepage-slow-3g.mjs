import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {chromium} from '@playwright/test';

const DEFAULT_RUNS = 5;
const DEFAULT_URL = 'http://127.0.0.1:4173/';
const DEFAULT_OUTPUT = 'test-results/performance/homepage-slow-3g.json';
const LATENCY_MS = 400;
const THROUGHPUT_KBPS = 400;
// CDP expects bytes/second. Network kbps is decimal: 400,000 bits / 8.
const THROUGHPUT_BYTES_PER_SECOND = (THROUGHPUT_KBPS * 1000) / 8;
const MARKER_SELECTOR = '#performance-homepage-marker';
const YOUTUBE_HOST_PATTERN = /(^|\.)(youtube\.com|youtube-nocookie\.com|ytimg\.com|googlevideo\.com)$/i;

const layoutFixture = {
  menus: [
    {
      id: 'performance-main-menu',
      name: 'Main menu',
      display_name: 'Main menu',
      description: 'Synthetic local navigation fixture',
      items: [
        {type: 'home', title: 'Home', url: '/', open_in_new_tab: false, children: []},
        {type: 'app', title: 'Projects', url: '/projects', open_in_new_tab: false, children: []},
      ],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ],
  footer: {
    id: 'performance-footer',
    name: 'Performance footer',
    slug: 'performance-footer',
    content: {
      columns: [{title: 'Innovate to Grow', body_html: '<p>UC Merced School of Engineering</p>'}],
      copyright: 'Innovate to Grow',
    },
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  homepage_route: '/',
};

const homepageFixture = {
  slug: 'home',
  route: '/',
  title: 'Home',
  page_css_class: 'cms-page performance-homepage',
  page_css: '',
  meta_description: 'Synthetic local homepage used for repeatable performance measurement.',
  blocks: [
    {
      block_type: 'rich_text',
      sort_order: 0,
      data: {
        heading: 'Innovate to Grow',
        heading_level: 1,
        body_html: [
          '<div id="performance-homepage-marker">',
          '<p>Connecting UC Merced students with industry and community partners.</p>',
          '<iframe src="https://www.youtube-nocookie.com/embed/performance-fixture" title="Program overview"></iframe>',
          '</div>',
        ].join(''),
      },
    },
    {
      block_type: 'navigation_grid',
      sort_order: 1,
      data: {
        heading: 'Explore Innovate to Grow',
        items: [
          {title: 'Projects', description: 'Discover student projects.', url: '/projects'},
          {title: 'Events', description: 'Find upcoming showcase events.', url: '/events'},
        ],
      },
    },
  ],
};

function parseArguments(argv) {
  const options = {url: DEFAULT_URL, runs: DEFAULT_RUNS, output: DEFAULT_OUTPUT};
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--url') options.url = argv[++index];
    else if (argument === '--runs') options.runs = Number(argv[++index]);
    else if (argument === '--output') options.output = argv[++index];
    else if (argument === '--help') options.help = true;
    else throw new Error(`Unknown argument: ${argument}`);
  }
  if (!Number.isInteger(options.runs) || options.runs < 1) {
    throw new Error('--runs must be a positive integer.');
  }
  new URL(options.url);
  return options;
}

function printHelp() {
  process.stdout.write(`Usage: npm run perf:homepage -- [options]\n\nOptions:\n  --url <url>       Preview homepage URL (default: ${DEFAULT_URL})\n  --runs <count>    Number of cold runs (default: ${DEFAULT_RUNS})\n  --output <path>   JSON result path (default: ${DEFAULT_OUTPUT})\n  --help            Show this help\n`);
}

function median(values) {
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function fixtureFor(pathname) {
  if (pathname === '/api/layout/') return layoutFixture;
  if (pathname === '/api/cms/homepage/') return homepageFixture;
  // Older preview builds may still resolve the homepage through the generic
  // CMS route; keep the fixture deterministic across either application build.
  if (pathname === '/api/cms/pages/') return homepageFixture;
  if (pathname === '/api/cms/embed-hosts/') {
    return {hosts: ['www.youtube-nocookie.com'], revision: 'performance-fixture'};
  }
  if (pathname === '/api/health/') {
    return {status: 'ok', database: 'ok', maintenance: false, maintenance_message: ''};
  }
  if (pathname === '/api/assistant/config/') {
    return {
      enabled: false,
      welcome_message: '',
      starter_questions: [],
      unavailable_message: 'Assistant disabled during synthetic performance measurement.',
      max_message_chars: 2000,
    };
  }
  return null;
}

async function installSyntheticRoutes(page, targetOrigin) {
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin === targetOrigin && url.pathname === '/api/analytics/pageview/') {
      await route.fulfill({status: 204});
      return;
    }
    if (url.origin === targetOrigin && url.pathname === '/api/layout/styles.css') {
      await route.fulfill({status: 200, contentType: 'text/css', body: ':root {}'});
      return;
    }
    if (url.origin === targetOrigin && url.pathname.startsWith('/api/')) {
      const fixture = fixtureFor(url.pathname);
      if (!fixture) {
        throw new Error(`Synthetic performance fixture missing for ${url.pathname}`);
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(fixture),
      });
      return;
    }
    if (url.origin !== targetOrigin) {
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
}

async function measureRun(browser, targetUrl, runNumber) {
  const context = await browser.newContext({serviceWorkers: 'block'});
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  const targetOrigin = new URL(targetUrl).origin;
  const requests = new Map();

  await installSyntheticRoutes(page, targetOrigin);
  await page.addInitScript((markerSelector) => {
    window.__performanceMeasurement = {lcpMs: null, meaningfulMarkerMs: null};
    const recordMeaningfulMarker = () => {
      if (
        window.__performanceMeasurement.meaningfulMarkerMs === null
        && document.querySelector(markerSelector)
      ) {
        window.__performanceMeasurement.meaningfulMarkerMs = performance.now();
        return true;
      }
      return false;
    };
    new MutationObserver((_, observer) => {
      if (recordMeaningfulMarker()) observer.disconnect();
    }).observe(document, {childList: true, subtree: true});
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const last = entries.at(-1);
      if (last) window.__performanceMeasurement.lcpMs = last.startTime;
    }).observe({type: 'largest-contentful-paint', buffered: true});
  }, MARKER_SELECTOR);

  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled', {cacheDisabled: true});
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: LATENCY_MS,
    downloadThroughput: THROUGHPUT_BYTES_PER_SECOND,
    uploadThroughput: THROUGHPUT_BYTES_PER_SECOND,
    connectionType: 'cellular3g',
  });
  cdp.on('Network.requestWillBeSent', (event) => {
    requests.set(event.requestId, {
      url: event.request.url,
      transferredBytes: 0,
      failed: false,
    });
  });
  cdp.on('Network.loadingFinished', (event) => {
    const request = requests.get(event.requestId);
    if (request) request.transferredBytes = event.encodedDataLength;
  });
  cdp.on('Network.loadingFailed', (event) => {
    const request = requests.get(event.requestId);
    if (request) request.failed = true;
  });

  const startedAt = new Date().toISOString();
  // The application deliberately loads UserWay immediately. External requests
  // are blocked for deterministic local runs, so wait for the document rather
  // than an external-script-dependent load event.
  await page.goto(targetUrl, {waitUntil: 'domcontentloaded', timeout: 30_000});
  await page.locator(MARKER_SELECTOR).waitFor({state: 'visible', timeout: 30_000});
  const meaningfulHomepageMarkerMs = await page.evaluate(() => (
    window.__performanceMeasurement.meaningfulMarkerMs
  ));
  if (meaningfulHomepageMarkerMs === null) {
    throw new Error(`Run ${runNumber} did not record the meaningful homepage marker.`);
  }
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(2000);

  const paintMetrics = await page.evaluate(() => ({
    fcpMs: performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null,
    lcpMs: window.__performanceMeasurement.lcpMs,
  }));
  if (paintMetrics.fcpMs === null || paintMetrics.lcpMs === null) {
    throw new Error(`Run ${runNumber} did not produce FCP and LCP metrics.`);
  }

  const completedRequests = [...requests.values()].filter((request) => !request.failed);
  const layoutRequest = completedRequests.find((request) => new URL(request.url).pathname === '/api/layout/');
  if (!layoutRequest) throw new Error(`Run ${runNumber} did not request /api/layout/.`);
  const youtubeRequestsBeforeInteraction = [...requests.values()].filter((request) => {
    try {
      return YOUTUBE_HOST_PATTERN.test(new URL(request.url).hostname);
    } catch {
      return false;
    }
  }).length;

  const result = {
    run: runNumber,
    started_at: startedAt,
    fcp_ms: paintMetrics.fcpMs,
    meaningful_homepage_marker_ms: meaningfulHomepageMarkerMs,
    lcp_ms: paintMetrics.lcpMs,
    transferred_bytes: completedRequests.reduce((total, request) => total + request.transferredBytes, 0),
    request_count: requests.size,
    youtube_requests_before_interaction: youtubeRequestsBeforeInteraction,
    layout_transfer_bytes: layoutRequest.transferredBytes,
  };
  await context.close();
  return result;
}

const options = parseArguments(process.argv.slice(2));
if (options.help) {
  printHelp();
  process.exit(0);
}

const browser = await chromium.launch({headless: true});
const runs = [];
try {
  for (let run = 1; run <= options.runs; run += 1) {
    process.stderr.write(`Measuring synthetic/local Slow 3G run ${run}/${options.runs}...\n`);
    runs.push(await measureRun(browser, options.url, run));
  }
} finally {
  await browser.close();
}

const metricKeys = [
  'fcp_ms',
  'meaningful_homepage_marker_ms',
  'lcp_ms',
  'transferred_bytes',
  'request_count',
  'youtube_requests_before_interaction',
  'layout_transfer_bytes',
];
const medians = Object.fromEntries(metricKeys.map((key) => [key, median(runs.map((run) => run[key]))]));
const report = {
  schema_version: 1,
  measurement: 'synthetic/local',
  description: 'Fixture-backed local homepage measurement; public API responses are intercepted and no CMS/DB data is mutated.',
  generated_at: new Date().toISOString(),
  target_url: options.url,
  browser: 'chromium',
  cache: 'cold browser context per run; HTTP cache disabled; service workers blocked',
  network: {
    profile: 'Slow 3G',
    latency_ms: LATENCY_MS,
    download_kbps: THROUGHPUT_KBPS,
    upload_kbps: THROUGHPUT_KBPS,
    throughput_bytes_per_second: THROUGHPUT_BYTES_PER_SECOND,
  },
  meaningful_marker: MARKER_SELECTOR,
  runs,
  median: medians,
};
const outputPath = path.resolve(options.output);
await mkdir(path.dirname(outputPath), {recursive: true});
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`);
process.stdout.write(`${JSON.stringify(report)}\n`);
process.stderr.write(`Wrote ${outputPath}\n`);
