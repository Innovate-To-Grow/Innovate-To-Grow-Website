import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {chromium} from '@playwright/test';
import {installSyntheticRoutes} from './homepage-fixtures.mjs';

const DEFAULT_RUNS = 5;
const DEFAULT_URL = 'http://127.0.0.1:4173/';
const DEFAULT_OUTPUT = 'test-results/performance/homepage-slow-3g.json';
const LATENCY_MS = 400;
const THROUGHPUT_KBPS = 400;
// CDP expects bytes/second. Network kbps is decimal: 400,000 bits / 8.
const THROUGHPUT_BYTES_PER_SECOND = (THROUGHPUT_KBPS * 1000) / 8;
const MARKER_SELECTOR = '#performance-homepage-marker';
const YOUTUBE_HOST_PATTERN = /(^|\.)(youtube\.com|youtube-nocookie\.com|ytimg\.com|googlevideo\.com)$/i;

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
