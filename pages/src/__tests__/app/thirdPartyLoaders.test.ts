import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {
  loadThirdPartyScripts,
  markIsolatedIframeRoute,
} from '@/app/thirdPartyLoaders';

const LOADER_IDS = ['i2g-userway-loader', 'i2g-siteimprove-loader'];

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  for (const id of LOADER_IDS) document.getElementById(id)?.remove();
  delete document.documentElement.dataset.blockPreview;
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('loadThirdPartyScripts', () => {
  it('loads UserWay immediately and defers SiteImprove', () => {
    loadThirdPartyScripts('/about');

    const userway = document.getElementById('i2g-userway-loader') as HTMLScriptElement;
    expect(userway.src).toBe('https://cdn.userway.org/widget.js');
    expect(userway.dataset.account).toBe('6Uvgvyrrph');
    expect(document.getElementById('i2g-siteimprove-loader')).toBeNull();

    window.dispatchEvent(new Event('load'));
    vi.advanceTimersByTime(1500);
    const siteimprove = document.getElementById('i2g-siteimprove-loader') as HTMLScriptElement;
    expect(siteimprove.src).toBe('https://siteimproveanalytics.com/js/siteanalyze_8343.js');
  });

  it('rechecks the current route before the delayed SiteImprove load', () => {
    window.history.replaceState({}, '', '/about');
    loadThirdPartyScripts('/about');

    window.history.replaceState({}, '', '/_embed/sponsor-widget');
    window.dispatchEvent(new Event('load'));
    vi.advanceTimersByTime(1500);

    expect(document.getElementById('i2g-userway-loader')).not.toBeNull();
    expect(document.getElementById('i2g-siteimprove-loader')).toBeNull();
  });

  it.each([
    ['/_block-preview', ''],
    ['/_embed/sponsor-widget', ''],
    ['/about', '?_isolated=1'],
  ])('does not load scripts in isolated route %s%s', (pathname, search) => {
    loadThirdPartyScripts(pathname, search);
    window.dispatchEvent(new Event('load'));
    vi.runAllTimers();

    expect(document.getElementById('i2g-userway-loader')).toBeNull();
    expect(document.getElementById('i2g-siteimprove-loader')).toBeNull();
  });

  it.each([
    ['/_block-preview', ''],
    ['/_embed/sponsor-widget', ''],
    ['/about', '?_isolated=1'],
  ])('marks isolated route %s%s before the app mounts', (pathname, search) => {
    markIsolatedIframeRoute(pathname, search);
    expect(document.documentElement).toHaveAttribute('data-block-preview');
  });
});
