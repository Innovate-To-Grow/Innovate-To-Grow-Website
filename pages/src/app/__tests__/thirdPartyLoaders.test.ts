import {afterEach, describe, expect, it} from 'vitest';

import {
  loadFontAwesomeStylesheet,
  loadThirdPartyScripts,
  markIsolatedIframeRoute,
} from '../thirdPartyLoaders';

const LOADER_IDS = [
  'i2g-font-awesome-stylesheet',
  'i2g-userway-loader',
  'i2g-siteimprove-loader',
];

afterEach(() => {
  for (const id of LOADER_IDS) {
    document.getElementById(id)?.remove();
  }
  delete document.documentElement.dataset.blockPreview;
});

describe('loadFontAwesomeStylesheet', () => {
  it('preloads the local stylesheet and applies it after loading', () => {
    loadFontAwesomeStylesheet();

    const link = document.getElementById(
      'i2g-font-awesome-stylesheet',
    ) as HTMLLinkElement;
    expect(link.rel).toBe('preload');
    expect(link.as).toBe('style');
    expect(link.href).toBe(
      `${window.location.origin}/static/vendor/font-awesome/4.7.0/css/font-awesome.min.css`,
    );

    link.dispatchEvent(new Event('load'));

    expect(link.rel).toBe('stylesheet');
  });

  it('is idempotent', () => {
    loadFontAwesomeStylesheet();
    loadFontAwesomeStylesheet();

    expect(
      document.querySelectorAll('#i2g-font-awesome-stylesheet'),
    ).toHaveLength(1);
  });
});

describe('loadThirdPartyScripts', () => {
  it('loads exact HTTPS third-party scripts on public routes', () => {
    loadThirdPartyScripts('/about');

    const userway = document.getElementById('i2g-userway-loader') as HTMLScriptElement;
    const siteimprove = document.getElementById('i2g-siteimprove-loader') as HTMLScriptElement;
    expect(userway.src).toBe('https://cdn.userway.org/widget.js');
    expect(userway.dataset.account).toBe('6Uvgvyrrph');
    expect(siteimprove.src).toBe(
      'https://siteimproveanalytics.com/js/siteanalyze_8343.js',
    );
  });

  it.each(['/_block-preview', '/_embed/sponsor-widget'])(
    'does not load scripts in isolated iframe route %s',
    (pathname) => {
      loadThirdPartyScripts(pathname);

      expect(document.getElementById('i2g-userway-loader')).toBeNull();
      expect(document.getElementById('i2g-siteimprove-loader')).toBeNull();
    },
  );

  it('is idempotent', () => {
    loadThirdPartyScripts('/about');
    loadThirdPartyScripts('/about');

    expect(document.querySelectorAll('#i2g-userway-loader')).toHaveLength(1);
    expect(document.querySelectorAll('#i2g-siteimprove-loader')).toHaveLength(1);
  });

  it.each(['/_block-preview', '/_embed/sponsor-widget'])(
    'marks isolated iframe route %s before the app mounts',
    (pathname) => {
      markIsolatedIframeRoute(pathname);

      expect(document.documentElement).toHaveAttribute('data-block-preview');
    },
  );
});
